#!/usr/bin/env python3
import asyncio
import socketio

async def trigger_new_problem():
    sio = socketio.AsyncClient()
    
    try:
        # Connect to the server
        await sio.connect('http://localhost:8000')
        print("Connected to server")
        
        # Join quiz first
        await sio.emit('join_quiz', {'username': 'Admin'})
        await asyncio.sleep(1)
        
        # Force new problem
        await sio.emit('force_new_problem', {'difficulty': 'medium'})
        print("Triggered new problem")
        
        await asyncio.sleep(2)
        await sio.disconnect()
        print("Disconnected")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_new_problem())
