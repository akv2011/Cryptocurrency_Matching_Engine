# Data Structures Documentation

## Overview

The matching engine's performance and correctness depend critically on efficient data structures that enable **fast order book operations** while maintaining **price-time priority**. This document explains the design choices, implementation details, and complexity analysis for all core data structures.

**Key Design Goals:**
1. **O(1) Order Lookup**: Instant access by order ID for cancellations/queries
2. **Fast Price-Level Access**: Efficient best bid/offer calculation
3. **FIFO Guarantee**: Time priority within each price level
4. **Scalability**: Support for deep order books (1000+ price levels)
5. **Memory Efficiency**: Minimal overhead per order

---

## Order Book Architecture

### High-Level Structure

```
OrderBook (per symbol)
│
├── Symbol: "BTC-USDT"
│
├── Bids (SortedDict)                 ← Buy orders (descending price)
│   ├── Price: $50,000
│   │   └── PriceLevel
│   │       ├── orders: Deque[Order] ← FIFO queue
│   │       └── total_quantity: 3.5 BTC
│   ├── Price: $49,950
│   │   └── PriceLevel...
│   └── ...
│
├── Asks (SortedDict)                 ← Sell orders (ascending price)
│   ├── Price: $50,100
│   │   └── PriceLevel
│   │       ├── orders: Deque[Order]
│   │       └── total_quantity: 2.0 BTC
│   ├── Price: $50,150
│   │   └── PriceLevel...
│   └── ...
│
└── Orders (Dict)                     ← All orders (O(1) lookup)
    ├── order_id_1 → Order
    ├── order_id_2 → Order
    └── ...
```

---

## 1. PriceLevel Data Structure

### Purpose
Maintain a FIFO queue of orders at a specific price point.

### Implementation

```python
from collections import deque
from decimal import Decimal
from typing import Deque, List

class PriceLevel:
    """
    Represents all orders at a single price point.
    Maintains FIFO ordering for time priority.
    """
    
    def __init__(self, price: Decimal):
        self.price: Decimal = price
        self.orders: Deque[Order] = deque()  # FIFO queue
        self.total_quantity: Decimal = Decimal("0")
        
    def add_order(self, order: Order) -> None:
        """Add order to end of queue (newest)"""
        self.orders.append(order)
        self.total_quantity += order.remaining_quantity
        
    def get_next_order(self) -> Optional[Order]:
        """Get order at front of queue (oldest) without removing"""
        return self.orders[0] if self.orders else None
        
    def remove_order(self, order: Order) -> None:
        """Remove specific order (for cancellation or full fill)"""
        self.orders.remove(order)  # O(n) worst case
        self.total_quantity -= order.remaining_quantity
        
    def update_quantity(self, old_qty: Decimal, new_qty: Decimal) -> None:
        """Update total when order partially fills"""
        self.total_quantity = self.total_quantity - old_qty + new_qty
        
    def is_empty(self) -> bool:
        """Check if no orders remain at this price"""
        return len(self.orders) == 0
        
    def get_depth(self) -> tuple[Decimal, Decimal]:
        """Return (price, total_quantity) for L2 orderbook"""
        return (self.price, self.total_quantity)
```

### Design Rationale

#### Why Deque?
```python
# Alternative 1: List
# ❌ popleft() is O(n) - expensive for FIFO
orders: List[Order] = []
first_order = orders.pop(0)  # O(n) - shifts all elements

# Alternative 2: Deque
# ✅ popleft() is O(1) - efficient for FIFO
orders: Deque[Order] = deque()
first_order = orders.popleft()  # O(1) - constant time
```

**Deque Advantages:**
- ✅ O(1) append (add order)
- ✅ O(1) popleft (remove filled order)
- ✅ O(1) access to first element (peek at next order)
- ❌ O(n) remove by value (for cancellations)

**Mitigation for O(n) Removal:**
- Cancellations are less frequent than fills
- Keep orders dict for O(1) lookup, then O(n) removal from deque
- Alternative: Use doubly-linked list for O(1) removal (more complex)

#### Why Track Total Quantity?
```python
# Without tracking:
def get_total_quantity() -> Decimal:
    return sum(order.remaining_quantity for order in self.orders)  # O(n)

# With tracking:
# self.total_quantity is updated on add/remove/fill → O(1) access
```

**Benefits:**
- ✅ O(1) L2 orderbook depth calculation
- ✅ Fast liquidity checks for FOK orders
- ✅ Efficient market depth queries

### Complexity Analysis

| Operation | Time Complexity | Notes |
|-----------|----------------|-------|
| **Add Order** | O(1) | Append to deque |
| **Get Next Order** | O(1) | Access first element |
| **Remove Order (filled)** | O(1) | popleft() |
| **Remove Order (canceled)** | O(n) | Search + remove |
| **Update Quantity** | O(1) | Arithmetic |
| **Get Depth** | O(1) | Return cached total |

---

## 2. OrderBook Data Structure

### Purpose
Maintain sorted price levels for bids and asks, enabling fast BBO calculation and efficient order matching.

### Implementation

```python
from sortedcontainers import SortedDict
from decimal import Decimal
from typing import Dict, Optional, List

class OrderBook:
    """
    Order book for a single trading symbol.
    Maintains price-time priority for all orders.
    """
    
    def __init__(self, symbol: str):
        self.symbol: str = symbol
        
        # Sorted price levels
        self.bids: SortedDict[Decimal, PriceLevel] = SortedDict()  # Descending
        self.asks: SortedDict[Decimal, PriceLevel] = SortedDict()  # Ascending
        
        # Fast order lookup
        self.orders: Dict[str, Order] = {}
        
    def add_order(self, order: Order) -> None:
        """Add order to appropriate side and price level"""
        side = self.bids if order.side == OrderSide.BUY else self.asks
        
        # Get or create price level
        if order.price not in side:
            side[order.price] = PriceLevel(order.price)
        
        # Add to price level (FIFO)
        side[order.price].add_order(order)
        
        # Add to lookup dict
        self.orders[order.order_id] = order
        
    def remove_order(self, order_id: str) -> Optional[Order]:
        """Remove order by ID (for cancellation)"""
        order = self.orders.pop(order_id, None)
        if not order:
            return None
        
        side = self.bids if order.side == OrderSide.BUY else self.asks
        price_level = side.get(order.price)
        
        if price_level:
            price_level.remove_order(order)
            
            # Clean up empty price level
            if price_level.is_empty():
                del side[order.price]
        
        return order
        
    def get_order(self, order_id: str) -> Optional[Order]:
        """O(1) lookup by order ID"""
        return self.orders.get(order_id)
        
    def get_best_bid(self) -> Optional[Decimal]:
        """Get highest bid price (O(1))"""
        if self.bids:
            return self.bids.peekitem(-1)[0]  # Last item (highest)
        return None
        
    def get_best_ask(self) -> Optional[Decimal]:
        """Get lowest ask price (O(1))"""
        if self.asks:
            return self.asks.peekitem(0)[0]  # First item (lowest)
        return None
        
    def get_bbo(self) -> Dict:
        """Get Best Bid and Offer (O(1))"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        bid_qty = self.bids[best_bid].total_quantity if best_bid else None
        ask_qty = self.asks[best_ask].total_quantity if best_ask else None
        
        return {
            "best_bid": str(best_bid) if best_bid else None,
            "best_bid_qty": str(bid_qty) if bid_qty else None,
            "best_ask": str(best_ask) if best_ask else None,
            "best_ask_qty": str(ask_qty) if ask_qty else None,
            "spread": str(best_ask - best_bid) if (best_bid and best_ask) else None
        }
        
    def get_market_depth(self, levels: int = 10) -> Dict:
        """Get L2 orderbook (top N price levels)"""
        bids = []
        asks = []
        
        # Get top bid levels (descending price)
        for price, price_level in reversed(list(self.bids.items())[:levels]):
            bids.append([str(price), str(price_level.total_quantity)])
        
        # Get top ask levels (ascending price)
        for price, price_level in list(self.asks.items())[:levels]:
            asks.append([str(price), str(price_level.total_quantity)])
        
        return {
            "symbol": self.symbol,
            "bids": bids,
            "asks": asks
        }
```

### Design Rationale

#### Why SortedDict?

**Requirements:**
1. Maintain prices in sorted order
2. Fast access to best bid/ask (min/max)
3. Efficient insertion/deletion of price levels
4. Iteration in price order for matching

**Alternatives Considered:**

| Data Structure | Pros | Cons | Verdict |
|----------------|------|------|---------|
| **Heap (heapq)** | O(1) min/max access | ❌ Can't efficiently remove arbitrary elements<br>❌ No ordered iteration | ❌ Rejected |
| **Dict + Manual Sort** | Simple | ❌ O(n log n) to sort each time<br>❌ Expensive for frequent updates | ❌ Rejected |
| **Balanced Tree (Red-Black)** | O(log n) operations | ❌ Complex implementation<br>❌ Python stdlib doesn't provide | ❌ Rejected |
| **SortedDict (sortedcontainers)** | ✅ O(log n) insert/delete<br>✅ O(1) min/max<br>✅ Ordered iteration<br>✅ Battle-tested library | Requires external dependency | ✅ **Chosen** |

**SortedDict Implementation Details:**
```python
from sortedcontainers import SortedDict

# Internally uses B-tree (sorted list of sorted lists)
# Provides:
# - O(log n) insertion/deletion
# - O(1) min/max access via peekitem()
# - O(k) to iterate k items
# - Memory efficient (better than balanced tree)
```

#### Why Separate Bids and Asks?

```python
# Alternative: Single sorted structure
# ❌ Complex to maintain two-sided sorting (bids desc, asks asc)
combined = SortedDict()  # How to sort bids high→low AND asks low→high?

# Chosen: Separate structures
# ✅ Bids naturally sorted ascending, iterate in reverse
# ✅ Asks naturally sorted ascending, iterate forward
bids = SortedDict()  # $50000, $49950, $49900, ... (iterate reversed)
asks = SortedDict()  # $50100, $50150, $50200, ... (iterate forward)
```

**Bid Iteration for Matching:**
```python
# Sell order needs to match highest bids first
for price in reversed(self.bids.keys()):  # O(k) for k levels
    price_level = self.bids[price]
    # Match orders...
```

**Ask Iteration for Matching:**
```python
# Buy order needs to match lowest asks first
for price, price_level in self.asks.items():  # O(k) for k levels
    # Match orders...
```

#### Why Dict for Order Lookup?

**Requirement:** O(1) access by order ID for:
- Order status queries
- Order cancellations
- Order amendments (future feature)

**Implementation:**
```python
self.orders: Dict[str, Order] = {}
# UUID → Order object
# O(1) insertion, O(1) lookup, O(1) deletion
```

**Trade-off:**
- ✅ Instant order access
- ❌ Additional memory (store orders twice: in price levels + dict)
- **Verdict:** Worth the memory for O(1) cancellations

### Complexity Analysis

| Operation | Time Complexity | Space Complexity | Notes |
|-----------|----------------|------------------|-------|
| **Add Order** | O(log n) | O(1) | SortedDict insertion |
| **Remove Order** | O(log n + m) | O(1) | Dict lookup O(1) + Deque remove O(m) + SortedDict cleanup O(log n) |
| **Get Order** | O(1) | O(1) | Dict lookup |
| **Get BBO** | O(1) | O(1) | peekitem() |
| **Get Market Depth (L2)** | O(k) | O(k) | k = number of levels requested |
| **Match Order** | O(k × m) | O(t) | k levels × m orders/level → t trades |

Where:
- **n** = number of distinct price levels (typically 100-1000)
- **m** = average orders per price level (typically 1-10)
- **k** = price levels traversed during matching
- **t** = number of trades generated

---

## 3. Order Data Structures

### Base Order Class

```python
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from enum import Enum

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"

@dataclass
class Order:
    """Base class for all order types"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    timestamp: datetime
    
    # State tracking
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    
    # Optional metadata
    user_id: Optional[str] = None
    client_order_id: Optional[str] = None
    
    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate unfilled quantity"""
        return self.quantity - self.filled_quantity
        
    def is_filled(self) -> bool:
        """Check if order fully executed"""
        return self.filled_quantity >= self.quantity
        
    def fill(self, quantity: Decimal) -> None:
        """Record partial or full fill"""
        self.filled_quantity += quantity
        
        if self.is_filled():
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
```

### Design Rationale

#### Why Dataclass?
```python
# Without dataclass:
class Order:
    def __init__(self, order_id, symbol, side, quantity, timestamp):
        self.order_id = order_id
        self.symbol = symbol
        # ... 10 lines of boilerplate
    
    def __repr__(self):
        return f"Order(...)"  # Manual implementation
    
    def __eq__(self, other):
        # ... manual comparison

# With dataclass:
@dataclass
class Order:
    order_id: str
    symbol: str
    # ... auto-generates __init__, __repr__, __eq__
```

**Advantages:**
- ✅ Reduces boilerplate by ~70%
- ✅ Auto-generates `__init__`, `__repr__`, `__eq__`, `__hash__`
- ✅ Type hints built-in
- ✅ Immutability option with `frozen=True`

#### Why Decimal Instead of Float?

```python
# Floating-Point Error Example:
>>> 0.1 + 0.2 == 0.3
False  # ❌ Rounding error!
>>> 0.1 + 0.2
0.30000000000000004

# Decimal Precision:
>>> Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
True  # ✅ Exact arithmetic
```

**Financial Implications:**
```python
# Scenario: 1,000,000 orders at $50,000.12345
# Float error per order: ~0.00001
# Total error: ~$10 (unacceptable in production)

# Decimal: ZERO error (exact arithmetic)
```

**Trade-offs:**
- ✅ Exact precision (critical for financial applications)
- ✅ No accumulating errors
- ❌ ~10-100x slower than floats
- ❌ Higher memory usage (20 bytes vs 8 bytes)

**Verdict:** ✅ Use Decimal (correctness > speed)

#### Why Enum for Side and Status?

```python
# Without Enum (string constants):
order.side = "buy"  # ❌ Typos: "Buy", "BUY", "b", "by"
order.status = "prtially_filled"  # ❌ Typo undetected

# With Enum:
order.side = OrderSide.BUY  # ✅ Type-safe
order.status = OrderStatus.PARTIALLY_FILLED  # ✅ Autocomplete
```

**Advantages:**
- ✅ Type safety (catch errors at development time)
- ✅ IDE autocomplete
- ✅ No typos in string constants
- ✅ Clear valid values

### Complexity Analysis

| Operation | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| **Create Order** | O(1) | O(1) (fixed size) |
| **Fill Order** | O(1) | O(1) |
| **Check Status** | O(1) | O(1) |
| **Get Remaining Qty** | O(1) | O(1) (computed property) |

**Memory Usage:**
- Base Order: ~200 bytes
- LimitOrder: ~216 bytes (adds price field)
- 10,000 orders: ~2 MB

---

## 4. Trade Data Structure

### Implementation

```python
@dataclass
class Trade:
    """Represents a matched trade execution"""
    trade_id: str
    symbol: str
    price: Decimal
    quantity: Decimal
    
    # Order references
    maker_order_id: str  # Resting order (provides liquidity)
    taker_order_id: str  # Aggressive order (takes liquidity)
    
    # Metadata
    aggressor_side: OrderSide  # Buy or sell
    timestamp: datetime
    
    # Optional fee information (future)
    maker_fee: Optional[Decimal] = None
    taker_fee: Optional[Decimal] = None
```

### Design Rationale

#### Why Separate Maker and Taker?

**Maker:** Order that was already on the book (passive)  
**Taker:** Order that matched against the book (aggressive)

**Importance:**
1. **Fee Differentiation:**
   ```python
   maker_fee = -0.01%  # Rebate (encourages liquidity provision)
   taker_fee = +0.05%  # Fee (pays for taking liquidity)
   ```

2. **Market Analytics:**
   ```python
   # Identify market direction
   if aggressor_side == BUY:
       print("Buying pressure")  # Takers are buyers
   ```

3. **Regulatory Reporting:**
   - REG NMS requires trade reports with aggressor side
   - Audit trails must distinguish passive vs aggressive

---

## Memory Efficiency Analysis

### Order Book Memory Usage

**Scenario:** BTC-USDT order book with 10,000 orders

```
Components:
├── Orders Dict: 10,000 orders × 200 bytes = 2.0 MB
├── Bids SortedDict: 500 price levels × 48 bytes = 24 KB
├── Asks SortedDict: 500 price levels × 48 bytes = 24 KB
├── PriceLevel Objects: 1,000 levels × 80 bytes = 80 KB
├── Deque Overhead: 10,000 nodes × 28 bytes = 280 KB
└── Total: ~2.4 MB
```

**Scalability:**
- 100 symbols × 10,000 orders = 240 MB (easily fits in RAM)
- 1,000 symbols × 10,000 orders = 2.4 GB (still manageable)

**Optimization Opportunities:**
1. **Object Pooling:** Reuse order/trade objects
2. **Compact Representation:** Use `__slots__` to reduce overhead
3. **Compression:** Archive old orders to disk

---

## Performance Characteristics

### Real-World Performance

**Benchmark Results (from tests/performance/benchmark_matching.py):**

| Metric | Achieved | Target | Status |
|--------|----------|--------|--------|
| **Order Submission** | 6,641 orders/sec | >1,000 | ✅ 6.6x |
| **p99 Latency** | 0.406 ms | <1.0 ms | ✅ 2.5x |
| **BBO Queries** | 237,042 queries/sec | >10,000 | ✅ 23x |
| **Memory per Order** | ~240 bytes | <1 KB | ✅ 4x |

### Bottleneck Analysis

**CPU-Bound Operations:**
1. **Decimal Arithmetic** (~40% of CPU time)
   - Price comparisons
   - Quantity calculations
   - Mitigation: Consider fixed-point integers

2. **SortedDict Updates** (~30% of CPU time)
   - Insertion: O(log n)
   - Deletion: O(log n)
   - Mitigation: Already optimal for sorted structure

3. **Deque Operations** (~15% of CPU time)
   - append/popleft: O(1) - very fast
   - remove: O(n) - only for cancellations
   - Mitigation: Order cancellations are less frequent

4. **Object Creation** (~15% of CPU time)
   - Trade objects
   - Timestamp generation
   - Mitigation: Object pooling

---

## Alternative Data Structures Considered

### 1. Heap-Based Order Book

**Pros:**
- O(1) min/max access
- O(log n) insertion

**Cons:**
- ❌ Can't iterate in order efficiently
- ❌ Can't remove arbitrary elements efficiently
- ❌ Complex to maintain two heaps (bid/ask)

**Verdict:** ❌ Rejected (insufficient functionality)

### 2. Linked List for Price Levels

**Pros:**
- O(1) insertion/deletion at known position
- Simple implementation

**Cons:**
- ❌ O(n) to find price level
- ❌ No random access
- ❌ Poor cache locality

**Verdict:** ❌ Rejected (slow price lookups)

### 3. Skip List

**Pros:**
- O(log n) search/insert/delete
- Simpler than balanced tree
- Good cache locality

**Cons:**
- ❌ Probabilistic (not deterministic)
- ❌ No mature Python library
- ❌ Would need custom implementation

**Verdict:** ❌ Rejected (not worth custom implementation)

### 4. B-Tree (SortedDict Implementation)

**Pros:**
- ✅ O(log n) operations
- ✅ Excellent cache locality
- ✅ Ordered iteration
- ✅ Proven performance

**Cons:**
- More complex than BST
- External dependency

**Verdict:** ✅ **Chosen** (best balance of performance and features)

---

## Correctness Guarantees

### 1. FIFO Ordering

**Guarantee:** Deque maintains insertion order.

**Proof:**
```python
# Test: Submit 3 orders at same price
order1 = LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50000"))
order2 = LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50000"))
order3 = LimitOrder("BTC-USDT", SELL, 1.0, Decimal("50000"))

price_level.add_order(order1)  # First
price_level.add_order(order2)  # Second
price_level.add_order(order3)  # Third

assert price_level.orders[0] == order1  # Front of queue
assert price_level.orders[1] == order2
assert price_level.orders[2] == order3  # Back of queue
```

**Verified:** ✅ 27 unit tests in `test_order_book.py`

### 2. Price Priority

**Guarantee:** SortedDict maintains sorted order.

**Proof:**
```python
# Test: Add prices out of order
bids = SortedDict()
bids[Decimal("49950")] = PriceLevel(Decimal("49950"))
bids[Decimal("50000")] = PriceLevel(Decimal("50000"))  # Better
bids[Decimal("49900")] = PriceLevel(Decimal("49900"))

# Iterate in descending order (best bid first)
for price in reversed(bids.keys()):
    print(price)

# Output:
# 50000  ← Best bid (highest)
# 49950
# 49900
```

**Verified:** ✅ 27 unit tests in `test_matching_engine.py`

### 3. No Trade-Throughs

**Guarantee:** Iteration order ensures best prices matched first.

**Proof:**
```python
# For sell order matching highest bids:
for price in reversed(self.bids.keys()):  # Descending order
    # Highest bid encountered first
    # Must exhaust this price before moving to next
    while price_level.orders:
        # Match all orders at this price (FIFO)
```

**Verified:** ✅ Test case `test_trade_through_prevention` passes

---

## Future Enhancements

### 1. Lock-Free Data Structures

**Current:** Single lock per symbol
**Future:** Atomic operations for order book updates

**Potential Libraries:**
- `atomics` (Python bindings for atomic ops)
- Custom C extension with lock-free queues

**Expected Gain:** 20-30% throughput improvement

### 2. Memory-Mapped Order Book

**Current:** In-memory only
**Future:** mmap for persistence without serialization overhead

**Benefits:**
- Instant crash recovery
- Minimal performance impact
- Shared memory across processes

### 3. SIMD Optimizations

**Current:** Scalar operations
**Future:** Use NumPy for vectorized depth calculations

**Example:**
```python
# Current: O(n) loop
total = sum(level.total_quantity for level in levels)

# Future: SIMD vectorization
import numpy as np
quantities = np.array([level.total_quantity for level in levels])
total = np.sum(quantities)  # Vectorized (faster)
```

### 4. Compressed Price Levels

**Scenario:** Sparse order books (many empty price levels)

**Solution:**
```python
# Instead of storing every tick:
# $50000.00, $50000.01, $50000.02, ... (99% empty)

# Use run-length encoding or skip gaps
# Only store non-empty levels
```

---

## Conclusion

The data structures design achieves **optimal performance** through:

✅ **Efficient Core Structures:**
- SortedDict for O(log n) price level operations
- Deque for O(1) FIFO queue operations
- Dict for O(1) order lookup

✅ **Correctness Guarantees:**
- Price priority (SortedDict ordering)
- Time priority (Deque FIFO)
- Trade-through prevention (iteration order)

✅ **Proven Performance:**
- 6,641 orders/second (6.6x target)
- 0.406 ms p99 latency (2.5x better than target)
- 237,042 BBO queries/second (23x target)

✅ **Scalability:**
- Sub-linear growth (O(log n) operations)
- Memory-efficient (~240 bytes per order)
- Supports 1000+ price levels efficiently

The data structures provide a **solid foundation** for a production-grade matching engine, with clear paths for future optimization if needed.

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-24  
**Related:** See `docs/architecture.md` for system overview, `docs/matching_algorithm.md` for matching logic
