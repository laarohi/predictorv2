"""API route modules."""

from fastapi import APIRouter

from app.api import admin, auth, competition, fixtures, leaderboard, predictions, scores

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(competition.router, prefix="/competition", tags=["competition"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(fixtures.router, prefix="/fixtures", tags=["fixtures"])
api_router.include_router(scores.router, prefix="/scores", tags=["scores"])
api_router.include_router(leaderboard.router, prefix="/leaderboard", tags=["leaderboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
