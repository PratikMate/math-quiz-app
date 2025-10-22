# Competitive Math Quiz

A real-time competitive math quiz application where multiple users compete to solve math problems simultaneously.

## Features

- Real-time multiplayer math competition
- AI-powered math problem generation with **intelligent prefetching**
- Fair concurrency handling for simultaneous submissions
- Live leaderboard and scoring system
- Network resilience and automatic reconnection
- **Batch question prefetching** for faster response times

## Tech Stack

**Frontend:**
- React 18 with TypeScript
- Tailwind CSS for styling
- Socket.IO client for real-time communication
- Vite for development and building

**Backend:**
- FastAPI with Python 3.11
- Socket.IO for WebSocket management
- Redis for real-time state management and **question prefetching**
- **PostgreSQL for persistent storage**
- Google Gemini API for AI problem generation with **batch optimization**

## Development Setup

### Prerequisites

- Node.js 18+ 
- Python 3.11+
- **Redis (REQUIRED)** - The application will not start without Redis
- **PostgreSQL (REQUIRED)** - For persistent storage

### Installation

1. Clone the repository
2. Install all dependencies:
   ```bash
   npm run install:all
   ```

3. **Set up PostgreSQL database:**
   ```bash
   cd backend
   python setup_postgres.py
   ```

4. **Start Redis server (REQUIRED):**
   ```bash
   # macOS (with Homebrew)
   brew install redis
   redis-server --daemonize yes
   
   # Ubuntu/Debian
   sudo apt install redis-server
   sudo systemctl start redis
   
   # Verify Redis is running
   redis-cli ping  # Should return "PONG"
   ```

5. Set up environment variables:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your configuration (DATABASE_URL will be set by setup script)
   ```

### Running the Application

**Safe startup (recommended):**
```bash
# This will check Redis and start the backend safely
cd backend
python start_app.py
```

**Manual startup:**
```bash
# Start both frontend and backend in development mode
npm run dev

# Or run them separately:
npm run dev:frontend  # Frontend (http://localhost:3000)
npm run dev:backend   # Backend (http://localhost:8000)
```

**Important:** The backend will refuse to start if Redis is not running. This prevents runtime errors and ensures proper functionality.

## Project Structure

```
competitive-math-quiz/
├── frontend/          # React frontend application
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── backend/           # FastAPI backend application
│   ├── main.py
│   ├── requirements.txt
│   └── .env
├── package.json       # Root package.json for scripts
└── README.md
```

## API Endpoints

- `GET /health` - Health check endpoint
- WebSocket events handled via Socket.IO

## Contributing

1. Follow the existing code style
2. Add tests for new features
3. Update documentation as needed

## License

MIT License