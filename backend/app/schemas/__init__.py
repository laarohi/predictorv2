"""Pydantic schemas for API request/response validation."""

from app.schemas.auth import (
    GoogleAuthCallback,
    Token,
    TokenPayload,
    UserCreate,
    UserLogin,
    UserRead,
    UserUpdate,
)
from app.schemas.fixture import FixtureRead, FixturesByGroup, LockStatus
from app.schemas.leaderboard import LeaderboardEntry, PointBreakdown, UserPoints
from app.schemas.prediction import (
    BracketPrediction,
    BracketPredictionUpdate,
    MatchPredictionCreate,
    MatchPredictionRead,
    MatchPredictionUpdate,
)
from app.schemas.score import LiveScoreResponse, ScoreRead, ScoreUpdate

__all__ = [
    # Auth
    "UserCreate",
    "UserLogin",
    "UserRead",
    "UserUpdate",
    "Token",
    "TokenPayload",
    "GoogleAuthCallback",
    # Fixtures
    "FixtureRead",
    "FixturesByGroup",
    "LockStatus",
    # Predictions
    "MatchPredictionCreate",
    "MatchPredictionRead",
    "MatchPredictionUpdate",
    "BracketPrediction",
    "BracketPredictionUpdate",
    # Scores
    "ScoreRead",
    "ScoreUpdate",
    "LiveScoreResponse",
    # Leaderboard
    "LeaderboardEntry",
    "PointBreakdown",
    "UserPoints",
]
