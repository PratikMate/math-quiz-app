"""
Integration tests for the competitive math quiz system.
"""
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.quiz_engine import QuizEngine
from app.services.submission_processor import SubmissionProcessor
from app.services.score_tracker import ScoreTracker
from app.services.concurrency_manager import ConcurrencyManager
from app.services.gemini_service import GeminiService
from app.models.math_problem import MathProblem, DifficultyLevel


class TestQuizWorkflow:
    """Test end-to-end quiz workflow integration."""
    
    @pytest_asyncio.fixture
    async def mock_gemini_service(self):
        """Create mock Gemini service for integration tests."""
        service = MagicMock(spec=GeminiService)
        service.generate_math_problem = AsyncMock(return_value={
            'question': 'What is 15 + 27?',
            'answer': 42.0
        })
        return service
    
    @pytest_asyncio.fixture
    async def quiz_engine(self, mock_gemini_service):
        """Create QuizEngine for integration testing."""
        return QuizEngine(gemini_service=mock_gemini_service)
    
    @pytest.fixture
    def submission_processor(self):
        """Create SubmissionProcessor for integration testing."""
        return SubmissionProcessor()
    
    @pytest_asyncio.fixture
    async def score_tracker(self, redis_service):
        """Create ScoreTracker for integration testing."""
        return ScoreTracker(redis_service=redis_service)
    
    @pytest_asyncio.fixture
    async def concurrency_manager(self, redis_service):
        """Create ConcurrencyManager for integration testing."""
        return ConcurrencyManager(redis_service)
    
    @pytest.mark.asyncio
    async def test_complete_quiz_round(self, quiz_engine, submission_processor, score_tracker):
        """Test a complete quiz round from problem generation to scoring."""
        # Generate a problem
        problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.EASY)
        assert isinstance(problem, MathProblem)
        
        # Simulate user submissions
        user1_id = "user1"
        user2_id = "user2"
        
        # First user submits correct answer
        result1 = await submission_processor.process_submission(
            user_id=user1_id,
            problem=problem,
            submitted_answer=problem.correct_answer
        )
        
        assert result1.is_correct is True
        assert result1.is_winner is True
        
        # Second user submits after problem is solved
        result2 = await submission_processor.process_submission(
            user_id=user2_id,
            problem=problem,
            submitted_answer=problem.correct_answer
        )
        
        assert result2.is_winner is False
        assert "already been solved" in result2.message
        
        # Update scores
        user1_score = await score_tracker.record_win(
            user_id=user1_id,
            username="User1",
            response_time_ms=2500,
            problem_id=str(problem.id)
        )
        
        assert user1_score.session_wins == 1
        assert user1_score.fastest_response_time_ms == 2500
    
    @pytest.mark.asyncio
    async def test_concurrent_submissions_with_redis(self, quiz_engine, concurrency_manager):
        """Test concurrent submissions using Redis-based concurrency manager."""
        # Generate a problem
        problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        # Simulate concurrent submissions
        users = ["user1", "user2", "user3"]
        tasks = []
        
        for user_id in users:
            task = concurrency_manager.submit_answer(
                user_id=user_id,
                problem=problem,
                submitted_answer=problem.correct_answer
            )
            tasks.append(task)
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        
        # Verify only one winner
        winners = [r for r in results if r.is_winner]
        assert len(winners) == 1
        
        # Verify all submissions were processed
        assert len(results) == 3
        
        # Verify winner has rank 1
        winner = winners[0]
        assert winner.rank == 1
    
    @pytest.mark.asyncio
    async def test_quiz_state_management(self, quiz_engine, concurrency_manager):
        """Test quiz state management and problem rotation."""
        # Generate first problem
        problem1 = await quiz_engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        # Submit answer and solve problem
        result = await concurrency_manager.submit_answer(
            user_id="user1",
            problem=problem1,
            submitted_answer=problem1.correct_answer
        )
        assert result.is_winner is True
        
        # Reset problem state for rotation
        success = await concurrency_manager.reset_problem_state(str(problem1.id))
        assert success is True
        
        # Generate new problem
        problem2 = await quiz_engine.rotate_question(DifficultyLevel.MEDIUM)
        assert isinstance(problem2, MathProblem)
        assert problem2.id != problem1.id
        
        # Should be able to submit to new problem
        result2 = await concurrency_manager.submit_answer(
            user_id="user1",
            problem=problem2,
            submitted_answer=problem2.correct_answer
        )
        assert result2.is_winner is True
    
    @pytest.mark.asyncio
    async def test_leaderboard_integration(self, score_tracker):
        """Test leaderboard functionality with multiple users."""
        # Create multiple users with different scores
        users_data = [
            ("user1", "Alice", 3, 6000),  # 3 wins, 6 seconds total
            ("user2", "Bob", 5, 8000),    # 5 wins, 8 seconds total
            ("user3", "Charlie", 2, 3000), # 2 wins, 3 seconds total
        ]
        
        for user_id, username, wins, total_time in users_data:
            for i in range(wins):
                await score_tracker.record_win(
                    user_id=user_id,
                    username=username,
                    response_time_ms=total_time // wins,
                    problem_id=str(uuid4())
                )
        
        # Get leaderboard
        leaderboard = await score_tracker.get_leaderboard(limit=10)
        
        assert len(leaderboard) == 3
        
        # Should be sorted by wins (desc), then by avg response time (asc)
        assert leaderboard[0]['user_id'] == "user2"  # 5 wins
        assert leaderboard[1]['user_id'] == "user1"  # 3 wins
        assert leaderboard[2]['user_id'] == "user3"  # 2 wins
        
        # Check rank assignment
        for i, entry in enumerate(leaderboard):
            assert entry['rank'] == i + 1
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, quiz_engine, submission_processor):
        """Test error handling in integrated workflow."""
        # Test with invalid problem generation
        with patch.object(quiz_engine.gemini_service, 'generate_math_problem', 
                         side_effect=Exception("API Error")):
            # Should fall back to predefined problems
            problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.EASY)
            assert isinstance(problem, MathProblem)
            # Should be a fallback problem
            assert problem.question in [p.question for p in quiz_engine._fallback_problems[DifficultyLevel.EASY.value]]
        
        # Test with invalid submission format
        valid_problem = MathProblem(
            question="What is 2 + 2?",
            correct_answer=4.0,
            difficulty=DifficultyLevel.EASY
        )
        
        result = await submission_processor.process_submission(
            user_id="user1",
            problem=valid_problem,
            submitted_answer="invalid_answer"
        )
        
        assert result.is_correct is False
        assert "Invalid submission format" in result.message
    
    @pytest.mark.asyncio
    async def test_session_statistics(self, score_tracker):
        """Test session statistics calculation."""
        # Add some users and scores
        await score_tracker.record_win("user1", "Alice", 2000, str(uuid4()))
        await score_tracker.record_win("user2", "Bob", 3000, str(uuid4()))
        await score_tracker.record_attempt("user3", "Charlie", str(uuid4()), 42.0, False, 1500)
        
        # Get session stats
        stats = await score_tracker.get_session_stats()
        
        assert stats['total_players'] == 3
        assert stats['total_wins'] == 2
        assert stats['total_attempts'] == 3
        assert stats['fastest_response_time_ms'] == 2000
        assert stats['average_response_time_ms'] > 0
    
    @pytest.mark.asyncio
    async def test_problem_validation_workflow(self, quiz_engine):
        """Test problem validation in the complete workflow."""
        # Mock AI service to return invalid problem
        quiz_engine.gemini_service.generate_math_problem.return_value = {
            'question': 'Invalid',  # Too short, no numbers
            'answer': 1.0
        }
        
        # Should fall back to valid problem
        problem = await quiz_engine.generate_problem_with_ai(DifficultyLevel.EASY)
        
        assert isinstance(problem, MathProblem)
        assert problem.question != 'Invalid'
        assert len(problem.question) > 5
        assert any(char.isdigit() for char in problem.question)


class TestWebSocketEventFlow:
    """Test WebSocket event flow simulation."""
    
    @pytest_asyncio.fixture
    async def concurrency_manager(self, redis_service):
        """Create ConcurrencyManager for integration testing."""
        return ConcurrencyManager(redis_service)
    
    @pytest_asyncio.fixture
    async def score_tracker(self, redis_service):
        """Create ScoreTracker for integration testing."""
        return ScoreTracker(redis_service=redis_service)
    
    @pytest.mark.asyncio
    async def test_user_join_and_submission_flow(self, concurrency_manager, score_tracker):
        """Test simulated WebSocket event flow."""
        # Simulate user joining
        user_id = "websocket_user"
        username = "WebSocketUser"
        
        # Initialize user score (simulates join_quiz event)
        user_score = await score_tracker.initialize_user_score(user_id, username)
        assert user_score.user_id == user_id
        assert user_score.username == username
        
        # Create a problem (simulates new_problem event)
        problem = MathProblem(
            question="What is 8 × 9?",
            correct_answer=72.0,
            difficulty=DifficultyLevel.EASY
        )
        
        # Submit answer (simulates submit_answer event)
        result = await concurrency_manager.submit_answer(
            user_id=user_id,
            problem=problem,
            submitted_answer=72.0
        )
        
        # Verify result (simulates winner_announced event)
        assert result.is_winner is True
        assert result.is_correct is True
        
        # Update score (simulates score update)
        updated_score = await score_tracker.record_win(
            user_id=user_id,
            username=username,
            response_time_ms=1800,
            problem_id=str(problem.id)
        )
        
        assert updated_score.session_wins == 1
        assert updated_score.fastest_response_time_ms == 1800
    
    @pytest.mark.asyncio
    async def test_multiple_users_websocket_simulation(self, concurrency_manager, score_tracker):
        """Test multiple users in WebSocket-like scenario."""
        # Simulate multiple users joining
        users = [
            ("ws_user1", "WSUser1"),
            ("ws_user2", "WSUser2"),
            ("ws_user3", "WSUser3")
        ]
        
        # Initialize all users
        for user_id, username in users:
            await score_tracker.initialize_user_score(user_id, username)
        
        # Create problem
        problem = MathProblem(
            question="What is 15 × 4?",
            correct_answer=60.0,
            difficulty=DifficultyLevel.EASY
        )
        
        # Simulate concurrent submissions with slight delays
        results = []
        for i, (user_id, username) in enumerate(users):
            # Add small delay to simulate network timing
            if i > 0:
                await asyncio.sleep(0.001)
            
            result = await concurrency_manager.submit_answer(
                user_id=user_id,
                problem=problem,
                submitted_answer=60.0
            )
            results.append((user_id, username, result))
        
        # Verify only first user wins
        winner_count = 0
        for user_id, username, result in results:
            if result.is_winner:
                winner_count += 1
                # Update winner's score
                await score_tracker.record_win(
                    user_id=user_id,
                    username=username,
                    response_time_ms=2000,
                    problem_id=str(problem.id)
                )
        
        assert winner_count == 1
        
        # Get leaderboard
        leaderboard = await score_tracker.get_leaderboard()
        winner_entry = next((entry for entry in leaderboard if entry['session_wins'] > 0), None)
        assert winner_entry is not None
        assert winner_entry['session_wins'] == 1


class TestDatabaseIntegration:
    """Test database integration scenarios."""
    
    @pytest_asyncio.fixture
    async def score_tracker(self, redis_service):
        """Create ScoreTracker for database integration testing."""
        return ScoreTracker(redis_service=redis_service)
    
    @pytest.mark.asyncio
    async def test_score_persistence_simulation(self, score_tracker):
        """Test score persistence with mock database."""
        # Mock database service
        mock_db = MagicMock()
        mock_db.get_or_create_user = AsyncMock(return_value=(
            {
                'id': str(uuid4()),
                'total_wins': 5,
                'total_problems_attempted': 10,
                'best_response_time': 1.5
            },
            False  # Existing user
        ))
        mock_db.record_submission = AsyncMock()
        mock_db.update_user_performance = AsyncMock(return_value={
            'total_wins': 6,
            'total_problems_attempted': 11,
            'best_response_time': 1.4
        })
        
        # Set mock database
        score_tracker.database_service = mock_db
        
        # Record a win
        user_score = await score_tracker.record_win(
            user_id="db_user",
            username="DatabaseUser",
            response_time_ms=1400,
            problem_id=str(uuid4())
        )
        
        # Verify database calls were made
        mock_db.get_or_create_user.assert_called_once()
        mock_db.record_submission.assert_called_once()
        mock_db.update_user_performance.assert_called_once()
        
        # Verify score includes persistent data
        assert user_score.all_time_wins == 6
        assert user_score.all_time_problems_attempted == 11
        assert user_score.session_wins == 1
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, score_tracker):
        """Test handling of database errors."""
        # Mock database service that raises errors
        mock_db = MagicMock()
        mock_db.get_or_create_user = AsyncMock(side_effect=Exception("Database connection failed"))
        
        score_tracker.database_service = mock_db
        
        # Should still work without database
        user_score = await score_tracker.initialize_user_score("error_user", "ErrorUser")
        
        assert user_score.user_id == "error_user"
        assert user_score.username == "ErrorUser"
        assert user_score.all_time_wins == 0  # Default values when DB fails