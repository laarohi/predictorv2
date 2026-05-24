"""SQLModel database models."""

from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.competition import Competition
from app.models.email_send import EmailSend
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.magic_link import MagicLinkToken
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.prediction_history import (
    BonusPredictionHistory,
    MatchPredictionHistory,
    PredictionAction,
    PredictionSource,
    TeamPredictionHistory,
)
from app.models.score import Score
from app.models.user import AuthProvider, User

__all__ = [
    "User",
    "AuthProvider",
    "BonusAnswer",
    "BonusPrediction",
    "BonusPredictionHistory",
    "Competition",
    "EmailSend",
    "Fixture",
    "MatchStatus",
    "LeaderboardSnapshot",
    "MagicLinkToken",
    "MatchPrediction",
    "MatchPredictionHistory",
    "PredictionAction",
    "PredictionSource",
    "TeamPrediction",
    "TeamPredictionHistory",
    "PredictionPhase",
    "Score",
]
