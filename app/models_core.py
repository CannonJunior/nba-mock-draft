"""
Pydantic data models for the NBA Mock Draft 2026 application.

All domain objects are validated via Pydantic v2 models.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Team(BaseModel):
    """
    Represents an NBA franchise.

    Attributes:
        abbreviation (str): ESPN CDN abbreviation (e.g. "gsw", "lal").
        name (str): Full team name (e.g. "Golden State Warriors").
        city (str): City or region (e.g. "San Francisco").
        nickname (str): Team nickname (e.g. "Warriors").
        primary_color (str): Hex color string for UI theming.
        secondary_color (str): Secondary hex color.
        logo_url (str): ESPN CDN logo image URL.
    """

    abbreviation: str
    name: str
    city: str
    nickname: str
    primary_color: str
    secondary_color: str
    logo_url: str


class InjuryRecord(BaseModel):
    """
    A single injury event for a player.

    Attributes:
        year (int): Season year the injury occurred.
        injury_type (str): Description of the injury (e.g. "ACL Tear").
        games_missed (Optional[int]): Number of games missed; None if unknown.
        details (Optional[str]): Additional context about the injury.
    """

    year: int
    injury_type: str
    games_missed: Optional[int] = None
    details: Optional[str] = None


class StatView(BaseModel):
    """
    A named collection of statistics for a specific view/category.

    Attributes:
        view_name (str): Display name for this stat view (e.g. "Season").
        season (str): Season label (e.g. "2025-26" or "Career").
        stats (dict[str, str | int | float]): Key-value stat pairs.
    """

    view_name: str
    season: str
    stats: dict[str, str | int | float] = Field(default_factory=dict)


class MediaLink(BaseModel):
    """
    A link to a media source about a player.

    Attributes:
        source_type (str): Category — "news", "twitter", "instagram",
            "mock_draft", or "video".
        title (str): Display title for the link.
        url (str): Full URL to the resource.
        source_name (str): Publication or account name.
        published_at (Optional[str]): ISO date string when available.
        thumbnail_url (Optional[str]): Optional preview image URL.
    """

    source_type: str
    title: str
    url: str
    source_name: str
    published_at: Optional[str] = None
    thumbnail_url: Optional[str] = None


class BiographicalInfo(BaseModel):
    """
    Physical and personal biographical data for an NBA draft prospect.

    Attributes:
        height_inches (Optional[int]): Height in total inches (without shoes).
        weight_lbs (Optional[int]): Weight in pounds.
        age (Optional[int]): Age at time of draft.
        hometown (Optional[str]): "City, State/Country" format.
        wingspan_inches (Optional[float]): Wingspan in inches.
        standing_reach_inches (Optional[float]): Standing reach in inches.
        lane_agility_seconds (Optional[float]): NBA combine lane agility time.
        sprint_seconds (Optional[float]): Three-quarter court sprint time.
        vertical_jump_inches (Optional[float]): Standing vertical leap in inches.
        max_vertical_inches (Optional[float]): Max vertical leap in inches.
    """

    height_inches: Optional[int] = None
    weight_lbs: Optional[int] = None
    age: Optional[int] = None
    hometown: Optional[str] = None
    wingspan_inches: Optional[float] = None
    standing_reach_inches: Optional[float] = None
    lane_agility_seconds: Optional[float] = None
    sprint_seconds: Optional[float] = None
    vertical_jump_inches: Optional[float] = None
    max_vertical_inches: Optional[float] = None


class Player(BaseModel):
    """
    A draft prospect with all associated scouting and media data.

    Attributes:
        player_id (str): Unique identifier.
        name (str): Full player name.
        position (str): Position code (e.g. "PG", "SF", "C").
        college (str): College, university, or league name.
        college_logo_url (Optional[str]): ESPN CDN college logo URL.
        bio (BiographicalInfo): Physical/personal data.
        injury_history (list[InjuryRecord]): All known injury records.
        stat_views (list[StatView]): Statistical data in multiple views.
        media_links (list[MediaLink]): External media references.
        grade (Optional[float]): Scouting grade (0-10 scale).
        notes (Optional[str]): Analyst notes on the prospect.
        grade_breakdown (Optional[dict]): Grade formula components.
    """

    player_id: str
    name: str
    position: str
    college: str
    college_logo_url: Optional[str] = None
    bio: BiographicalInfo = Field(default_factory=BiographicalInfo)
    injury_history: list[InjuryRecord] = Field(default_factory=list)
    stat_views: list[StatView] = Field(default_factory=list)
    media_links: list[MediaLink] = Field(default_factory=list)
    tweets: Optional[list] = None
    grade: Optional[float] = None
    notes: Optional[str] = None
    grade_breakdown: Optional[dict] = None


class Pick(BaseModel):
    """
    A single draft selection slot in the 2026 NBA Draft.

    Attributes:
        pick_number (int): Overall pick number (1-indexed).
        round (int): Round number (1 or 2).
        pick_in_round (int): Pick number within the round.
        current_team (str): Abbreviation of team currently holding the pick.
        traded_from (list[str]): Ordered list of prior team abbreviations
            representing the pick's trade chain (oldest first).
        trade_notes (Optional[str]): Human-readable trade context.
        is_lottery (bool): True if this is a lottery pick (top 14).
        player_id (Optional[str]): Linked player ID once assigned.
        team_needs_snapshot (Optional[dict]): Pre-pick team needs snapshot.
    """

    pick_number: int
    round: int
    pick_in_round: int
    current_team: str
    traded_from: list[str] = Field(default_factory=list)
    trade_notes: Optional[str] = None
    is_lottery: bool = False
    player_id: Optional[str] = None
    team_needs_snapshot: Optional[dict] = None


class EnrichedPick(BaseModel):
    """
    A pick enriched with full Team and Player objects for API responses.

    Attributes:
        pick (Pick): The raw pick data.
        team (Team): The current team holding this pick.
        traded_from_teams (list[Team]): Team objects for the trade chain.
        player (Optional[Player]): The assigned player, if any.
    """

    pick: Pick
    team: Team
    traded_from_teams: list[Team] = Field(default_factory=list)
    player: Optional[Player] = None
