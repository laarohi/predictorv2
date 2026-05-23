"""Tests for the Phase 1 batch send function and its scheduler gating.

The batch sender is the production code path that fires when the
phase1_deadline passes — most expensive single moment in the system
from a "we cannot get this wrong" perspective. These tests verify:

- Idempotency: a second invocation re-using the same idempotency rows
  doesn't double-send.
- Skip-no-predictions: users without any predictions aren't emailed.
- Skip-no-api-key: blank Resend key aborts the whole batch (rather
  than silently no-op'ing one user at a time).
- Failed sends don't write idempotency rows (so they retry next tick).
- Scheduler gate: receipts only fire when phase1_deadline is in the
  past; before that, the tick is a no-op.
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
    DEADLINE_KIND_PHASE_1,
    send_phase1_receipts,
)
from app.services.score_scheduler import _maybe_send_phase1_receipts


def _user(name: str = "x") -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.name = name
    user.email = f"{name}@example.com"
    user.is_active = True
    return user


def _competition() -> Competition:
    comp = MagicMock(spec=Competition)
    comp.id = uuid.uuid4()
    comp.phase1_deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    return comp


def _receipt_for(predictions_summary: str = "5 group · 2 bracket · 1 bonus"):
    """Build a minimal Receipt-shaped object for the builder mock."""
    receipt = MagicMock()
    receipt.subject = "test"
    receipt.html = "<p>h</p>"
    receipt.text = f"hi\n{predictions_summary}\nrest"
    return receipt


def _mock_session(users: list[User], already_sent_ids: set[uuid.UUID] | None = None) -> AsyncMock:
    """Wire two reads: user list + already-sent ids."""
    session = AsyncMock()
    user_result = MagicMock()
    user_result.scalars.return_value.all.return_value = users
    sent_result = MagicMock()
    sent_result.scalars.return_value.all.return_value = list(already_sent_ids or [])
    session.execute.side_effect = [user_result, sent_result]
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


class TestBatchSendBasic:
    """Happy path: every user gets sent, idempotency rows recorded."""

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_sends_to_each_user(self, mock_build, mock_send):
        users = [_user("a"), _user("b"), _user("c")]
        mock_build.return_value = _receipt_for()
        mock_send.return_value = EmailResult(message_id="msg_123")

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        assert result.sent == 3
        assert result.failed == 0
        assert result.skipped_already_sent == 0
        assert mock_send.call_count == 3
        # Per-user commits: 3 successful sends → 3 commits.
        assert session.commit.call_count == 3


class TestBatchSendIdempotency:
    """Already-sent users are skipped via the email_sends index."""

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_skips_users_already_in_idempotency_table(self, mock_build, mock_send):
        users = [_user("a"), _user("b"), _user("c")]
        mock_build.return_value = _receipt_for()
        mock_send.return_value = EmailResult(message_id="msg_123")

        # Users a and b have already been sent.
        already_sent = {users[0].id, users[1].id}
        session = _mock_session(users, already_sent)
        result = await send_phase1_receipts(session, _competition())

        assert result.sent == 1  # only user c
        assert result.skipped_already_sent == 2
        # Only one actual Resend call happened.
        assert mock_send.call_count == 1


class TestBatchSendSkipsNoPredictions:
    """Users with empty receipts (no preds) aren't emailed."""

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_skips_zero_prediction_users(self, mock_build, mock_send):
        users = [_user("a"), _user("b")]
        # User a has predictions; user b has none.
        mock_build.side_effect = [
            _receipt_for("5 group · 2 bracket · 1 bonus"),
            _receipt_for("0 group · 0 bracket · 0 bonus"),
        ]
        mock_send.return_value = EmailResult(message_id="msg_x")

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        assert result.sent == 1
        assert result.skipped_no_predictions == 1
        # User b's receipt was built (we needed the counts to decide),
        # but send_email was only called for user a.
        assert mock_send.call_count == 1


class TestBatchSendFailures:
    """Failed sends don't write idempotency rows; permanent vs transient
    failures both surface in the counts."""

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_failed_send_does_not_write_idempotency(self, mock_build, mock_send):
        users = [_user("a")]
        mock_build.return_value = _receipt_for()
        mock_send.side_effect = EmailSendError("4xx: from address not verified")

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        assert result.failed == 1
        assert result.sent == 0
        # No idempotency row added.
        added_rows = [c.args[0] for c in session.add.call_args_list]
        assert added_rows == []
        # No commit happened because no row was written.
        assert session.commit.call_count == 0


class TestBatchSendNoApiKey:
    """Blank RESEND_API_KEY aborts the whole batch."""

    @pytest.mark.asyncio
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_blank_api_key_aborts_batch(self, mock_build, mock_send):
        users = [_user("a"), _user("b"), _user("c")]
        mock_build.return_value = _receipt_for()
        mock_send.return_value = EmailResult(message_id=EMAIL_SKIPPED)

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        # First user triggers the skip detection → batch aborts.
        assert result.skipped_no_api_key == 1
        assert result.sent == 0
        # Only the first user was attempted.
        assert mock_send.call_count == 1


class TestBatchSendAllowlist:
    """EMAIL_TO_ALLOWLIST safety belt — only-send-to-listed-addresses mode."""

    @pytest.mark.asyncio
    @patch("app.services.receipts.get_settings")
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_allowlist_skips_non_listed_addresses(
        self, mock_build, mock_send, mock_get_settings
    ):
        """Three users; allowlist contains only the first two."""
        users = [_user("a"), _user("b"), _user("c")]
        # Construct emails to match _user() format: f"{name}@example.com"
        mock_settings = MagicMock()
        mock_settings.email_to_allowlist = "a@example.com, b@example.com"
        mock_get_settings.return_value = mock_settings

        mock_build.return_value = _receipt_for()
        mock_send.return_value = EmailResult(message_id="msg_ok")

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        assert result.sent == 2  # a, b
        assert result.skipped_not_in_allowlist == 1  # c
        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    @patch("app.services.receipts.get_settings")
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_blank_allowlist_sends_to_everyone(
        self, mock_build, mock_send, mock_get_settings
    ):
        """Default behavior: blank allowlist → no restriction."""
        users = [_user("a"), _user("b")]
        mock_settings = MagicMock()
        mock_settings.email_to_allowlist = ""
        mock_get_settings.return_value = mock_settings

        mock_build.return_value = _receipt_for()
        mock_send.return_value = EmailResult(message_id="msg_ok")

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        assert result.sent == 2
        assert result.skipped_not_in_allowlist == 0

    @pytest.mark.asyncio
    @patch("app.services.receipts.get_settings")
    @patch("app.services.receipts.send_email", new_callable=AsyncMock)
    @patch("app.services.receipts.build_phase1_receipt", new_callable=AsyncMock)
    async def test_allowlist_match_is_case_insensitive(
        self, mock_build, mock_send, mock_get_settings
    ):
        """Allowlist comparison normalises to lowercase on both sides."""
        users = [_user("Alice")]
        users[0].email = "Alice@Example.com"  # mixed case

        mock_settings = MagicMock()
        mock_settings.email_to_allowlist = "alice@example.com"
        mock_get_settings.return_value = mock_settings

        mock_build.return_value = _receipt_for()
        mock_send.return_value = EmailResult(message_id="msg_ok")

        session = _mock_session(users)
        result = await send_phase1_receipts(session, _competition())

        assert result.sent == 1
        assert result.skipped_not_in_allowlist == 0


class TestSchedulerGate:
    """The scheduler's pre-deadline gate."""

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase1_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_if_no_active_competition(self, mock_get_comp, mock_send):
        mock_get_comp.return_value = None
        session = AsyncMock()
        await _maybe_send_phase1_receipts(session)
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase1_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_if_no_deadline_set(self, mock_get_comp, mock_send):
        comp = MagicMock(spec=Competition)
        comp.phase1_deadline = None
        mock_get_comp.return_value = comp
        session = AsyncMock()
        await _maybe_send_phase1_receipts(session)
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase1_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_no_send_before_deadline(self, mock_get_comp, mock_send):
        comp = MagicMock(spec=Competition)
        comp.phase1_deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_get_comp.return_value = comp
        session = AsyncMock()
        await _maybe_send_phase1_receipts(session)
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.score_scheduler.send_phase1_receipts", new_callable=AsyncMock)
    @patch("app.services.score_scheduler.get_active_competition", new_callable=AsyncMock)
    async def test_sends_after_deadline(self, mock_get_comp, mock_send):
        comp = MagicMock(spec=Competition)
        comp.id = uuid.uuid4()
        comp.phase1_deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
        mock_get_comp.return_value = comp
        mock_send.return_value = BatchSendResult(sent=0)  # already-sent steady state
        session = AsyncMock()
        await _maybe_send_phase1_receipts(session)
        mock_send.assert_called_once_with(session, comp)
