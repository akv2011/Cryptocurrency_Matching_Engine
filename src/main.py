"""
Main entry point for the Cryptocurrency Matching Engine.

Single-process, single-port architecture:
  - REST API    →  http://<host>:<PORT>/api/v1/...
  - Market Data →  ws://<host>:<PORT>/market-data
  - Trade Feed  →  ws://<host>:<PORT>/trades

The PORT environment variable is used by Render (and other PaaS providers)
to indicate which port the container must listen on.  It defaults to 8080
for local development.

WebSocket callback registration is handled by the FastAPI lifespan hook
defined in src/api/rest_api.py — no threading or secondary event loops
needed here.
"""

import os
import uvicorn

from src.api.rest_api import app  # noqa: F401 – import triggers lifespan setup

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
