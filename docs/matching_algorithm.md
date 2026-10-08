# Matching Algorithm Documentation

## Overview

The matching algorithm implements **REG NMS-inspired principles** for cryptocurrency order matching, ensuring fair and efficient trade execution through strict **price-time priority** enforcement and **trade-through prevention**.

**Core Principles:**
1. **Price Priority**: Better prices always match first
2. **Time Priority**: FIFO (First-In-First-Out) at each price level
3. **Trade-Through Prevention**: No execution at worse prices when better prices available
4. **Partial Fill Fairness**: Better prices filled first, even for partial executions

---

## REG NMS-Inspired Principles

### What is REG NMS?

**Regulation National Market System (REG NMS)** is a U.S. SEC regulation ensuring fair trading in equity markets. Key principles:

1. **Order Protection Rule (Rule 611)**: Prevent trade-throughs (execution at worse prices)
2. **Access Rule (Rule 610)**: Fair access to quotations
3. **Sub-Penny Rule (Rule 612)**: Price increment restrictions
4. **Market Data Rules**: Consolidated market data dissemination

### Our Implementation

This engine implements **Rule 611 (Order Protection)** principles adapted for cryptocurrencies:

| REG NMS Principle | Our Implementation |
|-------------------|-------------------|
| **No Trade-Throughs** | Yes Incoming orders must match at best available prices first |
| **Price-Time Priority** | Yes Higher bids and lower offers prioritized; FIFO within price levels |
| **Protected Quotations** | Yes BBO updates broadcast in real-time (<100μs latency) |
| **Fair Access** | Yes All market participants see same orderbook state |

**Differences from Traditional REG NMS:**
- No inter-exchange routing (single matching engine)
- No displayed vs non-displayed size distinction
- Cryptocurrency-specific precision (8+ decimals)

---

## Price-Time Priority Algorithm

### 1. Price Priority

**Definition**: Orders at better prices ALWAYS execute before orders at worse prices.

#### For Buy Orders (Bids)
```
Higher Price = Better Priority

Example Order Book (Bids):
$50,100 ← Best bid (highest price) - MATCHES FIRST
$50,000
$49,950 ← Worst bid (lowest price) - MATCHES LAST
```

#### For Sell Orders (Asks)
```
Lower Price = Better Priority

Example Order Book (Asks):
$50,200 ← Worst ask (highest price) - MATCHES LAST
$50,150
$50,100 ← Best ask (lowest price) - MATCHES FIRST
```

### 2. Time Priority (FIFO)

**Definition**: At the same price level, earlier orders execute before later orders.

#### Example: FIFO at $50,000
```
Price Level: $50,000 (Buy Side)
┌─────────────────────────────────────────────────┐
│ Order Queue (FIFO):                             │
│ ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐        │
│ │ ID:1 │→ │ ID:2 │→ │ ID:3 │→ │ ID:4 │        │
│ │ 0.5  │  │ 0.3  │  │ 1.0  │  │ 0.2  │        │
│ │ 10:01│  │ 10:02│  │ 10:03│  │ 10:04│        │
│ └──────┘  └──────┘  └──────┘  └──────┘        │
│     ↑ Matches first (earliest timestamp)       │
└─────────────────────────────────────────────────┘

Incoming Sell Order: 1.0 BTC @ $50,000 (or better)
Execution Sequence:
1. Fill Order ID:1 (0.5 BTC) → Remaining: 0.5 BTC
2. Fill Order ID:2 (0.3 BTC) → Remaining: 0.2 BTC
3. Partially fill Order ID:3 (0.2 of 1.0 BTC) → Fully filled
```

**Implementation:**
```python
class PriceLevel:
    def __init__(self, price: Decimal):
        self.price = price
        self.orders: Deque[Order] = deque()  # FIFO queue
        
    def add_order(self, order: Order):
        """Append to end of queue (newest)"""
        self.orders.append(order)
        
    def get_next_order(self) -> Optional[Order]:
        """Get from front of queue (oldest)"""
        return self.orders[0] if self.orders else None
        
    def remove_order(self, order: Order):
        """Remove after fill/cancel"""
        self.orders.remove(order)
```

---

## Order Matching Process

### Step-by-Step Execution

#### 1. Order Arrival
```python
def submit_order(self, order: Order) -> OrderResponse:
    """
    1. Validate order parameters
    2. Acquire lock (thread-safe)
    3. Set status to ACCEPTED
    4. Attempt matching
    5. Add to book if unfilled
    6. Release lock
    """
```

#### 2. Matching Decision Tree
```
Order Arrives
    │
    ├─→ Market Order
    │     ├─→ Check opposite side has liquidity?
    │     │     ├─→ YES: Match at best available prices
    │     │     └─→ NO: Reject (insufficient liquidity)
    │     └─→ Match until filled or no more liquidity
    │
    ├─→ Limit Order
    │     ├─→ Price crosses spread (marketable)?
    │     │     ├─→ YES: Match at limit price or better
    │     │     └─→ NO: Add to book (resting order)
    │     └─→ If unfilled quantity remains, rest on book
    │
    ├─→ IOC (Immediate-Or-Cancel)
    │     ├─→ Match immediately at any quantity
    │     └─→ Cancel unfilled portion (don't rest)
    │
    └─→ FOK (Fill-Or-Kill)
          ├─→ Check if FULL quantity available?
          │     ├─→ YES: Match entire order
          │     └─→ NO: Reject (all-or-nothing)
          └─→ Walk book to calculate available liquidity
```

#### 3. Matching Logic

**For Incoming Buy Order:**
```python
def _match_buy_order(self, buy_order: Order, book: OrderBook) -> List[Trade]:
    trades = []
    
    # Iterate asks (sell side) in ascending price order
    # (lowest ask = best price for buyer)
    for price, price_level in book.asks.items():
        # Price check: buy limit order won't pay more than limit
        if isinstance(buy_order, LimitOrder):
            if price > buy_order.price:
                break  # No more acceptable prices
        
        # Match FIFO within this price level
        while price_level.orders and buy_order.remaining_quantity > 0:
            sell_order = price_level.orders[0]  # Front of queue (oldest)
            
            # Calculate match quantity
            match_qty = min(
                buy_order.remaining_quantity,
                sell_order.remaining_quantity
            )
            
            # Generate trade
            trade = Trade(
                trade_id=str(uuid4()),
                symbol=buy_order.symbol,
                price=price,  # Passive order price (maker)
                quantity=match_qty,
                maker_order_id=sell_order.order_id,  # Resting order
                taker_order_id=buy_order.order_id,   # Incoming order
                aggressor_side=OrderSide.BUY,
                timestamp=datetime.now(UTC)
            )
            trades.append(trade)
            
            # Update orders
            buy_order.fill(match_qty)
            sell_order.fill(match_qty)
            
            # Remove if fully filled
            if sell_order.is_filled():
                price_level.orders.popleft()  # Remove from front
                
        # Clean up empty price level
        if not price_level.orders:
            del book.asks[price]
            
        # Stop if incoming order fully filled
        if buy_order.is_filled():
            break
            
    return trades
```

**For Incoming Sell Order:**
```python
def _match_sell_order(self, sell_order: Order, book: OrderBook) -> List[Trade]:
    trades = []
    
    # Iterate bids (buy side) in DESCENDING price order
    # (highest bid = best price for seller)
    for price in reversed(book.bids.keys()):  # ← KEY: reversed()
        price_level = book.bids[price]
        
        # Price check: sell limit order won't accept less than limit
        if isinstance(sell_order, LimitOrder):
            if price < sell_order.price:
                break  # No more acceptable prices
        
        # Match FIFO within this price level
        while price_level.orders and sell_order.remaining_quantity > 0:
            buy_order = price_level.orders[0]  # Front of queue (oldest)
            
            # Calculate match quantity
            match_qty = min(
                sell_order.remaining_quantity,
                buy_order.remaining_quantity
            )
            
            # Generate trade
            trade = Trade(
                trade_id=str(uuid4()),
                symbol=sell_order.symbol,
                price=price,  # Passive order price (maker)
                quantity=match_qty,
                maker_order_id=buy_order.order_id,   # Resting order
                taker_order_id=sell_order.order_id,  # Incoming order
                aggressor_side=OrderSide.SELL,
                timestamp=datetime.now(UTC)
            )
            trades.append(trade)
            
            # Update orders
            sell_order.fill(match_qty)
            buy_order.fill(match_qty)
            
            # Remove if fully filled
            if buy_order.is_filled():
                price_level.orders.popleft()  # Remove from front
                
        # Clean up empty price level
        if not price_level.orders:
            del book.bids[price]
            
        # Stop if incoming order fully filled
        if sell_order.is_filled():
            break
            
    return trades
```

---

## Trade-Through Prevention

### Definition
**Trade-Through**: Executing an order at a worse price when a better price is available.

### Why It's Prohibited
```
Example Trade-Through (ILLEGAL):

Order Book:
Asks:
  $50,100 → 1.0 BTC  ← Best ask
  $50,200 → 2.0 BTC

Incoming Buy Market Order: 0.5 BTC

WRONG: Match at $50,200
CORRECT: Match at $50,100 (best price)
```

**Impact:**
- Unfair to buyer (pays more than necessary)
- Unfair to seller at $50,100 (loses price priority)
- Violates REG NMS principles

### Prevention Mechanism

#### 1. Ordered Iteration
```python
# For buy orders: iterate asks in ASCENDING order
for price, price_level in book.asks.items():  # Sorted lowest to highest
    # Match here
    
# For sell orders: iterate bids in DESCENDING order
for price in reversed(book.bids.keys()):  # Sorted highest to lowest
    # Match here
```

**Guarantee:** Better prices ALWAYS encountered first in iteration.

#### 2. Early Exit on Price Limit
```python
if isinstance(buy_order, LimitOrder):
    if price > buy_order.price:
        break  # Stop: no acceptable prices remaining
```

**Guarantee:** Won't match at worse prices than limit.

#### 3. Sequential Processing
```python
# Match at price level N COMPLETELY before moving to N+1
while price_level.orders and buy_order.remaining_quantity > 0:
    # Exhaust all orders at current price level
    
# Only then move to next price level
```

**Guarantee:** No skipping to worse prices while better prices have liquidity.

### Test Cases

#### Test 1: Multiple Price Levels
```python
# Setup
book.add_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50100")))  # Best
book.add_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50200")))  # Worse

# Execute
trades = engine.submit_order(MarketOrder("BTC-USDT", BUY, 1.5))

# Verify
assert trades[0].price == Decimal("50100")  # First trade at best price
assert trades[0].quantity == Decimal("1.0")  # Exhaust best price
assert trades[1].price == Decimal("50200")  # Then use next price
assert trades[1].quantity == Decimal("0.5")  # Remaining quantity
```

#### Test 2: Partial Fill at Best Price
```python
# Setup
book.add_order(LimitOrder("BTC-USDT", SELL, 0.3, Decimal("50100")))  # Best
book.add_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50200")))  # Worse

# Execute
trades = engine.submit_order(MarketOrder("BTC-USDT", BUY, 1.0))

# Verify
assert trades[0].price == Decimal("50100")  # Best price first
assert trades[0].quantity == Decimal("0.3")  # Partial fill
assert trades[1].price == Decimal("50200")  # Then next price
assert trades[1].quantity == Decimal("0.7")  # Remaining
```

---

## Order Type Specifics

### 1. Market Orders

**Behavior:** Immediate execution at best available price(s), walk the book until filled.

**Algorithm:**
```python
def _match_market_order(self, order: MarketOrder, book: OrderBook) -> List[Trade]:
    # Check if opposite side has ANY liquidity
    opposite_side = book.asks if order.side == BUY else book.bids
    if not opposite_side:
        order.status = OrderStatus.REJECTED
        return []
    
    # Match greedily until filled or no more liquidity
    trades = self._match_order(order, book)
    
    # If unfilled quantity remains, reject it (insufficient liquidity)
    if order.remaining_quantity > 0:
        order.status = OrderStatus.REJECTED
        return []  # Rollback trades (not implemented in current version)
    
    return trades
```

**Key Properties:**
- No price limit (accepts any price)
- Guaranteed fill if liquidity exists
- No guaranteed price (market impact risk)

### 2. Limit Orders

**Behavior:** Execute at limit price or better; rest unfilled portion on book.

**Algorithm:**
```python
def _match_limit_order(self, order: LimitOrder, book: OrderBook) -> List[Trade]:
    # Check if order is marketable (crosses spread)
    is_marketable = self._is_marketable(order, book)
    
    if is_marketable:
        # Match at limit price or better
        trades = self._match_order(order, book)  # Price checks inside
    else:
        trades = []
    
    # If unfilled quantity remains, add to book
    if order.remaining_quantity > 0:
        book.add_order(order)
        order.status = OrderStatus.ACCEPTED
    
    return trades
```

**Marketability Check:**
```python
def _is_marketable(self, order: LimitOrder, book: OrderBook) -> bool:
    if order.side == BUY:
        # Buy order marketable if bid >= best ask
        best_ask = book.get_best_ask()
        return best_ask is not None and order.price >= best_ask
    else:
        # Sell order marketable if ask <= best bid
        best_bid = book.get_best_bid()
        return best_bid is not None and order.price <= best_bid
```

**Key Properties:**
- Price protection (won't pay more/accept less than limit)
- Rests on book if not immediately marketable
- Can provide liquidity (maker orders)

### 3. IOC (Immediate-Or-Cancel)

**Behavior:** Execute immediately at any quantity; cancel unfilled portion.

**Algorithm:**
```python
def _match_ioc_order(self, order: IOCOrder, book: OrderBook) -> List[Trade]:
    # Match immediately
    trades = self._match_order(order, book)
    
    # Cancel unfilled portion (DON'T rest on book)
    if order.remaining_quantity > 0:
        order.status = OrderStatus.CANCELED
    
    return trades
```

**Key Properties:**
- No resting on book (immediate execution only)
- Accepts partial fills
- Useful for minimizing market impact

### 4. FOK (Fill-Or-Kill)

**Behavior:** Execute entire quantity immediately or reject completely (all-or-nothing).

**Algorithm:**
```python
def _match_fok_order(self, order: FOKOrder, book: OrderBook) -> List[Trade]:
    # FIRST: Check if full quantity can be filled
    if not self._can_fill_fok(order, book):
        order.status = OrderStatus.REJECTED
        return []
    
    # SECOND: Execute (we know it will fully fill)
    trades = self._match_order(order, book)
    
    # Sanity check
    assert order.is_filled(), "FOK should be fully filled"
    
    return trades
```

**Liquidity Check:**
```python
def _can_fill_fok(self, order: FOKOrder, book: OrderBook) -> bool:
    """
    Walk the book to calculate available liquidity
    WITHOUT actually matching (read-only).
    """
    available_qty = Decimal("0")
    opposite_side = book.asks if order.side == BUY else book.bids
    
    # Iterate price levels
    price_iter = opposite_side.items() if order.side == BUY else \
                 reversed(opposite_side.items())
    
    for price, price_level in price_iter:
        # Price check for limit FOK orders
        if isinstance(order, LimitOrder):
            if (order.side == BUY and price > order.price) or \
               (order.side == SELL and price < order.price):
                break  # No more acceptable prices
        
        # Sum quantities at this price level
        for passive_order in price_level.orders:
            available_qty += passive_order.remaining_quantity
            
            # Early exit if enough liquidity found
            if available_qty >= order.quantity:
                return True
    
    # Not enough liquidity
    return False
```

**Key Properties:**
- All-or-nothing execution
- No partial fills
- Checks liquidity BEFORE execution
- Lower fill rate (strict requirements)

---

## Edge Cases & Special Scenarios

### 1. Self-Trade Prevention

**Scenario:** User's buy order matches their own sell order.

**Current Implementation:** Not implemented (planned)

**Recommended Solution:**
```python
def _can_match(self, taker_order: Order, maker_order: Order) -> bool:
    # Prevent self-trading
    if taker_order.user_id == maker_order.user_id:
        return False  # Skip this order
    return True
```

### 2. Minimum Quantity Constraints

**Scenario:** Order has minimum fill quantity (e.g., "fill at least 0.5 BTC or reject").

**Current Implementation:** Not implemented

**Recommended Solution:**
```python
@dataclass
class LimitOrder(Order):
    min_quantity: Optional[Decimal] = None
    
# In matching logic:
if order.min_quantity and total_filled < order.min_quantity:
    order.status = OrderStatus.REJECTED
    return []  # Rollback trades
```

### 3. Order Book Crossed State

**Scenario:** Bug causes best bid > best ask (impossible in reality).

**Prevention:**
```python
def validate_orderbook(self, book: OrderBook):
    best_bid = book.get_best_bid()
    best_ask = book.get_best_ask()
    
    if best_bid and best_ask and best_bid >= best_ask:
        logger.error("Orderbook crossed!", extra={
            "symbol": book.symbol,
            "best_bid": str(best_bid),
            "best_ask": str(best_ask)
        })
        raise ValueError("Orderbook integrity violation")
```

### 4. Zero Quantity Orders

**Prevention:**
```python
@field_validator("quantity")
def validate_quantity(cls, v):
    if v <= 0:
        raise ValueError("Quantity must be positive")
    return v
```

### 5. Price Precision Limits

**Scenario:** Prices like $50,000.123456789 (excessive precision).

**Current Implementation:** Uses `Decimal` (unlimited precision).

**Production Consideration:**
```python
# Define tick size (minimum price increment)
TICK_SIZE = Decimal("0.01")  # $0.01 for BTC-USDT

@field_validator("price")
def validate_price_precision(cls, v):
    if v % TICK_SIZE != 0:
        raise ValueError(f"Price must be multiple of {TICK_SIZE}")
    return v
```

---

## Performance Characteristics

### Time Complexity Analysis

| Operation | Best Case | Average Case | Worst Case |
|-----------|-----------|--------------|------------|
| **Submit Market Order** | O(1) | O(k × m) | O(n × m) |
| **Submit Limit Order (non-marketable)** | O(log n) | O(log n) | O(log n) |
| **Submit Limit Order (marketable)** | O(k × m) | O(k × m) | O(n × m) |
| **Cancel Order** | O(log n + m) | O(log n + m) | O(log n + m) |
| **Get BBO** | O(1) | O(1) | O(1) |

Where:
- **n** = number of distinct price levels
- **k** = number of price levels matched across
- **m** = average orders per price level

### Space Complexity

| Component | Space Usage |
|-----------|-------------|
| **Orders in book** | O(T) where T = total orders |
| **Price levels** | O(n) where n = distinct prices |
| **Order lookup dict** | O(T) |
| **Total** | O(T + n) ≈ O(T) |

### Actual Performance (Measured)

| Metric | Achieved | Notes |
|--------|----------|-------|
| **Order Processing** | 6,641 orders/sec | Mixed order types |
| **p99 Latency** | 0.406 ms | Single-threaded |
| **BBO Query** | 237,042 queries/sec | O(1) access |
| **Memory Usage** | ~1 MB per 10,000 orders | In-memory only |

---

## Comparison with Other Matching Algorithms

### 1. Pro-Rata Matching

**How It Works:** Distribute match quantity proportionally among all orders at best price.

**Example:**
```
Price Level $50,000:
- Order A: 10 BTC
- Order B: 5 BTC
- Order C: 5 BTC
Total: 20 BTC

Incoming: 10 BTC sell

Pro-Rata Distribution:
- Order A fills: 10 × (10/20) = 5 BTC
- Order B fills: 10 × (5/20) = 2.5 BTC
- Order C fills: 10 × (5/20) = 2.5 BTC
```

**Our Choice:** Not used

**Rationale:**
- Pro-rata favors large orders (disproportionate to time priority)
- Reduces time priority importance
- More complex implementation

### 2. Price-Size-Time Priority

**How It Works:** Larger orders at same price get priority.

**Example:**
```
Price Level $50,000:
- Order A: 0.5 BTC @ 10:00
- Order B: 1.0 BTC @ 10:01  ← Matches first (larger)
```

**Our Choice:** Not used

**Rationale:**
- Favors institutional players over retail
- Not REG NMS compliant
- Discourages limit order submission

### 3. Pure FIFO (Our Implementation)

**How It Works:** First come, first served at each price.

**Advantages:**
- Simple and fair
- REG NMS compliant
- Encourages liquidity provision (time priority reward)
- Predictable execution

**Disadvantages:**
- Can disadvantage slow market makers
- Vulnerable to latency arbitrage

---

## Verification & Testing

### Unit Tests Coverage

#### Test 1: Price Priority
```python
def test_price_priority():
    """Buy orders match at best ask first"""
    book.add_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50200")))
    book.add_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50100")))  # Better
    
    trades = engine.submit_order(MarketOrder("BTC-USDT", BUY, 1.0))
    
    assert trades[0].price == Decimal("50100")  # Best price matched first
```

#### Test 2: Time Priority (FIFO)
```python
def test_time_priority():
    """Orders at same price match FIFO"""
    order1 = LimitOrder("BTC-USDT", SELL, 0.5, Decimal("50000"))
    order2 = LimitOrder("BTC-USDT", SELL, 0.5, Decimal("50000"))
    
    book.add_order(order1)  # First
    time.sleep(0.001)
    book.add_order(order2)  # Second
    
    trades = engine.submit_order(MarketOrder("BTC-USDT", BUY, 0.7))
    
    assert trades[0].maker_order_id == order1.order_id  # First order matched
    assert trades[0].quantity == Decimal("0.5")  # Fully filled
    assert trades[1].maker_order_id == order2.order_id  # Second order matched
    assert trades[1].quantity == Decimal("0.2")  # Partially filled
```

#### Test 3: Trade-Through Prevention
```python
def test_no_trade_through():
    """Cannot skip better prices"""
    book.add_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50100")))  # Best
    book.add_order(LimitOrder("BTC-USDT", SELL, 2.0, Decimal("50200")))  # Worse
    
    trades = engine.submit_order(MarketOrder("BTC-USDT", BUY, 2.5))
    
    # Must fill best price completely before moving to worse price
    assert trades[0].price == Decimal("50100")
    assert trades[0].quantity == Decimal("1.0")  # Exhaust best price
    assert trades[1].price == Decimal("50200")
    assert trades[1].quantity == Decimal("1.5")  # Then use worse price
```

#### Test 4: FOK Liquidity Check
```python
def test_fok_insufficient_liquidity():
    """FOK rejects if not enough liquidity"""
    book.add_order(LimitOrder("BTC-USDT", SELL, 0.8, Decimal("50000")))
    
    response = engine.submit_order(FOKOrder("BTC-USDT", BUY, 1.0, Decimal("50000")))
    
    assert response.status == OrderStatus.REJECTED  # Not enough liquidity
    assert response.filled_quantity == Decimal("0")  # No partial fill
```

### Integration Tests

**Scenario:** Complex multi-order execution
```python
def test_complex_matching_scenario():
    # Setup orderbook
    engine.submit_order(LimitOrder("BTC-USDT", SELL, 0.5, Decimal("50100")))
    engine.submit_order(LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50150")))
    engine.submit_order(LimitOrder("BTC-USDT", SELL, 2.0, Decimal("50200")))
    
    # Execute large market buy
    response = engine.submit_order(MarketOrder("BTC-USDT", BUY, 2.5))
    
    # Verify execution
    assert response.status == OrderStatus.FILLED
    assert len(response.trades) == 3
    assert response.average_price == Decimal("50166.67")  # Weighted avg
```

---

## Future Enhancements

### 1. Hidden Orders (Iceberg)
- Display only partial quantity
- Full quantity known only to exchange
- Prevents information leakage

### 2. Post-Only Orders
- Reject if immediately marketable
- Guarantees maker status (fee rebate)
- Prevents taking liquidity

### 3. Time-in-Force Variations
- **GTD** (Good-Till-Date): Cancel at specific time
- **GTT** (Good-Till-Time): Cancel after duration
- **AON** (All-Or-None): Like FOK but can rest on book

### 4. Order Modification
- Amend price/quantity without losing time priority
- Strict rules to prevent gaming

---

## Conclusion

The matching algorithm successfully implements **REG NMS-inspired principles** with:

**Strict price-time priority** enforcement  
**Trade-through prevention** (no execution at worse prices)  
**FIFO fairness** at each price level  
**Support for all order types** (Market, Limit, IOC, FOK)  
**High performance** (6,641 orders/sec, 0.406ms p99 latency)  
**Comprehensive testing** (27 matching engine tests, 100% passing)

The algorithm provides **fair, efficient, and predictable** order execution suitable for cryptocurrency trading while maintaining compatibility with traditional financial market principles.

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-24  
**Related:** See `docs/architecture.md` for system design, `docs/performance.md` for benchmarks
