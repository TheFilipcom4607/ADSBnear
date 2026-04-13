# ADSBnear ✈️

![alt text](https://assets.thefilip.com/adsbnear-v1.1.jpg)

A CircuitPython project that displays the nearest aircraft on a 16×2 LCD screen using real-time ADS-B data. Perfect for aviation enthusiasts who want to know what's flying overhead without checking their phone 24/7.
## V1.3 RELEASED! NOW YOU CAN DISPLAY DATA FROM YOUR LOCAL ADSB RECIEVER!
## What It Does

ADSBnear transforms your microcontroller into a live aircraft tracker. It can pull data from the [adsb.lol API](https://adsb.lol) via Wi-Fi **or** from a local ADS-B receiver (dump1090, readsb, tar1090) on your network. Watch as planes appear and disappear from your personal radar scope, displaying the closest aircraft's vital information on a compact LCD with intelligent polling that adapts to air traffic activity.

## Hardware Requirements

- **Microcontroller:** CircuitPython-compatible board (Raspberry Pi Pico W, ESP32-S3, etc.)
- **Display:** 16×2 LCD with I2C backpack (PCF8574)  
- **Connection:** Wi-Fi capability
- **Power:** USB power supply

## Inspiration

This project was inspired by [u/fil1983's "Nearest Aircraft Display"](https://www.reddit.com/r/ADSB/comments/1nb56ld/nearest_aircraft_display/) on Reddit. Their [original implementation](https://github.com/filbot/flight-display) features a beautiful large OLED display with advanced features.

ADSBnear is a simplified, budget-friendly alternative using a basic 16×2 LCD (with about 1/3 of the features of the original setup) for those who want core aircraft tracking functionality without the complexity or price.

## Quick Start

### 1. Prepare Your Board
Flash your microcontroller with the latest [CircuitPython firmware](https://circuitpython.org/downloads)

### 2. Install Files
```
CIRCUITPY/
├── main.py              # Main program file
├── lib/                 # Required libraries folder
└── plane_types.json     # Optional: Aircraft database
```

### 3. Configure Settings
Edit the configuration section at the top of `main.py`:

```python
# Data source: "api" for adsb.lol, "local" for a local ADS-B receiver
DATA_SOURCE = "api"

# API settings (used when DATA_SOURCE = "api")
API_RADIUS_KM = 7       # Search radius for API calls

# Local receiver settings (used when DATA_SOURCE = "local")
# Common URLs:
#   tar1090 / readsb:  http://<ip>/tar1090/data/aircraft.json
#   dump1090-fa:        http://<ip>/dump1090-fa/data/aircraft.json
#   dump1090 (default): http://<ip>:8080/data/aircraft.json
LOCAL_ADSB_URL = "http://192.168.1.100/tar1090/data/aircraft.json"

# Network Configuration
WIFI_SSID = "your_wifi_name"
WIFI_PASSWORD = "your_wifi_password"

# Location (get coordinates from Google Maps)
LATITUDE  = 52.16517  # Your latitude
LONGITUDE = 20.96894  # Your longitude

# Display Settings
DISPLAY_RADIUS_KM = 10 # Maximum distance to display

# Smart Polling Configuration
POLL_SEC = 4.0         # seconds between polls when a plane is displayed
NO_PLANE_POLL_SEC = 30.0 # seconds between polls when no plane is displayed
ERROR_POLL_SEC = 5.0   # seconds to wait on error before retrying

# Hardware Settings
LCD_I2C_ADDRESS = 0x27 # I2C address of LCD backpack
```

### 4. Install Libraries
Copy the included `lib/` folder to your CircuitPython device. Required libraries:
- LCD display library (credit: [Dan Halbert](https://github.com/dhalbert/CircuitPython_LCD))
- Standard CircuitPython networking libraries

### 5. Optional Enhancement
Copy `plane_types.json` for detailed aircraft names in console output (e.g., "Boeing 737 MAX 8" instead of "B38M"). 

*Note: This only affects serial console output due to 16×2 display limitations.*

## Usage

1. **Power on** your device
2. **Connect** - Device automatically connects to Wi-Fi
3. **Scan** - Begins searching for nearby aircraft
4. **Display** - Shows closest aircraft within range
5. **Smart Updates** - Polls every 4 seconds when aircraft present, every 30 seconds when skies are empty


## Troubleshooting

### Common Issues
- **No Wi-Fi connection:** Check SSID/password, ensure 2.4GHz network
- **Blank LCD:** Verify I2C address (try 0x3F if 0x27 doesn't work)
- **No aircraft data (API mode):** Check internet connection and API availability
- **No aircraft data (local mode):** Verify `LOCAL_ADSB_URL` is reachable — try opening it in a browser to confirm JSON is returned
- **Wrong distance/aircraft:** Verify latitude/longitude coordinates

### Testing I2C Address
Use this code snippet to scan for your LCD's I2C address:
```python
import board
import busio
i2c = busio.I2C(board.SCL, board.SDA)
print([hex(x) for x in i2c.scan()])
```

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `DATA_SOURCE` | `"api"` | `"api"` for adsb.lol, `"local"` for local receiver |
| `API_RADIUS_KM` | 7 | How far to search for aircraft (API mode) |
| `LOCAL_ADSB_URL` | `"http://..."` | URL of local receiver JSON endpoint |
| `LOCAL_AC_MSG_RATE` | `False` | Show per-aircraft msg/s instead of speed (local mode only) |
| `ALTERNATE_ROUTE` | `False` | Alternate line 1 between callsign and route every 2 seconds |
| `DISPLAY_RADIUS_KM` | 10 | Maximum distance to display |
| `POLL_SEC` | 4.0 | Update frequency when plane displayed |
| `NO_PLANE_POLL_SEC` | 30.0 | Update frequency when no planes |
| `ERROR_POLL_SEC` | 5.0 | Retry delay after errors |
| `LCD_I2C_ADDRESS` | 0x27 | I2C address of LCD backpack |
| `PLANE_TYPES_FILE` | "/plane_types.json" | Aircraft database file path |

## Changelog

### v1.7
- Route lookup now works with local feeders: when `ALTERNATE_ROUTE = True` and route data isn't in the aircraft JSON, the callsign is looked up via [adsbdb.com](https://api.adsbdb.com) (free, no key required). Results are cached per callsign so the API is only hit once per flight. SSL is automatically loaded when needed

### v1.6
- Added `ALTERNATE_ROUTE` config option: when enabled, line 1 alternates every 2 seconds between the callsign (e.g. `SAS2945`) and the route (e.g. `WAW-CDG`). Works with any data source that provides route or origin/destination fields. Falls back to callsign-only if no route data is present

### v1.5
- Added `LOCAL_AC_MSG_RATE` config option: in local mode, replaces the speed field on the aircraft display line with the per-aircraft message rate (e.g. `2.4msg/s`) received from that specific transponder

### v1.4
- In local mode, the idle screen now shows live feeder message rate (e.g. `2.4msg/s`) instead of uptime when no aircraft are in range

### v1.3
- Added local ADS-B receiver support (dump1090, readsb, tar1090) — set `DATA_SOURCE = "local"` and point `LOCAL_ADSB_URL` at your receiver
- SSL is only loaded when using API mode, saving memory in local mode
- Fixed altitude trend arrow logic (climb/descend arrows now work correctly)
- Added real bearing calculation in console output
- General code cleanup

### v1.2
Added debug info. Change ```DEBUG_INFO = False``` to ```True``` in the config to enable

### v1.1
Added arrow indicators after altitude numbers to show if planes are climbing ▲ or descending ▼

### v1.0
Initial release

## Credits

- **Inspiration:** [u/fil1983](https://github.com/filbot/flight-display) - Original advanced aircraft display
- **LCD Library:** [Dan Halbert](https://github.com/dhalbert/CircuitPython_LCD) - CircuitPython LCD library
- **Data Source:** [adsb.lol](https://adsb.lol) - Real-time ADS-B API
