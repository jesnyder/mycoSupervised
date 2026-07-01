"""
===========================================================
MULTI-SENSOR REACTOR DATA LOGGER (UPDATED)
Date: 2026-06-16
===========================================================

DESCRIPTION
-----------
This script logs serial CSV data from an Arduino-based
multi-sensor reactor system including:

- SHT30 (Temp/Humidity)
- 2x BME688 (Env + gas sensing)
- AS7341 spectral light sensor (DFRobot Gravity)
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
- Rejects lines that do not have exactly 22 columns
- Skips non-CSV Arduino startup text
- Prevents "incomplete packet" errors
- Always prints valid rows to terminal
"""

import serial
import time
import csv
from datetime import datetime

# =====================================================
# CONFIG
# =====================================================

SERIAL_PORT = "COM4"
BAUD_RATE = 115200

start_time = time.time()

filename = "REACTOR_SHT30_BME688_AS7341_" + datetime.now().strftime("%Y%m%d_%H%M") + ".csv"

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

                # MUST BE EXACTLY 22 FIELDS
                if len(parts) != 22:
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
                    clear = float(parts[17])
                    nir = float(parts[18])

                    stepper = float(parts[19])
                    pump = float(parts[20])
                    state = parts[21]

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

                    f1, f2, f3, f4, clear, nir,

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
                    "AS7341:", f1, f2, f3, f4, clear, nir,
                    "Pump:", pump, state
                )

            except KeyboardInterrupt:
                print("\nStopped by user.")
                break

            except Exception as e:
                print("ERROR:", e)
