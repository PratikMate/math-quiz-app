"""
Gemini API integration service for AI-powered math problem generation.
"""
import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any, List
import json
import re

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from ..models.math_problem import DifficultyLevel
from .structured_logger import get_structured_logger
from .performance_monitor import performance_monitor


logger = get_structured_logger(__name__)


class GeminiAPIError(Exception):
    """Custom exception for Gemini API related errors."""
    pass


class GeminiRateLimitError(GeminiAPIError):
    """Exception for rate limit errors."""
    pass


class GeminiService:
    """
    Service for interacting with Google's Gemini API to generate math problems.
    
    Handles API authentication, request formatting, response parsing,
    and error handling with retry logic.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini service with API key.
        
        Args:
            api_key: Google Gemini API key. If None, will try to get from environment.
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or set in environment")
        
        # Configure the API
        genai.configure(api_key=self.api_key)
        
        # Initialize the model
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        # Rate limiting and retry configuration
        self.max_retries = 3
        self.base_delay = 1.0  # Base delay for exponential backoff
        self.max_delay = 30.0  # Maximum delay between retries
    
    async def generate_mixed_problems(self, total_count: int = 15) -> List[Dict[str, Any]]:
        """
        Generate multiple math problems of mixed difficulties in a single API call.
        
        Args:
            total_count: Total number of problems to generate (distributed across difficulties)
            
        Returns:
            List of problem dictionaries with question, answer, and difficulty
        """
        easy_count = total_count // 3
        medium_count = total_count // 3  
        hard_count = total_count - easy_count - medium_count
        
        prompt = f"""Generate {total_count} math problems with the following distribution:
- {easy_count} EASY problems (basic arithmetic, single operations)
- {medium_count} MEDIUM problems (algebra, fractions, multi-step)  
- {hard_count} HARD problems (advanced algebra, geometry, complex calculations)

Return ONLY a JSON array with this exact format:
[
  {{"question": "What is 15 + 27?", "answer": "42", "difficulty": "easy"}},
  {{"question": "Solve for x: 2x + 5 = 13", "answer": "4", "difficulty": "medium"}},
  {{"question": "Find the area of a circle with radius 5", "answer": "78.54", "difficulty": "hard"}}
]

Requirements:
- Each question must be clear and solvable
- Answers must be numeric (no units)
- Mix different math topics within each difficulty
- Ensure problems are appropriate for their difficulty level"""

        try:
            response = await self._make_api_request(prompt, "generate_mixed_problems")
            
            # Parse JSON response
            import json
            problems = json.loads(response)
            
            if not isinstance(problems, list):
                raise ValueError("Response is not a list")
                
            return problems
            
        except Exception as e:
            logger.error(f"Mixed problem generation failed: {e}")
            raise GeminiAPIError(f"Failed to generate mixed problems: {e}")

    async def generate_math_problem(
        self, 
        difficulty: DifficultyLevel, 
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a math problem using Gemini API.
        
        Args:
            difficulty: The difficulty level for the problem
            topic: Optional specific math topic (e.g., "algebra", "geometry")
            
        Returns:
            Dictionary containing question and answer
            
        Raises:
            GeminiAPIError: If API request fails after retries
            GeminiRateLimitError: If rate limit is exceeded
        """
        start_time = time.time()
        prompt = self._create_prompt(difficulty, topic)
        
        for attempt in range(self.max_retries):
            attempt_start_time = time.time()
            rate_limited = False
            success = False
            error_msg = None
            
            try:
                # Make async API call
                response = await self._make_api_request(prompt)
                
                # Parse and validate response
                parsed_problem = self._parse_response(response)
                
                # Validate the generated problem
                if await self._validate_problem_format(parsed_problem):
                    success = True
                    response_time_ms = (time.time() - start_time) * 1000
                    
                    # Track successful API call
                    performance_monitor.track_gemini_api_call(
                        request_type="generate_problem",
                        response_time_ms=response_time_ms,
                        success=True,
                        rate_limited=False
                    )
                    
                    logger.log_gemini_api_call(
                        request_type="generate_problem",
                        response_time_ms=response_time_ms,
                        success=True,
                        difficulty=difficulty.value,
                        topic=topic,
                        attempts=attempt + 1
                    )
                    
                    return parsed_problem
                else:
                    error_msg = f"Generated problem failed validation on attempt {attempt + 1}"
                    logger.warning(error_msg, attempt=attempt + 1, difficulty=difficulty.value)
                    if attempt == self.max_retries - 1:
                        raise GeminiAPIError("Failed to generate valid problem after all retries")
                    
            except Exception as e:
                error_msg = str(e)
                
                if "rate limit" in str(e).lower() or "quota" in str(e).lower():
                    rate_limited = True
                    if attempt == self.max_retries - 1:
                        # Track rate limited failure
                        response_time_ms = (time.time() - start_time) * 1000
                        performance_monitor.track_gemini_api_call(
                            request_type="generate_problem",
                            response_time_ms=response_time_ms,
                            success=False,
                            rate_limited=True,
                            error=error_msg
                        )
                        
                        logger.log_gemini_api_call(
                            request_type="generate_problem",
                            response_time_ms=response_time_ms,
                            success=False,
                            rate_limited=True,
                            error=error_msg,
                            attempts=attempt + 1
                        )
                        
                        raise GeminiRateLimitError(f"Rate limit exceeded: {e}")
                    
                    # Exponential backoff for rate limits
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    logger.warning(
                        f"Rate limit hit, retrying in {delay}s",
                        attempt=attempt + 1,
                        delay_seconds=delay,
                        error=error_msg
                    )
                    await asyncio.sleep(delay)
                    continue
                
                if attempt == self.max_retries - 1:
                    # Track final failure
                    response_time_ms = (time.time() - start_time) * 1000
                    performance_monitor.track_gemini_api_call(
                        request_type="generate_problem",
                        response_time_ms=response_time_ms,
                        success=False,
                        rate_limited=False,
                        error=error_msg
                    )
                    
                    logger.log_gemini_api_call(
                        request_type="generate_problem",
                        response_time_ms=response_time_ms,
                        success=False,
                        rate_limited=False,
                        error=error_msg,
                        attempts=attempt + 1
                    )
                    
                    raise GeminiAPIError(f"API request failed after {self.max_retries} attempts: {e}")
                
                # Short delay for other errors
                await asyncio.sleep(self.base_delay)
            
            # Track individual attempt if not successful
            if not success:
                attempt_time_ms = (time.time() - attempt_start_time) * 1000
                performance_monitor.track_gemini_api_call(
                    request_type="generate_problem_attempt",
                    response_time_ms=attempt_time_ms,
                    success=False,
                    rate_limited=rate_limited,
                    error=error_msg
                )
        
        raise GeminiAPIError("Unexpected error in problem generation")
    
    def _create_prompt(self, difficulty: DifficultyLevel, topic: Optional[str] = None) -> str:
        """
        Create a structured prompt for math problem generation.
        
        Args:
            difficulty: The difficulty level
            topic: Optional specific topic
            
        Returns:
            Formatted prompt string
        """
        base_prompt = """Generate a math problem for a competitive quiz. 

Requirements:
- The problem should be solvable with basic arithmetic or algebra
- Provide ONLY the question and the numerical answer
- The answer must be a single number (integer or decimal)
- Format your response as JSON with 'question' and 'answer' fields
- Make the question clear and unambiguous

"""
        
        # Add difficulty-specific instructions
        if difficulty == DifficultyLevel.EASY:
            base_prompt += """Difficulty: EASY
- Use basic arithmetic (addition, subtraction, multiplication, division)
- Numbers should be small (under 100)
- Single-step problems
- Example: "What is 15 + 27?"

"""
        elif difficulty == DifficultyLevel.MEDIUM:
            base_prompt += """Difficulty: MEDIUM  
- Use multi-step arithmetic or basic algebra
- Numbers can be larger (up to 1000)
- May involve fractions, decimals, or percentages
- Example: "If 3x + 7 = 22, what is x?"

"""
        else:  # HARD
            base_prompt += """Difficulty: HARD
- Complex multi-step problems
- May involve quadratic equations, systems of equations, or advanced arithmetic
- Numbers can be large or involve multiple operations
- Example: "If x² - 5x + 6 = 0, what is the sum of all solutions?"

"""
        
        # Add topic-specific instructions if provided
        if topic:
            base_prompt += f"Topic focus: {topic}\n"
        
        base_prompt += """
Response format (JSON only):
{
  "question": "Your math problem here?",
  "answer": 42.5
}

Generate the problem now:"""
        
        return base_prompt
    
    async def _make_api_request(self, prompt: str) -> str:
        """
        Make async API request to Gemini.
        
        Args:
            prompt: The formatted prompt
            
        Returns:
            Raw response text from API
        """
        try:
            # Use asyncio to run the synchronous generate_content in a thread
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.model.generate_content(prompt)
            )
            
            if not response.text:
                raise GeminiAPIError("Empty response from Gemini API")
            
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API request failed: {e}")
            raise GeminiAPIError(f"API request failed: {e}")
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse Gemini API response to extract question and answer.
        
        Args:
            response_text: Raw response from API
            
        Returns:
            Dictionary with 'question' and 'answer' keys
            
        Raises:
            GeminiAPIError: If response cannot be parsed
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^}]*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                
                if 'question' in parsed and 'answer' in parsed:
                    return {
                        'question': str(parsed['question']).strip(),
                        'answer': float(parsed['answer'])
                    }
            
            # Fallback: try to parse structured text
            lines = response_text.strip().split('\n')
            question = None
            answer = None
            
            for line in lines:
                line = line.strip()
                if line.startswith(('Question:', 'Q:', 'Problem:')):
                    question = line.split(':', 1)[1].strip()
                elif line.startswith(('Answer:', 'A:', 'Solution:')):
                    answer_text = line.split(':', 1)[1].strip()
                    # Extract number from answer text
                    number_match = re.search(r'-?\d+\.?\d*', answer_text)
                    if number_match:
                        answer = float(number_match.group())
            
            if question and answer is not None:
                return {'question': question, 'answer': answer}
            
            raise GeminiAPIError(f"Could not parse response format: {response_text}")
            
        except json.JSONDecodeError as e:
            raise GeminiAPIError(f"Invalid JSON in response: {e}")
        except (ValueError, TypeError) as e:
            raise GeminiAPIError(f"Could not parse answer as number: {e}")
    
    async def _validate_problem_format(self, problem: Dict[str, Any]) -> bool:
        """
        Validate that the generated problem meets format requirements.
        
        Args:
            problem: Dictionary with question and answer
            
        Returns:
            True if problem is valid, False otherwise
        """
        try:
            question = problem.get('question', '')
            answer = problem.get('answer')
            
            # Check question format
            if not question or len(question.strip()) < 5:
                logger.warning("Question too short or empty")
                return False
            
            if not question.strip().endswith(('?', '.')):
                logger.warning("Question doesn't end with proper punctuation")
                return False
            
            # Check if question contains numbers or math symbols
            if not re.search(r'\d', question):
                logger.warning("Question doesn't contain any numbers")
                return False
            
            # Check answer format
            if answer is None:
                logger.warning("Answer is None")
                return False
            
            try:
                float_answer = float(answer)
                if abs(float_answer) > 1e10:
                    logger.warning("Answer is too large")
                    return False
            except (ValueError, TypeError):
                logger.warning("Answer is not a valid number")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating problem: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """
        Test the Gemini API connection with a simple request.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            test_problem = await self.generate_math_problem(DifficultyLevel.EASY)
            return test_problem is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False