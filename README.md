# ADSBnear ✈️

![alt text](https://assets.thefilip.com/adsbnear.jpg)

A CircuitPython project that displays the nearest aircraft on a 16×2 LCD screen using real-time ADS-B data. Perfect for aviation enthusiasts who want to know what's flying overhead without checking their phone 24/7.

## 🎯 What It Does

ADSBnear transforms your microcontroller into a live aircraft tracker that connects to the [adsb.lol API](https://adsb.lol) via Wi-Fi to fetch real-time aircraft positions near your location. Watch as planes appear and disappear from your personal radar scope, displaying the closest aircraft's vital information on a compact LCD with intelligent polling that adapts to air traffic activity.

## 🛠 Hardware Requirements

- **Microcontroller:** CircuitPython-compatible board (Raspberry Pi Pico W, ESP32-S3, etc.)
- **Display:** 16×2 LCD with I2C backpack (PCF8574)  
- **Connection:** Wi-Fi capability
- **Power:** USB power supply

## 💡 Inspiration

This project was inspired by [u/fil1983's "Nearest Aircraft Display"](https://www.reddit.com/r/ADSB/comments/1nb56ld/nearest_aircraft_display/) on Reddit. Their [original implementation](https://github.com/filbot/flight-display) features a beautiful large OLED display with advanced features.

ADSBnear is a simplified, budget-friendly alternative using a basic 16×2 LCD (with about 1/3 of the features of the original setup) for those who want core aircraft tracking functionality without the complexity or price.

## 🚀 Quick Start

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
# Network Configuration
WIFI_SSID = "your_wifi_name"
WIFI_PASSWORD = "your_wifi_password"

# Location (get coordinates from Google Maps)
LATITUDE  = 52.16517  # Your latitude
LONGITUDE = 20.96894  # Your longitude

# Display Settings
API_RADIUS_KM = 7      # Search radius for API calls
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

## 🖥 Usage

1. **Power on** your device
2. **Connect** - Device automatically connects to Wi-Fi
3. **Scan** - Begins searching for nearby aircraft
4. **Display** - Shows closest aircraft within range
5. **Smart Updates** - Polls every 4 seconds when aircraft present, every 30 seconds when skies are empty


## 🔧 Troubleshooting

### Common Issues
- **No Wi-Fi connection:** Check SSID/password, ensure 2.4GHz network
- **Blank LCD:** Verify I2C address (try 0x3F if 0x27 doesn't work)
- **No aircraft data:** Check internet connection and API availability
- **Wrong distance/aircraft:** Verify latitude/longitude coordinates

### Testing I2C Address
Use this code snippet to scan for your LCD's I2C address:
```python
import board
import busio
i2c = busio.I2C(board.SCL, board.SDA)
print([hex(x) for x in i2c.scan()])
```

## 📊 Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `API_RADIUS_KM` | 7 | How far to search for aircraft |
| `DISPLAY_RADIUS_KM` | 10 | Maximum distance to display |
| `POLL_SEC` | 4.0 | Update frequency when plane displayed |
| `NO_PLANE_POLL_SEC` | 30.0 | Update frequency when no planes |
| `ERROR_POLL_SEC` | 5.0 | Retry delay after API errors |
| `LCD_I2C_ADDRESS` | 0x27 | I2C address of LCD backpack |
| `PLANE_TYPES_FILE` | "/plane_types.json" | Aircraft database file path |

## 🙏 Credits

- **Inspiration:** [u/fil1983](https://github.com/filbot/flight-display) - Original advanced aircraft display
- **LCD Library:** [Dan Halbert](https://github.com/dhalbert/CircuitPython_LCD) - CircuitPython LCD library
- **Data Source:** [adsb.lol](https://adsb.lol) - Real-time ADS-B API
