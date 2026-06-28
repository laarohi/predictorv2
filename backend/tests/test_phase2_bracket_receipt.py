"""Tests for the Phase 2 knockout-bracket receipt + its scheduler gate.

Sent when phase2_bracket_deadline passes — each player's locked knockout
bracket. Mirrors the read-time scoring fallback EXACTLY: a player who never
re-picked gets their carried-over Phase 1 bracket (with a note), because that's
what actually scores. Counts only (blind pool intact); idempotent via
email_sends kind 'phase2_bracket'.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.competition import Competition
from app.models.user import User
from app.services.email import EMAIL_SKIPPED, EmailResult, EmailSendError
from app.services.receipts import (
    BatchSendResult,
    build_phase2_bracket_receipt,
    send_phase2_bracket_receipts,
)
from app.services.score_scheduler import _maybe_send_phase2_bracket_receipts


def _user(name: str = "x") -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.name = name
    u.email = f"{name}@example.com"
    u.is_active = True
    return u


def _team_pred(stage: str, team: str):
    p = MagicMock()
    p.stage = stage
    p.team = team
    return p


def _competition(active: bool = True, deadline_past: bool = True) -> Competition:
    comp = MagicMock(spec=Competition)
    comp.id = uuid.uuid4()
    comp.is_phase2_active = active
    comp.phase2_bracket_deadline = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
        if deadline_past
        else datetime.now(timezone.utc) + timedelta(hours=1)
    )
    return comp


def _receipt():
    r = MagicMock()
    r.subject = "test"
    r.html = "<p>h</p>"
    r.text = "body"
    return r


def _mock_session(users, already_sent_ids=None) -> AsyncMock:
    session = AsyncMock()
    user_result = MagicMock()
    user_result.scalars.return_value.all.return_value = users
    sent_result = MagicMock()
    sent_result.scalars.return_value.all.return_value = list(already_sent_ids or [])
    session.execute.side_effect = [user_result, sent_result]
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ── build_phase2_bracket_receipt ─────────────────────────────────────────────


class TestBuildReceipt:
    @pytest.mark.asyncio
    @patch("app.services.receipts._load_phase2_bracket_predictions", new_callable=AsyncMock)
    async def test_phase2_rows_shown_not_carried_over(self, mock_p2):
        mock_p2.return_value = [
            _team_pred("winner", "Brazil"),
            _team_pred("final", "Brazil"),
            _team_pred("final", "France"),
        ]
        receipt, has = await build_phase2_bracket_receipt(AsyncMock(), _user("amy"))
        assert has is True
        assert "knockout bracket" in receipt.subject.lower()
        assert "Brazil" in receipt.text and "France" in receipt.text
        # Updated bracket → NOT the carry-over note.
        assert "carries over" not in receipt.text
        assert "re-picked against the real Round of 32" in receipt.text

    @pytest.mark.asyncio
    @patch("app.services.receipts._load_bracket_predictions", new_callable=AsyncMock)
    @patch("app.services.receipts._load_phase2_bracket_predictions", new_callable=AsyncMock)
    async def test_carries_over_phase1_when_no_phase2_rows(self, mock_p2, mock_p1):
        mock_p2.return_value = []  # never re-picked
        mock_p1.return_value = [_team_pred("winner", "Argentina")]
        receipt, has = await build_phase2_bracket_receipt(AsyncMock(), _user("bob"))
        assert has is True
        assert "carries over" in receipt.text  # carry-over note present
        assert "Argentina" in receipt.text

    @pytest.mark.asyncio
    @patch("app.services.receipts._load_bracket_predictions", new_callable=AsyncMock)
    @patch("app.services.receipts._load_phase2_bracket_predictions", new_callable=AsyncMock)
    async def test_no_bracket_at_all_flags_empty(self, mock_p2, mock_p1):
        mock_p2.return_value = []
        mock_p1.return_value = []
        _receipt_obj, has = await build_phase2_bracket_receipt(AsyncMock(), _user("zoe"))
        assert has is False


# ── send_phase2_bracket_receipts ─────────────────────────────────────────────


class TestSend:
    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase2_bracket_receipt", new_callable=AsyncMock)
    async def test_sends_to_each_user_with_bracket(self, mock_build, mock_send):
        users = [_user("a"), _user("b"), _user("c")]
        mock_build.return_value = (_receipt(), True)
        mock_send.return_value = EmailResult(message_id="m")
        session = _mock_session(users)
        result = await send_phase2_bracket_receipts(session, _competition())
        assert result.sent == 3
        assert mock_send.call_count == 3
        assert session.commit.call_count == 3

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase2_bracket_receipt", new_callable=AsyncMock)
    async def test_skips_users_with_no_bracket(self, mock_build, mock_send):
        users = [_user("a"), _user("b")]
        mock_build.side_effect = [(_receipt(), True), (_receipt(), False)]
        mock_send.return_value = EmailResult(message_id="m")
        session = _mock_session(users)
        result = await send_phase2_bracket_receipts(session, _competition())
        assert result.sent == 1
        assert result.skipped_no_predictions == 1
        assert mock_send.call_count == 1

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase2_bracket_receipt", new_callable=AsyncMock)
    async def test_idempotent_skip_already_sent(self, mock_build, mock_send):
        users = [_user("a"), _user("b")]
        mock_build.return_value = (_receipt(), True)
        mock_send.return_value = EmailResult(message_id="m")
        session = _mock_session(users, {users[0].id})
        result = await send_phase2_bracket_receipts(session, _competition())
        assert result.sent == 1
        assert result.skipped_already_sent == 1
        assert mock_send.call_count == 1

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase2_bracket_receipt", new_callable=AsyncMock)
    async def test_failed_send_writes_no_idempotency_row(self, mock_build, mock_send):
        users = [_user("a")]
        mock_build.return_value = (_receipt(), True)
        mock_send.side_effect = EmailSendError("4xx")
        session = _mock_session(users)
        result = await send_phase2_bracket_receipts(session, _competition())
        assert result.failed == 1 and result.sent == 0
        assert [c.args[0] for c in session.add.call_args_list] == []
        assert session.commit.call_count == 0

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase2_bracket_receipt", new_callable=AsyncMock)
    async def test_blank_api_key_aborts_batch(self, mock_build, mock_send):
        users = [_user("a"), _user("b")]
        mock_build.return_value = (_receipt(), True)
        mock_send.return_value = EmailResult(message_id=EMAIL_SKIPPED)
        session = _mock_session(users)
        result = await send_phase2_bracket_receipts(session, _competition())
        assert result.skipped_no_api_key == 1 and result.sent == 0
        assert mock_send.call_count == 1


# ── scheduler gate ───────────────────────────────────────────────────────────


class TestSchedulerGate:
    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase2_bracket_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_if_no_active_competition(self, mock_comp, mock_send):
        mock_comp.return_value = None
        await _maybe_send_phase2_bracket_receipts(AsyncMock())
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase2_bracket_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_if_phase2_inactive(self, mock_comp, mock_send):
        mock_comp.return_value = _competition(active=False)
        await _maybe_send_phase2_bracket_receipts(AsyncMock())
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase2_bracket_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_if_no_deadline(self, mock_comp, mock_send):
        comp = _competition()
        comp.phase2_bracket_deadline = None
        mock_comp.return_value = comp
        await _maybe_send_phase2_bracket_receipts(AsyncMock())
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase2_bracket_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_before_deadline(self, mock_comp, mock_send):
        mock_comp.return_value = _competition(deadline_past=False)
        await _maybe_send_phase2_bracket_receipts(AsyncMock())
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase2_bracket_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_sends_after_deadline(self, mock_comp, mock_send):
        comp = _competition(deadline_past=True)
        mock_comp.return_value = comp
        mock_send.return_value = BatchSendResult(sent=0)
        session = AsyncMock()
        await _maybe_send_phase2_bracket_receipts(session)
        mock_send.assert_called_once_with(session, comp)
