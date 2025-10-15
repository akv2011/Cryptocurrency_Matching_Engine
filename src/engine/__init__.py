"""
Cryptocurrency Matching Engine - Core Engine Module

Implements REG NMS-inspired matching with price-time priority.
"""

from .order import (
    Order,
    MarketOrder,
    LimitOrder,
    IOCOrder,
    FOKOrder,
    OrderSide,
    OrderType,
    OrderStatus,
    create_order
)
from .order_book import OrderBook, PriceLevel
from .matching_engine import MatchingEngine, Trade

__all__ = [
    "Order",
    "MarketOrder",
    "LimitOrder",
    "IOCOrder",
    "FOKOrder",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "create_order",
    "OrderBook",
    "PriceLevel",
    "MatchingEngine",
    "Trade"
]
