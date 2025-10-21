# Competitive Math Quiz

A real-time competitive math quiz application where multiple users compete to solve math problems simultaneously.

## Features

- Real-time multiplayer math competition
- AI-powered math problem generation
- Fair concurrency handling for simultaneous submissions
- Live leaderboard and scoring system
- Network resilience and automatic reconnection

## Tech Stack

**Frontend:**
- React 18 with TypeScript
- Tailwind CSS for styling
- Socket.IO client for real-time communication
- Vite for development and building

**Backend:**
- FastAPI with Python 3.11
- Socket.IO for WebSocket management
- Redis for real-time state management
- PostgreSQL for persistent storage
- Google Gemini API for AI problem generation

## Development Setup

### Prerequisites

- Node.js 18+ 
- Python 3.11+
- Redis (for development)
- PostgreSQL (for development)

### Installation

1. Clone the repository
2. Install all dependencies:
   ```bash
   npm run install:all
   ```

3. Set up environment variables:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your configuration
   ```

### Running the Application

Start both frontend and backend in development mode:
```bash
npm run dev
```

Or run them separately:
```bash
# Frontend (runs on http://localhost:3000)
npm run dev:frontend

# Backend (runs on http://localhost:8000)
npm run dev:backend
```

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