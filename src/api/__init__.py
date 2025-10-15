"""
API module for REST and WebSocket endpoints.
"""

from .rest_api import app, get_matching_engine
from .websocket_market import start_server as start_market_data_server, create_market_data_callbacks
from .websocket_trades import start_server as start_trade_stream_server, create_trade_callback

__all__ = [
    "app",
    "get_matching_engine",
    "start_market_data_server",
    "start_trade_stream_server",
    "create_market_data_callbacks",
    "create_trade_callback"
]
