#!/usr/bin/env python3
"""
generate_study_summaries.py
Generated: 2026-06-17
Author: mycoSupervised project

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
  - studies/study001_pilot/   (fungal culture inoculated into a sterile substrate bag)

COLUMN NAME EVOLUTION (schema history)
---------------------------------------
The Python logging scripts were written incrementally, on a prior project
using this same rig, as sensors were added.  Each iteration changed column
names.  This script maps all historical names to a single canonical set so
stats and charts span the full study timeline even if older schema versions
reappear in future studies.

  Schema A  (SHT30 only):
    timestamp, elapsed_s, temperature_C, humidity_pct, speed_pct

  Schema B  (SHT30 + 1× BME688):
    timestamp, elapsed_s, sht30_temp_C, sht30_humidity_pct,
    bme688_temp_C, bme688_humidity_pct, bme688_pressure_hpa,
    bme688_gas_ohms, motor_speed_pct

  Schema C  (SHT30 + 2× BME688, no light sensor):
    pc_timestamp, elapsed_s, arduino_date, arduino_time, uptime_s,
    sht30_temp_C, sht30_humidity_pct,
    bme688_1_*, bme688_2_*, stepper_speed_pct, pump_speed_pct, pump_state

  Schema D  (SHT30 + 2× BME688 + AS7341 Mode-1 6-channel — study001_pilot,
             CSVs logged before 2026-07-08):
    Schema C + as7341_f1..f4, as7341_clear, as7341_nir
    AS7341 physically has 8 narrowband channels (F1-F8) + CLEAR + NIR, but
    reading all 8 requires two measurement passes (DFRobot_AS7341 Mode 1 and
    Mode 2 — see 01_stepper_motor.ino). Before 2026-07-08, study001_pilot's
    firmware only called Mode 1 (startMeasure(eF1F4ClearNIR) /
    readSpectralDataOne()), so F5-F8 were never captured. This was a firmware
    limitation, not a bug in this script — as7341_f5..f8 are simply absent
    from any CSV that doesn't log them, and this script tolerates that.

  Schema E  (SHT30 + 2× BME688 + AS7341 full 8-channel — study001_pilot,
             CSVs logged from 2026-07-08 onward):
    Schema C + as7341_f1..f8, as7341_clear, as7341_nir
    Firmware now calls both Mode 1 (eF1F4ClearNIR / readSpectralDataOne())
    and Mode 2 (eF5F8ClearNIR / readSpectralDataTwo()) every logging cycle,
    so all 8 filtered channels are captured each sample. CLEAR/NIR are
    logged once per row, from the Mode 1 pass. Schema D and Schema E CSVs
    can coexist in the same studies/ folder — this script processes each
    file's columns independently, so older 6-channel sessions simply have
    no as7341_f5..f8 values while newer sessions do.

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
  file sizes manageable.  Any gap > GAP_BREAK_THRESHOLD_S (60 s) between two
  consecutive *kept* points — whether between separate session files or
  inside a single session that stalled without closing (see WITHIN-SESSION
  GAPS above) — is marked with a null row so Plotly renders a visible break
  rather than a misleading connecting line across missing data.

  All y values outside sensor limits become null (JSON null → Plotly gap).

  A single shared x-timestamp array is stored once and reused by all chart
  groups, reducing file size.

TIMELINE ANALYSIS
-----------------
Each CSV file = one logging session. Sessions sorted by first valid
timestamp. A session file staying open does NOT guarantee continuous
capture — see WITHIN-SESSION GAPS below — so "session" here means "one CSV
file," not "one uninterrupted stretch of data."

  wall_clock_hours  : calendar span from first to last sample across all files
  total_logged_hours: sum of each session's own duration, MINUS any
                       within-session gap time (see below) — this is the
                       actual amount of time covered by real samples, not
                       just the span between a file's first and last row
  sessions[]        : per-file start/end/rows/sensors/within_gap_s
  gaps[]            : all gaps worth surfacing, both between sessions
                       (> SESSION_GAP_MIN_S = 5 s) and within a single
                       session (> GAP_BREAK_THRESHOLD_S = 60 s) — see
                       WITHIN-SESSION GAPS. Each entry has a 'type' field:
                       'between_sessions' or 'within_session'.

WITHIN-SESSION GAPS
--------------------
A single CSV file can stay open across a long logging interruption without
ever closing and reopening — e.g. if the host PC running the Python logger
goes to sleep, the Arduino keeps transmitting on its own independent clock,
but the tiny serial buffers can't hold hours of backlog, so most of what
the Arduino sent during the interruption is simply never captured. Only
checking gaps *between* files (the old behavior) makes this invisible: it
looks like one long, continuous session in the timeline and chart.

find_within_session_gaps() scans each session's own consecutive timestamps
for jumps > GAP_BREAK_THRESHOLD_S and records, for each one, how much the
Arduino's own uptime_s field advanced across the same two rows
(arduino_uptime_delta_s). A small uptime delta despite a large timestamp
gap means the Arduino kept running normally throughout — the interruption
was on the host PC / logger side, not a sensor or power failure. A large
uptime delta comparable to the gap itself would instead suggest the
Arduino was reset or also stalled. This diagnostic is reported per-gap in
gaps[] so it doesn't need to be re-derived by hand each time.

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
               min, max, range, mean,
               slope_per_hour, trend_r, diurnal_fit, diurnal_r2,
               best_fit_model }
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

docs/<study_name>.html loads these JS files and renders interactive Tabulator
tables, a session-timeline Plotly chart, a bad-data duration chart, and per-group
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
    # DFRobot_AS7341's readSpectralDataOne()/readSpectralDataTwo() return RAW,
    # unmodified 16-bit ADC register counts (confirmed against
    # DFRobot_AS7341.cpp getChannelData() — it reads two register bytes into
    # a uint16_t with no scaling). 65535 = full-scale saturation; upper limit
    # set to 65534 so saturated rows are flagged above_max. (Do NOT assume a
    # normalized 0-1000 scale here — an earlier version of this script did,
    # based on an empirical observation that study001_pilot's specific light
    # source/gain/integration-time settings happened to keep raw counts under
    # ~1000; that is a lighting/gain artifact of one study, not a library
    # behavior, and would have silently nulled out valid readings from any
    # brighter session or different gain setting.)
    **{f'as7341_f{i}': (0.0, 65534.0) for i in range(1, 9)},
    'as7341_clear':           (0.0, 65534.0),
    'as7341_nir':             (0.0, 65534.0),
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
    # Wavelength/color per the AMS AS7341 datasheet visible-light detection
    # ranges: F1 405-425nm, F2 435-455nm, F3 470-490nm, F4 505-525nm,
    # F5 545-565nm, F6 580-600nm, F7 620-640nm, F8 670-690nm.
    'as7341_f1':              ('AS7341 F1 (415nm Violet)', 'counts'),
    'as7341_f2':              ('AS7341 F2 (445nm Indigo)', 'counts'),
    'as7341_f3':              ('AS7341 F3 (480nm Blue)',   'counts'),
    'as7341_f4':              ('AS7341 F4 (515nm Cyan)',   'counts'),
    'as7341_f5':              ('AS7341 F5 (555nm Green)',  'counts'),
    'as7341_f6':              ('AS7341 F6 (590nm Yellow)', 'counts'),
    'as7341_f7':              ('AS7341 F7 (630nm Orange)', 'counts'),
    'as7341_f8':              ('AS7341 F8 (680nm Red)',    'counts'),
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
    # Light spectrum (counts) — AS7341 channels. Trace colors approximate
    # each channel's actual wavelength (violet -> red across F1-F8) so the
    # chart legend reads like a visible spectrum; CLEAR/NIR are neutral.
    'as7341_f1':   ('light', 'F1 Violet (415nm)', '#6f42c1'),
    'as7341_f2':   ('light', 'F2 Indigo (445nm)', '#4c51bf'),
    'as7341_f3':   ('light', 'F3 Blue (480nm)',   '#1f6feb'),
    'as7341_f4':   ('light', 'F4 Cyan (515nm)',   '#0e8a86'),
    'as7341_f5':   ('light', 'F5 Green (555nm)',  '#1a7f37'),
    'as7341_f6':   ('light', 'F6 Yellow (590nm)', '#9a6700'),
    'as7341_f7':   ('light', 'F7 Orange (630nm)', '#bc4c00'),
    'as7341_f8':   ('light', 'F8 Red (680nm)',    '#cf222e'),
    'as7341_clear':('light', 'CLEAR',             '#656d76'),
    'as7341_nir':  ('light', 'NIR (~855nm)',      '#57606a'),
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

# Any gap between two consecutive timestamps larger than this is treated as a
# logging interruption: it gets a null-row break in the charts (so Plotly
# doesn't draw a connecting line across it) and an entry in the gaps list.
# Applies both between sessions (different CSV files) and *within* a single
# session (see WITHIN-SESSION GAPS below) — one consistent threshold for
# "this doesn't look like normal sampling jitter anymore." 60s is comfortably
# above the fastest logging interval used so far (3-5s), so ordinary jitter
# never triggers it, but a stalled PC logger reliably does.
GAP_BREAK_THRESHOLD_S = 60

# Between-session gaps use a much lower threshold (5s) than within-session
# gaps (60s, above) because there are only ever a handful of sessions (one
# per CSV file) so a low threshold doesn't create noise, and small gaps
# between files are usually meaningful (e.g. the logger being restarted).
SESSION_GAP_MIN_S = 5


# ── Trend, diurnal-cycle & functional-form regression ─────────────────────────
# All fits use only the Python standard library (no numpy/scipy): every model
# below is either fit directly by closed-form OLS, or linearised (log/ln
# transform) so a closed-form OLS still applies. See docs/index.html
# ("Trend & Diurnal Regression Analysis") for the full write-up of the method
# and the reasoning behind each threshold.
MIN_TREND_POINTS     = 3      # need at least 3 points for a meaningful line
MIN_DIURNAL_POINTS   = 20     # need enough points to fit 3 harmonic parameters reliably
DIURNAL_R2_THRESHOLD = 0.15   # heuristic: >=15% of variance explained by a 24h cycle
FIT_R2_THRESHOLD      = 0.30  # heuristic: >=30% of variance explained to report a functional form


def ols(x, y):
    """
    Ordinary least-squares fit of y = intercept + slope*x.
    Returns (slope, intercept, r) or None if fewer than 2 points or x is
    constant (zero variance).  r is Pearson's correlation coefficient
    (None if y is constant).
    """
    n = len(x)
    if n < 2:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        return None
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = my - slope * mx
    syy = sum((yi - my) ** 2 for yi in y)
    r = (sxy / math.sqrt(sxx * syy)) if syy > 0 else None
    return slope, intercept, r


def r2_in_original_space(y, yhat):
    """R^2 = 1 - SS_res/SS_tot, comparing predictions to actual y (both in
    the same, untransformed units) so different candidate models are
    directly comparable. None if y has zero variance."""
    n = len(y)
    my = sum(y) / n
    ss_tot = sum((yi - my) ** 2 for yi in y)
    if ss_tot == 0:
        return None
    ss_res = sum((yi - yhi) ** 2 for yi, yhi in zip(y, yhat))
    return max(0.0, 1 - ss_res / ss_tot)


def solve_3x3(A, b):
    """Solve a 3x3 linear system by Gaussian elimination with partial
    pivoting.  Returns None if the matrix is singular."""
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(3):
        pivot_row = max(range(col, 3), key=lambda r: abs(M[r][col]))
        if abs(M[pivot_row][col]) < 1e-12:
            return None
        M[col], M[pivot_row] = M[pivot_row], M[col]
        for r in range(3):
            if r == col:
                continue
            factor = M[r][col] / M[col][col]
            for c in range(col, 4):
                M[r][c] -= factor * M[col][c]
    return [M[i][3] / M[i][i] for i in range(3)]


def diurnal_fit_r2(t_hours, y):
    """
    Fit y = a + b*sin(theta) + c*cos(theta), theta = 2*pi*t_hours/24 (a
    24-hour harmonic), by closed-form least squares, and return the R^2 of
    that fit — the fraction of variance explained by a diurnal cycle of any
    phase/amplitude. A phase shift only redistributes the fit between the
    sin and cos terms, so R^2 does not depend on the arbitrary choice of
    time origin used for t_hours. None if too few points or the fit is
    degenerate.
    """
    n = len(y)
    if n < MIN_DIURNAL_POINTS:
        return None
    theta = [2 * math.pi * t / 24.0 for t in t_hours]
    s = [math.sin(th) for th in theta]
    c = [math.cos(th) for th in theta]

    sum1, sums, sumc = float(n), sum(s), sum(c)
    sumss = sum(si * si for si in s)
    sumcc = sum(ci * ci for ci in c)
    sumsc = sum(si * ci for si, ci in zip(s, c))
    sumy  = sum(y)
    sumsy = sum(si * yi for si, yi in zip(s, y))
    sumcy = sum(ci * yi for ci, yi in zip(c, y))

    A = [[sum1, sums, sumc], [sums, sumss, sumsc], [sumc, sumsc, sumcc]]
    coeffs = solve_3x3(A, [sumy, sumsy, sumcy])
    if coeffs is None:
        return None
    a0, b0, c0 = coeffs

    yhat = [a0 + b0 * si + c0 * ci for si, ci in zip(s, c)]
    return r2_in_original_space(y, yhat)


def best_fit_model(t_hours, y):
    """
    Compare Linear, Exponential (growth/decay), Logarithmic, and Power-law
    fits of y vs. elapsed time, each obtained via OLS after the appropriate
    linearising transform (ln(y) and/or ln(t)), with R^2 always evaluated
    back in original y-units so the candidates are comparable on equal
    footing. Returns the label of the best-fitting candidate, or None if no
    candidate clears FIT_R2_THRESHOLD (no clear functional form — data is
    ~flat or dominated by noise).
    """
    n = len(y)
    if n < MIN_TREND_POINTS:
        return None

    candidates = []  # [(label, r2), ...]

    # Linear: y = a + b*t
    lin = ols(t_hours, y)
    if lin:
        slope, intercept, _ = lin
        yhat = [intercept + slope * ti for ti in t_hours]
        r2 = r2_in_original_space(y, yhat)
        if r2 is not None:
            candidates.append(('Linear', r2))

    all_positive_y = all(yi > 0 for yi in y)
    t_min = min(t_hours)
    t_shift = [ti - t_min + 0.01 for ti in t_hours]  # > 0, so ln(t) is defined
    ln_t = [math.log(ti) for ti in t_shift]

    # Exponential: y = a * exp(b*t)  ->  ln(y) = ln(a) + b*t
    if all_positive_y:
        try:
            ln_y = [math.log(yi) for yi in y]
            exp_fit = ols(t_hours, ln_y)
            if exp_fit:
                slope, intercept, _ = exp_fit
                a = math.exp(intercept)
                yhat = [a * math.exp(slope * ti) for ti in t_hours]
                r2 = r2_in_original_space(y, yhat)
                if r2 is not None:
                    label = 'Exponential Growth' if slope > 0 else 'Exponential Decay'
                    candidates.append((label, r2))
        except (ValueError, OverflowError):
            pass

    # Logarithmic: y = a + b*ln(t)
    log_fit = ols(ln_t, y)
    if log_fit:
        slope, intercept, _ = log_fit
        yhat = [intercept + slope * lti for lti in ln_t]
        r2 = r2_in_original_space(y, yhat)
        if r2 is not None:
            candidates.append(('Logarithmic', r2))

    # Power law: y = a * t^b  ->  ln(y) = ln(a) + b*ln(t)
    if all_positive_y:
        try:
            ln_y = [math.log(yi) for yi in y]
            pow_fit = ols(ln_t, ln_y)
            if pow_fit:
                slope, intercept, _ = pow_fit
                a = math.exp(intercept)
                yhat = [a * (ti ** slope) for ti in t_shift]
                r2 = r2_in_original_space(y, yhat)
                if r2 is not None:
                    candidates.append(('Power Law', r2))
        except (ValueError, OverflowError):
            pass

    if not candidates:
        return None
    best_label, best_r2 = max(candidates, key=lambda c: c[1])
    return best_label if best_r2 >= FIT_R2_THRESHOLD else None


def compute_trend_stats(valid_pairs):
    """
    Given a list of (datetime, float) valid samples for one sensor column,
    return (slope_per_hour, trend_r, diurnal_fit, diurnal_r2, best_fit_model).

    slope/r use each sample's absolute epoch time (hours) as x, so results
    do not depend on an arbitrary choice of time origin. slope/r are None
    if there are too few points; diurnal_fit is True/False/None;
    best_fit_model is a label string or None.
    """
    if len(valid_pairs) < MIN_TREND_POINTS:
        return None, None, None, None, None

    t_hours = [dt.timestamp() / 3600.0 for dt, _ in valid_pairs]
    y = [v for _, v in valid_pairs]

    lin = ols(t_hours, y)
    slope, r = (lin[0], lin[2]) if lin else (None, None)

    diurnal_r2 = diurnal_fit_r2(t_hours, y)
    diurnal_fit = None if diurnal_r2 is None else (diurnal_r2 >= DIURNAL_R2_THRESHOLD)

    model = best_fit_model(t_hours, y)

    return (
        None if slope is None else round(slope, 6),
        None if r is None else round(r, 4),
        diurnal_fit,
        None if diurnal_r2 is None else round(diurnal_r2, 4),
        model,
    )


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

def find_within_session_gaps(ts_list, rows):
    """
    Scan one session's consecutive valid timestamps for gaps larger than
    GAP_BREAK_THRESHOLD_S. A single CSV file can stay open across a long
    logging interruption (e.g. the host PC sleeping) without ever closing —
    the file boundary alone can't reveal that, so this looks inside the file.

    For each gap, also reports how much the Arduino's own 'uptime_s' field
    advanced across the same two rows (when parseable). The Arduino runs on
    its own clock, independent of the host PC and Python process: if
    uptime_s advanced by roughly the same amount as the gap itself, the
    Arduino was also not measuring/idle for that stretch; if uptime_s barely
    moved while the PC clock jumped, the Arduino kept running fine and the
    interruption was purely on the host PC / logger side (e.g. the PC went
    to sleep and stopped reading the serial port, so the Arduino's readings
    during that window were generated but never captured).

    Returns a list of dicts: start (datetime), end (datetime), gap_s (float),
    arduino_uptime_delta_s (float | None).
    """
    gaps = []
    for j in range(1, len(ts_list)):
        t0, t1 = ts_list[j - 1], ts_list[j]
        if t0 is None or t1 is None:
            continue
        gap_s = (t1 - t0).total_seconds()
        if gap_s <= GAP_BREAK_THRESHOLD_S:
            continue
        uptime_delta = None
        try:
            uptime_delta = float(rows[j].get('uptime_s')) - float(rows[j - 1].get('uptime_s'))
        except (TypeError, ValueError):
            pass
        gaps.append({
            'start': t0,
            'end': t1,
            'gap_s': gap_s,
            'arduino_uptime_delta_s': uptime_delta,
        })
    return gaps


def load_study_files(study_dir):
    """
    Read every CSV in study_dir, normalise column names, and return a list of
    session dicts sorted by start timestamp.  Empty / unreadable files skipped.

    Each session dict:
      file            : filename
      start_dt        : first valid timestamp (datetime)
      end_dt          : last valid timestamp (datetime)
      duration_s      : seconds from first to last timestamp
      within_gaps     : list of gaps *inside* this file — see
                        find_within_session_gaps()
      within_gap_s    : total seconds covered by within_gaps (subtracted from
                        duration_s wherever "actually logged" time is needed)
      rows            : list of normalised row dicts
      ts_list         : parallel list of datetime | None per row
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

        within_gaps = find_within_session_gaps(ts_list, rows)

        sessions.append({
            'file':          fname,
            'start_dt':      min(valid_ts),
            'end_dt':        max(valid_ts),
            'duration_s':    (max(valid_ts) - min(valid_ts)).total_seconds(),
            'within_gaps':   within_gaps,
            'within_gap_s':  sum(g['gap_s'] for g in within_gaps),
            'rows':          rows,
            'ts_list':       ts_list,
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
        valid_pairs = []  # (datetime, float) — retained for trend/diurnal/model-fit regression
        bad_entries = []
        bad_reasons = defaultdict(int)

        for dt, val in entries:
            bad, reason = is_bad(col, val)
            if bad:
                bad_entries.append((dt, reason))
                bad_reasons[reason] += 1
            else:
                fval = float(val)
                valid_vals.append(fval)
                valid_pairs.append((dt, fval))

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

        (entry['slope_per_hour'], entry['trend_r'], entry['diurnal_fit'],
         entry['diurnal_r2'], entry['best_fit_model']) = compute_trend_stats(valid_pairs)

        stats[col] = entry

    return stats


# ── Chart data ────────────────────────────────────────────────────────────────

def build_chart_data(sessions):
    """
    Build downsampled time-series data for all chart groups across all sessions.

    Steps:
      1. Compute a global downsample step so total output ≤ MAX_CHART_POINTS.
      2. Within each session, take every step-th row.
      3. Insert a null-valued row wherever a known real gap (between
         sessions, or within one — see WITHIN-SESSION GAPS above) falls
         between two consecutive *kept* points, so Plotly shows a visible
         break instead of a connecting line. Real gaps are looked up from
         precomputed intervals rather than re-derived from the downsampled
         spacing itself: after thinning to every step-th row, consecutive
         kept points are naturally step * (sampling interval) apart — e.g.
         at a 64-row stride and a 3-5s sampling interval, ~200-300s — which
         can easily exceed GAP_BREAK_THRESHOLD_S on its own with no real
         interruption. Checking the downsampled delta directly would flag
         nearly every point as a break; checking against the actual known
         gap intervals instead avoids that.
      4. Produce a single shared x-timestamp array and per-trace y arrays
         (bad / out-of-range values become None → JSON null → Plotly gap).
      5. Only include chart groups and traces that have at least some valid data.

    Returns a dict ready for JSON serialisation.
    """
    total_rows = sum(len(s['rows']) for s in sessions)
    step = max(1, total_rows // MAX_CHART_POINTS)

    # Precompute every real gap (> GAP_BREAK_THRESHOLD_S) as a (start, end)
    # interval, from both between-session and within-session sources, sorted
    # by start. Used below to place breaks correctly regardless of the
    # downsampling stride.
    gap_intervals = []
    for i in range(1, len(sessions)):
        gap_s = (sessions[i]['start_dt'] - sessions[i - 1]['end_dt']).total_seconds()
        if gap_s > GAP_BREAK_THRESHOLD_S:
            gap_intervals.append((sessions[i - 1]['end_dt'], sessions[i]['start_dt']))
    for sess in sessions:
        for g in sess['within_gaps']:
            gap_intervals.append((g['start'], g['end']))
    gap_intervals.sort()

    # Downsample each session independently, then concatenate in order.
    flat = []
    for sess in sessions:
        pairs = [
            (dt, row)
            for dt, row in zip(sess['ts_list'], sess['rows'])
            if dt is not None
        ]
        flat.extend(pairs[::step])

    # Single pass: insert a None separator between consecutive *kept*
    # points whenever a known gap interval starts inside that span. A
    # two-pointer sweep works because both flat (by construction) and
    # gap_intervals (sorted above) are in chronological order.
    flat_with_breaks = []
    prev_dt = None
    gi, n_gaps = 0, len(gap_intervals)
    for dt, row in flat:
        if prev_dt is not None:
            while gi < n_gaps and gap_intervals[gi][1] <= prev_dt:
                gi += 1
            if gi < n_gaps and prev_dt <= gap_intervals[gi][0] < dt:
                flat_with_breaks.append((prev_dt, None))  # separator
        flat_with_breaks.append((dt, row))
        prev_dt = dt
    flat = flat_with_breaks

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
    """
    Return text of the study's description file, or None if absent.
    Looks for description.txt first, then falls back to any description*.txt
    (e.g. description_001.txt) so per-session numbered description files work too.
    """
    candidates = [os.path.join(study_dir, 'description.txt')]
    candidates += sorted(glob.glob(os.path.join(study_dir, 'description*.txt')))
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as fh:
                text = fh.read().strip()
            if text:
                return text
    return None


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
                f"Mean humidity was high ({mean_h:.0f}% RH), expected inside a substrate "
                f"bag where evaporation and fungal respiration raise moisture levels."
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
        wall_s      = (sessions[-1]['end_dt'] - sessions[0]['start_dt']).total_seconds()
        within_gap_s = sum(s['within_gap_s'] for s in sessions)
        logged_s    = sum(s['duration_s'] for s in sessions) - within_gap_s
        coverage    = logged_s / wall_s if wall_s > 0 else 1.0
        n           = len(sessions)
        n_within_gaps = sum(len(s['within_gaps']) for s in sessions)
        if coverage > 0.9 and n_within_gaps == 0:
            bullets.append(
                f"Logging coverage was continuous: {coverage * 100:.0f}% of the "
                f"{wall_s / 3600:.1f} h experiment span captured across {n} session(s)."
            )
        else:
            gap_h = (wall_s - logged_s) / 3600
            within_note = ""
            if n_within_gaps:
                within_h = within_gap_s / 3600
                within_note = (
                    f" {n_within_gaps} of those gap(s) occurred *inside* an otherwise "
                    f"continuous session file (~{within_h:.1f} h total) — the logger process "
                    f"stayed running the whole time but stopped capturing data for a stretch, "
                    f"most consistent with the host PC sleeping or the serial connection "
                    f"stalling, not the Arduino itself resetting (check each gap's "
                    f"arduino_uptime_delta_s in the timeline data: a small delta despite a "
                    f"large gap means the Arduino kept running fine throughout)."
                )
            bullets.append(
                f"Logging ran across {n} session(s) with ~{gap_h:.1f} h of gaps "
                f"in a {wall_s / 3600:.1f} h window ({coverage * 100:.0f}% coverage)."
                f"{within_note} Gaps between separate session files likely reflect "
                f"equipment restarts or deliberate pauses between experimental phases."
            )

    # ── Temperature-pressure relationship text ────────────────────────────
    if tc and pc:
        mean_p  = ps['mean']
        range_p = ps['range']
        dev     = abs(mean_p - 1013.25)

        p1 = (
            f"Pressure is governed by local atmospheric conditions rather than substrate "
            f"temperature or activity. "
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
    overall_start   = sessions[0]['start_dt']
    overall_end     = sessions[-1]['end_dt']
    wall_clock_s    = (overall_end - overall_start).total_seconds()
    total_within_gap_s = sum(s['within_gap_s'] for s in sessions)
    # "Logged" time excludes within-session gaps: a session's duration_s
    # spans first-to-last timestamp in the file, but any within_gaps inside
    # that span were not actually captured (see find_within_session_gaps).
    total_logged_s = sum(s['duration_s'] for s in sessions) - total_within_gap_s

    session_summaries = []
    for s in sessions:
        all_cols    = set(col for row in s['rows'] for col in row)
        sensor_cols = sorted(
            c for c in all_cols
            if c not in SKIP_STATS and c != 'timestamp' and not c.startswith('arduino_')
        )
        session_summaries.append({
            'file':          s['file'],
            'start':         s['start_dt'].strftime('%Y-%m-%d %H:%M:%S'),
            'end':           s['end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
            'duration_s':    int(s['duration_s']),
            'within_gap_s':  int(s['within_gap_s']),
            'rows':          len(s['rows']),
            'sensors':       sensor_cols,
        })

    gaps = []
    for i in range(1, len(sessions)):
        gap_s = (sessions[i]['start_dt'] - sessions[i - 1]['end_dt']).total_seconds()
        if gap_s > SESSION_GAP_MIN_S:
            gaps.append({
                'type':        'between_sessions',
                'after_file':  sessions[i - 1]['file'],
                'before_file': sessions[i]['file'],
                'gap_start':   sessions[i - 1]['end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                'gap_end':     sessions[i]['start_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                'gap_s':       int(gap_s),
                'gap_minutes': round(gap_s / 60, 1),
                'gap_hours':   round(gap_s / 3600, 2),
            })
    for s in sessions:
        for g in s['within_gaps']:
            gaps.append({
                'type':                    'within_session',
                'file':                    s['file'],
                'gap_start':               g['start'].strftime('%Y-%m-%d %H:%M:%S'),
                'gap_end':                 g['end'].strftime('%Y-%m-%d %H:%M:%S'),
                'gap_s':                   int(g['gap_s']),
                'gap_minutes':             round(g['gap_s'] / 60, 1),
                'gap_hours':               round(g['gap_s'] / 3600, 2),
                'arduino_uptime_delta_s':  g['arduino_uptime_delta_s'],
            })
    gaps.sort(key=lambda g: g['gap_start'])

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

    print(f'  {len(sessions)} sessions, {int(total_logged_s):,} s logged, '
          f'{len(gaps)} gap(s) ({int(total_within_gap_s):,} s within-session)')
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
