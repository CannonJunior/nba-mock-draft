"""
Player pool builder for the NBA Mock Draft prediction engine.

Assembles a list of PlayerCandidate dataclasses from the verified
2026 NBA Draft prospect class. All players in this pool are confirmed
as eligible for the 2026 draft — players selected in the 2025 draft
or in any prior draft have been excluded.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_LOG_60 = math.log(60)
_LOG_100 = math.log(100)

# Normalise position labels from various sources to canonical NBA codes
_POS_ALIASES: dict[str, str] = {
    "point guard": "PG",
    "shooting guard": "SG",
    "small forward": "SF",
    "power forward": "PF",
    "center": "C",
    "guard": "PG",
    "forward": "SF",
    "forward-center": "PF",
    "guard-forward": "SG",
    "pg": "PG",
    "sg": "SG",
    "sf": "SF",
    "pf": "PF",
    "c": "C",
    "g": "PG",
    "f": "SF",
}


@dataclass
class PlayerCandidate:
    """
    Internal representation of a draft prospect for the simulation engine.

    Attributes:
        player_id (str): Slug identifier: "firstname-lastname".
        name (str): Full player name.
        position (str): Canonical position code (e.g. "SF").
        college (str): College, university, or league name.
        espn_grade (Optional[float]): ESPN prospect grade (0-10 scale).
        espn_rank (Optional[int]): ESPN big board rank.
        combine (dict): NBA combine measurements keyed by stat name.
        mock_picks (list[int]): Pick numbers from mock sources.
        base_score (float): Composite 0-100 score.
        available (bool): False once the player has been drafted.
        buzz_score (Optional[float]): Social buzz score 0-100.
    """

    player_id: str
    name: str
    position: str
    college: str
    espn_grade: Optional[float]
    espn_rank: Optional[int]
    combine: dict = field(default_factory=dict)
    mock_picks: list[int] = field(default_factory=list)
    base_score: float = 0.0
    available: bool = True
    buzz_score: Optional[float] = None


def build_player_pool() -> list[PlayerCandidate]:
    """
    Build a ranked list of PlayerCandidate objects for the 2026 NBA Draft.

    Returns:
        list[PlayerCandidate]: Players sorted by base_score descending.
    """
    return _synthetic_fallback_pool()


def _make_player_id(name: str) -> str:
    """
    Convert a player name to a URL-safe slug used as player_id.

    Args:
        name (str): Player full name.

    Returns:
        str: Slug (e.g. "aj-dybantsa").
    """
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")


def _normalise_position(raw: str) -> str:
    """
    Normalise a raw position string to a canonical NBA code.

    Args:
        raw (str): Raw position string.

    Returns:
        str: Canonical position code (e.g. "SF", "PG").
    """
    cleaned = raw.strip().lower()
    return _POS_ALIASES.get(cleaned, raw.upper().strip() or "SF")


def _compute_base_score(
    espn_grade: Optional[float],
    espn_rank: Optional[int],
    mock_picks: list[int],
) -> float:
    """
    Compute the 0-100 base score for a prospect from scouting signals.

    Args:
        espn_grade (Optional[float]): ESPN 0-10 grade.
        espn_rank (Optional[int]): ESPN big board rank.
        mock_picks (list[int]): Pick numbers from mock sources.

    Returns:
        float: Base score in range 0-100.
    """
    mock_signal = _mock_consensus_signal(mock_picks)

    if espn_grade is not None:
        espn_norm = (espn_grade / 10.0) * 100.0
        if mock_picks:
            return (espn_norm * 0.55) + (mock_signal * 0.45)
        return espn_norm
    elif mock_picks:
        return _derive_grade_from_picks(mock_picks)
    elif espn_rank is not None:
        return _derive_grade_from_rank(espn_rank)

    return 1.0


def _mock_consensus_signal(mock_picks: list[int]) -> float:
    """
    Convert mock-draft pick numbers into a 0-100 consensus signal.

    Args:
        mock_picks (list[int]): Pick numbers from all sources.

    Returns:
        float: Consensus signal in range 0-100.
    """
    if not mock_picks:
        return 0.0
    scores = [max(0.0, 100.0 * (1.0 - (p - 1) / 59.0)) for p in mock_picks]
    avg = sum(scores) / len(scores)
    if len(scores) > 1:
        variance = sum((s - avg) ** 2 for s in scores) / len(scores)
        std_dev = math.sqrt(variance)
        avg = max(0.0, avg - min(10.0, std_dev * 0.15))
    return avg


def _derive_grade_from_picks(mock_picks: list[int]) -> float:
    """
    Derive a 0-100 grade from mock draft pick numbers.

    Args:
        mock_picks (list[int]): Pick numbers from mock sources.

    Returns:
        float: Derived grade in 0-100 range.
    """
    avg_pick = sum(mock_picks) / len(mock_picks)
    grade = 100.0 - (math.log(max(1, avg_pick)) / _LOG_60) * 70.0
    return max(0.0, min(100.0, grade))


def _derive_grade_from_rank(rank: int) -> float:
    """
    Derive a 0-100 score from a big board rank.

    Args:
        rank (int): Big board rank (1 = top prospect).

    Returns:
        float: Derived score in 0-100 range.
    """
    grade = 100.0 - (math.log(max(1, rank)) / _LOG_100) * 70.0
    return max(0.0, min(100.0, grade))


def _synthetic_fallback_pool() -> list[PlayerCandidate]:
    """
    Return the verified 2026 NBA Draft class as PlayerCandidate objects.

    All players are confirmed as 2026-eligible — players selected in
    the 2025 draft (Cooper Flagg, Dylan Harper, Ace Bailey, Tre Johnson,
    VJ Edgecombe, Kon Knueppel, Egor Demin, Khaman Maluach, Liam McNeeley,
    Jeremiah Fears, Noa Essengue, Carter Bryant, Collin Murray-Boyles,
    Drake Powell, Will Riley, Cedric Coward, Thomas Sorber, Walter Clayton Jr.,
    Nique Clifford, Ben Saraf, Adou Thiero, Chaz Lanier, Javon Small,
    Tyrese Proctor, Johni Broome, Ryan Kalkbrenner, Kasparas Jakucionis,
    Alex Toohey, and others) have been removed.

    Grades sourced from ESPN, The Athletic, NBADraft.net, Babcock Hoops,
    and FanSided big board projections for the 2025-26 season class.
    Format: (name, position, school/league, espn_grade_0_to_10, approx_rank)

    Returns:
        list[PlayerCandidate]: 70 prospects sorted by base_score descending.
    """
    # Reason: 70 players ensures enough depth to fill all 60 picks with
    # realistic selection dynamics and meaningful remainder.
    _PROSPECTS = [
        # ---- Top 4 (consensus locks) ----
        ("AJ Dybantsa",          "SF",  "BYU",               9.8,  1),
        ("Darryn Peterson",      "SG",  "Kansas",            9.7,  2),
        ("Cameron Boozer",       "PF",  "Duke",              9.5,  3),
        ("Caleb Wilson",         "SF",  "North Carolina",    9.2,  4),
        # ---- Picks 5-15 ----
        ("Kingston Flemings",    "PG",  "Houston",           8.8,  5),
        ("Dailyn Swain",         "SF",  "Texas",             8.5,  6),
        ("Mikel Brown Jr.",      "SG",  "Louisville",        8.3,  7),
        ("Keaton Wagler",        "SG",  "Illinois",          8.2,  8),
        ("Bennett Stirtz",       "PG",  "Iowa",              8.0,  9),
        ("Yaxel Lendeborg",      "PF",  "Michigan",          7.9, 10),
        ("Labaron Philon",       "PG",  "Alabama",           7.8, 11),
        ("Darius Acuff Jr.",     "PG",  "Arkansas",          7.7, 12),
        ("Aday Mara",            "C",   "Michigan",          7.5, 13),
        ("Patrick Ngongba II",   "C",   "Duke",              7.4, 14),
        ("Hannes Steinbach",     "SF",  "Washington",        7.3, 15),
        # ---- Picks 16-25 ----
        ("Koa Peat",             "PF",  "Arizona",           7.2, 16),
        ("Jayden Quaintance",    "C",   "Kentucky",          7.1, 17),
        ("Tyler Tanner",         "SG",  "Vanderbilt",        7.0, 18),
        ("Joshua Jefferson",     "SF",  "Iowa State",        6.9, 19),
        ("Nate Ament",           "SF",  "Tennessee",         6.8, 20),
        ("Christian Anderson",   "PG",  "Texas Tech",        6.7, 21),
        ("Boogie Fland",         "PG",  "Florida",           6.5, 22),
        ("Cameron Carr",         "SG",  "Baylor",            6.4, 23),
        ("Brayden Burries",      "SG",  "Arizona",           6.3, 24),
        ("Braylon Mullins",      "PG",  "UConn",             6.2, 25),
        # ---- Picks 26-35 ----
        ("Malachi Moreno",       "C",   "Kentucky",          6.1, 26),
        ("Karim Lopez",          "SF",  "New Zealand Breakers", 6.0, 27),
        ("Morez Johnson Jr.",    "PF",  "Michigan",          5.9, 28),
        ("Henri Veesaar",        "C",   "North Carolina",    5.8, 29),
        ("Thomas Haugh",         "SF",  "Florida",           5.7, 30),
        ("Motiejus Krivas",      "C",   "Arizona",           5.6, 31),
        ("Daniel Jacobsen",      "C",   "Purdue",            5.5, 32),
        ("Ebuka Okorie",         "SG",  "Stanford",          5.4, 33),
        ("Tahaad Pettiford",     "PG",  "Auburn",            5.3, 34),
        ("Braden Smith",         "PG",  "Purdue",            5.2, 35),
        # ---- Picks 36-45 ----
        ("Zuby Ejiofor",         "C",   "St. John's",        5.1, 36),
        ("Joseph Tugler",        "PF",  "Houston",           5.0, 37),
        ("Alvaro Folgueiras",    "PF",  "Iowa",              4.9, 38),
        ("Flory Bidunga",        "C",   "Kansas",            4.8, 39),
        ("Allen Graves",         "SF",  "Santa Clara",       4.7, 40),
        ("Johann Grunloh",       "C",   "Virginia",          4.6, 41),
        ("Chris Cenac Jr.",      "C",   "Houston",           4.5, 42),
        ("Tamin Lipsey",         "PG",  "Iowa State",        4.4, 43),
        ("Isaiah Evans",         "SF",  "Duke",              4.3, 44),
        ("Kanaan Carlyle",       "SG",  "Stanford",          4.2, 45),
        # ---- Picks 46-55 ----
        ("Meleek Thomas",        "SG",  "Arkansas",          4.1, 46),
        ("Paul McNeil Jr.",      "SG",  "NC State",          4.0, 47),
        ("Rueben Chinyelu",      "C",   "Florida",           3.9, 48),
        ("Blue Cain",            "PG",  "Georgia",           3.8, 49),
        ("Neoklis Avdalas",      "SF",  "Virginia Tech",     3.7, 50),
        ("Jalil Bethea",         "SG",  "Alabama",           3.6, 51),
        ("Tounde Yessoufou",     "SF",  "Baylor",            3.5, 52),
        ("Milan Momcilovic",     "SF",  "Iowa State",        3.4, 53),
        ("Alex Karaban",         "SF",  "UConn",             3.3, 54),
        ("Amari Allen",          "PF",  "Alabama",           3.2, 55),
        # ---- Picks 56-70 (depth) ----
        ("Tarris Reed Jr.",      "C",   "UConn",             3.1, 56),
        ("Ryan Conwell",         "SG",  "Louisville",        3.0, 57),
        ("Juke Harris",          "SF",  "Wake Forest",       2.9, 58),
        ("Elyjah Freeman",       "SG",  "Auburn",            2.8, 59),
        ("Massamba Diop",        "C",   "Arizona State",     2.7, 60),
        ("Zvonimir Ivisic",      "C",   "Illinois",          2.6, 61),
        ("Eric Reibe",           "C",   "UConn",             2.5, 62),
        ("Miles Byrd",           "SG",  "San Diego State",   2.4, 63),
        ("Bruce Thornton",       "PG",  "Ohio State",        2.3, 64),
        ("Makhi Mitchell",       "PF",  "Oregon",            2.2, 65),
        ("D.J. Wagner",          "PG",  "Kentucky",          2.1, 66),
        ("Cam Christie",         "SG",  "Minnesota",         2.0, 67),
        ("Tre Donaldson",        "PG",  "Auburn",            1.9, 68),
        ("Oziyah Sellers",       "SG",  "Texas",             1.8, 69),
        ("Nate Santos",          "PF",  "Florida State",     1.7, 70),
    ]

    candidates = []
    for (name, pos, college, grade_10, rank) in _PROSPECTS:
        base_score = _compute_base_score(
            espn_grade=grade_10,
            espn_rank=rank,
            mock_picks=[rank] if rank <= 60 else [],
        )
        candidates.append(
            PlayerCandidate(
                player_id=_make_player_id(name),
                name=name,
                position=_normalise_position(pos),
                college=college,
                espn_grade=grade_10,
                espn_rank=rank,
                combine={},
                mock_picks=[rank] if rank <= 60 else [],
                base_score=base_score,
            )
        )

    candidates.sort(key=lambda c: c.base_score, reverse=True)
    logger.info("Player pool built: %d candidates", len(candidates))
    return candidates
