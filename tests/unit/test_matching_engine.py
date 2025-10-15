"""
Unit tests for Matching Engine.

Tests REG NMS-inspired matching logic with price-time priority and trade-through prevention.
"""

import pytest
from decimal import Decimal
from src.engine import (
    MatchingEngine,
    MarketOrder,
    LimitOrder,
    IOCOrder,
    FOKOrder,
    OrderSide,
    OrderStatus
)


class TestMatchingEngineBasics:
    """Test basic matching engine operations."""
    
    def test_engine_initialization(self):
        """Engine initializes with no order books."""
        engine = MatchingEngine()
        
        assert len(engine.order_books) == 0
        assert engine.trade_counter == 0
    
    def test_create_orderbook_on_demand(self):
        """Order books created automatically for new symbols."""
        engine = MatchingEngine()
        
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        engine.submit_order(order)
        
        assert "BTC-USDT" in engine.order_books


class TestMarketOrderMatching:
    """Test market order execution."""
    
    def test_market_buy_full_fill(self):
        """Market buy order fills completely against available asks."""
        engine = MatchingEngine()
        
        # Add sell orders
        sell1 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000"))
        engine.submit_order(sell1)
        
        # Submit market buy
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.FILLED
        assert processed_order.filled_quantity == Decimal("1")
        assert len(trades) == 1
        assert trades[0].price == Decimal("50000")
    
    def test_market_sell_full_fill(self):
        """Market sell order fills completely against available bids."""
        engine = MatchingEngine()
        
        # Add buy order
        buy1 = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        engine.submit_order(buy1)
        
        # Submit market sell
        sell = MarketOrder("BTC-USDT", OrderSide.SELL, Decimal("1"))
        processed_order, trades = engine.submit_order(sell)
        
        assert processed_order.status == OrderStatus.FILLED
        assert len(trades) == 1
        assert trades[0].price == Decimal("50000")
    
    def test_market_order_walks_book(self):
        """Market order walks through multiple price levels."""
        engine = MatchingEngine()
        
        # Add multiple sell orders at different prices
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50100")))
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50200")))
        
        # Submit market buy for more than first level
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1.2"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.FILLED
        assert len(trades) == 3  # Matched at 3 different price levels
        assert trades[0].price == Decimal("50000")  # Best price first
        assert trades[1].price == Decimal("50100")
        assert trades[2].price == Decimal("50200")
    
    def test_market_order_partial_fill_insufficient_liquidity(self):
        """Market order partially fills when liquidity runs out."""
        engine = MatchingEngine()
        
        # Add limited sell orders
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        
        # Try to buy more than available
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.filled_quantity == Decimal("0.5")
        assert processed_order.quantity == Decimal("0.5")  # Unfilled portion
        assert len(trades) == 1


class TestLimitOrderMatching:
    """Test limit order execution."""
    
    def test_limit_order_immediate_match(self):
        """Marketable limit order executes immediately."""
        engine = MatchingEngine()
        
        # Add sell order at 50000
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000")))
        
        # Buy at 50100 (crosses spread)
        buy = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50100"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.FILLED
        assert len(trades) == 1
        assert trades[0].price == Decimal("50000")  # Executes at maker price
    
    def test_limit_order_rests_on_book(self):
        """Non-marketable limit order rests on book."""
        engine = MatchingEngine()
        
        # Add sell order at 50100
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100")))
        
        # Buy at 50000 (doesn't cross spread)
        buy = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.ACCEPTED
        assert processed_order.quantity == Decimal("1")  # Nothing filled
        assert len(trades) == 0
        
        # Verify order is on book
        order_book = engine.get_orderbook("BTC-USDT")
        assert buy.order_id in order_book.orders
    
    def test_limit_order_partial_fill_then_rest(self):
        """Limit order partially fills then rests remainder."""
        engine = MatchingEngine()
        
        # Add sell order for 0.5
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        
        # Buy 1.0 at 50000 (only 0.5 available)
        buy = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.PARTIALLY_FILLED
        assert processed_order.filled_quantity == Decimal("0.5")
        assert processed_order.quantity == Decimal("0.5")  # Resting on book
        assert len(trades) == 1
        
        # Verify remainder is on book
        order_book = engine.get_orderbook("BTC-USDT")
        assert buy.order_id in order_book.orders


class TestIOCOrderMatching:
    """Test IOC (Immediate-Or-Cancel) order execution."""
    
    def test_ioc_full_fill(self):
        """IOC fills completely when sufficient liquidity."""
        engine = MatchingEngine()
        
        # Add sell orders
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000")))
        
        # IOC buy
        buy = IOCOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.FILLED
        assert len(trades) == 1
    
    def test_ioc_partial_fill_cancels_remainder(self):
        """IOC partially fills then cancels unfilled portion."""
        engine = MatchingEngine()
        
        # Add partial liquidity
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        
        # IOC buy for more than available
        buy = IOCOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.filled_quantity == Decimal("0.5")
        assert processed_order.status == OrderStatus.CANCELED  # Remainder canceled
        assert len(trades) == 1
        
        # Verify NOT on book
        order_book = engine.get_orderbook("BTC-USDT")
        assert buy.order_id not in order_book.orders
    
    def test_ioc_no_match_immediate_cancel(self):
        """IOC cancels immediately when no matches."""
        engine = MatchingEngine()
        
        # No orders on book
        buy = IOCOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.CANCELED
        assert processed_order.filled_quantity == Decimal("0")
        assert len(trades) == 0


class TestFOKOrderMatching:
    """Test FOK (Fill-Or-Kill) order execution."""
    
    def test_fok_full_fill_sufficient_liquidity(self):
        """FOK fills completely when sufficient liquidity."""
        engine = MatchingEngine()
        
        # Add sufficient liquidity
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1.5"), Decimal("50000")))
        
        # FOK buy for 1.0
        buy = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.FILLED
        assert processed_order.filled_quantity == Decimal("1")
        assert len(trades) > 0
    
    def test_fok_rejected_insufficient_liquidity(self):
        """FOK rejected when insufficient liquidity."""
        engine = MatchingEngine()
        
        # Add insufficient liquidity
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        
        # FOK buy for 1.0 (more than available)
        buy = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.REJECTED
        assert processed_order.filled_quantity == Decimal("0")
        assert len(trades) == 0
    
    def test_fok_rejected_no_liquidity(self):
        """FOK rejected when no liquidity."""
        engine = MatchingEngine()
        
        # No orders on book
        buy = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.REJECTED
        assert len(trades) == 0
    
    def test_fok_checks_liquidity_across_levels(self):
        """FOK checks total liquidity across multiple price levels."""
        engine = MatchingEngine()
        
        # Add liquidity across levels
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000")))
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50100")))
        
        # FOK buy for 1.0 at max price 50100
        buy = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50100"))
        processed_order, trades = engine.submit_order(buy)
        
        assert processed_order.status == OrderStatus.FILLED
        assert len(trades) == 2  # Filled across both levels


class TestPriceTimePriority:
    """Test REG NMS-inspired price-time priority."""
    
    def test_price_priority_best_price_first(self):
        """Better prices execute before worse prices."""
        engine = MatchingEngine()
        
        # Add sell orders at different prices
        sell_high = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50200"))
        sell_low = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000"))
        sell_mid = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50100"))
        
        engine.submit_order(sell_high)
        engine.submit_order(sell_low)
        engine.submit_order(sell_mid)
        
        # Market buy
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("2"))
        _, trades = engine.submit_order(buy)
        
        # Should execute at best prices first
        assert trades[0].price == Decimal("50000")
        assert trades[1].price == Decimal("50100")
    
    def test_time_priority_fifo_at_same_price(self):
        """Orders at same price execute in FIFO order."""
        engine = MatchingEngine()
        
        # Add sell orders at same price in sequence
        sell1 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000"))
        sell2 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000"))
        sell3 = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50000"))
        
        engine.submit_order(sell1)
        engine.submit_order(sell2)
        engine.submit_order(sell3)
        
        # Buy enough to match first two
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        _, trades = engine.submit_order(buy)
        
        # Should match sell1 and sell2 in that order
        assert len(trades) == 2
        assert trades[0].maker_order_id == sell1.order_id
        assert trades[1].maker_order_id == sell2.order_id


class TestTradeThroughPrevention:
    """Test that trade-throughs are prevented."""
    
    def test_no_trade_through_matches_best_price_first(self):
        """Incoming order matches at best available price first."""
        engine = MatchingEngine()
        
        # Add sell orders at different prices
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000")))
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50200")))
        
        # Buy at high price - should still get best available
        buy = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("51000"))
        _, trades = engine.submit_order(buy)
        
        # Must execute at 50000 (best ask), not 50200 or 51000
        assert trades[0].price == Decimal("50000")
    
    def test_partial_fills_at_better_prices_first(self):
        """Order fills at better prices before moving to worse prices."""
        engine = MatchingEngine()
        
        # Add liquidity at multiple levels
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.3"), Decimal("50000")))
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("0.5"), Decimal("50100")))
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50200")))
        
        # Buy 1.0 - should fill all of 50000, all of 50100, partial 50200
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        _, trades = engine.submit_order(buy)
        
        # Verify execution order
        assert trades[0].price == Decimal("50000")
        assert trades[0].quantity == Decimal("0.3")
        assert trades[1].price == Decimal("50100")
        assert trades[1].quantity == Decimal("0.5")
        assert trades[2].price == Decimal("50200")
        assert trades[2].quantity == Decimal("0.2")


class TestOrderCancellation:
    """Test order cancellation."""
    
    def test_cancel_resting_order(self):
        """Resting orders can be canceled."""
        engine = MatchingEngine()
        
        # Add resting order
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        engine.submit_order(order)
        
        # Cancel it
        canceled = engine.cancel_order("BTC-USDT", order.order_id)
        
        assert canceled is not None
        assert canceled.status == OrderStatus.CANCELED
        
        # Verify removed from book
        order_book = engine.get_orderbook("BTC-USDT")
        assert order.order_id not in order_book.orders
    
    def test_cancel_nonexistent_order(self):
        """Canceling nonexistent order returns None."""
        engine = MatchingEngine()
        
        canceled = engine.cancel_order("BTC-USDT", "nonexistent_id")
        
        assert canceled is None


class TestTradeGeneration:
    """Test trade record generation."""
    
    def test_trade_has_required_fields(self):
        """Trades include all required fields."""
        engine = MatchingEngine()
        
        # Setup and execute trade
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000")))
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        _, trades = engine.submit_order(buy)
        
        trade = trades[0]
        assert trade.trade_id is not None
        assert trade.symbol == "BTC-USDT"
        assert trade.price == Decimal("50000")
        assert trade.quantity == Decimal("1")
        assert trade.maker_order_id is not None
        assert trade.taker_order_id == buy.order_id
        assert trade.aggressor_side == OrderSide.BUY
        assert trade.timestamp is not None
    
    def test_trade_serialization(self):
        """Trades can be serialized to dict."""
        engine = MatchingEngine()
        
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000")))
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        _, trades = engine.submit_order(buy)
        
        trade_dict = trades[0].to_dict()
        
        assert trade_dict["type"] == "trade"
        assert "trade_id" in trade_dict
        assert "timestamp" in trade_dict


class TestCallbacks:
    """Test engine callbacks for event notifications."""
    
    def test_trade_callback_triggered(self):
        """Trade callback triggered on execution."""
        engine = MatchingEngine()
        trades_received = []
        
        def trade_callback(trade):
            trades_received.append(trade)
        
        engine.register_trade_callback(trade_callback)
        
        # Execute trade
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000")))
        buy = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        engine.submit_order(buy)
        
        assert len(trades_received) == 1
    
    def test_bbo_callback_triggered(self):
        """BBO callback triggered on book updates."""
        engine = MatchingEngine()
        bbo_updates = []
        
        def bbo_callback(symbol, bbo):
            bbo_updates.append((symbol, bbo))
        
        engine.register_bbo_update_callback(bbo_callback)
        
        # Add order (triggers BBO update)
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        
        assert len(bbo_updates) > 0
        assert bbo_updates[0][0] == "BTC-USDT"


class TestEngineStatistics:
    """Test engine statistics and monitoring."""
    
    def test_statistics_format(self):
        """Statistics return expected fields."""
        engine = MatchingEngine()
        
        # Add some orders
        engine.submit_order(LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000")))
        engine.submit_order(LimitOrder("ETH-USDT", OrderSide.SELL, Decimal("10"), Decimal("3000")))
        
        stats = engine.get_statistics()
        
        assert "total_symbols" in stats
        assert "total_orders" in stats
        assert "total_trades" in stats
        assert stats["total_symbols"] == 2
