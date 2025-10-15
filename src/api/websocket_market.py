"""
WebSocket server for real-time market data streaming.

Streams:
- L2 Order Book updates
- BBO (Best Bid/Offer) updates
"""

import asyncio
import json
from typing import Set
from datetime import datetime
from decimal import Decimal
import websockets
from websockets.server import WebSocketServerProtocol

from ..utils.logger import get_logger

logger = get_logger(__name__)

# Connected clients
connected_clients: Set[WebSocketServerProtocol] = set()


def format_decimal(value: Decimal) -> str:
    """Format Decimal as string for JSON serialization."""
    return str(value)


async def handle_client(websocket: WebSocketServerProtocol, path: str):
    """
    Handle WebSocket client connection for market data.
    
    Clients can subscribe to specific symbols or receive all updates.
    """
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    logger.info("market_data_client_connected", extra={"client_id": client_id, "path": path})
    
    # Add client to connected set
    connected_clients.add(websocket)
    
    try:
        # Send welcome message
        await websocket.send(json.dumps({
            "type": "welcome",
            "message": "Connected to market data stream",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }))
        
        # Keep connection alive and handle incoming messages (if any)
        async for message in websocket:
            try:
                data = json.loads(message)
                # Handle subscription requests or other commands
                if data.get("action") == "ping":
                    await websocket.send(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }))
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }))
    
    except websockets.exceptions.ConnectionClosed:
        logger.info("market_data_client_disconnected", extra={"client_id": client_id})
    except Exception as e:
        logger.error("market_data_error", extra={"client_id": client_id, "error": str(e)}, exc_info=True)
    finally:
        # Remove client from connected set
        connected_clients.discard(websocket)


async def broadcast_bbo_update(symbol: str, bbo: tuple):
    """
    Broadcast BBO update to all connected clients.
    
    Args:
        symbol: Trading pair
        bbo: ((bid_price, bid_qty), (ask_price, ask_qty))
    """
    best_bid, best_ask = bbo
    
    message = {
        "type": "bbo",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "symbol": symbol,
        "best_bid": format_decimal(best_bid[0]) if best_bid else None,
        "best_bid_qty": format_decimal(best_bid[1]) if best_bid else None,
        "best_ask": format_decimal(best_ask[0]) if best_ask else None,
        "best_ask_qty": format_decimal(best_ask[1]) if best_ask else None
    }
    
    # Broadcast to all connected clients
    if connected_clients:
        message_json = json.dumps(message)
        disconnected_clients = set()
        
        for client in connected_clients:
            try:
                await client.send(message_json)
            except websockets.exceptions.ConnectionClosed:
                disconnected_clients.add(client)
            except Exception as e:
                logger.error("bbo_broadcast_error", extra={"error": str(e)})
                disconnected_clients.add(client)
        
        # Remove disconnected clients
        connected_clients.difference_update(disconnected_clients)


async def broadcast_orderbook_update(symbol: str, depth: tuple):
    """
    Broadcast L2 orderbook update to all connected clients.
    
    Args:
        symbol: Trading pair
        depth: (bids, asks) where each is list of (price, qty) tuples
    """
    bids, asks = depth
    
    message = {
        "type": "orderbook",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "symbol": symbol,
        "bids": [[format_decimal(price), format_decimal(qty)] for price, qty in bids],
        "asks": [[format_decimal(price), format_decimal(qty)] for price, qty in asks]
    }
    
    # Broadcast to all connected clients
    if connected_clients:
        message_json = json.dumps(message)
        disconnected_clients = set()
        
        for client in connected_clients:
            try:
                await client.send(message_json)
            except websockets.exceptions.ConnectionClosed:
                disconnected_clients.add(client)
            except Exception as e:
                logger.error("orderbook_broadcast_error", extra={"error": str(e)})
                disconnected_clients.add(client)
        
        # Remove disconnected clients
        connected_clients.difference_update(disconnected_clients)


def create_market_data_callbacks(loop: asyncio.AbstractEventLoop):
    """
    Create callback functions for matching engine integration.
    
    These callbacks will be registered with the matching engine to receive
    real-time updates and broadcast them to WebSocket clients.
    
    Args:
        loop: Event loop for running async broadcasts
        
    Returns:
        (bbo_callback, orderbook_callback) tuple
    """
    def bbo_callback(symbol: str, bbo: tuple):
        """Callback for BBO updates from matching engine."""
        asyncio.run_coroutine_threadsafe(
            broadcast_bbo_update(symbol, bbo),
            loop
        )
    
    def orderbook_callback(symbol: str, depth: tuple):
        """Callback for orderbook updates from matching engine."""
        asyncio.run_coroutine_threadsafe(
            broadcast_orderbook_update(symbol, depth),
            loop
        )
    
    return bbo_callback, orderbook_callback


async def start_server(host: str = "0.0.0.0", port: int = 8081):
    """
    Start WebSocket server for market data.
    
    Args:
        host: Server host
        port: Server port
    """
    logger.info("market_data_server_starting", extra={"host": host, "port": port})
    
    async with websockets.serve(handle_client, host, port):
        logger.info("market_data_server_started", extra={"host": host, "port": port})
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    # Run standalone server for testing
    asyncio.run(start_server())
