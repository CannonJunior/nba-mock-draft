"""
Position value and need boost configuration for the NBA Mock Draft engine.

Defines position tier weights and need boost multipliers used by the
draft scoring engine. All config is loaded from module-level constants
so it can be invalidated and reloaded without a server restart.
"""

from __future__ import annotations

# Position tier weights for NBA.
# Reason: wings (SF) and playmakers (PG) command premium value in modern NBA.
# All positions are weighted relative to the baseline of 1.0.
_POSITION_WEIGHTS: dict[str, float] = {
    "PG": 1.10,   # Playmakers are franchise cornerstones
    "SG": 1.05,   # Shooting guards valued for shooting + athleticism
    "SF": 1.15,   # Wings most versatile and valuable in modern NBA
    "PF": 1.05,   # Stretch fours and switchable bigs are premium
    "C":  1.10,   # Rim protectors and modern big men highly valued
    "G":  1.05,   # Generic guard
    "F":  1.08,   # Generic forward
}

# Need boost multipliers by need level (1-5 scale).
# Reason: additive fractions applied as (1 + boost) in the scoring formula.
# Level 5 = critical need (~35% boost), level 0 = no need (-12% penalty).
_NEED_BOOSTS: dict[int, float] = {
    5: 0.35,   # Critical need — strongly prefer this position
    4: 0.20,   # High need
    3: 0.08,   # Moderate need
    2: 0.00,   # Low need — neutral
    1: -0.05,  # Minimal need — slight penalty
    0: -0.12,  # Already addressed — penalise
}

# Supply pressure configuration for the scoring engine.
_SUPPLY_PRESSURE_CONFIG: dict[str, float] = {
    "talent_cliff_threshold": 12.0,  # base_score gap that triggers cliff pressure
    "early_drain_threshold": 0.50,   # fraction of top-10 gone that triggers drain
    "max_boost": 1.20,               # maximum supply pressure multiplier
}

# Invalidation flag: set True to re-read config on next call.
_cache_valid: bool = True


def apply_position_weight(base_score: float, position: str) -> float:
    """
    Apply the position tier weight to a player's base score.

    Args:
        base_score (float): Raw 0-100 composite score.
        position (str): Canonical NBA position code (e.g. "SF").

    Returns:
        float: Position-adjusted score.
    """
    weight = _POSITION_WEIGHTS.get(position, 1.0)
    return base_score * weight


def get_need_boost(need_level: int) -> float:
    """
    Return the additive need boost for a given need level.

    Args:
        need_level (int): Need level 0-5.

    Returns:
        float: Additive boost value; positive = want this position,
               negative = don't need this position.
    """
    clamped = max(0, min(5, need_level))
    return _NEED_BOOSTS.get(clamped, 0.0)


def get_supply_pressure_config() -> dict[str, float]:
    """
    Return the supply pressure configuration dict.

    Returns:
        dict[str, float]: Keys talent_cliff_threshold, early_drain_threshold,
            max_boost.
    """
    return _SUPPLY_PRESSURE_CONFIG.copy()


def invalidate_cache() -> None:
    """
    Mark the position value config as stale so it reloads on next access.

    Currently a no-op since config is module-level constants, but kept
    for API parity with the NFL version to avoid breaking callers.
    """
    global _cache_valid
    _cache_valid = False
