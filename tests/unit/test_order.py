"""
Unit tests for Order models.

Tests order creation, validation, state management, and all order types.
"""

import pytest
from decimal import Decimal
from src.engine.order import (
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


class TestOrderValidation:
    """Test order validation and error handling."""
    
    def test_positive_quantity_required(self):
        """Order quantity must be positive."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0"), Decimal("50000"))
        
        with pytest.raises(ValueError, match="quantity must be positive"):
            LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("-1"), Decimal("50000"))
    
    def test_positive_price_required(self):
        """Order price must be positive."""
        with pytest.raises(ValueError, match="price must be positive"):
            LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("0"))
        
        with pytest.raises(ValueError, match="price must be positive"):
            LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("-100"))
    
    def test_limit_order_requires_price(self):
        """Limit orders must have a price."""
        with pytest.raises(ValueError, match="require a price"):
            Order("BTC-USDT", OrderSide.BUY, Decimal("1"), OrderType.LIMIT, price=None)
    
    def test_ioc_order_requires_price(self):
        """IOC orders must have a price."""
        with pytest.raises(ValueError, match="require a price"):
            Order("BTC-USDT", OrderSide.BUY, Decimal("1"), OrderType.IOC, price=None)
    
    def test_fok_order_requires_price(self):
        """FOK orders must have a price."""
        with pytest.raises(ValueError, match="require a price"):
            Order("BTC-USDT", OrderSide.BUY, Decimal("1"), OrderType.FOK, price=None)


class TestMarketOrder:
    """Test market order behavior."""
    
    def test_market_order_creation(self):
        """Market orders can be created without price."""
        order = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"))
        
        assert order.symbol == "BTC-USDT"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("0.5")
        assert order.price is None
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.PENDING
    
    def test_market_order_is_marketable(self):
        """Market orders are always marketable."""
        order = MarketOrder("BTC-USDT", OrderSide.BUY, Decimal("1"))
        assert order.is_marketable is True


class TestLimitOrder:
    """Test limit order behavior."""
    
    def test_limit_order_creation(self):
        """Limit orders must have price."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000"))
        
        assert order.symbol == "BTC-USDT"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("0.5")
        assert order.price == Decimal("50000")
        assert order.order_type == OrderType.LIMIT
    
    def test_buy_limit_marketability(self):
        """Buy limit is marketable if price >= best ask."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        # Marketable: bid price >= ask price
        assert order.is_marketable_against(Decimal("50000")) is True
        assert order.is_marketable_against(Decimal("49999")) is True
        
        # Not marketable: bid price < ask price
        assert order.is_marketable_against(Decimal("50001")) is False
    
    def test_sell_limit_marketability(self):
        """Sell limit is marketable if price <= best bid."""
        order = LimitOrder("BTC-USDT", OrderSide.SELL, Decimal("1"), Decimal("50000"))
        
        # Marketable: ask price <= bid price
        assert order.is_marketable_against(Decimal("50000")) is True
        assert order.is_marketable_against(Decimal("50001")) is True
        
        # Not marketable: ask price > bid price
        assert order.is_marketable_against(Decimal("49999")) is False


class TestIOCOrder:
    """Test IOC (Immediate-Or-Cancel) order behavior."""
    
    def test_ioc_order_creation(self):
        """IOC orders must have price."""
        order = IOCOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000"))
        
        assert order.order_type == OrderType.IOC
        assert order.price == Decimal("50000")
    
    def test_ioc_is_marketable(self):
        """IOC orders are immediately marketable."""
        order = IOCOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        assert order.is_marketable is True


class TestFOKOrder:
    """Test FOK (Fill-Or-Kill) order behavior."""
    
    def test_fok_order_creation(self):
        """FOK orders must have price."""
        order = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000"))
        
        assert order.order_type == OrderType.FOK
        assert order.price == Decimal("50000")
    
    def test_fok_is_marketable(self):
        """FOK orders are immediately marketable."""
        order = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        assert order.is_marketable is True
    
    def test_fok_fill_validation(self):
        """FOK orders can be filled in multiple transactions."""
        order = FOKOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        # FOK orders can be filled across multiple price levels
        # (matching engine ensures complete fill before execution)
        order.fill(Decimal("0.5"), Decimal("50000"))
        assert order.status == OrderStatus.PARTIALLY_FILLED
        
        # Complete the fill
        order.fill(Decimal("0.5"), Decimal("50100"))
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Decimal("1")


class TestOrderFilling:
    """Test order fill operations."""
    
    def test_partial_fill(self):
        """Orders can be partially filled."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        order.fill(Decimal("0.3"), Decimal("50000"))
        
        assert order.filled_quantity == Decimal("0.3")
        assert order.quantity == Decimal("0.7")
        assert order.status == OrderStatus.PARTIALLY_FILLED
    
    def test_complete_fill(self):
        """Orders can be completely filled."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        order.fill(Decimal("1"), Decimal("50000"))
        
        assert order.filled_quantity == Decimal("1")
        assert order.quantity == Decimal("0")
        assert order.status == OrderStatus.FILLED
    
    def test_multiple_fills(self):
        """Orders can be filled in multiple transactions."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        order.fill(Decimal("0.3"), Decimal("50000"))
        order.fill(Decimal("0.2"), Decimal("49999"))
        order.fill(Decimal("0.5"), Decimal("50001"))
        
        assert order.filled_quantity == Decimal("1")
        assert order.quantity == Decimal("0")
        assert order.status == OrderStatus.FILLED
        assert len(order.trades) == 3
    
    def test_overfill_prevented(self):
        """Cannot fill more than remaining quantity."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        with pytest.raises(ValueError, match="exceeds remaining quantity"):
            order.fill(Decimal("1.5"), Decimal("50000"))
    
    def test_average_price_calculation(self):
        """Average price calculated correctly across multiple fills."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        
        order.fill(Decimal("0.5"), Decimal("50000"))  # 0.5 * 50000 = 25000
        order.fill(Decimal("0.5"), Decimal("51000"))  # 0.5 * 51000 = 25500
        
        # Average: (25000 + 25500) / 1 = 50500
        assert order.average_price == Decimal("50500")


class TestOrderStateManagement:
    """Test order state transitions."""
    
    def test_initial_state_pending(self):
        """New orders start in PENDING state."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        assert order.status == OrderStatus.PENDING
    
    def test_accept_order(self):
        """Orders can be accepted."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        order.accept()
        assert order.status == OrderStatus.ACCEPTED
    
    def test_cancel_order(self):
        """Orders can be canceled."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        order.accept()
        order.cancel()
        assert order.status == OrderStatus.CANCELED
    
    def test_cannot_cancel_filled_order(self):
        """Cannot cancel filled orders."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        order.fill(Decimal("1"), Decimal("50000"))
        
        with pytest.raises(ValueError, match="Cannot cancel"):
            order.cancel()
    
    def test_reject_order(self):
        """Orders can be rejected."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("1"), Decimal("50000"))
        order.reject("Insufficient funds")
        assert order.status == OrderStatus.REJECTED


class TestOrderFactory:
    """Test order creation factory function."""
    
    def test_create_market_order(self):
        """Factory creates market orders."""
        order = create_order("BTC-USDT", "market", "buy", "0.5")
        
        assert isinstance(order, MarketOrder)
        assert order.order_type == OrderType.MARKET
    
    def test_create_limit_order(self):
        """Factory creates limit orders."""
        order = create_order("BTC-USDT", "limit", "buy", "0.5", "50000")
        
        assert isinstance(order, LimitOrder)
        assert order.price == Decimal("50000")
    
    def test_create_ioc_order(self):
        """Factory creates IOC orders."""
        order = create_order("BTC-USDT", "ioc", "sell", "1", "50000")
        
        assert isinstance(order, IOCOrder)
        assert order.side == OrderSide.SELL
    
    def test_create_fok_order(self):
        """Factory creates FOK orders."""
        order = create_order("BTC-USDT", "fok", "buy", "2", "49000")
        
        assert isinstance(order, FOKOrder)
    
    def test_invalid_order_type(self):
        """Factory rejects invalid order types."""
        with pytest.raises(ValueError, match="Invalid order_type"):
            create_order("BTC-USDT", "invalid", "buy", "1")
    
    def test_invalid_side(self):
        """Factory rejects invalid sides."""
        with pytest.raises(ValueError, match="Invalid side"):
            create_order("BTC-USDT", "market", "invalid", "1")
    
    def test_invalid_quantity(self):
        """Factory rejects invalid quantities."""
        with pytest.raises(ValueError, match="Invalid quantity"):
            create_order("BTC-USDT", "market", "buy", "not_a_number")
    
    def test_limit_requires_price(self):
        """Factory enforces price requirement for limit orders."""
        with pytest.raises(ValueError, match="require a price"):
            create_order("BTC-USDT", "limit", "buy", "1", None)


class TestOrderSerialization:
    """Test order serialization for API responses."""
    
    def test_order_to_dict(self):
        """Orders can be serialized to dictionary."""
        order = LimitOrder("BTC-USDT", OrderSide.BUY, Decimal("0.5"), Decimal("50000"), user_id="user123")
        order.accept()
        order.fill(Decimal("0.3"), Decimal("50000"))
        
        data = order.to_dict()
        
        assert data["symbol"] == "BTC-USDT"
        assert data["side"] == "buy"
        assert data["order_type"] == "limit"
        assert data["price"] == "50000"
        assert data["original_quantity"] == "0.5"
        assert data["quantity"] == "0.2"
        assert data["filled_quantity"] == "0.3"
        assert data["status"] == "partially_filled"
        assert data["user_id"] == "user123"
        assert "timestamp" in data
        assert "order_id" in data
