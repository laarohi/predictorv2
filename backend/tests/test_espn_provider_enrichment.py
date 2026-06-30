"""EspnScoreProvider enriches past-regulation knockouts from the summary
endpoint, turning a bare (and possibly corrupted) live running total into an
authoritative per-period split.
"""

import pytest

from app.services.external.espn import EspnError
from app.services.external_scores import EspnScoreProvider, ExternalScore
from app.models.fixture import MatchStatus


def _ko_event(event_id, home, away, *, home_score, away_score, home_pen, away_pen):
    """A finished-after-penalties scoreboard event, carrying the (corrupted)
    live running total — what enrichment must override."""
    return {
        "id": event_id,
        "competitions": [
            {
                "status": {
                    "type": {"name": "STATUS_FINAL_PEN", "state": "post", "completed": True},
                    "period": 5,
                    "displayClock": "120'",
                },
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": home},
                     "score": str(home_score), "shootoutScore": home_pen},
                    {"homeAway": "away", "team": {"displayName": away},
                     "score": str(away_score), "shootoutScore": away_pen},
                ],
            }
        ],
    }


def _group_event(home, away, home_score, away_score):
    return {
        "id": "g1",
        "competitions": [
            {
                "status": {
                    "type": {"name": "STATUS_FULL_TIME", "state": "post", "completed": True},
                    "period": 2,
                    "displayClock": "90'",
                },
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": home}, "score": str(home_score)},
                    {"homeAway": "away", "team": {"displayName": away}, "score": str(away_score)},
                ],
            }
        ],
    }


def _summary(home_ls, away_ls, *, home_score, away_score, home_pen, away_pen):
    def competitor(side, ls, score, pen):
        c = {"homeAway": side, "score": str(score),
             "linescores": [{"displayValue": str(v)} for v in ls]}
        if pen is not None:
            c["shootoutScore"] = pen
        return c
    return {"header": {"competitions": [{"competitors": [
        competitor("home", home_ls, home_score, home_pen),
        competitor("away", away_ls, away_score, away_pen),
    ]}]}}


class _FakeClient:
    def __init__(self, events, summaries):
        self._events = events
        self._summaries = summaries
        self.summary_calls = []

    async def get_scoreboard(self, slug, dates):
        return self._events

    async def get_summary(self, slug, event_id):
        self.summary_calls.append(event_id)
        if event_id not in self._summaries:
            raise EspnError(f"no summary for {event_id}")
        return self._summaries[event_id]


@pytest.mark.asyncio
async def test_shootout_event_is_enriched_to_authoritative_split():
    # Scoreboard shows the corrupted transient (0-0, 4-4 pens); the summary has
    # the clean per-period truth (1-1 / 1-1 / 3-4).
    events = [_ko_event("760489", "Germany", "Paraguay",
                        home_score=0, away_score=0, home_pen=4, away_pen=4)]
    summaries = {"760489": _summary([0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
                                    home_score=1, away_score=1, home_pen=3, away_pen=4)}
    provider = EspnScoreProvider(client=_FakeClient(events, summaries))

    scores = await provider.fetch_live_scores("WC")

    assert len(scores) == 1
    s = scores[0]
    assert (s.home_team, s.away_team) == ("Germany", "Paraguay")
    assert (s.home_score, s.away_score) == (1, 1)            # 90'
    assert (s.home_score_et, s.away_score_et) == (1, 1)      # after ET
    assert (s.home_penalties, s.away_penalties) == (3, 4)    # shootout
    assert s.final_authoritative is True
    assert s.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_group_event_is_not_enriched():
    client = _FakeClient([_group_event("Spain", "Austria", 2, 1)], {})
    provider = EspnScoreProvider(client=client)

    scores = await provider.fetch_live_scores("WC")

    assert client.summary_calls == []                       # no summary fetched
    assert (scores[0].home_score, scores[0].away_score) == (2, 1)
    assert scores[0].final_authoritative is False


@pytest.mark.asyncio
async def test_enrichment_falls_back_when_summary_inconsistent():
    # Summary present but undecided (4-4 pens) → parser returns None → the base
    # (non-authoritative) running total is left for score_sync's freeze.
    events = [_ko_event("x", "Netherlands", "Morocco",
                        home_score=1, away_score=1, home_pen=4, away_pen=4)]
    summaries = {"x": _summary([0, 1, 0, 0, 4], [1, 0, 0, 0, 4],
                               home_score=1, away_score=1, home_pen=4, away_pen=4)}
    provider = EspnScoreProvider(client=_FakeClient(events, summaries))

    scores = await provider.fetch_live_scores("WC")

    assert scores[0].final_authoritative is False
    assert (scores[0].home_penalties, scores[0].away_penalties) == (4, 4)  # untouched


@pytest.mark.asyncio
async def test_enrichment_falls_back_when_summary_fetch_errors():
    events = [_ko_event("missing", "Brazil", "Japan",
                        home_score=2, away_score=2, home_pen=5, away_pen=4)]
    provider = EspnScoreProvider(client=_FakeClient(events, summaries={}))

    scores = await provider.fetch_live_scores("WC")

    assert scores[0].final_authoritative is False  # base score retained, no crash


# ── fetch_final_check (the settlement cross-check source) ──────────────────── #

def _ext(event_id):
    return ExternalScore(
        external_id="", home_team="H", away_team="A",
        home_score=0, away_score=0, status=MatchStatus.FINISHED,
        espn_event_id=event_id,
    )


@pytest.mark.asyncio
async def test_final_check_shootout_returns_aet_total_and_pens():
    summaries = {"e": _summary([0, 1, 0, 0, 3], [1, 0, 0, 0, 4],
                               home_score=1, away_score=1, home_pen=3, away_pen=4)}
    provider = EspnScoreProvider(client=_FakeClient([], summaries))
    assert await provider.fetch_final_check(_ext("e")) == (1, 1, 3, 4)


@pytest.mark.asyncio
async def test_final_check_group_returns_total_no_pens():
    summaries = {"g": _summary([2, 0], [0, 1], home_score=2, away_score=1,
                               home_pen=None, away_pen=None)}
    provider = EspnScoreProvider(client=_FakeClient([], summaries))
    assert await provider.fetch_final_check(_ext("g")) == (2, 1, None, None)


@pytest.mark.asyncio
async def test_final_check_none_without_event_id():
    provider = EspnScoreProvider(client=_FakeClient([], {}))
    assert await provider.fetch_final_check(_ext(None)) is None


@pytest.mark.asyncio
async def test_final_check_none_on_fetch_error():
    provider = EspnScoreProvider(client=_FakeClient([], {}))  # no summary for "x"
    assert await provider.fetch_final_check(_ext("x")) is None
