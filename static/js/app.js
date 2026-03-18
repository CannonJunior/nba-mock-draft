/**
 * NBA Mock Draft 2026 — Frontend Application
 *
 * Handles:
 *  - Round tab switching (with All Rounds support)
 *  - Position filtering
 *  - Pick row expand/collapse (detail panel)
 *  - Stats tab switching per pick
 *  - Injury history toggle
 *  - Image fallback for broken logos
 *  - "NEW" badge system for recently added media
 */

"use strict";

// ============================================================
// Round Tabs
// ============================================================

// Cached NodeLists — queried once on DOMContentLoaded.
let _roundTabs = null;
let _roundPanels = null;

// Currently active positions for filtering. Empty set = show all positions.
const _activePositions = new Set();

/**
 * Activate a specific round tab and show its panel.
 * Pass round=0 to show all rounds simultaneously.
 * @param {number} round - Round number (1 or 2), or 0 for all rounds.
 */
function activateRound(round) {
  const showAll = round === 0;

  // Update numbered tab styling
  (_roundTabs || document.querySelectorAll(".round-tab")).forEach((tab) => {
    tab.classList.toggle("active", parseInt(tab.dataset.round) === round);
  });

  // Update "All" button styling
  const allTab = document.getElementById("all-rounds-tab");
  if (allTab) allTab.classList.toggle("active", showAll);

  // Show/hide panels — all visible when round=0
  (_roundPanels || document.querySelectorAll(".round-panel")).forEach((panel) => {
    panel.classList.toggle(
      "active",
      showAll || parseInt(panel.dataset.round) === round
    );
  });

  // Persist selection; "0" restores All Rounds on reload
  sessionStorage.setItem("activeRound", round);

  // Re-apply position filter so rows in newly visible panels are correctly shown/hidden
  applyPositionFilter();
}

// ============================================================
// Position Filters
// ============================================================

// Canonical NBA position order for the filter bar.
const _POSITION_ORDER = ["PG", "SG", "SF", "PF", "C"];

/**
 * Build position filter buttons from the positions actually present in the pick data.
 * Inserts buttons into #position-filters in canonical position order.
 */
function buildPositionFilters() {
  const container = document.getElementById("position-filters");
  if (!container) return;

  // Collect unique non-empty positions from rendered pick rows
  const present = new Set();
  document.querySelectorAll(".pick-row[data-position]").forEach((row) => {
    const pos = row.dataset.position;
    if (pos) present.add(pos);
  });

  if (present.size === 0) return; // No predictions yet — hide the filter bar entirely

  // Render buttons in canonical order; append any unknown positions at the end
  const ordered = _POSITION_ORDER.filter((p) => present.has(p));
  _POSITION_ORDER.forEach((p) => present.delete(p));
  present.forEach((p) => ordered.push(p)); // any remaining unknown positions

  ordered.forEach((pos) => {
    const btn = document.createElement("button");
    btn.className = "pos-filter-btn";
    btn.dataset.position = pos;
    btn.textContent = pos;
    btn.title = `Filter picks: ${pos}`;
    btn.addEventListener("click", (e) => {
      togglePositionFilter(pos);
      e.stopPropagation();
    });
    container.appendChild(btn);
  });
}

/**
 * Toggle a position filter on or off. Multiple positions can be active at once;
 * if none are active the filter shows all picks.
 * @param {string} pos - Position code to toggle (e.g. "PG", "SF").
 */
function togglePositionFilter(pos) {
  if (_activePositions.has(pos)) {
    _activePositions.delete(pos);
  } else {
    _activePositions.add(pos);
  }

  // Sync button active states
  document.querySelectorAll(".pos-filter-btn").forEach((btn) => {
    btn.classList.toggle("active", _activePositions.has(btn.dataset.position));
  });

  applyPositionFilter();
}

/**
 * Show or hide pick rows (and their expanded detail rows) based on the active
 * position filters. If no filters are active all rows are shown.
 *
 * Reason: detail rows use a CSS class (.visible) for display, but inline
 * style.display overrides class-based rules. We always reset the inline style
 * to "" for visible rows so CSS retains control, and only set it to "none"
 * for filtered-out rows to hide them regardless of the .visible class.
 */
function applyPositionFilter() {
  const filterActive = _activePositions.size > 0;

  document.querySelectorAll(".pick-row").forEach((row) => {
    const pos = row.dataset.position || "";
    const visible = !filterActive || _activePositions.has(pos);

    row.style.display = visible ? "" : "none";

    // Always reset detail row inline style so .visible CSS class controls display.
    const pickNum = row.dataset.pickNumber;
    const detailRow = document.getElementById(`detail-${pickNum}`);
    if (detailRow) {
      detailRow.style.display = visible ? "" : "none";
    }
  });
}

// ============================================================
// "NEW" Badge System
// ============================================================

/**
 * Mark media items and pick rows as "new" if they were fetched after the
 * last time the user clicked "Run Predictions".
 */
function markNewItems() {
  const lastRefresh = localStorage.getItem("nbaMockLastRefresh");
  if (!lastRefresh) return;

  const seenPicks = new Set(
    JSON.parse(localStorage.getItem("nbaMockSeenPicks") || "[]")
  );

  document.querySelectorAll("[data-fetched-at]").forEach((el) => {
    const fetchedAt = el.dataset.fetchedAt;
    if (!fetchedAt || fetchedAt <= lastRefresh) return;

    el.classList.add("is-new");
    const itemBadge = el.querySelector(".new-item-badge");
    if (itemBadge) itemBadge.classList.add("visible");

    const detailRow = el.closest("tr.detail-row");
    if (!detailRow) return;
    const pickNum = detailRow.id.replace("detail-", "");
    if (seenPicks.has(pickNum)) return;

    const rowBadge = document.getElementById(`new-badge-${pickNum}`);
    if (rowBadge) rowBadge.classList.add("visible");
  });
}

/**
 * Clear NEW badges for a specific pick after the user expands its row.
 * @param {string|number} pickNum - The pick number.
 */
function clearPickNewBadge(pickNum) {
  const pn = String(pickNum);

  const rowBadge = document.getElementById(`new-badge-${pn}`);
  if (rowBadge) rowBadge.classList.remove("visible");

  const detailRow = document.getElementById(`detail-${pn}`);
  if (detailRow) {
    detailRow.querySelectorAll("[data-fetched-at]").forEach((el) => {
      el.classList.remove("is-new");
      const itemBadge = el.querySelector(".new-item-badge");
      if (itemBadge) itemBadge.classList.remove("visible");
    });
  }

  const seen = new Set(
    JSON.parse(localStorage.getItem("nbaMockSeenPicks") || "[]")
  );
  seen.add(pn);
  localStorage.setItem("nbaMockSeenPicks", JSON.stringify([...seen]));
}

// ============================================================
// Pick Row Expand / Collapse
// ============================================================

/**
 * Toggle the detail panel for a given pick row.
 * @param {HTMLElement} row - The pick-row <tr> element that was clicked.
 */
function togglePickDetail(row) {
  const pickNum = row.dataset.pickNumber;
  const detailRow = document.getElementById(`detail-${pickNum}`);
  if (!detailRow) return;

  const isExpanded = row.classList.contains("expanded");

  if (isExpanded) {
    collapsePickRow(row, detailRow);
  } else {
    expandPickRow(row, detailRow, pickNum);
  }
}

/**
 * Expand a pick row to show its detail panel and clear its NEW badge.
 * @param {HTMLElement} row - The pick-row element.
 * @param {HTMLElement} detailRow - The corresponding detail-row element.
 * @param {string} pickNum - The pick number.
 */
function expandPickRow(row, detailRow, pickNum) {
  row.classList.add("expanded");
  detailRow.classList.add("visible");
  if (pickNum) clearPickNewBadge(pickNum);
}

/**
 * Collapse a pick row and hide its detail panel.
 * @param {HTMLElement} row - The pick-row element.
 * @param {HTMLElement} detailRow - The corresponding detail-row element.
 */
function collapsePickRow(row, detailRow) {
  row.classList.remove("expanded");
  detailRow.classList.remove("visible");
}

// ============================================================
// Stats Tabs (per pick)
// ============================================================

/**
 * Switch the active stats view tab within a pick's detail panel.
 * @param {HTMLElement} tabEl - The clicked stats-tab element.
 * @param {string} pickNum - The pick number string.
 * @param {string} viewName - The stats view name to activate.
 */
function activateStatsTab(tabEl, pickNum, viewName) {
  const panel = tabEl.closest(".detail-panel");
  panel.querySelectorAll(".stats-tab").forEach((t) => t.classList.remove("active"));
  panel.querySelectorAll(".stats-view").forEach((v) => v.classList.remove("active"));

  tabEl.classList.add("active");
  const view = panel.querySelector(`.stats-view[data-view="${viewName}"]`);
  if (view) view.classList.add("active");
}

// ============================================================
// Injury History Toggle
// ============================================================

/**
 * Toggle visibility of injury list for a pick.
 * @param {HTMLElement} toggleEl - The toggle button element.
 */
function toggleInjuryList(toggleEl) {
  const list = toggleEl.nextElementSibling;
  if (!list) return;
  const isOpen = list.classList.contains("open");
  list.classList.toggle("open", !isOpen);
  toggleEl.querySelector(".toggle-arrow").textContent = isOpen ? "▸" : "▾";
}

// ============================================================
// Logo Image Fallback
// ============================================================

/**
 * Replace a broken logo image with a text abbreviation badge.
 * @param {HTMLImageElement} img - The broken img element.
 * @param {string} abbrev - Team abbreviation for fallback text.
 */
function onLogoError(img, abbrev) {
  img.onerror = null;
  img.style.display = "none";

  const badge = document.createElement("span");
  badge.textContent = abbrev.toUpperCase();
  badge.style.cssText =
    "display:inline-flex;align-items:center;justify-content:center;" +
    "width:48px;height:48px;border-radius:50%;background:#192028;" +
    "border:2px solid #2a3340;font-size:0.65rem;font-weight:700;" +
    "color:#8a9ab0;letter-spacing:0.04em;";
  img.parentNode.insertBefore(badge, img.nextSibling);
}

// ============================================================
// Height Formatting
// ============================================================

/**
 * Convert height in total inches to feet-inches display string.
 * @param {number|null} totalInches - Height in inches.
 * @returns {string} Formatted string (e.g. "6'4\"") or "—".
 */
function formatHeight(totalInches) {
  if (!totalInches) return "—";
  const feet = Math.floor(totalInches / 12);
  const inches = totalInches % 12;
  return `${feet}'${inches}"`;
}

// ============================================================
// Predictions
// ============================================================

/**
 * Simulate the rest of the 2025-26 NBA season, run the draft lottery,
 * and then run the player-selection draft simulation.
 * Shows a multi-stage progress label and reloads the page on success.
 */
async function simulateSeason() {
  const btn = document.getElementById("simulate-season-btn");
  const icon = document.getElementById("simulate-season-btn-icon");
  const label = document.getElementById("simulate-season-btn-label");
  const refreshBtn = document.getElementById("predictions-btn");

  if (!btn) return;

  const refreshTs = new Date().toISOString();

  btn.disabled = true;
  btn.classList.add("loading");
  if (refreshBtn) refreshBtn.disabled = true;
  if (icon) icon.textContent = "⏳";
  if (label) label.textContent = "Simulating season…";

  try {
    const res = await fetch("/api/predictions/simulate-season", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();

    if (icon) icon.textContent = "✓";
    const top4 = (data.lottery_order || []).slice(0, 4).join(", ").toUpperCase();
    if (label) label.textContent = `Done — Lottery: ${top4}`;

    localStorage.setItem("nbaMockLastRefresh", refreshTs);
    localStorage.removeItem("nbaMockSeenPicks");

    setTimeout(() => window.location.reload(), 1200);
  } catch (err) {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.classList.add("error");
    if (refreshBtn) refreshBtn.disabled = false;
    if (icon) icon.textContent = "✗";
    if (label) label.textContent = "Error — retry";
    console.error("Season simulation failed:", err);
    setTimeout(() => {
      btn.classList.remove("error");
      if (icon) icon.textContent = "🏀";
      if (label) label.textContent = "Simulate Season";
    }, 3000);
  }
}

/**
 * Call the predictions API, record refresh timestamp, and reload the page.
 */
async function runPredictions() {
  const btn = document.getElementById("predictions-btn");
  const icon = document.getElementById("predictions-btn-icon");
  const label = document.getElementById("predictions-btn-label");
  const simBtn = document.getElementById("simulate-season-btn");

  if (!btn) return;

  const refreshTs = new Date().toISOString();

  btn.disabled = true;
  btn.classList.add("loading");
  if (simBtn) simBtn.disabled = true;
  if (icon) icon.textContent = "⏳";
  if (label) label.textContent = "Running…";

  try {
    const res = await fetch("/api/predictions/run", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (icon) icon.textContent = "✓";
    if (label) label.textContent = `Done — ${data.picks_assigned} picks`;

    localStorage.setItem("nbaMockLastRefresh", refreshTs);
    localStorage.removeItem("nbaMockSeenPicks");

    setTimeout(() => window.location.reload(), 800);
  } catch (err) {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.classList.add("error");
    if (simBtn) simBtn.disabled = false;
    if (icon) icon.textContent = "✗";
    if (label) label.textContent = "Error — retry";
    console.error("Predictions run failed:", err);
    setTimeout(() => {
      btn.classList.remove("error");
      if (icon) icon.textContent = "⟳";
      if (label) label.textContent = "Refresh Predictions";
    }, 3000);
  }
}

// ============================================================
// DOM Initialisation
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  _roundTabs = document.querySelectorAll(".round-tab[data-round]");
  _roundPanels = document.querySelectorAll(".round-panel");

  // Restore last active round (0 = All Rounds) or default to round 1
  const savedRound = parseInt(sessionStorage.getItem("activeRound") || "1");
  activateRound(savedRound);

  // Wire numbered round tab clicks using cached list
  _roundTabs.forEach((tab) => {
    tab.addEventListener("click", () => activateRound(parseInt(tab.dataset.round)));
  });

  // Wire "All Rounds" button
  const allTab = document.getElementById("all-rounds-tab");
  if (allTab) allTab.addEventListener("click", () => activateRound(0));

  // Build and wire position filter buttons from pick data
  buildPositionFilters();

  // Wire pick row clicks via event delegation — one listener instead of one per row.
  // Reason: 60 individual addEventListener calls on .pick-row replaced with a
  // single delegated handler, reducing memory overhead and init time.
  document.addEventListener("click", (e) => {
    const row = e.target.closest(".pick-row");
    if (row && !e.target.closest(".stats-tab, .injury-toggle, a")) {
      togglePickDetail(row);
    }
  });

  // Event delegation for stats tab clicks
  document.addEventListener("click", (e) => {
    const statsTab = e.target.closest(".stats-tab");
    if (!statsTab) return;
    const panel = statsTab.closest(".detail-panel");
    const viewName = statsTab.dataset.view;
    if (panel && viewName) {
      activateStatsTab(statsTab, null, viewName);
      e.stopPropagation();
    }
  });

  // Event delegation for injury toggles
  document.addEventListener("click", (e) => {
    const toggle = e.target.closest(".injury-toggle");
    if (!toggle) return;
    toggleInjuryList(toggle);
    e.stopPropagation();
  });

  // Render height values
  document.querySelectorAll(".height-display").forEach((el) => {
    const inches = parseInt(el.dataset.inches);
    if (!isNaN(inches)) el.textContent = formatHeight(inches);
  });

  markNewItems();
});
