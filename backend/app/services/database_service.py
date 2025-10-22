"""
Database service for managing persistent data operations.
"""
import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from ..database.connection import db_manager, get_db_session
from ..database.repositories import RepositoryManager
from ..database.models import User, Problem, Submission
from .structured_logger import get_structured_logger
from .cache_service import CacheService

logger = get_structured_logger(__name__)


class DatabaseService:
    """
    Service class for database operations with high-level business logic.
    """
    
    def __init__(self):
        """Initialize database service."""
        self.cache_service: Optional[CacheService] = None
    
    def set_cache_service(self, cache_service: CacheService):
        """Set cache service for performance optimization."""
        self.cache_service = cache_service
    
    async def initialize(self):
        """Initialize database connection and create tables if needed."""
        try:
            await db_manager.initialize()
            await db_manager.create_tables()
            logger.info("Database service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database service: {e}", exception=e)
            raise
    
    async def close(self):
        """Close database connections."""
        await db_manager.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database health status."""
        return await db_manager.health_check()
    
    # User operations
    async def get_or_create_user(self, username: str) -> tuple[Dict[str, Any], bool]:
        """
        Get existing user or create new one.
        
        Args:
            username: Username to search for or create
            
        Returns:
            Tuple of (user_dict, created_flag)
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            
            user, created = await repo.users.get_or_create_user(username)
            await repo.commit()
            
            user_dict = {
                'id': str(user.id),
                'username': user.username,
                'total_wins': user.total_wins,
                'total_problems_attempted': user.total_problems_attempted,
                'best_response_time': user.best_response_time,
                'win_rate': user.win_rate,
                'created_at': user.created_at.isoformat(),
                'last_active': user.last_active.isoformat()
            }
            
            return user_dict, created
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.
        
        Args:
            user_id: User UUID
            
        Returns:
            User dictionary or None if not found
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            return await repo.users.get_user_stats(user_id)
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username.
        
        Args:
            username: Username to search for
            
        Returns:
            User dictionary or None if not found
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            user = await repo.users.get_user_by_username(username)
            
            if not user:
                return None
            
            return await repo.users.get_user_stats(user.id)
    
    async def update_user_performance(
        self,
        user_id: UUID,
        won_problem: bool = False,
        response_time_ms: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update user performance statistics.
        
        Args:
            user_id: User UUID
            won_problem: Whether the user won a problem
            response_time_ms: Response time in milliseconds
            
        Returns:
            Updated user stats or None if user not found
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            
            user = await repo.users.get_user_by_id(user_id)
            if not user:
                return None
            
            # Update statistics
            if won_problem:
                user.total_wins += 1
            
            user.total_problems_attempted += 1
            
            if response_time_ms is not None:
                response_time_seconds = response_time_ms / 1000.0
                if user.best_response_time is None or response_time_seconds < user.best_response_time:
                    user.best_response_time = response_time_seconds
            
            user.update_last_active()
            
            await repo.commit()
            
            return await repo.users.get_user_stats(user.id)
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top users leaderboard with caching.
        
        Args:
            limit: Maximum number of users to return
            
        Returns:
            List of user dictionaries sorted by performance
        """
        # Try cache first if available
        if self.cache_service:
            cached_leaderboard = await self.cache_service.get(
                "leaderboard", 
                f"top_{limit}",
                ttl=60  # Cache for 1 minute
            )
            if cached_leaderboard:
                return cached_leaderboard
        
        start_time = time.time()
        
        async for session in get_db_session():
            repo = RepositoryManager(session)
            users = await repo.users.get_top_users(limit)
            
            leaderboard = []
            for user in users:
                user_stats = await repo.users.get_user_stats(user.id)
                if user_stats:
                    leaderboard.append(user_stats)
            
            duration_ms = (time.time() - start_time) * 1000
            logger.log_database_query(
                query_type="SELECT",
                table="users",
                duration_ms=duration_ms,
                rows_affected=len(leaderboard),
                operation="get_leaderboard",
                limit=limit
            )
            
            # Cache the result
            if self.cache_service and leaderboard:
                await self.cache_service.set(
                    "leaderboard",
                    f"top_{limit}",
                    leaderboard,
                    ttl=60
                )
            
            return leaderboard
    
    # Problem operations
    async def store_problem(
        self,
        problem_id: UUID,
        question: str,
        correct_answer: float,
        difficulty: str
    ) -> Dict[str, Any]:
        """
        Store a new problem in the database.
        
        Args:
            problem_id: Problem UUID
            question: Problem question text
            correct_answer: Correct numerical answer
            difficulty: Difficulty level
            
        Returns:
            Problem dictionary
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            
            # Check if problem already exists
            existing_problem = await repo.problems.get_problem_by_id(problem_id)
            if existing_problem:
                return {
                    'id': str(existing_problem.id),
                    'question': existing_problem.question,
                    'correct_answer': existing_problem.correct_answer,
                    'difficulty': existing_problem.difficulty,
                    'created_at': existing_problem.created_at.isoformat(),
                    'is_solved': existing_problem.is_solved,
                    'solved_by': str(existing_problem.solved_by) if existing_problem.solved_by else None,
                    'solved_at': existing_problem.solved_at.isoformat() if existing_problem.solved_at else None
                }
            
            # Create new problem with specific ID
            problem = Problem(
                id=problem_id,
                question=question,
                correct_answer=correct_answer,
                difficulty=difficulty
            )
            session.add(problem)
            await repo.commit()
            
            return {
                'id': str(problem.id),
                'question': problem.question,
                'correct_answer': problem.correct_answer,
                'difficulty': problem.difficulty,
                'created_at': problem.created_at.isoformat(),
                'is_solved': problem.is_solved,
                'solved_by': None,
                'solved_at': None
            }
    
    async def mark_problem_solved(
        self,
        problem_id: UUID,
        user_id: UUID,
        solved_time: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Mark a problem as solved by a user.
        
        Args:
            problem_id: Problem UUID
            user_id: User UUID who solved it
            solved_time: When it was solved
            
        Returns:
            Updated problem dictionary or None if not found
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            
            problem = await repo.problems.mark_problem_solved(problem_id, user_id, solved_time)
            if not problem:
                return None
            
            await repo.commit()
            
            return {
                'id': str(problem.id),
                'question': problem.question,
                'correct_answer': problem.correct_answer,
                'difficulty': problem.difficulty,
                'created_at': problem.created_at.isoformat(),
                'is_solved': problem.is_solved,
                'solved_by': str(problem.solved_by) if problem.solved_by else None,
                'solved_at': problem.solved_at.isoformat() if problem.solved_at else None
            }
    
    # Submission operations
    async def record_submission(
        self,
        user_id: UUID,
        problem_id: UUID,
        submitted_answer: float,
        is_correct: bool,
        response_time_ms: int
    ) -> Dict[str, Any]:
        """
        Record a user's answer submission.
        
        Args:
            user_id: User UUID
            problem_id: Problem UUID
            submitted_answer: User's submitted answer
            is_correct: Whether the answer is correct
            response_time_ms: Response time in milliseconds
            
        Returns:
            Submission dictionary
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            
            submission = await repo.submissions.create_submission(
                user_id=user_id,
                problem_id=problem_id,
                submitted_answer=submitted_answer,
                is_correct=is_correct,
                response_time_ms=response_time_ms
            )
            
            await repo.commit()
            
            return {
                'id': str(submission.id),
                'user_id': str(submission.user_id),
                'problem_id': str(submission.problem_id),
                'submitted_answer': submission.submitted_answer,
                'is_correct': submission.is_correct,
                'response_time_ms': submission.response_time_ms,
                'response_time_seconds': submission.response_time_seconds,
                'submitted_at': submission.submitted_at.isoformat()
            }
    
    async def get_user_submissions(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get user's submission history.
        
        Args:
            user_id: User UUID
            limit: Maximum number of submissions to return
            
        Returns:
            List of submission dictionaries
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            submissions = await repo.submissions.get_user_submissions(user_id, limit)
            
            return [
                {
                    'id': str(sub.id),
                    'problem_id': str(sub.problem_id),
                    'submitted_answer': sub.submitted_answer,
                    'is_correct': sub.is_correct,
                    'response_time_ms': sub.response_time_ms,
                    'submitted_at': sub.submitted_at.isoformat(),
                    'problem_question': sub.problem.question if sub.problem else None,
                    'problem_difficulty': sub.problem.difficulty if sub.problem else None
                }
                for sub in submissions
            ]
    
    async def get_fastest_submissions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get fastest correct submissions across all problems.
        
        Args:
            limit: Maximum number of submissions to return
            
        Returns:
            List of fastest submission dictionaries
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            submissions = await repo.submissions.get_fastest_submissions(limit)
            
            return [
                {
                    'id': str(sub.id),
                    'user_id': str(sub.user_id),
                    'username': sub.user.username if sub.user else 'Unknown',
                    'problem_id': str(sub.problem_id),
                    'problem_question': sub.problem.question if sub.problem else None,
                    'submitted_answer': sub.submitted_answer,
                    'response_time_ms': sub.response_time_ms,
                    'submitted_at': sub.submitted_at.isoformat()
                }
                for sub in submissions
            ]
    
    # Analytics operations
    async def get_system_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive system statistics.
        
        Returns:
            Dictionary with system statistics
        """
        async for session in get_db_session():
            repo = RepositoryManager(session)
            
            from sqlalchemy import text
            # Get counts
            total_users_result = await session.execute(text("SELECT COUNT(*) FROM users"))
            total_problems_result = await session.execute(text("SELECT COUNT(*) FROM problems"))
            total_submissions_result = await session.execute(text("SELECT COUNT(*) FROM submissions"))
            solved_problems_result = await session.execute(text("SELECT COUNT(*) FROM problems WHERE solved_by IS NOT NULL"))
            
            total_users = total_users_result.scalar()
            total_problems = total_problems_result.scalar()
            total_submissions = total_submissions_result.scalar()
            solved_problems = solved_problems_result.scalar()
            
            # Get recent activity (SQLite compatible)
            recent_users_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-24 hours')")
            )
            recent_users = recent_users_result.scalar()
            
            return {
                'total_users': total_users,
                'total_problems': total_problems,
                'total_submissions': total_submissions,
                'solved_problems': solved_problems,
                'unsolved_problems': total_problems - solved_problems,
                'recent_active_users': recent_users,
                'solve_rate': (solved_problems / total_problems * 100) if total_problems > 0 else 0
            }