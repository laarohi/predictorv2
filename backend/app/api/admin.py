"""Admin API routes for dashboard and management."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.dependencies import AdminUser, DbSession
from app.models._datetime import aware_utc, utc_now
from app.models.bonus import BonusAnswer
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.audit_log import build_user_history
from app.services.bonus import (
    compute_bonus_answers_for_competition,
    fetch_competition_teams,
    get_fifa_rankings,
    get_questions as get_bonus_questions,
)
from app.services.email import EmailSendError, send_email
from app.services.external_scores import get_score_provider, ExternalScore
from app.services.knockout_resolver import (
    ResolutionReport,
    apply_knockout_resolution,
)
from app.services.leaderboard import invalidate_cache
from app.services.receipts import build_phase1_receipt
from app.services.score_sync import sync_scores_once


router = APIRouter()


class AdminStats(BaseModel):
    """Admin dashboard statistics."""

    total_users: int
    active_users: int
    total_fixtures: int
    completed_fixtures: int
    live_fixtures: int
    total_predictions: int
    total_scores: int


class UserAdminView(BaseModel):
    """User data for admin view."""

    id: uuid.UUID
    email: str
    name: str
    auth_provider: str
    is_admin: bool
    is_active: bool
    paid: bool
    created_at: datetime
    prediction_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


class CompetitionAdminView(BaseModel):
    """Competition data for admin view."""

    id: uuid.UUID
    name: str
    entry_fee: float
    phase1_deadline: datetime | None
    is_phase2_active: bool
    phase2_activated_at: datetime | None
    phase2_bracket_deadline: datetime | None
    phase2_deadline: datetime | None
    is_active: bool
    fixture_count: int
    user_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


class Phase1DeadlineRequest(BaseModel):
    """Request to set Phase 1 deadline."""

    # AwareDatetime: a naive timestamp here would silently shift the lock by
    # the sender's UTC offset — the single most lock-critical field there is.
    deadline: AwareDatetime  # When Phase 1 predictions lock


class Phase2ActivateRequest(BaseModel):
    """Request to activate Phase 2."""

    bracket_deadline: AwareDatetime  # When Phase 2 bracket predictions lock


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    session: DbSession,
    _admin: AdminUser,
) -> AdminStats:
    """Get admin dashboard statistics."""
    # User counts
    total_users = await session.scalar(
        select(func.count(User.id)).where(User.is_ghost == False)  # noqa: E712
    )
    active_users = await session.scalar(
        select(func.count(User.id)).where(
            User.is_active == True, User.is_ghost == False  # noqa: E712
        )
    )

    # Fixture counts
    total_fixtures = await session.scalar(select(func.count(Fixture.id)))
    completed_fixtures = await session.scalar(
        select(func.count(Fixture.id)).where(Fixture.status == MatchStatus.FINISHED)
    )
    live_fixtures = await session.scalar(
        select(func.count(Fixture.id)).where(
            Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME])
        )
    )

    # Prediction and score counts
    total_predictions = await session.scalar(select(func.count(MatchPrediction.id)))
    total_scores = await session.scalar(select(func.count(Score.id)))

    return AdminStats(
        total_users=total_users or 0,
        active_users=active_users or 0,
        total_fixtures=total_fixtures or 0,
        completed_fixtures=completed_fixtures or 0,
        live_fixtures=live_fixtures or 0,
        total_predictions=total_predictions or 0,
        total_scores=total_scores or 0,
    )


@router.get("/users", response_model=list[UserAdminView])
async def get_all_users(
    session: DbSession,
    _admin: AdminUser,
) -> list[UserAdminView]:
    """Get all users with prediction counts (admin only)."""
    # Get users with prediction counts
    result = await session.execute(
        select(
            User,
            func.count(MatchPrediction.id).label("prediction_count")
        )
        .outerjoin(MatchPrediction, User.id == MatchPrediction.user_id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    rows = result.all()

    return [
        UserAdminView(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_provider=user.auth_provider.value,
            is_admin=user.is_admin,
            is_active=user.is_active,
            paid=user.paid,
            created_at=user.created_at,
            prediction_count=count,
        )
        for user, count in rows
    ]


@router.patch("/users/{user_id}/admin", response_model=UserAdminView)
async def toggle_user_admin(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle admin status for a user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_admin = not user.is_admin
    user.updated_at = utc_now()
    await session.commit()
    await session.refresh(user)

    # Get prediction count
    count = await session.scalar(
        select(func.count(MatchPrediction.id)).where(MatchPrediction.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        paid=user.paid,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.patch("/users/{user_id}/active", response_model=UserAdminView)
async def toggle_user_active(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle active status for a user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = not user.is_active
    user.updated_at = utc_now()
    await session.commit()
    await session.refresh(user)

    # Get prediction count
    count = await session.scalar(
        select(func.count(MatchPrediction.id)).where(MatchPrediction.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        paid=user.paid,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.patch("/users/{user_id}/paid", response_model=UserAdminView)
async def toggle_user_paid(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle paid status for a user (admin only). Used to track who has
    paid the competition entry fee."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.paid = not user.paid
    user.updated_at = utc_now()
    await session.commit()
    await session.refresh(user)

    count = await session.scalar(
        select(func.count(MatchPrediction.id)).where(MatchPrediction.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        paid=user.paid,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.get("/competitions", response_model=list[CompetitionAdminView])
async def get_all_competitions(
    session: DbSession,
    _admin: AdminUser,
) -> list[CompetitionAdminView]:
    """Get all competitions with stats (admin only)."""
    result = await session.execute(
        select(
            Competition,
            func.count(func.distinct(Fixture.id)).label("fixture_count"),
            func.count(func.distinct(User.id)).label("user_count"),
        )
        .outerjoin(Fixture, Competition.id == Fixture.competition_id)
        .outerjoin(User, Competition.id == User.competition_id)
        .group_by(Competition.id)
        .order_by(Competition.created_at.desc())
    )
    rows = result.all()

    return [
        CompetitionAdminView(
            id=comp.id,
            name=comp.name,
            entry_fee=float(comp.entry_fee),
            phase1_deadline=comp.phase1_deadline,
            is_phase2_active=comp.is_phase2_active,
            phase2_activated_at=comp.phase2_activated_at,
            phase2_bracket_deadline=comp.phase2_bracket_deadline,
            phase2_deadline=comp.phase2_deadline,
            is_active=comp.is_active,
            fixture_count=fixture_count,
            user_count=user_count,
        )
        for comp, fixture_count, user_count in rows
    ]


@router.post("/competition/phase2/activate")
async def activate_phase2(
    request: Phase2ActivateRequest,
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Activate Phase 2 for the active competition.

    This enables the Phase 2 tab for all users and sets the bracket deadline.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    if competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 is already active"
        )

    if request.bracket_deadline <= utc_now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bracket_deadline must be in the future",
        )

    # The bracket must lock before the first knockout match kicks off:
    # scoring counts every TeamPrediction row once a fixture finishes, so a
    # deadline after kickoff would let still-editable picks score (and leak
    # onto the leaderboard while others can still counter-pick).
    result = await session.execute(
        select(func.min(Fixture.kickoff)).where(
            Fixture.competition_id == competition.id,
            Fixture.stage != "group",
            Fixture.status == "scheduled",
        )
    )
    first_ko_kickoff = result.scalar_one_or_none()
    if first_ko_kickoff and request.bracket_deadline > aware_utc(first_ko_kickoff):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "bracket_deadline must not be after the first knockout "
                f"kickoff ({aware_utc(first_ko_kickoff).isoformat()})"
            ),
        )

    # Activate Phase 2
    competition.is_phase2_active = True
    competition.phase2_activated_at = utc_now()
    competition.phase2_bracket_deadline = request.bracket_deadline
    competition.updated_at = utc_now()

    await session.commit()

    # The "knockouts are live" push is fired by the scheduler tick
    # (send_phase2_opened), not here, so activation returns instantly instead
    # of blocking on a fan-out of sends.

    return {
        "status": "Phase 2 activated",
        "bracket_deadline": request.bracket_deadline.isoformat(),
        "activated_at": competition.phase2_activated_at.isoformat(),
    }


@router.post("/competition/phase2/deactivate")
async def deactivate_phase2(
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Deactivate Phase 2 for the active competition.

    This hides the Phase 2 tab. Useful for testing or rollback.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    if not competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 is not active"
        )

    # Deactivate Phase 2
    competition.is_phase2_active = False
    competition.updated_at = utc_now()

    await session.commit()

    return {"status": "Phase 2 deactivated"}


@router.post("/competition/phase1/deadline")
async def set_phase1_deadline(
    request: Phase1DeadlineRequest,
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Set the Phase 1 deadline for the active competition.

    This sets when group stage predictions lock.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    # One-way after lock: once the deadline has passed, predictions are
    # locked and the deadline must never move again — re-posting a later
    # deadline would silently reopen every Phase 1 prediction.
    if competition.phase1_deadline and utc_now() >= aware_utc(competition.phase1_deadline):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Phase 1 deadline has already passed; predictions are locked "
                "and the deadline can no longer be changed."
            ),
        )

    competition.phase1_deadline = request.deadline
    competition.updated_at = utc_now()

    await session.commit()

    return {
        "status": "Phase 1 deadline set",
        "deadline": request.deadline.isoformat(),
    }


class SyncScoresResponse(BaseModel):
    """Response from score sync operation."""

    synced: int
    updated: int
    errors: list[str]


@router.post("/scores/sync", response_model=SyncScoresResponse)
async def sync_scores_from_api(
    session: DbSession,
    _admin: AdminUser,
) -> SyncScoresResponse:
    """Sync live scores from external API (admin only).

    Thin wrapper around `score_sync.sync_scores_once`. The same code path
    powers the background scheduler — this endpoint is the manual escape
    hatch.
    """
    result = await sync_scores_once(session)
    return SyncScoresResponse(
        synced=result.synced,
        updated=result.updated,
        errors=result.errors,
    )


# ============================================================================
# Bonus question answers (admin sets the correct answer per question)
# ============================================================================


class BonusAnswerView(BaseModel):
    """One question + the full list of correct answers (empty if unresolved),
    for the admin UI. Multiple entries in `correct_answers` indicate a tie —
    every entry awards full points to any user who picked it.

    `computed_answers` is the auto-derived answer(s) calculated from
    fixtures + scores (for group_stage and top_flop questions). It's
    purely advisory: the admin can apply it via the UI or override with
    a manual entry. Awards-category questions always have an empty
    `computed_answers` since they're manual-only."""

    question_id: str
    label: str
    category: str
    points: int
    input_type: str
    correct_answers: list[str]
    computed_answers: list[str]
    resolved_at: datetime | None


class BonusAnswerUpdate(BaseModel):
    """Payload for admin setting / replacing the correct answers for a
    question. The full list replaces whatever was previously stored —
    empty list un-resolves the question."""

    question_id: str
    correct_answers: list[str]


def _build_view(
    q,
    rows: list[BonusAnswer] | None,
    computed: list[str] | None = None,
) -> BonusAnswerView:
    """Helper: assemble a BonusAnswerView from a question definition +
    its (possibly empty) list of stored answer rows. `resolved_at` is the
    most recent resolution timestamp across rows; falsy if no rows.
    `computed` is the auto-derived suggestion (empty for awards or when
    no data is available yet)."""
    rs = rows or []
    return BonusAnswerView(
        question_id=q.id,
        label=q.label,
        category=q.category,
        points=q.points,
        input_type=q.input_type,
        correct_answers=[r.correct_answer for r in rs],
        computed_answers=computed or [],
        resolved_at=max((r.resolved_at for r in rs), default=None) if rs else None,
    )


@router.get("/bonus/answers", response_model=list[BonusAnswerView])
async def list_bonus_answers(
    session: DbSession,
    _admin: AdminUser,
) -> list[BonusAnswerView]:
    """List every bonus question with its full list of stored correct
    answers. Joins the YAML question list with the per-competition
    `bonus_answers` rows; questions with no stored answer get an empty
    list and a null `resolved_at`.
    """
    competition_teams = await fetch_competition_teams(session)
    rankings = await get_fifa_rankings(session)
    qs = get_bonus_questions(competition_teams=competition_teams, rankings=rankings)
    comp_result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        return [_build_view(q, None) for q in qs]

    ans_result = await session.execute(
        select(BonusAnswer).where(BonusAnswer.competition_id == competition.id)
    )
    rows_by_qid: dict[str, list[BonusAnswer]] = {}
    for row in ans_result.scalars().all():
        rows_by_qid.setdefault(row.question_id, []).append(row)

    # Auto-computed suggestions for group_stage + top_flop questions.
    # Awards have no entries here (manual-only) and the helper returns []
    # for any qid it doesn't know about, so we don't need to special-case
    # them — they just see an empty `computed_answers` field.
    computed_by_qid = await compute_bonus_answers_for_competition(
        session, competition.id
    )

    return [
        _build_view(q, rows_by_qid.get(q.id), computed_by_qid.get(q.id, []))
        for q in qs
    ]


@router.post("/bonus/answers", response_model=BonusAnswerView)
async def set_bonus_answer(
    payload: BonusAnswerUpdate,
    session: DbSession,
    _admin: AdminUser,
) -> BonusAnswerView:
    """Replace the correct answers for a bonus question. Empty list
    un-resolves the question (all existing rows deleted). Multiple
    entries record a tie — every entry awards full points. Invalidates
    the leaderboard cache so points propagate on the next fetch."""
    valid_questions = {q.id: q for q in get_bonus_questions()}
    if payload.question_id not in valid_questions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown question_id: {payload.question_id}",
        )

    comp_result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition",
        )

    # Normalise + dedupe inbound answers, dropping empty entries.
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in payload.correct_answers:
        s = (raw or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)

    q = valid_questions[payload.question_id]

    # Replace-all semantics: delete every row for this (comp, question)
    # and re-insert the new set. Simpler than diffing, and the table is
    # tiny (12 questions × ~3 answers).
    existing_rows = (
        await session.execute(
            select(BonusAnswer)
            .where(BonusAnswer.competition_id == competition.id)
            .where(BonusAnswer.question_id == payload.question_id)
        )
    ).scalars().all()
    for row in existing_rows:
        await session.delete(row)

    new_rows: list[BonusAnswer] = []
    for ans in cleaned:
        row = BonusAnswer(
            competition_id=competition.id,
            question_id=payload.question_id,
            correct_answer=ans,
        )
        session.add(row)
        new_rows.append(row)
    await session.commit()
    for row in new_rows:
        await session.refresh(row)
    invalidate_cache()

    # Re-compute the auto-suggestion so the frontend can keep showing the
    # "Use computed" chip after a manual save.
    computed_by_qid = await compute_bonus_answers_for_competition(
        session, competition.id
    )
    return _build_view(q, new_rows, computed_by_qid.get(q.id, []))


class UserHistoryResponse(BaseModel):
    """Audit log view for one user.

    `user` carries enough context to title the page; `events` is a flat
    list newest-first. Client-side toggles (phase / show locks /
    group-by) all operate on this list.
    """

    user: UserAdminView
    events: list[dict]


@router.get("/users/{user_id}/history", response_model=UserHistoryResponse)
async def get_user_audit_history(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserHistoryResponse:
    """Prettified audit log for one user — for dispute resolution.

    Returns every recorded change to this user's predictions across the
    three history tables, formatted for human reading. The page is
    designed so a screenshot of a row is sufficient to settle a dispute.
    """
    # Load the user.
    user_row = await session.execute(select(User).where(User.id == user_id))
    user = user_row.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    prediction_count = await session.scalar(
        select(func.count(MatchPrediction.id)).where(MatchPrediction.user_id == user_id)
    )

    events = await build_user_history(session, user_id)

    return UserHistoryResponse(
        user=UserAdminView(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_provider=user.auth_provider.value,
            is_admin=user.is_admin,
            is_active=user.is_active,
            paid=user.paid,
            created_at=user.created_at,
            prediction_count=prediction_count or 0,
        ),
        events=[e.to_dict() for e in events],
    )


class TestReceiptResponse(BaseModel):
    """Result of a test-receipt send. Returns the Resend message id so the
    admin can correlate against their Resend dashboard if anything's
    weird (e.g. the email lands in spam — they can check the dashboard's
    delivery log)."""

    status: str  # "sent" | "skipped" (api key blank)
    message_id: str | None
    sent_to: str
    subject: str


@router.post("/receipts/test/phase1", response_model=TestReceiptResponse)
async def send_phase1_test_receipt(
    session: DbSession,
    admin: AdminUser,
) -> TestReceiptResponse:
    """Send the admin a copy of their own Phase 1 receipt — for previewing
    the email format and verifying Resend wiring before the real deadline.

    Always sends to the calling admin's own email. Does not write to any
    idempotency table — the admin can fire repeatedly to iterate on the
    template. The actual production trigger (the scheduler tick that
    fires at phase1_deadline) is separate and will be wired later.
    """
    receipt = await build_phase1_receipt(session, admin)
    try:
        result = await send_email(
            to=admin.email,
            subject=receipt.subject,
            html=receipt.html,
            text=receipt.text,
        )
    except EmailSendError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email send failed: {e}",
        )

    return TestReceiptResponse(
        status="skipped" if not result.ok else "sent",
        message_id=result.message_id,
        sent_to=admin.email,
        subject=receipt.subject,
    )


# ---------------------------------------------------------------------------
# Knockout bracket resolution
# ---------------------------------------------------------------------------


class KnockoutMatchupView(BaseModel):
    """One computed knockout matchup (FIFA match number → teams)."""

    match_number: int
    home_team: str
    away_team: str


class KnockoutStampChangeView(BaseModel):
    """One knockout fixture row that was (or would be) stamped."""

    external_id: str
    match_number: int
    stage: str
    old_home: str
    old_away: str
    new_home: str
    new_away: str
    old_match_number: int | None


class ResolveKnockoutResponse(BaseModel):
    """Result of POST /fixtures/resolve-knockout.

    In dry-run/preview mode nothing is committed; `changes` still lists every
    row that WOULD be stamped, and `matchups` is the full computed table for
    human verification against the official bracket.
    """

    dry_run: bool
    groups_complete: bool
    r32_resolved: bool
    changed_count: int
    matchups: list[KnockoutMatchupView]
    changes: list[KnockoutStampChangeView]
    unresolved: list[int]
    notes: list[str]


def _resolution_to_response(report: ResolutionReport) -> ResolveKnockoutResponse:
    return ResolveKnockoutResponse(
        dry_run=report.dry_run,
        groups_complete=report.groups_complete,
        r32_resolved=report.r32_resolved,
        changed_count=report.changed_count,
        matchups=[
            KnockoutMatchupView(match_number=mn, home_team=h, away_team=a)
            for mn, (h, a) in report.matchups.items()
        ],
        changes=[
            KnockoutStampChangeView(
                external_id=c.external_id,
                match_number=c.match_number,
                stage=c.stage,
                old_home=c.old_home,
                old_away=c.old_away,
                new_home=c.new_home,
                new_away=c.new_away,
                old_match_number=c.old_match_number,
            )
            for c in report.changes
        ],
        unresolved=report.unresolved,
        notes=report.notes,
    )


@router.post("/fixtures/resolve-knockout", response_model=ResolveKnockoutResponse)
async def resolve_knockout_fixtures(
    session: DbSession,
    _admin: AdminUser,
    dry_run: bool = True,
) -> ResolveKnockoutResponse:
    """Stamp real team names + FIFA match_number onto the knockout fixtures.

    Computes the real knockout matchups from ACTUAL group standings (R32) and
    actual prior-round results (R16→Final) using the official FIFA 2026 bracket
    routing, then stamps them onto the existing knockout Fixture rows (matched
    by Football-Data external_id). Preserves each row's kickoff/external_id and
    never deletes rows.

    `dry_run` defaults to True (preview): returns the computed matchups and the
    list of rows that WOULD change, committing nothing. Pass `dry_run=false`
    (query param) to apply and commit. Idempotent: re-applying the same results
    is a no-op.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    report = await apply_knockout_resolution(
        session, competition, dry_run=dry_run
    )

    if not dry_run and report.changed_count:
        # Stamped team names feed the bracket / advancement scoring views; drop
        # the cached leaderboard so the change is reflected immediately.
        invalidate_cache()

    return _resolution_to_response(report)
