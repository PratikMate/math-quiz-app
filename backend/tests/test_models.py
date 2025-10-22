"""
Unit tests for math problem models and validation.
"""
import pytest
from datetime import datetime
from uuid import UUID, uuid4

from app.models.math_problem import (
    MathProblem, 
    AnswerSubmission, 
    AnswerValidationResult,
    DifficultyLevel,
    validate_answer
)


class TestMathProblem:
    """Test MathProblem model validation and functionality."""
    
    def test_valid_problem_creation(self):
        """Test creating a valid math problem."""
        problem = MathProblem(
            question="What is 2 + 2?",
            correct_answer=4.0,
            difficulty=DifficultyLevel.EASY
        )
        
        assert problem.question == "What is 2 + 2?"
        assert problem.correct_answer == 4.0
        assert problem.difficulty == DifficultyLevel.EASY
        assert isinstance(problem.id, UUID)
        assert isinstance(problem.created_at, datetime)
    
    def test_question_validation(self):
        """Test question format validation."""
        # Valid questions
        valid_questions = [
            "What is 15 + 27?",
            "Calculate 3 × 4.",
            "If x = 5, what is 2x + 1?",
            "What is the area of a circle with radius 3?"
        ]
        
        for question in valid_questions:
            problem = MathProblem(
                question=question,
                correct_answer=1.0,
                difficulty=DifficultyLevel.EASY
            )
            assert problem.question == question
    
    def test_invalid_question_validation(self):
        """Test invalid question formats."""
        invalid_questions = [
            "",  # Empty
            "   ",  # Whitespace only
            "No numbers here",  # No numbers
            "What is two plus two",  # No punctuation
        ]
        
        for question in invalid_questions:
            with pytest.raises(ValueError):
                MathProblem(
                    question=question,
                    correct_answer=1.0,
                    difficulty=DifficultyLevel.EASY
                )
    
    def test_answer_precision_validation(self):
        """Test answer precision and range validation."""
        # Valid answers
        valid_answers = [42, 42.5, -15.25, 0, 0.000001]
        
        for answer in valid_answers:
            problem = MathProblem(
                question="What is the answer?",
                correct_answer=answer,
                difficulty=DifficultyLevel.EASY
            )
            assert isinstance(problem.correct_answer, float)
        
        # Invalid answers (too large)
        with pytest.raises(ValueError):
            MathProblem(
                question="What is the answer?",
                correct_answer=1e11,  # Too large
                difficulty=DifficultyLevel.EASY
            )
    
    def test_solved_consistency_validation(self):
        """Test that solved_by and solved_at are consistent."""
        user_id = uuid4()
        solved_time = datetime.utcnow()
        
        # Valid: both set
        problem = MathProblem(
            question="What is 1 + 1?",
            correct_answer=2.0,
            difficulty=DifficultyLevel.EASY,
            solved_by=user_id,
            solved_at=solved_time
        )
        assert problem.solved_by == user_id
        assert problem.solved_at == solved_time
        
        # Valid: both None
        problem = MathProblem(
            question="What is 1 + 1?",
            correct_answer=2.0,
            difficulty=DifficultyLevel.EASY
        )
        assert problem.solved_by is None
        assert problem.solved_at is None
        
        # Invalid: only solved_by set
        with pytest.raises(ValueError):
            MathProblem(
                question="What is 1 + 1?",
                correct_answer=2.0,
                difficulty=DifficultyLevel.EASY,
                solved_by=user_id
            )
        
        # Invalid: only solved_at set
        with pytest.raises(ValueError):
            MathProblem(
                question="What is 1 + 1?",
                correct_answer=2.0,
                difficulty=DifficultyLevel.EASY,
                solved_at=solved_time
            )


class TestAnswerSubmission:
    """Test AnswerSubmission model validation and parsing."""
    
    def test_valid_submission_creation(self):
        """Test creating valid answer submissions."""
        user_id = uuid4()
        problem_id = uuid4()
        
        submission = AnswerSubmission(
            user_id=user_id,
            problem_id=problem_id,
            submitted_answer=42.5
        )
        
        assert submission.user_id == user_id
        assert submission.problem_id == problem_id
        assert submission.submitted_answer == 42.5
        assert isinstance(submission.submitted_at, datetime)
    
    def test_numeric_answer_parsing(self):
        """Test parsing various numeric formats."""
        user_id = uuid4()
        problem_id = uuid4()
        
        test_cases = [
            (42, 42.0),
            (42.5, 42.5),
            (-15, -15.0),
            ("42", 42.0),
            ("42.5", 42.5),
            ("-15.25", -15.25),
            ("  42.5  ", 42.5),  # With whitespace
        ]
        
        for input_answer, expected in test_cases:
            submission = AnswerSubmission(
                user_id=user_id,
                problem_id=problem_id,
                submitted_answer=input_answer
            )
            assert submission.submitted_answer == expected
    
    def test_fraction_parsing(self):
        """Test parsing fraction formats."""
        user_id = uuid4()
        problem_id = uuid4()
        
        test_cases = [
            ("1/2", 0.5),
            ("3/4", 0.75),
            ("22/7", 22/7),
            ("-1/3", -1/3),
            ("  5/2  ", 2.5),  # With whitespace
        ]
        
        for input_answer, expected in test_cases:
            submission = AnswerSubmission(
                user_id=user_id,
                problem_id=problem_id,
                submitted_answer=input_answer
            )
            assert abs(submission.submitted_answer - expected) < 1e-6
    
    def test_invalid_answer_formats(self):
        """Test invalid answer format handling."""
        user_id = uuid4()
        problem_id = uuid4()
        
        invalid_answers = [
            None,
            "",
            "   ",
            "not a number",
            "1/0",  # Division by zero
            "1/2/3",  # Multiple divisions
            "1e11",  # Too large
        ]
        
        for invalid_answer in invalid_answers:
            with pytest.raises(ValueError):
                AnswerSubmission(
                    user_id=user_id,
                    problem_id=problem_id,
                    submitted_answer=invalid_answer
                )


class TestAnswerValidation:
    """Test answer validation logic."""
    
    def test_correct_answer_validation(self):
        """Test validation of correct answers."""
        problem = MathProblem(
            question="What is 2 + 2?",
            correct_answer=4.0,
            difficulty=DifficultyLevel.EASY
        )
        
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=4.0
        )
        
        result = validate_answer(submission, problem)
        
        assert result.is_correct is True
        assert result.submitted_value == 4.0
        assert result.correct_value == 4.0
        assert result.message is None
    
    def test_incorrect_answer_validation(self):
        """Test validation of incorrect answers."""
        problem = MathProblem(
            question="What is 2 + 2?",
            correct_answer=4.0,
            difficulty=DifficultyLevel.EASY
        )
        
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=5.0
        )
        
        result = validate_answer(submission, problem)
        
        assert result.is_correct is False
        assert result.submitted_value == 5.0
        assert result.correct_value == 4.0
        assert result.message is not None
    
    def test_tolerance_validation(self):
        """Test validation with floating point tolerance."""
        problem = MathProblem(
            question="What is 1/3?",
            correct_answer=0.333333,
            difficulty=DifficultyLevel.MEDIUM
        )
        
        # Very close answer (within tolerance)
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=0.333334
        )
        
        result = validate_answer(submission, problem)
        assert result.is_correct is True
        
        # Answer outside tolerance
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=0.5
        )
        
        result = validate_answer(submission, problem)
        assert result.is_correct is False
    
    def test_validation_result_messages(self):
        """Test validation result message generation."""
        problem = MathProblem(
            question="What is 10?",
            correct_answer=10.0,
            difficulty=DifficultyLevel.EASY
        )
        
        # Very close answer
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=10.05
        )
        result = validate_answer(submission, problem)
        assert "Very close" in result.message
        
        # Close answer
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=10.5
        )
        result = validate_answer(submission, problem)
        assert "Close" in result.message
        
        # Far answer
        submission = AnswerSubmission(
            user_id=uuid4(),
            problem_id=problem.id,
            submitted_answer=15.0
        )
        result = validate_answer(submission, problem)
        assert "Incorrect" in result.message