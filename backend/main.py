import os
import logging
import asyncio
import random
import hashlib
from datetime import datetime
from typing import Dict, Set, Optional, Any
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import socketio
import uvicorn

from config import settings, setup_logging, log_startup_info, get_cors_origins, get_websocket_config, is_production
from app.services.quiz_engine import QuizEngine
from app.services.submission_processor import SubmissionProcessor
from app.services.redis_service import RedisService
from app.services.prefetch_service import PrefetchService
from app.services.concurrency_manager import ConcurrencyManager
from app.services.score_tracker import ScoreTracker
from app.services.database_service import DatabaseService
from app.services.performance_monitor import performance_monitor
from app.services.structured_logger import get_structured_logger, RequestTracer
from app.services.cache_service import CacheService
from app.models.math_problem import MathProblem, AnswerSubmission, DifficultyLevel

# Setup logging first
setup_logging()
logger = logging.getLogger(__name__)

# Log startup information
log_startup_info()

# Create Socket.IO server with production configuration
websocket_config = get_websocket_config()
sio = socketio.AsyncServer(**websocket_config)

# Create FastAPI app with production settings
app = FastAPI(
    title="Competitive Math Quiz API",
    version="1.0.0",
    debug=settings.DEBUG,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add security middleware for production
if is_production():
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure with actual domains in production
    )

# Add CORS middleware with production settings
cors_origins = get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Import error handlers
from app.error_handlers import (
    QuizException, ValidationException, ServiceException,
    handle_quiz_exception, handle_validation_error, handle_http_exception, handle_general_exception
)
from app.security import check_rate_limit, SecurityHeaders
from pydantic import ValidationError

# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    if is_production():
        security_headers = SecurityHeaders.get_security_headers()
        for header, value in security_headers.items():
            response.headers[header] = value
    
    return response

# Add rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to requests."""
    if is_production():
        await check_rate_limit(request)
    
    response = await call_next(request)
    return response

# Add performance monitoring middleware
@app.middleware("http")
async def performance_monitoring_middleware(request: Request, call_next):
    """Track API performance metrics."""
    # Extract user ID from headers if available
    user_id = request.headers.get('X-User-ID')
    
    async with performance_monitor.track_request(
        endpoint=str(request.url.path),
        method=request.method,
        user_id=user_id
    ) as tracker:
        try:
            response = await call_next(request)
            tracker.set_status(response.status_code)
            return response
        except Exception as e:
            tracker.set_error(str(e))
            raise

# Exception handlers
@app.exception_handler(QuizException)
async def quiz_exception_handler(request: Request, exc: QuizException):
    return await handle_quiz_exception(request, exc)

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return await handle_validation_error(request, exc)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return await handle_http_exception(request, exc)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return await handle_general_exception(request, exc)

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize Redis and database connections on startup."""
    try:
        # Start performance monitoring
        await performance_monitor.start_monitoring()
        logger.info("Performance monitoring started")
        
        # Initialize Redis - REQUIRED for app to function
        try:
            await redis_service.connect()
            # Test Redis connection
            await redis_service.redis_client.ping()
            logger.info("Redis service connected successfully")
        except Exception as redis_error:
            logger.error(f"CRITICAL: Redis connection failed: {redis_error}")
            logger.error("Redis is required for the application to function properly")
            logger.error("Please start Redis server: redis-server --daemonize yes")
            raise SystemExit("Application cannot start without Redis")
        
        # Initialize Database
        await database_service.initialize()
        logger.info("Database service initialized successfully")
        
        # Start prefetch service
        await prefetch_service.start()
        logger.info("Question prefetch service started")
        
        # Load current problem from Redis if exists
        global current_problem_cache
        problem_data = await redis_service.get_current_problem()
        if problem_data:
            current_problem_cache = MathProblem(
                id=UUID(problem_data['id']),
                question=problem_data['question'],
                correct_answer=problem_data['correct_answer'],
                difficulty=DifficultyLevel(problem_data['difficulty']) if isinstance(problem_data['difficulty'], str) else problem_data['difficulty'],
                created_at=datetime.fromisoformat(problem_data['created_at'])
            )
            logger.info(f"Loaded current problem from Redis: {current_problem_cache.id}")
        
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise SystemExit(f"Application startup failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup Redis and database connections on shutdown."""
    try:
        # Stop prefetch service
        await prefetch_service.stop()
        logger.info("Prefetch service stopped")
        
        # Stop performance monitoring
        await performance_monitor.stop_monitoring()
        logger.info("Performance monitoring stopped")
        
        await redis_service.disconnect()
        logger.info("Redis service disconnected")
        
        await database_service.close()
        logger.info("Database service closed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}")

# Initialize services
quiz_engine = QuizEngine()
submission_processor = SubmissionProcessor()
redis_service = RedisService()
prefetch_service = PrefetchService(quiz_engine, redis_service, settings)

# Set prefetch service in quiz engine
quiz_engine.prefetch_service = prefetch_service
database_service = DatabaseService()
cache_service = CacheService(redis_service)
concurrency_manager = ConcurrencyManager(redis_service)
score_tracker = ScoreTracker(redis_service, database_service)

# Set up service dependencies
database_service.set_cache_service(cache_service)

# Quiz room constant
QUIZ_ROOM = "main_quiz"

# Global state for current problem (cached from Redis)
current_problem_cache: Optional[MathProblem] = None

# In-memory fallback for user sessions when Redis fails
user_sessions: Dict[str, Dict[str, Any]] = {}

# Question rotation function
async def rotate_to_next_question(delay_seconds: int = 2):
    """
    Rotate to the next question after a delay using Redis state management.
    
    Args:
        delay_seconds: Delay before generating new question
    """
    try:
        # Wait for the specified delay to show winner announcement
        await asyncio.sleep(delay_seconds)
        
        global current_problem_cache
        
        # Reset submission state for the current problem
        if current_problem_cache:
            await concurrency_manager.reset_problem_state(str(current_problem_cache.id))
        
        # Generate new problem with varied difficulty
        current_difficulty = current_problem_cache.difficulty if current_problem_cache else DifficultyLevel.MEDIUM
        
        # Rotate difficulty for variety (optional enhancement)
        difficulty_rotation = {
            DifficultyLevel.EASY: DifficultyLevel.MEDIUM,
            DifficultyLevel.MEDIUM: DifficultyLevel.HARD,
            DifficultyLevel.HARD: DifficultyLevel.EASY
        }
        
        # 70% chance to keep same difficulty, 30% chance to rotate
        if random.random() < 0.3:
            next_difficulty = difficulty_rotation.get(current_difficulty, DifficultyLevel.MEDIUM)
        else:
            next_difficulty = current_difficulty
        
        # Generate new problem
        new_problem = await quiz_engine.rotate_question(next_difficulty)
        current_problem_cache = new_problem
        
        # Store in Redis
        problem_data = {
            'id': str(new_problem.id),
            'question': new_problem.question,
            'correct_answer': new_problem.correct_answer,
            'difficulty': new_problem.difficulty.value,
            'created_at': new_problem.created_at.isoformat()
        }
        await redis_service.set_current_problem(problem_data)
        
        # Store in database for persistence
        try:
            await database_service.store_problem(
                problem_id=new_problem.id,
                question=new_problem.question,
                correct_answer=new_problem.correct_answer,
                difficulty=new_problem.difficulty.value
            )
            logger.info(f"Stored problem in database: {new_problem.id}")
        except Exception as db_error:
            logger.warning(f"Failed to store problem in database: {db_error}")
        
        logger.info(f"Rotated to new problem: {new_problem.id} - {new_problem.question}")
        
        # Broadcast new problem to all users
        await sio.emit('new_problem', {
            'problem': problem_data,
            'message': 'New problem available!'
        }, room=QUIZ_ROOM)
        
        # Send updated user stats/leaderboard
        await broadcast_leaderboard_update()
        
    except Exception as e:
        logger.error(f"Error in question rotation: {e}")
        # If rotation fails, try to generate a basic problem
        try:
            fallback_problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.MEDIUM)
            current_problem_cache = fallback_problem
            
            problem_data = {
                'id': str(fallback_problem.id),
                'question': fallback_problem.question,
                'correct_answer': fallback_problem.correct_answer,
                'difficulty': fallback_problem.difficulty.value,
                'created_at': fallback_problem.created_at.isoformat()
            }
            await redis_service.set_current_problem(problem_data)
            
            await sio.emit('new_problem', {
                'problem': problem_data,
                'message': 'New problem available!'
            }, room=QUIZ_ROOM)
            
        except Exception as fallback_error:
            logger.error(f"Fallback problem generation failed: {fallback_error}")
            await sio.emit('error', {
                'message': 'Failed to generate new problem. Please refresh the page.'
            }, room=QUIZ_ROOM)

async def broadcast_leaderboard_update():
    """
    Broadcast updated leaderboard to all users using score tracker.
    """
    try:
        # Get leaderboard from score tracker
        leaderboard = await score_tracker.get_leaderboard(limit=10)
        
        # Get session stats
        session_stats = await score_tracker.get_session_stats()
        
        # Broadcast to all users
        await sio.emit('leaderboard_update', {
            'leaderboard': leaderboard,
            'session_stats': session_stats,
            'timestamp': datetime.utcnow().isoformat()
        }, room=QUIZ_ROOM)
        
    except Exception as e:
        logger.error(f"Error broadcasting leaderboard update: {e}")

# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    performance_monitor.track_websocket_connection(sid, 'connect')
    logger.info(f"Client {sid} connected")
    await sio.emit('connected', {
        'message': 'Connected to quiz server',
        'timestamp': datetime.utcnow().isoformat()
    }, room=sid)

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    performance_monitor.track_websocket_connection(sid, 'disconnect')
    logger.info(f"Client {sid} disconnected")
    
    # Get user info before removing
    user_info = await redis_service.get_user_session(sid)
    
    # Remove from Redis
    await redis_service.remove_active_user(sid)
    
    if user_info:
        # Get updated active users count
        active_users_count = await redis_service.get_active_users_count()
        
        # Notify other users
        await sio.emit('user_left', {
            'user_id': sid,
            'username': user_info.get('username', 'Anonymous'),
            'active_users_count': active_users_count
        }, room=QUIZ_ROOM, skip_sid=sid)

@sio.event
async def join_quiz(sid, data):
    """
    Handle user joining the quiz using Redis for state management.
    
    Expected data format:
    {
        "username": "optional_username",
        "preferred_difficulty": "easy|medium|hard"
    }
    """
    try:
        username = data.get('username', f'User_{sid[:8]}') if data else f'User_{sid[:8]}'
        preferred_difficulty = data.get('preferred_difficulty', 'medium') if data else 'medium'
        
        # Add user to quiz room
        await sio.enter_room(sid, QUIZ_ROOM)
        
        # Store user session info in Redis
        user_data = {
            'username': username,
            'joined_at': datetime.utcnow().isoformat(),
            'score': 0,
            'wins': 0,
            'preferred_difficulty': preferred_difficulty
        }
        await redis_service.add_active_user(sid, user_data)
        
        # Initialize user score tracking
        await score_tracker.initialize_user_score(sid, username)
        
        logger.info(f"User {username} ({sid}) joined quiz")
        
        # Get active users count
        active_users_count = await redis_service.get_active_users_count()
        
        # Send confirmation to user
        await sio.emit('quiz_joined', {
            'message': 'Successfully joined the quiz',
            'user_id': sid,
            'username': username,
            'active_users_count': active_users_count
        }, room=sid)
        
        # Send current problem if one exists
        global current_problem_cache
        if current_problem_cache:
            await sio.emit('new_problem', {
                'problem': {
                    'id': str(current_problem_cache.id),
                    'question': current_problem_cache.question,
                    'difficulty': current_problem_cache.difficulty.value if hasattr(current_problem_cache.difficulty, 'value') else str(current_problem_cache.difficulty),
                    'created_at': current_problem_cache.created_at.isoformat()
                }
            }, room=sid)
        
        # Notify other users
        await sio.emit('user_joined', {
            'user_id': sid,
            'username': username,
            'active_users_count': active_users_count
        }, room=QUIZ_ROOM, skip_sid=sid)
        
    except Exception as e:
        logger.error(f"Error in join_quiz: {e}")
        await sio.emit('error', {
            'message': 'Failed to join quiz',
            'error': str(e)
        }, room=sid)

@sio.event
async def submit_answer(sid, data):
    """
    Handle answer submission using Redis-backed concurrency management.
    
    Expected data format:
    {
        "answer": "user_answer",
        "problem_id": "problem_uuid"
    }
    """
    performance_monitor.track_websocket_connection(
        sid, 
        'submit_answer', 
        {'data_size': len(str(data)) if data else 0}
    )
    
    try:
        # Check if user is in active session
        user_session = await redis_service.get_user_session(sid)
        if not user_session:
            await sio.emit('error', {
                'message': 'User not in quiz session'
            }, room=sid)
            return
        
        global current_problem_cache
        if not current_problem_cache:
            await sio.emit('error', {
                'message': 'No active problem to answer'
            }, room=sid)
            return
        
        # Validate problem ID
        submitted_problem_id = data.get('problem_id')
        if submitted_problem_id != str(current_problem_cache.id):
            await sio.emit('error', {
                'message': 'Problem ID mismatch'
            }, room=sid)
            return
        
        user_answer = data.get('answer')
        if user_answer is None:
            await sio.emit('error', {
                'message': 'Answer is required'
            }, room=sid)
            return
        
        # Process submission with Redis-backed concurrency management
        submission_result = await concurrency_manager.submit_answer(
            user_id=sid,
            problem=current_problem_cache,
            submitted_answer=user_answer
        )
        
        # Send confirmation to user
        await sio.emit('answer_received', {
            'message': submission_result.message,
            'is_correct': submission_result.is_correct,
            'is_winner': submission_result.is_winner,
            'submitted_answer': submission_result.validation_result.submitted_value,
            'server_timestamp': submission_result.server_timestamp.isoformat(),
            'feedback': submission_result.validation_result.message,
            'rank': submission_result.rank
        }, room=sid)
        
        # If user is the winner, announce and prepare for question rotation
        if submission_result.is_winner:
            # Calculate response time (simplified - in real implementation would use submission timestamp)
            response_time_ms = int((submission_result.server_timestamp - current_problem_cache.created_at).total_seconds() * 1000)
            
            # Update score tracking
            updated_score = await score_tracker.record_win(
                user_id=sid,
                username=user_session['username'],
                response_time_ms=response_time_ms,
                problem_id=str(current_problem_cache.id)
            )
            
            # Update user stats in Redis for backward compatibility
            await redis_service.update_user_session(sid, {
                'score': updated_score.session_wins,
                'wins': updated_score.session_wins
            })
            
            # Mark problem as solved (handled by concurrency manager)
            # Create a deterministic UUID from session ID
            sid_hash = hashlib.md5(sid.encode()).hexdigest()
            current_problem_cache.solved_by = UUID(sid_hash)
            current_problem_cache.solved_at = submission_result.server_timestamp
            
            # Mark problem as solved in database if user has persistent ID
            try:
                user_score = await score_tracker.get_user_score(sid)
                if user_score and user_score.persistent_user_id:
                    await database_service.mark_problem_solved(
                        problem_id=current_problem_cache.id,
                        user_id=UUID(user_score.persistent_user_id),
                        solved_time=submission_result.server_timestamp
                    )
                    logger.info(f"Marked problem {current_problem_cache.id} as solved by {user_score.persistent_user_id}")
            except Exception as db_error:
                logger.warning(f"Failed to mark problem as solved in database: {db_error}")
            
            # Announce winner to all users
            await sio.emit('winner_announced', {
                'winner': {
                    'user_id': sid,
                    'username': user_session['username'],
                    'answer': submission_result.validation_result.submitted_value,
                    'correct_answer': submission_result.validation_result.correct_value,
                    'response_time': submission_result.server_timestamp.isoformat()
                },
                'problem': {
                    'id': str(current_problem_cache.id),
                    'question': current_problem_cache.question
                }
            }, room=QUIZ_ROOM)
            
            logger.info(f"Winner: {user_session['username']} ({sid}) solved problem {current_problem_cache.id}")
            
            # Schedule question rotation after 2-second delay
            asyncio.create_task(rotate_to_next_question(delay_seconds=2))
        else:
            # Record attempt for non-winning submissions
            await score_tracker.record_attempt(sid, user_session['username'])
        
    except Exception as e:
        logger.error(f"Error in submit_answer: {e}")
        await sio.emit('error', {
            'message': 'Failed to process answer',
            'error': str(e)
        }, room=sid)

@sio.event
async def request_current_problem(sid, data=None):
    """
    Handle request for current active problem using Redis state.
    """
    try:
        # Check if user is in active session
        user_session = await redis_service.get_user_session(sid)
        if not user_session:
            await sio.emit('error', {
                'message': 'User not in quiz session'
            }, room=sid)
            return
        
        global current_problem_cache
        if current_problem_cache:
            await sio.emit('new_problem', {
                'problem': {
                    'id': str(current_problem_cache.id),
                    'question': current_problem_cache.question,
                    'difficulty': current_problem_cache.difficulty.value if hasattr(current_problem_cache.difficulty, 'value') else str(current_problem_cache.difficulty),
                    'created_at': current_problem_cache.created_at.isoformat()
                }
            }, room=sid)
        else:
            # Generate a new problem if none exists
            try:
                new_problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.MEDIUM)
            except Exception as e:
                logger.error(f"Problem generation failed: {e}")
                # Force fallback to built-in problems
                fallback_problem = quiz_engine._get_fallback_problem(DifficultyLevel.MEDIUM, avoid_recent=True)
                if fallback_problem:
                    new_problem = fallback_problem
                    logger.info(f"Using fallback problem due to API limits")
                else:
                    # Generate basic problem if no fallback available
                    new_problem = quiz_engine._generate_basic_problem(DifficultyLevel.MEDIUM)
                    logger.info(f"Using basic generated problem")
            
            current_problem_cache = new_problem
            
            # Store in Redis
            problem_data = {
                'id': str(new_problem.id),
                'question': new_problem.question,
                'correct_answer': new_problem.correct_answer,
                'difficulty': new_problem.difficulty.value if hasattr(new_problem.difficulty, 'value') else str(new_problem.difficulty),
                'created_at': new_problem.created_at.isoformat()
            }
            await redis_service.set_current_problem(problem_data)
            
            # Broadcast to all users
            await sio.emit('new_problem', {
                'problem': problem_data
            }, room=QUIZ_ROOM)
            
    except Exception as e:
        logger.error(f"Error in request_current_problem: {e}")
        await sio.emit('error', {
            'message': 'Failed to get current problem',
            'error': str(e)
        }, room=sid)

@sio.event
async def request_problem_with_difficulty(sid, data):
    """
    Handle request for new problem with specific difficulty.
    """
    try:
        # Check if user is in active session
        user_session = await redis_service.get_user_session(sid)
        if not user_session:
            await sio.emit('error', {
                'message': 'User not in quiz session'
            }, room=sid)
            return
        
        # Get difficulty from request or user preference
        difficulty = data.get('difficulty') if data else None
        if not difficulty:
            difficulty = user_session.get('preferred_difficulty', 'medium')
        
        try:
            difficulty_level = DifficultyLevel(difficulty.lower())
        except ValueError:
            difficulty_level = DifficultyLevel.MEDIUM
        
        global current_problem_cache
        
        # Reset current problem state
        if current_problem_cache:
            await concurrency_manager.reset_problem_state(str(current_problem_cache.id))
        
        # Generate new problem with requested difficulty
        try:
            new_problem = await quiz_engine.generate_problem_with_ai(difficulty_level)
        except Exception as e:
            logger.error(f"Problem generation failed: {e}")
            # Force fallback to built-in problems
            fallback_problem = quiz_engine._get_fallback_problem(difficulty_level, avoid_recent=True)
            if fallback_problem:
                new_problem = fallback_problem
                logger.info(f"Using fallback problem due to API limits")
            else:
                # Generate basic problem if no fallback available
                new_problem = quiz_engine._generate_basic_problem(difficulty_level)
                logger.info(f"Using basic generated problem")
        
        current_problem_cache = new_problem
        
        # Store in Redis
        problem_data = {
            'id': str(new_problem.id),
            'question': new_problem.question,
            'correct_answer': new_problem.correct_answer,
            'difficulty': new_problem.difficulty.value if hasattr(new_problem.difficulty, 'value') else str(new_problem.difficulty),
            'created_at': new_problem.created_at.isoformat()
        }
        await redis_service.set_current_problem(problem_data)
        
        logger.info(f"Generated {difficulty_level.value} problem for user {user_session['username']}")
        
        # Broadcast to all users
        await sio.emit('new_problem', {
            'problem': problem_data,
            'message': f'New {difficulty_level.value} problem available!'
        }, room=QUIZ_ROOM)
        
    except Exception as e:
        logger.error(f"Error in request_problem_with_difficulty: {e}")
        await sio.emit('error', {
            'message': 'Failed to generate problem with difficulty',
            'error': str(e)
        }, room=sid)

# Additional Socket.IO events for admin/testing
@sio.event
async def get_quiz_stats(sid, data):
    """Get current quiz statistics using Redis data."""
    try:
        global current_problem_cache
        
        # Get stats from Redis
        active_users_count = await redis_service.get_active_users_count()
        user_sessions = await redis_service.get_all_user_sessions()
        submission_stats = await concurrency_manager.get_submission_stats()
        
        stats = {
            'active_users_count': active_users_count,
            'current_problem_id': str(current_problem_cache.id) if current_problem_cache else None,
            'users': [
                {
                    'user_id': user_id,
                    'username': info.get('username', 'Unknown'),
                    'score': info.get('score', 0),
                    'wins': info.get('wins', 0)
                }
                for user_id, info in user_sessions.items()
            ],
            'submission_stats': submission_stats,
            'redis_health': await redis_service.health_check()
        }
        
        await sio.emit('quiz_stats', stats, room=sid)
        
    except Exception as e:
        logger.error(f"Error in get_quiz_stats: {e}")
        await sio.emit('error', {
            'message': 'Failed to get quiz stats',
            'error': str(e)
        }, room=sid)

@sio.event
async def force_new_problem(sid, data):
    """
    Force generation of a new problem using Redis state management.
    """
    try:
        # Check if user is in active session
        user_session = await redis_service.get_user_session(sid)
        if not user_session:
            await sio.emit('error', {
                'message': 'User not in quiz session'
            }, room=sid)
            return
        
        global current_problem_cache
        
        # Reset current problem state
        if current_problem_cache:
            await concurrency_manager.reset_problem_state(str(current_problem_cache.id))
        
        # Generate new problem
        difficulty = data.get('difficulty', 'medium')
        try:
            difficulty_level = DifficultyLevel(difficulty.lower())
        except ValueError:
            difficulty_level = DifficultyLevel.MEDIUM
        
        new_problem = await quiz_engine.generate_problem_with_ai(difficulty_level)
        current_problem_cache = new_problem
        
        # Store in Redis
        problem_data = {
            'id': str(new_problem.id),
            'question': new_problem.question,
            'correct_answer': new_problem.correct_answer,
            'difficulty': new_problem.difficulty.value,
            'created_at': new_problem.created_at.isoformat()
        }
        await redis_service.set_current_problem(problem_data)
        
        logger.info(f"Forced new problem generation: {new_problem.id}")
        
        # Broadcast to all users
        await sio.emit('new_problem', {
            'problem': problem_data,
            'message': 'New problem generated!'
        }, room=QUIZ_ROOM)
        
    except Exception as e:
        logger.error(f"Error in force_new_problem: {e}")
        await sio.emit('error', {
            'message': 'Failed to generate new problem',
            'error': str(e)
        }, room=sid)

@sio.event
async def get_leaderboard(sid, data):
    """
    Handle request for current leaderboard.
    """
    try:
        # Check if user is in active session
        user_session = await redis_service.get_user_session(sid)
        if not user_session:
            await sio.emit('error', {
                'message': 'User not in quiz session'
            }, room=sid)
            return
        
        # Get leaderboard and session stats
        leaderboard = await score_tracker.get_leaderboard(limit=10)
        session_stats = await score_tracker.get_session_stats()
        
        # Send to requesting user
        await sio.emit('leaderboard_data', {
            'leaderboard': leaderboard,
            'session_stats': session_stats,
            'timestamp': datetime.utcnow().isoformat()
        }, room=sid)
        
    except Exception as e:
        logger.error(f"Error in get_leaderboard: {e}")
        await sio.emit('error', {
            'message': 'Failed to get leaderboard',
            'error': str(e)
        }, room=sid)

# Include health check router
from health_check import health_router
app.include_router(health_router)

@app.get("/api/stats")
async def get_api_stats():
    """REST endpoint for quiz statistics using Redis data."""
    try:
        global current_problem_cache
        
        active_users_count = await redis_service.get_active_users_count()
        user_sessions = await redis_service.get_all_user_sessions()
        submission_stats = await concurrency_manager.get_submission_stats()
        redis_health = await redis_service.health_check()
        
        return {
            "active_users": active_users_count,
            "current_problem": str(current_problem_cache.id) if current_problem_cache else None,
            "total_sessions": len(user_sessions),
            "submission_stats": submission_stats,
            "redis_health": redis_health
        }
    except Exception as e:
        logger.error(f"Error getting API stats: {e}")
        return {
            "error": str(e),
            "active_users": 0,
            "current_problem": None,
            "total_sessions": 0
        }

@app.get("/api/redis/health")
async def redis_health_check():
    """Health check endpoint specifically for Redis."""
    return await redis_service.health_check()

@app.get("/api/database/health")
async def database_health_check():
    """Health check endpoint specifically for Database."""
    return await database_service.health_check()

@app.get("/api/database/stats")
async def database_stats():
    """Get database statistics."""
    try:
        return await database_service.get_system_stats()
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {"error": str(e)}

@app.get("/api/leaderboard/all-time")
async def get_all_time_leaderboard(limit: int = 10):
    """Get all-time leaderboard from persistent storage."""
    try:
        return await score_tracker.get_all_time_leaderboard(limit)
    except Exception as e:
        logger.error(f"Error getting all-time leaderboard: {e}")
        return {"error": str(e)}

@app.get("/api/leaderboard/fastest")
async def get_fastest_times_leaderboard(limit: int = 10):
    """Get fastest response times leaderboard."""
    try:
        return await score_tracker.get_fastest_times_leaderboard(limit)
    except Exception as e:
        logger.error(f"Error getting fastest times leaderboard: {e}")
        return {"error": str(e)}

@app.get("/api/user/{user_id}/stats")
async def get_user_comprehensive_stats(user_id: str):
    """Get comprehensive user statistics including session and all-time data."""
    try:
        return await score_tracker.get_user_statistics(user_id)
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {"error": str(e)}

# Performance monitoring endpoints

@app.get("/api/performance/summary")
async def get_performance_summary():
    """Get comprehensive performance summary."""
    try:
        return performance_monitor.get_comprehensive_report()
    except Exception as e:
        logger.error(f"Error getting performance summary: {e}")
        return {"error": str(e)}

@app.get("/api/performance/api")
async def get_api_performance(minutes: int = 60):
    """Get API performance metrics for the last N minutes."""
    try:
        return performance_monitor.get_api_performance_summary(minutes)
    except Exception as e:
        logger.error(f"Error getting API performance: {e}")
        return {"error": str(e)}

@app.get("/api/performance/system")
async def get_system_performance():
    """Get current system performance metrics."""
    try:
        return performance_monitor.get_system_performance_summary()
    except Exception as e:
        logger.error(f"Error getting system performance: {e}")
        return {"error": str(e)}

@app.get("/api/performance/gemini")
async def get_gemini_performance(minutes: int = 60):
    """Get Gemini API performance metrics."""
    try:
        return performance_monitor.get_gemini_api_summary(minutes)
    except Exception as e:
        logger.error(f"Error getting Gemini performance: {e}")
        return {"error": str(e)}

@app.get("/api/performance/websockets")
async def get_websocket_performance():
    """Get WebSocket connection metrics."""
    try:
        return performance_monitor.get_websocket_summary()
    except Exception as e:
        logger.error(f"Error getting WebSocket performance: {e}")
        return {"error": str(e)}

@app.get("/api/prefetch/stats")
async def get_prefetch_stats():
    """Get prefetch cache statistics."""
    try:
        stats = await prefetch_service.get_cache_stats()
        return {
            "cache_stats": stats,
            "config": {
                "enabled": prefetch_service.enabled,
                "batch_size": prefetch_service.batch_size,
                "min_threshold": prefetch_service.min_threshold
            }
        }
    except Exception as e:
        logger.error(f"Error getting prefetch stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get prefetch stats")

@app.get("/api/performance/cache")
async def get_cache_performance():
    """Get cache performance statistics."""
    try:
        cache_stats = cache_service.get_cache_stats()
        redis_memory = await redis_service.get_memory_usage()
        
        return {
            "cache_stats": cache_stats,
            "redis_memory": redis_memory
        }
    except Exception as e:
        logger.error(f"Error getting cache performance: {e}")
        return {"error": str(e)}

@app.post("/api/performance/cache/clear/{namespace}")
async def clear_cache_namespace(namespace: str):
    """Clear cache for a specific namespace."""
    try:
        cleared_count = await cache_service.clear_namespace(namespace)
        return {
            "message": f"Cleared {cleared_count} entries from namespace: {namespace}",
            "cleared_count": cleared_count
        }
    except Exception as e:
        logger.error(f"Error clearing cache namespace {namespace}: {e}")
        return {"error": str(e)}

# Mount Socket.IO app
socket_app = socketio.ASGIApp(sio, app)

if __name__ == "__main__":
    uvicorn.run(
        socket_app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        access_log=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )