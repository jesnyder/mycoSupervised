/*
===========================================================
MULTI-SENSOR REACTOR LOGGING SYSTEM
Date: 2026-06-16
===========================================================

DESCRIPTION
-----------
This Arduino system logs environmental, chemical, and optical
data from multiple I2C sensors and a peristaltic pump system.
Data is streamed via Serial in CSV format for Python logging.

SENSORS INCLUDED
-----------------

1) SHT30 Temperature & Humidity Sensor
   - Library: Adafruit_SHT31
   - Address: 0x44
   - Measurements:
       Temperature (°C)
       Humidity (%RH)

2) BME688 #1 (Environmental Gas Sensor)
   - Library: Adafruit_BME680
   - Address: 0x76
   - Measurements:
       Temperature (°C)
       Humidity (%RH)
       Pressure (hPa)
       Gas resistance (ohms, VOC indicator)

3) BME688 #2 (Environmental Gas Sensor)
   - Library: Adafruit_BME680
   - Address: 0x77
   - Measurements:
       Temperature (°C)
       Humidity (%RH)
       Pressure (hPa)
       Gas resistance (ohms, VOC indicator)

4) AS7341 Spectral Light Sensor (DFRobot Gravity)
   - Library: DFRobot_AS7341
   - Address: 0x39
   - Measurements (raw ADC counts):
       F1 (Blue band)
       F2 (Cyan band)
       F3 (Green band)
       F4 (Yellow band)
       CLEAR (broad visible light)
       NIR (near-infrared)

5) Peristaltic Pump
   - PWM Pin: 5
   - Measurements:
       Pump speed (% duty cycle)
       Pump state (ON/OFF)
       Cycle timing (ON/OFF intervals in minutes)

-----------------------------------------------------------

I2C SUMMARY (from scanner)
--------------------------
0x39 → AS7341 spectral sensor
0x44 → SHT30 temperature/humidity
0x76 → BME688 #1
0x77 → BME688 #2

-----------------------------------------------------------

REQUIRED LIBRARIES (INSTALL IN ARDUINO IDE)
-------------------------------------------
1. Adafruit SHT31 Library
2. Adafruit BME680 Library
3. DFRobot AS7341 Library

Wire.h is built-in.

-----------------------------------------------------------

SYSTEM BEHAVIOR
----------------
- Logs every 3 seconds
- Generates timestamp from internal millis() clock
- Controls pump using ON/OFF cycle timing
- Reads all sensors sequentially
- Outputs CSV line over Serial for Python capture

PUMP SERIAL CONTROL
--------------------
- Send "P<value>" over Serial to set pump speed (0-100%)
- Examples:
    P0    → pump off
    P50   → half speed
    P100  → full speed
- Takes effect immediately; persists until next command
- Only applies when pump cycle state is ON

-----------------------------------------------------------

IMPORTANT LEARNINGS (FROM DEBUGGING)
------------------------------------
1. AS7341 library versions differ significantly:
   - Struct fields are NOT consistent across versions
   - Correct approach is pointer-based access:
       uint16_t* ch = (uint16_t*)&data;

2. DFRobot AS7341 API:
   - startMeasure() requires mode argument
   - readSpectralDataOne() returns struct, not channel calls

3. Pump logic must explicitly reset state or it can "stick off"

4. I2C multi-device systems require correct addressing (0x76/0x77)

===========================================================
*/

#include <Wire.h>
#include <Adafruit_SHT31.h>
#include <Adafruit_BME680.h>
#include "DFRobot_AS7341.h"

// =====================================================
// TIME BASE (NO RTC)
// =====================================================

unsigned long startMillis = 0;

int startYear  = 2026;
int startMonth = 6;
int startDay   = 18;
int startHour  = 12;
int startMin   = 0;
int startSec   = 0;

// =====================================================
// SENSORS
// =====================================================

Adafruit_SHT31 sht30;

// BME688 #1 (0x76)
Adafruit_BME680 bme688_1;

// BME688 #2 (0x77)
Adafruit_BME680 bme688_2;

// AS7341 light sensor
DFRobot_AS7341 as7341;

// =====================================================
// PUMP
// =====================================================

const int PUMP_PIN = 5;

int pumpSpeedPercent = 0;
bool pumpEnabled = false;

float PUMP_ON_TIME_MIN  = 0.0;
float PUMP_OFF_TIME_MIN = 1000.0;

unsigned long pumpCycleStart = 100;
bool pumpCycleState = true;

// =====================================================
// STEPPER
// =====================================================

const int STEP_PIN = 2;
const int DIR_PIN  = 3;

int speedPercent = 0;

// =====================================================
// TIMING
// =====================================================

unsigned long lastLog = 0;

// =====================================================
// SERIAL INPUT BUFFER
// =====================================================

String serialBuffer = "";

// =====================================================
// TIME HELPERS
// =====================================================

String two(int v) {
  if (v < 10) return "0" + String(v);
  return String(v);
}

void getDateTime(unsigned long ms, String &dateStr, String &timeStr) {

  unsigned long s = ms / 1000;

  int sec  = (startSec + s) % 60;
  int min  = (startMin + (startSec + s) / 60) % 60;
  int hour = (startHour + (startMin + (startSec + s) / 60) / 60) % 24;

  unsigned long days = (startHour + (startMin + (startSec + s) / 60) / 60) / 24;

  int day = startDay + days;

  dateStr = String(startYear) + "-" + two(startMonth) + "-" + two(day);
  timeStr = two(hour) + ":" + two(min) + ":" + two(sec);
}

// =====================================================
// SERIAL COMMAND HANDLER
// =====================================================

void handleSerialCommand(String cmd) {
  cmd.trim();

  if (cmd.length() >= 2 && cmd.charAt(0) == 'P') {
    String valStr = cmd.substring(1);
    int val = valStr.toInt();

    if (val < 0)   val = 0;
    if (val > 100) val = 100;

    pumpSpeedPercent = val;

    Serial.print("# PUMP SPEED SET TO: ");
    Serial.print(pumpSpeedPercent);
    Serial.println("%");
  } else {
    Serial.print("# UNKNOWN COMMAND: ");
    Serial.println(cmd);
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {

  pinMode(PUMP_PIN, OUTPUT);

  Serial.begin(115200);
  Wire.begin();

  startMillis = millis();
  pumpCycleStart = millis();

  Serial.println("\n===== SYSTEM START =====");
  Serial.println("# Pump speed control: send P<0-100> (e.g. P0, P50, P100)");

  // SHT30
  sht30.begin(0x44);

  // BME688 #1
  bme688_1.begin(0x76);
  bme688_1.setTemperatureOversampling(BME680_OS_8X);
  bme688_1.setHumidityOversampling(BME680_OS_2X);
  bme688_1.setPressureOversampling(BME680_OS_4X);
  bme688_1.setGasHeater(320, 150);

  // BME688 #2
  bme688_2.begin(0x77);
  bme688_2.setTemperatureOversampling(BME680_OS_8X);
  bme688_2.setHumidityOversampling(BME680_OS_2X);
  bme688_2.setPressureOversampling(BME680_OS_4X);
  bme688_2.setGasHeater(320, 150);

  // AS7341
  while (as7341.begin() != 0) {
    delay(1000);
  }
  as7341.startMeasure(DFRobot_AS7341::eF1F4ClearNIR);

  // CSV HEADER
  Serial.println();
  Serial.println(
    "DATE,TIME,UPTIME_S,"
    "SHT30_T,SHT30_H,"
    "BME1_T,BME1_H,BME1_P,BME1_G,"
    "BME2_T,BME2_H,BME2_P,BME2_G,"
    "AS7341_F1,AS7341_F2,AS7341_F3,AS7341_F4,AS7341_CLEAR,AS7341_NIR,"
    "STEPPER_SPEED,PUMP_SPEED,PUMP_STATE"
  );
}

// =====================================================
// LOOP
// =====================================================

void loop() {

  unsigned long now = millis();

  // SERIAL INPUT — read characters into buffer, process on newline
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        handleSerialCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
    }
  }

  // PUMP CYCLE
  unsigned long onMs  = PUMP_ON_TIME_MIN * 60000;
  unsigned long offMs = PUMP_OFF_TIME_MIN * 60000;

  if (pumpCycleState) {
    if (now - pumpCycleStart >= onMs) {
      pumpCycleState = false;
      pumpCycleStart = now;
    }
  } else {
    if (now - pumpCycleStart >= offMs) {
      pumpCycleState = true;
      pumpCycleStart = now;
    }
  }

  analogWrite(PUMP_PIN,
    pumpCycleState ? map(pumpSpeedPercent, 0, 100, 0, 255) : 0
  );

  // LOGGING
  if (millis() - lastLog >= 3000) {

    unsigned long uptime_s = millis() / 1000;

    String dateStr, timeStr;
    getDateTime(now, dateStr, timeStr);

    float shtT = sht30.readTemperature();
    float shtH = sht30.readHumidity();

    float b1T, b1H, b1P, b1G;
    float b2T, b2H, b2P, b2G;

    bme688_1.performReading();
    b1T = bme688_1.temperature;
    b1H = bme688_1.humidity;
    b1P = bme688_1.pressure / 100.0;
    b1G = bme688_1.gas_resistance;

    bme688_2.performReading();
    b2T = bme688_2.temperature;
    b2H = bme688_2.humidity;
    b2P = bme688_2.pressure / 100.0;
    b2G = bme688_2.gas_resistance;

    delay(50);
    DFRobot_AS7341::sModeOneData_t data =
      as7341.readSpectralDataOne();

    uint16_t *ch = (uint16_t*)&data;

    Serial.print(dateStr); Serial.print(",");
    Serial.print(timeStr); Serial.print(",");
    Serial.print(uptime_s); Serial.print(",");

    Serial.print(shtT); Serial.print(",");
    Serial.print(shtH); Serial.print(",");

    Serial.print(b1T); Serial.print(",");
    Serial.print(b1H); Serial.print(",");
    Serial.print(b1P); Serial.print(",");
    Serial.print(b1G); Serial.print(",");

    Serial.print(b2T); Serial.print(",");
    Serial.print(b2H); Serial.print(",");
    Serial.print(b2P); Serial.print(",");
    Serial.print(b2G); Serial.print(",");

    Serial.print(ch[0]); Serial.print(",");
    Serial.print(ch[1]); Serial.print(",");
    Serial.print(ch[2]); Serial.print(",");
    Serial.print(ch[3]); Serial.print(",");
    Serial.print(ch[4]); Serial.print(",");
    Serial.print(ch[5]); Serial.print(",");

    Serial.print(speedPercent); Serial.print(",");
    Serial.print(pumpSpeedPercent); Serial.print(",");
    Serial.println(pumpCycleState ? "ON" : "OFF");

    lastLog = millis();
  }
}
