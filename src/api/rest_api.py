"""
REST API for order submission.

Implements POST /api/v1/orders endpoint with validation and error handling.
Also mounts FastAPI-native WebSocket endpoints:
  - /market-data   (BBO + L2 orderbook stream)
  - /trades        (trade execution stream)
Both WebSocket streams were previously served as standalone servers on ports
8081 and 8082.  Consolidating everything onto a single port enables
deployment on Render's free tier which exposes only one public port.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional
from decimal import Decimal, InvalidOperation
from datetime import datetime
import json

from ..engine import MatchingEngine, create_order, Order
from ..utils.logger import get_logger
from .ws_managers import market_data_manager, trade_stream_manager

logger = get_logger(__name__)

# Initialize matching engine (singleton)
matching_engine = MatchingEngine()


# ---------------------------------------------------------------------------
# Lifespan: wire matching-engine callbacks to the WS connection managers
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register WebSocket broadcast callbacks with the matching engine on startup.

    The callbacks are cleared first so that repeated lifespan cycles (e.g.
    TestClient instantiated multiple times in the same process) never
    accumulate duplicate callbacks on the module-level engine singleton.
    """
    # Clear any callbacks registered by a previous lifespan cycle
    matching_engine.on_bbo_update_callbacks.clear()
    matching_engine.on_orderbook_update_callbacks.clear()
    matching_engine.on_trade_callbacks.clear()

    bbo_cb, orderbook_cb = market_data_manager.make_callbacks()
    trade_cb = trade_stream_manager.make_callback()

    matching_engine.register_bbo_update_callback(bbo_cb)
    matching_engine.register_orderbook_update_callback(orderbook_cb)
    matching_engine.register_trade_callback(trade_cb)

    logger.info("websocket_callbacks_registered")
    yield
    # Nothing to clean up on shutdown


# Create FastAPI app
app = FastAPI(
    title="Cryptocurrency Matching Engine API",
    description="REG NMS-inspired matching engine with price-time priority",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models

class OrderRequest(BaseModel):
    """Order submission request."""
    symbol: str = Field(..., example="BTC-USDT", description="Trading pair")
    order_type: str = Field(..., example="limit", description="Order type: market, limit, ioc, fok")
    side: str = Field(..., example="buy", description="Order side: buy or sell")
    quantity: str = Field(..., example="0.5", description="Order quantity")
    price: Optional[str] = Field(None, example="50000.00", description="Limit price (required for limit/ioc/fok)")
    user_id: Optional[str] = Field(None, example="user123", description="User identifier")
    
    @validator('symbol')
    def validate_symbol(cls, v):
        if not v or len(v) < 3:
            raise ValueError("Symbol must be at least 3 characters")
        return v.upper()
    
    @validator('order_type')
    def validate_order_type(cls, v):
        valid_types = ['market', 'limit', 'ioc', 'fok']
        if v.lower() not in valid_types:
            raise ValueError(f"Invalid order_type. Must be one of: {', '.join(valid_types)}")
        return v.lower()
    
    @validator('side')
    def validate_side(cls, v):
        if v.lower() not in ['buy', 'sell']:
            raise ValueError("Invalid side. Must be 'buy' or 'sell'")
        return v.lower()
    
    @validator('quantity')
    def validate_quantity(cls, v):
        try:
            qty = Decimal(v)
            if qty <= 0:
                raise ValueError("Quantity must be positive")
        except InvalidOperation:
            raise ValueError(f"Invalid quantity format: {v}")
        return v
    
    @validator('price')
    def validate_price(cls, v, values):
        if v is None:
            return v
        try:
            price = Decimal(v)
            if price <= 0:
                raise ValueError("Price must be positive")
        except InvalidOperation:
            raise ValueError(f"Invalid price format: {v}")
        return v


class OrderResponse(BaseModel):
    """Order submission response."""
    order_id: str
    status: str
    filled_quantity: str
    remaining_quantity: str
    average_price: Optional[str]
    timestamp: str
    symbol: str
    order_type: str
    side: str
    original_quantity: str
    price: Optional[str]
    trades: int = Field(description="Number of trades executed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "order_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "status": "filled",
                "filled_quantity": "0.5",
                "remaining_quantity": "0.0",
                "average_price": "50000.00",
                "timestamp": "2025-10-15T12:34:56.789Z",
                "symbol": "BTC-USDT",
                "order_type": "limit",
                "side": "buy",
                "original_quantity": "0.5",
                "price": "50000.00",
                "trades": 2
            }
        }


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    message: str
    timestamp: str


# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Cryptocurrency Matching Engine",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/api/v1/health")
async def health_check():
    """Detailed health check with engine statistics."""
    stats = matching_engine.get_statistics()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "statistics": stats
    }


@app.post(
    "/api/v1/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid order parameters"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def submit_order(order_request: OrderRequest):
    """
    Submit an order to the matching engine.
    
    Processes the order immediately with the following flow:
    1. Validate order parameters
    2. Match against existing orders (if marketable)
    3. Rest unmatched portion on book (for limit orders)
    4. Return execution report
    
    **Order Types:**
    - **market**: Execute immediately at best available price(s)
    - **limit**: Execute at specified price or better, rest on book
    - **ioc**: Immediate-Or-Cancel - execute immediately, cancel remainder
    - **fok**: Fill-Or-Kill - execute entire order or reject completely
    
    **Response Status Values:**
    - **filled**: Order completely filled
    - **partially_filled**: Order partially filled, remainder resting on book (limit only)
    - **accepted**: Order accepted and resting on book (limit only, not immediately marketable)
    - **canceled**: Order canceled (IOC with partial fill, or FOK rejected)
    - **rejected**: Order rejected (FOK with insufficient liquidity, or validation error)
    """
    try:
        # Log order submission
        logger.info(
            "order_submitted",
            extra={
                "symbol": order_request.symbol,
                "order_type": order_request.order_type,
                "side": order_request.side,
                "quantity": order_request.quantity,
                "price": order_request.price,
                "user_id": order_request.user_id
            }
        )
        
        # Create order object
        try:
            order = create_order(
                symbol=order_request.symbol,
                order_type=order_request.order_type,
                side=order_request.side,
                quantity=order_request.quantity,
                price=order_request.price,
                user_id=order_request.user_id
            )
        except ValueError as e:
            logger.warning("order_validation_failed", extra={"error": str(e), "request": order_request.dict()})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        # Submit to matching engine
        processed_order, trades = matching_engine.submit_order(order)
        
        # Log execution results
        logger.info(
            "order_processed",
            extra={
                "order_id": processed_order.order_id,
                "status": processed_order.status.value,
                "filled_quantity": str(processed_order.filled_quantity),
                "trades": len(trades)
            }
        )
        
        # Build response
        response = OrderResponse(
            order_id=processed_order.order_id,
            status=processed_order.status.value,
            filled_quantity=str(processed_order.filled_quantity),
            remaining_quantity=str(processed_order.quantity),
            average_price=str(processed_order.average_price) if processed_order.average_price else None,
            timestamp=processed_order.timestamp.isoformat() + "Z",
            symbol=processed_order.symbol,
            order_type=processed_order.order_type.value,
            side=processed_order.side.value,
            original_quantity=str(processed_order.original_quantity),
            price=str(processed_order.price) if processed_order.price else None,
            trades=len(trades)
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "order_processing_error",
            extra={"error": str(e), "request": order_request.dict()},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error processing order: {str(e)}"
        )


@app.get("/api/v1/orderbook/{symbol}")
async def get_orderbook(symbol: str, levels: int = 10):
    """
    Get L2 order book depth for a symbol.
    
    Args:
        symbol: Trading pair (e.g., BTC-USDT)
        levels: Number of price levels to return (default 10)
        
    Returns:
        Order book with bids and asks
    """
    symbol = symbol.upper()
    depth = matching_engine.get_market_depth(symbol, levels)
    
    if depth is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No order book found for symbol {symbol}"
        )
    
    bids, asks = depth
    
    return {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "bids": [[str(price), str(qty)] for price, qty in bids],
        "asks": [[str(price), str(qty)] for price, qty in asks]
    }


@app.get("/api/v1/bbo/{symbol}")
async def get_bbo(symbol: str):
    """
    Get Best Bid and Offer (BBO) for a symbol.
    
    Args:
        symbol: Trading pair (e.g., BTC-USDT)
        
    Returns:
        Best bid and ask with quantities
    """
    symbol = symbol.upper()
    bbo = matching_engine.get_bbo(symbol)
    
    if bbo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No order book found for symbol {symbol}"
        )
    
    best_bid, best_ask = bbo
    
    return {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "best_bid": str(best_bid[0]) if best_bid else None,
        "best_bid_qty": str(best_bid[1]) if best_bid else None,
        "best_ask": str(best_ask[0]) if best_ask else None,
        "best_ask_qty": str(best_ask[1]) if best_ask else None
    }


@app.delete("/api/v1/orders/{symbol}/{order_id}")
async def cancel_order(symbol: str, order_id: str):
    """
    Cancel an order.
    
    Args:
        symbol: Trading pair
        order_id: Order ID to cancel
        
    Returns:
        Canceled order details
    """
    symbol = symbol.upper()
    
    canceled_order = matching_engine.cancel_order(symbol, order_id)
    
    if canceled_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found for symbol {symbol}"
        )
    
    logger.info(
        "order_canceled",
        extra={
            "order_id": order_id,
            "symbol": symbol
        }
    )
    
    return {
        "order_id": canceled_order.order_id,
        "status": canceled_order.status.value,
        "message": "Order canceled successfully"
    }


@app.get("/api/v1/statistics")
async def get_statistics():
    """Get matching engine statistics."""
    stats = matching_engine.get_statistics()
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **stats
    }


# ---------------------------------------------------------------------------
# /health  — Render free-tier healthcheck path
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint used by Render (and other orchestrators)."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# WebSocket endpoints (single-port, FastAPI-native)
# ---------------------------------------------------------------------------

@app.websocket("/market-data")
async def ws_market_data(websocket: WebSocket):
    """
    Real-time market data stream.

    Pushes BBO and L2 orderbook updates for every symbol.
    Message types: ``welcome``, ``bbo``, ``orderbook``, ``pong``, ``error``.

    Clients may send ``{"action": "ping"}`` to receive a pong reply.
    """
    await market_data_manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                if data.get("action") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }))
    except WebSocketDisconnect:
        market_data_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("market_data_ws_error", extra={"error": str(exc)}, exc_info=True)
        market_data_manager.disconnect(websocket)


@app.websocket("/trades")
async def ws_trades(websocket: WebSocket):
    """
    Real-time trade execution stream.

    Pushes trade execution reports as they are generated by the matching engine.
    Message types: ``welcome``, ``trade`` (via trade.to_dict()), ``pong``, ``error``.

    Clients may send ``{"action": "ping"}`` to receive a pong reply.
    """
    await trade_stream_manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                if data.get("action") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }))
    except WebSocketDisconnect:
        trade_stream_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("trade_stream_ws_error", extra={"error": str(exc)}, exc_info=True)
        trade_stream_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Export matching engine for any code that still imports it directly
# ---------------------------------------------------------------------------

def get_matching_engine() -> MatchingEngine:
    """Get the matching engine instance."""
    return matching_engine
