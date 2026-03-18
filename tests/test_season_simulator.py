"""
Tests for app.analytics.season_simulator.

Covers: record loading, game simulation, lottery mechanics, draft order
application, and the full end-to-end pipeline.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.analytics.season_simulator import (
    TeamRecord,
    SimulationResult,
    load_team_records,
    load_current_records,
    simulate_remaining_games,
    run_lottery,
    simulate_season_and_lottery,
    apply_draft_order_to_picks,
    build_simulation_summary,
    _LOTTERY_ODDS,
)

_DATA_DIR = Path(__file__).parent.parent / "data"
_PICKS_PATH = _DATA_DIR / "picks.json"
_RECORDS_PATH = _DATA_DIR / "config" / "team_records_2026.json"


# ---------------------------------------------------------------------------
# TeamRecord unit tests
# ---------------------------------------------------------------------------


def test_team_record_win_pct_basic():
    """Win percentage is computed correctly."""
    rec = TeamRecord("tst", wins=40, losses=30, games_remaining=12, conference="east")
    assert abs(rec.win_pct - 40 / 70) < 1e-9


def test_team_record_win_pct_no_games():
    """Win percentage defaults to 0.5 when no games played."""
    rec = TeamRecord("tst", wins=0, losses=0, games_remaining=82, conference="west")
    assert rec.win_pct == 0.5


def test_team_record_games_played():
    """games_played returns wins + losses."""
    rec = TeamRecord("tst", wins=33, losses=27, games_remaining=22, conference="east")
    assert rec.games_played == 60


# ---------------------------------------------------------------------------
# load_team_records
# ---------------------------------------------------------------------------


def test_load_team_records_returns_30_teams():
    """All 30 NBA teams are present in the records config."""
    records = load_team_records()
    assert len(records) == 30


def test_load_team_records_required_fields():
    """Each record has valid wins, losses, games_remaining, and conference."""
    records = load_team_records()
    for abbr, rec in records.items():
        assert rec.wins >= 0
        assert rec.losses >= 0
        assert rec.games_remaining >= 0
        assert rec.conference in ("east", "west"), f"{abbr} has bad conference"


def test_load_team_records_known_teams():
    """Key team abbreviations are present."""
    records = load_team_records()
    for abbr in ("bos", "lal", "gsw", "okc", "was", "cha"):
        assert abbr in records, f"{abbr} missing from records config"


# ---------------------------------------------------------------------------
# load_current_records
# ---------------------------------------------------------------------------


def test_load_current_records_returns_30_teams():
    """load_current_records returns a (wins, losses) tuple for all 30 teams."""
    records = load_current_records()
    assert len(records) == 30


def test_load_current_records_are_mid_season():
    """Current records reflect mid-season state (not 82-game totals)."""
    records = load_current_records()
    for abbr, (wins, losses) in records.items():
        total = wins + losses
        assert total < 82, f"{abbr} shows {total} games — expected mid-season count"


def test_load_current_records_format():
    """Each entry is a 2-tuple of non-negative ints."""
    records = load_current_records()
    for abbr, (wins, losses) in records.items():
        assert isinstance(wins, int) and wins >= 0
        assert isinstance(losses, int) and losses >= 0


# ---------------------------------------------------------------------------
# simulate_remaining_games
# ---------------------------------------------------------------------------


def test_simulate_remaining_games_zeroes_remaining(monkeypatch):
    """After simulation, games_remaining is 0 for all teams."""
    records = load_team_records()
    random.seed(42)
    result = simulate_remaining_games(records)
    assert all(r.games_remaining == 0 for r in result.values())


def test_simulate_remaining_games_total_games_preserved(monkeypatch):
    """Each team's wins + losses equals games_per_season after simulation."""
    records = load_team_records()
    with open(_RECORDS_PATH) as f:
        config = json.load(f)
    games_per_season = config["games_per_season"]

    random.seed(7)
    result = simulate_remaining_games(records)
    for rec in result.values():
        assert rec.wins + rec.losses == games_per_season


def test_simulate_remaining_games_wins_change():
    """Simulating remaining games changes at least one team's win total."""
    records = load_team_records()
    wins_before = {a: r.wins for a, r in records.items()}
    random.seed(99)
    result = simulate_remaining_games(records)
    wins_after = {a: r.wins for a, r in result.items()}
    assert wins_before != wins_after


# ---------------------------------------------------------------------------
# run_lottery
# ---------------------------------------------------------------------------


def test_run_lottery_returns_14_teams():
    """Lottery result contains exactly 14 teams."""
    teams = [f"t{i:02d}" for i in range(14)]
    result = run_lottery(teams)
    assert len(result) == 14


def test_run_lottery_contains_all_input_teams():
    """Every input team appears exactly once in the lottery result."""
    teams = [f"t{i:02d}" for i in range(14)]
    result = run_lottery(teams)
    assert sorted(result) == sorted(teams)


def test_run_lottery_wrong_count_raises():
    """Passing a team list not of length 14 raises ValueError."""
    with pytest.raises(ValueError):
        run_lottery(["a", "b", "c"])


def test_run_lottery_top4_any_team(monkeypatch):
    """Any of the 14 lottery teams can appear in the top-4 (seeded run)."""
    teams = [f"t{i:02d}" for i in range(14)]
    top4_seen = set()
    for seed in range(50):
        random.seed(seed)
        result = run_lottery(list(teams))
        top4_seen.update(result[:4])
    # With 50 seeds, multiple different teams should win top-4 slots.
    assert len(top4_seen) > 4


# ---------------------------------------------------------------------------
# simulate_season_and_lottery
# ---------------------------------------------------------------------------


def test_simulate_season_full_draft_order_length():
    """full_draft_order contains exactly 30 teams."""
    result = simulate_season_and_lottery(seed=0)
    assert len(result.full_draft_order) == 30


def test_simulate_season_lottery_order_length():
    """lottery_order contains exactly 14 teams."""
    result = simulate_season_and_lottery(seed=1)
    assert len(result.lottery_order) == 14


def test_simulate_season_playoff_order_length():
    """playoff_order contains exactly 16 teams."""
    result = simulate_season_and_lottery(seed=2)
    assert len(result.playoff_order) == 16


def test_simulate_season_no_duplicate_teams():
    """All 30 teams in full_draft_order are unique."""
    result = simulate_season_and_lottery(seed=3)
    assert len(set(result.full_draft_order)) == 30


def test_simulate_season_lottery_precedes_playoff():
    """Lottery teams occupy indices 0-13 and playoff teams 14-29."""
    result = simulate_season_and_lottery(seed=4)
    assert result.full_draft_order[:14] == result.lottery_order
    assert result.full_draft_order[14:] == result.playoff_order


def test_simulate_season_deterministic_with_seed():
    """Same seed produces the same draft order."""
    r1 = simulate_season_and_lottery(seed=42)
    r2 = simulate_season_and_lottery(seed=42)
    assert r1.full_draft_order == r2.full_draft_order


def test_simulate_season_lottery_odds_used_length():
    """lottery_odds_used covers all 14 lottery teams."""
    result = simulate_season_and_lottery(seed=5)
    assert len(result.lottery_odds_used) == 14
    assert set(result.lottery_odds_used.keys()) == set(result.lottery_order)


# ---------------------------------------------------------------------------
# apply_draft_order_to_picks
# ---------------------------------------------------------------------------


def test_apply_draft_order_updates_picks_file(tmp_path, monkeypatch):
    """After apply_draft_order_to_picks, picks.json current_team matches order."""
    # Build a minimal 6-pick file (2 rounds × 3 teams).
    fake_picks = {
        "picks": [
            {"pick_number": i + 1, "round": 1 if i < 3 else 2,
             "pick_in_round": (i % 3) + 1, "current_team": "old",
             "is_lottery": i < 2, "player_id": "p1",
             "team_needs_snapshot": {}, "traded_from": ["x"],
             "trade_notes": "old note"}
            for i in range(6)
        ]
    }
    picks_file = tmp_path / "picks.json"
    picks_file.write_text(json.dumps(fake_picks))

    # Monkeypatch the module-level path.
    monkeypatch.setattr(
        "app.analytics.season_simulator._PICKS_PATH", picks_file
    )

    draft_order = ["aaa", "bbb", "ccc"] + ["d"] * 27  # 30 teams
    result = SimulationResult(
        final_records={},
        lottery_order=draft_order[:14],
        playoff_order=draft_order[14:],
        full_draft_order=draft_order,
        lottery_odds_used={},
    )

    apply_draft_order_to_picks(result)

    updated = json.loads(picks_file.read_text())
    r1_picks = [p for p in updated["picks"] if p["round"] == 1]
    assert r1_picks[0]["current_team"] == "aaa"
    assert r1_picks[1]["current_team"] == "bbb"
    assert r1_picks[2]["current_team"] == "ccc"


def test_apply_draft_order_clears_player_ids(tmp_path, monkeypatch):
    """player_id and team_needs_snapshot are cleared after apply."""
    fake_picks = {
        "picks": [
            {"pick_number": 1, "round": 1, "pick_in_round": 1,
             "current_team": "old", "is_lottery": True,
             "player_id": "some-player", "team_needs_snapshot": {"x": 1},
             "traded_from": ["y"], "trade_notes": "note"}
        ]
    }
    picks_file = tmp_path / "picks.json"
    picks_file.write_text(json.dumps(fake_picks))
    monkeypatch.setattr("app.analytics.season_simulator._PICKS_PATH", picks_file)

    draft_order = ["abc"] + ["z"] * 29
    result = SimulationResult(
        final_records={},
        lottery_order=draft_order[:14],
        playoff_order=draft_order[14:],
        full_draft_order=draft_order,
        lottery_odds_used={},
    )
    apply_draft_order_to_picks(result)
    updated = json.loads(picks_file.read_text())
    pick = updated["picks"][0]
    assert pick["player_id"] is None
    assert pick["team_needs_snapshot"] is None
    assert pick["traded_from"] == []
    assert pick["trade_notes"] is None


# ---------------------------------------------------------------------------
# build_simulation_summary
# ---------------------------------------------------------------------------


def test_build_simulation_summary_keys():
    """Summary dict contains expected top-level keys."""
    result = simulate_season_and_lottery(seed=10)
    summary = build_simulation_summary(result)
    assert "final_records" in summary
    assert "lottery_order" in summary
    assert "full_draft_order" in summary
    assert "lottery_odds_used" in summary


def test_build_simulation_summary_records_have_win_pct():
    """Each team record entry in the summary has a win_pct field."""
    result = simulate_season_and_lottery(seed=11)
    summary = build_simulation_summary(result)
    for abbr, rec in summary["final_records"].items():
        assert "win_pct" in rec, f"{abbr} missing win_pct"
        assert 0.0 <= rec["win_pct"] <= 1.0


# ---------------------------------------------------------------------------
# API endpoint integration (using TestClient)
# ---------------------------------------------------------------------------


def test_simulate_season_endpoint(tmp_path, monkeypatch):
    """POST /api/predictions/simulate-season returns 200 with expected keys."""
    from fastapi.testclient import TestClient
    from server import app

    # Patch the picks path so tests don't mutate real data.
    real_picks = json.loads(_PICKS_PATH.read_text())
    tmp_picks = tmp_path / "picks.json"
    tmp_picks.write_text(json.dumps(real_picks))

    monkeypatch.setattr("app.analytics.season_simulator._PICKS_PATH", tmp_picks)
    monkeypatch.setattr("app.analytics.simulator._PICKS_PATH", tmp_picks)
    tmp_players = tmp_path / "players.json"
    tmp_players.write_text(json.dumps({"players": []}))
    monkeypatch.setattr("app.analytics.simulator._PLAYERS_PATH", tmp_players)

    client = TestClient(app)
    res = client.post("/api/predictions/simulate-season")
    assert res.status_code == 200
    data = res.json()
    assert "picks_assigned" in data
    assert "lottery_order" in data
    assert len(data["lottery_order"]) == 14
    assert "full_draft_order" in data
    assert len(data["full_draft_order"]) == 30
