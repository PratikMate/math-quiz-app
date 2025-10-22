"""
Answer submission processing service with concurrency handling and winner detection.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import UUID

from ..models.math_problem import (
    MathProblem, 
    AnswerSubmission, 
    AnswerValidationResult,
    validate_answer
)


logger = logging.getLogger(__name__)


class SubmissionResult:
    """Result of processing an answer submission."""
    
    def __init__(
        self,
        submission_id: str,
        user_id: str,
        is_correct: bool,
        is_winner: bool,
        server_timestamp: datetime,
        validation_result: AnswerValidationResult,
        message: str = ""
    ):
        self.submission_id = submission_id
        self.user_id = user_id
        self.is_correct = is_correct
        self.is_winner = is_winner
        self.server_timestamp = server_timestamp
        self.validation_result = validation_result
        self.message = message


class SubmissionProcessor:
    """
    Handles answer submission processing with fair timing and winner detection.
    
    Implements server-side timestamping, submission validation, and atomic
    winner detection to ensure fair competition between users.
    """
    
    def __init__(self):
        """Initialize submission processor."""
        # Track submissions per problem for winner detection
        self._problem_submissions: Dict[str, List[SubmissionResult]] = {}
        
        # Track which problems have been solved (have winners)
        self._solved_problems: Set[str] = set()
        
        # Lock for atomic winner detection
        self._submission_locks: Dict[str, asyncio.Lock] = {}
        
        # Track users who have already submitted for each problem
        self._user_submissions: Dict[str, Set[str]] = {}  # problem_id -> set of user_ids
    
    async def process_submission(
        self,
        user_id: str,
        problem: MathProblem,
        submitted_answer: any,
        submission_id: Optional[str] = None
    ) -> SubmissionResult:
        """
        Process an answer submission with server-side timestamping and winner detection.
        
        Args:
            user_id: ID of the user submitting the answer
            problem: The math problem being answered
            submitted_answer: The user's submitted answer
            submission_id: Optional submission ID for tracking
            
        Returns:
            SubmissionResult with processing details
            
        Raises:
            ValueError: If submission is invalid or duplicate
        """
        problem_id = str(problem.id)
        submission_id = submission_id or f"{user_id}_{problem_id}_{datetime.utcnow().timestamp()}"
        
        # Server-side timestamp for fair timing
        server_timestamp = datetime.utcnow()
        
        # Check if problem is already solved
        if problem_id in self._solved_problems:
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=False,
                is_winner=False,
                server_timestamp=server_timestamp,
                validation_result=AnswerValidationResult(
                    is_correct=False,
                    submitted_value=0.0,
                    correct_value=problem.correct_answer,
                    message="Problem already solved"
                ),
                message="This problem has already been solved by another user"
            )
        
        # Check for duplicate submission from same user
        if problem_id not in self._user_submissions:
            self._user_submissions[problem_id] = set()
        
        if user_id in self._user_submissions[problem_id]:
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=False,
                is_winner=False,
                server_timestamp=server_timestamp,
                validation_result=AnswerValidationResult(
                    is_correct=False,
                    submitted_value=0.0,
                    correct_value=problem.correct_answer,
                    message="Duplicate submission"
                ),
                message="You have already submitted an answer for this problem"
            )
        
        # Create submission object for validation
        try:
            # Handle user_id conversion - for session IDs, create a deterministic UUID
            if isinstance(user_id, str):
                import hashlib
                user_hash = hashlib.md5(user_id.encode()).hexdigest()
                user_uuid = UUID(user_hash)
            else:
                user_uuid = user_id
                
            submission = AnswerSubmission(
                user_id=user_uuid,
                problem_id=problem.id,
                submitted_answer=submitted_answer,
                submitted_at=server_timestamp
            )
        except Exception as e:
            logger.error(f"Failed to create submission object: {e}")
            return SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=False,
                is_winner=False,
                server_timestamp=server_timestamp,
                validation_result=AnswerValidationResult(
                    is_correct=False,
                    submitted_value=0.0,
                    correct_value=problem.correct_answer,
                    message="Invalid submission format"
                ),
                message=f"Invalid submission format: {str(e)}"
            )
        
        # Validate the answer
        validation_result = validate_answer(submission, problem)
        
        # Get or create lock for this problem
        if problem_id not in self._submission_locks:
            self._submission_locks[problem_id] = asyncio.Lock()
        
        # Atomic winner detection using lock
        async with self._submission_locks[problem_id]:
            # Double-check if problem was solved while waiting for lock
            if problem_id in self._solved_problems:
                return SubmissionResult(
                    submission_id=submission_id,
                    user_id=user_id,
                    is_correct=validation_result.is_correct,
                    is_winner=False,
                    server_timestamp=server_timestamp,
                    validation_result=validation_result,
                    message="Problem was solved while processing your submission"
                )
            
            # Mark user as having submitted for this problem
            self._user_submissions[problem_id].add(user_id)
            
            # Create submission result
            is_winner = False
            message = ""
            
            if validation_result.is_correct:
                # This is the first correct answer - user wins!
                is_winner = True
                self._solved_problems.add(problem_id)
                message = "Congratulations! You are the winner!"
                
                logger.info(f"Winner detected: User {user_id} solved problem {problem_id}")
            else:
                message = validation_result.message or "Incorrect answer"
            
            # Store submission for tracking
            result = SubmissionResult(
                submission_id=submission_id,
                user_id=user_id,
                is_correct=validation_result.is_correct,
                is_winner=is_winner,
                server_timestamp=server_timestamp,
                validation_result=validation_result,
                message=message
            )
            
            # Add to problem submissions list
            if problem_id not in self._problem_submissions:
                self._problem_submissions[problem_id] = []
            self._problem_submissions[problem_id].append(result)
            
            return result
    
    def get_problem_submissions(self, problem_id: str) -> List[SubmissionResult]:
        """
        Get all submissions for a specific problem.
        
        Args:
            problem_id: The problem ID
            
        Returns:
            List of SubmissionResult objects for the problem
        """
        return self._problem_submissions.get(problem_id, [])
    
    def get_winner(self, problem_id: str) -> Optional[SubmissionResult]:
        """
        Get the winner submission for a specific problem.
        
        Args:
            problem_id: The problem ID
            
        Returns:
            SubmissionResult of the winner, or None if no winner yet
        """
        submissions = self.get_problem_submissions(problem_id)
        for submission in submissions:
            if submission.is_winner:
                return submission
        return None
    
    def is_problem_solved(self, problem_id: str) -> bool:
        """
        Check if a problem has been solved (has a winner).
        
        Args:
            problem_id: The problem ID
            
        Returns:
            True if problem is solved, False otherwise
        """
        return problem_id in self._solved_problems
    
    def reset_problem_state(self, problem_id: str) -> None:
        """
        Reset the state for a specific problem (for question rotation).
        
        Args:
            problem_id: The problem ID to reset
        """
        # Remove from solved problems
        self._solved_problems.discard(problem_id)
        
        # Clear submissions
        self._problem_submissions.pop(problem_id, None)
        
        # Clear user submissions tracking
        self._user_submissions.pop(problem_id, None)
        
        # Remove lock (will be recreated if needed)
        self._submission_locks.pop(problem_id, None)
        
        logger.info(f"Reset state for problem {problem_id}")
    
    def get_submission_stats(self) -> Dict:
        """
        Get statistics about submissions for monitoring.
        
        Returns:
            Dictionary with submission statistics
        """
        total_submissions = sum(len(subs) for subs in self._problem_submissions.values())
        solved_problems_count = len(self._solved_problems)
        active_problems = len(self._problem_submissions) - solved_problems_count
        
        return {
            "total_submissions": total_submissions,
            "solved_problems": solved_problems_count,
            "active_problems": active_problems,
            "problems_with_submissions": len(self._problem_submissions)
        }