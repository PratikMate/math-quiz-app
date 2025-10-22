"""
Unit tests for SubmissionProcessor service.
"""
import pytest
from datetime import datetime
from uuid import uuid4

from app.services.submission_processor import SubmissionProcessor, SubmissionResult
from app.models.math_problem import MathProblem, DifficultyLevel


class TestSubmissionProcessor:
    """Test SubmissionProcessor answer handling and winner detection."""
    
    @pytest.fixture
    def processor(self):
        """Create a SubmissionProcessor instance."""
        return SubmissionProcessor()
    
    @pytest.fixture
    def sample_problem(self):
        """Create a sample problem for testing."""
        return MathProblem(
            id=uuid4(),
            question="What is 10 + 15?",
            correct_answer=25.0,
            difficulty=DifficultyLevel.EASY
        )
    
    @pytest.mark.asyncio
    async def test_correct_answer_submission(self, processor, sample_problem):
        """Test processing a correct answer submission."""
        user_id = "user123"
        
        result = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        
        assert isinstance(result, SubmissionResult)
        assert result.user_id == user_id
        assert result.is_correct is True
        assert result.is_winner is True
        assert result.validation_result.is_correct is True
        assert "Congratulations" in result.message
    
    @pytest.mark.asyncio
    async def test_incorrect_answer_submission(self, processor, sample_problem):
        """Test processing an incorrect answer submission."""
        user_id = "user123"
        
        result = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=30.0
        )
        
        assert isinstance(result, SubmissionResult)
        assert result.user_id == user_id
        assert result.is_correct is False
        assert result.is_winner is False
        assert result.validation_result.is_correct is False
        assert "Incorrect" in result.message
    
    @pytest.mark.asyncio
    async def test_duplicate_submission_prevention(self, processor, sample_problem):
        """Test prevention of duplicate submissions from same user."""
        user_id = "user123"
        
        # First submission
        result1 = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        assert result1.is_winner is True
        
        # Second submission from same user
        result2 = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        
        assert result2.is_correct is False
        assert result2.is_winner is False
        assert "already submitted" in result2.message
    
    @pytest.mark.asyncio
    async def test_problem_already_solved(self, processor, sample_problem):
        """Test submission to already solved problem."""
        user1_id = "user1"
        user2_id = "user2"
        
        # First user solves the problem
        result1 = await processor.process_submission(
            user_id=user1_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        assert result1.is_winner is True
        
        # Second user tries to submit
        result2 = await processor.process_submission(
            user_id=user2_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        
        assert result2.is_correct is False
        assert result2.is_winner is False
        assert "already been solved" in result2.message
    
    @pytest.mark.asyncio
    async def test_concurrent_submissions_winner_detection(self, processor, sample_problem):
        """Test winner detection with multiple concurrent correct submissions."""
        user1_id = "user1"
        user2_id = "user2"
        user3_id = "user3"
        
        # Simulate concurrent submissions (first correct answer wins)
        result1 = await processor.process_submission(
            user_id=user1_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        
        result2 = await processor.process_submission(
            user_id=user2_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        
        result3 = await processor.process_submission(
            user_id=user3_id,
            problem=sample_problem,
            submitted_answer=30.0  # Incorrect
        )
        
        # First correct submission should win
        assert result1.is_winner is True
        assert result1.is_correct is True
        
        # Second correct submission should not win (problem already solved)
        assert result2.is_winner is False
        assert "already been solved" in result2.message
        
        # Incorrect submission should not win
        assert result3.is_winner is False
        assert result3.is_correct is False
    
    @pytest.mark.asyncio
    async def test_server_side_timestamping(self, processor, sample_problem):
        """Test that submissions are timestamped on server side."""
        user_id = "user123"
        
        before_submission = datetime.utcnow()
        
        result = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=25.0
        )
        
        after_submission = datetime.utcnow()
        
        # Server timestamp should be between before and after
        assert before_submission <= result.server_timestamp <= after_submission
    
    @pytest.mark.asyncio
    async def test_invalid_submission_format(self, processor, sample_problem):
        """Test handling of invalid submission formats."""
        user_id = "user123"
        
        # Test with invalid answer format
        result = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer="not a number"
        )
        
        assert result.is_correct is False
        assert result.is_winner is False
        assert "Invalid submission format" in result.message
    
    def test_get_problem_submissions(self, processor, sample_problem):
        """Test retrieving submissions for a problem."""
        problem_id = str(sample_problem.id)
        
        # Initially no submissions
        submissions = processor.get_problem_submissions(problem_id)
        assert len(submissions) == 0
        
        # After processing submissions, should be able to retrieve them
        # This would be tested with actual submissions in integration tests
    
    def test_get_winner(self, processor, sample_problem):
        """Test retrieving winner for a problem."""
        problem_id = str(sample_problem.id)
        
        # Initially no winner
        winner = processor.get_winner(problem_id)
        assert winner is None
        
        # After a winning submission, should be able to retrieve winner
        # This would be tested with actual submissions in integration tests
    
    def test_is_problem_solved(self, processor, sample_problem):
        """Test checking if problem is solved."""
        problem_id = str(sample_problem.id)
        
        # Initially not solved
        assert processor.is_problem_solved(problem_id) is False
        
        # After solving, should return True
        # This would be tested with actual submissions in integration tests
    
    def test_reset_problem_state(self, processor, sample_problem):
        """Test resetting problem state for question rotation."""
        problem_id = str(sample_problem.id)
        
        # Reset state (should not raise errors)
        processor.reset_problem_state(problem_id)
        
        # After reset, problem should not be solved
        assert processor.is_problem_solved(problem_id) is False
        
        # Submissions should be cleared
        submissions = processor.get_problem_submissions(problem_id)
        assert len(submissions) == 0
    
    def test_get_submission_stats(self, processor):
        """Test getting submission statistics."""
        stats = processor.get_submission_stats()
        
        assert isinstance(stats, dict)
        assert "total_submissions" in stats
        assert "solved_problems" in stats
        assert "active_problems" in stats
        assert "problems_with_submissions" in stats
        
        # Initially all should be zero
        assert stats["total_submissions"] == 0
        assert stats["solved_problems"] == 0
        assert stats["active_problems"] == 0
        assert stats["problems_with_submissions"] == 0
    
    @pytest.mark.asyncio
    async def test_submission_result_properties(self, processor, sample_problem):
        """Test SubmissionResult object properties."""
        user_id = "user123"
        submission_id = "test_submission_123"
        
        result = await processor.process_submission(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=25.0,
            submission_id=submission_id
        )
        
        # Check all properties are set correctly
        assert result.submission_id == submission_id
        assert result.user_id == user_id
        assert isinstance(result.server_timestamp, datetime)
        assert result.validation_result is not None
        assert isinstance(result.message, str)
        assert isinstance(result.is_correct, bool)
        assert isinstance(result.is_winner, bool)
    
    @pytest.mark.asyncio
    async def test_multiple_problems_isolation(self, processor):
        """Test that submissions to different problems are isolated."""
        # Create two different problems
        problem1 = MathProblem(
            id=uuid4(),
            question="What is 5 + 5?",
            correct_answer=10.0,
            difficulty=DifficultyLevel.EASY
        )
        
        problem2 = MathProblem(
            id=uuid4(),
            question="What is 3 × 4?",
            correct_answer=12.0,
            difficulty=DifficultyLevel.EASY
        )
        
        user_id = "user123"
        
        # Submit to first problem
        result1 = await processor.process_submission(
            user_id=user_id,
            problem=problem1,
            submitted_answer=10.0
        )
        
        # Submit to second problem (should be allowed)
        result2 = await processor.process_submission(
            user_id=user_id,
            problem=problem2,
            submitted_answer=12.0
        )
        
        # Both should be winners of their respective problems
        assert result1.is_winner is True
        assert result2.is_winner is True
        
        # Problems should be independently solved
        assert processor.is_problem_solved(str(problem1.id)) is True
        assert processor.is_problem_solved(str(problem2.id)) is True