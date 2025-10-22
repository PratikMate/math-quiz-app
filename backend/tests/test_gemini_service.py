"""
Unit tests for Gemini AI service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.services.gemini_service import GeminiService, GeminiAPIError, GeminiRateLimitError
from app.models.math_problem import DifficultyLevel


class TestGeminiService:
    """Test GeminiService AI problem generation."""
    
    def test_service_initialization(self):
        """Test service initialization with API key."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                assert service.api_key == "test_key"
    
    def test_initialization_without_api_key(self):
        """Test service initialization fails without API key."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="GEMINI_API_KEY must be provided"):
                GeminiService()
    
    @pytest.mark.asyncio
    async def test_successful_problem_generation(self):
        """Test successful AI problem generation."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel') as mock_model_class:
                # Mock the model instance
                mock_model = MagicMock()
                mock_model_class.return_value = mock_model
                
                # Mock successful API response
                mock_response = MagicMock()
                mock_response.text = json.dumps({
                    "question": "What is 15 + 27?",
                    "answer": 42
                })
                
                service = GeminiService(api_key="test_key")
                
                # Mock the async API call
                with patch.object(service, '_make_api_request', return_value=mock_response.text):
                    result = await service.generate_math_problem(DifficultyLevel.EASY)
                    
                    assert result['question'] == "What is 15 + 27?"
                    assert result['answer'] == 42.0
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test rate limit error handling with retries."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                # Mock rate limit error
                rate_limit_error = Exception("rate limit exceeded")
                
                with patch.object(service, '_make_api_request', side_effect=rate_limit_error):
                    with pytest.raises(GeminiRateLimitError):
                        await service.generate_math_problem(DifficultyLevel.EASY)
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        """Test general API error handling."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                # Mock general API error
                api_error = Exception("API connection failed")
                
                with patch.object(service, '_make_api_request', side_effect=api_error):
                    with pytest.raises(GeminiAPIError):
                        await service.generate_math_problem(DifficultyLevel.EASY)
    
    def test_prompt_creation_easy(self):
        """Test prompt creation for easy difficulty."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                prompt = service._create_prompt(DifficultyLevel.EASY)
                
                assert "EASY" in prompt
                assert "basic arithmetic" in prompt
                assert "under 100" in prompt
    
    def test_prompt_creation_medium(self):
        """Test prompt creation for medium difficulty."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                prompt = service._create_prompt(DifficultyLevel.MEDIUM)
                
                assert "MEDIUM" in prompt
                assert "multi-step" in prompt
                assert "up to 1000" in prompt
    
    def test_prompt_creation_hard(self):
        """Test prompt creation for hard difficulty."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                prompt = service._create_prompt(DifficultyLevel.HARD)
                
                assert "HARD" in prompt
                assert "Complex" in prompt
                assert "quadratic" in prompt
    
    def test_prompt_creation_with_topic(self):
        """Test prompt creation with specific topic."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                prompt = service._create_prompt(DifficultyLevel.EASY, topic="algebra")
                
                assert "algebra" in prompt
    
    def test_response_parsing_json(self):
        """Test parsing valid JSON response."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                json_response = '{"question": "What is 2 + 2?", "answer": 4}'
                
                result = service._parse_response(json_response)
                
                assert result['question'] == "What is 2 + 2?"
                assert result['answer'] == 4.0
    
    def test_response_parsing_structured_text(self):
        """Test parsing structured text response."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                text_response = """
                Question: What is 5 × 6?
                Answer: 30
                """
                
                result = service._parse_response(text_response)
                
                assert result['question'] == "What is 5 × 6?"
                assert result['answer'] == 30.0
    
    def test_response_parsing_invalid(self):
        """Test parsing invalid response format."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                invalid_response = "This is not a valid response format"
                
                with pytest.raises(GeminiAPIError):
                    service._parse_response(invalid_response)
    
    @pytest.mark.asyncio
    async def test_problem_validation_valid(self):
        """Test validation of valid problems."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                valid_problem = {
                    'question': 'What is 15 + 27?',
                    'answer': 42.0
                }
                
                is_valid = await service._validate_problem_format(valid_problem)
                assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_problem_validation_invalid_question(self):
        """Test validation of invalid questions."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                invalid_problems = [
                    {'question': '', 'answer': 42.0},  # Empty question
                    {'question': 'Hi', 'answer': 42.0},  # Too short
                    {'question': 'No numbers here', 'answer': 42.0},  # No numbers
                    {'question': 'What is two plus two', 'answer': 42.0},  # No punctuation
                ]
                
                for problem in invalid_problems:
                    is_valid = await service._validate_problem_format(problem)
                    assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_problem_validation_invalid_answer(self):
        """Test validation of invalid answers."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                invalid_problems = [
                    {'question': 'What is 2 + 2?', 'answer': None},  # None answer
                    {'question': 'What is 2 + 2?', 'answer': 'four'},  # Non-numeric
                    {'question': 'What is 2 + 2?', 'answer': 1e11},  # Too large
                ]
                
                for problem in invalid_problems:
                    is_valid = await service._validate_problem_format(problem)
                    assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_connection_test_success(self):
        """Test successful connection test."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                # Mock successful problem generation
                with patch.object(service, 'generate_math_problem', return_value={'question': 'test', 'answer': 1}):
                    result = await service.test_connection()
                    assert result is True
    
    @pytest.mark.asyncio
    async def test_connection_test_failure(self):
        """Test failed connection test."""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                service = GeminiService(api_key="test_key")
                
                # Mock failed problem generation
                with patch.object(service, 'generate_math_problem', side_effect=GeminiAPIError("Connection failed")):
                    result = await service.test_connection()
                    assert result is False