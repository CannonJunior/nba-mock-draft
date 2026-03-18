"""
Season simulator for the NBA 2025-2026 season.

Simulates remaining games to determine final records, runs the draft lottery
to determine top-pick order, then updates picks.json with the new draft order.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_PICKS_PATH = _DATA_DIR / "picks.json"
_RECORDS_PATH = _DATA_DIR / "config" / "team_records_2026.json"
_TRADE_CONFIG_PATH = _DATA_DIR / "config" / "draft_pick_trades_2026.json"

# NBA draft lottery odds (index 0 = worst record, index 13 = best lottery record).
# These odds govern which team wins each of the top-4 lottery picks.
_LOTTERY_ODDS: list[float] = [
    14.0,  # rank 1  (worst)
    13.4,  # rank 2
    12.7,  # rank 3
    12.0,  # rank 4
    10.5,  # rank 5
    9.0,   # rank 6
    7.5,   # rank 7
    6.0,   # rank 8
    4.5,   # rank 9
    3.0,   # rank 10
    2.0,   # rank 11
    1.5,   # rank 12
    1.0,   # rank 13
    0.5,   # rank 14 (best of lottery teams)
]


@dataclass
class TeamRecord:
    """Current and simulated win-loss record for one NBA team."""

    abbreviation: str
    wins: int
    losses: int
    games_remaining: int
    conference: str  # "east" or "west"

    @property
    def win_pct(self) -> float:
        """Return win percentage (0.0–1.0)."""
        played = self.wins + self.losses
        return self.wins / played if played > 0 else 0.5

    @property
    def games_played(self) -> int:
        """Return number of games already played."""
        return self.wins + self.losses


@dataclass
class SimulationResult:
    """Full output of a season-plus-lottery simulation run."""

    final_records: dict[str, TeamRecord]
    lottery_order: list[str]      # 14 lottery teams in final pick order (pick 1 = index 0)
    playoff_order: list[str]      # 16 non-lottery teams, worst-to-best record
    full_draft_order: list[str]   # all 30 teams, picks 1-30 (index 0 = pick 1)
    lottery_odds_used: dict[str, float]  # team abbr -> lottery odds %


def load_team_records() -> dict[str, TeamRecord]:
    """
    Load current 2025-26 team records from config.

    Returns:
        dict[str, TeamRecord]: Mapping of team abbreviation to TeamRecord.

    Raises:
        FileNotFoundError: If team_records_2026.json does not exist.
    """
    with open(_RECORDS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        entry["abbreviation"]: TeamRecord(
            abbreviation=entry["abbreviation"],
            wins=entry["wins"],
            losses=entry["losses"],
            games_remaining=entry["games_remaining"],
            conference=entry["conference"],
        )
        for entry in data["teams"]
    }


def simulate_remaining_games(records: dict[str, TeamRecord]) -> dict[str, TeamRecord]:
    """
    Simulate each team's remaining regular-season games independently.

    Each remaining game is a Bernoulli trial where the win probability is
    derived from the team's current win percentage, lightly regressed toward
    .500 to reflect end-of-season variance.

    Args:
        records: Current team records keyed by abbreviation.

    Returns:
        Updated records after all remaining games are simulated.
    """
    for record in records.values():
        base_pct = record.win_pct
        # Regress 30% toward .500 to add realistic variance.
        adjusted_pct = 0.70 * base_pct + 0.30 * 0.50
        for _ in range(record.games_remaining):
            if random.random() < adjusted_pct:
                record.wins += 1
            else:
                record.losses += 1
        record.games_remaining = 0

    return records


def _weighted_lottery_draw(teams: list[str], weights: list[float]) -> str:
    """
    Draw one team from a weighted lottery pool (without replacement logic
    handled by the caller).

    Args:
        teams: List of eligible team abbreviations.
        weights: Parallel list of lottery weights.

    Returns:
        The abbreviation of the winning team.
    """
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0.0
    for team, weight in zip(teams, weights):
        cumulative += weight
        if r <= cumulative:
            return team
    return teams[-1]  # fallback (floating-point edge case)


def run_lottery(lottery_teams: list[str]) -> list[str]:
    """
    Simulate the NBA draft lottery for the 14 lowest-record teams.

    The lottery determines the top-4 picks via weighted random draw.
    Picks 5-14 go to the remaining lottery teams in order of record
    (worst to best), as in the real NBA.

    Args:
        lottery_teams: 14 team abbreviations sorted worst-to-best record
                       (index 0 = worst record = highest odds).

    Returns:
        14 team abbreviations in final lottery pick order (index 0 = pick 1).
    """
    if len(lottery_teams) != 14:
        raise ValueError(f"Expected 14 lottery teams, got {len(lottery_teams)}")

    remaining = list(lottery_teams)
    remaining_weights = list(_LOTTERY_ODDS)
    top_4: list[str] = []

    for _ in range(4):
        winner = _weighted_lottery_draw(remaining, remaining_weights)
        idx = remaining.index(winner)
        top_4.append(winner)
        remaining.pop(idx)
        remaining_weights.pop(idx)

    # Picks 5-14: remaining teams maintain worst-to-best record order.
    return top_4 + remaining


def simulate_season_and_lottery(seed: Optional[int] = None) -> SimulationResult:
    """
    Run the full season simulation and draft lottery.

    Steps:
    1. Load current team records.
    2. Simulate remaining regular-season games.
    3. Rank all 30 teams by final wins to identify lottery (bottom 14)
       and non-lottery (top 16) groups.
    4. Run the lottery to determine picks 1-4.
    5. Assign picks 5-14 to remaining lottery teams by record.
    6. Assign picks 15-30 to non-lottery teams, worst-to-best.

    Args:
        seed: Optional random seed for reproducibility in tests.

    Returns:
        SimulationResult with final records and full 30-team draft order.
    """
    if seed is not None:
        random.seed(seed)

    records = load_team_records()
    final_records = simulate_remaining_games(records)

    # Sort all 30 teams by wins ascending (worst first).
    # Use losses descending as tiebreaker (more losses = slightly worse).
    sorted_teams = sorted(
        final_records.values(),
        key=lambda r: (r.wins, -r.losses),
    )

    lottery_teams = [r.abbreviation for r in sorted_teams[:14]]
    playoff_teams = [r.abbreviation for r in sorted_teams[14:]]  # worst→best

    lottery_odds_used = {
        team: _LOTTERY_ODDS[i] for i, team in enumerate(lottery_teams)
    }

    lottery_order = run_lottery(lottery_teams)

    return SimulationResult(
        final_records=final_records,
        lottery_order=lottery_order,
        playoff_order=playoff_teams,
        full_draft_order=lottery_order + playoff_teams,
        lottery_odds_used=lottery_odds_used,
    )


def apply_draft_order_to_picks(result: SimulationResult) -> int:
    """
    Rewrite picks.json with the simulated draft order, applying all known
    trade rules via TradeResolver.

    Round 1 (picks 1-30) and Round 2 (picks 31-60) are both resolved using
    the trade rules in draft_pick_trades_2026.json.  Player assignments and
    need snapshots are cleared so the draft simulation can repopulate them.

    Args:
        result: SimulationResult from simulate_season_and_lottery().

    Returns:
        Total number of pick records updated.
    """
    from app.analytics.trade_resolver import TradeResolver

    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    assignments = resolver.resolve_all(result.full_draft_order)

    with open(_PICKS_PATH, "r", encoding="utf-8") as f:
        picks_data = json.load(f)

    updated = 0
    for pick_row in picks_data.get("picks", []):
        pick_number: int = pick_row["pick_number"]
        round_num: int = pick_row["round"]
        pick_in_round: int = pick_row["pick_in_round"]

        assignment = assignments.get(pick_number)
        if assignment:
            pick_row["current_team"] = assignment.current_team
            pick_row["traded_from"] = assignment.traded_from
            pick_row["trade_notes"] = assignment.trade_notes
            updated += 1
        else:
            # Fallback: use base order (no trade rule found)
            team_idx = pick_in_round - 1
            if team_idx < len(result.full_draft_order):
                pick_row["current_team"] = result.full_draft_order[team_idx]
                pick_row["traded_from"] = []
                pick_row["trade_notes"] = None

        if round_num == 1:
            pick_row["is_lottery"] = (pick_in_round <= 14)

        # Clear stale player assignments; draft sim will repopulate.
        pick_row["player_id"] = None
        pick_row["team_needs_snapshot"] = None

    with open(_PICKS_PATH, "w", encoding="utf-8") as f:
        json.dump(picks_data, f, indent=2, ensure_ascii=False)

    logger.info(
        "Rewrote %d pick records with trade-resolved draft order (lottery top 4: %s)",
        updated,
        ", ".join(result.lottery_order[:4]),
    )
    return updated


def load_current_records() -> dict[str, tuple[int, int]]:
    """
    Load current mid-season team records from config.

    Always reads from team_records_2026.json — never from any cached or
    simulated file — so the page shows real current standings on startup.

    Returns:
        dict mapping team abbreviation to (wins, losses) tuples.
    """
    try:
        with open(_RECORDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            entry["abbreviation"]: (entry["wins"], entry["losses"])
            for entry in data.get("teams", [])
        }
    except Exception:
        return {}


def build_simulation_summary(result: SimulationResult) -> dict:
    """
    Build a JSON-serialisable summary of the simulation result for the API.

    Args:
        result: SimulationResult from simulate_season_and_lottery().

    Returns:
        dict with final_records, lottery_order, and full_draft_order.
    """
    records_out = {
        abbr: {
            "wins": rec.wins,
            "losses": rec.losses,
            "win_pct": round(rec.win_pct, 3),
            "conference": rec.conference,
        }
        for abbr, rec in result.final_records.items()
    }

    return {
        "final_records": records_out,
        "lottery_order": result.lottery_order,
        "playoff_order": result.playoff_order,
        "full_draft_order": result.full_draft_order,
        "lottery_odds_used": result.lottery_odds_used,
    }
