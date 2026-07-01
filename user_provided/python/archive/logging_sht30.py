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

        writer.writerow([
            "timestamp",
            "elapsed_s",

            "sht30_temp_C",
            "sht30_humidity_pct",

            "bme688_temp_C",
            "bme688_humidity_pct",
            "bme688_pressure_hpa",
            "bme688_gas_ohms",

            "motor_speed_pct"
        ])

        print("time | elapsed | SHT30_T | SHT30_H | BME_T | BME_H | BME_P | BME_G | SPEED")
        print("-" * 100)

        while True:
            try:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                parts = line.split(",")

                # EXPECT 8 VALUES FROM ARDUINO
                if len(parts) < 8:
                    continue

                try:
                    t_ms = float(parts[0])

                    sht_temp = float(parts[1])
                    sht_hum  = float(parts[2])

                    bme_temp = float(parts[3])
                    bme_hum  = float(parts[4])
                    bme_press = float(parts[5])
                    bme_gas  = float(parts[6])

                    speed = float(parts[7])

                except ValueError:
                    continue

                elapsed = round(time.time() - start_time, 2)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                writer.writerow([
                    timestamp,
                    elapsed,

                    sht_temp,
                    sht_hum,

                    bme_temp,
                    bme_hum,
                    bme_press,
                    bme_gas,

                    speed
                ])

                f.flush()

                print(
                    timestamp,
                    elapsed,
                    sht_temp,
                    sht_hum,
                    bme_temp,
                    bme_hum,
                    bme_press,
                    bme_gas,
                    speed
                )

            except KeyboardInterrupt:
                print("Stopped.")
                break

            except Exception as e:
                print("Error:", e)