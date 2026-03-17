"""
Predictions API router for the NBA Mock Draft 2026 application.

Endpoints:
    POST /api/predictions/run  — simulate all 60 picks
    GET  /api/predictions/status — last run metadata
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

predictions_router = APIRouter(prefix="/api/predictions", tags=["predictions"])

# In-process state for the last simulation run (resets on server restart)
_last_run: dict = {
    "last_run": None,
    "picks_assigned": 0,
    "players_in_pool": 0,
    "duration_ms": 0,
}


class RunResponse(BaseModel):
    """
    Response model for POST /api/predictions/run.

    Attributes:
        picks_assigned (int): Number of picks that received a player_id.
        players_created (int): Number of player records written to players.json.
        duration_ms (int): Wall-clock time of the full operation in milliseconds.
        errors (list[str]): Any non-fatal errors encountered.
    """

    picks_assigned: int
    players_created: int
    duration_ms: int
    errors: list[str]


class StatusResponse(BaseModel):
    """
    Response model for GET /api/predictions/status.

    Attributes:
        last_run (Optional[str]): ISO timestamp of the last run, or None.
        picks_assigned (int): Picks assigned in the last run.
        players_in_pool (int): Player pool size in the last run.
    """

    last_run: Optional[str]
    picks_assigned: int
    players_in_pool: int


@predictions_router.post("/run", response_model=RunResponse)
async def run_predictions() -> RunResponse:
    """
    Run the full prediction pipeline: build pool → simulate → write results.

    Steps:
    1. Build player pool from synthetic 2026 prospect data.
    2. Load team needs from config.
    3. Run sequential simulation across all 60 picks.
    4. Write data/players.json and update data/picks.json player_ids.
    5. Clear data_loader LRU cache so API immediately serves new data.

    Returns:
        RunResponse: Summary of the operation including counts and timing.

    Raises:
        HTTPException 500: If the simulation itself fails.
    """
    start_ts = time.perf_counter()
    errors: list[str] = []

    # Invalidate position_value cache so any config changes are picked up
    from app.analytics.position_value import invalidate_cache as _invalidate_pv
    _invalidate_pv()

    # --- Phase 1: build player pool ---
    try:
        from app.analytics.player_pool import build_player_pool

        pool = build_player_pool()
        players_in_pool = len(pool)
    except Exception as exc:
        logger.error("Failed to build player pool: %s", exc)
        raise HTTPException(status_code=500, detail=f"Player pool build failed: {exc}")

    # --- Phase 2: simulate + write ---
    try:
        from app.analytics.simulator import simulate_and_write

        picks_assigned, players_created = simulate_and_write(player_pool=pool)
    except Exception as exc:
        logger.error("Simulation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Simulation failed: {exc}")

    # --- Phase 3: clear data_loader cache ---
    try:
        from app import data_loader

        data_loader.clear_cache()
    except Exception as exc:
        logger.warning("Cache clear failed (non-fatal): %s", exc)

    duration_ms = int((time.perf_counter() - start_ts) * 1000)

    _last_run.update(
        {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "picks_assigned": picks_assigned,
            "players_in_pool": players_in_pool,
            "duration_ms": duration_ms,
        }
    )

    logger.info(
        "Prediction run complete: %d picks assigned, %d players, %dms",
        picks_assigned,
        players_created,
        duration_ms,
    )

    return RunResponse(
        picks_assigned=picks_assigned,
        players_created=players_created,
        duration_ms=duration_ms,
        errors=errors,
    )


@predictions_router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """
    Return metadata about the most recent prediction run.

    Returns:
        StatusResponse: Last run timestamp, picks assigned, and pool size.
    """
    return StatusResponse(
        last_run=_last_run["last_run"],
        picks_assigned=_last_run["picks_assigned"],
        players_in_pool=_last_run["players_in_pool"],
    )
