"""
Unit tests for ConcurrencyManager Redis-based operations.
"""
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.concurrency_manager import ConcurrencyManager, SubmissionResult
from app.models.math_problem import MathProblem, DifficultyLevel


class TestConcurrencyManager:
    """Test ConcurrencyManager Redis-based concurrency control."""
    
    @pytest_asyncio.fixture
    async def concurrency_manager(self, redis_service):
        """Create ConcurrencyManager with fake Redis."""
        return ConcurrencyManager(redis_service)
    
    @pytest.fixture
    def sample_problem(self):
        """Create a sample problem for testing."""
        return MathProblem(
            id=uuid4(),
            question="What is 8 × 7?",
            correct_answer=56.0,
            difficulty=DifficultyLevel.EASY
        )
    
    @pytest.mark.asyncio
    async def test_first_correct_submission_wins(self, concurrency_manager, sample_problem):
        """Test that first correct submission wins."""
        user_id = "user1"
        
        result = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        assert isinstance(result, SubmissionResult)
        assert result.user_id == user_id
        assert result.is_correct is True
        assert result.is_winner is True
        assert result.rank == 1
        assert "Congratulations" in result.message
    
    @pytest.mark.asyncio
    async def test_incorrect_submission(self, concurrency_manager, sample_problem):
        """Test incorrect answer submission."""
        user_id = "user1"
        
        result = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=50.0  # Incorrect
        )
        
        assert result.is_correct is False
        assert result.is_winner is False
        assert result.rank is None
        assert "Incorrect" in result.message
    
    @pytest.mark.asyncio
    async def test_duplicate_submission_prevention(self, concurrency_manager, sample_problem):
        """Test prevention of duplicate submissions."""
        user_id = "user1"
        
        # First submission
        result1 = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        assert result1.is_winner is True
        
        # Second submission from same user
        result2 = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        assert result2.is_correct is False
        assert result2.is_winner is False
        assert "already submitted" in result2.message
    
    @pytest.mark.asyncio
    async def test_problem_already_solved(self, concurrency_manager, sample_problem):
        """Test submission to already solved problem."""
        user1_id = "user1"
        user2_id = "user2"
        
        # First user solves
        result1 = await concurrency_manager.submit_answer(
            user_id=user1_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        assert result1.is_winner is True
        
        # Second user tries to submit
        result2 = await concurrency_manager.submit_answer(
            user_id=user2_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        assert result2.is_correct is False
        assert result2.is_winner is False
        assert "already been solved" in result2.message
    
    @pytest.mark.asyncio
    async def test_concurrent_correct_submissions_ranking(self, concurrency_manager, sample_problem):
        """Test ranking of concurrent correct submissions."""
        # Simulate multiple users submitting correct answers
        users = ["user1", "user2", "user3"]
        results = []
        
        # Submit answers concurrently (in practice, these would have slight timing differences)
        for i, user_id in enumerate(users):
            # Add small delay to simulate timing differences
            if i > 0:
                await asyncio.sleep(0.001)
            
            result = await concurrency_manager.submit_answer(
                user_id=user_id,
                problem=sample_problem,
                submitted_answer=56.0
            )
            results.append(result)
        
        # First submission should win
        assert results[0].is_winner is True
        assert results[0].rank == 1
        
        # Subsequent submissions should not win (problem already solved)
        for result in results[1:]:
            assert result.is_winner is False
    
    @pytest.mark.asyncio
    async def test_server_side_timestamping(self, concurrency_manager, sample_problem):
        """Test server-side timestamping for fair timing."""
        user_id = "user1"
        
        before_submission = datetime.utcnow()
        
        result = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        after_submission = datetime.utcnow()
        
        # Server timestamp should be between before and after
        assert before_submission <= result.server_timestamp <= after_submission
    
    @pytest.mark.asyncio
    async def test_redis_submission_storage(self, concurrency_manager, sample_problem):
        """Test that submissions are stored in Redis."""
        user_id = "user1"
        problem_id = str(sample_problem.id)
        
        await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        # Check that submission was stored
        submissions_key = f"{concurrency_manager.SUBMISSIONS_KEY_PREFIX}:{problem_id}"
        stored_data = await concurrency_manager.redis.redis_client.hget(submissions_key, user_id)
        
        assert stored_data is not None
        
        import json
        submission_info = json.loads(stored_data)
        assert submission_info['is_correct'] is True
        assert submission_info['submitted_answer'] == 56.0
    
    @pytest.mark.asyncio
    async def test_correct_submissions_sorted_set(self, concurrency_manager, sample_problem):
        """Test that correct submissions are stored in sorted set by timestamp."""
        user_id = "user1"
        problem_id = str(sample_problem.id)
        
        await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        # Check correct submissions sorted set
        correct_key = f"{concurrency_manager.CORRECT_SUBMISSIONS_KEY_PREFIX}:{problem_id}"
        rank = await concurrency_manager.redis.redis_client.zrank(correct_key, user_id)
        
        assert rank == 0  # First (and only) correct submission
    
    @pytest.mark.asyncio
    async def test_user_submission_tracking(self, concurrency_manager, sample_problem):
        """Test tracking of users who have submitted."""
        user_id = "user1"
        problem_id = str(sample_problem.id)
        
        await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        # Check user submissions set
        user_submissions_key = f"{concurrency_manager.USER_SUBMISSIONS_KEY_PREFIX}:{problem_id}"
        is_member = await concurrency_manager.redis.redis_client.sismember(user_submissions_key, user_id)
        
        assert is_member is True
    
    @pytest.mark.asyncio
    async def test_solved_problems_tracking(self, concurrency_manager, sample_problem):
        """Test tracking of solved problems."""
        user_id = "user1"
        problem_id = str(sample_problem.id)
        
        await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        # Check solved problems set
        is_solved = await concurrency_manager.redis.redis_client.sismember(
            concurrency_manager.SOLVED_PROBLEMS_KEY, problem_id
        )
        
        assert is_solved is True
    
    @pytest.mark.asyncio
    async def test_get_problem_winner(self, concurrency_manager, sample_problem):
        """Test retrieving problem winner."""
        user_id = "winner_user"
        
        # Submit winning answer
        await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        # Get winner information
        winner_info = await concurrency_manager.get_problem_winner(str(sample_problem.id))
        
        assert winner_info is not None
        assert winner_info['user_id'] == user_id
        assert isinstance(winner_info['timestamp'], datetime)
    
    @pytest.mark.asyncio
    async def test_get_problem_submissions(self, concurrency_manager, sample_problem):
        """Test retrieving all submissions for a problem."""
        users = ["user1", "user2", "user3"]
        answers = [56.0, 50.0, 56.0]  # Correct, incorrect, correct
        
        # Submit multiple answers
        for user_id, answer in zip(users, answers):
            await concurrency_manager.submit_answer(
                user_id=user_id,
                problem=sample_problem,
                submitted_answer=answer
            )
        
        # Get all submissions
        submissions = await concurrency_manager.get_problem_submissions(str(sample_problem.id))
        
        assert len(submissions) == 3
        
        # Should be ordered by timestamp
        for submission in submissions:
            assert 'user_id' in submission
            assert 'timestamp' in submission
            assert 'is_correct' in submission
            assert 'submitted_answer' in submission
    
    @pytest.mark.asyncio
    async def test_reset_problem_state(self, concurrency_manager, sample_problem):
        """Test resetting problem state for question rotation."""
        user_id = "user1"
        problem_id = str(sample_problem.id)
        
        # Submit answer to create state
        await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        
        # Verify problem is solved
        assert await concurrency_manager._is_problem_solved(problem_id) is True
        
        # Reset state
        success = await concurrency_manager.reset_problem_state(problem_id)
        assert success is True
        
        # Verify state is cleared
        assert await concurrency_manager._is_problem_solved(problem_id) is False
        
        # Should be able to submit again
        result = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer=56.0
        )
        assert result.is_winner is True
    
    @pytest.mark.asyncio
    async def test_submission_stats(self, concurrency_manager, sample_problem):
        """Test getting submission statistics."""
        # Submit some answers
        await concurrency_manager.submit_answer("user1", sample_problem, 56.0)
        await concurrency_manager.submit_answer("user2", sample_problem, 50.0)
        
        stats = await concurrency_manager.get_submission_stats()
        
        assert isinstance(stats, dict)
        assert "solved_problems" in stats
        assert "active_problems" in stats
        assert "redis_connected" in stats
        
        assert stats["solved_problems"] >= 1  # At least one solved
    
    @pytest.mark.asyncio
    async def test_invalid_answer_format_handling(self, concurrency_manager, sample_problem):
        """Test handling of invalid answer formats."""
        user_id = "user1"
        
        result = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=sample_problem,
            submitted_answer="not a number"
        )
        
        assert result.is_correct is False
        assert result.is_winner is False
        assert "Validation error" in result.validation_result.message
    
    @pytest.mark.asyncio
    async def test_lock_acquisition_and_release(self, concurrency_manager, sample_problem):
        """Test distributed lock acquisition and release."""
        problem_id = str(sample_problem.id)
        
        # Acquire lock
        acquired = await concurrency_manager._acquire_problem_lock(problem_id)
        assert acquired is True
        
        # Try to acquire same lock (should fail)
        acquired_again = await concurrency_manager._acquire_problem_lock(problem_id)
        assert acquired_again is False
        
        # Release lock
        await concurrency_manager._release_problem_lock(problem_id)
        
        # Should be able to acquire again
        acquired_after_release = await concurrency_manager._acquire_problem_lock(problem_id)
        assert acquired_after_release is True
        
        # Clean up
        await concurrency_manager._release_problem_lock(problem_id)
    
    @pytest.mark.asyncio
    async def test_multiple_problems_isolation(self, concurrency_manager):
        """Test that different problems are isolated."""
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
        
        user_id = "user1"
        
        # Submit to both problems
        result1 = await concurrency_manager.submit_answer(user_id, problem1, 10.0)
        result2 = await concurrency_manager.submit_answer(user_id, problem2, 12.0)
        
        # Both should be winners of their respective problems
        assert result1.is_winner is True
        assert result2.is_winner is True
        
        # Problems should be independently solved
        assert await concurrency_manager._is_problem_solved(str(problem1.id)) is True
        assert await concurrency_manager._is_problem_solved(str(problem2.id)) is True