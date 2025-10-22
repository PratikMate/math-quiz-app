"""
SQLAlchemy database models for the competitive math quiz system.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .connection import Base


class User(Base):
    """
    User model for storing user information and performance data.
    """
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        index=True
    )
    
    # User information
    username: Mapped[str] = mapped_column(
        String(50), 
        unique=True, 
        nullable=False,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Performance statistics
    total_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_problems_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_response_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Relationships
    problems_solved: Mapped[list["Problem"]] = relationship(
        "Problem", 
        back_populates="solver",
        foreign_keys="Problem.solved_by"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', wins={self.total_wins})>"
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate as percentage."""
        if self.total_problems_attempted == 0:
            return 0.0
        return (self.total_wins / self.total_problems_attempted) * 100
    
    def update_last_active(self):
        """Update the last_active timestamp to current time."""
        self.last_active = datetime.utcnow()


class Problem(Base):
    """
    Problem model for storing math problems and their solutions.
    """
    __tablename__ = "problems"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        index=True
    )
    
    # Problem content
    question: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    solved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Solution tracking
    solved_by: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )
    
    # Relationships
    solver: Mapped[Optional["User"]] = relationship(
        "User", 
        back_populates="problems_solved",
        foreign_keys=[solved_by]
    )
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", 
        back_populates="problem",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Problem(id={self.id}, difficulty='{self.difficulty}', solved={self.solved_by is not None})>"
    
    @property
    def is_solved(self) -> bool:
        """Check if the problem has been solved."""
        return self.solved_by is not None and self.solved_at is not None
    
    def mark_as_solved(self, user_id: UUID, solved_time: Optional[datetime] = None):
        """Mark the problem as solved by a specific user."""
        self.solved_by = user_id
        self.solved_at = solved_time or datetime.utcnow()


class Submission(Base):
    """
    Submission model for storing user answer attempts.
    """
    __tablename__ = "submissions"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        index=True
    )
    
    # Foreign keys
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )
    problem_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("problems.id"),
        nullable=False,
        index=True
    )
    
    # Submission data
    submitted_answer: Mapped[float] = mapped_column(Float, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    
    # Timing information
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="submissions")
    problem: Mapped["Problem"] = relationship("Problem", back_populates="submissions")
    
    def __repr__(self) -> str:
        return f"<Submission(id={self.id}, user_id={self.user_id}, correct={self.is_correct}, time={self.response_time_ms}ms)>"
    
    @property
    def response_time_seconds(self) -> float:
        """Get response time in seconds."""
        return self.response_time_ms / 1000.0