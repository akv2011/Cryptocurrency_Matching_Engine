"""
Matching Engine implementing REG NMS-inspired principles.

Key features:
- Price-time priority: Higher bids and lower offers execute first, FIFO at each level
- Trade-through prevention: Incoming orders MUST match at best prices first
- Partial fills: Orders fill at better prices before moving to next level
- Support for Market, Limit, IOC, and FOK orders
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import threading

from .order import Order, OrderType, OrderSide, OrderStatus, MarketOrder, LimitOrder, IOCOrder, FOKOrder
from .order_book import OrderBook


class Trade:
    """Represents an executed trade between two orders."""
    
    def __init__(
        self,
        trade_id: str,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
        maker_order_id: str,
        taker_order_id: str,
        aggressor_side: OrderSide,
        timestamp: datetime
    ):
        self.trade_id = trade_id
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.maker_order_id = maker_order_id
        self.taker_order_id = taker_order_id
        self.aggressor_side = aggressor_side
        self.timestamp = timestamp
    
    def to_dict(self) -> dict:
        """Serialize trade for API/WebSocket streaming."""
        return {
            "type": "trade",
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "maker_order_id": self.maker_order_id,
            "taker_order_id": self.taker_order_id,
            "aggressor_side": self.aggressor_side.value,
            "timestamp": self.timestamp.isoformat() + "Z"
        }
    
    def __repr__(self) -> str:
        return (
            f"Trade(id={self.trade_id[:8]}, {self.symbol}, "
            f"{self.quantity}@{self.price}, aggressor={self.aggressor_side.value})"
        )


class MatchingEngine:
    """
    High-performance matching engine with REG NMS-inspired principles.
    
    Maintains separate order books for each trading pair.
    Processes orders with strict price-time priority.
    Prevents trade-through violations.
    
    Thread-safe for concurrent order submission.
    """
    
    def __init__(self):
        self.order_books: Dict[str, OrderBook] = {}
        self.trade_counter = 0
        self.lock = threading.Lock()  # Ensure thread-safe operations
        
        # Callbacks for event notifications
        self.on_trade_callbacks = []
        self.on_bbo_update_callbacks = []
        self.on_orderbook_update_callbacks = []
    
    def get_or_create_orderbook(self, symbol: str) -> OrderBook:
        """Get existing order book or create new one for symbol."""
        if symbol not in self.order_books:
            self.order_books[symbol] = OrderBook(symbol)
        return self.order_books[symbol]
    
    def submit_order(self, order: Order) -> Tuple[Order, List[Trade]]:
        """
        Submit order to matching engine.
        
        Process flow:
        1. Validate order
        2. Attempt matching against opposite side
        3. For limit orders: rest unmatched portion on book
        4. For IOC/FOK: handle according to order type rules
        5. Generate trades and update order book
        6. Trigger callbacks for market data updates
        
        Args:
            order: Order to process
            
        Returns:
            (processed_order, list_of_trades) tuple
        """
        with self.lock:
            order_book = self.get_or_create_orderbook(order.symbol)
            trades = []
            
            # Accept the order
            order.accept()
            
            # Process based on order type
            if isinstance(order, MarketOrder):
                trades = self._match_market_order(order, order_book)
            elif isinstance(order, FOKOrder):
                trades = self._match_fok_order(order, order_book)
            elif isinstance(order, IOCOrder):
                trades = self._match_ioc_order(order, order_book)
            elif isinstance(order, LimitOrder):
                trades = self._match_limit_order(order, order_book)
            else:
                raise ValueError(f"Unsupported order type: {type(order)}")
            
            # Trigger callbacks for market data updates
            if trades:
                for trade in trades:
                    self._notify_trade(trade)
            
            # Always notify BBO/orderbook updates (even if no trades)
            self._notify_bbo_update(order_book)
            self._notify_orderbook_update(order_book)
            
            return (order, trades)
    
    def _match_market_order(self, order: MarketOrder, order_book: OrderBook) -> List[Trade]:
        """
        Match market order against best available prices.
        
        Market orders walk the book until fully filled or liquidity exhausted.
        They do NOT rest on the book.
        """
        trades = []
        matches = order_book.match_order(order)
        
        # Execute all possible matches
        for maker_order, match_price, match_qty in matches:
            trade = self._execute_trade(
                maker_order=maker_order,
                taker_order=order,
                price=match_price,
                quantity=match_qty,
                order_book=order_book
            )
            trades.append(trade)
        
        # Market orders don't rest on book, any unfilled portion is lost
        if order.quantity > 0:
            # Partial fill for market order (ran out of liquidity)
            pass
        
        return trades
    
    def _match_limit_order(self, order: LimitOrder, order_book: OrderBook) -> List[Trade]:
        """
        Match limit order at specified price or better.
        
        - Immediately marketable portion executes
        - Unmatched portion rests on book in price-time priority
        """
        trades = []
        matches = order_book.match_order(order)
        
        # Execute all possible matches at acceptable prices
        for maker_order, match_price, match_qty in matches:
            trade = self._execute_trade(
                maker_order=maker_order,
                taker_order=order,
                price=match_price,
                quantity=match_qty,
                order_book=order_book
            )
            trades.append(trade)
        
        # Rest unmatched portion on book
        if order.quantity > 0:
            order_book.add_order(order)
        
        return trades
    
    def _match_ioc_order(self, order: IOCOrder, order_book: OrderBook) -> List[Trade]:
        """
        Match IOC (Immediate-Or-Cancel) order.
        
        - Executes immediately at specified price or better
        - Partial fills allowed
        - Unfilled portion is canceled (does not rest on book)
        """
        trades = []
        matches = order_book.match_order(order)
        
        # Execute all possible matches
        for maker_order, match_price, match_qty in matches:
            trade = self._execute_trade(
                maker_order=maker_order,
                taker_order=order,
                price=match_price,
                quantity=match_qty,
                order_book=order_book
            )
            trades.append(trade)
        
        # Cancel any unfilled portion (IOC doesn't rest on book)
        if order.quantity > 0:
            order.cancel()
        
        return trades
    
    def _match_fok_order(self, order: FOKOrder, order_book: OrderBook) -> List[Trade]:
        """
        Match FOK (Fill-Or-Kill) order.
        
        - All-or-nothing execution
        - Must check FULL liquidity before executing
        - If can't fill completely, reject entire order
        - No partial fills
        """
        trades = []
        
        # Check if we have sufficient liquidity to fill entire order
        can_fill = order_book.can_fill_quantity(
            side=order.side,
            quantity=order.original_quantity,
            max_price=order.price
        )
        
        if not can_fill:
            # Reject order - insufficient liquidity
            order.reject("Insufficient liquidity for FOK order")
            return trades
        
        # We have liquidity, now execute matches
        matches = order_book.match_order(order)
        
        # Execute all matches (should fill entire order)
        for maker_order, match_price, match_qty in matches:
            trade = self._execute_trade(
                maker_order=maker_order,
                taker_order=order,
                price=match_price,
                quantity=match_qty,
                order_book=order_book
            )
            trades.append(trade)
        
        # Verify complete fill (should always be true if can_fill was correct)
        if order.quantity > 0:
            raise RuntimeError(
                f"FOK order not completely filled despite liquidity check. "
                f"Remaining: {order.quantity}"
            )
        
        return trades
    
    def _execute_trade(
        self,
        maker_order: Order,
        taker_order: Order,
        price: Decimal,
        quantity: Decimal,
        order_book: OrderBook
    ) -> Trade:
        """
        Execute a trade between maker and taker orders.
        
        This is where the actual order filling happens:
        1. Fill both orders
        2. Remove maker from book if fully filled
        3. Generate trade record
        
        Args:
            maker_order: Resting order on the book
            taker_order: Incoming aggressive order
            price: Execution price (maker's price)
            quantity: Execution quantity
            order_book: Order book being matched against
            
        Returns:
            Trade record
        """
        # Fill both orders
        maker_order.fill(quantity, price)
        taker_order.fill(quantity, price)
        
        # Remove maker from book if fully filled
        if maker_order.status == OrderStatus.FILLED:
            order_book.remove_order(maker_order.order_id)
        
        # Generate trade record
        self.trade_counter += 1
        trade = Trade(
            trade_id=f"trade_{self.trade_counter}",
            symbol=taker_order.symbol,
            price=price,
            quantity=quantity,
            maker_order_id=maker_order.order_id,
            taker_order_id=taker_order.order_id,
            aggressor_side=taker_order.side,
            timestamp=datetime.utcnow()
        )
        
        return trade
    
    def cancel_order(self, symbol: str, order_id: str) -> Optional[Order]:
        """
        Cancel an order resting on the book.
        
        Args:
            symbol: Trading pair
            order_id: Order to cancel
            
        Returns:
            Canceled order, or None if not found
        """
        with self.lock:
            if symbol not in self.order_books:
                return None
            
            order_book = self.order_books[symbol]
            order = order_book.remove_order(order_id)
            
            if order:
                order.cancel()
                # Notify market data updates
                self._notify_bbo_update(order_book)
                self._notify_orderbook_update(order_book)
            
            return order
    
    def get_order(self, symbol: str, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        if symbol not in self.order_books:
            return None
        return self.order_books[symbol].get_order(order_id)
    
    def get_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """Get order book for symbol."""
        return self.order_books.get(symbol)
    
    def get_bbo(self, symbol: str) -> Optional[Tuple[Optional[Tuple[Decimal, Decimal]], Optional[Tuple[Decimal, Decimal]]]]:
        """Get Best Bid and Offer for symbol."""
        if symbol not in self.order_books:
            return None
        return self.order_books[symbol].get_bbo()
    
    def get_market_depth(self, symbol: str, levels: int = 10) -> Optional[Tuple[List[Tuple[Decimal, Decimal]], List[Tuple[Decimal, Decimal]]]]:
        """Get L2 market depth for symbol."""
        if symbol not in self.order_books:
            return None
        return self.order_books[symbol].get_market_depth(levels)
    
    # Callback registration for event notifications
    
    def register_trade_callback(self, callback):
        """Register callback for trade events: callback(trade)"""
        self.on_trade_callbacks.append(callback)
    
    def register_bbo_update_callback(self, callback):
        """Register callback for BBO updates: callback(symbol, bbo)"""
        self.on_bbo_update_callbacks.append(callback)
    
    def register_orderbook_update_callback(self, callback):
        """Register callback for orderbook updates: callback(symbol, depth)"""
        self.on_orderbook_update_callbacks.append(callback)
    
    def _notify_trade(self, trade: Trade):
        """Notify registered callbacks about trade execution."""
        for callback in self.on_trade_callbacks:
            try:
                callback(trade)
            except Exception as e:
                # Don't let callback errors break the engine
                print(f"Error in trade callback: {e}")
    
    def _notify_bbo_update(self, order_book: OrderBook):
        """Notify registered callbacks about BBO updates."""
        bbo = order_book.get_bbo()
        for callback in self.on_bbo_update_callbacks:
            try:
                callback(order_book.symbol, bbo)
            except Exception as e:
                print(f"Error in BBO update callback: {e}")
    
    def _notify_orderbook_update(self, order_book: OrderBook):
        """Notify registered callbacks about orderbook updates."""
        depth = order_book.get_market_depth()
        for callback in self.on_orderbook_update_callbacks:
            try:
                callback(order_book.symbol, depth)
            except Exception as e:
                print(f"Error in orderbook update callback: {e}")
    
    def get_statistics(self) -> dict:
        """Get engine statistics for monitoring."""
        total_orders = sum(len(ob.orders) for ob in self.order_books.values())
        
        return {
            "total_symbols": len(self.order_books),
            "total_orders": total_orders,
            "total_trades": self.trade_counter,
            "order_books": {
                symbol: ob.get_statistics()
                for symbol, ob in self.order_books.items()
            }
        }
    
    def __repr__(self) -> str:
        return f"MatchingEngine(symbols={len(self.order_books)}, trades={self.trade_counter})"
