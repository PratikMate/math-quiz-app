import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=os.getenv('CORS_ORIGINS', '*').split(',')
)

# Create FastAPI app
app = FastAPI(title="Competitive Math Quiz API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', '*').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    print(f"Client {sid} connected")
    await sio.emit('connected', {'message': 'Connected to quiz server'}, room=sid)

@sio.event
async def disconnect(sid):
    print(f"Client {sid} disconnected")

@sio.event
async def join_quiz(sid, data):
    print(f"Client {sid} joined quiz")
    await sio.emit('quiz_joined', {'message': 'Successfully joined the quiz'}, room=sid)

# Basic health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Quiz server is running"}

# Mount Socket.IO app
socket_app = socketio.ASGIApp(sio, app)

if __name__ == "__main__":
    uvicorn.run(
        socket_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )