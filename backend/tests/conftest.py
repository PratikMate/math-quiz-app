"""
Pytest configuration and shared fixtures for testing.
"""
import asyncio
import pytest
import pytest_asyncio
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.models.math_problem import MathProblem, DifficultyLevel
from app.services.redis_service import RedisService
from app.services.gemini_service import GeminiService

# Configure pytest-asyncio
pytest_asyncio.auto_mode = True


@pytest_asyncio.fixture
async def fake_redis():
    """Create a fake Redis client for testing."""
    redis_client = fakeredis.aioredis.FakeRedis()
    yield redis_client
    await redis_client.flushall()
    await redis_client.aclose()


@pytest_asyncio.fixture
async def redis_service(fake_redis):
    """Create a RedisService instance with fake Redis."""
    service = RedisService()
    service.redis_client = fake_redis
    return service


@pytest.fixture
def mock_gemini_service():
    """Create a mock GeminiService for testing."""
    service = MagicMock(spec=GeminiService)
    service.generate_math_problem = AsyncMock()
    service.test_connection = AsyncMock(return_value=True)
    return service


@pytest.fixture
def sample_easy_problem():
    """Create a sample easy math problem for testing."""
    return MathProblem(
        id=uuid4(),
        question="What is 15 + 27?",
        correct_answer=42.0,
        difficulty=DifficultyLevel.EASY
    )


@pytest.fixture
def sample_medium_problem():
    """Create a sample medium math problem for testing."""
    return MathProblem(
        id=uuid4(),
        question="If 3x + 7 = 22, what is x?",
        correct_answer=5.0,
        difficulty=DifficultyLevel.MEDIUM
    )


@pytest.fixture
def sample_hard_problem():
    """Create a sample hard math problem for testing."""
    return MathProblem(
        id=uuid4(),
        question="If x² - 5x + 6 = 0, what is the sum of all solutions?",
        correct_answer=5.0,
        difficulty=DifficultyLevel.HARD
    )


@pytest.fixture
def sample_ai_response():
    """Sample AI response for testing problem generation."""
    return {
        'question': 'What is 12 × 8?',
        'answer': 96.0
    }