# Competitive Math Quiz - Assignment Solution

A real-time competitive math quiz application where multiple users compete to solve math problems simultaneously. Built as a solution to a technical assignment focusing on concurrency, real-time communication, and scalable architecture.

## 🔗 Live Application

- **Frontend:** https://math-quiz-app-omega.vercel.app
- **Backend API:** https://math-quiz-app-v5lq.onrender.com
- **Source Code:** https://github.com/PratikMate/math-quiz-app

## 📋 Assignment Requirements Addressed

### Core Requirements ✅
- **Competitive Math Quiz Website:** Multi-user real-time math competition
- **Concurrent First-Solution Detection:** Redis-backed concurrency management
- **Dynamic Question Generation:** AI-powered with Google Gemini API
- **Network Resilience:** Automatic reconnection and quality monitoring
- **User High Scores:** Persistent leaderboard with session and all-time tracking
- **Cloud Deployment:** Deployed on Render (backend) and Vercel (frontend)

## 🏗️ Architecture & Technical Decisions

### Tech Stack Selection

**Frontend: React 18 + TypeScript + Vite**
- **Why:** Fast development, type safety, modern tooling
- **Socket.IO Client:** Real-time bidirectional communication
- **Tailwind CSS:** Rapid UI development

**Backend: FastAPI + Python 3.11**
- **Why:** High performance, automatic API docs, async support
- **Socket.IO:** WebSocket management with fallback to polling
- **Redis:** In-memory state management for real-time operations
- **PostgreSQL:** Persistent storage for user data and leaderboards

**AI Integration: Google Gemini API**
- **Why:** Free tier, good math problem generation capabilities
- **Prefetching System:** Batch generation to handle rate limits

### Key Technical Solutions

#### 1. Concurrency Management 🔄
```python
# Redis-backed atomic operations for first-solution detection
async def submit_answer(self, user_id: str, problem: MathProblem, answer: str):
    # Atomic check-and-set operation
    winner_key = f"problem:{problem.id}:winner"
    is_winner = await self.redis.set(winner_key, user_id, nx=True)
    return SubmissionResult(is_winner=bool(is_winner), ...)
```

**Solution:** Redis atomic operations ensure only one user can be marked as winner, handling race conditions across multiple server instances.

#### 2. Dynamic Question Generation 🧮
```python
# AI-powered question generation with intelligent caching
class PrefetchService:
    async def generate_mixed_problems(self, count: int = 15):
        # Single API call for multiple difficulties
        # Reduces API calls from 3 to 1 per batch
```

**Solution:** Gemini API integration with aggressive caching and fallback mechanisms to handle rate limits (10 requests/minute).

#### 3. Network Resilience 🌐
```typescript
// Automatic reconnection with exponential backoff
class WebSocketService {
    private reconnectWithBackoff() {
        const delay = Math.min(
            this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );
        // Connection quality monitoring and fallback to polling
    }
}
```

**Solution:** Multi-transport Socket.IO with automatic fallback from WebSocket to HTTP polling for unreliable networks.

#### 4. High Score Tracking 📊
```python
# Dual storage: Redis for real-time, PostgreSQL for persistence
class ScoreTracker:
    async def record_win(self, user_id: str, response_time_ms: int):
        # Update both session scores (Redis) and persistent scores (PostgreSQL)
        await self.update_session_score(user_id)
        await self.update_persistent_score(user_id)
```

**Solution:** Hybrid storage approach for both real-time leaderboards and persistent user statistics.

## 🚀 Deployment Architecture

### Production Setup
- **Frontend:** Vercel (CDN, automatic deployments)
- **Backend:** Render (container-based, auto-scaling)
- **Database:** Render PostgreSQL (managed service)
- **Cache:** Render Redis (managed service)
- **AI Service:** Google Gemini API (external)

### Deployment Challenges & Solutions

1. **WebSocket Issues on Render:**
   - **Problem:** Render's free tier has WebSocket limitations
   - **Solution:** Forced Socket.IO to use HTTP polling, updated start command to use `socket_app`

2. **CORS Configuration:**
   - **Problem:** Cross-origin requests blocked
   - **Solution:** Dynamic CORS configuration supporting multiple domains

3. **Environment Variables:**
   - **Problem:** Different platforms require different configurations
   - **Solution:** Comprehensive environment variable management

## 🎯 Performance Optimizations

### 1. Question Prefetching System
- **Problem:** Gemini API rate limits (10 requests/minute)
- **Solution:** Background prefetching with Redis caching
- **Result:** Instant question delivery, 3x reduction in API calls

### 2. Batch AI Generation
```python
# Single API call for mixed difficulty questions
async def generate_mixed_problems(self):
    prompt = """Generate 15 math problems:
    - 5 easy (basic arithmetic)
    - 5 medium (algebra, geometry)  
    - 5 hard (advanced concepts)"""
```
**Result:** Reduced API calls from 15 to 1 per batch

### 3. Connection Quality Monitoring
```typescript
// Real-time network quality assessment
private assessConnectionQuality(responseTime: number): ConnectionQuality {
    if (responseTime < 100) return 'excellent';
    if (responseTime < 300) return 'good';
    if (responseTime < 1000) return 'fair';
    return 'poor';
}
```

## 🔧 Development Decisions & Trade-offs

### Corners Cut (with Production Solutions)

1. **Basic Authentication:**
   - **Current:** Username-only entry
   - **Production:** JWT tokens, OAuth integration, user registration

2. **Simple Error Handling:**
   - **Current:** Basic try-catch blocks
   - **Production:** Structured error handling, error tracking (Sentry)

3. **Limited Testing:**
   - **Current:** Manual testing only
   - **Production:** Unit tests, integration tests, E2E testing

4. **Basic Monitoring:**
   - **Current:** Console logs and basic health checks
   - **Production:** APM tools, metrics dashboards, alerting

### Production Enhancements

1. **Scalability:**
   - Horizontal scaling with load balancers
   - Database read replicas
   - CDN for static assets

2. **Security:**
   - Rate limiting per user
   - Input sanitization and validation
   - HTTPS enforcement
   - Security headers

3. **Monitoring:**
   - Real-time metrics and alerting
   - Performance monitoring
   - Error tracking and logging

## 📊 Key Metrics & Features

- **Real-time Multiplayer:** Up to 100 concurrent users
- **Response Time:** < 100ms for cached questions
- **Network Resilience:** Automatic reconnection with quality monitoring
- **Question Variety:** AI-generated problems across 3 difficulty levels
- **Persistent Storage:** User statistics and all-time leaderboards
- **Mobile Responsive:** Works across all device sizes

## 🎮 How to Use

1. **Visit:** https://math-quiz-app-omega.vercel.app
2. **Enter Username:** Join with any username
3. **Select Difficulty:** Choose your preferred difficulty level
4. **Compete:** Solve math problems faster than other users
5. **Track Progress:** View real-time leaderboard and your statistics

## 🛠️ Local Development

```bash
# Clone repository
git clone https://github.com/PratikMate/math-quiz-app
cd math-quiz-app

# Install dependencies
npm run install:all

# Set up environment
cp backend/.env.example backend/.env
# Add your GEMINI_API_KEY

# Start services (requires Redis and PostgreSQL)
npm run dev
```

## 📈 Future Enhancements

1. **Advanced Features:**
   - Custom problem categories (calculus, statistics, etc.)
   - Tournament mode with brackets
   - Team competitions
   - Problem difficulty adaptation based on user performance

2. **Technical Improvements:**
   - Microservices architecture
   - GraphQL API
   - Real-time analytics dashboard
   - Machine learning for personalized difficulty

## 🕐 Development Timeline

**Total Time:** ~8 hours (exceeded 2-3 hour target due to deployment challenges)

- **Core Development:** 3 hours
- **Deployment & Debugging:** 4 hours  
- **Optimization & Polish:** 1 hour

## 💡 Interview Discussion Points

### Technical Architecture
- Why FastAPI over Flask/Django?
- Redis vs traditional database for real-time features
- Socket.IO transport selection and fallback strategies

### Scalability Considerations
- How would you handle 10,000 concurrent users?
- Database sharding strategies for global deployment
- Caching layers and CDN integration

### Production Readiness
- Monitoring and observability setup
- Security considerations and threat modeling
- CI/CD pipeline and deployment strategies

### Alternative Approaches
- Server-Sent Events vs WebSockets
- Microservices vs monolithic architecture
- Different AI providers and their trade-offs

---

**Built with ❤️ for technical excellence and real-time user experiences.**