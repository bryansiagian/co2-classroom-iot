# IoT End-to-End Stability Test — 2026-11-06

## Objective
Verify the stability of the ESP32 sensor data transmission pipeline from the development environment to the H200 server database.

## System Architecture
ESP32 (MH-Z19C, DHT22, PIR) → Windows Mobile Hotspot → Mosquitto MQTT → Python SSH Relay → H200 MQTT Broker → Backend → SQLite.

## Test Configuration
- Date: November 6, 2026
- Start: 23:20:31 WIB
- End: 23:50:31 WIB
- Duration: 30 minutes
- ESP32 publish interval: 10 seconds
- MQTT topic: `classroom/gd525/sensors`
- Environment: Development, outside the official GD525 classroom deployment

## Stability Results

| Metric | Result |
|---|---|
| Expected records | 180 |
| Stored records | 180 |
| Mean interval | 10.00 seconds |
| Median interval | 10.00 seconds |
| Maximum interval | 11.00 seconds |
| Gaps greater than 20 seconds | 0 |
| Duplicate received timestamps | 0 |

## Sensor Readings

| Sensor | Minimum | Maximum |
|---|---|---|
| CO₂ (MH-Z19C) | 1347 ppm | 2229 ppm |
| Temperature (DHT22) | 25.8°C | 26.4°C |
| Relative humidity (DHT22) | 82.0% | 87.6% |

PIR readings: 174 active and 6 inactive.

## Observations
1. The complete data transmission pipeline operated successfully for 30 minutes.
2. All 180 nominally expected records were stored in the H200 SQLite database.
3. No timestamp duplicates or transmission gaps greater than 20 seconds were detected.
4. Some CO₂ spikes were caused by manually moving the sensor PCB close to the operator's face, exposing the sensor to exhaled air.
5. This development dataset must not be treated as representative classroom data.
6. The test does not independently establish a 100% MQTT delivery rate without device-side sequence identifiers.

## Previously Resolved Issue
Two Mosquitto instances were running on Windows. ESP32 connected to the broker listening on the hotspot interface, while the local subscriber and relay connected to a separate Windows Service instance on loopback.

The issue was resolved by stopping the additional Mosquitto Windows Service, allowing all local clients to use the same broker instance.

## Conclusion
The development IoT data pipeline passed the initial 30-minute stability test according to the defined criteria.

## Next Steps
- Validate sensor readings under stationary conditions.
- Investigate unexpected CO₂ changes and PIR behavior.
- Add message sequence identifiers and examine potential duplicate delivery.
- Verify one-minute resampling and 15-minute prediction windows.
- Prepare official data collection in classroom GD525.