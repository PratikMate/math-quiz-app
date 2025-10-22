"""
Math problem data models and validation.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator, root_validator
import re


class DifficultyLevel(str, Enum):
    """Difficulty levels for math problems."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MathProblem(BaseModel):
    """
    Data model for a math problem with validation.
    
    Represents a single math problem with question text, correct answer,
    difficulty level, and metadata for tracking and validation.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the problem")
    question: str = Field(..., min_length=5, max_length=500, description="The math problem question text")
    correct_answer: str = Field(..., description="The correct answer (can be text or number)")
    difficulty: DifficultyLevel = Field(..., description="Difficulty level of the problem")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the problem was created")
    solved_by: Optional[UUID] = Field(None, description="User ID who solved this problem first")
    solved_at: Optional[datetime] = Field(None, description="When the problem was solved")
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

    @validator('question')
    def validate_question_format(cls, v):
        """
        Validate that the question is properly formatted and contains mathematical content.
        """
        if not v.strip():
            raise ValueError("Question cannot be empty or whitespace only")
        
        # Check for basic math symbols or numbers
        math_pattern = r'[\d+\-*/=().\s]+'
        if not re.search(r'\d', v):
            raise ValueError("Question must contain at least one number")
        
        # Ensure question ends with proper punctuation
        if not v.strip().endswith(('?', '.')):
            raise ValueError("Question must end with '?' or '.'")
        
        return v.strip()

    @validator('correct_answer')
    def validate_answer_format(cls, v):
        """
        Validate answer format.
        """
        if not v or not str(v).strip():
            raise ValueError("Answer cannot be empty")
        
        return str(v).strip()

    @root_validator(skip_on_failure=True)
    def validate_solved_consistency(cls, values):
        """
        Ensure solved_by and solved_at are consistent.
        """
        solved_by = values.get('solved_by')
        solved_at = values.get('solved_at')
        
        if solved_by is not None and solved_at is None:
            raise ValueError("solved_at must be provided when solved_by is set")
        
        if solved_by is None and solved_at is not None:
            raise ValueError("solved_by must be provided when solved_at is set")
        
        return values


class AnswerSubmission(BaseModel):
    """
    Data model for user answer submissions with validation.
    """
    user_id: UUID = Field(..., description="ID of the user submitting the answer")
    problem_id: UUID = Field(..., description="ID of the problem being answered")
    submitted_answer: Union[int, float, str] = Field(..., description="The user's answer")
    submitted_at: datetime = Field(default_factory=datetime.utcnow, description="When the answer was submitted")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

    @validator('submitted_answer', pre=True)
    def parse_and_validate_answer(cls, v):
        """
        Parse and validate various numeric formats from user input.
        
        Handles integers, floats, fractions, and string representations.
        """
        if v is None:
            raise ValueError("Answer cannot be None")
        
        # If already a number, validate range
        if isinstance(v, (int, float)):
            if abs(v) > 1e10:
                raise ValueError("Answer must be within reasonable range")
            return float(v)
        
        # Handle string input
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Answer cannot be empty")
            
            try:
                # Handle basic fractions (e.g., "1/2", "3/4")
                if '/' in v and v.count('/') == 1:
                    numerator, denominator = v.split('/')
                    num = float(numerator.strip())
                    den = float(denominator.strip())
                    if den == 0:
                        raise ValueError("Division by zero in fraction")
                    result = num / den
                else:
                    # Handle decimal numbers, integers, negative numbers
                    result = float(v)
                
                # Validate range
                if abs(result) > 1e10:
                    raise ValueError("Answer must be within reasonable range")
                
                return round(result, 6)
                
            except ValueError as e:
                if "could not convert" in str(e) or "invalid literal" in str(e):
                    raise ValueError(f"Invalid number format: {v}")
                raise e
        
        raise ValueError(f"Unsupported answer type: {type(v)}")


class AnswerValidationResult(BaseModel):
    """
    Result of answer validation with detailed feedback.
    """
    is_correct: bool = Field(..., description="Whether the answer is correct")
    submitted_value: str = Field(..., description="The submitted answer")
    correct_value: str = Field(..., description="The correct answer")
    tolerance: float = Field(default=1e-6, description="Tolerance used for comparison")
    message: Optional[str] = Field(None, description="Additional feedback message")
    
    @classmethod
    def create_result(cls, submitted: Union[str, int, float], correct: Union[str, int, float], tolerance: float = 1e-6) -> 'AnswerValidationResult':
        """
        Create validation result by comparing submitted and correct answers.
        
        Args:
            submitted: The user's submitted answer
            correct: The correct answer
            tolerance: Tolerance for floating point comparison
            
        Returns:
            AnswerValidationResult with comparison details
        """
        # Convert both to strings for consistent handling
        submitted_str = str(submitted).strip()
        correct_str = str(correct).strip()
        
        # Try numeric comparison first
        try:
            submitted_num = float(submitted_str)
            correct_num = float(correct_str)
            is_correct = abs(submitted_num - correct_num) <= tolerance
            
            message = None
            if not is_correct:
                diff = abs(submitted_num - correct_num)
                if diff < 0.1:
                    message = "Very close! Check your calculation."
                elif diff < 1.0:
                    message = "Close, but not quite right."
                else:
                    message = "Incorrect answer."
        except (ValueError, TypeError):
            # Fall back to string comparison for non-numeric answers
            is_correct = submitted_str.lower() == correct_str.lower()
            message = "Incorrect answer." if not is_correct else None
        
        return cls(
            is_correct=is_correct,
            submitted_value=submitted_str,
            correct_value=correct_str,
            tolerance=tolerance,
            message=message
        )


def validate_answer(submission: AnswerSubmission, problem: MathProblem) -> AnswerValidationResult:
    """
    Validate a user's answer submission against the correct answer.
    
    Args:
        submission: The user's answer submission
        problem: The math problem with correct answer
        
    Returns:
        AnswerValidationResult with validation details
    """
    return AnswerValidationResult.create_result(
        submitted=submission.submitted_answer,
        correct=problem.correct_answer
    )