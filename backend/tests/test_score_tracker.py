"""
Unit tests for ScoreTracker service.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.score_tracker import ScoreTracker, UserScore


class TestUserScore:
    """Test UserScore data structure."""
    
    def test_user_score_creation(self):
        """Test creating a UserScore instance."""
        user_score = UserScore(
            user_id="user123",
            username="TestUser"
        )
        
        assert user_score.user_id == "user123"
        assert user_score.username == "TestUser"
        assert user_score.session_wins == 0
        assert user_score.session_problems_attempted == 0
        assert user_score.total_response_time_ms == 0
        assert user_score.fastest_response_time_ms is None
        assert user_score.last_win_time is None
    
    def test_average_response_time_calculation(self):
        """Test average response time calculation."""
        user_score = UserScore(
            user_id="user123",
            username="TestUser",
            session_wins=3,
            total_response_time_ms=6000  # 6 seconds total
        )
        
        assert user_score.average_response_time_ms == 2000.0  # 2 seconds average
    
    def test_average_response_time_no_wins(self):
        """Test average response time when no wins."""
        user_score = UserScore(
            user_id="user123",
            username="TestUser",
            session_wins=0,
            total_response_time_ms=0
        )
        
        assert user_score.average_response_time_ms == 0.0
    
    def test_to_dict_conversion(self):
        """Test converting UserScore to dictionary."""
        user_score = UserScore(
            user_id="user123",
            username="TestUser",
            session_wins=2,
            fastest_response_time_ms=1500
        )
        
        data = user_score.to_dict()
        
        assert isinstance(data, dict)
        assert data['user_id'] == "user123"
        assert data['username'] == "TestUser"
        assert data['session_wins'] == 2
        assert data['fastest_response_time_ms'] == 1500
    
    def test_from_dict_creation(self):
        """Test creating UserScore from dictionary."""
        data = {
            'user_id': "user123",
            'username': "TestUser",
            'session_wins': 2,
            'fastest_response_time_ms': 1500,
            'last_win_time': datetime.utcnow().isoformat()
        }
        
        user_score = UserScore.from_dict(data)
        
        assert user_score.user_id == "user123"
        assert user_score.username == "TestUser"
        assert user_score.session_wins == 2
        assert user_score.fastest_response_time_ms == 1500
        assert isinstance(user_score.last_win_time, datetime)


class TestScoreTracker:
    """Test ScoreTracker functionality."""
    
    @pytest.fixture
    def mock_redis_service(self):
        """Create mock Redis service."""
        service = MagicMock()
        service.redis_client = AsyncMock()
        service.SESSION_EXPIRY = 3600
        return service
    
    @pytest.fixture
    def mock_database_service(self):
        """Create mock database service."""
        service = MagicMock()
        service.get_or_create_user = AsyncMock()
        service.record_submission = AsyncMock()
        service.update_user_performance = AsyncMock()
        service.get_user_by_id = AsyncMock()
        service.get_user_submissions = AsyncMock()
        service.get_leaderboard = AsyncMock()
        service.get_fastest_submissions = AsyncMock()
        return service
    
    @pytest.fixture
    def score_tracker(self, mock_redis_service, mock_database_service):
        """Create ScoreTracker instance with mocked services."""
        return ScoreTracker(
            redis_service=mock_redis_service,
            database_service=mock_database_service
        )
    
    @pytest.mark.asyncio
    async def test_initialize_new_user_score(self, score_tracker, mock_database_service):
        """Test initializing score for a new user."""
        user_id = "user123"
        username = "TestUser"
        
        # Mock database response for new user
        mock_database_service.get_or_create_user.return_value = (
            {
                'id': str(uuid4()),
                'total_wins': 0,
                'total_problems_attempted': 0,
                'best_response_time': None
            },
            True  # Created new user
        )
        
        # Mock Redis get returns None (no existing data)
        score_tracker.redis_service.redis_client.get.return_value = None
        
        user_score = await score_tracker.initialize_user_score(user_id, username)
        
        assert isinstance(user_score, UserScore)
        assert user_score.user_id == user_id
        assert user_score.username == username
        assert user_score.session_wins == 0
        assert user_score.all_time_wins == 0
    
    @pytest.mark.asyncio
    async def test_initialize_existing_user_score(self, score_tracker, mock_database_service):
        """Test initializing score for existing user."""
        user_id = "user123"
        username = "TestUser"
        
        # Mock existing Redis data
        existing_data = {
            'user_id': user_id,
            'username': username,
            'session_wins': 2,
            'session_problems_attempted': 5
        }
        import json
        score_tracker.redis_service.redis_client.get.return_value = json.dumps(existing_data)
        
        # Mock database response for existing user
        mock_database_service.get_or_create_user.return_value = (
            {
                'id': str(uuid4()),
                'total_wins': 10,
                'total_problems_attempted': 25,
                'best_response_time': 1.5
            },
            False  # Existing user
        )
        
        user_score = await score_tracker.initialize_user_score(user_id, username)
        
        assert user_score.session_wins == 2
        assert user_score.session_problems_attempted == 5
        assert user_score.all_time_wins == 10
        assert user_score.all_time_problems_attempted == 25
    
    @pytest.mark.asyncio
    async def test_record_win(self, score_tracker, mock_database_service):
        """Test recording a win for a user."""
        user_id = "user123"
        username = "TestUser"
        response_time_ms = 2500
        problem_id = str(uuid4())
        
        # Mock database responses
        mock_database_service.get_or_create_user.return_value = (
            {'id': str(uuid4()), 'total_wins': 0, 'total_problems_attempted': 0, 'best_response_time': None},
            True
        )
        mock_database_service.update_user_performance.return_value = {
            'total_wins': 1,
            'total_problems_attempted': 1,
            'best_response_time': 2.5
        }
        
        # Mock Redis operations
        score_tracker.redis_service.redis_client.get.return_value = None
        score_tracker.redis_service.redis_client.setex = AsyncMock()
        
        user_score = await score_tracker.record_win(user_id, username, response_time_ms, problem_id)
        
        assert user_score.session_wins == 1
        assert user_score.session_problems_attempted == 1
        assert user_score.total_response_time_ms == response_time_ms
        assert user_score.fastest_response_time_ms == response_time_ms
        assert user_score.last_win_time is not None
    
    @pytest.mark.asyncio
    async def test_record_attempt(self, score_tracker, mock_database_service):
        """Test recording a problem attempt."""
        user_id = "user123"
        username = "TestUser"
        problem_id = str(uuid4())
        
        # Mock database responses
        mock_database_service.get_or_create_user.return_value = (
            {'id': str(uuid4()), 'total_wins': 0, 'total_problems_attempted': 0, 'best_response_time': None},
            True
        )
        
        # Mock Redis operations
        score_tracker.redis_service.redis_client.get.return_value = None
        score_tracker.redis_service.redis_client.setex = AsyncMock()
        
        user_score = await score_tracker.record_attempt(
            user_id, username, problem_id, 42.0, False, 3000
        )
        
        assert user_score.session_problems_attempted == 1
        assert user_score.session_wins == 0  # Incorrect attempt
    
    @pytest.mark.asyncio
    async def test_get_user_score_from_cache(self, score_tracker):
        """Test getting user score from cache."""
        user_id = "user123"
        user_score = UserScore(user_id=user_id, username="TestUser", session_wins=3)
        
        # Add to cache
        score_tracker._score_cache[user_id] = user_score
        
        retrieved_score = await score_tracker.get_user_score(user_id)
        
        assert retrieved_score == user_score
        assert retrieved_score.session_wins == 3
    
    @pytest.mark.asyncio
    async def test_get_user_score_from_redis(self, score_tracker):
        """Test getting user score from Redis when not in cache."""
        user_id = "user123"
        
        # Mock Redis data
        score_data = {
            'user_id': user_id,
            'username': "TestUser",
            'session_wins': 2
        }
        import json
        score_tracker.redis_service.redis_client.get.return_value = json.dumps(score_data)
        
        retrieved_score = await score_tracker.get_user_score(user_id)
        
        assert retrieved_score is not None
        assert retrieved_score.user_id == user_id
        assert retrieved_score.session_wins == 2
        # Should also be added to cache
        assert user_id in score_tracker._score_cache
    
    @pytest.mark.asyncio
    async def test_get_user_score_not_found(self, score_tracker):
        """Test getting user score when user doesn't exist."""
        user_id = "nonexistent"
        
        # Mock Redis returns None
        score_tracker.redis_service.redis_client.get.return_value = None
        
        retrieved_score = await score_tracker.get_user_score(user_id)
        
        assert retrieved_score is None
    
    @pytest.mark.asyncio
    async def test_get_leaderboard(self, score_tracker):
        """Test getting session leaderboard."""
        # Add some users to cache
        users = [
            UserScore("user1", "User1", session_wins=5, total_response_time_ms=10000),
            UserScore("user2", "User2", session_wins=3, total_response_time_ms=9000),
            UserScore("user3", "User3", session_wins=5, total_response_time_ms=8000),  # Faster
            UserScore("user4", "User4", session_wins=1, total_response_time_ms=2000),
        ]
        
        for user in users:
            score_tracker._score_cache[user.user_id] = user
        
        leaderboard = await score_tracker.get_leaderboard(limit=3)
        
        assert len(leaderboard) == 3
        # Should be sorted by wins (desc), then by avg response time (asc)
        assert leaderboard[0]['user_id'] == "user3"  # 5 wins, faster
        assert leaderboard[1]['user_id'] == "user1"  # 5 wins, slower
        assert leaderboard[2]['user_id'] == "user2"  # 3 wins
        
        # Check rank assignment
        assert leaderboard[0]['rank'] == 1
        assert leaderboard[1]['rank'] == 2
        assert leaderboard[2]['rank'] == 3
    
    @pytest.mark.asyncio
    async def test_get_all_time_leaderboard(self, score_tracker, mock_database_service):
        """Test getting all-time leaderboard from database."""
        # Mock database leaderboard
        mock_leaderboard = [
            {'username': 'TopPlayer', 'total_wins': 100},
            {'username': 'SecondPlace', 'total_wins': 75},
        ]
        mock_database_service.get_leaderboard.return_value = mock_leaderboard
        
        leaderboard = await score_tracker.get_all_time_leaderboard(limit=10)
        
        assert len(leaderboard) == 2
        assert leaderboard[0]['rank'] == 1
        assert leaderboard[1]['rank'] == 2
        assert leaderboard[0]['username'] == 'TopPlayer'
    
    @pytest.mark.asyncio
    async def test_get_session_stats(self, score_tracker):
        """Test getting session statistics."""
        # Add some users to cache
        users = [
            UserScore("user1", "User1", session_wins=3, session_problems_attempted=5, 
                     total_response_time_ms=6000, fastest_response_time_ms=1500),
            UserScore("user2", "User2", session_wins=2, session_problems_attempted=4, 
                     total_response_time_ms=5000, fastest_response_time_ms=2000),
        ]
        
        for user in users:
            score_tracker._score_cache[user.user_id] = user
        
        stats = await score_tracker.get_session_stats()
        
        assert stats['total_players'] == 2
        assert stats['total_wins'] == 5
        assert stats['total_attempts'] == 9
        assert stats['fastest_response_time_ms'] == 1500
        assert stats['average_response_time_ms'] > 0
    
    @pytest.mark.asyncio
    async def test_reset_session_scores(self, score_tracker):
        """Test resetting all session scores."""
        # Add some data to cache
        score_tracker._score_cache["user1"] = UserScore("user1", "User1", session_wins=5)
        
        # Mock Redis operations
        score_tracker.redis_service.redis_client.keys.return_value = ["quiz:scores:user1"]
        score_tracker.redis_service.redis_client.delete = AsyncMock()
        
        result = await score_tracker.reset_session_scores()
        
        assert result is True
        assert len(score_tracker._score_cache) == 0
        score_tracker.redis_service.redis_client.delete.assert_called()
    
    @pytest.mark.asyncio
    async def test_cleanup_inactive_users(self, score_tracker):
        """Test cleaning up inactive user scores."""
        # Add users to cache
        score_tracker._score_cache["active_user"] = UserScore("active_user", "Active")
        score_tracker._score_cache["inactive_user"] = UserScore("inactive_user", "Inactive")
        
        # Mock Redis delete
        score_tracker.redis_service.redis_client.delete = AsyncMock()
        
        # Only active_user is in the active list
        cleaned_count = await score_tracker.cleanup_inactive_users(["active_user"])
        
        assert cleaned_count == 1
        assert "active_user" in score_tracker._score_cache
        assert "inactive_user" not in score_tracker._score_cache
    
    @pytest.mark.asyncio
    async def test_fastest_response_time_update(self, score_tracker, mock_database_service):
        """Test that fastest response time is updated correctly."""
        user_id = "user123"
        username = "TestUser"
        
        # Mock database responses
        mock_database_service.get_or_create_user.return_value = (
            {'id': str(uuid4()), 'total_wins': 0, 'total_problems_attempted': 0, 'best_response_time': None},
            True
        )
        mock_database_service.update_user_performance.return_value = {
            'total_wins': 1, 'total_problems_attempted': 1, 'best_response_time': 2.0
        }
        
        # Mock Redis operations
        score_tracker.redis_service.redis_client.get.return_value = None
        score_tracker.redis_service.redis_client.setex = AsyncMock()
        
        # First win with 3000ms
        user_score = await score_tracker.record_win(user_id, username, 3000, str(uuid4()))
        assert user_score.fastest_response_time_ms == 3000
        
        # Second win with faster time (2000ms)
        user_score = await score_tracker.record_win(user_id, username, 2000, str(uuid4()))
        assert user_score.fastest_response_time_ms == 2000
        
        # Third win with slower time (4000ms) - should not update fastest
        user_score = await score_tracker.record_win(user_id, username, 4000, str(uuid4()))
        assert user_score.fastest_response_time_ms == 2000  # Still the fastest