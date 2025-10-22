"""
Unit tests for QuizEngine service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.quiz_engine import QuizEngine, QuizEngineError
from app.services.gemini_service import GeminiService, GeminiAPIError
from app.models.math_problem import MathProblem, DifficultyLevel, AnswerSubmission


class TestQuizEngine:
    """Test QuizEngine problem generation and validation."""
    
    @pytest.fixture
    def mock_gemini_service(self):
        """Create mock Gemini service."""
        service = MagicMock(spec=GeminiService)
        service.generate_math_problem = AsyncMock()
        return service
    
    def test_engine_initialization(self, mock_gemini_service):
        """Test quiz engine initialization."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        assert engine.gemini_service == mock_gemini_service
        assert len(engine._problem_cache) == 3  # One for each difficulty
        assert len(engine._fallback_problems) == 3
    
    @pytest.mark.asyncio
    async def test_successful_ai_problem_generation(self, mock_gemini_service):
        """Test successful AI problem generation."""
        # Mock AI response
        mock_gemini_service.generate_math_problem.return_value = {
            'question': 'What is 12 × 8?',
            'answer': 96.0
        }
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        problem = await engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        assert isinstance(problem, MathProblem)
        assert problem.question == 'What is 12 × 8?'
        assert problem.correct_answer == 96.0
        assert problem.difficulty == DifficultyLevel.EASY
        
        # Verify AI service was called
        mock_gemini_service.generate_math_problem.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ai_failure_fallback(self, mock_gemini_service):
        """Test fallback to pre-defined problems when AI fails."""
        # Mock AI failure
        mock_gemini_service.generate_math_problem.side_effect = GeminiAPIError("API failed")
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        problem = await engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        assert isinstance(problem, MathProblem)
        assert problem.difficulty == DifficultyLevel.EASY
        # Should be one of the fallback problems
        assert problem.question in [p.question for p in engine._fallback_problems[DifficultyLevel.EASY.value]]
    
    @pytest.mark.asyncio
    async def test_problem_caching(self, mock_gemini_service):
        """Test problem caching functionality."""
        # Mock AI response
        mock_gemini_service.generate_math_problem.return_value = {
            'question': 'What is 5 + 7?',
            'answer': 12.0
        }
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Generate first problem (should call AI)
        problem1 = await engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        # Add to cache manually for testing
        await engine._add_to_cache(problem1)
        
        # Generate second problem (should use cache)
        problem2 = await engine._get_cached_problem(DifficultyLevel.EASY, avoid_recent=False)
        
        assert problem2 is not None
        assert problem2.question == problem1.question
    
    @pytest.mark.asyncio
    async def test_recent_problem_avoidance(self, mock_gemini_service):
        """Test avoiding recently generated problems."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Track a recent problem
        recent_question = "What is 2 + 2?"
        await engine._track_recent_problem(recent_question)
        
        # Create a problem with the same question
        recent_problem = MathProblem(
            question=recent_question,
            correct_answer=4.0,
            difficulty=DifficultyLevel.EASY
        )
        
        # Add to cache
        await engine._add_to_cache(recent_problem)
        
        # Try to get cached problem avoiding recent ones
        cached_problem = await engine._get_cached_problem(DifficultyLevel.EASY, avoid_recent=True)
        
        # Should not return the recent problem
        assert cached_problem is None or cached_problem.question != recent_question
    
    @pytest.mark.asyncio
    async def test_answer_validation_correct(self, mock_gemini_service, sample_easy_problem):
        """Test correct answer validation."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Mock finding the problem
        engine._find_problem_by_id = AsyncMock(return_value=sample_easy_problem)
        
        result = await engine.validate_answer(sample_easy_problem.id, 42.0)
        
        assert result.is_correct is True
        assert result.submitted_value == 42.0
        assert result.correct_value == 42.0
    
    @pytest.mark.asyncio
    async def test_answer_validation_incorrect(self, mock_gemini_service, sample_easy_problem):
        """Test incorrect answer validation."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Mock finding the problem
        engine._find_problem_by_id = AsyncMock(return_value=sample_easy_problem)
        
        result = await engine.validate_answer(sample_easy_problem.id, 50.0)
        
        assert result.is_correct is False
        assert result.submitted_value == 50.0
        assert result.correct_value == 42.0
    
    @pytest.mark.asyncio
    async def test_answer_validation_problem_not_found(self, mock_gemini_service):
        """Test answer validation when problem not found."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Mock problem not found
        engine._find_problem_by_id = AsyncMock(return_value=None)
        
        with pytest.raises(QuizEngineError, match="Problem with ID .* not found"):
            await engine.validate_answer(uuid4(), 42.0)
    
    @pytest.mark.asyncio
    async def test_question_rotation(self, mock_gemini_service):
        """Test question rotation functionality."""
        # Mock AI response
        mock_gemini_service.generate_math_problem.return_value = {
            'question': 'What is 9 × 7?',
            'answer': 63.0
        }
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        new_problem = await engine.rotate_question(DifficultyLevel.MEDIUM)
        
        assert isinstance(new_problem, MathProblem)
        assert new_problem.difficulty == DifficultyLevel.MEDIUM
        
        # Verify AI service was called
        mock_gemini_service.generate_math_problem.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_question_rotation_random_difficulty(self, mock_gemini_service):
        """Test question rotation with random difficulty selection."""
        # Mock AI response
        mock_gemini_service.generate_math_problem.return_value = {
            'question': 'Random difficulty problem?',
            'answer': 100.0
        }
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        new_problem = await engine.rotate_question()  # No difficulty specified
        
        assert isinstance(new_problem, MathProblem)
        assert new_problem.difficulty in [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]
    
    def test_fallback_problems_creation(self, mock_gemini_service):
        """Test creation of fallback problems."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        fallback_problems = engine._fallback_problems
        
        # Should have problems for each difficulty
        assert DifficultyLevel.EASY.value in fallback_problems
        assert DifficultyLevel.MEDIUM.value in fallback_problems
        assert DifficultyLevel.HARD.value in fallback_problems
        
        # Each difficulty should have multiple problems
        for difficulty in DifficultyLevel:
            problems = fallback_problems[difficulty.value]
            assert len(problems) >= 3  # At least 3 fallback problems per difficulty
            
            for problem in problems:
                assert isinstance(problem, MathProblem)
                assert problem.difficulty == difficulty
    
    def test_get_fallback_problem(self, mock_gemini_service):
        """Test getting fallback problems."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Get fallback problem for each difficulty
        for difficulty in DifficultyLevel:
            problem = engine._get_fallback_problem(difficulty, avoid_recent=False)
            
            assert problem is not None
            assert isinstance(problem, MathProblem)
            assert problem.difficulty == difficulty
    
    def test_get_fallback_problem_avoid_recent(self, mock_gemini_service):
        """Test getting fallback problems while avoiding recent ones."""
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Get a fallback problem
        problem = engine._get_fallback_problem(DifficultyLevel.EASY, avoid_recent=False)
        
        # Mark it as recent
        engine._recent_problems.append(problem.question)
        
        # Try to get another problem avoiding recent ones
        new_problem = engine._get_fallback_problem(DifficultyLevel.EASY, avoid_recent=True)
        
        # Should get a different problem or None if all are recent
        if new_problem is not None:
            assert new_problem.question != problem.question
    
    @pytest.mark.asyncio
    async def test_cache_refresh_mechanism(self, mock_gemini_service):
        """Test automatic cache refresh when running low."""
        # Mock AI response
        mock_gemini_service.generate_math_problem.return_value = {
            'question': 'Cache refresh test?',
            'answer': 1.0
        }
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Manually trigger cache refresh
        await engine._refresh_cache_if_needed(DifficultyLevel.EASY)
        
        # Should have called AI service to generate new problems
        assert mock_gemini_service.generate_math_problem.called
    
    @pytest.mark.asyncio
    async def test_ai_problem_validation_failure(self, mock_gemini_service):
        """Test handling of AI problems that fail validation."""
        # Mock AI response that will fail validation
        mock_gemini_service.generate_math_problem.return_value = {
            'question': 'Invalid',  # Too short, no numbers
            'answer': 1.0
        }
        
        engine = QuizEngine(gemini_service=mock_gemini_service)
        
        # Should fall back to pre-defined problems
        problem = await engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        assert isinstance(problem, MathProblem)
        # Should be a fallback problem, not the invalid AI-generated one
        assert problem.question != 'Invalid'