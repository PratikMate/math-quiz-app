"""
Repository classes for database operations with async support.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy import select, update, delete, desc, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import User, Problem, Submission


class BaseRepository:
    """Base repository class with common database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def commit(self):
        """Commit the current transaction."""
        await self.session.commit()
    
    async def rollback(self):
        """Rollback the current transaction."""
        await self.session.rollback()
    
    async def refresh(self, instance):
        """Refresh an instance from the database."""
        await self.session.refresh(instance)


class UserRepository(BaseRepository):
    """Repository for User model operations."""
    
    async def create_user(self, username: str) -> User:
        """
        Create a new user.
        
        Args:
            username: Unique username for the user
            
        Returns:
            User: Created user instance
        """
        user = User(username=username)
        self.session.add(user)
        await self.session.flush()  # Get the ID without committing
        return user
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            user_id: User UUID
            
        Returns:
            User or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username to search for
            
        Returns:
            User or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create_user(self, username: str) -> tuple[User, bool]:
        """
        Get existing user or create new one.
        
        Args:
            username: Username to search for or create
            
        Returns:
            Tuple of (User, created_flag)
        """
        user = await self.get_user_by_username(username)
        if user:
            return user, False
        
        user = await self.create_user(username)
        return user, True
    
    async def update_user_stats(
        self, 
        user_id: UUID, 
        total_wins: Optional[int] = None,
        total_problems_attempted: Optional[int] = None,
        best_response_time: Optional[float] = None
    ) -> Optional[User]:
        """
        Update user statistics.
        
        Args:
            user_id: User UUID
            total_wins: New total wins count
            total_problems_attempted: New total problems attempted count
            best_response_time: New best response time
            
        Returns:
            Updated User or None if not found
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        if total_wins is not None:
            user.total_wins = total_wins
        if total_problems_attempted is not None:
            user.total_problems_attempted = total_problems_attempted
        if best_response_time is not None:
            if user.best_response_time is None or best_response_time < user.best_response_time:
                user.best_response_time = best_response_time
        
        user.update_last_active()
        return user
    
    async def get_top_users(self, limit: int = 10) -> List[User]:
        """
        Get top users by total wins.
        
        Args:
            limit: Maximum number of users to return
            
        Returns:
            List of top users
        """
        result = await self.session.execute(
            select(User)
            .order_by(desc(User.total_wins), User.best_response_time.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_user_stats(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive user statistics.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary with user stats or None if user not found
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Get additional stats from submissions
        submission_stats = await self.session.execute(
            select(
                func.count(Submission.id).label('total_submissions'),
                func.count(Submission.id).filter(Submission.is_correct == True).label('correct_submissions'),
                func.avg(Submission.response_time_ms).label('avg_response_time')
            )
            .where(Submission.user_id == user_id)
        )
        stats = submission_stats.first()
        
        return {
            'user_id': str(user.id),
            'username': user.username,
            'total_wins': user.total_wins,
            'total_problems_attempted': user.total_problems_attempted,
            'best_response_time': user.best_response_time,
            'win_rate': user.win_rate,
            'created_at': user.created_at,
            'last_active': user.last_active,
            'total_submissions': stats.total_submissions or 0,
            'correct_submissions': stats.correct_submissions or 0,
            'avg_response_time': float(stats.avg_response_time) if stats.avg_response_time else None
        }


class ProblemRepository(BaseRepository):
    """Repository for Problem model operations."""
    
    async def create_problem(
        self, 
        question: str, 
        correct_answer: float, 
        difficulty: str
    ) -> Problem:
        """
        Create a new problem.
        
        Args:
            question: Problem question text
            correct_answer: Correct numerical answer
            difficulty: Difficulty level (easy, medium, hard)
            
        Returns:
            Problem: Created problem instance
        """
        problem = Problem(
            question=question,
            correct_answer=correct_answer,
            difficulty=difficulty
        )
        self.session.add(problem)
        await self.session.flush()
        return problem
    
    async def get_problem_by_id(self, problem_id: UUID) -> Optional[Problem]:
        """
        Get problem by ID with solver information.
        
        Args:
            problem_id: Problem UUID
            
        Returns:
            Problem or None if not found
        """
        result = await self.session.execute(
            select(Problem)
            .options(selectinload(Problem.solver))
            .where(Problem.id == problem_id)
        )
        return result.scalar_one_or_none()
    
    async def mark_problem_solved(
        self, 
        problem_id: UUID, 
        user_id: UUID, 
        solved_time: Optional[datetime] = None
    ) -> Optional[Problem]:
        """
        Mark a problem as solved by a user.
        
        Args:
            problem_id: Problem UUID
            user_id: User UUID who solved it
            solved_time: When it was solved (defaults to now)
            
        Returns:
            Updated Problem or None if not found
        """
        problem = await self.get_problem_by_id(problem_id)
        if not problem:
            return None
        
        problem.mark_as_solved(user_id, solved_time)
        return problem
    
    async def get_recent_problems(self, limit: int = 10) -> List[Problem]:
        """
        Get recently created problems.
        
        Args:
            limit: Maximum number of problems to return
            
        Returns:
            List of recent problems
        """
        result = await self.session.execute(
            select(Problem)
            .options(selectinload(Problem.solver))
            .order_by(desc(Problem.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_problems_by_difficulty(self, difficulty: str, limit: int = 10) -> List[Problem]:
        """
        Get problems by difficulty level.
        
        Args:
            difficulty: Difficulty level to filter by
            limit: Maximum number of problems to return
            
        Returns:
            List of problems with specified difficulty
        """
        result = await self.session.execute(
            select(Problem)
            .where(Problem.difficulty == difficulty)
            .order_by(desc(Problem.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_unsolved_problems(self, limit: int = 10) -> List[Problem]:
        """
        Get unsolved problems.
        
        Args:
            limit: Maximum number of problems to return
            
        Returns:
            List of unsolved problems
        """
        result = await self.session.execute(
            select(Problem)
            .where(Problem.solved_by.is_(None))
            .order_by(desc(Problem.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class SubmissionRepository(BaseRepository):
    """Repository for Submission model operations."""
    
    async def create_submission(
        self,
        user_id: UUID,
        problem_id: UUID,
        submitted_answer: float,
        is_correct: bool,
        response_time_ms: int
    ) -> Submission:
        """
        Create a new submission.
        
        Args:
            user_id: User UUID
            problem_id: Problem UUID
            submitted_answer: User's submitted answer
            is_correct: Whether the answer is correct
            response_time_ms: Response time in milliseconds
            
        Returns:
            Submission: Created submission instance
        """
        submission = Submission(
            user_id=user_id,
            problem_id=problem_id,
            submitted_answer=submitted_answer,
            is_correct=is_correct,
            response_time_ms=response_time_ms
        )
        self.session.add(submission)
        await self.session.flush()
        return submission
    
    async def get_submission_by_id(self, submission_id: UUID) -> Optional[Submission]:
        """
        Get submission by ID with user and problem information.
        
        Args:
            submission_id: Submission UUID
            
        Returns:
            Submission or None if not found
        """
        result = await self.session.execute(
            select(Submission)
            .options(selectinload(Submission.user), selectinload(Submission.problem))
            .where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_submissions(
        self, 
        user_id: UUID, 
        limit: int = 50
    ) -> List[Submission]:
        """
        Get submissions by user.
        
        Args:
            user_id: User UUID
            limit: Maximum number of submissions to return
            
        Returns:
            List of user's submissions
        """
        result = await self.session.execute(
            select(Submission)
            .options(selectinload(Submission.problem))
            .where(Submission.user_id == user_id)
            .order_by(desc(Submission.submitted_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_problem_submissions(
        self, 
        problem_id: UUID, 
        limit: int = 50
    ) -> List[Submission]:
        """
        Get submissions for a specific problem.
        
        Args:
            problem_id: Problem UUID
            limit: Maximum number of submissions to return
            
        Returns:
            List of problem's submissions
        """
        result = await self.session.execute(
            select(Submission)
            .options(selectinload(Submission.user))
            .where(Submission.problem_id == problem_id)
            .order_by(Submission.submitted_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_winning_submission(self, problem_id: UUID) -> Optional[Submission]:
        """
        Get the winning (first correct) submission for a problem.
        
        Args:
            problem_id: Problem UUID
            
        Returns:
            Winning submission or None if no correct submissions
        """
        result = await self.session.execute(
            select(Submission)
            .options(selectinload(Submission.user))
            .where(
                and_(
                    Submission.problem_id == problem_id,
                    Submission.is_correct == True
                )
            )
            .order_by(Submission.submitted_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_user_correct_submissions(
        self, 
        user_id: UUID, 
        limit: int = 50
    ) -> List[Submission]:
        """
        Get user's correct submissions.
        
        Args:
            user_id: User UUID
            limit: Maximum number of submissions to return
            
        Returns:
            List of user's correct submissions
        """
        result = await self.session.execute(
            select(Submission)
            .options(selectinload(Submission.problem))
            .where(
                and_(
                    Submission.user_id == user_id,
                    Submission.is_correct == True
                )
            )
            .order_by(desc(Submission.submitted_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_fastest_submissions(self, limit: int = 10) -> List[Submission]:
        """
        Get fastest correct submissions across all problems.
        
        Args:
            limit: Maximum number of submissions to return
            
        Returns:
            List of fastest correct submissions
        """
        result = await self.session.execute(
            select(Submission)
            .options(selectinload(Submission.user), selectinload(Submission.problem))
            .where(Submission.is_correct == True)
            .order_by(Submission.response_time_ms.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


class RepositoryManager:
    """
    Manager class that provides access to all repositories with a shared session.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.problems = ProblemRepository(session)
        self.submissions = SubmissionRepository(session)
    
    async def commit(self):
        """Commit all changes in the current transaction."""
        await self.session.commit()
    
    async def rollback(self):
        """Rollback all changes in the current transaction."""
        await self.session.rollback()