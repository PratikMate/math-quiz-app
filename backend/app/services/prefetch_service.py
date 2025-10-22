"""
Question prefetch service for batch AI generation.
"""
import asyncio
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from ..models.math_problem import MathProblem, DifficultyLevel
from .quiz_engine import QuizEngine
from .redis_service import RedisService

logger = logging.getLogger(__name__)


class PrefetchService:
    """
    Service for prefetching questions in batches to improve response times.
    """
    
    def __init__(self, quiz_engine: QuizEngine, redis_service: RedisService, settings=None):
        self.quiz_engine = quiz_engine
        self.redis_service = redis_service
        
        # Configuration from settings
        if settings:
            self.batch_size = settings.PREFETCH_BATCH_SIZE
            self.min_threshold = settings.PREFETCH_MIN_THRESHOLD
            self.enabled = settings.PREFETCH_ENABLED
        else:
            # Fallback to environment variables
            import os
            self.batch_size = int(os.getenv('PREFETCH_BATCH_SIZE', '20'))
            self.min_threshold = int(os.getenv('PREFETCH_MIN_THRESHOLD', '5'))
            self.enabled = os.getenv('PREFETCH_ENABLED', 'true').lower() == 'true'
        
        # Redis keys for prefetched questions
        self.prefetch_keys = {
            DifficultyLevel.EASY: "prefetch:questions:easy",
            DifficultyLevel.MEDIUM: "prefetch:questions:medium", 
            DifficultyLevel.HARD: "prefetch:questions:hard"
        }
        
        # Background task management
        self._prefetch_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
    async def start(self):
        """Start the prefetch service."""
        if not self.enabled:
            logger.info("Prefetch service disabled")
            return
            
        logger.info("Starting question prefetch service")
        
        # Initial prefetch for all difficulties
        await self._initial_prefetch()
        
        # Start background prefetch task
        self._prefetch_task = asyncio.create_task(self._prefetch_loop())
        
    async def stop(self):
        """Stop the prefetch service."""
        if self._prefetch_task:
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._prefetch_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._prefetch_task.cancel()
            logger.info("Prefetch service stopped")
    
    async def get_question(self, difficulty: DifficultyLevel) -> Optional[MathProblem]:
        """
        Get a prefetched question for the given difficulty.
        
        Args:
            difficulty: The difficulty level
            
        Returns:
            MathProblem if available, None if cache is empty
        """
        if not self.enabled:
            return None
            
        try:
            key = self.prefetch_keys[difficulty]
            
            # Get question from Redis list (LPOP removes and returns first item)
            question_data = await self.redis_service.redis_client.lpop(key)
            
            if question_data:
                import json
                data = json.loads(question_data)
                
                # Reconstruct MathProblem
                problem = MathProblem(
                    id=data['id'],
                    question=data['question'],
                    correct_answer=data['correct_answer'],
                    difficulty=DifficultyLevel(data['difficulty']),
                    created_at=datetime.fromisoformat(data['created_at'])
                )
                
                logger.info(f"Retrieved prefetched question for {difficulty.value}")
                
                # Trigger refill if below threshold
                await self._check_and_refill(difficulty)
                
                return problem
                
        except Exception as e:
            logger.error(f"Error retrieving prefetched question: {e}")
            
        return None
    
    async def _initial_prefetch(self):
        """Perform initial prefetch for all difficulty levels using mixed generation."""
        logger.info("Performing initial question prefetch with mixed generation")
        
        try:
            # Generate mixed problems in a single API call
            mixed_problems = await self.quiz_engine.gemini_service.generate_mixed_problems(
                total_count=self.batch_size
            )
            
            # Distribute problems by difficulty
            for problem_data in mixed_problems:
                try:
                    difficulty = DifficultyLevel(problem_data['difficulty'].lower())
                    
                    # Create MathProblem instance
                    problem = MathProblem(
                        question=problem_data['question'],
                        correct_answer=str(problem_data['answer']),
                        difficulty=difficulty
                    )
                    
                    # Store in Redis
                    key = self.prefetch_keys[difficulty]
                    question_data = json.dumps({
                        'id': str(problem.id),
                        'question': problem.question,
                        'correct_answer': problem.correct_answer,
                        'difficulty': problem.difficulty.value if hasattr(problem.difficulty, 'value') else str(problem.difficulty),
                        'created_at': problem.created_at.isoformat()
                    })
                    
                    await self.redis_service.redis_client.rpush(key, question_data)
                    await self.redis_service.redis_client.expire(key, 86400)  # 24 hours
                    
                except Exception as e:
                    logger.warning(f"Failed to process problem: {problem_data}, error: {e}")
                    continue
            
            logger.info(f"Initial prefetch completed with {len(mixed_problems)} mixed problems")
            
        except Exception as e:
            logger.error(f"Mixed prefetch failed, falling back to individual generation: {e}")
            # Fallback to original method
            await self._initial_prefetch_fallback()
    
    async def _initial_prefetch_fallback(self):
        """Fallback to original individual prefetch method."""
        logger.info("Using fallback individual prefetch")
        
        tasks = []
        for difficulty in DifficultyLevel:
            task = asyncio.create_task(self._prefetch_batch(difficulty))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Fallback prefetch completed")
    
    async def _prefetch_loop(self):
        """Background loop to maintain question cache."""
        while not self._stop_event.is_set():
            try:
                # Check all difficulty levels
                for difficulty in DifficultyLevel:
                    await self._check_and_refill(difficulty)
                
                # Wait before next check (30 seconds)
                await asyncio.wait_for(self._stop_event.wait(), timeout=30.0)
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                logger.error(f"Error in prefetch loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying
    
    async def _check_and_refill(self, difficulty: DifficultyLevel):
        """Check cache level and refill if needed."""
        try:
            key = self.prefetch_keys[difficulty]
            current_count = await self.redis_service.redis_client.llen(key)
            
            if current_count < self.min_threshold:
                logger.info(f"Refilling {difficulty.value} questions (current: {current_count})")
                await self._prefetch_batch(difficulty)
                
        except Exception as e:
            logger.error(f"Error checking cache for {difficulty.value}: {e}")
    
    async def _prefetch_batch(self, difficulty: DifficultyLevel):
        """Prefetch a batch of questions for the given difficulty."""
        try:
            key = self.prefetch_keys[difficulty]
            
            # Generate questions in smaller concurrent batches to avoid API limits
            batch_size = min(self.batch_size, 10)  # Limit concurrent requests
            questions = []
            
            # Generate in chunks of 5 to be API-friendly
            for i in range(0, batch_size, 5):
                chunk_size = min(5, batch_size - i)
                tasks = []
                
                for _ in range(chunk_size):
                    task = asyncio.create_task(
                        self.quiz_engine.generate_problem_with_ai(difficulty)
                    )
                    tasks.append(task)
                
                # Wait for chunk to complete
                chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Add successful results
                for result in chunk_results:
                    if isinstance(result, MathProblem):
                        questions.append(result)
                    else:
                        logger.warning(f"Failed to generate question: {result}")
                
                # Small delay between chunks to be API-friendly
                if i + chunk_size < batch_size:
                    await asyncio.sleep(1)
            
            # Store questions in Redis
            if questions:
                pipeline = self.redis_service.redis_client.pipeline()
                
                for question in questions:
                    import json
                    question_data = json.dumps({
                        'id': str(question.id),
                        'question': question.question,
                        'correct_answer': question.correct_answer,
                        'difficulty': question.difficulty.value if hasattr(question.difficulty, 'value') else str(question.difficulty),
                        'created_at': question.created_at.isoformat()
                    })
                    
                    pipeline.rpush(key, question_data)
                
                # Set expiration (24 hours)
                pipeline.expire(key, 86400)
                
                await pipeline.execute()
                
                logger.info(f"Prefetched {len(questions)} questions for {difficulty.value}")
            
        except Exception as e:
            logger.error(f"Error prefetching {difficulty.value} questions: {e}")
    
    async def get_cache_stats(self) -> Dict[str, int]:
        """Get current cache statistics."""
        stats = {}
        
        try:
            for difficulty in DifficultyLevel:
                key = self.prefetch_keys[difficulty]
                count = await self.redis_service.redis_client.llen(key)
                stats[difficulty.value] = count
                
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            
        return stats
