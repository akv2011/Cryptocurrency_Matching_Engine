"""
Order models for the cryptocurrency matching engine.

Implements different order types with proper validation and state management:
- Market Order: Immediate execution at best available price
- Limit Order: Execute at specified price or better
- IOC (Immediate-Or-Cancel): Execute immediately, cancel unfilled portion
- FOK (Fill-Or-Kill): Execute entire order immediately or cancel completely
"""

from decimal import Decimal
from enum import Enum
from typing import Optional
from datetime import datetime
import uuid


class OrderSide(Enum):
    """Order side: buy or sell"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Supported order types"""
    MARKET = "market"
    LIMIT = "limit"
    IOC = "ioc"  # Immediate-Or-Cancel
    FOK = "fok"  # Fill-Or-Kill


class OrderStatus(Enum):
    """Order lifecycle states"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELED = "canceled"


class Order:
    """
    Base order class with common functionality.
    
    Maintains price-time priority through microsecond-precision timestamps.
    Uses Decimal for precise financial calculations.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        price: Optional[Decimal] = None,
        order_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """
        Initialize an order.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            side: Buy or Sell
            quantity: Order quantity (must be positive)
            order_type: Market, Limit, IOC, or FOK
            price: Limit price (required for limit orders)
            order_id: Unique order identifier (auto-generated if None)
            user_id: User identifier for tracking
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {quantity}")
        
        if order_type in (OrderType.LIMIT, OrderType.IOC, OrderType.FOK) and price is None:
            raise ValueError(f"{order_type.value} orders require a price")
        
        if price is not None and price <= 0:
            raise ValueError(f"Order price must be positive, got {price}")
        
        # Core attributes
        self.order_id = order_id or str(uuid.uuid4())
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.price = price
        
        # Quantity tracking
        self.original_quantity = quantity
        self.quantity = quantity  # Remaining quantity
        self.filled_quantity = Decimal("0")
        
        # State management
        self.status = OrderStatus.PENDING
        self.timestamp = datetime.utcnow()  # High-precision timestamp for FIFO
        
        # Optional metadata
        self.user_id = user_id
        
        # Trade tracking
        self.trades = []  # List of (price, quantity) tuples
    
    def fill(self, quantity: Decimal, price: Decimal) -> None:
        """
        Fill (partial or complete) the order.
        
        Args:
            quantity: Quantity to fill
            price: Execution price
            
        Raises:
            ValueError: If fill quantity exceeds remaining quantity
        """
        if quantity <= 0:
            raise ValueError(f"Fill quantity must be positive, got {quantity}")
        
        if quantity > self.quantity:
            raise ValueError(
                f"Fill quantity {quantity} exceeds remaining quantity {self.quantity}"
            )
        
        self.quantity -= quantity
        self.filled_quantity += quantity
        self.trades.append((price, quantity))
        
        # Update status
        if self.quantity == 0:
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
    
    def cancel(self) -> None:
        """Cancel the order."""
        if self.status in (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED):
            raise ValueError(f"Cannot cancel order with status {self.status.value}")
        
        self.status = OrderStatus.CANCELED
    
    def reject(self, reason: str = "") -> None:
        """
        Reject the order.
        
        Args:
            reason: Rejection reason for logging
        """
        self.status = OrderStatus.REJECTED
    
    def accept(self) -> None:
        """Mark order as accepted."""
        if self.status == OrderStatus.PENDING:
            self.status = OrderStatus.ACCEPTED
    
    @property
    def is_marketable(self) -> bool:
        """Check if order can be immediately executed (abstract for subclasses)."""
        raise NotImplementedError("Subclasses must implement is_marketable")
    
    @property
    def average_price(self) -> Optional[Decimal]:
        """Calculate average execution price."""
        if not self.trades:
            return None
        
        total_value = sum(price * qty for price, qty in self.trades)
        return total_value / self.filled_quantity if self.filled_quantity > 0 else None
    
    def to_dict(self) -> dict:
        """Serialize order to dictionary for API responses."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "order_type": self.order_type.value,
            "side": self.side.value,
            "price": str(self.price) if self.price else None,
            "original_quantity": str(self.original_quantity),
            "quantity": str(self.quantity),
            "filled_quantity": str(self.filled_quantity),
            "status": self.status.value,
            "average_price": str(self.average_price) if self.average_price else None,
            "timestamp": self.timestamp.isoformat() + "Z",
            "user_id": self.user_id
        }
    
    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id[:8]}, {self.side.value} {self.quantity}/{self.original_quantity} "
            f"{self.symbol} @ {self.price or 'MARKET'}, status={self.status.value})"
        )


class MarketOrder(Order):
    """
    Market order: Execute immediately at best available price(s).
    
    Walks the order book until fully filled or liquidity exhausted.
    Does not rest on the book.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        super().__init__(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            price=None,
            order_id=order_id,
            user_id=user_id
        )
    
    @property
    def is_marketable(self) -> bool:
        """Market orders are always immediately marketable."""
        return True


class LimitOrder(Order):
    """
    Limit order: Execute at specified price or better.
    
    - Buy: Execute at limit price or lower
    - Sell: Execute at limit price or higher
    
    Unmatched portion rests on the order book in price-time priority.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        order_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        super().__init__(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=price,
            order_id=order_id,
            user_id=user_id
        )
    
    @property
    def is_marketable(self) -> bool:
        """
        Limit orders may be immediately marketable depending on price.
        Actual marketability checked by matching engine against current book.
        """
        return False  # Conservative default; engine determines actual marketability
    
    def is_marketable_against(self, best_price: Optional[Decimal]) -> bool:
        """
        Check if limit order can cross the spread.
        
        Args:
            best_price: Best bid (for sell orders) or best ask (for buy orders)
            
        Returns:
            True if order can immediately execute
        """
        if best_price is None:
            return False
        
        if self.side == OrderSide.BUY:
            # Buy limit is marketable if price >= best ask
            return self.price >= best_price
        else:
            # Sell limit is marketable if price <= best bid
            return self.price <= best_price


class IOCOrder(Order):
    """
    Immediate-Or-Cancel (IOC): Execute all or part immediately, cancel remainder.
    
    - Matches against available liquidity at specified price or better
    - Does not rest on the book
    - Partial fills allowed
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        order_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        super().__init__(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.IOC,
            price=price,
            order_id=order_id,
            user_id=user_id
        )
    
    @property
    def is_marketable(self) -> bool:
        """IOC orders are immediately marketable (execute or cancel)."""
        return True


class FOKOrder(Order):
    """
    Fill-Or-Kill (FOK): Execute entire order immediately or cancel completely.
    
    - All-or-nothing execution
    - Must check full liquidity BEFORE execution
    - No partial fills
    - Does not rest on the book
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        order_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        super().__init__(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.FOK,
            price=price,
            order_id=order_id,
            user_id=user_id
        )
    
    @property
    def is_marketable(self) -> bool:
        """FOK orders are immediately marketable (execute or kill)."""
        return True
    
    def fill(self, quantity: Decimal, price: Decimal) -> None:
        """
        Override fill to allow multiple fills across price levels.
        
        FOK orders can be filled in multiple transactions as long as 
        the total quantity is filled completely (checked by matching engine).
        """
        # Allow multiple fills - the matching engine ensures complete fill
        super().fill(quantity, price)


def create_order(
    symbol: str,
    order_type: str,
    side: str,
    quantity: str,
    price: Optional[str] = None,
    order_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Order:
    """
    Factory function to create orders from API request parameters.
    
    Args:
        symbol: Trading pair (e.g., "BTC-USDT")
        order_type: "market", "limit", "ioc", or "fok"
        side: "buy" or "sell"
        quantity: Order quantity as string
        price: Limit price as string (required for limit/IOC/FOK)
        order_id: Optional unique identifier
        user_id: Optional user identifier
        
    Returns:
        Appropriate Order subclass instance
        
    Raises:
        ValueError: If parameters are invalid
    """
    # Parse and validate inputs
    try:
        qty = Decimal(quantity)
    except Exception as e:
        raise ValueError(f"Invalid quantity '{quantity}': {e}")
    
    try:
        parsed_price = Decimal(price) if price else None
    except Exception as e:
        raise ValueError(f"Invalid price '{price}': {e}")
    
    try:
        order_side = OrderSide(side.lower())
    except ValueError:
        raise ValueError(f"Invalid side '{side}'. Must be 'buy' or 'sell'")
    
    try:
        parsed_order_type = OrderType(order_type.lower())
    except ValueError:
        raise ValueError(
            f"Invalid order_type '{order_type}'. "
            f"Must be one of: market, limit, ioc, fok"
        )
    
    # Create appropriate order type
    if parsed_order_type == OrderType.MARKET:
        return MarketOrder(
            symbol=symbol,
            side=order_side,
            quantity=qty,
            order_id=order_id,
            user_id=user_id
        )
    elif parsed_order_type == OrderType.LIMIT:
        if parsed_price is None:
            raise ValueError("Limit orders require a price")
        return LimitOrder(
            symbol=symbol,
            side=order_side,
            quantity=qty,
            price=parsed_price,
            order_id=order_id,
            user_id=user_id
        )
    elif parsed_order_type == OrderType.IOC:
        if parsed_price is None:
            raise ValueError("IOC orders require a price")
        return IOCOrder(
            symbol=symbol,
            side=order_side,
            quantity=qty,
            price=parsed_price,
            order_id=order_id,
            user_id=user_id
        )
    elif parsed_order_type == OrderType.FOK:
        if parsed_price is None:
            raise ValueError("FOK orders require a price")
        return FOKOrder(
            symbol=symbol,
            side=order_side,
            quantity=qty,
            price=parsed_price,
            order_id=order_id,
            user_id=user_id
        )
    else:
        raise ValueError(f"Unsupported order type: {order_type}")
