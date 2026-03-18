"""
Unit tests for the NBA Mock Draft API routes.
"""

import pytest
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def test_index_returns_html():
    """GET / returns 200 with HTML content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "NBA Mock Draft" in response.text


def test_get_all_picks():
    """GET /api/picks returns a list of 60 picks."""
    response = client.get("/api/picks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 60


def test_get_round_1_picks():
    """GET /api/picks?round=1 returns exactly 30 picks."""
    response = client.get("/api/picks?round=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 30
    for item in data:
        assert item["pick"]["round"] == 1


def test_get_round_2_picks():
    """GET /api/picks?round=2 returns exactly 30 picks."""
    response = client.get("/api/picks?round=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 30
    for item in data:
        assert item["pick"]["round"] == 2


def test_get_pick_by_number():
    """GET /api/picks/1 returns pick #1 with a valid team."""
    response = client.get("/api/picks/1")
    assert response.status_code == 200
    data = response.json()
    assert data["pick"]["pick_number"] == 1
    assert data["team"]["abbreviation"]  # non-empty team abbreviation


def test_get_pick_not_found():
    """GET /api/picks/999 returns 404."""
    response = client.get("/api/picks/999")
    assert response.status_code == 404


def test_get_all_teams():
    """GET /api/teams returns all 30 NBA teams."""
    response = client.get("/api/teams")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 30


def test_get_team_by_abbreviation():
    """GET /api/teams/gsw returns the Golden State Warriors."""
    response = client.get("/api/teams/gsw")
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == "Warriors"
    assert data["abbreviation"] == "gsw"


def test_get_team_case_insensitive():
    """GET /api/teams/LAL returns the Lakers (case insensitive)."""
    response = client.get("/api/teams/LAL")
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == "Lakers"


def test_get_team_not_found():
    """GET /api/teams/xyz returns 404."""
    response = client.get("/api/teams/xyz")
    assert response.status_code == 404


def test_clear_cache():
    """POST /api/cache/clear returns 200 with confirmation message."""
    response = client.post("/api/cache/clear")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_round_filter_invalid():
    """GET /api/picks?round=3 returns 422 (no round 3 in NBA)."""
    response = client.get("/api/picks?round=3")
    assert response.status_code == 422


def test_picks_first_overall():
    """Pick #1 is pick-in-round 1 with a valid team assigned."""
    response = client.get("/api/picks/1")
    assert response.status_code == 200
    data = response.json()
    assert data["team"]["abbreviation"]  # non-empty team abbreviation
    assert data["pick"]["pick_in_round"] == 1


def test_picks_last_pick():
    """Pick #60 is the final pick (Washington via OKC, R2P30)."""
    response = client.get("/api/picks/60")
    assert response.status_code == 200
    data = response.json()
    assert data["pick"]["round"] == 2
    assert data["pick"]["pick_in_round"] == 30
