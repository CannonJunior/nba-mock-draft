"""
Tests for app.analytics.trade_resolver.TradeResolver.

Covers: PickAssignment dataclass, simple transfers, protected transfers,
range-only transfers, swap groups, best-of groups, and the full resolve pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analytics.trade_resolver import PickAssignment, TradeResolver

_DATA_DIR = Path(__file__).parent.parent / "data"
_TRADE_CONFIG_PATH = _DATA_DIR / "config" / "draft_pick_trades_2026.json"

# Canonical 30-team draft order that matches approximate current standings.
# Teams are listed worst-to-best record so index 0 = pick 1.
_CANONICAL_ORDER = [
    "ind",  # 1  – worst record
    "was",  # 2
    "bkn",  # 3
    "sac",  # 4
    "uta",  # 5
    "dal",  # 6
    "nop",  # 7
    "mem",  # 8
    "chi",  # 9
    "mil",  # 10
    "por",  # 11
    "gsw",  # 12
    "lac",  # 13
    "cha",  # 14
    "sas",  # 15
    "phi",  # 16
    "tor",  # 17
    "orl",  # 18
    "atl",  # 19
    "mia",  # 20
    "cle",  # 21
    "phx",  # 22
    "det",  # 23
    "den",  # 24
    "min",  # 25
    "hou",  # 26
    "lal",  # 27
    "nyk",  # 28
    "bos",  # 29
    "okc",  # 30
]


# ---------------------------------------------------------------------------
# PickAssignment dataclass
# ---------------------------------------------------------------------------


def test_pick_assignment_defaults():
    """PickAssignment initialises with empty chain and no notes."""
    pa = PickAssignment(slot=1, current_team="ind", original_team="ind")
    assert pa.traded_from == []
    assert pa.trade_notes is None


def test_pick_assignment_fields():
    """PickAssignment stores all fields correctly."""
    pa = PickAssignment(
        slot=5,
        current_team="okc",
        original_team="lac",
        traded_from=["lac"],
        trade_notes="test note",
    )
    assert pa.slot == 5
    assert pa.current_team == "okc"
    assert pa.original_team == "lac"
    assert pa.traded_from == ["lac"]
    assert pa.trade_notes == "test note"


# ---------------------------------------------------------------------------
# TradeResolver initialisation
# ---------------------------------------------------------------------------


def test_trade_resolver_loads_config():
    """TradeResolver loads the real trade config without error."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    assert resolver is not None


def test_trade_resolver_missing_config_raises(tmp_path):
    """TradeResolver raises FileNotFoundError for a missing config path."""
    with pytest.raises(FileNotFoundError):
        TradeResolver(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# resolve() – basic structure
# ---------------------------------------------------------------------------


def test_resolve_r1_returns_30_assignments():
    """resolve() for round 1 always returns exactly 30 PickAssignment objects."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    assert len(result) == 30


def test_resolve_r2_returns_30_assignments():
    """resolve() for round 2 always returns exactly 30 PickAssignment objects."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)
    assert len(result) == 30


def test_resolve_slots_are_1_to_30():
    """Resolved assignments have slots numbered 1 through 30 (no gaps)."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    assert [a.slot for a in result] == list(range(1, 31))


def test_resolve_all_returns_60_picks():
    """resolve_all() returns a dict with keys 1-60."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve_all(_CANONICAL_ORDER)
    assert set(result.keys()) == set(range(1, 61))


def test_resolve_all_pick_number_mapping():
    """R1 assignments have pick_number == slot; R2 assignments have pick_number == 30 + slot."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve_all(_CANONICAL_ORDER)
    for pick_number, assignment in result.items():
        if pick_number <= 30:
            assert assignment.slot == pick_number
        else:
            assert assignment.slot == pick_number - 30


# ---------------------------------------------------------------------------
# Simple transfers
# ---------------------------------------------------------------------------


def test_simple_transfer_lac_to_okc():
    """LAC's first-round pick (slot 13 in canonical order) goes to OKC."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    lac_slot = _CANONICAL_ORDER.index("lac") + 1  # 13
    assignment = next(a for a in result if a.slot == lac_slot)
    assert assignment.current_team == "okc"
    assert assignment.original_team == "lac"
    assert "lac" in assignment.traded_from


def test_simple_transfer_orl_to_mem():
    """ORL's first-round pick goes to MEM."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    orl_slot = _CANONICAL_ORDER.index("orl") + 1  # 18
    assignment = next(a for a in result if a.slot == orl_slot)
    assert assignment.current_team == "mem"
    assert assignment.original_team == "orl"


def test_simple_transfer_phx_to_cha():
    """PHX's first-round pick goes to CHA."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    phx_slot = _CANONICAL_ORDER.index("phx") + 1  # 22 in canonical order
    assignment = next(a for a in result if a.slot == phx_slot)
    assert assignment.current_team == "cha"
    assert assignment.original_team == "phx"


# ---------------------------------------------------------------------------
# Protected transfers
# ---------------------------------------------------------------------------


def test_protected_phi_to_okc_conveys_outside_top4():
    """PHI's pick at slot 16 (outside top-4) conveys to OKC."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    phi_slot = _CANONICAL_ORDER.index("phi") + 1  # 16
    assignment = next(a for a in result if a.slot == phi_slot)
    assert assignment.current_team == "okc"
    assert assignment.original_team == "phi"


def test_protected_phi_to_okc_stays_inside_top4():
    """PHI's pick at slot <= 4 stays with PHI (top-4 protection)."""
    order = list(_CANONICAL_ORDER)
    # Move phi to slot 3 by inserting at index 2
    order.remove("phi")
    order.insert(2, "phi")
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=1)
    phi_slot = order.index("phi") + 1
    assert phi_slot <= 4
    assignment = next(a for a in result if a.slot == phi_slot)
    assert assignment.current_team == "phi"


def test_protected_hou_to_phi_via_okc_conveys_outside_top4():
    """HOU's pick at slot 26 (outside top-4) conveys to PHI (via OKC)."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    hou_slot = _CANONICAL_ORDER.index("hou") + 1  # 26
    assignment = next(a for a in result if a.slot == hou_slot)
    assert assignment.current_team == "phi"
    assert assignment.original_team == "hou"
    assert "okc" in assignment.traded_from


def test_protected_uta_to_okc_conveys_outside_top8():
    """UTA's pick at slot 5 is inside top-8, so stays with UTA."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    uta_slot = _CANONICAL_ORDER.index("uta") + 1  # 5
    assert uta_slot <= 8
    assignment = next(a for a in result if a.slot == uta_slot)
    # Protected (slot <= 8) → stays with UTA
    assert assignment.current_team == "uta"


def test_protected_uta_to_okc_conveys_outside_top8_when_slot_exceeds_8():
    """UTA's pick at slot 9 conveys to OKC."""
    order = list(_CANONICAL_ORDER)
    # Move uta to slot 9 (index 8)
    order.remove("uta")
    order.insert(8, "uta")
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=1)
    uta_slot = order.index("uta") + 1
    assert uta_slot == 9
    assignment = next(a for a in result if a.slot == uta_slot)
    assert assignment.current_team == "okc"


def test_protected_por_to_chi_stays_inside_top14():
    """POR at slot 11 is inside top-14, so pick stays with POR."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    por_slot = _CANONICAL_ORDER.index("por") + 1  # 11
    assert por_slot <= 14
    assignment = next(a for a in result if a.slot == por_slot)
    assert assignment.current_team == "por"


def test_protected_was_to_nyk_stays_inside_top8():
    """WAS at slot 2 stays with WAS (top-8 protected)."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    was_slot = _CANONICAL_ORDER.index("was") + 1  # 2
    assignment = next(a for a in result if a.slot == was_slot)
    assert assignment.current_team == "was"


def test_protected_was_to_nyk_conveys_outside_top8():
    """WAS at slot 9 conveys to NYK."""
    order = list(_CANONICAL_ORDER)
    order.remove("was")
    order.insert(8, "was")  # slot 9
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=1)
    was_slot = order.index("was") + 1
    assignment = next(a for a in result if a.slot == was_slot)
    assert assignment.current_team == "nyk"


# ---------------------------------------------------------------------------
# Range-only transfers
# ---------------------------------------------------------------------------


def test_range_only_ind_stays_outside_range():
    """IND at slot 1 (outside range 5-9) keeps its own pick."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    ind_slot = _CANONICAL_ORDER.index("ind") + 1  # 1
    assignment = next(a for a in result if a.slot == ind_slot)
    assert assignment.current_team == "ind"


def test_range_only_ind_conveys_inside_range():
    """IND at slot 7 (inside range 5-9) conveys to LAC."""
    order = list(_CANONICAL_ORDER)
    order.remove("ind")
    order.insert(6, "ind")  # slot 7
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=1)
    ind_slot = order.index("ind") + 1
    assignment = next(a for a in result if a.slot == ind_slot)
    assert assignment.current_team == "lac"
    assert assignment.original_team == "ind"


def test_range_only_ind_stays_at_slot_4():
    """IND at slot 4 (below min of 5) stays with IND."""
    order = list(_CANONICAL_ORDER)
    order.remove("ind")
    order.insert(3, "ind")  # slot 4
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=1)
    ind_slot = order.index("ind") + 1
    assignment = next(a for a in result if a.slot == ind_slot)
    assert assignment.current_team == "ind"


def test_range_only_ind_stays_at_slot_10():
    """IND at slot 10 (above max of 9) stays with IND."""
    order = list(_CANONICAL_ORDER)
    order.remove("ind")
    order.insert(9, "ind")  # slot 10
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=1)
    ind_slot = order.index("ind") + 1
    assignment = next(a for a in result if a.slot == ind_slot)
    assert assignment.current_team == "ind"


# ---------------------------------------------------------------------------
# Swap groups
# ---------------------------------------------------------------------------


def test_swap_sas_atl_cle_sas_gets_best():
    """In SAS/ATL/CLE swap, SAS gets the best (lowest) slot among the three."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)

    sas_slot = _CANONICAL_ORDER.index("sas") + 1  # 15
    atl_slot = _CANONICAL_ORDER.index("atl") + 1  # 19
    cle_slot = _CANONICAL_ORDER.index("cle") + 1  # 21

    best_slot = min(sas_slot, atl_slot, cle_slot)  # 15
    assignment = next(a for a in result if a.slot == best_slot)
    assert assignment.current_team == "sas"


def test_swap_sas_atl_cle_cle_gets_worst():
    """In SAS/ATL/CLE swap, CLE ends up with the worst (highest) slot."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)

    sas_slot = _CANONICAL_ORDER.index("sas") + 1  # 15
    atl_slot = _CANONICAL_ORDER.index("atl") + 1  # 19
    cle_slot = _CANONICAL_ORDER.index("cle") + 1  # 21

    worst_slot = max(sas_slot, atl_slot, cle_slot)  # 21
    assignment = next(a for a in result if a.slot == worst_slot)
    assert assignment.current_team == "cle"


def test_swap_uta_det_min_uta_gets_best():
    """In UTA/DET/MIN swap, UTA gets the best slot."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)

    uta_slot = _CANONICAL_ORDER.index("uta") + 1  # 5
    det_slot = _CANONICAL_ORDER.index("det") + 1  # 23
    min_slot = _CANONICAL_ORDER.index("min") + 1  # 25

    best_slot = min(uta_slot, det_slot, min_slot)  # 5
    assignment = next(a for a in result if a.slot == best_slot)
    # UTA is already at best slot AND is top-8 protected (stays with UTA), so
    # the swap still resolves UTA at slot 5.
    assert assignment.current_team == "uta"


# ---------------------------------------------------------------------------
# Best-of groups
# ---------------------------------------------------------------------------


def test_best_of_hawks_superfirst_atl_gets_lower_slot():
    """ATL receives the better (lower-slot) pick between NOP and MIL."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)

    nop_slot = _CANONICAL_ORDER.index("nop") + 1  # 7
    mil_slot = _CANONICAL_ORDER.index("mil") + 1  # 10

    best_slot = min(nop_slot, mil_slot)  # 7
    assignment = next(a for a in result if a.slot == best_slot)
    assert assignment.current_team == "atl"


def test_best_of_hawks_superfirst_mil_gets_worse_pick():
    """MIL receives the worse (higher-slot) pick between NOP and MIL."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=1)

    nop_slot = _CANONICAL_ORDER.index("nop") + 1  # 7
    mil_slot = _CANONICAL_ORDER.index("mil") + 1  # 10

    worst_slot = max(nop_slot, mil_slot)  # 10
    assignment = next(a for a in result if a.slot == worst_slot)
    assert assignment.current_team == "mil"


# ---------------------------------------------------------------------------
# Round 2 trades
# ---------------------------------------------------------------------------


def test_r2_simple_transfer_ind_to_mem():
    """IND's R2 pick goes to MEM."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)
    ind_slot = _CANONICAL_ORDER.index("ind") + 1
    assignment = next(a for a in result if a.slot == ind_slot)
    assert assignment.current_team == "mem"


def test_r2_simple_transfer_chi_to_hou():
    """CHI's R2 pick goes to HOU."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)
    chi_slot = _CANONICAL_ORDER.index("chi") + 1
    assignment = next(a for a in result if a.slot == chi_slot)
    assert assignment.current_team == "hou"


def test_r2_simple_transfer_lal_to_gsw():
    """LAL's R2 pick goes to GSW."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)
    lal_slot = _CANONICAL_ORDER.index("lal") + 1
    assignment = next(a for a in result if a.slot == lal_slot)
    assert assignment.current_team == "gsw"


def test_r2_protected_was_to_nyk_when_r1_was_protected():
    """WAS R2 pick goes to NYK when WAS R1 pick is top-8 protected (slot ≤ 8)."""
    # In canonical order, WAS is at slot 2 (top-8 protected → stays with WAS).
    # The r1_protected rule: R2 conveys to NYK if R1 was protected (slot ≤ 8).
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)
    was_slot = _CANONICAL_ORDER.index("was") + 1  # 2
    assignment = next(a for a in result if a.slot == was_slot)
    assert assignment.current_team == "nyk"


def test_r2_protected_was_stays_when_r1_not_protected():
    """WAS R2 pick stays with WAS when WAS R1 slot > 8 (pick conveyed to NYK in R1)."""
    order = list(_CANONICAL_ORDER)
    order.remove("was")
    order.insert(8, "was")  # slot 9 — outside top-8, R1 pick conveys to NYK
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=2)
    was_slot = order.index("was") + 1  # 9
    assignment = next(a for a in result if a.slot == was_slot)
    assert assignment.current_team == "was"


def test_r2_protected_uta_to_sas_when_slot_5_or_more():
    """UTA R2 pick at slot 5 conveys to SAS (slot 5 > threshold 4)."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)
    uta_slot = _CANONICAL_ORDER.index("uta") + 1  # 5
    assignment = next(a for a in result if a.slot == uta_slot)
    assert assignment.current_team == "sas"


def test_r2_protected_uta_stays_when_slot_4_or_less():
    """UTA R2 pick at slot 4 stays (r2_bottom protection: slot ≤ 4)."""
    order = list(_CANONICAL_ORDER)
    order.remove("uta")
    order.insert(3, "uta")  # slot 4
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(order, round_num=2)
    uta_slot = order.index("uta") + 1
    assert uta_slot == 4
    assignment = next(a for a in result if a.slot == uta_slot)
    assert assignment.current_team == "uta"


def test_r2_best_of_bos_gets_best_of_det_mil_orl():
    """BOS gets the best (lowest-slot) pick among DET, MIL, ORL in R2."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)

    det_slot = _CANONICAL_ORDER.index("det") + 1  # 23
    mil_slot = _CANONICAL_ORDER.index("mil") + 1  # 10
    orl_slot = _CANONICAL_ORDER.index("orl") + 1  # 18

    best_slot = min(det_slot, mil_slot, orl_slot)  # 10 (mil)
    assignment = next(a for a in result if a.slot == best_slot)
    assert assignment.current_team == "bos"


def test_r2_best_of_mia_gets_best_of_den_gsw():
    """MIA gets the better (lower-slot) of DEN and GSW R2 picks."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    result = resolver.resolve(_CANONICAL_ORDER, round_num=2)

    den_slot = _CANONICAL_ORDER.index("den") + 1  # 24
    gsw_slot = _CANONICAL_ORDER.index("gsw") + 1  # 12

    best_slot = min(den_slot, gsw_slot)  # 12 (gsw)
    assignment = next(a for a in result if a.slot == best_slot)
    assert assignment.current_team == "mia"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_resolve_is_deterministic():
    """Calling resolve() twice with the same input produces identical results."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    r1 = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    r2 = resolver.resolve(_CANONICAL_ORDER, round_num=1)
    assert [(a.slot, a.current_team, a.original_team) for a in r1] == \
           [(a.slot, a.current_team, a.original_team) for a in r2]


def test_resolve_all_is_deterministic():
    """resolve_all() is deterministic across calls."""
    resolver = TradeResolver(_TRADE_CONFIG_PATH)
    r1 = resolver.resolve_all(_CANONICAL_ORDER)
    r2 = resolver.resolve_all(_CANONICAL_ORDER)
    for pick_num in range(1, 61):
        assert r1[pick_num].current_team == r2[pick_num].current_team


# ---------------------------------------------------------------------------
# Custom minimal config (no external file dependency)
# ---------------------------------------------------------------------------


def test_minimal_simple_transfer(tmp_path):
    """A minimal config with one simple transfer correctly reassigns a pick."""
    config = {
        "first_round": {
            "simple_transfers": [
                {"id": "a-to-b", "from_team": "aaa", "to_team": "bbb", "notes": "test"}
            ],
            "protected_transfers": [],
            "range_only_transfers": [],
            "swap_groups": [],
            "best_of_groups": [],
        },
        "second_round": {
            "simple_transfers": [],
            "protected_transfers": [],
            "range_only_transfers": [],
            "swap_groups": [],
            "best_of_groups": [],
        },
    }
    cfg_path = tmp_path / "trades.json"
    cfg_path.write_text(json.dumps(config))

    order = ["aaa"] + [f"t{i:02d}" for i in range(29)]
    resolver = TradeResolver(cfg_path)
    result = resolver.resolve(order, round_num=1)

    assert result[0].slot == 1
    assert result[0].current_team == "bbb"
    assert result[0].original_team == "aaa"
    assert "aaa" in result[0].traded_from


def test_minimal_no_trades_unchanged(tmp_path):
    """With no trade rules, every slot keeps its original team."""
    config = {
        "first_round": {
            "simple_transfers": [],
            "protected_transfers": [],
            "range_only_transfers": [],
            "swap_groups": [],
            "best_of_groups": [],
        },
        "second_round": {
            "simple_transfers": [],
            "protected_transfers": [],
            "range_only_transfers": [],
            "swap_groups": [],
            "best_of_groups": [],
        },
    }
    cfg_path = tmp_path / "trades.json"
    cfg_path.write_text(json.dumps(config))

    order = [f"t{i:02d}" for i in range(30)]
    resolver = TradeResolver(cfg_path)
    result = resolver.resolve(order, round_num=1)

    for i, a in enumerate(result):
        assert a.current_team == order[i]
        assert a.traded_from == []
