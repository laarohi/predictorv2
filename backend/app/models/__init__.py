"""SQLModel database models."""

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import AuthProvider, User

__all__ = [
    "User",
    "AuthProvider",
    "Competition",
    "Fixture",
    "MatchStatus",
    "MatchPrediction",
    "TeamPrediction",
    "PredictionPhase",
    "Score",
]
