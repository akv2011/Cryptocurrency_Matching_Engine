# Copilot Instructions: High-Performance Cryptocurrency Matching Engine

## Project Overview

This is a **GoQuant interview assignment** to build a production-grade cryptocurrency matching engine implementing REG NMS-inspired principles with strict price-time priority and internal order protection.

** Check Tasks.md file every new call to check which task pending after finishing a task update it then start next automacatically

** Test before updating the Task.md test the fatures 

**⚠️ CONFIDENTIALITY**: This is a private assignment. Code and documentation must remain confidential and not be shared publicly.

## Key Requirements

### Performance Targets
- **Throughput**: >1000 orders/second
- **Latency**: Order processing <1ms (p99), BBO updates <100μs (p99), Trade generation <500μs (p99)
- **Language**: Python (chosen for rapid development and maintainability)

### Core Components
1. **Matching Engine**: Price-time priority FIFO matching with trade-through prevention
2. **Order Book**: Efficient data structure with O(1) order lookup, fast price-level operations
3. **REST API**: Order submission endpoint (`POST /api/v1/orders`)
4. **WebSocket APIs**: Real-time market data (L2 orderbook, BBO) and trade execution streams
5. **Order Types**: Market, Limit, IOC (Immediate-Or-Cancel), FOK (Fill-Or-Kill)

## Critical Implementation Details

### REG NMS-Inspired Principles
- **Price Priority**: Higher bids and lower offers ALWAYS execute first
- **Time Priority**: FIFO at each price level (strict timestamp ordering)
- **Trade-Through Prevention**: Incoming marketable orders MUST match at best available prices first
- **Partial Fills**: Orders must fill at better prices before moving to next level

### Order Matching Logic
```python
# Marketable buy order matching sequence:
# 1. Check best ask price
# 2. Match against all orders at best price (FIFO)
# 3. If quantity remains, move to next ask price level
# 4. Repeat until order filled or no more liquidity
# 5. For limit orders: rest remaining quantity on book
```

### Data Structures (Critical)
- **Order Book**: Use `SortedDict` or similar for price levels with FIFO queues per level
- **Order Storage**: Dict for O(1) lookup by order_id
- **Price Levels**: Must support fast insertion/deletion and iteration in price order
- **Timestamps**: Use high-precision timestamps (microseconds) for time priority

## Project Structure

```
src/
├── engine/
│   ├── matching_engine.py    # Core matching logic - MOST CRITICAL FILE
│   ├── order_book.py         # Order book data structure
│   └── order.py              # Order models (Market, Limit, IOC, FOK)
├── api/
│   ├── rest_api.py           # FastAPI/Flask REST endpoints
│   ├── websocket_market.py   # WebSocket for L2 orderbook & BBO
│   └── websocket_trades.py   # WebSocket for trade executions
├── utils/
│   ├── logger.py             # Structured JSON logging
│   └── metrics.py            # Performance metrics collection
tests/
├── unit/                     # >90% coverage required
├── integration/              # API endpoint tests
└── performance/              # Latency benchmarks
```

## Development Workflow

### When Adding New Features
1. **Check TASKS.md** - Track progress against assignment requirements
2. **Update checklist** in TASKS.md as you complete items
3. **Document design decisions** - Why this approach vs alternatives
4. **Add tests immediately** - Don't defer testing

### Testing Strategy
```bash
# Unit tests (matching logic, order book operations)
pytest tests/unit/ -v --cov=src --cov-report=html

# Integration tests (API endpoints)
pytest tests/integration/ -v

# Performance benchmarks
python tests/performance/benchmark_matching.py
```

### Performance Profiling
```python
# Use cProfile for bottleneck identification
python -m cProfile -o profile.stats src/main.py

# Analyze with snakeviz
snakeviz profile.stats
```

## Code Conventions

### Order State Machine
```
pending → accepted → [partially_filled] → filled
                  ↘ rejected
                  ↘ canceled
```

### WebSocket Message Format (MUST FOLLOW)
```json
// Market Data
{"type": "orderbook|bbo", "timestamp": "ISO8601", "symbol": "BTC-USDT", ...}

// Trade Execution  
{"type": "trade", "trade_id": "...", "price": "...", "aggressor_side": "buy|sell", ...}
```

### Error Handling
- **Invalid orders**: Return 400 with descriptive error message
- **Insufficient liquidity**: Partial fill for Market/IOC, reject FOK
- **System errors**: Log with context, return 500

### Logging Format
```python
# Structured JSON logging required for audit trail
logger.info("order_submitted", extra={
    "order_id": "...",
    "symbol": "BTC-USDT",
    "side": "buy",
    "quantity": "0.5",
    "timestamp": "..."
})
```

## Common Pitfalls to Avoid

1. **Trade-Through Violations**: NEVER match at worse price when better price available
2. **Time Priority Bugs**: Must use strict FIFO - insertion order matters
3. **Partial Fill Logic**: Must try best prices first, even for partial fills
4. **FOK vs IOC**: FOK checks full liquidity BEFORE execution, IOC fills what's available
5. **Price Precision**: Use Decimal for financial calculations, NEVER float
6. **Concurrency**: Be careful with shared state if using threads/async

## Libraries & Dependencies

### Recommended Stack
```python
# Web Framework
fastapi>=0.104.0  # REST API with async support
uvicorn>=0.24.0   # ASGI server

# WebSocket
websockets>=12.0  # Real-time data streaming

# Data Structures
sortedcontainers>=2.4.0  # SortedDict for order book

# Testing
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-asyncio>=0.21.0

# Performance
py-spy  # Profiling without overhead
```

#

## Quick Start

```bash
# Setup environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start engine
python src/main.py

# Test REST API
curl -X POST http://localhost:8080/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC-USDT","order_type":"limit","side":"buy","quantity":"0.5","price":"50000"}'

# Connect to WebSocket
# Market Data: ws://localhost:8080/market-data
# Trades: ws://localhost:8080/trades
```

## References

- **TASKS.md** - Complete assignment checklist with all requirements
- **Instructions** - `.github/instructions/` - Development workflow guidelines

## Need Help?

1. Check TASKS.md for requirement details
2. Profile code early to identify performance bottlenecks

---

**Remember**: This is a time-sensitive assignment. Focus on core requirements first, bonus features if time permits. Code quality and correctness are more important than feature completeness.
