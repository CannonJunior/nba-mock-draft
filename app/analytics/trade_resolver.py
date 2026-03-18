"""
Trade resolver for NBA 2026 draft pick obligations.

Applies all known trade rules (transfers, protections, range-only conditions,
swap groups, and best-of groups) to a post-lottery draft order to produce the
final pick ownership for all 60 draft slots.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TRADE_CONFIG_PATH = Path(__file__).parent.parent.parent / "data" / "config" / "draft_pick_trades_2026.json"


@dataclass
class PickAssignment:
    """Final ownership assignment for a single draft pick slot."""

    slot: int               # 1-based position in the draft order for this round
    current_team: str       # team that holds the pick right
    original_team: str      # team whose record/lottery position determines the slot
    traded_from: list[str] = field(default_factory=list)  # prior owners (chain)
    trade_notes: Optional[str] = None


class TradeResolver:
    """
    Resolve final pick ownership for the 2026 NBA Draft by applying all known
    trade rules to a post-lottery base order.

    Resolution pipeline (applied in order):
        1. Apply best-of groups (multi-team pick distributions)
        2. Apply swap groups (multi-team positional swaps)
        3. Apply simple (unconditional) transfers
        4. Apply protected transfers (top-N and special protections)
        5. Apply range-only transfers (picks that convey only within a slot window)

    The input ``draft_order`` is the post-lottery list of 30 teams ordered
    worst-to-best (index 0 = pick 1).  The slot for each team equals its
    1-based index in this list.  All protection thresholds are evaluated
    against these final slot positions, so the caller must pass the fully
    lottery-adjusted order.
    """

    def __init__(self, config_path: Path = _TRADE_CONFIG_PATH) -> None:
        """
        Load trade rules from the config file.

        Args:
            config_path: Path to draft_pick_trades_2026.json.
        """
        with open(config_path, "r", encoding="utf-8") as f:
            self._config = json.load(f)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_all(self, draft_order: list[str]) -> dict[int, PickAssignment]:
        """
        Resolve all 60 pick assignments (rounds 1 and 2) using the provided
        post-lottery draft order.

        Args:
            draft_order: 30 team abbreviations, index 0 = pick 1 (worst record
                         or lottery winner).

        Returns:
            dict mapping pick_number (1-60) to PickAssignment.
        """
        r1 = self.resolve(draft_order, round_num=1)
        r2 = self.resolve(draft_order, round_num=2)

        result: dict[int, PickAssignment] = {}
        for assignment in r1:
            pick_number = assignment.slot            # R1: slot == pick_number
            result[pick_number] = assignment
        for assignment in r2:
            pick_number = 30 + assignment.slot       # R2: pick_number = 30 + slot
            result[pick_number] = assignment

        return result

    def resolve(self, draft_order: list[str], round_num: int) -> list[PickAssignment]:
        """
        Resolve pick ownership for one round.

        Args:
            draft_order: 30 teams in slot order (index 0 = slot 1).
            round_num: 1 or 2.

        Returns:
            List of 30 PickAssignment objects ordered by slot (1-30).
        """
        rules = self._config["first_round" if round_num == 1 else "second_round"]

        # Build working state: slot → assignment
        assignments: dict[int, PickAssignment] = {
            i + 1: PickAssignment(
                slot=i + 1,
                current_team=team,
                original_team=team,
            )
            for i, team in enumerate(draft_order)
        }

        # team → current slot (updated after each phase)
        team_slot: dict[str, list[int]] = {}
        for slot, a in assignments.items():
            team_slot.setdefault(a.original_team, []).append(slot)

        # Phase 1: Best-of groups
        self._apply_best_of_groups(assignments, team_slot, rules.get("best_of_groups", []))

        # Phase 2: Swap groups
        self._apply_swap_groups(assignments, team_slot, rules.get("swap_groups", []))

        # Phase 3: Simple transfers
        self._apply_simple_transfers(assignments, team_slot, rules.get("simple_transfers", []))

        # Phase 4: Protected transfers
        self._apply_protected_transfers(
            assignments, team_slot, rules.get("protected_transfers", []),
            draft_order, round_num
        )

        # Phase 5: Range-only transfers
        self._apply_range_only_transfers(
            assignments, team_slot, rules.get("range_only_transfers", [])
        )

        return sorted(assignments.values(), key=lambda a: a.slot)

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _find_slot_for_original_team(
        self, team: str, assignments: dict[int, PickAssignment]
    ) -> Optional[int]:
        """Return the slot whose original_team matches, or None."""
        for slot, a in assignments.items():
            if a.original_team == team:
                return slot
        return None

    def _apply_best_of_groups(
        self,
        assignments: dict[int, PickAssignment],
        team_slot: dict[str, list[int]],
        groups: list[dict],
    ) -> None:
        """
        For each best-of group, collect the source teams' original slots, sort
        ascending (lowest slot = best pick), and distribute according to the
        rank ordering in the config.
        """
        for group in groups:
            source_teams: list[str] = group["source_teams"]
            distribution: list[dict] = group["distribution"]
            notes: str = group.get("notes", "")

            # Collect (slot, original_team) pairs for all source teams
            source_slots: list[tuple[int, str]] = []
            for team in source_teams:
                slot = self._find_slot_for_original_team(team, assignments)
                if slot is not None:
                    source_slots.append((slot, team))

            # Sort ascending: best (lowest slot number) first
            source_slots.sort(key=lambda x: x[0])

            for rank_entry in distribution:
                rank = rank_entry["rank"] - 1       # 0-based index
                to_team = rank_entry["to_team"]

                if rank >= len(source_slots):
                    continue

                slot, orig_team = source_slots[rank]
                prev_owner = assignments[slot].current_team

                # Only update traded_from if ownership actually changes
                if prev_owner != to_team:
                    chain = list(assignments[slot].traded_from)
                    if prev_owner not in chain:
                        chain.append(prev_owner)
                    assignments[slot] = PickAssignment(
                        slot=slot,
                        current_team=to_team,
                        original_team=orig_team,
                        traded_from=chain,
                        trade_notes=notes,
                    )

    def _apply_swap_groups(
        self,
        assignments: dict[int, PickAssignment],
        team_slot: dict[str, list[int]],
        groups: list[dict],
    ) -> None:
        """
        For each swap group, collect each base team's original slot, sort
        ascending (best pick first), and redistribute according to priority_order
        (index 0 = highest priority = gets best pick).
        """
        for group in groups:
            base_teams: list[str] = group["base_teams"]
            priority_order: list[str] = group["priority_order"]
            notes: str = group.get("notes", "")

            # Collect (slot, original_team) for each base team
            group_slots: list[tuple[int, str]] = []
            for team in base_teams:
                slot = self._find_slot_for_original_team(team, assignments)
                if slot is not None:
                    group_slots.append((slot, team))

            if not group_slots:
                continue

            # Sort ascending: best pick (lowest slot) first
            group_slots.sort(key=lambda x: x[0])

            # Assign best slot to first team in priority_order, etc.
            for priority_idx, team in enumerate(priority_order):
                if priority_idx >= len(group_slots):
                    break

                slot, orig_team = group_slots[priority_idx]
                prev_owner = assignments[slot].current_team

                if prev_owner != team:
                    chain = list(assignments[slot].traded_from)
                    if prev_owner not in chain:
                        chain.append(prev_owner)
                    assignments[slot] = PickAssignment(
                        slot=slot,
                        current_team=team,
                        original_team=orig_team,
                        traded_from=chain,
                        trade_notes=notes,
                    )

    def _apply_simple_transfers(
        self,
        assignments: dict[int, PickAssignment],
        team_slot: dict[str, list[int]],
        transfers: list[dict],
    ) -> None:
        """Unconditionally reassign a team's pick to another team."""
        for transfer in transfers:
            from_team: str = transfer["from_team"]
            to_team: str = transfer["to_team"]
            notes: str = transfer.get("notes", "")

            slot = self._find_slot_for_original_team(from_team, assignments)
            if slot is None:
                logger.debug("simple_transfer: no slot found for from_team=%s", from_team)
                continue

            prev_owner = assignments[slot].current_team
            if prev_owner == to_team:
                continue  # already assigned correctly

            chain = list(assignments[slot].traded_from)
            if prev_owner not in chain:
                chain.append(prev_owner)

            assignments[slot] = PickAssignment(
                slot=slot,
                current_team=to_team,
                original_team=from_team,
                traded_from=chain,
                trade_notes=notes,
            )

    def _apply_protected_transfers(
        self,
        assignments: dict[int, PickAssignment],
        team_slot: dict[str, list[int]],
        transfers: list[dict],
        draft_order: list[str],
        round_num: int,
    ) -> None:
        """
        Apply pick transfers that are conditional on pick position.

        Protection types:
            "top"           — stays with from_team if slot <= threshold
            "r2_bottom"     — R2 only: stays with from_team if slot <= threshold
                              (i.e., pick number is in the "top N of R2" = picks 31 to 30+N)
            "r1_protected"  — R2 conditional: conveys only if from_team's R1 pick
                              was itself protected (stayed with the team)
        """
        for transfer in transfers:
            from_team: str = transfer["from_team"]
            to_team: str = transfer["to_team"]
            via: list[str] = transfer.get("via", [])
            protection_type: str = transfer["protection_type"]
            notes: str = transfer.get("notes", "")

            slot = self._find_slot_for_original_team(from_team, assignments)
            if slot is None:
                continue

            conveys = self._check_protected_conveys(
                protection_type=protection_type,
                threshold=transfer.get("protection_threshold", 0),
                slot=slot,
                from_team=from_team,
                draft_order=draft_order,
                round_num=round_num,
                assignments=assignments,
            )

            if not conveys:
                logger.debug(
                    "protected_transfer %s → %s: pick stays (slot=%d, threshold=%d)",
                    from_team, to_team, slot, transfer.get("protection_threshold", 0),
                )
                continue

            prev_owner = assignments[slot].current_team
            chain = list(assignments[slot].traded_from)
            if prev_owner not in chain:
                chain.append(prev_owner)
            for v in via:
                if v not in chain:
                    chain.append(v)

            assignments[slot] = PickAssignment(
                slot=slot,
                current_team=to_team,
                original_team=from_team,
                traded_from=chain,
                trade_notes=notes,
            )
            logger.debug(
                "protected_transfer %s → %s: pick conveys at slot %d",
                from_team, to_team, slot,
            )

    def _check_protected_conveys(
        self,
        protection_type: str,
        threshold: int,
        slot: int,
        from_team: str,
        draft_order: list[str],
        round_num: int,
        assignments: dict[int, PickAssignment],
    ) -> bool:
        """
        Return True if the protected transfer DOES convey (protection NOT triggered).

        Args:
            protection_type: One of "top", "r2_bottom", "r1_protected".
            threshold: Numeric threshold for the protection check.
            slot: The pick's current slot in this round (1-based).
            from_team: The team whose pick may convey.
            draft_order: The full post-lottery 30-team list.
            round_num: 1 or 2.
            assignments: Current R1 or R2 assignments (for cross-round lookups).
        """
        if protection_type == "top":
            # Stays with from_team if slot <= threshold; conveys if slot > threshold
            return slot > threshold

        if protection_type == "r2_bottom":
            # R2 variant: stays if slot <= threshold (top of R2); conveys otherwise
            return slot > threshold

        if protection_type == "r1_protected":
            # R2 pick conveys only if the from_team's R1 pick was top-8 protected
            # (i.e., stayed with the team).  We check whether from_team's R1 slot
            # is ≤ threshold (the R1 protection boundary is 8 for WAS→NYK).
            r1_slot = self._find_r1_slot_for_team(from_team, draft_order)
            if r1_slot is None:
                return False
            # The R1 pick is "protected" (stays with from_team) when r1_slot <= threshold
            return r1_slot <= threshold

        logger.warning("Unknown protection_type=%s; defaulting to no conveyance", protection_type)
        return False

    def _find_r1_slot_for_team(self, team: str, draft_order: list[str]) -> Optional[int]:
        """Return the 1-based R1 slot for a team in the base draft order, or None."""
        try:
            return draft_order.index(team) + 1
        except ValueError:
            return None

    def _apply_range_only_transfers(
        self,
        assignments: dict[int, PickAssignment],
        team_slot: dict[str, list[int]],
        transfers: list[dict],
    ) -> None:
        """
        Transfer a pick only when its slot falls within [min, max] (inclusive).
        Outside the range the pick stays with the from_team.
        """
        for transfer in transfers:
            from_team: str = transfer["from_team"]
            to_team: str = transfer["to_team"]
            slot_min: int = transfer["conveys_if_slot_min"]
            slot_max: int = transfer["conveys_if_slot_max"]
            notes: str = transfer.get("notes", "")

            slot = self._find_slot_for_original_team(from_team, assignments)
            if slot is None:
                continue

            if not (slot_min <= slot <= slot_max):
                logger.debug(
                    "range_only_transfer %s → %s: slot %d outside [%d,%d], stays",
                    from_team, to_team, slot, slot_min, slot_max,
                )
                continue

            prev_owner = assignments[slot].current_team
            if prev_owner == to_team:
                continue

            chain = list(assignments[slot].traded_from)
            if prev_owner not in chain:
                chain.append(prev_owner)

            assignments[slot] = PickAssignment(
                slot=slot,
                current_team=to_team,
                original_team=from_team,
                traded_from=chain,
                trade_notes=notes,
            )
            logger.debug(
                "range_only_transfer %s → %s: slot %d in [%d,%d], conveys",
                from_team, to_team, slot, slot_min, slot_max,
            )
