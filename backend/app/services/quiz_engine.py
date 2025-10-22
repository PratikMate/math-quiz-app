"""
Quiz engine service for managing math problem generation and validation.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from ..models.math_problem import (
    MathProblem, 
    AnswerSubmission, 
    AnswerValidationResult,
    DifficultyLevel,
    validate_answer
)
from .gemini_service import GeminiService, GeminiAPIError, GeminiRateLimitError


logger = logging.getLogger(__name__)


class QuizEngineError(Exception):
    """Custom exception for quiz engine errors."""
    pass


class QuizEngine:
    """
    Core quiz engine that manages math problem generation, validation, and caching.
    
    Handles AI-powered problem generation with fallback mechanisms,
    problem caching to reduce API calls, and answer validation.
    """
    
    def __init__(self, gemini_service: Optional[GeminiService] = None, prefetch_service=None):
        """
        Initialize quiz engine with Gemini service and prefetch service.
        
        Args:
            gemini_service: Optional GeminiService instance. If None, creates new one.
            prefetch_service: Optional PrefetchService for cached questions.
        """
        self.gemini_service = gemini_service or GeminiService()
        self.prefetch_service = prefetch_service
        
        # Problem cache to reduce API calls
        self._problem_cache: Dict[str, List[MathProblem]] = {
            difficulty.value: [] for difficulty in DifficultyLevel
        }
        
        # Cache configuration
        self.cache_size_per_difficulty = 10
        self.cache_refresh_threshold = 3  # Refresh when cache has 3 or fewer items
        
        # Fallback problems for when API fails
        self._fallback_problems = self._create_fallback_problems()
        
        # Recent problems tracking (to avoid duplicates)
        self._recent_problems: List[str] = []
        self.max_recent_problems = 10
        
        # Problem generation topics for variety
        self.math_topics = [
            "arithmetic",
            "algebra", 
            "fractions",
            "percentages",
            "geometry",
            "word problems"
        ]
    
    async def generate_problem_with_ai(
        self, 
        difficulty: DifficultyLevel,
        avoid_recent: bool = True,
        use_prefetch: bool = True
    ) -> MathProblem:
        """
        Generate a new math problem using AI with caching and fallback.
        
        Args:
            difficulty: The difficulty level for the problem
            avoid_recent: Whether to avoid recently generated problems
            use_prefetch: Whether to try prefetched questions first
            
        Returns:
            MathProblem instance
            
        Raises:
            QuizEngineError: If problem generation fails completely
        """
        # Try prefetched questions first for faster response
        if use_prefetch and self.prefetch_service:
            prefetched = await self.prefetch_service.get_question(difficulty)
            if prefetched and (not avoid_recent or prefetched.question not in self._recent_problems):
                await self._track_recent_problem(prefetched.question)
                return prefetched
        
        # Try to get from cache
        cached_problem = await self._get_cached_problem(difficulty, avoid_recent)
        if cached_problem:
            return cached_problem
        
        # Generate new problem with AI
        try:
            ai_problem = await self._generate_ai_problem(difficulty)
            
            # Validate the AI-generated problem
            if await self._validate_ai_problem(ai_problem):
                # Add to cache
                await self._add_to_cache(ai_problem)
                return ai_problem
            else:
                logger.warning("AI-generated problem failed validation, using fallback")
                
        except (GeminiAPIError, GeminiRateLimitError) as e:
            logger.error(f"AI problem generation failed: {e}")
        
        # Fallback to pre-defined problems
        fallback_problem = self._get_fallback_problem(difficulty, avoid_recent)
        if fallback_problem:
            return fallback_problem
        
        raise QuizEngineError(f"Failed to generate problem for difficulty {difficulty}")
    
    async def validate_answer(self, problem_id: UUID, submitted_answer: Any) -> AnswerValidationResult:
        """
        Validate a user's answer against the correct answer.
        
        Args:
            problem_id: ID of the problem being answered
            submitted_answer: The user's submitted answer
            
        Returns:
            AnswerValidationResult with validation details
            
        Raises:
            QuizEngineError: If problem not found or validation fails
        """
        # Find the problem (in a real implementation, this would query the database)
        problem = await self._find_problem_by_id(problem_id)
        if not problem:
            raise QuizEngineError(f"Problem with ID {problem_id} not found")
        
        try:
            # Create submission object for validation
            submission = AnswerSubmission(
                user_id=UUID('00000000-0000-0000-0000-000000000000'),  # Placeholder
                problem_id=problem_id,
                submitted_answer=submitted_answer
            )
            
            # Validate the answer
            result = validate_answer(submission, problem)
            
            # Track recent problems if answer is correct
            if result.is_correct:
                await self._track_recent_problem(problem.question)
            
            return result
            
        except Exception as e:
            logger.error(f"Answer validation failed: {e}")
            raise QuizEngineError(f"Answer validation failed: {e}")
    
    async def get_current_problem(self) -> Optional[MathProblem]:
        """
        Get the current active problem.
        
        In a full implementation, this would retrieve from Redis or database.
        For now, returns None as placeholder.
        
        Returns:
            Current MathProblem or None if no active problem
        """
        # Placeholder - in real implementation, get from Redis/database
        return None
    
    async def rotate_question(self, current_difficulty: Optional[DifficultyLevel] = None) -> MathProblem:
        """
        Generate a new problem for question rotation.
        
        Args:
            current_difficulty: Current difficulty level, or None for random
            
        Returns:
            New MathProblem for the next round
        """
        # Choose difficulty (random if not specified)
        if current_difficulty is None:
            difficulty = random.choice(list(DifficultyLevel))
        else:
            difficulty = current_difficulty
        
        # Generate new problem
        new_problem = await self.generate_problem_with_ai(difficulty)
        
        # Refresh cache in background if needed
        asyncio.create_task(self._refresh_cache_if_needed(difficulty))
        
        return new_problem
    
    async def _generate_ai_problem(self, difficulty: DifficultyLevel) -> MathProblem:
        """
        Generate a problem using AI service.
        
        Args:
            difficulty: The difficulty level
            
        Returns:
            MathProblem instance
        """
        # Choose random topic for variety
        topic = random.choice(self.math_topics) if random.random() < 0.7 else None
        
        # Generate with Gemini
        ai_response = await self.gemini_service.generate_math_problem(difficulty, topic)
        
        # Create MathProblem instance
        problem = MathProblem(
            question=ai_response['question'],
            correct_answer=str(ai_response['answer']),  # Convert to string
            difficulty=difficulty
        )
        
        return problem
    
    def _generate_basic_problem(self, difficulty: DifficultyLevel) -> MathProblem:
        """Generate a basic math problem without AI."""
        import random
        from uuid import uuid4
        from datetime import datetime
        
        if difficulty == DifficultyLevel.EASY:
            a, b = random.randint(1, 10), random.randint(1, 10)
            operation = random.choice(['+', '-'])
        elif difficulty == DifficultyLevel.MEDIUM:
            a, b = random.randint(10, 50), random.randint(1, 20)
            operation = random.choice(['+', '-', '*'])
        else:  # HARD
            a, b = random.randint(20, 100), random.randint(2, 15)
            operation = random.choice(['+', '-', '*'])
        
        if operation == '+':
            answer = a + b
            question = f"What is {a} + {b}?"
        elif operation == '-':
            if a < b:
                a, b = b, a  # Ensure positive result
            answer = a - b
            question = f"What is {a} - {b}?"
        else:  # multiplication
            answer = a * b
            question = f"What is {a} × {b}?"
        
        return MathProblem(
            id=uuid4(),
            question=question,
            correct_answer=str(answer),
            difficulty=difficulty,
            created_at=datetime.now()
        )
    
    async def _validate_ai_problem(self, problem: MathProblem) -> bool:
        """
        Validate an AI-generated problem for quality and correctness.
        
        Args:
            problem: The MathProblem to validate
            
        Returns:
            True if problem is valid, False otherwise
        """
        try:
            # Check if problem is too similar to recent ones
            if problem.question in self._recent_problems:
                logger.info("Problem too similar to recent problem")
                return False
            
            # Basic validation is already done by Pydantic model
            # Additional validation could include:
            # - Checking if the problem makes mathematical sense
            # - Verifying the answer by attempting to solve it
            # - Ensuring appropriate difficulty level
            
            return True
            
        except Exception as e:
            logger.error(f"Problem validation failed: {e}")
            return False
    
    async def _get_cached_problem(
        self, 
        difficulty: DifficultyLevel, 
        avoid_recent: bool = True
    ) -> Optional[MathProblem]:
        """
        Get a problem from cache if available.
        
        Args:
            difficulty: The difficulty level
            avoid_recent: Whether to avoid recently used problems
            
        Returns:
            Cached MathProblem or None if cache is empty
        """
        difficulty_key = difficulty if isinstance(difficulty, str) else difficulty.value
        cache = self._problem_cache[difficulty_key]
        
        if not cache:
            return None
        
        if avoid_recent:
            # Filter out recent problems
            available_problems = [
                p for p in cache 
                if p.question not in self._recent_problems
            ]
            if available_problems:
                problem = available_problems.pop(0)
                cache.remove(problem)
                return problem
        
        # Return any cached problem if no filtering or no non-recent problems
        if cache:
            return cache.pop(0)
        
        return None
    
    async def _add_to_cache(self, problem: MathProblem) -> None:
        """
        Add a problem to the cache.
        
        Args:
            problem: The MathProblem to cache
        """
        difficulty_key = problem.difficulty if isinstance(problem.difficulty, str) else problem.difficulty.value
        cache = self._problem_cache[difficulty_key]
        
        # Add to cache if not full
        if len(cache) < self.cache_size_per_difficulty:
            cache.append(problem)
    
    async def _refresh_cache_if_needed(self, difficulty: DifficultyLevel) -> None:
        """
        Refresh cache if it's running low on problems.
        
        Args:
            difficulty: The difficulty level to refresh
        """
        difficulty_key = difficulty if isinstance(difficulty, str) else difficulty.value
        cache = self._problem_cache[difficulty_key]
        
        if len(cache) <= self.cache_refresh_threshold:
            logger.info(f"Refreshing cache for difficulty {difficulty.value}")
            
            # Generate multiple problems to refill cache
            tasks = []
            problems_to_generate = self.cache_size_per_difficulty - len(cache)
            
            for _ in range(min(problems_to_generate, 5)):  # Limit concurrent generations
                task = asyncio.create_task(self._generate_ai_problem(difficulty))
                tasks.append(task)
            
            try:
                new_problems = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in new_problems:
                    if isinstance(result, MathProblem):
                        await self._add_to_cache(result)
                    else:
                        logger.warning(f"Failed to generate cache problem: {result}")
                        
            except Exception as e:
                logger.error(f"Cache refresh failed: {e}")
    
    async def _track_recent_problem(self, question: str) -> None:
        """
        Track a problem as recently used.
        
        Args:
            question: The question text to track
        """
        self._recent_problems.append(question)
        
        # Keep only the most recent problems
        if len(self._recent_problems) > self.max_recent_problems:
            self._recent_problems.pop(0)
    
    def _get_fallback_problem(
        self, 
        difficulty: DifficultyLevel, 
        avoid_recent: bool = True
    ) -> Optional[MathProblem]:
        """
        Get a fallback problem when AI generation fails.
        
        Args:
            difficulty: The difficulty level
            avoid_recent: Whether to avoid recently used problems
            
        Returns:
            Fallback MathProblem or None if none available
        """
        difficulty_key = difficulty if isinstance(difficulty, str) else difficulty.value
        fallback_problems = self._fallback_problems.get(difficulty_key, [])
        
        if avoid_recent:
            available_problems = [
                p for p in fallback_problems 
                if p.question not in self._recent_problems
            ]
            if available_problems:
                return random.choice(available_problems)
        
        if fallback_problems:
            return random.choice(fallback_problems)
        
        return None
    
    def _create_fallback_problems(self) -> Dict[str, List[MathProblem]]:
        """
        Create a set of fallback problems for when AI generation fails.
        
        Returns:
            Dictionary mapping difficulty to list of problems
        """
        fallback_problems = {
            DifficultyLevel.EASY.value: [
                MathProblem(question="What is 15 + 27?", correct_answer="42", difficulty=DifficultyLevel.EASY),
                MathProblem(question="What is 8 × 7?", correct_answer="56", difficulty=DifficultyLevel.EASY),
                MathProblem(question="What is 100 - 37?", correct_answer="63", difficulty=DifficultyLevel.EASY),
                MathProblem(question="What is 84 ÷ 12?", correct_answer="7", difficulty=DifficultyLevel.EASY),
                MathProblem(question="What is 25 + 18?", correct_answer="43", difficulty=DifficultyLevel.EASY),
            ],
            DifficultyLevel.MEDIUM.value: [
                MathProblem(question="If 3x + 7 = 22, what is x?", correct_answer="5", difficulty=DifficultyLevel.MEDIUM),
                MathProblem(question="What is 15% of 240?", correct_answer="36", difficulty=DifficultyLevel.MEDIUM),
                MathProblem(question="What is 2³ + 4²?", correct_answer="24", difficulty=DifficultyLevel.MEDIUM),
                MathProblem(question="If a rectangle has length 12 and width 8, what is its area?", correct_answer="96", difficulty=DifficultyLevel.MEDIUM),
                MathProblem(question="What is 7 × 13 - 25?", correct_answer="66", difficulty=DifficultyLevel.MEDIUM),
            ],
            DifficultyLevel.HARD.value: [
                MathProblem(question="If x² - 5x + 6 = 0, what is the sum of all solutions?", correct_answer="5", difficulty=DifficultyLevel.HARD),
                MathProblem(question="What is the value of log₂(64)?", correct_answer="6", difficulty=DifficultyLevel.HARD),
                MathProblem(question="If 2x + 3y = 12 and x - y = 1, what is x?", correct_answer="3", difficulty=DifficultyLevel.HARD),
                MathProblem(question="What is the derivative of x³ + 2x² - 5x + 3 at x = 2?", correct_answer="15", difficulty=DifficultyLevel.HARD),
                MathProblem(question="What is the area of a circle with radius 5? Use π ≈ 3.14159.", correct_answer="78.54", difficulty=DifficultyLevel.HARD),
            ]
        }
        
        return fallback_problems
    
    async def _find_problem_by_id(self, problem_id: UUID) -> Optional[MathProblem]:
        """
        Find a problem by its ID.
        
        This is a placeholder implementation. In a real system, this would
        query the database or Redis cache.
        
        Args:
            problem_id: The problem ID to find
            
        Returns:
            MathProblem if found, None otherwise
        """
        # For now, we'll need to get the current problem from the quiz state
        # This is a temporary solution until we implement proper storage
        return None