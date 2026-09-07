# High-Performance Cryptocurrency Matching Engine

A production-grade cryptocurrency matching engine implementing REG NMS-inspired principles with strict price-time priority and internal order protection.

## Deployment (Render free tier)

The engine is deployed as a single Docker container on
[Render](https://render.com), one process, one port.

### Architecture (single-port)

| Endpoint | URL |
|---|---|
| REST API | `https://<host>/api/v1/...` |
| Interactive docs | `https://<host>/docs` |
| Health check | `https://<host>/health` |
| Market Data (BBO + orderbook) | `wss://<host>/market-data` |
| Trade Execution stream | `wss://<host>/trades` |

All three transport layers run inside the same uvicorn process on the
port supplied by Render's `PORT` environment variable (defaults to 8080
locally).

### Deploy to Render

1. Push this repo to GitHub.
2. In the [Render dashboard](https://dashboard.render.com) choose
   **New > Web Service**, connect the repo, and select **Docker** as
   the environment.
3. Render auto-detects `render.yaml` and creates a free-tier web
   service.  No additional environment variables are required.
4. Once deployed, your live URLs will be:
   - `https://<your-render-slug>.onrender.com/docs`
   - `wss://<your-render-slug>.onrender.com/market-data`
   - `wss://<your-render-slug>.onrender.com/trades`

### Rebuild Docker locally

```bash
# Build image
docker build -t crypto-matching-engine .

# Run locally (same behaviour as Render)
docker run -p 8080:8080 crypto-matching-engine

# Or override the port
docker run -e PORT=9000 -p 9000:9000 crypto-matching-engine
```

---

## 🎯 Project Goals

Build a high-performance matching engine capable of:
- Processing **>1000 orders/second**
- **<1ms** order processing latency (p99)
- **<100μs** BBO update latency (p99)  
- **<500μs** trade generation latency (p99)

### Core Features
- ✅ REG NMS-inspired price-time priority matching
- ✅ Internal order protection (no trade-throughs)
- ✅ Multiple order types (Market, Limit, IOC, FOK)
- ✅ REST API for order submission
- ✅ WebSocket APIs for real-time market data and trades
- ✅ Comprehensive logging and audit trails
- ✅ High test coverage (>90%)

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- pip or conda

### Installation

```bash
# Clone repository (already done)
cd Cryptocurrency_Matching_Engine

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Unix/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Engine

```bash
# Start the matching engine
python src/main.py

# The engine will start:
# - REST API on http://localhost:8080
# - WebSocket Market Data on ws://localhost:8080/market-data
# - WebSocket Trades on ws://localhost:8080/trades
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test suites
pytest tests/unit/ -v            # Unit tests
pytest tests/integration/ -v     # Integration tests  
pytest tests/performance/ -v     # Performance benchmarks

# View coverage report
open htmlcov/index.html  # or start htmlcov/index.html on Windows
```

## 📡 API Usage

### REST API - Submit Orders

```bash
# Submit a limit buy order
curl -X POST http://localhost:8080/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USDT",
    "order_type": "limit",
    "side": "buy",
    "quantity": "0.5",
    "price": "50000.00"
  }'

# Response
{
  "order_id": "order_123456",
  "status": "accepted",
  "filled_quantity": "0.0",
  "remaining_quantity": "0.5",
  "average_price": "0.00",
  "timestamp": "2025-10-15T12:34:56.789Z"
}
```

### WebSocket - Market Data

```javascript
// Connect to market data feed
const ws = new WebSocket('ws://localhost:8080/market-data');

ws.on('message', (data) => {
  const update = JSON.parse(data);
  
  if (update.type === 'bbo') {
    console.log(`BBO Update: Bid ${update.best_bid} @ ${update.best_bid_qty}, Ask ${update.best_ask} @ ${update.best_ask_qty}`);
  }
  
  if (update.type === 'orderbook') {
    console.log('Order Book Update:', update);
  }
});
```

### WebSocket - Trade Feed

```javascript
// Connect to trade execution feed
const ws = new WebSocket('ws://localhost:8080/trades');

ws.on('message', (data) => {
  const trade = JSON.parse(data);
  console.log(`Trade: ${trade.quantity} @ ${trade.price} (${trade.aggressor_side})`);
});
```

## 🏗️ Architecture

```
┌─────────────────┐
│   REST Client   │
└────────┬────────┘
         │ POST /api/v1/orders
         ↓
┌─────────────────────────────┐
│     Order Gateway (REST)     │
│   - Validation               │
│   - Order acceptance         │
└────────┬────────────────────┘
         ↓
┌─────────────────────────────┐
│   Matching Engine (Core)     │
│   - Price-time priority      │
│   - Trade execution          │
│   - BBO calculation          │
└────┬─────────────────┬──────┘
     ↓                 ↓
┌──────────┐    ┌─────────────┐
│ Order    │    │   Trade     │
│ Book     │    │   Generator │
└────┬─────┘    └──────┬──────┘
     ↓                 ↓
┌─────────────────────────────┐
│    Market Data Server       │
│    (WebSocket)              │
│  - BBO updates              │
│  - L2 orderbook updates     │
└─────────────────────────────┘
     ↓
┌─────────────────────────────┐
│    Trade Data Server        │
│    (WebSocket)              │
│  - Trade execution feed     │
└─────────────────────────────┘
```

See [docs/architecture.md](./docs/architecture.md) for detailed architecture documentation.

## 📂 Project Structure

```
Cryptocurrency_Matching_Engine/
├── src/
│   ├── engine/
│   │   ├── matching_engine.py    # Core matching logic
│   │   ├── order_book.py         # Order book data structure
│   │   └── order.py              # Order models
│   ├── api/
│   │   ├── rest_api.py           # REST API endpoints
│   │   ├── websocket_market.py   # Market data WebSocket
│   │   └── websocket_trades.py   # Trade execution WebSocket
│   ├── utils/
│   │   ├── logger.py             # Logging utilities
│   │   └── metrics.py            # Performance metrics
│   └── persistence/              # (Bonus) Persistence layer
├── tests/
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── performance/              # Performance benchmarks
├── docs/
│   ├── architecture.md           # System architecture
│   ├── api_spec.yaml             # OpenAPI specification
│   ├── algorithm.md              # Matching algorithm details
│   └── performance.md            # Performance analysis
├── .github/
│   ├── copilot-instructions.md   # AI coding agent guidelines
│   └── instructions/             # Development workflow instructions
├── .taskmaster/                  # TaskMaster AI configuration
├── TASKS.md                      # Assignment checklist
├── README.md                     # This file
└── requirements.txt              # Python dependencies
```

## 📚 Documentation

- **[TASKS.md](./TASKS.md)** - Complete assignment checklist with all requirements
- **[.github/copilot-instructions.md](./.github/copilot-instructions.md)** - Guidelines for AI coding assistants
- **[docs/architecture.md](./docs/architecture.md)** - System architecture and design decisions
- **[docs/algorithm.md](./docs/algorithm.md)** - Detailed matching algorithm explanation
- **[docs/api_spec.yaml](./docs/api_spec.yaml)** - OpenAPI specification
- **[docs/performance.md](./docs/performance.md)** - Performance analysis and benchmarks

## 🧪 Testing Strategy

### Unit Tests
- Matching engine logic (all order types)
- Order book operations (insert, delete, match)
- Price-time priority validation
- Trade-through prevention
- Edge cases (FOK, IOC scenarios)

### Integration Tests
- REST API endpoints
- WebSocket connections
- End-to-end order flow
- Error handling

### Performance Tests
- Order processing throughput
- Latency measurements (p50, p95, p99)
- Memory usage profiling
- Concurrency stress tests

Target: **>90% code coverage**

## 📊 Performance Benchmarks

```bash
# Run performance benchmarks
python tests/performance/benchmark_matching.py

# Profile critical paths
python -m cProfile -o profile.stats src/main.py
snakeviz profile.stats
```

Expected results:
- Order processing: <1ms (p99)
- BBO updates: <100μs (p99)
- Trade generation: <500μs (p99)
- Throughput: >1000 orders/second

## 🎁 Bonus Features

- [ ] Advanced order types (Stop-Loss, Stop-Limit, Take-Profit)
- [ ] Persistence layer with recovery
- [ ] Detailed performance optimization
- [ ] Maker-taker fee model

See [TASKS.md](./TASKS.md) for complete bonus feature checklist.

## 📧 Submission

**Email to**: careers@goquant.io  
**CC**: himanshu.vairagade@goquant.io  
**Subject**: "Backend Assignment - REG NMS Matching Engine"

**Include**:
- Resume
- Link to private GitHub repository
- Video demonstration (private/unlisted)
- Documentation

## ⚠️ Confidentiality

**CRITICAL REMINDER**:
- ❌ Do NOT make repository public
- ❌ Do NOT upload video publicly
- ✅ Keep everything private
- ✅ Share only with GoQuant team

## 🛠️ Development Tools

### TaskMaster AI
Project uses TaskMaster for AI-powered task management:

```bash
# List tasks
task-master list

# Get next task
task-master next

# Update progress
task-master update-task --id 1 --prompt "Completed feature X"
```

### VS Code Integration
- Copilot configured with project-specific instructions
- MCP server for TaskMaster integration
- See `.github/copilot-instructions.md` for AI assistant guidelines

## 📝 License

This is a confidential interview assignment. All rights reserved.

## 🤝 Contact

For questions about this assignment, contact the GoQuant team at careers@goquant.io.

---

**Last Updated**: October 15, 2025  
**Status**: 🚧 In Development
