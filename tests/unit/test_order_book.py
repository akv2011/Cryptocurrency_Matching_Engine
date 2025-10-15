"""
Unit tests for OrderBook data structure.

Tests price-time priority, FIFO queues, and book operations.
"""

import pytest
from decimal import Decimal
from src.engine.order import LimitOrder, OrderSide
from src.engine.order_book import OrderBook, PriceLevel


class TestPriceLevel:
    """Test PriceLevel FIFO queue operations."""
    
    def test_price_level_creation(self):
        """Price levels track price and orders."""
        level = PriceLevel(Decimal("50000"))
        
        assert level.price == Decimal("50000")
        assert level.total_quantity == Decimal("0")
        assert level.is_empty()
    
    def test_add_order_fifo(self):
        """Orders added to price level in FIFO order."""
        level = PriceLevel(Decimal("50000"))
        
        order1 = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        order2 = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000"))
        
        level.add_order(order1)
        level.add_order(order2)
        
        assert level.total_quantity == Decimal("1.5")
        assert level.peek_first() == order1  # First in, first out
    
    def test_remove_order(self):
        """Orders can be removed from price level."""
        level = PriceLevel(Decimal("50000"))
        
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        level.add_order(order)
        
        removed = level.remove_order(order)
        
        assert removed is True
        assert level.is_empty()
        assert level.total_quantity == Decimal("0")


class TestOrderBookBasics:
    """Test basic order book operations."""
    
    def test_orderbook_creation(self):
        """Order books track symbol."""
        book = OrderBook("BTC-USDT")
        
        assert book.symbol == "BTC-USDT"
        assert len(book.orders) == 0
    
    def test_add_buy_order(self):
        """Buy orders added to bid side."""
        book = OrderBook("BTC-USDT")
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        book.add_order(order)
        
        assert order.order_id in book.orders
        assert Decimal("50000") in book.bids
    
    def test_add_sell_order(self):
        """Sell orders added to ask side."""
        book = OrderBook("BTC-USDT")
        order = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100"))
        
        book.add_order(order)
        
        assert order.order_id in book.orders
        assert Decimal("50100") in book.asks
    
    def test_remove_order(self):
        """Orders can be removed from book."""
        book = OrderBook("BTC-USDT")
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        book.add_order(order)
        removed = book.remove_order(order.order_id)
        
        assert removed == order
        assert order.order_id not in book.orders
        assert Decimal("50000") not in book.bids
    
    def test_get_order(self):
        """Orders can be retrieved by ID."""
        book = OrderBook("BTC-USDT")
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        book.add_order(order)
        
        retrieved = book.get_order(order.order_id)
        assert retrieved == order


class TestBBOCalculation:
    """Test Best Bid/Offer calculation."""
    
    def test_empty_book_bbo(self):
        """Empty book returns None for BBO."""
        book = OrderBook("BTC-USDT")
        
        assert book.get_best_bid() is None
        assert book.get_best_ask() is None
    
    def test_single_bid(self):
        """Best bid calculated correctly."""
        book = OrderBook("BTC-USDT")
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        book.add_order(order)
        
        best_bid = book.get_best_bid()
        assert best_bid == (Decimal("50000"), Decimal("1"))
    
    def test_single_ask(self):
        """Best ask calculated correctly."""
        book = OrderBook("BTC-USDT")
        order = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100"))
        
        book.add_order(order)
        
        best_ask = book.get_best_ask()
        assert best_ask == (Decimal("50100"), Decimal("1"))
    
    def test_multiple_bids_highest_wins(self):
        """Highest bid is best bid."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50100")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("2"), Decimal("49900")))
        
        best_bid = book.get_best_bid()
        assert best_bid[0] == Decimal("50100")  # Highest price
    
    def test_multiple_asks_lowest_wins(self):
        """Lowest ask is best ask."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50200")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50100")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("2"), Decimal("50300")))
        
        best_ask = book.get_best_ask()
        assert best_ask[0] == Decimal("50100")  # Lowest price
    
    def test_aggregated_quantity_at_best_price(self):
        """BBO quantity is sum of all orders at best price."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("2"), Decimal("50000")))
        
        best_bid = book.get_best_bid()
        assert best_bid[1] == Decimal("3.5")  # Total quantity


class TestPriceTimePriority:
    """Test price-time priority matching."""
    
    def test_fifo_at_same_price(self):
        """Orders at same price matched in FIFO order."""
        book = OrderBook("BTC-USDT")
        
        order1 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000"))
        order2 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000"))
        order3 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("2"), Decimal("50000"))
        
        book.add_order(order1)
        book.add_order(order2)
        book.add_order(order3)
        
        orders = book.get_orders_at_price(OrderSide.SELL, Decimal("50000"))
        
        assert orders[0] == order1  # First in
        assert orders[1] == order2  # Second in
        assert orders[2] == order3  # Third in
    
    def test_price_priority_over_time(self):
        """Better prices matched before worse prices regardless of time."""
        book = OrderBook("BTC-USDT")
        
        # Add in time order, but different prices
        order1 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50200"))
        order2 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50100"))
        order3 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("2"), Decimal("50300"))
        
        book.add_order(order1)
        book.add_order(order2)
        book.add_order(order3)
        
        # Best ask should be order2 (lowest price), even though it was second
        best_ask = book.get_best_ask()
        assert best_ask[0] == Decimal("50100")


class TestMarketDepth:
    """Test L2 order book depth."""
    
    def test_market_depth_format(self):
        """Market depth returns (bids, asks) tuples."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100")))
        
        bids, asks = book.get_market_depth()
        
        assert isinstance(bids, list)
        assert isinstance(asks, list)
        assert len(bids) > 0
        assert len(asks) > 0
    
    def test_market_depth_levels(self):
        """Market depth respects level limit."""
        book = OrderBook("BTC-USDT")
        
        # Add 20 bid levels
        for i in range(20):
            price = Decimal(50000 - i * 10)
            book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), price))
        
        bids, _ = book.get_market_depth(levels=5)
        
        assert len(bids) == 5  # Only top 5 levels
        assert bids[0][0] == Decimal("50000")  # Best bid first
    
    def test_market_depth_aggregated(self):
        """Market depth aggregates quantities at each price."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("2"), Decimal("49900")))
        
        bids, _ = book.get_market_depth()
        
        # First level: 50000 with 1.5 total
        assert bids[0] == (Decimal("50000"), Decimal("1.5"))
        # Second level: 49900 with 2.0 total
        assert bids[1] == (Decimal("49900"), Decimal("2"))


class TestOrderMatching:
    """Test order matching logic."""
    
    def test_match_buy_against_asks(self):
        """Buy orders match against asks."""
        book = OrderBook("BTC-USDT")
        
        # Add sell orders
        sell1 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000"))
        sell2 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50100"))
        book.add_order(sell1)
        book.add_order(sell2)
        
        # Match buy order
        buy = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1.2"), Decimal("50200"))
        matches = book.match_order(buy)
        
        # Should match all of sell1 and part of sell2
        assert len(matches) >= 2
        assert matches[0][0] == sell1  # First match against sell1
    
    def test_match_sell_against_bids(self):
        """Sell orders match against bids."""
        book = OrderBook("BTC-USDT")
        
        # Add buy orders
        buy1 = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        buy2 = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("49900"))
        book.add_order(buy1)
        book.add_order(buy2)
        
        # Match sell order
        sell = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1.2"), Decimal("49800"))
        matches = book.match_order(sell)
        
        # Should match all of buy1 and part of buy2
        assert len(matches) >= 2
        assert matches[0][0] == buy1  # First match against buy1 (better price)
    
    def test_no_match_when_prices_dont_cross(self):
        """No matches when buy price < sell price."""
        book = OrderBook("BTC-USDT")
        
        # Add sell order at 50100
        sell = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100"))
        book.add_order(sell)
        
        # Try to buy at 50000 (below ask)
        buy = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        matches = book.match_order(buy)
        
        assert len(matches) == 0


class TestFOKLiquidityCheck:
    """Test FOK order liquidity validation."""
    
    def test_sufficient_liquidity_single_level(self):
        """FOK succeeds when sufficient liquidity at one price."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("2"), Decimal("50000")))
        
        can_fill = book.can_fill_quantity(OrderSide.BUY, Decimal("1.5"), Decimal("50000"))
        
        assert can_fill is True
    
    def test_sufficient_liquidity_multiple_levels(self):
        """FOK succeeds when sufficient liquidity across levels."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100")))
        
        can_fill = book.can_fill_quantity(OrderSide.BUY, Decimal("1.2"), Decimal("50100"))
        
        assert can_fill is True
    
    def test_insufficient_liquidity(self):
        """FOK fails when insufficient liquidity."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        
        can_fill = book.can_fill_quantity(OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        assert can_fill is False
    
    def test_price_limit_respected(self):
        """FOK only considers orders within price limit."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50200")))
        
        # Can fill 1.0 if we go up to 50200
        assert book.can_fill_quantity(OrderSide.BUY, Decimal("1"), Decimal("50200")) is True
        
        # Cannot fill 1.0 if we stop at 50100
        assert book.can_fill_quantity(OrderSide.BUY, Decimal("1"), Decimal("50100")) is False


class TestOrderBookStatistics:
    """Test order book statistics and monitoring."""
    
    def test_statistics_format(self):
        """Statistics return expected fields."""
        book = OrderBook("BTC-USDT")
        
        book.add_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        book.add_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100")))
        
        stats = book.get_statistics()
        
        assert "symbol" in stats
        assert "total_orders" in stats
        assert "bid_levels" in stats
        assert "ask_levels" in stats
        assert stats["total_orders"] == 2
        assert stats["bid_levels"] == 1
        assert stats["ask_levels"] == 1
