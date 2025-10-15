"""
Order Book implementation for high-performance matching.

Uses SortedDict for efficient price-level operations with FIFO queues per level.
Provides O(1) order lookup and fast BBO (Best Bid/Offer) calculation.
"""

from collections import deque
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sortedcontainers import SortedDict

from .order import Order, OrderSide


class PriceLevel:
    """
    Represents all orders at a single price level.
    
    Maintains FIFO queue for time priority. All operations are O(1).
    """
    
    def __init__(self, price: Decimal):
        self.price = price
        self.orders: deque[Order] = deque()  # FIFO queue for time priority
        self.total_quantity = Decimal("0")
    
    def add_order(self, order: Order) -> None:
        """Add order to the end of the queue (newest)."""
        self.orders.append(order)
        self.total_quantity += order.quantity
    
    def remove_order(self, order: Order) -> bool:
        """
        Remove specific order from the queue.
        
        Returns:
            True if order was found and removed, False otherwise
        """
        try:
            self.orders.remove(order)
            self.total_quantity -= order.quantity
            return True
        except ValueError:
            return False
    
    def is_empty(self) -> bool:
        """Check if price level has any orders."""
        return len(self.orders) == 0
    
    def peek_first(self) -> Optional[Order]:
        """Get first order without removing it."""
        return self.orders[0] if self.orders else None
    
    def __repr__(self) -> str:
        return f"PriceLevel(price={self.price}, qty={self.total_quantity}, orders={len(self.orders)})"


class OrderBook:
    """
    Order book for a single trading pair.
    
    Key features:
    - SortedDict for efficient price-level operations
    - FIFO queues at each price level for time priority
    - O(1) order lookup by ID
    - Fast BBO calculation
    - Supports add, modify, cancel operations
    
    Data structures:
    - bids: SortedDict with prices in descending order (highest bid first)
    - asks: SortedDict with prices in ascending order (lowest ask first)
    - orders: Dict for O(1) order lookup
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        
        # Price levels: SortedDict for efficient operations
        # Bids: highest price first (reverse order)
        self.bids = SortedDict()
        # Asks: lowest price first (normal order)
        self.asks = SortedDict()
        
        # Order tracking for O(1) lookup
        self.orders: Dict[str, Order] = {}
    
    def add_order(self, order: Order) -> None:
        """
        Add order to the book.
        
        Args:
            order: Order to add (must be limit order type that rests on book)
            
        Raises:
            ValueError: If order already exists or invalid
        """
        if order.order_id in self.orders:
            raise ValueError(f"Order {order.order_id} already exists in book")
        
        if order.price is None:
            raise ValueError("Cannot add order without price to book")
        
        # Select appropriate side
        price_levels = self.bids if order.side == OrderSide.BUY else self.asks
        
        # Create price level if doesn't exist
        if order.price not in price_levels:
            price_levels[order.price] = PriceLevel(order.price)
        
        # Add order to price level
        price_level = price_levels[order.price]
        price_level.add_order(order)
        
        # Track order for O(1) lookup
        self.orders[order.order_id] = order
    
    def remove_order(self, order_id: str) -> Optional[Order]:
        """
        Remove order from the book.
        
        Args:
            order_id: ID of order to remove
            
        Returns:
            Removed order, or None if not found
        """
        order = self.orders.get(order_id)
        if order is None:
            return None
        
        # Select appropriate side
        price_levels = self.bids if order.side == OrderSide.BUY else self.asks
        
        # Remove from price level
        if order.price in price_levels:
            price_level = price_levels[order.price]
            price_level.remove_order(order)
            
            # Clean up empty price level
            if price_level.is_empty():
                del price_levels[order.price]
        
        # Remove from tracking
        del self.orders[order_id]
        
        return order
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """O(1) order lookup."""
        return self.orders.get(order_id)
    
    def get_best_bid(self) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get best bid price and total quantity.
        
        Returns:
            (price, total_quantity) tuple, or None if no bids
        """
        if not self.bids:
            return None
        
        # Highest bid is at the end (reverse sorted)
        best_price = self.bids.keys()[-1]
        price_level = self.bids[best_price]
        return (best_price, price_level.total_quantity)
    
    def get_best_ask(self) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get best ask price and total quantity.
        
        Returns:
            (price, total_quantity) tuple, or None if no asks
        """
        if not self.asks:
            return None
        
        # Lowest ask is at the beginning (normal sorted)
        best_price = self.asks.keys()[0]
        price_level = self.asks[best_price]
        return (best_price, price_level.total_quantity)
    
    def get_bbo(self) -> Tuple[Optional[Tuple[Decimal, Decimal]], Optional[Tuple[Decimal, Decimal]]]:
        """
        Get Best Bid and Offer (BBO).
        
        Returns:
            ((bid_price, bid_qty), (ask_price, ask_qty)) tuple
            Either or both can be None if side is empty
        """
        return (self.get_best_bid(), self.get_best_ask())
    
    def get_market_depth(self, levels: int = 10) -> Tuple[List[Tuple[Decimal, Decimal]], List[Tuple[Decimal, Decimal]]]:
        """
        Get L2 order book depth (aggregated by price level).
        
        Args:
            levels: Number of price levels to return per side
            
        Returns:
            (bids, asks) where each is list of (price, total_quantity) tuples
            Bids in descending order, asks in ascending order
        """
        # Get top N bid levels (highest prices)
        bid_prices = list(self.bids.keys())[-levels:] if self.bids else []
        bid_prices.reverse()  # Highest first
        bids = [(price, self.bids[price].total_quantity) for price in bid_prices]
        
        # Get top N ask levels (lowest prices)
        ask_prices = list(self.asks.keys())[:levels] if self.asks else []
        asks = [(price, self.asks[price].total_quantity) for price in ask_prices]
        
        return (bids, asks)
    
    def get_orders_at_price(self, side: OrderSide, price: Decimal) -> List[Order]:
        """
        Get all orders at a specific price level.
        
        Args:
            side: BUY or SELL
            price: Price level
            
        Returns:
            List of orders in FIFO order (oldest first)
        """
        price_levels = self.bids if side == OrderSide.BUY else self.asks
        
        if price not in price_levels:
            return []
        
        price_level = price_levels[price]
        return list(price_level.orders)
    
    def match_order(self, incoming_order: Order) -> List[Tuple[Order, Decimal, Decimal]]:
        """
        Find matching orders for an incoming order.
        
        This method identifies potential matches but does NOT execute them.
        The matching engine is responsible for actual execution.
        
        Args:
            incoming_order: Order to match against the book
            
        Returns:
            List of (maker_order, match_price, match_quantity) tuples
            in the order they should be executed (FIFO within each price level)
        """
        matches = []
        remaining_qty = incoming_order.quantity
        
        # Select opposite side of the book
        if incoming_order.side == OrderSide.BUY:
            # Match against asks (sells) - iterate in ascending order (best ask first)
            price_levels = self.asks
            can_match = lambda ask_price: incoming_order.price is None or incoming_order.price >= ask_price
            price_order = list(price_levels.keys())  # Ascending order
        else:
            # Match against bids (buys) - iterate in descending order (best bid first)
            price_levels = self.bids
            can_match = lambda bid_price: incoming_order.price is None or incoming_order.price <= bid_price
            price_order = list(reversed(price_levels.keys()))  # Descending order
        
        # Iterate through price levels in order
        for price in price_order:
            # Check if we can match at this price
            if not can_match(price):
                break
            
            price_level = price_levels[price]
            
            # Match against orders at this price level (FIFO)
            for maker_order in list(price_level.orders):
                if remaining_qty <= 0:
                    break
                
                # Determine match quantity
                match_qty = min(remaining_qty, maker_order.quantity)
                matches.append((maker_order, price, match_qty))
                
                remaining_qty -= match_qty
            
            if remaining_qty <= 0:
                break
        
        return matches
    
    def can_fill_quantity(self, side: OrderSide, quantity: Decimal, max_price: Optional[Decimal] = None) -> bool:
        """
        Check if there's enough liquidity to fill a quantity.
        
        Used for FOK order validation.
        
        Args:
            side: BUY or SELL (side of incoming order)
            quantity: Quantity to check
            max_price: Maximum price for buys, minimum price for sells
            
        Returns:
            True if order book has sufficient liquidity
        """
        available_qty = Decimal("0")
        
        # Select opposite side of the book
        if side == OrderSide.BUY:
            price_levels = self.asks
            can_use = lambda price: max_price is None or price <= max_price
        else:
            price_levels = self.bids
            can_use = lambda price: max_price is None or price >= max_price
        
        # Sum up available quantity at acceptable prices
        for price, price_level in price_levels.items():
            if not can_use(price):
                break
            
            available_qty += price_level.total_quantity
            
            if available_qty >= quantity:
                return True
        
        return False
    
    def clear(self) -> None:
        """Remove all orders from the book."""
        self.bids.clear()
        self.asks.clear()
        self.orders.clear()
    
    def get_statistics(self) -> dict:
        """Get order book statistics for monitoring."""
        return {
            "symbol": self.symbol,
            "total_orders": len(self.orders),
            "bid_levels": len(self.bids),
            "ask_levels": len(self.asks),
            "total_bid_quantity": sum(pl.total_quantity for pl in self.bids.values()),
            "total_ask_quantity": sum(pl.total_quantity for pl in self.asks.values()),
            "best_bid": self.get_best_bid(),
            "best_ask": self.get_best_ask()
        }
    
    def __repr__(self) -> str:
        bbo = self.get_bbo()
        bid_str = f"{bbo[0][0]}@{bbo[0][1]}" if bbo[0] else "None"
        ask_str = f"{bbo[1][0]}@{bbo[1][1]}" if bbo[1] else "None"
        return f"OrderBook({self.symbol}, bid={bid_str}, ask={ask_str}, orders={len(self.orders)})"
