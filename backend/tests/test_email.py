"""Tests for the Resend email wrapper.

httpx is mocked at the AsyncClient level so the tests don't make real
network calls. We verify the request shape, response handling, retry
behaviour on 5xx, and graceful no-op when the API key is blank.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.email import (
    EMAIL_SKIPPED,
    EmailResult,
    EmailSendError,
    send_email,
)


def _mock_settings(api_key: str = "re_test_key", from_addr: str = "Test <a@b.com>"):
    """Patch get_settings to return predictable email config."""
    mock = MagicMock()
    mock.resend_api_key = api_key
    mock.email_from = from_addr
    return mock


def _http_response(status: int, body: dict | None = None) -> MagicMock:
    """Build a mock httpx.Response with the given status + JSON body."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json.return_value = body or {}
    response.text = ""
    response.reason_phrase = ""
    return response


class TestSendEmailSuccess:
    """Happy path: Resend returns 200 with a message id."""

    @pytest.mark.asyncio
    @patch("app.services.email.get_settings")
    @patch("app.services.email.httpx.AsyncClient")
    async def test_returns_message_id_on_200(self, mock_client_cls, mock_get_settings):
        mock_get_settings.return_value = _mock_settings()
        mock_client = AsyncMock()
        mock_client.post.return_value = _http_response(200, {"id": "msg_abc123"})
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await send_email(
            to="recipient@example.com",
            subject="Test",
            html="<p>Hello</p>",
        )

        assert result.ok is True
        assert result.message_id == "msg_abc123"

    @pytest.mark.asyncio
    @patch("app.services.email.get_settings")
    @patch("app.services.email.httpx.AsyncClient")
    async def test_sends_correct_payload(self, mock_client_cls, mock_get_settings):
        mock_get_settings.return_value = _mock_settings(from_addr="Brand <brand@x.com>")
        mock_client = AsyncMock()
        mock_client.post.return_value = _http_response(200, {"id": "msg_1"})
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        await send_email(
            to=["a@x.com", "b@x.com"],
            subject="Hi",
            html="<p>H</p>",
            text="H plain",
        )

        # Inspect the POST call's payload.
        call_kwargs = mock_client.post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["from"] == "Brand <brand@x.com>"
        assert payload["to"] == ["a@x.com", "b@x.com"]
        assert payload["subject"] == "Hi"
        assert payload["html"] == "<p>H</p>"
        assert payload["text"] == "H plain"
        assert call_kwargs["headers"]["Authorization"] == "Bearer re_test_key"


class TestSendEmailNoApiKey:
    """Blank RESEND_API_KEY → return sentinel, no HTTP call made."""

    @pytest.mark.asyncio
    @patch("app.services.email.get_settings")
    @patch("app.services.email.httpx.AsyncClient")
    async def test_skips_when_key_blank(self, mock_client_cls, mock_get_settings):
        mock_get_settings.return_value = _mock_settings(api_key="")
        result = await send_email(
            to="x@y.com",
            subject="S",
            html="<p>H</p>",
        )

        assert result.message_id == EMAIL_SKIPPED
        assert result.ok is False  # sentinel doesn't count as ok
        # Critically: no HTTP client was constructed at all.
        mock_client_cls.assert_not_called()


class TestSendEmailRetries:
    """5xx retries with exponential backoff; 4xx fails fast."""

    @pytest.mark.asyncio
    @patch("app.services.email.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.services.email.get_settings")
    @patch("app.services.email.httpx.AsyncClient")
    async def test_5xx_retries_and_eventually_succeeds(
        self, mock_client_cls, mock_get_settings, _mock_sleep
    ):
        mock_get_settings.return_value = _mock_settings()
        mock_client = AsyncMock()
        # Two 503s then a 200.
        mock_client.post.side_effect = [
            _http_response(503),
            _http_response(503),
            _http_response(200, {"id": "msg_after_retry"}),
        ]
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await send_email(to="x@y.com", subject="S", html="<p>H</p>")
        assert result.message_id == "msg_after_retry"
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    @patch("app.services.email.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.services.email.get_settings")
    @patch("app.services.email.httpx.AsyncClient")
    async def test_5xx_exhausts_retries(self, mock_client_cls, mock_get_settings, _mock_sleep):
        mock_get_settings.return_value = _mock_settings()
        mock_client = AsyncMock()
        mock_client.post.return_value = _http_response(500)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(EmailSendError, match="retries exhausted"):
            await send_email(to="x@y.com", subject="S", html="<p>H</p>")
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    @patch("app.services.email.get_settings")
    @patch("app.services.email.httpx.AsyncClient")
    async def test_4xx_no_retry(self, mock_client_cls, mock_get_settings):
        """422 (e.g. invalid from address) is permanent — must not retry."""
        mock_get_settings.return_value = _mock_settings()
        mock_client = AsyncMock()
        mock_client.post.return_value = _http_response(
            422, {"message": "from address not verified"}
        )
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(EmailSendError, match="not verified"):
            await send_email(to="x@y.com", subject="S", html="<p>H</p>")
        assert mock_client.post.call_count == 1
