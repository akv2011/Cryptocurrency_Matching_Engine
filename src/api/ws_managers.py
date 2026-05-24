"""
WebSocket connection managers for FastAPI-native WebSocket endpoints.

These managers replace the standalone `websockets`-library servers that
previously ran on ports 8081 and 8082.  They keep the same JSON message
shapes so existing clients continue to work without any changes.

Design:
  - MarketDataManager  – handles /market-data  (BBO + L2 orderbook)
  - TradeStreamManager – handles /trades       (trade execution reports)

Each manager:
  1. Holds a set of live FastAPI WebSocket connections.
  2. Exposes sync callback hooks (bbo_callback, orderbook_callback /
     trade_callback) that can be registered directly with the matching
     engine.  Those callbacks schedule async coroutines on the running
     event loop via asyncio.get_event_loop().create_task(), which is
     safe because uvicorn's event loop is already running when startup
     fires.
  3. Has a broadcast() coroutine that fans out a JSON message to every
     live connection, pruning any that have disconnected.
"""

import asyncio
import json
from typing import Set
from datetime import datetime
from decimal import Decimal

from fastapi import WebSocket, WebSocketDisconnect

from ..engine import Trade
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _format_decimal(value: Decimal) -> str:
    """Format Decimal as string for JSON serialisation (same as legacy servers)."""
    return str(value)


# ---------------------------------------------------------------------------
# Market Data Manager
# ---------------------------------------------------------------------------

class MarketDataManager:
    """
    Connection manager for the /market-data WebSocket endpoint.

    Streams BBO and L2 orderbook updates to all connected clients.
    """

    def __init__(self):
        self._clients: Set[WebSocket] = set()

    # -- Connection lifecycle -----------------------------------------------

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and add it to the active set."""
        await websocket.accept()
        self._clients.add(websocket)
        client_id = self._client_id(websocket)
        logger.info("market_data_client_connected", extra={"client_id": client_id})
        await websocket.send_text(json.dumps({
            "type": "welcome",
            "message": "Connected to market data stream",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active set on disconnect."""
        self._clients.discard(websocket)
        client_id = self._client_id(websocket)
        logger.info("market_data_client_disconnected", extra={"client_id": client_id})

    # -- Broadcasting -------------------------------------------------------

    async def broadcast(self, message: str) -> None:
        """Send *message* (a JSON string) to every connected client."""
        if not self._clients:
            return

        dead: Set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        self._clients -= dead

    async def broadcast_bbo_update(self, symbol: str, bbo: tuple) -> None:
        """Broadcast a BBO update.  Same JSON shape as the legacy server."""
        best_bid, best_ask = bbo
        message = json.dumps({
            "type": "bbo",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "best_bid": _format_decimal(best_bid[0]) if best_bid else None,
            "best_bid_qty": _format_decimal(best_bid[1]) if best_bid else None,
            "best_ask": _format_decimal(best_ask[0]) if best_ask else None,
            "best_ask_qty": _format_decimal(best_ask[1]) if best_ask else None,
        })
        await self.broadcast(message)

    async def broadcast_orderbook_update(self, symbol: str, depth: tuple) -> None:
        """Broadcast an L2 orderbook update.  Same JSON shape as the legacy server."""
        bids, asks = depth
        message = json.dumps({
            "type": "orderbook",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "bids": [[_format_decimal(p), _format_decimal(q)] for p, q in bids],
            "asks": [[_format_decimal(p), _format_decimal(q)] for p, q in asks],
        })
        await self.broadcast(message)

    # -- Matching-engine callback factories ---------------------------------

    def make_callbacks(self):
        """
        Return (bbo_callback, orderbook_callback) suitable for direct
        registration with MatchingEngine.

        The matching engine calls these from a *sync* context (inside
        submit_order), so we schedule the async broadcast coroutines onto
        the running uvicorn event loop with create_task().
        """
        def bbo_callback(symbol: str, bbo: tuple) -> None:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.broadcast_bbo_update(symbol, bbo))
            except Exception as exc:
                logger.error("bbo_callback_error", extra={"error": str(exc)})

        def orderbook_callback(symbol: str, depth: tuple) -> None:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.broadcast_orderbook_update(symbol, depth))
            except Exception as exc:
                logger.error("orderbook_callback_error", extra={"error": str(exc)})

        return bbo_callback, orderbook_callback

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _client_id(ws: WebSocket) -> str:
        try:
            return f"{ws.client.host}:{ws.client.port}"
        except Exception:
            return "unknown"


# ---------------------------------------------------------------------------
# Trade Stream Manager
# ---------------------------------------------------------------------------

class TradeStreamManager:
    """
    Connection manager for the /trades WebSocket endpoint.

    Streams trade execution reports to all connected clients.
    """

    def __init__(self):
        self._clients: Set[WebSocket] = set()

    # -- Connection lifecycle -----------------------------------------------

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and add it to the active set."""
        await websocket.accept()
        self._clients.add(websocket)
        client_id = self._client_id(websocket)
        logger.info("trade_stream_client_connected", extra={"client_id": client_id})
        await websocket.send_text(json.dumps({
            "type": "welcome",
            "message": "Connected to trade execution stream",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active set on disconnect."""
        self._clients.discard(websocket)
        client_id = self._client_id(websocket)
        logger.info("trade_stream_client_disconnected", extra={"client_id": client_id})

    # -- Broadcasting -------------------------------------------------------

    async def broadcast(self, message: str) -> None:
        """Send *message* (a JSON string) to every connected client."""
        if not self._clients:
            return

        dead: Set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        self._clients -= dead

    async def broadcast_trade(self, trade: Trade) -> None:
        """Broadcast a trade execution report.  Same JSON shape as legacy server."""
        message = json.dumps(trade.to_dict())
        await self.broadcast(message)
        logger.debug("trade_broadcasted", extra={
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "clients": len(self._clients),
        })

    # -- Matching-engine callback factory -----------------------------------

    def make_callback(self):
        """
        Return a trade_callback suitable for direct registration with
        MatchingEngine.

        The matching engine calls this from a *sync* context, so we
        schedule the async broadcast coroutine onto the running uvicorn
        event loop with create_task().
        """
        def trade_callback(trade: Trade) -> None:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.broadcast_trade(trade))
            except Exception as exc:
                logger.error("trade_callback_error", extra={"error": str(exc)})

        return trade_callback

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _client_id(ws: WebSocket) -> str:
        try:
            return f"{ws.client.host}:{ws.client.port}"
        except Exception:
            return "unknown"


# ---------------------------------------------------------------------------
# Module-level singletons shared between rest_api.py and main.py
# ---------------------------------------------------------------------------

market_data_manager = MarketDataManager()
trade_stream_manager = TradeStreamManager()
