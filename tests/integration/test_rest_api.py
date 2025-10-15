"""
Quick integration test for REST API.

Tests basic order submission through the API.
"""

from fastapi.testclient import TestClient
from src.api.rest_api import app

def test_rest_api_health():
    """Test health endpoint."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Cryptocurrency Matching Engine"


def test_submit_limit_order():
    """Test submitting a limit order via REST API."""
    client = TestClient(app)
    
    # Submit a buy order
    response = client.post("/api/v1/orders", json={
        "symbol": "BTC-USDT",
        "order_type": "limit",
        "side": "buy",
        "quantity": "1.0",
        "price": "50000.00"
    })
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ["accepted", "filled"]
    assert "order_id" in data
    assert data["symbol"] == "BTC-USDT"


def test_submit_market_order_with_liquidity():
    """Test market order execution."""
    client = TestClient(app)
    
    # First add a sell order
    client.post("/api/v1/orders", json={
        "symbol": "ETH-USDT",
        "order_type": "limit",
        "side": "sell",
        "quantity": "10.0",
        "price": "3000.00"
    })
    
    # Then submit market buy
    response = client.post("/api/v1/orders", json={
        "symbol": "ETH-USDT",
        "order_type": "market",
        "side": "buy",
        "quantity": "5.0"
    })
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "filled"
    assert float(data["filled_quantity"]) == 5.0


def test_get_orderbook():
    """Test orderbook endpoint."""
    client = TestClient(app)
    
    # Add some orders first
    client.post("/api/v1/orders", json={
        "symbol": "BTC-USDT",
        "order_type": "limit",
        "side": "buy",
        "quantity": "1.0",
        "price": "50000.00"
    })
    
    # Get orderbook
    response = client.get("/api/v1/orderbook/BTC-USDT")
    assert response.status_code == 200
    data = response.json()
    assert "bids" in data
    assert "asks" in data
    assert data["symbol"] == "BTC-USDT"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
