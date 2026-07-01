#!/usr/bin/env bash
# =============================================================================
# build.sh — astroPharmReactor data pipeline
# =============================================================================
#
# PURPOSE
#   Two-step build that regenerates the website study summaries from raw data:
#
#   Step 1 — generate_study_summaries.py
#     Walks studies/study*/ (repo root) for CSV log files.
#     Normalises column names across all schema versions (SHT30-only → dual
#     BME688 + AS7341).  Filters bad/saturated values.  Computes per-variable
#     min/max/range/mean, bad-data windows, and downsampled time-series chart
#     data.  Writes one JS data file per study to docs/js/.
#
#   Step 2 — open docs/index.html in the system default browser.
#     The page loads the generated JS files and renders Plotly charts, a
#     session-timeline chart, a bad-data bar chart, and a sortable/downloadable
#     Tabulator stats table for each study — all at the top of the page.
#
# USAGE
#   From the repo root:
#     bash user_provided/makefile/build.sh
#
#   From this directory:
#     ./build.sh
#
# FIRST RUN — make executable:
#   chmod +x user_provided/makefile/build.sh
#
# OVERRIDE PYTHON INTERPRETER
#   PYTHON=python3.11 bash build.sh
#
# OUTPUT FILES
#   docs/js/study001_ecoli.js
#   docs/js/study002_ecoli.js
#   (one JS file per study* folder found under studies/)
#
# DEPENDENCIES
#   Python 3 — standard library only (csv, glob, json, math, os, datetime)
# =============================================================================

set -euo pipefail

# ── Resolve paths relative to this script's location ─────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_SCRIPT="$REPO_ROOT/user_provided/python/generate_study_summaries.py"
INDEX_HTML="$REPO_ROOT/docs/index.html"
PYTHON="${PYTHON:-python3}"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     astroPharmReactor  —  experiment          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Repo  : $REPO_ROOT"
echo "  Python: $("$PYTHON" --version 2>&1)"
echo ""

# ── Step 1: generate study summary JS files ───────────────────────────────────
echo "[ 1 / 2 ]  Scraping Arduino CSV data and generating study summaries …"
echo "           $PYTHON_SCRIPT"
echo ""
"$PYTHON" "$PYTHON_SCRIPT"

# ── Step 2: open the docs site in the default browser ────────────────────────
echo ""
echo "[ 2 / 2 ]  Opening site …"
echo "           $INDEX_HTML"

if command -v xdg-open &>/dev/null; then
    xdg-open "$INDEX_HTML"
elif command -v open &>/dev/null; then
    open "$INDEX_HTML"
else
    echo ""
    echo "  No browser opener found (tried xdg-open, open)."
    echo "  Open manually: file://$INDEX_HTML"
fi

echo ""
echo "  ✓  Build complete."
echo ""
