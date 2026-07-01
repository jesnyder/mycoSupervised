import serial
import time
import csv
from datetime import datetime

SERIAL_PORT = "COM4"
BAUD_RATE = 115200

start_time = time.time()

filename = "SHIT30_BME688_" + datetime.now().strftime("%Y%m%d%H%M") + ".csv"

print("Logging to:", filename)

with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
    time.sleep(2)

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)

        # =====================================================
        # UPDATED HEADER (MATCHS NEW ARDUINO OUTPUT)
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

            "stepper_speed_pct",
            "pump_speed_pct",
            "pump_state"
        ])

        print("Logging started...")
        print("-" * 110)

        while True:
            try:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                parts = line.split(",")

                # EXPECT 15 COLUMNS FROM ARDUINO
                if len(parts) < 15:
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

                    stepper = float(parts[13])
                    pump    = float(parts[14])
                    state   = parts[15]

                except ValueError:
                    continue

                pc_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                elapsed = round(time.time() - start_time, 2)

                writer.writerow([
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

                    stepper,
                    pump,
                    state
                ])

                f.flush()

                print(
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
                    stepper,
                    pump,
                    state
                )

            except KeyboardInterrupt:
                print("Stopped.")
                break

            except Exception as e:
                print("Error:", e)