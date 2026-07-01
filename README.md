# astroPharmReactor

**Last updated: 2026-06-17**

An Arduino-based bioreactor environmental monitoring system for pharmaceutical microbiology research. The system continuously logs multi-sensor environmental data during bacterial culture experiments (currently E. coli), and controls a peristaltic pump and stepper motor for media flow and agitation.

---

## Session Checkpoint

Use this section to resume work. At the start of a new session, ask Claude to read this README.

**Current status (2026-06-17):** Two E. coli pilot studies complete (study001, study002). The AS7341 spectral light sensor was added during Study 002. The main logger script (`logging_sht30_bme688_bme688_as7341.py`) is the current working version — it reads all four sensors and logs 24-column CSV files. Recent commits added the light sensor and example log outputs. The system is in active use and being refined between studies.

**Open threads / next steps to discuss:**
- (add notes here as discussions happen)

---

## Objective

Monitor and log environmental conditions inside a bioreactor over extended experimental runs. Sensor data (temperature, humidity, pressure, volatile organic compounds, and spectral light) is streamed from an Arduino over serial and saved to timestamped CSV files by a Python logger running on a host PC. The goal is pharmaceutical-grade microbial culture monitoring with a reproducible, extensible sensor stack.

---

## Hardware

### Microcontroller
- **Arduino** (serial at 115200 baud, no RTC — timestamps are assigned by the host PC)

### Sensors (I2C bus)

| Sensor | I2C Address | Measurements |
|--------|-------------|-------------|
| SHT30 Temperature & Humidity | 0x44 | Temperature (°C), Relative Humidity (%RH) |
| BME688 #1 Gas/Environmental | 0x76 (SDO → GND) | Temperature, Humidity, Pressure (hPa), Gas Resistance (Ω) |
| BME688 #2 Gas/Environmental | 0x77 (SDO → VCC) | Temperature, Humidity, Pressure (hPa), Gas Resistance (Ω) |
| AS7341 Spectral Light (DFRobot Gravity) | 0x39 | F1 Blue, F2 Cyan, F3 Green, F4 Yellow, CLEAR, NIR |

The two BME688 sensors are differentiated by the state of their SDO pin: BME688 #1 has SDO pulled to GND (address 0x76) and BME688 #2 has SDO pulled to VCC/3.3V (address 0x77). This allows two identical sensors on the same I2C bus.

### Actuators

| Actuator | Pin(s) | Notes |
|----------|--------|-------|
| Peristaltic Pump | PWM Pin 5 | Configurable duty cycle; default 10 min ON / 1 min OFF |
| Stepper Motor | Step: Pin 2, Dir: Pin 3 | Mixing/agitation |

---

## Software

### Arduino Firmware

**File:** `user_provided/arduino/01_stepper_motor/01_stepper_motor.ino`  
Written in C/C++. Reads all sensors every second and streams comma-separated values over serial at 115200 baud. Controls pump duty cycle timing and stepper motor speed. No real-time clock — Arduino timestamps are millis() since boot; absolute timestamps are added by the Python logger.

**Required Arduino libraries:**
- `Wire` (built-in)
- `Adafruit_SHT31`
- `Adafruit_BME680`
- `DFRobot_AS7341`

### Python Data Loggers

**Location:** `user_provided/arduino/01_stepper_motor/` (run from here alongside the Arduino .ino)  
**Archived copies:** `user_provided/python/archive/`

Python scripts open the Arduino serial port, parse incoming CSV lines, prepend a PC timestamp and elapsed time, and write rows directly to the correct `studies/` subfolder. Scripts handle malformed packets and Arduino startup noise gracefully and print live sensor values to the terminal.

| Script | Sensors Logged | Used In |
|--------|----------------|---------|
| `logging_sht30.py` | SHT30 + 1× BME688 | Study 001 |
| `logging_sht30_bme688_bme688.py` | SHT30 + 2× BME688 | Study 002 early runs |
| `logging_sht30_bme688_bme688_as7341.py` | SHT30 + 2× BME688 + AS7341 | Study 002 current |

The current full-sensor logger outputs **24-column CSV files**: PC timestamp, elapsed time, SHT30 (temp, humidity), BME688 #1 (temp, humidity, pressure, gas resistance), BME688 #2 (same), AS7341 (F1–F4, CLEAR, NIR), stepper speed, pump speed, pump state.

**Output path** — controlled by two variables at the top of each script:
```python
SERIAL_PORT = "COM4"          # Windows: "COM4"  |  Linux: "/dev/ttyUSB0"
STUDY_NAME  = 'study002_ecoli'  # routes CSV output to studies/study002_ecoli/
```
The script resolves the absolute path to `studies/STUDY_NAME/` automatically and creates the folder if it does not exist. Running `build.sh` after a session will pick up the new CSV immediately.

**Python dependencies:** `pyserial`

### Website / Data Pipeline

**`user_provided/python/generate_study_summaries.py`** — Reads all CSV files from `studies/study*/`, normalises column names across five historical schema versions, filters bad/saturated sensor values, downsamples to ~4 000 points per study, and writes one JS file per study to `docs/js/`.

Each generated JS file exports two globals consumed by `docs/index.html`:

| Global | Contents |
|--------|----------|
| `window.STUDY_SUMMARIES["study_name"]` | Experiment description (from `description.txt`), timeline (sessions, gaps, wall-clock, logged hours), per-variable stats (min/max/range/mean, bad-row count, bad-data windows), auto-generated interpretation (temp-pressure text + result bullets) |
| `window.STUDY_CHARTS["study_name"]` | Shared x-timestamps, downsampled y arrays per sensor trace (null = bad data or session gap), grouped by measurement unit (temperature, humidity, pressure, gas, light) |

**`docs/index.html`** — Static single-page dashboard. No server required. Libraries:
- **[Plotly.js](https://plotly.com/javascript/)** — session Gantt timeline, bad-data bar chart, dual-axis Temperature + Pressure chart, per-group time-series charts, live CSV drop visualizer
- **[Tabulator v6](https://tabulator.info/)** — sortable / downloadable tables for sensors, actuators, logger scripts, and per-study variable statistics

**`user_provided/makefile/build.sh`** — Runs the Python pipeline then opens `docs/index.html` in the browser.

```bash
bash user_provided/makefile/build.sh
```

### Running the Logger

1. Upload `01_stepper_motor.ino` to the Arduino via Arduino IDE.
2. Connect the Arduino via USB and confirm the serial port (`/dev/ttyUSB0` on Linux, `COM3`/`COM4` on Windows).
3. Edit `SERIAL_PORT` and `STUDY_NAME` at the top of the logging script if needed.
4. Run from `user_provided/arduino/01_stepper_motor/`:
   ```bash
   python logging_sht30_bme688_bme688_as7341.py
   ```
5. CSVs are written directly to `studies/study002_ecoli/` (or whichever study is set).
6. After a session, run `bash user_provided/makefile/build.sh` to update the dashboard.

### Adding experiment notes

Place a `description.txt` file in the study folder to add a description that appears at the top of the study block on the website:
```
studies/study002_ecoli/description.txt
```
Plain text, any length. Run `build.sh` to include it in the dashboard.

---

## Data

Logged CSV files are organized by study under `studies/` at the repo root:

```
studies/
├── study001_ecoli/    — Pilot study 1 (SHT30 → SHT30 + BME688)
└── study002_ecoli/    — Pilot study 2 (SHT30 + 2× BME688 → + AS7341)
```

Study 001: 12 sessions, ~111 hours logged. Study 002: 9 sessions, ~23 hours logged.  
The website pipeline reads from `studies/` — copy or move completed sessions here to include them in the dashboard.

---

## Git History Summary

| Commit | Description |
|--------|-------------|
| 4f243f0 | Added AS7341 light sensor and example log outputs |
| 8c48146 | Added light sensor (initial integration) |
| d19c50d | Uploaded Study 002 day 1 data |
| 5f4460e | Updated pump cycle to 10-minute ON time |
| 11ea7b1 | Updated logging for dual BME688 configuration |
