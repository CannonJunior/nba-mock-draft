"""
Sequential draft simulator for the NBA Mock Draft prediction engine.

Simulates all 60 picks in order, selecting the best-fit available player
for each team based on team value scores. Writes results to:
  - data/players.json   (player profiles)
  - data/picks.json     (player_id fields populated)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.analytics.draft_engine import rank_players_for_team
from app.analytics.player_pool import PlayerCandidate, build_player_pool
from app.analytics.team_context import (
    TeamNeedState,
    build_team_need_states,
    update_team_need,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_PICKS_PATH = _DATA_DIR / "picks.json"
_PLAYERS_PATH = _DATA_DIR / "players.json"

# Grade display calibration constants.
# Top-60 picks have base_scores roughly in [15, 100].
# Map onto the [6.5, 9.9] band scouts use for draftable prospects.
_GRADE_SCORE_MIN = 15.0
_GRADE_SCORE_MAX = 100.0
_GRADE_DISPLAY_MIN = 6.5
_GRADE_DISPLAY_MAX = 9.9


def run_simulation(
    player_pool: Optional[list[PlayerCandidate]] = None,
) -> tuple[dict[int, PlayerCandidate], dict[int, dict]]:
    """
    Simulate all 60 draft picks sequentially and return pick-to-player mapping
    along with a per-pick team need snapshot captured before each selection.

    Args:
        player_pool (Optional[list[PlayerCandidate]]): Pre-built pool.
            If None, will call build_player_pool() to construct the pool.

    Returns:
        tuple:
            - dict[int, PlayerCandidate]: pick_number → selected player.
            - dict[int, dict]: pick_number → team need snapshot (pre-pick).
    """
    picks_data = _load_picks_json()
    picks = picks_data.get("picks", [])

    if not picks:
        logger.error("No picks found in picks.json — aborting simulation")
        return {}, {}

    if player_pool is None:
        player_pool = build_player_pool()

    if not player_pool:
        logger.error("Player pool is empty — aborting simulation")
        return {}, {}

    team_abbrevs = list({p["current_team"] for p in picks})
    team_states: dict[str, TeamNeedState] = build_team_need_states(team_abbrevs)

    pool = list(player_pool)
    available: list[PlayerCandidate] = [p for p in pool if p.available]

    results: dict[int, PlayerCandidate] = {}
    need_snapshots: dict[int, dict] = {}

    for pick_row in picks:
        pick_number = pick_row["pick_number"]
        team = pick_row["current_team"]

        if not available:
            logger.warning("Pick %d: No available players remaining!", pick_number)
            break

        team_state = team_states.get(team)
        if team_state is None:
            logger.warning("Pick %d: Unknown team '%s', creating empty state", pick_number, team)
            team_state = TeamNeedState(team=team)
            team_states[team] = team_state

        need_snapshots[pick_number] = {
            "team": team,
            "needs_ranked": _build_needs_ranked(team_state),
            "picks_made": list(team_state.picks_made),
        }

        ranked = rank_players_for_team(available, team_state)
        if not ranked:
            logger.warning("Pick %d: ranking returned empty for team %s", pick_number, team)
            continue

        _, selected = ranked[0]
        selected.available = False
        available.remove(selected)
        results[pick_number] = selected
        update_team_need(team_state, selected.position)

        logger.debug(
            "Pick %3d | %-4s | %-25s | %-5s | score=%.1f",
            pick_number,
            team.upper(),
            selected.name,
            selected.position,
            ranked[0][0],
        )

    logger.info("Simulation complete: %d/%d picks assigned", len(results), len(picks))
    return results, need_snapshots


def _build_needs_ranked(state: TeamNeedState) -> list[dict]:
    """
    Return the team's positional needs sorted by need level descending.

    Args:
        state (TeamNeedState): Current team need state.

    Returns:
        list[dict]: Ordered list of {"position": str, "need_level": int} dicts.
    """
    sorted_needs = sorted(
        state.needs.items(),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return [
        {"position": pos, "need_level": level}
        for pos, level in sorted_needs
        if level > 0
    ]


def write_results(
    results: dict[int, PlayerCandidate],
    need_snapshots: Optional[dict[int, dict]] = None,
) -> tuple[int, int]:
    """
    Write simulation results to data/players.json and data/picks.json.

    Args:
        results (dict[int, PlayerCandidate]): pick_number → PlayerCandidate.
        need_snapshots (Optional[dict[int, dict]]): pick_number → need snapshot.

    Returns:
        tuple[int, int]: (picks_assigned, players_created) counts.
    """
    players_list = [
        _candidate_to_player_dict(player)
        for player in results.values()
    ]
    _PLAYERS_PATH.write_text(
        json.dumps({"players": players_list}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote %d player records to %s", len(players_list), _PLAYERS_PATH)

    picks_data = _load_picks_json()
    player_id_map: dict[int, str] = {
        pick_num: candidate.player_id for pick_num, candidate in results.items()
    }

    updated_count = 0
    for pick_row in picks_data.get("picks", []):
        pick_num = pick_row["pick_number"]
        if pick_num in player_id_map:
            pick_row["player_id"] = player_id_map[pick_num]
            updated_count += 1
        if need_snapshots and pick_num in need_snapshots:
            pick_row["team_needs_snapshot"] = need_snapshots[pick_num]

    _PICKS_PATH.write_text(
        json.dumps(picks_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Updated %d pick player_id fields in %s", updated_count, _PICKS_PATH)

    return updated_count, len(players_list)


def simulate_and_write(
    player_pool: Optional[list[PlayerCandidate]] = None,
) -> tuple[int, int]:
    """
    Run simulation then write results. Convenience wrapper.

    Args:
        player_pool (Optional[list[PlayerCandidate]]): Pre-built pool.

    Returns:
        tuple[int, int]: (picks_assigned, players_created).
    """
    results, need_snapshots = run_simulation(player_pool=player_pool)
    if not results:
        return 0, 0
    return write_results(results, need_snapshots=need_snapshots)


# ---------------------------------------------------------------------------
# Grade and serialisation helpers
# ---------------------------------------------------------------------------


def _compute_display_grade(candidate: PlayerCandidate) -> float:
    """
    Compute the displayed 0-10 scouting grade for a player.

    Priority:
    1. ESPN scouting grade (when available).
    2. Model-derived: linearly rescales base_score onto [6.5, 9.9].

    Args:
        candidate (PlayerCandidate): Scored prospect.

    Returns:
        float: Grade in [_GRADE_DISPLAY_MIN, _GRADE_DISPLAY_MAX].
    """
    if candidate.espn_grade is not None and candidate.espn_grade > 0:
        return round(candidate.espn_grade, 1)

    ratio = (candidate.base_score - _GRADE_SCORE_MIN) / (
        _GRADE_SCORE_MAX - _GRADE_SCORE_MIN
    )
    derived = _GRADE_DISPLAY_MIN + ratio * (_GRADE_DISPLAY_MAX - _GRADE_DISPLAY_MIN)
    return round(max(_GRADE_DISPLAY_MIN, min(_GRADE_DISPLAY_MAX, derived)), 1)


def _build_grade_breakdown(candidate: PlayerCandidate) -> dict:
    """
    Build a grade explanation dict for display in the expanded pick panel.

    Args:
        candidate (PlayerCandidate): Scored prospect.

    Returns:
        dict: Keys grade_source, base_score, formula, components.
    """
    mock_picks = candidate.mock_picks or []
    has_espn = candidate.espn_grade is not None and candidate.espn_grade > 0
    has_mock = bool(mock_picks)

    if has_espn:
        grade_source = "ESPN Scouting Grade"
        formula = "ESPN 55% + Mock Consensus 45%" if has_mock else "ESPN Grade (primary)"
    elif has_mock:
        grade_source = "Model-Derived (Mock Consensus)"
        formula = "Mock consensus log-linear curve"
    else:
        grade_source = "Model-Derived (Big Board Rank)"
        formula = "Big board rank log-linear curve"

    components: dict[str, str] = {}
    if has_espn:
        components["ESPN Grade"] = f"{candidate.espn_grade:.1f}/10"
    if candidate.espn_rank:
        components["Big Board Rank"] = f"#{candidate.espn_rank}"
    if has_mock:
        avg_pick = sum(mock_picks) / len(mock_picks)
        components[f"Mock Consensus ({len(mock_picks)} src)"] = f"#{avg_pick:.0f} avg"
    if candidate.buzz_score is not None:
        components["Buzz Score"] = f"{candidate.buzz_score:.0f}/100"

    return {
        "grade_source": grade_source,
        "formula": formula,
        "base_score": round(candidate.base_score, 1),
        "components": components,
    }


def _candidate_to_player_dict(candidate: PlayerCandidate) -> dict:
    """
    Convert a PlayerCandidate to a Player-compatible JSON dict.

    Args:
        candidate (PlayerCandidate): Simulated draft selection.

    Returns:
        dict: JSON-serialisable player record matching the Player Pydantic model.
    """
    combine = candidate.combine or {}
    bio: dict = {}
    for field in ("height_inches", "weight_lbs", "wingspan_inches",
                  "standing_reach_inches", "lane_agility_seconds",
                  "sprint_seconds", "vertical_jump_inches", "max_vertical_inches"):
        if combine.get(field):
            bio[field] = combine[field]

    # Build Projection stat view
    grade_bd = _build_grade_breakdown(candidate)
    proj: dict[str, str | int | float] = {}
    if candidate.espn_grade:
        proj["ESPN Grade"] = f"{candidate.espn_grade:.1f}/10"
    if candidate.espn_rank:
        proj["Big Board Rank"] = f"#{candidate.espn_rank}"
    if candidate.mock_picks:
        avg_p = sum(candidate.mock_picks) / len(candidate.mock_picks)
        proj["Mock Consensus"] = f"#{avg_p:.0f} avg ({len(candidate.mock_picks)} src)"
    proj["Model Score"] = f"{grade_bd['base_score']}/100"

    stat_views = [{
        "view_name": "Projection",
        "season": "2026",
        "stats": proj,
    }]

    grade = _compute_display_grade(candidate)

    mock_note = ""
    if candidate.mock_picks:
        avg_mock = sum(candidate.mock_picks) / len(candidate.mock_picks)
        mock_note = (
            f"Mock consensus avg pick: {avg_mock:.1f} "
            f"({len(candidate.mock_picks)} source(s)). "
        )

    return {
        "player_id": candidate.player_id,
        "name": candidate.name,
        "position": candidate.position,
        "college": candidate.college,
        "college_logo_url": None,
        "bio": bio,
        "injury_history": [],
        "stat_views": stat_views,
        "media_links": [],
        "tweets": [],
        "grade": grade,
        "grade_breakdown": grade_bd,
        "notes": (
            f"{mock_note}Model score: {grade_bd['base_score']}/100 "
            f"({grade_bd['grade_source']})."
        ),
    }


def _load_picks_json() -> dict:
    """
    Load picks.json from disk.

    Returns:
        dict: Parsed picks JSON with a "picks" key.
    """
    if not _PICKS_PATH.exists():
        return {"picks": []}
    with open(_PICKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
