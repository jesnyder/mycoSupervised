"""
===========================================================
MULTI-SENSOR REACTOR DATA LOGGER (UPDATED)
Date: 2026-07-08
===========================================================

DESCRIPTION
-----------
This script logs serial CSV data from an Arduino-based
multi-sensor reactor system including:

- SHT30 (Temp/Humidity)
- 2x BME688 (Env + gas sensing)
- AS7341 spectral light sensor (DFRobot Gravity) - full 8-channel
  spectrum (F1-F8) + CLEAR + NIR, read via both DFRobot_AS7341
  measurement modes each logging cycle (see 01_stepper_motor.ino)
- Pump + system state

It safely handles:
- startup noise
- incomplete serial packets
- malformed CSV lines

OUTPUT
------
CSV file with timestamped environmental + spectral data
and real-time terminal echo.

IMPORTANT FIXES
---------------
- Rejects lines that do not have exactly 26 columns
- Skips non-CSV Arduino startup text
- Prevents "incomplete packet" errors
- Always prints valid rows to terminal

SCHEMA NOTE
-----------
As of 2026-07-08 the firmware reads both AS7341 measurement modes each
cycle, so this logger now emits 8 spectral channels (as7341_f1..f8)
instead of the previous 4 (as7341_f1..f4). CSVs collected before this
date have 24 columns (22 Arduino fields); CSVs collected after have 28
(26 Arduino fields). generate_study_summaries.py handles both schemas
automatically per-file - see its Schema D / Schema E documentation.
"""

import os
import serial
import time
import csv
from datetime import datetime

# =====================================================
# CONFIG
# =====================================================

SERIAL_PORT = "COM6"       # Windows: "COM4" / Linux: "/dev/ttyUSB0"
BAUD_RATE   = 115200

# ── Output directory ──────────────────────────────────────────────────────────
# Set STUDY_NAME to route CSVs to the correct studies/ subfolder so that
# build.sh (and generate_study_summaries.py) can find them automatically.
# Path is resolved relative to this script: 3 levels up → repo root → studies/
STUDY_NAME  = 'study001_pilot'
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT  = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..'))
OUTPUT_DIR  = os.path.join(_REPO_ROOT, 'studies', STUDY_NAME)
os.makedirs(OUTPUT_DIR, exist_ok=True)

start_time = time.time()

filename = os.path.join(
    OUTPUT_DIR,
    f"REACTOR_SHT30_BME688_AS7341_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
)

print("Logging to:", filename)

# =====================================================
# SERIAL + FILE
# =====================================================

with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
    time.sleep(2)  # allow Arduino reset

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)

        # =====================================================
        # CSV HEADER (MATCH ARDUINO EXACTLY)
        # =====================================================
        writer.writerow([
            "pc_timestamp",
            "elapsed_s",

            "arduino_date",
            "arduino_time",
            "uptime_s",

            "sht30_temp_C",
            "sht30_humidity_pct",

            "bme688_1_temp_C",
            "bme688_1_humidity_pct",
            "bme688_1_pressure_hpa",
            "bme688_1_gas_ohms",

            "bme688_2_temp_C",
            "bme688_2_humidity_pct",
            "bme688_2_pressure_hpa",
            "bme688_2_gas_ohms",

            "as7341_f1",
            "as7341_f2",
            "as7341_f3",
            "as7341_f4",
            "as7341_f5",
            "as7341_f6",
            "as7341_f7",
            "as7341_f8",
            "as7341_clear",
            "as7341_nir",

            "stepper_speed_pct",
            "pump_speed_pct",
            "pump_state"
        ])

        print("Logging started...\n")
        print("-" * 120)

        # =====================================================
        # MAIN LOOP
        # =====================================================
        while True:
            try:
                line = ser.readline().decode(errors="ignore").strip()

                # skip empty lines
                if not line:
                    continue

                # skip Arduino startup messages
                if "SYSTEM START" in line or "===== " in line:
                    continue

                parts = line.split(",")

                # MUST BE EXACTLY 26 FIELDS
                if len(parts) != 26:
                    print("SKIP (bad packet length):", len(parts), "->", line)
                    continue

                try:
                    arduino_date = parts[0]
                    arduino_time = parts[1]
                    uptime_s     = float(parts[2])

                    sht_temp = float(parts[3])
                    sht_hum  = float(parts[4])

                    b1_t = float(parts[5])
                    b1_h = float(parts[6])
                    b1_p = float(parts[7])
                    b1_g = float(parts[8])

                    b2_t = float(parts[9])
                    b2_h = float(parts[10])
                    b2_p = float(parts[11])
                    b2_g = float(parts[12])

                    f1 = float(parts[13])
                    f2 = float(parts[14])
                    f3 = float(parts[15])
                    f4 = float(parts[16])
                    f5 = float(parts[17])
                    f6 = float(parts[18])
                    f7 = float(parts[19])
                    f8 = float(parts[20])
                    clear = float(parts[21])
                    nir = float(parts[22])

                    stepper = float(parts[23])
                    pump = float(parts[24])
                    state = parts[25]

                except ValueError:
                    print("SKIP (parse error):", line)
                    continue

                pc_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                elapsed = round(time.time() - start_time, 2)

                row = [
                    pc_timestamp,
                    elapsed,

                    arduino_date,
                    arduino_time,
                    uptime_s,

                    sht_temp,
                    sht_hum,

                    b1_t,
                    b1_h,
                    b1_p,
                    b1_g,

                    b2_t,
                    b2_h,
                    b2_p,
                    b2_g,

                    f1, f2, f3, f4, f5, f6, f7, f8, clear, nir,

                    stepper,
                    pump,
                    state
                ]

                writer.writerow(row)
                f.flush()

                # =================================================
                # TERMINAL OUTPUT (CLEAN + ALWAYS PRINTS)
                # =================================================
                print(
                    pc_timestamp,
                    "uptime:", uptime_s,
                    "T:", sht_temp,
                    "RH:", sht_hum,
                    "B1:", b1_t, b1_h, b1_p, b1_g,
                    "B2:", b2_t, b2_h, b2_p, b2_g,
                    "AS7341:", f1, f2, f3, f4, f5, f6, f7, f8, clear, nir,
                    "Pump:", pump, state
                )

            except KeyboardInterrupt:
                print("\nStopped by user.")
                break

            except Exception as e:
                print("ERROR:", e)
