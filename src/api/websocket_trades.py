"""
WebSocket server for real-time trade execution streaming.

Streams:
- Trade execution reports with maker/taker details
"""

import asyncio
import json
from typing import Set
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from ..engine import Trade
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Connected clients
connected_clients: Set[WebSocketServerProtocol] = set()


async def handle_client(websocket: WebSocketServerProtocol, path: str):
    """
    Handle WebSocket client connection for trade execution stream.
    
    Clients receive all trade execution reports in real-time.
    """
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    logger.info("trade_stream_client_connected", extra={"client_id": client_id, "path": path})
    
    # Add client to connected set
    connected_clients.add(websocket)
    
    try:
        # Send welcome message
        await websocket.send(json.dumps({
            "type": "welcome",
            "message": "Connected to trade execution stream",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }))
        
        # Keep connection alive and handle incoming messages (if any)
        async for message in websocket:
            try:
                data = json.loads(message)
                # Handle ping or other commands
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
        logger.info("trade_stream_client_disconnected", extra={"client_id": client_id})
    except Exception as e:
        logger.error("trade_stream_error", extra={"client_id": client_id, "error": str(e)}, exc_info=True)
    finally:
        # Remove client from connected set
        connected_clients.discard(websocket)


async def broadcast_trade(trade: Trade):
    """
    Broadcast trade execution to all connected clients.
    
    Args:
        trade: Trade object from matching engine
    """
    message = trade.to_dict()
    
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
                logger.error("trade_broadcast_error", extra={"error": str(e)})
                disconnected_clients.add(client)
        
        # Remove disconnected clients
        connected_clients.difference_update(disconnected_clients)
        
        logger.debug("trade_broadcasted", extra={
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "clients": len(connected_clients)
        })


def create_trade_callback(loop: asyncio.AbstractEventLoop):
    """
    Create callback function for matching engine integration.
    
    This callback will be registered with the matching engine to receive
    trade executions and broadcast them to WebSocket clients.
    
    Args:
        loop: Event loop for running async broadcasts
        
    Returns:
        Trade callback function
    """
    def trade_callback(trade: Trade):
        """Callback for trade executions from matching engine."""
        asyncio.run_coroutine_threadsafe(
            broadcast_trade(trade),
            loop
        )
    
    return trade_callback


async def start_server(host: str = "0.0.0.0", port: int = 8082):
    """
    Start WebSocket server for trade execution stream.
    
    Args:
        host: Server host
        port: Server port
    """
    logger.info("trade_stream_server_starting", extra={"host": host, "port": port})
    
    async with websockets.serve(handle_client, host, port):
        logger.info("trade_stream_server_started", extra={"host": host, "port": port})
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    # Run standalone server for testing
    asyncio.run(start_server())
