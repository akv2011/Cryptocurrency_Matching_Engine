# GoQuant Assignment: High-Performance Cryptocurrency Matching Engine

## 📋 Assignment Overview

**Objective**: Develop a high-performance cryptocurrency matching engine implementing REG NMS-inspired principles of price-time priority and internal order protection.

**Submission Deadline**: 7 days from October 14, 2025  
**Language**: Python (chosen for rapid development and maintainability)  
**Performance Target**: >1000 orders/second

---

## ✅ Core Requirements

### 1. Matching Engine Logic (REG NMS-Inspired)

#### 1.1 BBO Calculation and Dissemination
- [x] Implement real-time Best Bid and Offer (BBO) calculation for each trading pair
- [x] Ensure BBO updates instantaneously on order add/modify/cancel/match events
- [x] Achieve sub-millisecond BBO update latency

#### 1.2 Internal Order Protection & Price-Time Priority
- [x] Implement strict FIFO (First-In-First-Out) at each price level
- [x] Ensure price priority: higher bids and lower offers always prioritized
- [x] Prevent internal trade-throughs
- [x] Ensure marketable orders match at best available prices
- [x] Implement partial fills at better prices before moving to next level

#### 1.3 Order Type Support
- [x] **Market Order**: Immediate execution at best available price(s)
  - Walk the book until fully filled
  - Handle insufficient liquidity gracefully
- [x] **Limit Order**: Execute at specified price or better
  - Rest on book if not immediately marketable
  - Maintain in price-time priority queue
- [x] **Immediate-Or-Cancel (IOC)**: Execute all or part immediately
  - Cancel unfilled portion
  - No trade-through violations
- [x] **Fill-Or-Kill (FOK)**: Execute entire order immediately or cancel completely
  - All-or-nothing execution
  - Must check full liquidity before execution

---

### 2. Data Structures

#### 2.1 Order Book
- [x] Design efficient price-level aggregation
- [x] Implement fast insertion, deletion, and matching operations
- [x] Optimize memory-efficient design for deep books
- [x] Support multiple trading pairs

#### 2.2 Order Management
- [x] Implement order storage with O(1) lookup by ID
- [x] Track order state (open, partially filled, filled, canceled)
- [x] Store order metadata (timestamps, user info, etc.)

---

### 3. APIs

#### 3.1 Order Submission API (REST)
- [x] Implement REST endpoint: `POST /api/v1/orders`
- [x] Accept request payload:
  ```json
  {
    "symbol": "BTC-USDT",
    "order_type": "limit|market|ioc|fok",
    "side": "buy|sell",
    "quantity": "0.5",
    "price": "50000.00"  // required for limit orders
  }
  ```
- [x] Return response:
  ```json
  {
    "order_id": "unique_order_id",
    "status": "accepted|rejected|filled|partially_filled",
    "filled_quantity": "0.5",
    "remaining_quantity": "0.0",
    "average_price": "50000.00",
    "timestamp": "2025-10-15T12:34:56.789Z"
  }
  ```

#### 3.2 Market Data API (WebSocket)
- [x] Implement WebSocket connection: `ws://localhost:8081/market-data`
- [x] Stream L2 Order Book Updates:
  ```json
  {
    "type": "orderbook",
    "timestamp": "2025-10-15T12:34:56.789Z",
    "symbol": "BTC-USDT",
    "asks": [["50100.00", "1.5"], ["50150.00", "2.0"]],
    "bids": [["50000.00", "1.0"], ["49950.00", "3.5"]]
  }
  ```
- [x] Stream BBO Updates ✅ **VERIFIED: Implemented in websocket_market.py**
  ```json
  {
    "type": "bbo",
    "timestamp": "2025-10-15T12:34:56.789Z",
    "symbol": "BTC-USDT",
    "best_bid": "50000.00",
    "best_bid_qty": "1.0",
    "best_ask": "50100.00",
    "best_ask_qty": "1.5"
  }
  ```

#### 3.3 Trade Execution API (WebSocket)
- [x] Implement WebSocket connection: `ws://localhost:8082/trades`
- [x] Stream Trade Execution Reports (implemented in websocket_trades.py):
  ```json
  {
    "type": "trade",
    "timestamp": "2025-10-15T12:34:56.789Z",
    "symbol": "BTC-USDT",
    "trade_id": "trade_12345",
    "price": "50000.00",
    "quantity": "0.5",
    "aggressor_side": "buy",
    "maker_order_id": "order_67890",
    "taker_order_id": "order_12346"
  }
  ```

---

### 4. Technical Requirements

- [x] Achieve >1000 orders/second processing capability ✅ **VERIFIED: 6,641 orders/sec (6.6x target)**
  - **Performance Benchmark Results:**
  - Throughput: 6,641.70 orders/second
  - p99 Latency: 0.406 ms (target: <1ms) ✓
  - BBO Query Speed: 6.7 μs p99 (target: <100μs) ✓
  - Market Order Processing: 4,203.94 orders/second
- [x] Implement robust error handling ✅ **VERIFIED: 88/88 tests passing**
  - Invalid order parameters rejection
  - Insufficient liquidity handling
  - Graceful degradation under load
- [x] Implement comprehensive logging ✅ **VERIFIED: Implemented in utils/logger.py**
  - Structured logging (JSON format)
  - Order lifecycle tracking
  - Performance metrics collection
  - Audit trail for all operations
- [x] Write clean, maintainable, well-documented code ✅ **VERIFIED: Type hints, docstrings, clear structure**
- [x] Create unit tests for core matching logic ✅ **VERIFIED: 88 tests, 100% passing, 86-92% coverage**
  - test_order.py: 34 tests (92% coverage)
  - test_order_book.py: 27 tests (88% coverage)
  - test_matching_engine.py: 27 tests (86% coverage)
- [x] Create integration tests for API endpoints ✅ **VERIFIED: 4/4 tests passing**
  - Health check endpoint
  - Limit order submission
  - Market order execution
  - Orderbook retrieval

---

## 🎁 Bonus Features (Recommended)

### 1. Advanced Order Types
- [ ] **Stop-Loss**: Trigger market order when price reaches stop level
- [ ] **Stop-Limit**: Trigger limit order when price reaches stop level
- [ ] **Take-Profit**: Automatically close position at profit target

### 2. Persistence Layer
- [ ] Implement order book state snapshots
- [ ] Create transaction log for replay capability
- [ ] Enable recovery from restart
- [ ] Use SQLite or Redis for storage

### 3. Concurrency & Performance Optimization
- [x] Conduct detailed latency profiling ✅ **VERIFIED: Performance benchmarks completed**
  - Order processing latency: 0.406ms p99 (target: <1ms p99) ✓
  - BBO update latency: 6.7μs p99 (target: <100μs p99) ✓
  - Trade generation latency: Included in order processing
- [ ] Explore lock-free data structures
- [ ] Implement memory pool allocation
- [ ] Apply zero-copy techniques where possible
- [ ] Optimize for CPU cache efficiency
- [x] Create performance benchmarks and analysis report ✅ **VERIFIED: tests/performance/benchmark_matching.py**

### 4. Basic Fee Model
- [ ] Implement maker-taker fee structure
  - Maker fee: -0.01% (rebate)
  - Taker fee: +0.05%
- [ ] Include fee calculations in trade reports
- [ ] Track fees per user

---

## 📚 Documentation Requirements

### System Architecture
- [x] Document overall system design and components ✅ **VERIFIED: docs/architecture.md created**
- [x] Explain design choices and trade-offs ✅ **VERIFIED: Detailed trade-off analysis included**
- [x] Provide architecture diagrams ✅ **VERIFIED: ASCII diagrams for components and data flow**
- [x] Document data flow through the system ✅ **VERIFIED: Order submission, WebSocket, and trade flows documented**

### Data Structures
- [x] Explain order book implementation ✅ **VERIFIED: docs/data_structures.md created**
- [x] Document data structure choices and rationale ✅ **VERIFIED: SortedDict, Deque, Dict trade-offs explained**
- [x] Provide complexity analysis (time/space) ✅ **VERIFIED: Full complexity tables for all operations**

### Matching Algorithm
- [x] Detail price-time priority implementation ✅ **VERIFIED: docs/matching_algorithm.md created**
- [x] Explain order matching process ✅ **VERIFIED: Step-by-step execution with code examples**
- [x] Document REG NMS-inspired principles ✅ **VERIFIED: Trade-through prevention, FIFO, price priority**

### API Specifications
- [x] Create OpenAPI/Swagger documentation ✅ **VERIFIED: docs/api_spec.yaml created**
- [x] Document all endpoints and message formats ✅ **VERIFIED: Full REST API spec with schemas**
- [x] Provide usage examples ✅ **VERIFIED: Request/response examples for all endpoints**

### Performance Analysis
- [x] Document benchmarking methodology ✅ **VERIFIED: docs/performance.md created**
- [x] Present performance results ✅ **VERIFIED: Detailed results with comparisons**
- [x] Identify optimization opportunities ✅ **VERIFIED: Bottleneck analysis included**
- [x] Compare against targets ✅ **VERIFIED: All targets exceeded 2.5-6.6x**

---

## 🎬 Deliverables

### Code
- [x] Complete source code with inline documentation ✅ **VERIFIED: All core components implemented**
- [x] Unit test suite ✅ **VERIFIED: 88 tests, 100% passing, 86-92% coverage**
- [x] Integration test suite ✅ **VERIFIED: 4 REST API tests passing**
- [x] Performance benchmarks ✅ **VERIFIED: All targets exceeded (6.6x throughput, 2.5x latency)**
- [x] README with setup instructions ✅ **VERIFIED: Comprehensive README.md exists**

### Video Demonstration
- [ ] Record system functionality demo (order submission, market data)
- [ ] Walk through core matching logic and data structures
- [ ] Explain design choices and REG NMS implementation
- [ ] Demonstrate performance benchmarks
- [ ] Keep video private (not public on YouTube)

### Documentation
- [x] System architecture document ✅ **VERIFIED: docs/architecture.md created**
- [x] Data structure explanations ✅ **VERIFIED: docs/data_structures.md created**
- [ ] API specifications (OpenAPI/Swagger)
- [x] Matching algorithm detailed explanation ✅ **VERIFIED: docs/matching_algorithm.md created**
- [x] Design trade-offs and rationale ✅ **VERIFIED: Included in architecture.md**
- [x] Performance analysis report (if bonus completed) ✅ **VERIFIED: docs/performance.md created**

---

## 📧 Submission Instructions

**MANDATORY FOR ACCEPTANCE**

- [ ] Email to: `careers@goquant.io`
- [ ] CC: `himanshu.vairagade@goquant.io`
- [ ] Subject: "Backend Assignment - REG NMS Matching Engine"
- [ ] Attachments:
  - [ ] Resume
  - [ ] Link to private GitHub repository
  - [ ] Video demonstration link (private)
  - [ ] Documentation

---

## ⚠️ Confidentiality Notice

**CRITICAL**: This assignment and all work produced are strictly confidential.

- ❌ Do NOT post code publicly on GitHub
- ❌ Do NOT upload video publicly on YouTube  
- ✅ Keep repository private
- ✅ Share only with GoQuant team
- ✅ Ensure video is private/unlisted

---

## 🏗️ Project Structure (Recommended)

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
│   └── persistence/              # Bonus: persistence layer
├── tests/
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── performance/              # Performance benchmarks
├── docs/
│   ├── architecture.md           # System architecture
│   ├── api_spec.yaml             # OpenAPI specification
│   └── performance.md            # Performance analysis
├── README.md                     # Setup and usage instructions
└── requirements.txt              # Python dependencies
```

---

## 📝 Notes

- Focus on core features first, then bonus features if time permits
- Profile early and often to meet performance targets
- Document as you code, not at the end
- Test incrementally to catch issues early
- Keep code clean and maintainable

**Status**: 🚧 In Progress
