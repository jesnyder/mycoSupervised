#!/usr/bin/env python3
"""
generate_study_summaries.py
Generated: 2026-06-17
Author: astroPharmReactor project

OBJECTIVE
---------
Scan every study* folder under studies/ (repo root), read all CSV log files,
normalise inconsistent column names that changed as the logging scripts evolved,
compute per-variable statistics (ignoring bad / saturated sensor values), build
downsampled time-series chart data grouped by measurement unit, and write one
JavaScript data file per study to docs/js/.

The original CSV files are NEVER modified.  All normalisation and filtering
happens in memory only.

Running this script regenerates the entire website data layer:
  bash user_provided/makefile/build.sh

STUDY FOLDER DISCOVERY
-----------------------
The script looks for study* directories directly under studies/ (repo root):
  - studies/study001_ecoli/   (SHT30 only → SHT30+BME688)
  - studies/study002_ecoli/   (SHT30+2×BME688 → +AS7341 4ch → +AS7341 8ch)

COLUMN NAME EVOLUTION (schema history)
---------------------------------------
The Python logging scripts were written incrementally as sensors were added.
Each iteration changed column names.  This script maps all historical names
to a single canonical set so stats and charts span the full study timeline.

  Schema A  (SHT30 only — early study001):
    timestamp, elapsed_s, temperature_C, humidity_pct, speed_pct

  Schema B  (SHT30 + 1× BME688 — later study001, two study002 files):
    timestamp, elapsed_s, sht30_temp_C, sht30_humidity_pct,
    bme688_temp_C, bme688_humidity_pct, bme688_pressure_hpa,
    bme688_gas_ohms, motor_speed_pct

  Schema C  (SHT30 + 2× BME688 — study002, no light sensor):
    pc_timestamp, elapsed_s, arduino_date, arduino_time, uptime_s,
    sht30_temp_C, sht30_humidity_pct,
    bme688_1_*, bme688_2_*, stepper_speed_pct, pump_speed_pct, pump_state

  Schema D  (SHT30 + 2× BME688 + AS7341 4-channel — study002):
    Schema C + as7341_f1..f4, as7341_clear, as7341_nir

  Schema E  (SHT30 + 2× BME688 + AS7341 8-channel — study002 latest):
    Schema C + as7341_f1..f8, as7341_clear, as7341_nir

Canonical column aliases (COL_ALIASES):
  pc_timestamp          → timestamp
  temperature_C         → sht30_temp_C
  humidity_pct          → sht30_humidity_pct
  bme688_temp_C         → bme688_1_temp_C   (single-sensor era = sensor #1)
  bme688_humidity_pct   → bme688_1_humidity_pct
  bme688_pressure_hpa   → bme688_1_pressure_hpa
  bme688_gas_ohms       → bme688_1_gas_ohms
  speed_pct             → stepper_speed_pct
  motor_speed_pct       → stepper_speed_pct

BAD / SATURATED DATA FILTERING
--------------------------------
Values are flagged as bad (null in charts, excluded from stats, counted) when:
  1. Not parseable as a float, or is NaN / Inf
  2. Below the sensor's minimum valid range  (e.g. SHT30 reads -45 °C before
     it is ready — below its -40 °C minimum spec)
  3. Above the sensor's maximum valid range  (e.g. AS7341 16-bit ADC saturates
     at 65535 counts)
  4. Humidity exactly at 0 % or 100 % (sensor saturation boundary)

Sensor limits (SENSOR_LIMITS):
  sht30_temp_C             : -40 to 85 °C
  sht30_humidity_pct       :  0.1 to 99.9 % RH
  bme688_1/2_temp_C        : -40 to 85 °C
  bme688_1/2_humidity_pct  :  0.1 to 99.9 % RH
  bme688_1/2_pressure_hpa  : 300 to 1100 hPa
  bme688_1/2_gas_ohms      :   1 to 500 000 Ω
  as7341_f1..f8            :   0 to 65534 counts  (65535 = ADC saturated)
  as7341_clear / nir       :   0 to 65534 counts

CHART DATA GENERATION
----------------------
Sensor columns are mapped to named chart groups by measurement unit so that
sensors sharing the same unit appear on the same Plotly chart, distinguished
by colour.

  Chart groups (CHART_GROUPS):
    temperature  : sht30_temp_C, bme688_1_temp_C, bme688_2_temp_C       (°C)
    humidity     : sht30_humidity_pct, bme688_1/2_humidity_pct          (% RH)
    pressure     : bme688_1_pressure_hpa, bme688_2_pressure_hpa         (hPa)
    gas          : bme688_1_gas_ohms, bme688_2_gas_ohms                  (Ω)
    light        : as7341_f1..f8, as7341_clear, as7341_nir             (counts)

  Consistent sensor colours across all charts:
    SHT30     = #0969da (blue)
    BME688 #1 = #1a7f37 (green)
    BME688 #2 = #cf222e (red)
    AS7341 F1..F8, CLEAR, NIR = distinct palette

Downsampling:
  All sessions are merged into one time-ordered flat list.  A global
  downsample step (total_rows // MAX_CHART_POINTS) is applied so that each
  study produces at most MAX_CHART_POINTS data points per trace, keeping JS
  file sizes manageable.  Session gaps > 60 s are marked with a null row so
  Plotly renders a visible break rather than a misleading connecting line.

  All y values outside sensor limits become null (JSON null → Plotly gap).

  A single shared x-timestamp array is stored once and reused by all chart
  groups, reducing file size.

TIMELINE ANALYSIS
-----------------
Each CSV file = one logging session (Arduino running continuously).
Sessions sorted by first valid timestamp.

  wall_clock_hours  : calendar span from first to last sample across all files
  total_logged_hours: sum of each session's own duration (excludes gaps)
  sessions[]        : per-file start/end/rows/sensors
  gaps[]            : intervals > 5 s between consecutive sessions

OUTPUT JS FILES  (docs/js/<study_name>.js)
------------------------------------------
Each file sets two globals:

  window.STUDY_SUMMARIES["<name>"] = {
    study, generated,
    timeline: { first, last, wall_clock_hours, total_logged_hours,
                session_count, gap_count, sessions[], gaps[] },
    variables: {
      <col>: { label, unit, total_rows, valid_rows, bad_rows,
               bad_duration_s, bad_reasons, bad_windows[],
               min, max, range, mean }
    }
  };

  window.STUDY_CHARTS["<name>"] = {
    original_rows, sampled_rows,
    x: [...shared ISO timestamps...],
    groups: {
      temperature: { title, unit, traces: [{ name, color, y[] }] },
      humidity:    { ... },
      pressure:    { ... },
      gas:         { ... },
      light:       { ... },
    }
  };

docs/index.html loads these JS files and renders interactive Tabulator tables,
a session-timeline Plotly chart, a bad-data duration chart, and per-group
time-series Plotly charts for each study.

DEPENDENCIES
------------
Python standard library only: csv, glob, json, math, os, datetime, collections.

USAGE
-----
  python generate_study_summaries.py
  # or via the build script:
  bash user_provided/makefile/build.sh
"""

import csv
import glob
import json
import math
import os
from collections import defaultdict
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
STUDIES_DIR = os.path.join(REPO_ROOT, 'studies')
JS_OUT_DIR  = os.path.join(REPO_ROOT, 'docs', 'js')

# ── Column name normalisation ─────────────────────────────────────────────────
# Maps every historical column name → canonical name.
# Columns not listed here are kept as-is.
COL_ALIASES = {
    'pc_timestamp':         'timestamp',
    'temperature_C':        'sht30_temp_C',
    'humidity_pct':         'sht30_humidity_pct',
    'bme688_temp_C':        'bme688_1_temp_C',
    'bme688_humidity_pct':  'bme688_1_humidity_pct',
    'bme688_pressure_hpa':  'bme688_1_pressure_hpa',
    'bme688_gas_ohms':      'bme688_1_gas_ohms',
    'speed_pct':            'stepper_speed_pct',
    'motor_speed_pct':      'stepper_speed_pct',
}

# Columns excluded from sensor stats (metadata, control outputs, non-sensor)
SKIP_STATS = {
    'timestamp', 'elapsed_s', 'arduino_date', 'arduino_time',
    'uptime_s', 'stepper_speed_pct', 'pump_speed_pct', 'pump_state',
}

# ── Sensor valid ranges ───────────────────────────────────────────────────────
# Values outside [lo, hi] are flagged bad: null in charts, excluded from stats.
SENSOR_LIMITS = {
    'sht30_temp_C':           (-40.0,   85.0),
    'sht30_humidity_pct':     (  0.1,   99.9),
    'bme688_1_temp_C':        (-40.0,   85.0),
    'bme688_1_humidity_pct':  (  0.1,   99.9),
    'bme688_1_pressure_hpa':  (300.0, 1100.0),
    'bme688_1_gas_ohms':      (  1.0, 500000.0),
    'bme688_2_temp_C':        (-40.0,   85.0),
    'bme688_2_humidity_pct':  (  0.1,   99.9),
    'bme688_2_pressure_hpa':  (300.0, 1100.0),
    'bme688_2_gas_ohms':      (  1.0, 500000.0),
    # DFRobot_AS7341 library outputs a normalized 0–1000 scale, not raw 16-bit ADC.
    # A reading of exactly 1000 means the channel is saturated (ADC full-scale).
    # Upper limit set to 999 so that saturated rows are flagged above_max.
    **{f'as7341_f{i}': (0.0, 999.0) for i in range(1, 9)},
    'as7341_clear':           (0.0, 999.0),
    'as7341_nir':             (0.0, 999.0),
}

# Human-readable label and SI unit per canonical column
VARIABLE_META = {
    'sht30_temp_C':           ('SHT30 Temperature',        '°C'),
    'sht30_humidity_pct':     ('SHT30 Humidity',           '% RH'),
    'bme688_1_temp_C':        ('BME688 #1 Temperature',    '°C'),
    'bme688_1_humidity_pct':  ('BME688 #1 Humidity',       '% RH'),
    'bme688_1_pressure_hpa':  ('BME688 #1 Pressure',       'hPa'),
    'bme688_1_gas_ohms':      ('BME688 #1 Gas Resistance', 'Ω'),
    'bme688_2_temp_C':        ('BME688 #2 Temperature',    '°C'),
    'bme688_2_humidity_pct':  ('BME688 #2 Humidity',       '% RH'),
    'bme688_2_pressure_hpa':  ('BME688 #2 Pressure',       'hPa'),
    'bme688_2_gas_ohms':      ('BME688 #2 Gas Resistance', 'Ω'),
    **{f'as7341_f{i}': (f'AS7341 F{i}', 'counts') for i in range(1, 9)},
    'as7341_clear':           ('AS7341 CLEAR',             'counts'),
    'as7341_nir':             ('AS7341 NIR',               'counts'),
}

# ── Chart groups ──────────────────────────────────────────────────────────────
# Maps canonical column → (group_key, trace display name, hex colour).
# Sensors with the same unit go in the same group; same sensor = same colour
# across groups so the viewer can track a sensor across temperature/humidity/etc.
CHART_GROUPS = {
    # Temperature (°C) — left y-axis on temperature chart
    'sht30_temp_C':           ('temperature', 'SHT30',     '#0969da'),
    'bme688_1_temp_C':        ('temperature', 'BME688 #1', '#1a7f37'),
    'bme688_2_temp_C':        ('temperature', 'BME688 #2', '#cf222e'),
    # Humidity (% RH)
    'sht30_humidity_pct':     ('humidity',    'SHT30',     '#0969da'),
    'bme688_1_humidity_pct':  ('humidity',    'BME688 #1', '#1a7f37'),
    'bme688_2_humidity_pct':  ('humidity',    'BME688 #2', '#cf222e'),
    # Pressure (hPa)
    'bme688_1_pressure_hpa':  ('pressure',    'BME688 #1', '#1a7f37'),
    'bme688_2_pressure_hpa':  ('pressure',    'BME688 #2', '#cf222e'),
    # Gas resistance (Ω) — proxy for VOC / culture activity
    'bme688_1_gas_ohms':      ('gas',         'BME688 #1', '#1a7f37'),
    'bme688_2_gas_ohms':      ('gas',         'BME688 #2', '#cf222e'),
    # Light spectrum (counts) — AS7341 channels
    'as7341_f1':   ('light', 'F1 Blue',   '#1f6feb'),
    'as7341_f2':   ('light', 'F2 Cyan',   '#1b7c83'),
    'as7341_f3':   ('light', 'F3 Green',  '#1a7f37'),
    'as7341_f4':   ('light', 'F4 Yellow', '#9a6700'),
    'as7341_f5':   ('light', 'F5',        '#6e40c9'),
    'as7341_f6':   ('light', 'F6',        '#bf3989'),
    'as7341_f7':   ('light', 'F7',        '#953800'),
    'as7341_f8':   ('light', 'F8',        '#116329'),
    'as7341_clear':('light', 'CLEAR',     '#656d76'),
    'as7341_nir':  ('light', 'NIR',       '#8250df'),
}

# Title and y-axis label for each chart group
CHART_GROUP_META = {
    'temperature': ('Temperature',    '°C'),
    'humidity':    ('Humidity',       '% RH'),
    'pressure':    ('Pressure',       'hPa'),
    'gas':         ('Gas Resistance', 'Ω'),
    'light':       ('Light Spectrum', 'counts'),
}

# Target number of data points per trace after downsampling.
# ~4 000 points is smooth in Plotly and keeps JS files well under 2 MB.
MAX_CHART_POINTS = 4000


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalise_row(raw_row):
    """Apply COL_ALIASES to a row dict.  Returns new dict; input is unchanged."""
    return {COL_ALIASES.get(k, k): v for k, v in raw_row.items()}


def parse_timestamp(s):
    """Parse a timestamp string to datetime, or return None on failure."""
    if not s:
        return None
    s = s.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def is_bad(col, raw_value):
    """
    Return (bad: bool, reason: str) for a raw sensor string value.
    Reasons: 'nan', 'below_min', 'above_max', or '' when valid.
    """
    try:
        v = float(raw_value)
    except (ValueError, TypeError):
        return True, 'nan'
    if math.isnan(v) or math.isinf(v):
        return True, 'nan'
    if col in SENSOR_LIMITS:
        lo, hi = SENSOR_LIMITS[col]
        if v < lo:
            return True, 'below_min'
        if v > hi:
            return True, 'above_max'
    return False, ''


# ── File loading ──────────────────────────────────────────────────────────────

def load_study_files(study_dir):
    """
    Read every CSV in study_dir, normalise column names, and return a list of
    session dicts sorted by start timestamp.  Empty / unreadable files skipped.

    Each session dict:
      file       : filename
      start_dt   : first valid timestamp (datetime)
      end_dt     : last valid timestamp (datetime)
      duration_s : seconds from first to last timestamp
      rows       : list of normalised row dicts
      ts_list    : parallel list of datetime | None per row
    """
    csv_paths = sorted(glob.glob(os.path.join(study_dir, '*.csv')))
    sessions  = []

    for path in csv_paths:
        fname = os.path.basename(path)
        try:
            with open(path, newline='', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    print(f'  [skip] {fname}: no header row')
                    continue
                raw_rows = list(reader)
        except Exception as exc:
            print(f'  [skip] {fname}: {exc}')
            continue

        if not raw_rows:
            print(f'  [skip] {fname}: empty file')
            continue

        rows    = [normalise_row(r) for r in raw_rows]
        ts_list = [parse_timestamp(r.get('timestamp', '')) for r in rows]
        valid_ts = [t for t in ts_list if t is not None]

        if not valid_ts:
            print(f'  [skip] {fname}: no parseable timestamps')
            continue

        sessions.append({
            'file':       fname,
            'start_dt':   min(valid_ts),
            'end_dt':     max(valid_ts),
            'duration_s': (max(valid_ts) - min(valid_ts)).total_seconds(),
            'rows':       rows,
            'ts_list':    ts_list,
        })

    sessions.sort(key=lambda s: s['start_dt'])
    return sessions


# ── Variable statistics ───────────────────────────────────────────────────────

def compute_variable_stats(sessions):
    """
    Collect all (datetime, raw_value) pairs per sensor column across all
    sessions and compute valid/bad counts, bad windows, and min/max/range/mean.
    Returns a dict keyed by canonical column name.
    """
    col_entries = defaultdict(list)

    for sess in sessions:
        for row, dt in zip(sess['rows'], sess['ts_list']):
            if dt is None:
                continue
            for col, val in row.items():
                if col in SKIP_STATS or col == 'timestamp' or col.startswith('arduino_'):
                    continue
                col_entries[col].append((dt, val))

    stats = {}

    for col, entries in sorted(col_entries.items()):
        entries.sort(key=lambda x: x[0])

        valid_vals  = []
        bad_entries = []
        bad_reasons = defaultdict(int)

        for dt, val in entries:
            bad, reason = is_bad(col, val)
            if bad:
                bad_entries.append((dt, reason))
                bad_reasons[reason] += 1
            else:
                valid_vals.append(float(val))

        # Group consecutive bad timestamps into windows (gap > 5 s = new window)
        bad_windows = []
        if bad_entries:
            w_start = w_end = bad_entries[0][0]
            w_reason = bad_entries[0][1]
            for dt, reason in bad_entries[1:]:
                if (dt - w_end).total_seconds() <= 5:
                    w_end = dt
                else:
                    bad_windows.append({
                        'start':      w_start.strftime('%Y-%m-%d %H:%M:%S'),
                        'end':        w_end.strftime('%Y-%m-%d %H:%M:%S'),
                        'duration_s': int((w_end - w_start).total_seconds()) + 1,
                        'reason':     w_reason,
                    })
                    w_start, w_end, w_reason = dt, dt, reason
            bad_windows.append({
                'start':      w_start.strftime('%Y-%m-%d %H:%M:%S'),
                'end':        w_end.strftime('%Y-%m-%d %H:%M:%S'),
                'duration_s': int((w_end - w_start).total_seconds()) + 1,
                'reason':     w_reason,
            })

        label, unit = VARIABLE_META.get(col, (col, ''))
        entry = {
            'label':          label,
            'unit':           unit,
            'total_rows':     len(entries),
            'valid_rows':     len(valid_vals),
            'bad_rows':       len(entries) - len(valid_vals),
            'bad_duration_s': sum(w['duration_s'] for w in bad_windows),
            'bad_reasons':    dict(bad_reasons),
            'bad_windows':    bad_windows,
        }
        if valid_vals:
            entry['min']   = round(min(valid_vals), 4)
            entry['max']   = round(max(valid_vals), 4)
            entry['range'] = round(max(valid_vals) - min(valid_vals), 4)
            entry['mean']  = round(sum(valid_vals) / len(valid_vals), 4)
        else:
            entry['min'] = entry['max'] = entry['range'] = entry['mean'] = None

        stats[col] = entry

    return stats


# ── Chart data ────────────────────────────────────────────────────────────────

def build_chart_data(sessions):
    """
    Build downsampled time-series data for all chart groups across all sessions.

    Steps:
      1. Compute a global downsample step so total output ≤ MAX_CHART_POINTS.
      2. Within each session, take every step-th row.
      3. Insert a null-valued row at session boundaries where gap > 60 s so
         Plotly shows a visible break instead of a connecting line.
      4. Produce a single shared x-timestamp array and per-trace y arrays
         (bad / out-of-range values become None → JSON null → Plotly gap).
      5. Only include chart groups and traces that have at least some valid data.

    Returns a dict ready for JSON serialisation.
    """
    total_rows = sum(len(s['rows']) for s in sessions)
    step = max(1, total_rows // MAX_CHART_POINTS)

    # Build flat list of (datetime, row_dict | None)
    # None entries are session-gap separators that produce line breaks in Plotly
    flat = []
    for i, sess in enumerate(sessions):
        pairs = [
            (dt, row)
            for dt, row in zip(sess['ts_list'], sess['rows'])
            if dt is not None
        ]
        flat.extend(pairs[::step])

        if i < len(sessions) - 1:
            gap_s = (sessions[i + 1]['start_dt'] - sess['end_dt']).total_seconds()
            if gap_s > 60:
                flat.append((sess['end_dt'], None))  # separator

    # Shared x timestamps
    x = [dt.strftime('%Y-%m-%d %H:%M:%S') for dt, _ in flat]

    # Determine which chart columns are present anywhere in the flat data
    present_cols = set()
    for _, row in flat:
        if row is not None:
            present_cols.update(row.keys())
    chart_cols = sorted(
        col for col in present_cols
        if col in CHART_GROUPS
    )

    # Build y arrays (float or None) per column
    col_y = {}
    for col in chart_cols:
        y = []
        for _, row in flat:
            if row is None:
                y.append(None)
                continue
            val = row.get(col, '')
            if not val:
                y.append(None)
            else:
                bad, _ = is_bad(col, val)
                y.append(None if bad else round(float(val), 2))
        col_y[col] = y

    # Group into chart groups; skip traces with no valid data at all
    groups = {}
    group_order = ['temperature', 'humidity', 'pressure', 'gas', 'light']

    for col in chart_cols:
        group_key, trace_name, color = CHART_GROUPS[col]
        if any(v is not None for v in col_y[col]):
            if group_key not in groups:
                title, unit = CHART_GROUP_META[group_key]
                groups[group_key] = {'title': title, 'unit': unit, 'traces': []}
            groups[group_key]['traces'].append({
                'name':  trace_name,
                'color': color,
                'y':     col_y[col],
            })

    # Return groups in defined display order
    ordered_groups = {k: groups[k] for k in group_order if k in groups}

    return {
        'original_rows': total_rows,
        'sampled_rows':  len(x),
        'x':             x,
        'groups':        ordered_groups,
    }


# ── Experiment description ───────────────────────────────────────────────────

def read_description(study_dir):
    """Return text of description.txt from study_dir, or None if absent."""
    path = os.path.join(study_dir, 'description.txt')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return fh.read().strip() or None


# ── Data interpretation ───────────────────────────────────────────────────────

def generate_interpretation(sessions, variable_stats):
    """
    Produce plain-English interpretation text from the computed statistics.
    Uses only data already in variable_stats (no second pass over raw CSVs).

    Returns:
      {
        'temp_pressure_text': str,  — 2-3 sentences about T-P relationship
        'bullets': [str, ...]       — interpretation bullets for results section
      }
    """
    bullets = []

    # ── Helper: first stat dict that has a non-None mean ─────────────────
    def best(cols):
        for c in cols:
            if variable_stats.get(c, {}).get('mean') is not None:
                return c, variable_stats[c]
        return None, None

    tc, ts = best(['bme688_1_temp_C', 'sht30_temp_C', 'bme688_2_temp_C'])
    pc, ps = best(['bme688_1_pressure_hpa', 'bme688_2_pressure_hpa'])
    gc, gs = best(['bme688_1_gas_ohms', 'bme688_2_gas_ohms'])

    # ── Temperature stability ─────────────────────────────────────────────
    if tc:
        mean_t, range_t, lbl_t = ts['mean'], ts['range'], ts['label']
        if range_t < 2:
            bullets.append(
                f"Temperature was stable: {lbl_t} averaged {mean_t:.1f} °C with a range "
                f"of only {range_t:.1f} °C, consistent with a controlled incubation environment."
            )
        elif range_t < 5:
            bullets.append(
                f"Temperature showed moderate variation: {lbl_t} averaged {mean_t:.1f} °C "
                f"(range {range_t:.1f} °C), likely reflecting differences between sessions "
                f"rather than within-session instability."
            )
        else:
            bullets.append(
                f"Temperature varied substantially: {lbl_t} averaged {mean_t:.1f} °C "
                f"(range {range_t:.1f} °C). Conditions likely differed between sessions, "
                f"or warm-up / cool-down periods were captured."
            )

    # ── Sensor agreement ─────────────────────────────────────────────────
    m1 = variable_stats.get('bme688_1_temp_C', {}).get('mean')
    m2 = variable_stats.get('bme688_2_temp_C', {}).get('mean')
    ms = variable_stats.get('sht30_temp_C',    {}).get('mean')

    if m1 is not None and m2 is not None:
        diff_bb = abs(m1 - m2)
        if diff_bb < 0.5:
            bullets.append(
                f"The two BME688 sensors agreed closely on temperature "
                f"(mean offset {diff_bb:.2f} °C), supporting measurement reliability."
            )
        elif diff_bb < 2.0:
            bullets.append(
                f"The BME688 sensors showed a mean temperature offset of {diff_bb:.2f} °C — "
                f"within the ±1 °C manufacturer tolerance. Sensor placement differences "
                f"(e.g. proximity to the pump motor) may contribute."
            )
        else:
            bullets.append(
                f"A {diff_bb:.1f} °C mean offset between BME688 #1 and #2 is larger than "
                f"typical calibration tolerance and may indicate one sensor is influenced "
                f"by a local heat source or has drifted from its factory calibration."
            )

    if ms is not None and m1 is not None:
        diff_sb = abs(ms - m1)
        if diff_sb > 1.5:
            bullets.append(
                f"SHT30 and BME688 #1 mean temperatures differed by {diff_sb:.1f} °C. "
                f"The two sensor types have different thermal time constants and housings; "
                f"placement in different locations inside the vessel can account for this."
            )

    # ── Humidity ─────────────────────────────────────────────────────────
    hc, hs = best(['sht30_humidity_pct', 'bme688_1_humidity_pct'])
    if hc:
        mean_h = hs['mean']
        if mean_h > 80:
            bullets.append(
                f"Mean humidity was high ({mean_h:.0f}% RH), expected in a bioreactor "
                f"environment where media evaporation and culture respiration raise moisture levels."
            )

    # ── Gas resistance / culture proxy ───────────────────────────────────
    if gc:
        mean_g   = gs['mean']
        range_g  = gs['range']
        kohm     = mean_g / 1000
        pct_var  = range_g / mean_g * 100 if mean_g else 0

        level = (
            "low — elevated VOC loading or a sensor still in thermal conditioning"
            if kohm < 10 else
            "high — relatively clean or low-VOC environment" if kohm > 100 else
            "moderate"
        )
        trend = (
            f"Wide variation ({pct_var:.0f}% of mean) may correlate with culture growth phases."
            if pct_var > 30 else
            "Gas resistance was relatively stable across sessions."
        )
        bullets.append(
            f"BME688 gas resistance averaged {kohm:.0f} kΩ ({level}). "
            f"{trend} "
            f"Note: BME688 gas readings require several hours of thermal conditioning "
            f"before stabilising — early-session values should be interpreted cautiously."
        )

    # ── Bad data ─────────────────────────────────────────────────────────
    high_bad = sorted(
        [(s['label'], s['bad_rows'] / s['total_rows'] * 100,
          max(s['bad_reasons'], key=s['bad_reasons'].get) if s['bad_reasons'] else '?')
         for s in variable_stats.values()
         if s['total_rows'] > 0 and s['bad_rows'] / s['total_rows'] > 0.05],
        key=lambda x: -x[1]
    )
    if high_bad:
        parts = [f"{lbl} ({pct:.0f}%, {rsn})" for lbl, pct, rsn in high_bad[:3]]
        bullets.append(
            f"Sensors with >5% bad readings: {'; '.join(parts)}. "
            f"High bad fractions usually indicate a disconnected or initialising sensor "
            f"rather than a fundamental measurement failure."
        )
    else:
        bullets.append(
            "Bad-reading rates were low for all channels — startup transients and "
            "saturation events were brief and well-isolated."
        )

    # ── Session coverage ─────────────────────────────────────────────────
    if sessions:
        wall_s   = (sessions[-1]['end_dt'] - sessions[0]['start_dt']).total_seconds()
        logged_s = sum(s['duration_s'] for s in sessions)
        coverage = logged_s / wall_s if wall_s > 0 else 1.0
        n        = len(sessions)
        if coverage > 0.9:
            bullets.append(
                f"Logging coverage was continuous: {coverage * 100:.0f}% of the "
                f"{wall_s / 3600:.1f} h experiment span captured across {n} session(s)."
            )
        else:
            gap_h = (wall_s - logged_s) / 3600
            bullets.append(
                f"Logging ran across {n} session(s) with ~{gap_h:.1f} h of gaps "
                f"in a {wall_s / 3600:.1f} h window ({coverage * 100:.0f}% coverage). "
                f"Gaps likely reflect equipment restarts or deliberate pauses between "
                f"experimental phases."
            )

    # ── Temperature-pressure relationship text ────────────────────────────
    if tc and pc:
        mean_p  = ps['mean']
        range_p = ps['range']
        dev     = abs(mean_p - 1013.25)

        p1 = (
            f"This bioreactor is an open vessel, so pressure is governed by local atmospheric "
            f"conditions rather than culture temperature or activity. "
            f"{ps['label']} averaged {mean_p:.1f} hPa (range: {range_p:.1f} hPa) — "
        )
        p1 += (
            "consistent with standard atmospheric pressure."
            if dev < 15 else
            f"{dev:.0f} hPa {'below' if mean_p < 1013.25 else 'above'} "
            f"sea-level standard, consistent with this site's altitude."
        )

        if range_p < 3:
            p2 = (
                " Pressure was very stable throughout, as expected for an open system. "
                "Any apparent co-variation with temperature in the chart is noise rather "
                "than a physical coupling."
            )
        elif range_p < 10:
            p2 = (
                " Moderate pressure variation likely reflects day-to-day weather changes "
                "across the multi-session experiment, not culture-driven effects."
            )
        else:
            p2 = (
                " The wider pressure range may reflect weather variation, "
                "BME688 temperature-compensation artefacts, or sensor drift across the "
                "multi-day experiment."
            )
        tp_text = p1 + p2

    elif tc:
        tp_text = (
            "No pressure sensor was present during this study period. "
            "Temperature trends are shown on the left axis only."
        )
    elif pc:
        mean_p  = ps['mean']
        range_p = ps['range']
        tp_text = (
            f"Pressure averaged {mean_p:.1f} hPa (range: {range_p:.1f} hPa). "
            "No temperature data was available for this period."
        )
    else:
        tp_text = (
            "Insufficient data to characterise the temperature-pressure relationship."
        )

    return {
        'temp_pressure_text': tp_text,
        'bullets':            bullets,
    }


# ── Study summary ─────────────────────────────────────────────────────────────

def summarise_study(study_dir):
    """
    Load all sessions, compute timeline + stats + chart data, and return the
    full summary dict.  Returns None if no valid sessions are found.
    """
    study_name = os.path.basename(study_dir)
    print(f'\nProcessing {study_name} ...')

    sessions = load_study_files(study_dir)
    if not sessions:
        print('  No valid sessions found — skipping.')
        return None

    # Timeline
    overall_start  = sessions[0]['start_dt']
    overall_end    = sessions[-1]['end_dt']
    wall_clock_s   = (overall_end - overall_start).total_seconds()
    total_logged_s = sum(s['duration_s'] for s in sessions)

    session_summaries = []
    for s in sessions:
        all_cols    = set(col for row in s['rows'] for col in row)
        sensor_cols = sorted(
            c for c in all_cols
            if c not in SKIP_STATS and c != 'timestamp' and not c.startswith('arduino_')
        )
        session_summaries.append({
            'file':       s['file'],
            'start':      s['start_dt'].strftime('%Y-%m-%d %H:%M:%S'),
            'end':        s['end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
            'duration_s': int(s['duration_s']),
            'rows':       len(s['rows']),
            'sensors':    sensor_cols,
        })

    gaps = []
    for i in range(1, len(sessions)):
        gap_s = (sessions[i]['start_dt'] - sessions[i - 1]['end_dt']).total_seconds()
        if gap_s > 5:
            gaps.append({
                'after_file':  sessions[i - 1]['file'],
                'before_file': sessions[i]['file'],
                'gap_s':       int(gap_s),
                'gap_minutes': round(gap_s / 60, 1),
                'gap_hours':   round(gap_s / 3600, 2),
            })

    timeline = {
        'first':              overall_start.strftime('%Y-%m-%d %H:%M:%S'),
        'last':               overall_end.strftime('%Y-%m-%d %H:%M:%S'),
        'wall_clock_s':       int(wall_clock_s),
        'wall_clock_hours':   round(wall_clock_s / 3600, 2),
        'total_logged_s':     int(total_logged_s),
        'total_logged_hours': round(total_logged_s / 3600, 2),
        'session_count':      len(sessions),
        'gap_count':          len(gaps),
        'sessions':           session_summaries,
        'gaps':               gaps,
    }

    print(f'  {len(sessions)} sessions, {int(total_logged_s):,} s logged')
    print('  Computing variable stats ...')
    variable_stats = compute_variable_stats(sessions)

    print('  Building chart data ...')
    chart_data = build_chart_data(sessions)
    print(f'  Chart: {chart_data["original_rows"]:,} rows → '
          f'{chart_data["sampled_rows"]:,} sampled, '
          f'{len(chart_data["groups"])} groups')

    description    = read_description(study_dir)
    interpretation = generate_interpretation(sessions, variable_stats)
    if description:
        print(f'  Description: {len(description)} chars')

    return {
        'study':          study_name,
        'generated':      datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'description':    description,
        'interpretation': interpretation,
        'timeline':       timeline,
        'variables':      variable_stats,
        'charts':         chart_data,
    }


# ── JS output ─────────────────────────────────────────────────────────────────

def write_js(summary, out_dir):
    """
    Write docs/js/<study_name>.js containing two window globals:
      window.STUDY_SUMMARIES["<name>"]  — stats / timeline
      window.STUDY_CHARTS["<name>"]     — downsampled time-series chart data
    """
    study_name = summary['study']
    out_path   = os.path.join(out_dir, f'{study_name}.js')

    # Split summary into stats and chart portions
    chart_data = summary.pop('charts')

    summary_json = json.dumps(summary,    indent=2, ensure_ascii=False)
    chart_json   = json.dumps(chart_data, indent=2, ensure_ascii=False)

    header = (
        f'// Auto-generated by generate_study_summaries.py\n'
        f'// Study: {study_name}  |  Generated: {summary["generated"]}\n'
        f'// Re-generate: bash user_provided/makefile/build.sh\n\n'
    )

    js = (
        header +
        f'window.STUDY_SUMMARIES = window.STUDY_SUMMARIES || {{}};\n'
        f'window.STUDY_SUMMARIES["{study_name}"] = {summary_json};\n\n'
        f'window.STUDY_CHARTS = window.STUDY_CHARTS || {{}};\n'
        f'window.STUDY_CHARTS["{study_name}"] = {chart_json};\n'
    )

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(js)

    size_kb = os.path.getsize(out_path) / 1024
    print(f'  → {os.path.relpath(out_path, REPO_ROOT)}  ({size_kb:.0f} KB)')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    study_dirs = sorted(
        d for d in glob.glob(os.path.join(STUDIES_DIR, 'study*'))
        if os.path.isdir(d)
    )

    if not study_dirs:
        print(f'No study* folders found under {STUDIES_DIR}')
        return

    names = [os.path.basename(d) for d in study_dirs]
    print(f'Found {len(study_dirs)} study folder(s): {names}')
    print(f'Output: {JS_OUT_DIR}')

    for sd in study_dirs:
        summary = summarise_study(sd)
        if summary:
            write_js(summary, JS_OUT_DIR)

    print('\nDone.')


if __name__ == '__main__':
    main()
