"""
Concurrency manager service for atomic submission processing and winner determination.
"""
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from .redis_service import RedisService
from ..models.math_problem import MathProblem, AnswerSubmission, AnswerValidationResult, validate_answer


logger = logging.getLogger(__name__)


class SubmissionResult:
    """Result of processing an answer submission with Redis-backed concurrency control."""
    
    def __init__(
        self,
        submission_id: str,
        user_id: str,
        is_correct: bool,
        is_winner: bool,
        server_timestamp: datetime,
        validation_result: AnswerValidationResult,
        message: str = "",
        rank: Optional[int] = None
    ):
        self.submission_id = submission_id
        self.user_id = user_id
        self.is_correct = is_correct
        self.is_winner = is_winner
        self.server_timestamp = server_timestamp
        self.validation_result = validation_result
        self.message = message
        self.rank = rank  # Position in submission order (1 = first, 2 = second, etc.)


class ConcurrencyManager:
    """
    Manages atomic submission processing using Redis for fair competition.
    
    Uses Redis sorted sets for timestamp-based submission ordering,
    distributed locking for winner determination, and submission deduplication.
    """
    
    def __init__(self, redis_service: RedisService):
        """
        Initialize concurrency manager with Redis service.
        
        Args:
            redis_service: RedisService instance for data operations
        """
        self.redis = redis_service
        
        # Redis key patterns
        self.SUBMISSIONS_KEY_PREFIX = "quiz:submissions"
        self.CORRECT_SUBMISSIONS_KEY_PREFIX = "quiz:correct_submissions"
        self.USER_SUBMISSIONS_KEY_PREFIX = "quiz:user_submissions"
        self.PROBLEM_LOCK_PREFIX = "quiz:lock"
        self.SOLVED_PROBLEMS_KEY = "quiz:solved_problems"
        
        # Lock configuration
        self.LOCK_TIMEOUT = 5  # seconds
        self.LOCK_RETRY_DELAY = 0.01  # 10ms
        self.MAX_LOCK_RETRIES = 100
    
    async def submit_answer(
        self,
        user_id: str,
        problem: MathProblem,
        submitted_answer: any,
        submission_id: Optional[str] = None
    ) -> SubmissionResult:
        """
        Process answer submission with atomic winner determination using Redis.
        
        Uses Redis sorted sets for timestamp-based submission ordering and
        distributed locking to ensure fair winner detection.
        
        Args:
            user_id: ID of the user submitting the answer
            problem: The math problem being answered
            submitted_answer: The user's submitted answer
            submission_id: Optional submission ID for tracking
            
        Returns:
            SubmissionResult with processing details including winner status
        """
        problem_id = str(problem.id)
        submission_id = submission_id or f"{user_id}_{problem_id}_{time.time()}"
        server_timestamp = datetime.utcnow()
        timestamp_score = server_timestamp.timestamp()
        
        # Check if problem is already solved
        if await self._is_problem_solved(problem_id):
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=False,
                is_winner=False,
                server_timestamp=server_timestamp,
                validation_result=AnswerValidationResult(
                    is_correct=False,
                    submitted_value="0",
                    correct_value=str(problem.correct_answer),
                    message="Problem already solved"
                ),
                message="This problem has already been solved by another user"
            )
        
        # Check for duplicate submission
        if await self._has_user_submitted(problem_id, user_id):
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=False,
                is_winner=False,
                server_timestamp=server_timestamp,
                validation_result=AnswerValidationResult(
                    is_correct=False,
                    submitted_value="0",
                    correct_value=str(problem.correct_answer),
                    message="Duplicate submission"
                ),
                message="You have already submitted an answer for this problem"
            )
        
        # Validate the answer
        validation_result = await self._validate_submission(user_id, problem, submitted_answer, server_timestamp)
        
        # Acquire distributed lock for atomic processing
        lock_acquired = await self._acquire_problem_lock(problem_id)
        if not lock_acquired:
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=validation_result.is_correct,
                is_winner=False,
                server_timestamp=server_timestamp,
                validation_result=validation_result,
                message="Failed to process submission due to high concurrency. Please try again."
            )
        
        try:
            # Double-check if problem was solved while acquiring lock
            if await self._is_problem_solved(problem_id):
                return SubmissionResult(
                    submission_id=submission_id,
                    user_id=user_id,
                    is_correct=validation_result.is_correct,
                    is_winner=False,
                    server_timestamp=server_timestamp,
                    validation_result=validation_result,
                    message="Problem was solved while processing your submission"
                )
            
            # Record submission in Redis sorted set (all submissions)
            await self._record_submission(problem_id, user_id, submission_id, timestamp_score, validation_result)
            
            # Mark user as having submitted
            await self._mark_user_submitted(problem_id, user_id)
            
            is_winner = False
            rank = None
            message = ""
            
            if validation_result.is_correct:
                # Add to correct submissions sorted set and check if first
                rank = await self._record_correct_submission(problem_id, user_id, timestamp_score)
                
                if rank == 1:
                    # This is the first correct answer - user wins!
                    is_winner = True
                    await self._mark_problem_solved(problem_id, user_id, server_timestamp)
                    message = "Congratulations! You are the winner!"
                    logger.info(f"Winner detected: User {user_id} solved problem {problem_id}")
                else:
                    message = f"Correct answer! You were #{rank} to solve this problem."
            else:
                message = validation_result.message or "Incorrect answer"
            
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=validation_result.is_correct,
                is_winner=is_winner,
                server_timestamp=server_timestamp,
                validation_result=validation_result,
                message=message,
                rank=rank
            )
            
        finally:
            # Always release the lock
            await self._release_problem_lock(problem_id)
    
    async def get_problem_winner(self, problem_id: str) -> Optional[Dict]:
        """
        Get the winner information for a specific problem.
        
        Args:
            problem_id: The problem ID
            
        Returns:
            Winner information dictionary or None if no winner
        """
        try:
            # Get the first (earliest) correct submission
            correct_submissions_key = f"{self.CORRECT_SUBMISSIONS_KEY_PREFIX}:{problem_id}"
            
            # Get the earliest submission (lowest score/timestamp)
            earliest = await self.redis.redis_client.zrange(
                correct_submissions_key, 0, 0, withscores=True
            )
            
            if earliest:
                user_id = earliest[0][0].decode() if isinstance(earliest[0][0], bytes) else earliest[0][0]
                timestamp_score = earliest[0][1]
                
                # Get submission details
                submissions_key = f"{self.SUBMISSIONS_KEY_PREFIX}:{problem_id}"
                submission_data = await self.redis.redis_client.hget(submissions_key, user_id)
                
                if submission_data:
                    submission_info = json.loads(submission_data)
                    return {
                        'user_id': user_id,
                        'timestamp': datetime.fromtimestamp(timestamp_score),
                        'submission_info': submission_info
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get problem winner for {problem_id}: {e}")
            return None
    
    async def get_problem_submissions(self, problem_id: str, limit: int = 100) -> List[Dict]:
        """
        Get all submissions for a problem ordered by timestamp.
        
        Args:
            problem_id: The problem ID
            limit: Maximum number of submissions to return
            
        Returns:
            List of submission dictionaries ordered by timestamp
        """
        try:
            submissions_key = f"{self.SUBMISSIONS_KEY_PREFIX}:{problem_id}"
            
            # Get all submissions as hash
            all_submissions = await self.redis.redis_client.hgetall(submissions_key)
            
            submissions = []
            for user_id, submission_data in all_submissions.items():
                if isinstance(user_id, bytes):
                    user_id = user_id.decode()
                
                submission_info = json.loads(submission_data)
                submissions.append({
                    'user_id': user_id,
                    'timestamp': datetime.fromtimestamp(submission_info['timestamp']),
                    'is_correct': submission_info['is_correct'],
                    'submitted_answer': submission_info['submitted_answer']
                })
            
            # Sort by timestamp
            submissions.sort(key=lambda x: x['timestamp'])
            
            return submissions[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get problem submissions for {problem_id}: {e}")
            return []
    
    async def reset_problem_state(self, problem_id: str) -> bool:
        """
        Reset all state for a specific problem (for question rotation).
        
        Args:
            problem_id: The problem ID to reset
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Keys to clean up
            keys_to_delete = [
                f"{self.SUBMISSIONS_KEY_PREFIX}:{problem_id}",
                f"{self.CORRECT_SUBMISSIONS_KEY_PREFIX}:{problem_id}",
                f"{self.USER_SUBMISSIONS_KEY_PREFIX}:{problem_id}",
                f"{self.PROBLEM_LOCK_PREFIX}:{problem_id}"
            ]
            
            # Delete all keys
            if keys_to_delete:
                await self.redis.redis_client.delete(*keys_to_delete)
            
            # Remove from solved problems set
            await self.redis.redis_client.srem(self.SOLVED_PROBLEMS_KEY, problem_id)
            
            logger.info(f"Reset state for problem {problem_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset problem state for {problem_id}: {e}")
            return False
    
    async def get_submission_stats(self) -> Dict:
        """
        Get statistics about submissions for monitoring.
        
        Returns:
            Dictionary with submission statistics
        """
        try:
            # Get solved problems count
            solved_count = await self.redis.redis_client.scard(self.SOLVED_PROBLEMS_KEY)
            
            # Get pattern-based key counts (approximate)
            submission_keys = []
            async for key in self.redis.redis_client.scan_iter(match=f"{self.SUBMISSIONS_KEY_PREFIX}:*"):
                submission_keys.append(key)
            
            return {
                "solved_problems": solved_count,
                "active_problems": len(submission_keys),
                "redis_connected": await self.redis.is_connected()
            }
            
        except Exception as e:
            logger.error(f"Failed to get submission stats: {e}")
            return {"error": str(e)}
    
    # Private helper methods
    
    async def _validate_submission(
        self, 
        user_id: str, 
        problem: MathProblem, 
        submitted_answer: any, 
        timestamp: datetime
    ) -> AnswerValidationResult:
        """Validate a submission answer."""
        try:
            # Create submission object for validation
            import hashlib
            user_hash = hashlib.md5(user_id.encode()).hexdigest()
            user_uuid = UUID(user_hash)
            
            submission = AnswerSubmission(
                user_id=user_uuid,
                problem_id=problem.id,
                submitted_answer=submitted_answer,
                submitted_at=timestamp
            )
            
            return validate_answer(submission, problem)
            
        except Exception as e:
            logger.error(f"Submission validation failed: {e}")
            return AnswerValidationResult(
                is_correct=False,
                submitted_value=0.0,
                correct_value=problem.correct_answer,
                message=f"Validation error: {str(e)}"
            )
    
    async def _is_problem_solved(self, problem_id: str) -> bool:
        """Check if problem is already solved."""
        try:
            return await self.redis.redis_client.sismember(self.SOLVED_PROBLEMS_KEY, problem_id)
        except Exception as e:
            logger.error(f"Failed to check if problem solved: {e}")
            return False
    
    async def _has_user_submitted(self, problem_id: str, user_id: str) -> bool:
        """Check if user has already submitted for this problem."""
        try:
            user_submissions_key = f"{self.USER_SUBMISSIONS_KEY_PREFIX}:{problem_id}"
            return await self.redis.redis_client.sismember(user_submissions_key, user_id)
        except Exception as e:
            logger.error(f"Failed to check user submission: {e}")
            return False
    
    async def _record_submission(
        self, 
        problem_id: str, 
        user_id: str, 
        submission_id: str, 
        timestamp_score: float, 
        validation_result: AnswerValidationResult
    ) -> None:
        """Record submission in Redis."""
        try:
            submissions_key = f"{self.SUBMISSIONS_KEY_PREFIX}:{problem_id}"
            
            submission_data = {
                'submission_id': submission_id,
                'timestamp': timestamp_score,
                'is_correct': validation_result.is_correct,
                'submitted_answer': validation_result.submitted_value,
                'correct_answer': validation_result.correct_value
            }
            
            await self.redis.redis_client.hset(
                submissions_key, 
                user_id, 
                json.dumps(submission_data, default=str)
            )
            
            # Set expiration on the key
            await self.redis.redis_client.expire(submissions_key, self.redis.PROBLEM_EXPIRY)
            
        except Exception as e:
            logger.error(f"Failed to record submission: {e}")
    
    async def _record_correct_submission(self, problem_id: str, user_id: str, timestamp_score: float) -> int:
        """
        Record correct submission and return rank (1-based).
        
        Returns:
            Rank of this submission (1 = first, 2 = second, etc.)
        """
        try:
            correct_submissions_key = f"{self.CORRECT_SUBMISSIONS_KEY_PREFIX}:{problem_id}"
            
            # Add to sorted set with timestamp as score
            await self.redis.redis_client.zadd(correct_submissions_key, {user_id: timestamp_score})
            
            # Set expiration
            await self.redis.redis_client.expire(correct_submissions_key, self.redis.PROBLEM_EXPIRY)
            
            # Get rank (0-based, so add 1)
            rank = await self.redis.redis_client.zrank(correct_submissions_key, user_id)
            return (rank + 1) if rank is not None else 1
            
        except Exception as e:
            logger.error(f"Failed to record correct submission: {e}")
            return 1
    
    async def _mark_user_submitted(self, problem_id: str, user_id: str) -> None:
        """Mark user as having submitted for this problem."""
        try:
            user_submissions_key = f"{self.USER_SUBMISSIONS_KEY_PREFIX}:{problem_id}"
            await self.redis.redis_client.sadd(user_submissions_key, user_id)
            await self.redis.redis_client.expire(user_submissions_key, self.redis.PROBLEM_EXPIRY)
        except Exception as e:
            logger.error(f"Failed to mark user submitted: {e}")
    
    async def _mark_problem_solved(self, problem_id: str, winner_user_id: str, timestamp: datetime) -> None:
        """Mark problem as solved with winner information."""
        try:
            await self.redis.redis_client.sadd(self.SOLVED_PROBLEMS_KEY, problem_id)
            
            # Store winner information
            winner_key = f"quiz:winner:{problem_id}"
            winner_data = {
                'user_id': winner_user_id,
                'solved_at': timestamp.isoformat()
            }
            await self.redis.redis_client.setex(
                winner_key, 
                self.redis.PROBLEM_EXPIRY, 
                json.dumps(winner_data)
            )
            
        except Exception as e:
            logger.error(f"Failed to mark problem solved: {e}")
    
    async def _acquire_problem_lock(self, problem_id: str) -> bool:
        """
        Acquire distributed lock for problem processing.
        
        Returns:
            True if lock acquired, False otherwise
        """
        lock_key = f"{self.PROBLEM_LOCK_PREFIX}:{problem_id}"
        
        for attempt in range(self.MAX_LOCK_RETRIES):
            try:
                # Try to set lock with expiration (NX = only if not exists)
                acquired = await self.redis.redis_client.set(
                    lock_key, 
                    "locked", 
                    nx=True, 
                    ex=self.LOCK_TIMEOUT
                )
                
                if acquired:
                    return True
                
                # Wait before retry
                await asyncio.sleep(self.LOCK_RETRY_DELAY)
                
            except Exception as e:
                logger.error(f"Lock acquisition attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(self.LOCK_RETRY_DELAY)
        
        logger.warning(f"Failed to acquire lock for problem {problem_id} after {self.MAX_LOCK_RETRIES} attempts")
        return False
    
    async def _release_problem_lock(self, problem_id: str) -> None:
        """Release distributed lock for problem processing."""
        try:
            lock_key = f"{self.PROBLEM_LOCK_PREFIX}:{problem_id}"
            await self.redis.redis_client.delete(lock_key)
        except Exception as e:
            logger.error(f"Failed to release lock for problem {problem_id}: {e}")


# Import asyncio at the end to avoid circular imports
import asyncio