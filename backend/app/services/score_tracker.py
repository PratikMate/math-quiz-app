"""
Score tracking service for managing user scores and leaderboards.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from uuid import UUID

from .redis_service import RedisService


logger = logging.getLogger(__name__)


@dataclass
class UserScore:
    """User score data structure."""
    user_id: str
    username: str
    session_wins: int = 0
    session_problems_attempted: int = 0
    total_response_time_ms: int = 0
    fastest_response_time_ms: Optional[int] = None
    last_win_time: Optional[datetime] = None
    # Persistent data from database
    persistent_user_id: Optional[str] = None
    all_time_wins: int = 0
    all_time_problems_attempted: int = 0
    all_time_best_response_time: Optional[float] = None
    
    @property
    def average_response_time_ms(self) -> float:
        """Calculate average response time for correct answers."""
        if self.session_wins == 0:
            return 0.0
        return self.total_response_time_ms / self.session_wins
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if self.last_win_time:
            data['last_win_time'] = self.last_win_time.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserScore':
        """Create UserScore from dictionary."""
        if 'last_win_time' in data and data['last_win_time']:
            data['last_win_time'] = datetime.fromisoformat(data['last_win_time'])
        return cls(**data)


class ScoreTracker:
    """
    Manages user scoring and leaderboards for the competitive math quiz.
    
    Tracks session-based scores including wins, response times, and maintains
    real-time leaderboards. Uses Redis for session data and database for persistence.
    """
    
    def __init__(self, redis_service: RedisService, database_service=None):
        """
        Initialize score tracker with Redis and database services.
        
        Args:
            redis_service: Redis service instance for session data
            database_service: Database service instance for persistent data
        """
        self.redis_service = redis_service
        self.database_service = database_service
        
        # Redis key prefixes
        self.SCORES_KEY_PREFIX = "quiz:scores"
        self.LEADERBOARD_KEY = "quiz:leaderboard"
        self.SESSION_STATS_KEY = "quiz:session_stats"
        
        # In-memory cache for fast access
        self._score_cache: Dict[str, UserScore] = {}
        self._cache_dirty = False
    
    async def initialize_user_score(self, user_id: str, username: str) -> UserScore:
        """
        Initialize or retrieve user score data with persistent database integration.
        
        Args:
            user_id: User identifier (session ID)
            username: User display name
            
        Returns:
            UserScore instance for the user
        """
        try:
            # Check cache first
            if user_id in self._score_cache:
                return self._score_cache[user_id]
            
            # Try to load from Redis
            score_key = f"{self.SCORES_KEY_PREFIX}:{user_id}"
            score_data = await self.redis_service.redis_client.get(score_key)
            
            if score_data:
                import json
                data = json.loads(score_data)
                user_score = UserScore.from_dict(data)
                # Update username in case it changed
                user_score.username = username
            else:
                # Create new user score
                user_score = UserScore(user_id=user_id, username=username)
            
            # Load persistent data from database if available
            if self.database_service:
                try:
                    # Get or create user in database
                    db_user, created = await self.database_service.get_or_create_user(username)
                    user_score.persistent_user_id = db_user['id']
                    user_score.all_time_wins = db_user['total_wins']
                    user_score.all_time_problems_attempted = db_user['total_problems_attempted']
                    user_score.all_time_best_response_time = db_user['best_response_time']
                    
                    if created:
                        logger.info(f"Created new persistent user: {username}")
                    else:
                        logger.info(f"Loaded persistent data for user: {username}")
                        
                except Exception as db_error:
                    logger.warning(f"Failed to load persistent data for {username}: {db_error}")
            
            # Cache the score
            self._score_cache[user_id] = user_score
            
            # Save to Redis
            await self._save_user_score(user_score)
            
            return user_score
            
        except Exception as e:
            logger.error(f"Failed to initialize user score for {user_id}: {e}")
            # Return default score on error
            user_score = UserScore(user_id=user_id, username=username)
            self._score_cache[user_id] = user_score
            return user_score
    
    async def record_win(
        self, 
        user_id: str, 
        username: str, 
        response_time_ms: int,
        problem_id: str
    ) -> UserScore:
        """
        Record a win for a user and update both session and persistent scores.
        
        Args:
            user_id: User identifier (session ID)
            username: User display name
            response_time_ms: Response time in milliseconds
            problem_id: ID of the solved problem
            
        Returns:
            Updated UserScore instance
        """
        try:
            # Get or initialize user score
            user_score = await self.initialize_user_score(user_id, username)
            
            # Update session statistics
            user_score.session_wins += 1
            user_score.session_problems_attempted += 1
            user_score.total_response_time_ms += response_time_ms
            user_score.last_win_time = datetime.utcnow()
            
            # Update fastest response time
            if (user_score.fastest_response_time_ms is None or 
                response_time_ms < user_score.fastest_response_time_ms):
                user_score.fastest_response_time_ms = response_time_ms
            
            # Update persistent data in database
            if self.database_service and user_score.persistent_user_id:
                try:
                    # Record the submission in database
                    await self.database_service.record_submission(
                        user_id=UUID(user_score.persistent_user_id),
                        problem_id=UUID(problem_id),
                        submitted_answer=0.0,  # We don't have the actual answer here
                        is_correct=True,
                        response_time_ms=response_time_ms
                    )
                    
                    # Update user performance statistics
                    updated_user = await self.database_service.update_user_performance(
                        user_id=UUID(user_score.persistent_user_id),
                        won_problem=True,
                        response_time_ms=response_time_ms
                    )
                    
                    if updated_user:
                        # Update cached persistent data
                        user_score.all_time_wins = updated_user['total_wins']
                        user_score.all_time_problems_attempted = updated_user['total_problems_attempted']
                        user_score.all_time_best_response_time = updated_user['best_response_time']
                        
                        logger.info(f"Updated persistent data for {username}: {updated_user['total_wins']} total wins")
                    
                except Exception as db_error:
                    logger.warning(f"Failed to update persistent data for {username}: {db_error}")
            
            # Save to Redis
            await self._save_user_score(user_score)
            
            # Update leaderboard
            await self._update_leaderboard()
            
            logger.info(f"Recorded win for {username} ({user_id}): {response_time_ms}ms")
            
            return user_score
            
        except Exception as e:
            logger.error(f"Failed to record win for {user_id}: {e}")
            return await self.initialize_user_score(user_id, username)
    
    async def record_attempt(self, user_id: str, username: str, problem_id: str = None, submitted_answer: float = None, is_correct: bool = False, response_time_ms: int = None) -> UserScore:
        """
        Record a problem attempt (correct or incorrect) for a user.
        
        Args:
            user_id: User identifier (session ID)
            username: User display name
            problem_id: ID of the attempted problem
            submitted_answer: User's submitted answer
            is_correct: Whether the answer was correct
            response_time_ms: Response time in milliseconds
            
        Returns:
            Updated UserScore instance
        """
        try:
            # Get or initialize user score
            user_score = await self.initialize_user_score(user_id, username)
            
            # Update attempt count
            user_score.session_problems_attempted += 1
            
            # Record in database if available
            if (self.database_service and user_score.persistent_user_id and 
                problem_id and submitted_answer is not None and response_time_ms is not None):
                try:
                    await self.database_service.record_submission(
                        user_id=UUID(user_score.persistent_user_id),
                        problem_id=UUID(problem_id),
                        submitted_answer=submitted_answer,
                        is_correct=is_correct,
                        response_time_ms=response_time_ms
                    )
                    
                    # Update user performance (for attempts, not wins)
                    if not is_correct:
                        await self.database_service.update_user_performance(
                            user_id=UUID(user_score.persistent_user_id),
                            won_problem=False,
                            response_time_ms=None
                        )
                    
                except Exception as db_error:
                    logger.warning(f"Failed to record attempt in database for {username}: {db_error}")
            
            # Save to Redis
            await self._save_user_score(user_score)
            
            return user_score
            
        except Exception as e:
            logger.error(f"Failed to record attempt for {user_id}: {e}")
            return await self.initialize_user_score(user_id, username)
    
    async def get_user_score(self, user_id: str) -> Optional[UserScore]:
        """
        Get current score for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserScore instance or None if user not found
        """
        try:
            # Check cache first
            if user_id in self._score_cache:
                return self._score_cache[user_id]
            
            # Load from Redis
            score_key = f"{self.SCORES_KEY_PREFIX}:{user_id}"
            score_data = await self.redis_service.redis_client.get(score_key)
            
            if score_data:
                import json
                data = json.loads(score_data)
                user_score = UserScore.from_dict(data)
                self._score_cache[user_id] = user_score
                return user_score
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user score for {user_id}: {e}")
            return None
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get current session leaderboard sorted by wins and response time.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of user score dictionaries sorted by performance
        """
        try:
            # Get all cached scores
            all_scores = list(self._score_cache.values())
            
            # If cache is empty, try to load from Redis
            if not all_scores:
                await self._load_all_scores_from_redis()
                all_scores = list(self._score_cache.values())
            
            # Sort by wins (descending), then by average response time (ascending)
            sorted_scores = sorted(
                all_scores,
                key=lambda x: (-x.session_wins, x.average_response_time_ms if x.session_wins > 0 else float('inf'))
            )
            
            # Convert to dictionaries and add rank
            leaderboard = []
            for rank, score in enumerate(sorted_scores[:limit], 1):
                score_dict = score.to_dict()
                score_dict['rank'] = rank
                score_dict['average_response_time_ms'] = round(score.average_response_time_ms, 1)
                leaderboard.append(score_dict)
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}")
            return []
    
    async def get_all_time_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get all-time leaderboard from persistent database storage.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of user dictionaries sorted by all-time performance
        """
        try:
            if not self.database_service:
                logger.warning("Database service not available for all-time leaderboard")
                return []
            
            # Get leaderboard from database
            leaderboard = await self.database_service.get_leaderboard(limit)
            
            # Add rank information
            for rank, user_data in enumerate(leaderboard, 1):
                user_data['rank'] = rank
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Failed to get all-time leaderboard: {e}")
            return []
    
    async def get_user_statistics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive statistics for a user including session and all-time data.
        
        Args:
            user_id: User identifier (session ID)
            
        Returns:
            Dictionary with comprehensive user statistics
        """
        try:
            # Get session data
            user_score = await self.get_user_score(user_id)
            if not user_score:
                return None
            
            stats = {
                'session_data': user_score.to_dict(),
                'all_time_data': None
            }
            
            # Get persistent data from database
            if self.database_service and user_score.persistent_user_id:
                try:
                    db_stats = await self.database_service.get_user_by_id(UUID(user_score.persistent_user_id))
                    if db_stats:
                        stats['all_time_data'] = db_stats
                        
                        # Get user's submission history
                        submissions = await self.database_service.get_user_submissions(
                            UUID(user_score.persistent_user_id), 
                            limit=20
                        )
                        stats['recent_submissions'] = submissions
                        
                except Exception as db_error:
                    logger.warning(f"Failed to get persistent stats for user {user_id}: {db_error}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get user statistics for {user_id}: {e}")
            return None
    
    async def get_fastest_times_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get leaderboard of fastest response times from database.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of fastest submission records
        """
        try:
            if not self.database_service:
                return []
            
            fastest_submissions = await self.database_service.get_fastest_submissions(limit)
            
            # Add rank information
            for rank, submission in enumerate(fastest_submissions, 1):
                submission['rank'] = rank
            
            return fastest_submissions
            
        except Exception as e:
            logger.error(f"Failed to get fastest times leaderboard: {e}")
            return []
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """
        Get overall session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        try:
            all_scores = list(self._score_cache.values())
            
            if not all_scores:
                return {
                    'total_players': 0,
                    'total_wins': 0,
                    'total_attempts': 0,
                    'average_response_time_ms': 0.0,
                    'fastest_response_time_ms': None
                }
            
            total_wins = sum(score.session_wins for score in all_scores)
            total_attempts = sum(score.session_problems_attempted for score in all_scores)
            
            # Calculate overall average response time
            total_response_time = sum(score.total_response_time_ms for score in all_scores)
            average_response_time = total_response_time / total_wins if total_wins > 0 else 0.0
            
            # Find fastest response time
            fastest_times = [
                score.fastest_response_time_ms 
                for score in all_scores 
                if score.fastest_response_time_ms is not None
            ]
            fastest_response_time = min(fastest_times) if fastest_times else None
            
            return {
                'total_players': len(all_scores),
                'total_wins': total_wins,
                'total_attempts': total_attempts,
                'average_response_time_ms': round(average_response_time, 1),
                'fastest_response_time_ms': fastest_response_time
            }
            
        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            return {}
    
    async def reset_session_scores(self) -> bool:
        """
        Reset all session scores (for new quiz sessions).
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear cache
            self._score_cache.clear()
            
            # Clear Redis scores
            pattern = f"{self.SCORES_KEY_PREFIX}:*"
            keys = await self.redis_service.redis_client.keys(pattern)
            if keys:
                await self.redis_service.redis_client.delete(*keys)
            
            # Clear leaderboard
            await self.redis_service.redis_client.delete(self.LEADERBOARD_KEY)
            
            logger.info("Reset all session scores")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset session scores: {e}")
            return False
    
    async def cleanup_inactive_users(self, active_user_ids: List[str]) -> int:
        """
        Remove scores for users who are no longer active.
        
        Args:
            active_user_ids: List of currently active user IDs
            
        Returns:
            Number of inactive users cleaned up
        """
        try:
            cleaned_count = 0
            inactive_users = []
            
            # Find inactive users in cache
            for user_id in list(self._score_cache.keys()):
                if user_id not in active_user_ids:
                    inactive_users.append(user_id)
            
            # Remove inactive users
            for user_id in inactive_users:
                del self._score_cache[user_id]
                
                # Remove from Redis
                score_key = f"{self.SCORES_KEY_PREFIX}:{user_id}"
                await self.redis_service.redis_client.delete(score_key)
                
                cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} inactive user scores")
                await self._update_leaderboard()
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup inactive users: {e}")
            return 0
    
    async def _save_user_score(self, user_score: UserScore) -> bool:
        """
        Save user score to Redis.
        
        Args:
            user_score: UserScore instance to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            score_key = f"{self.SCORES_KEY_PREFIX}:{user_score.user_id}"
            score_data = user_score.to_dict()
            
            import json
            await self.redis_service.redis_client.setex(
                score_key,
                self.redis_service.SESSION_EXPIRY,
                json.dumps(score_data, default=str)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save user score: {e}")
            return False
    
    async def _load_all_scores_from_redis(self) -> None:
        """Load all user scores from Redis into cache."""
        try:
            pattern = f"{self.SCORES_KEY_PREFIX}:*"
            keys = await self.redis_service.redis_client.keys(pattern)
            
            for key in keys:
                score_data = await self.redis_service.redis_client.get(key)
                if score_data:
                    import json
                    data = json.loads(score_data)
                    user_score = UserScore.from_dict(data)
                    self._score_cache[user_score.user_id] = user_score
                    
        except Exception as e:
            logger.error(f"Failed to load scores from Redis: {e}")
    
    async def _update_leaderboard(self) -> None:
        """Update the cached leaderboard in Redis."""
        try:
            leaderboard = await self.get_leaderboard(limit=50)  # Store top 50
            
            import json
            await self.redis_service.redis_client.setex(
                self.LEADERBOARD_KEY,
                300,  # 5 minutes expiry
                json.dumps(leaderboard, default=str)
            )
            
        except Exception as e:
            logger.error(f"Failed to update leaderboard: {e}")