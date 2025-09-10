import json
import math
import time
import ssl

import wifi
import socketpool
import adafruit_requests

import board
from lcd.lcd import LCD
from lcd.i2c_pcf8574_interface import I2CPCF8574Interface

# ─────────────── USER SETTINGS ─────────────── #

API_RADIUS_KM       = 7     # how far (nm? its weird) to ask the API
DISPLAY_RADIUS_KM   = 10    # how far (km) to accept & show

WIFI_SSID           = "CHANGEME"
WIFI_PASSWORD       = "CHANGEME"

LATITUDE            = CHANGEME
LONGITUDE           = CHANGEME

POLL_SEC            = 4.0    # seconds between polls when a plane is displayed
NO_PLANE_POLL_SEC   = 30.0   # seconds between polls when no plane is displayed
ERROR_POLL_SEC      = 5.0    # seconds to wait on error before retrying

LCD_I2C_ADDRESS     = 0x27
PLANE_TYPES_FILE    = "/plane_types.json"

DEBUG_INFO = True   # set True to enable debug messages

# ─────────────── Arrows ─────────────── #

UP_ARROW = [
    0b00000,
    0b00000,
    0b00100,
    0b01110,
    0b11111,
    0b00000,
    0b00000,
    0b00000,
]

DOWN_ARROW = [
    0b00000,
    0b00000,
    0b00000,
    0b11111,
    0b01110,
    0b00100,
    0b00000,
    0b00000,
]

LEVEL_ARROW = [
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b11111,
    0b00000,
    0b00000,
    0b00000,
]

# ─────────────── LCD SETUP ─────────────── #

i2c       = board.I2C()  # default 100 kHz on board.SCL & board.SDA
interface = I2CPCF8574Interface(i2c, LCD_I2C_ADDRESS)
lcd       = LCD(interface, num_rows=2, num_cols=16)
lcd.create_char(0, UP_ARROW)
lcd.create_char(1, DOWN_ARROW)
lcd.create_char(2, LEVEL_ARROW)

lcd.clear()
lcd.print("    ADSBnear")
lcd.set_cursor_pos(1, 0)
lcd.print("  Connecting..")

# ─────────────── DEBUG PRINT ─────────────── #

def debug_print(*args, **kwargs):
    if DEBUG_INFO:
        print(*args, **kwargs)

# ────────── WIFI & HTTP SESSION ────────── #

wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
pool     = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())
debug_print("Connected to Wi-Fi")
debug_print("My IP address:", wifi.radio.ipv4_address)
debug_print("Router:", wifi.radio.ipv4_gateway)
debug_print("DNS:", wifi.radio.ipv4_dns)

# ──────── PLANE TYPE LOOKUP ────────── #

def load_plane_types(fname):
    try:
        with open(fname, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}

PLANE_NAMES = load_plane_types(PLANE_TYPES_FILE)

# ─────────────── UTILITIES ─────────────── #

def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float('nan')

EARTH_R = 6371.0088  # km

def gc_distance_km(lat1, lon1, lat2, lon2):
    if math.isnan(lat2) or math.isnan(lon2):
        return float('nan')
    phi1, phi2, d_lambda = map(math.radians, (lat1, lat2, lon2 - lon1))
    a = (math.sin((phi2 - phi1)/2)**2
         + math.cos(phi1)*math.cos(phi2)*math.sin(d_lambda/2)**2)
    return 2 * EARTH_R * math.asin(math.sqrt(a))

def ft_to_m(ft):
    return ft * 0.3048

def kn_to_kmh(kn):
    return kn * 1.852

def api_url():
    return f"https://api.adsb.lol/v2/closest/{LATITUDE:.6f}/{LONGITUDE:.6f}/{API_RADIUS_KM}"

# ──────── LCD TEXT HELPERS (16×2) ───────── #

def pad16(text):
    text = "" if text is None else str(text)
    return (text + " " * 16)[:16]

# ───────── ALTITUDE TREND AWARE LCD FORMATTER ───────── #

_last_alt = None
_last_flight = None

def format_lcd(ac):
    global _last_alt, _last_flight

    lat    = to_float(ac.get("lat"))
    lon    = to_float(ac.get("lon"))
    gs_kn  = to_float(ac.get("gs"))
    alt_ft = to_float(ac.get("alt_geom") or ac.get("alt_baro"))

    if math.isnan(gs_kn):
        gs_kn = 0.0
    if math.isnan(alt_ft):
        alt_ft = 0.0

    dist = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)
    dist_str = "--" if math.isnan(dist) else str(int(dist + 0.5))

    flt_raw = (ac.get("flight") or "????").strip()[:7]

    raw_type = (ac.get("t") or "").strip().upper()
    if not raw_type:
        type_code = "????"
    elif len(raw_type) >= 4:
        type_code = raw_type[:4]
    else:
        type_code = raw_type + "?" * (4 - len(raw_type))

    base = f"{flt_raw} {dist_str}km {type_code}"
    while len(base) > 16 and len(flt_raw) > 1:
        flt_raw = flt_raw[:-1]
        base = f"{flt_raw} {dist_str}km {type_code}"

    if len(base) < 16:
        pad_total = 16 - len(base)
        left_pad = pad_total // 2
        right_pad = pad_total - left_pad
        line1 = " " * left_pad + base + " " * right_pad
    else:
        line1 = base[:16]

    # altitude & speed line with trend arrow
    alt_m  = ft_to_m(alt_ft)
    gs_kmh = kn_to_kmh(gs_kn)

    # reset arrow if new flight
    arrow = chr(2)  # default level
    if flt_raw != _last_flight:
        _last_alt = None
    else:
        if _last_alt is not None:
            delta = alt_m - _last_alt
            if delta > 20:      # climbing more than 20 m
                arrow = chr(0)  # up
        elif delta < -20:   # descending more than 20 m
            arrow = chr(1)  # down
        else:
            # keep previous arrow if we were already climbing/descending
            if arrow not in (chr(0), chr(1)):
                arrow = chr(2)

    _last_alt = alt_m
    _last_flight = flt_raw

    line2 = f"{int(alt_m+0.5):5d}m{arrow} {int(gs_kmh+0.5):3d}km/h"
    line2 = pad16(line2)

    return line1, line2


def format_console(ac):
    lat     = to_float(ac.get("lat"))
    lon     = to_float(ac.get("lon"))
    api_dst = to_float(ac.get("dst"))
    gs_kn   = to_float(ac.get("gs"))
    alt_ft  = to_float(ac.get("alt_geom") or ac.get("alt_baro"))

    if math.isnan(gs_kn):
        gs_kn = 0.0
    if math.isnan(alt_ft):
        alt_ft = 0.0

    dist_km = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)
    gs_kmh  = kn_to_kmh(gs_kn)
    alt_m   = ft_to_m(alt_ft)

    flt  = (ac.get("flight") or "????").strip()
    reg  = (ac.get("r")      or "").strip()
    code = (ac.get("t")      or "").strip()
    name = PLANE_NAMES.get(code, "(unknown)")
    type_str = f"{code:<4}  {name:<28}"

    def fmt(x):
        return "---" if math.isnan(x) else f"{x:5.1f}"

    brg = "---"
    if not math.isnan(dist_km):
        brg = f"{math.degrees(math.atan2(0, 0)):.1f}°"  # placeholder

    return (
        f"{flt:<8}  {type_str}{reg:<6}  "
      + f"{fmt(dist_km)} km (API {fmt(api_dst)})  "
      + f"{brg}  "
      + f"{alt_ft:5.0f} ft ({alt_m:4.0f} m)  "
      + f"{gs_kn:3.0f} kn / {gs_kmh:3.0f} km/h"
    )

# ──────────────── MAIN LOOP ────────────────── #

def fetch_closest():
    url = api_url()
    debug_print("Fetching URL:", url)
    response = requests.get(url)
    debug_print("Response status:", response.status_code)
    return response.json()

while True:
    try:
        data = fetch_closest()
        now = time.localtime()
        timestr = f"{now[3]:02d}:{now[4]:02d}:{now[5]:02d}"

        # assume no plane until we display one
        plane_displayed = False

        if data and data.get("ac"):
            ac = data["ac"][0]
            lat = to_float(ac.get("lat"))
            lon = to_float(ac.get("lon"))
            dist = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)

            if not math.isnan(dist) and dist <= DISPLAY_RADIUS_KM:
                # display the nearest aircraft
                line1, line2 = format_lcd(ac)
                lcd.clear()
                lcd.print(line1)
                lcd.set_cursor_pos(1, 0)
                lcd.print(line2)
                print(timestr, format_console(ac))
                plane_displayed = True
            else:
                # no aircraft in display radius
                lcd.clear()
                lcd.print("No planes within")
                lcd.set_cursor_pos(1, 0)
                lcd.print(f"{DISPLAY_RADIUS_KM}km | Scanning")
                print(timestr, f"No aircraft within {DISPLAY_RADIUS_KM} km")
        else:
            # API returned no data or no 'ac' list
            lcd.clear()
            lcd.print("No planes within")
            lcd.set_cursor_pos(1, 0)
            lcd.print(f"{DISPLAY_RADIUS_KM}km | Scanning")
            print(timestr, f"No aircraft within {DISPLAY_RADIUS_KM} km")

        # choose sleep interval based on whether we showed a plane
        if plane_displayed:
            next_poll = POLL_SEC
        else:
            next_poll = NO_PLANE_POLL_SEC

    except Exception as err:
        debug_print("Exception details:", repr(err))
        print("ERROR:", err)  # keep this visible even if DEBUG_INFO = False
        lcd.clear()
        lcd.print("API / Wi-Fi Err")
        lcd.set_cursor_pos(1, 0)
        lcd.print("Retrying...")
        next_poll = ERROR_POLL_SEC

    # sleep before next API call
    time.sleep(next_poll)
