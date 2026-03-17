"""
Team context module for the NBA Mock Draft prediction engine.

Loads team positional needs from config and maintains per-team
TeamNeedState objects that are updated throughout the simulation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_TEAM_NEEDS_CONFIG_PATH = (
    Path(__file__).parent.parent.parent / "data" / "config" / "team_needs_2026.json"
)
_TEAM_MAP_PATH = (
    Path(__file__).parent.parent.parent / "data" / "config" / "team_name_map.json"
)

# Default need level when no data exists for a team-position pair
_DEFAULT_NEED_LEVEL = 2

_NEED_REDUCTION_HIGH = 2   # applied when current level >= 4
_NEED_REDUCTION_LOW = 1    # applied when current level 1-3
_NEED_FLOOR = 0

# Positions where drafting one player fully zeros out the team's need.
# Reason: teams rarely draft two franchise point guards in the same draft.
_ZERO_OUT_AFTER_DRAFT: set[str] = set()


@dataclass
class TeamNeedState:
    """
    Mutable need state for a single NBA team during simulation.

    Attributes:
        team (str): Team abbreviation (e.g. "gsw").
        needs (dict[str, int]): Position → need level 1-5.
        picks_made (list[str]): Positions drafted so far in this simulation.
    """

    team: str
    needs: dict[str, int] = field(default_factory=dict)
    picks_made: list[str] = field(default_factory=list)

    def get_need(self, position: str) -> int:
        """
        Return the current need level for a position.

        Args:
            position (str): Position code (e.g. "PG").

        Returns:
            int: Need level 0-5; defaults to _DEFAULT_NEED_LEVEL if unknown.
        """
        return self.needs.get(position, _DEFAULT_NEED_LEVEL)


def build_team_need_states(team_abbrevs: list[str]) -> dict[str, TeamNeedState]:
    """
    Build a TeamNeedState for every team abbreviation from config.

    Args:
        team_abbrevs (list[str]): List of team abbreviations.

    Returns:
        dict[str, TeamNeedState]: Mapping of team abbreviation → TeamNeedState.
    """
    config_needs = _load_team_needs_from_config()

    states: dict[str, TeamNeedState] = {}
    for abbrev in team_abbrevs:
        needs = config_needs.get(abbrev.lower(), {})
        states[abbrev] = TeamNeedState(team=abbrev, needs=needs)

    logger.info(
        "Team need states built for %d teams (%d with config data)",
        len(states),
        sum(1 for s in states.values() if s.needs),
    )
    return states


def update_team_need(state: TeamNeedState, position_drafted: str) -> None:
    """
    Reduce a team's need for a position after they draft a player there.

    Args:
        state (TeamNeedState): The team's current need state (mutated in place).
        position_drafted (str): Position code of the player just drafted.
    """
    current = state.needs.get(position_drafted, _DEFAULT_NEED_LEVEL)

    if position_drafted in _ZERO_OUT_AFTER_DRAFT:
        state.needs[position_drafted] = _NEED_FLOOR
    elif current >= _NEED_REDUCTION_HIGH:
        state.needs[position_drafted] = max(_NEED_FLOOR, current - _NEED_REDUCTION_HIGH)
    else:
        state.needs[position_drafted] = max(_NEED_FLOOR, current - _NEED_REDUCTION_LOW)

    state.picks_made.append(position_drafted)

    logger.debug(
        "[%s] Drafted %s — need level %d → %d",
        state.team,
        position_drafted,
        current,
        state.needs[position_drafted],
    )


def get_need_boost_for_team(state: TeamNeedState, position: str) -> float:
    """
    Return the need boost multiplier for a team-position pair.

    Args:
        state (TeamNeedState): Current team need state.
        position (str): Position to evaluate.

    Returns:
        float: Additive boost value from the position_value config.
    """
    from app.analytics.position_value import get_need_boost

    need_level = state.get_need(position)
    return get_need_boost(need_level)


def _load_team_needs_from_config() -> dict[str, dict[str, int]]:
    """
    Load curated team needs from data/config/team_needs_2026.json.

    Returns:
        dict[str, dict[str, int]]: Lower-cased team abbreviation →
            {position: need_level}. Empty dict if file is missing.
    """
    if not _TEAM_NEEDS_CONFIG_PATH.exists():
        return {}

    try:
        with open(_TEAM_NEEDS_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {k.lower(): v for k, v in raw.get("teams", {}).items()}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load team_needs_2026.json: %s", exc)
        return {}
