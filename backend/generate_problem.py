#!/usr/bin/env python3
"""
Simple script to generate an initial problem for the quiz
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.quiz_engine import QuizEngine
from app.services.redis_service import RedisService
from app.models.math_problem import DifficultyLevel

async def generate_initial_problem():
    """Generate and store an initial problem"""
    try:
        # Initialize services
        quiz_engine = QuizEngine()
        redis_service = RedisService()
        
        # Connect to Redis
        await redis_service.connect()
        
        # Generate a problem
        problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.MEDIUM)
        
        # Store in Redis
        problem_data = {
            'id': str(problem.id),
            'question': problem.question,
            'correct_answer': problem.correct_answer,
            'difficulty': problem.difficulty.value,
            'created_at': problem.created_at.isoformat()
        }
        await redis_service.set_current_problem(problem_data)
        
        print(f"✅ Generated initial problem: {problem.question}")
        print(f"Answer: {problem.correct_answer}")
        
        # Close connections
        await redis_service.close()
        
    except Exception as e:
        print(f"❌ Failed to generate problem: {e}")

if __name__ == "__main__":
    asyncio.run(generate_initial_problem())
