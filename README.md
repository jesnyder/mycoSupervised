# mycoSupervised

**Last updated: 2026-06-30**

An Arduino-based environmental monitoring system for observing fungal growth through a solid substrate. The system continuously logs multi-sensor environmental data (temperature, humidity, pressure, VOC proxy, and spectral light) from a liquid fungal culture inoculated into a bag of sterile substrate.

This repo previously hosted **astroPharmReactor**, an E. coli bioreactor monitoring project. It has been repurposed for fungal substrate colonization studies; the historical bacterial studies and their generated dashboard data have been removed.

---

## Session Checkpoint

Use this section to resume work. At the start of a new session, ask Claude to read this README.

**Current status (2026-06-30):** Study 001 (pilot) just started — a liquid culture of fungus was inoculated into a bag of sterile substrate and outfitted with sensors at 5:00pm. Two short logging sessions exist so far (~10 minutes total). The sensor stack and logging scripts are unchanged from the prior project; only the organism, vessel, and sensor placement have changed. Stepper motor and pump remain wired but idle — this is a passive substrate monitoring setup, not an actively mixed liquid culture.

**Open threads / next steps to discuss:**
- (add notes here as discussions happen)

---

## Objective

Monitor and log environmental conditions in and around a fungus-inoculated substrate bag over an extended colonization period. Sensor data (temperature, humidity, pressure, volatile organic compounds via gas resistance, and spectral light) is streamed from an Arduino over serial and saved to timestamped CSV files by a Python logger running on a host PC. The goal is to build a low-cost, reproducible sensor stack for tracking substrate colonization — using temperature/humidity/VOC changes as proxies for fungal metabolic activity, and light transmission through the bag as a proxy for mycelial density.

**Study 001 (pilot)** — a liquid culture of fungus was inoculated into a bag of sterile substrate and instrumented on 2026-06-30 at 5:00pm:
- SHT30 and BME688 #1 sit **outside the bag**, on the table next to it, measuring **ambient room conditions**.
- BME688 #2 sits **inside the bag**, in contact with the substrate headspace.
- The AS7341 light sensor sits **under the bag**, illuminated from above with a light strong enough to max out the sensor (1000 across all channels) if the bag were not there — so the bag's own light attenuation is the signal of interest. As mycelium colonizes the substrate and the bag interior turns opaque with growth, transmitted light reaching the sensor is expected to decrease.

---

## Hardware

### Microcontroller
- **Arduino** (serial at 115200 baud, no RTC — timestamps are assigned by the host PC)

### Sensors (I2C bus)

| Sensor | I2C Address | Measurements | Placement (Study 001) |
|--------|-------------|-------------|-------------|
| SHT30 Temperature & Humidity | 0x44 | Temperature (°C), Relative Humidity (%RH) | Outside the bag (ambient) |
| BME688 #1 Gas/Environmental | 0x76 (SDO → GND) | Temperature, Humidity, Pressure (hPa), Gas Resistance (Ω) | Outside the bag (ambient) |
| BME688 #2 Gas/Environmental | 0x77 (SDO → VCC) | Temperature, Humidity, Pressure (hPa), Gas Resistance (Ω) | Inside the bag |
| AS7341 Spectral Light (DFRobot Gravity) | 0x39 | F1 Blue, F2 Cyan, F3 Green, F4 Yellow, CLEAR, NIR | Under the bag, strongly illuminated from above |

The two BME688 sensors are differentiated by the state of their SDO pin: BME688 #1 has SDO pulled to GND (address 0x76) and BME688 #2 has SDO pulled to VCC/3.3V (address 0x77). This allows two identical sensors on the same I2C bus — one outside the bag as an ambient baseline, one inside the bag against the substrate.

### Actuators

| Actuator | Pin(s) | Notes |
|----------|--------|-------|
| Peristaltic Pump | PWM Pin 5 | Wired but idle for Study 001 (passive substrate, no liquid feed) |
| Stepper Motor | Step: Pin 2, Dir: Pin 3 | Wired but idle for Study 001 (no agitation of a solid substrate) |

---

## Software

### Arduino Firmware

**File:** `user_provided/arduino/01_stepper_motor/01_stepper_motor.ino`  
Written in C/C++. Reads all sensors and streams comma-separated values over serial at 115200 baud every 3 seconds. Controls pump duty cycle timing and stepper motor speed (unused in Study 001). No real-time clock — Arduino timestamps are millis() since boot; absolute timestamps are added by the Python logger.

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
| `logging_sht30.py` | SHT30 + 1× BME688 | (historical, prior project) |
| `logging_sht30_bme688_bme688.py` | SHT30 + 2× BME688 | (historical, prior project) |
| `logging_sht30_bme688_bme688_as7341.py` | SHT30 + 2× BME688 + AS7341 | Study 001 |

The current full-sensor logger outputs **24-column CSV files**: PC timestamp, elapsed time, SHT30 (temp, humidity), BME688 #1 (temp, humidity, pressure, gas resistance), BME688 #2 (same), AS7341 (F1–F4, CLEAR, NIR), stepper speed, pump speed, pump state.

**Output path** — controlled by two variables at the top of each script:
```python
SERIAL_PORT = "COM4"          # Windows: "COM4"  |  Linux: "/dev/ttyUSB0"
STUDY_NAME  = 'study001_pilot'  # routes CSV output to studies/study001_pilot/
```
The script resolves the absolute path to `studies/STUDY_NAME/` automatically and creates the folder if it does not exist. Running `build.sh` after a session will pick up the new CSV immediately.

**Python dependencies:** `pyserial`

### Website / Data Pipeline

**`user_provided/python/generate_study_summaries.py`** — Reads all CSV files from `studies/study*/`, normalises column names across historical schema versions, filters bad/saturated sensor values, downsamples to ~4 000 points per study, and writes one JS file per study to `docs/js/`.

Each generated JS file exports two globals consumed by that study's own page (e.g. `docs/study001_pilot.html`):

| Global | Contents |
|--------|----------|
| `window.STUDY_SUMMARIES["study_name"]` | Experiment description (from `description_001.txt`), timeline (sessions, gaps, wall-clock, logged hours), per-variable stats (min/max/range/mean, bad-row count, bad-data windows), auto-generated interpretation (temp-pressure text + result bullets) |
| `window.STUDY_CHARTS["study_name"]` | Shared x-timestamps, downsampled y arrays per sensor trace (null = bad data or session gap), grouped by measurement unit (temperature, humidity, pressure, gas, light) |

The site is a small static multi-page dashboard, navigated via a left sidebar. No server required.
- **`docs/index.html`** — the About page: objective, hardware, wiring, software, and sensor physics reference. Does not load any study data.
- **`docs/study001_pilot.html`** — Study 001's dedicated analysis page: description, timeline, variable stats, time-series charts, weather overlay, cross-correlation scatter plots, and data export, all rendered from `docs/js/study001_pilot.js`. Each future study gets its own page in the same pattern, linked from the sidebar.

Libraries:
- **[Plotly.js](https://plotly.com/javascript/)** — session Gantt timeline, bad-data bar chart, dual-axis Temperature + Pressure chart, per-group time-series charts (study pages only)
- **[Tabulator v6](https://tabulator.info/)** — sortable / downloadable tables for sensors, wiring, actuators, logger scripts (About page), and per-study variable statistics (study pages)

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
5. CSVs are written directly to `studies/study001_pilot/` (or whichever study is set).
6. After a session, run `bash user_provided/makefile/build.sh` to update the dashboard.

### Adding experiment notes

Place a `description_001.txt`-style plain-text file in the study folder to add a description that appears at the top of the study block on the website:
```
studies/study001_pilot/description_001.txt
```
Plain text, any length. Run `build.sh` to include it in the dashboard.

---

## Data

Logged CSV files are organized by study under `studies/` at the repo root:

```
studies/
└── study001_pilot/    — Pilot study: fungal culture inoculated into a sterile substrate bag
```

Study 001 started 2026-06-30; sensors were just deployed and logging is ongoing.  
The website pipeline reads from `studies/` — copy or move completed sessions here to include them in the dashboard.

---

## Git History Summary

| Commit | Description |
|--------|-------------|
| 0d62d85 | study001 updated |
| 8c1db2e | first comit |
| a6548ee | Initial commit |
