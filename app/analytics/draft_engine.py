"""
Draft scoring engine for the NBA Mock Draft prediction engine.

Computes a team-specific value score for every available player at each
pick, incorporating position tier weights, team need boosts, and supply
pressure factors that update dynamically as the simulation progresses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.analytics.player_pool import PlayerCandidate
    from app.analytics.team_context import TeamNeedState

from app.analytics.position_value import (
    apply_position_weight,
    get_supply_pressure_config,
)
from app.analytics.team_context import get_need_boost_for_team

logger = logging.getLogger(__name__)

# Quality scaling constants for need boost attenuation.
# Reason: a marginal player at a needed position should not receive the same
# boost as an elite prospect. Quality gate scales the boost proportionally.
_QUALITY_FLOOR = 15.0
_QUALITY_CEILING = 100.0

# Franchise talent premium threshold.
# Reason: truly elite prospects (base_score ≥ 85, ~grade 8.5+) get a
# multiplier that reflects the "you cannot pass on this player" dynamic
# in real drafts. Prevents a team's positional need from burying a generational
# talent whose grade gap vs. the next-best player is too large to ignore.
_FRANCHISE_THRESHOLD = 85.0
_FRANCHISE_SCALE = 30.0  # at base_score=115 the multiplier would be 2.0x


def compute_team_value(
    player: "PlayerCandidate",
    team_state: "TeamNeedState",
    available_players: list["PlayerCandidate"],
    *,
    _pos_index: "dict[str, list[PlayerCandidate]] | None" = None,
) -> float:
    """
    Compute the team-specific value of a player for a given team at this pick.

    Formula:
        team_value = position_adjusted
                   * (1 + need_boost)
                   * supply_pressure_factor

    Args:
        player (PlayerCandidate): The candidate being evaluated.
        team_state (TeamNeedState): Current need state for the selecting team.
        available_players (list[PlayerCandidate]): All still-available players.
        _pos_index (dict | None): Pre-built position index to avoid redundant filtering.

    Returns:
        float: Composite team value score (higher = better fit for this team).
    """
    # Step 1: position-adjusted base score
    pos_adjusted = apply_position_weight(player.base_score, player.position)

    # Step 2: team need boost
    need_boost = get_need_boost_for_team(team_state, player.position)

    # Quality gate: only positive boosts are quality-scaled
    if need_boost > 0:
        quality_range = _QUALITY_CEILING - _QUALITY_FLOOR
        quality_scale = max(
            0.0, min(1.0, (player.base_score - _QUALITY_FLOOR) / quality_range)
        )
        need_boost = need_boost * quality_scale

    need_multiplier = 1.0 + need_boost

    # Step 3: supply pressure factor
    supply_factor = _supply_pressure_factor(
        player=player,
        team_state=team_state,
        available_players=available_players,
        pos_index=_pos_index,
    )

    # Step 4: franchise talent premium
    # Reason: genuinely elite prospects (base_score ≥ 85) should not fall
    # because of positional need — teams cannot afford to pass on them.
    franchise_mult = 1.0
    if player.base_score >= _FRANCHISE_THRESHOLD:
        franchise_mult = 1.0 + (player.base_score - _FRANCHISE_THRESHOLD) / _FRANCHISE_SCALE

    return pos_adjusted * need_multiplier * supply_factor * franchise_mult


def _supply_pressure_factor(
    player: "PlayerCandidate",
    team_state: "TeamNeedState",
    available_players: list["PlayerCandidate"],
    pos_index: "dict[str, list[PlayerCandidate]] | None" = None,
) -> float:
    """
    Compute a supply pressure multiplier for a player's position.

    Args:
        player (PlayerCandidate): The candidate being scored.
        team_state (TeamNeedState): Current team need state.
        available_players (list[PlayerCandidate]): Remaining available players.
        pos_index (dict | None): Optional pre-built position index.

    Returns:
        float: Multiplier in range [1.0, max_boost]. 1.0 means no pressure.
    """
    sp_config = get_supply_pressure_config()
    cliff_threshold = sp_config["talent_cliff_threshold"]
    drain_threshold = sp_config["early_drain_threshold"]
    max_boost = sp_config["max_boost"]

    position = player.position
    need_level = team_state.get_need(position)

    if need_level < 3:
        return 1.0

    if pos_index is not None:
        pos_players = pos_index.get(position, [])
    else:
        pos_players = sorted(
            [p for p in available_players if p.position == position],
            key=lambda p: p.base_score,
            reverse=True,
        )

    if not pos_players:
        return 1.0

    talent_cliff = 0.0
    if len(pos_players) >= 2:
        talent_cliff = pos_players[0].base_score - pos_players[1].base_score

    drain_rate = _compute_drain_rate(position, available_players, pos_index)

    cliff_pressure = talent_cliff > cliff_threshold
    drain_pressure = drain_rate > drain_threshold

    if not cliff_pressure and not drain_pressure:
        return 1.0

    pressure_strength = 0.0
    if cliff_pressure:
        pressure_strength = max(
            pressure_strength,
            min(1.0, talent_cliff / (cliff_threshold * 2)),
        )
    if drain_pressure:
        pressure_strength = max(pressure_strength, min(1.0, drain_rate))

    factor = 1.0 + (max_boost - 1.0) * pressure_strength
    return min(max_boost, factor)


def _compute_drain_rate(
    position: str,
    available_players: list["PlayerCandidate"],
    pos_index: "dict[str, list[PlayerCandidate]] | None" = None,
) -> float:
    """
    Estimate how much of the top talent at a position has already been picked.

    Args:
        position (str): Position code to evaluate.
        available_players (list[PlayerCandidate]): Remaining available players.
        pos_index (dict | None): Optional pre-built position index.

    Returns:
        float: Drain rate in [0.0, 1.0]; 1.0 = all top-8 gone.
    """
    _TOP_N = 8  # Reason: top-8 per position is the meaningful premium tier in NBA

    if pos_index is not None:
        pos_players = pos_index.get(position, [])
    else:
        pos_players = [p for p in available_players if p.position == position]

    if not pos_players:
        return 1.0

    still_available = min(_TOP_N, len(pos_players))
    return 1.0 - (still_available / _TOP_N)


def rank_players_for_team(
    available_players: list["PlayerCandidate"],
    team_state: "TeamNeedState",
) -> list[tuple[float, "PlayerCandidate"]]:
    """
    Score all available players for a team and return sorted (score, player) pairs.

    Args:
        available_players (list[PlayerCandidate]): All still-available players.
        team_state (TeamNeedState): Current team need state.

    Returns:
        list[tuple[float, PlayerCandidate]]: Sorted descending by team value.
    """
    # Reason: build position index once here so supply pressure checks inside
    # compute_team_value avoid O(n) re-filtering for every player scored.
    pos_index: dict[str, list["PlayerCandidate"]] = {}
    for p in available_players:
        pos_index.setdefault(p.position, []).append(p)
    for lst in pos_index.values():
        lst.sort(key=lambda p: p.base_score, reverse=True)

    scored = [
        (compute_team_value(p, team_state, available_players, _pos_index=pos_index), p)
        for p in available_players
    ]
    return sorted(scored, key=lambda x: x[0], reverse=True)
