"""
Main entry point for the Cryptocurrency Matching Engine.

Starts:
- REST API server (FastAPI/Uvicorn)
- WebSocket market data server
- WebSocket trade execution server
"""

import asyncio
import threading
from typing import Optional
import uvicorn
from fastapi import FastAPI

from src.api.rest_api import app, get_matching_engine
from src.api.websocket_market import start_server as start_market_data_server, create_market_data_callbacks
from src.api.websocket_trades import start_server as start_trade_stream_server, create_trade_callback
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Configuration
REST_API_HOST = "0.0.0.0"
REST_API_PORT = 8080
MARKET_DATA_WS_HOST = "0.0.0.0"
MARKET_DATA_WS_PORT = 8081
TRADE_STREAM_WS_HOST = "0.0.0.0"
TRADE_STREAM_WS_PORT = 8082


async def run_websocket_servers():
    """Run both WebSocket servers concurrently."""
    # Get event loop for callbacks
    loop = asyncio.get_event_loop()
    
    # Get matching engine instance
    matching_engine = get_matching_engine()
    
    # Create and register callbacks
    bbo_callback, orderbook_callback = create_market_data_callbacks(loop)
    trade_callback = create_trade_callback(loop)
    
    matching_engine.register_bbo_update_callback(bbo_callback)
    matching_engine.register_orderbook_update_callback(orderbook_callback)
    matching_engine.register_trade_callback(trade_callback)
    
    logger.info("websocket_callbacks_registered")
    
    # Run both WebSocket servers concurrently
    await asyncio.gather(
        start_market_data_server(MARKET_DATA_WS_HOST, MARKET_DATA_WS_PORT),
        start_trade_stream_server(TRADE_STREAM_WS_HOST, TRADE_STREAM_WS_PORT)
    )


def run_rest_api():
    """Run REST API server with Uvicorn."""
    logger.info("rest_api_starting", extra={
        "host": REST_API_HOST,
        "port": REST_API_PORT
    })
    
    uvicorn.run(
        app,
        host=REST_API_HOST,
        port=REST_API_PORT,
        log_level="info",
        access_log=True
    )


def main():
    """
    Main entry point - starts all servers.
    
    Architecture:
    - REST API runs on port 8080 (order submission)
    - Market Data WebSocket on port 8081 (BBO, orderbook)
    - Trade Stream WebSocket on port 8082 (execution reports)
    """
    logger.info("matching_engine_starting")
    
    # Start WebSocket servers in separate thread with its own event loop
    def run_websockets():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_websocket_servers())
    
    websocket_thread = threading.Thread(target=run_websockets, daemon=True)
    websocket_thread.start()
    
    logger.info("websocket_servers_started")
    
    # Run REST API in main thread (blocking)
    run_rest_api()


if __name__ == "__main__":
    main()
