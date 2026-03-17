"""
Unit tests for the NBA Mock Draft Pydantic models.
"""

import pytest
from app.models_core import (
    BiographicalInfo,
    EnrichedPick,
    InjuryRecord,
    MediaLink,
    Pick,
    Player,
    StatView,
    Team,
)


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


def test_team_valid():
    """Team model accepts all required fields."""
    team = Team(
        abbreviation="gsw",
        name="Golden State Warriors",
        city="San Francisco",
        nickname="Warriors",
        primary_color="#1d428a",
        secondary_color="#ffc72c",
        logo_url="https://a.espncdn.com/i/teamlogos/nba/500/gsw.png",
    )
    assert team.abbreviation == "gsw"
    assert team.nickname == "Warriors"


def test_team_missing_field():
    """Team model raises ValidationError when a required field is absent."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Team(abbreviation="gsw", name="Golden State Warriors")


# ---------------------------------------------------------------------------
# BiographicalInfo — NBA-specific fields
# ---------------------------------------------------------------------------


def test_bio_nba_fields():
    """BiographicalInfo stores NBA-specific measurements correctly."""
    bio = BiographicalInfo(
        height_inches=79,
        weight_lbs=220,
        wingspan_inches=83.5,
        standing_reach_inches=104.0,
        lane_agility_seconds=10.82,
        vertical_jump_inches=28.5,
        max_vertical_inches=35.0,
    )
    assert bio.height_inches == 79
    assert bio.wingspan_inches == 83.5
    assert bio.lane_agility_seconds == 10.82


def test_bio_all_none():
    """BiographicalInfo allows all optional fields to be None."""
    bio = BiographicalInfo()
    assert bio.height_inches is None
    assert bio.wingspan_inches is None


# ---------------------------------------------------------------------------
# Pick
# ---------------------------------------------------------------------------


def test_pick_valid():
    """Pick model accepts all required fields with sensible defaults."""
    pick = Pick(
        pick_number=1,
        round=1,
        pick_in_round=1,
        current_team="was",
    )
    assert pick.pick_number == 1
    assert pick.traded_from == []
    assert pick.is_lottery is False
    assert pick.player_id is None


def test_pick_lottery_flag():
    """Pick model stores lottery flag correctly."""
    pick = Pick(
        pick_number=5,
        round=1,
        pick_in_round=5,
        current_team="sas",
        is_lottery=True,
    )
    assert pick.is_lottery is True


def test_pick_with_trade():
    """Pick model stores traded_from list correctly."""
    pick = Pick(
        pick_number=12,
        round=1,
        pick_in_round=12,
        current_team="orl",
        traded_from=["was", "det"],
        trade_notes="Acquired via multi-team deal",
    )
    assert pick.traded_from == ["was", "det"]
    assert pick.trade_notes == "Acquired via multi-team deal"


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------


def test_player_valid():
    """Player model creates with required fields and defaults."""
    player = Player(
        player_id="aj-dybantsa",
        name="AJ Dybantsa",
        position="SF",
        college="BYU",
    )
    assert player.player_id == "aj-dybantsa"
    assert player.position == "SF"
    assert player.injury_history == []
    assert player.stat_views == []


def test_player_with_grade():
    """Player grade field accepts float values."""
    player = Player(
        player_id="aj-dybantsa",
        name="AJ Dybantsa",
        position="SF",
        college="BYU",
        grade=9.8,
    )
    assert player.grade == 9.8


def test_player_with_bio():
    """Player bio field stores BiographicalInfo correctly."""
    bio = BiographicalInfo(height_inches=79, weight_lbs=215)
    player = Player(
        player_id="aj-dybantsa",
        name="AJ Dybantsa",
        position="SF",
        college="BYU",
        bio=bio,
    )
    assert player.bio.height_inches == 79


# ---------------------------------------------------------------------------
# StatView
# ---------------------------------------------------------------------------


def test_stat_view_valid():
    """StatView stores season stats correctly."""
    sv = StatView(
        view_name="Season",
        season="2025-26",
        stats={"PPG": 17.5, "RPG": 6.3, "APG": 3.1},
    )
    assert sv.stats["PPG"] == 17.5


def test_stat_view_empty_stats():
    """StatView allows empty stats dict."""
    sv = StatView(view_name="Projection", season="2026", stats={})
    assert sv.stats == {}


# ---------------------------------------------------------------------------
# EnrichedPick
# ---------------------------------------------------------------------------


def test_enriched_pick_no_player():
    """EnrichedPick allows player to be None for unassigned picks."""
    team = Team(
        abbreviation="was",
        name="Washington Wizards",
        city="Washington",
        nickname="Wizards",
        primary_color="#002b5c",
        secondary_color="#e31837",
        logo_url="https://a.espncdn.com/i/teamlogos/nba/500/was.png",
    )
    pick = Pick(pick_number=1, round=1, pick_in_round=1, current_team="was")
    ep = EnrichedPick(pick=pick, team=team)
    assert ep.player is None
    assert ep.traded_from_teams == []


def test_enriched_pick_with_player():
    """EnrichedPick correctly stores an assigned player."""
    team = Team(
        abbreviation="was",
        name="Washington Wizards",
        city="Washington",
        nickname="Wizards",
        primary_color="#002b5c",
        secondary_color="#e31837",
        logo_url="https://a.espncdn.com/i/teamlogos/nba/500/was.png",
    )
    pick = Pick(
        pick_number=1, round=1, pick_in_round=1,
        current_team="was", player_id="aj-dybantsa",
    )
    player = Player(
        player_id="aj-dybantsa", name="AJ Dybantsa",
        position="SF", college="BYU", grade=9.8,
    )
    ep = EnrichedPick(pick=pick, team=team, player=player)
    assert ep.player.name == "AJ Dybantsa"
    assert ep.player.grade == 9.8
