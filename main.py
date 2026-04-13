import json
import math
import time

import wifi
import socketpool
import adafruit_requests

import board
from lcd.lcd import LCD
from lcd.i2c_pcf8574_interface import I2CPCF8574Interface

# ─────────────── USER SETTINGS ─────────────── #

# Data source: "api" for adsb.lol, "local" for a local ADS-B receiver
DATA_SOURCE         = "api"

# API settings (used when DATA_SOURCE = "api")
API_RADIUS_KM       = 7       # search radius for API queries

# Local receiver settings (used when DATA_SOURCE = "local")
# Common URLs:
#   tar1090 / readsb:  http://<ip>/tar1090/data/aircraft.json
#   dump1090-fa:        http://<ip>/dump1090-fa/data/aircraft.json
#   dump1090 (default): http://<ip>:8080/data/aircraft.json
LOCAL_ADSB_URL      = "http://192.168.1.100/tar1090/data/aircraft.json"
LOCAL_AC_MSG_RATE   = False   # show per-aircraft msg/s instead of speed (local mode only)

DISPLAY_RADIUS_KM   = 10      # max distance (km) to show on display

WIFI_SSID           = "CHANGEME"
WIFI_PASSWORD       = "CHANGEME"

LATITUDE            = CHANGEME
LONGITUDE           = CHANGEME

POLL_SEC            = 4.0     # seconds between polls when a plane is displayed
NO_PLANE_POLL_SEC   = 30.0    # seconds between polls when no plane is displayed
ERROR_POLL_SEC      = 5.0     # seconds to wait on error before retrying

LCD_I2C_ADDRESS     = 0x27
PLANE_TYPES_FILE    = "/plane_types.json"

DEBUG_INFO          = True    # set True to enable debug messages

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

i2c       = board.I2C()
interface = I2CPCF8574Interface(i2c, LCD_I2C_ADDRESS)
lcd       = LCD(interface, num_rows=2, num_cols=16)
lcd.create_char(0, UP_ARROW)
lcd.create_char(1, DOWN_ARROW)
lcd.create_char(2, LEVEL_ARROW)

lcd.clear()
lcd.print("    ADSBnear")
lcd.set_cursor_pos(1, 0)
lcd.print("  Connecting..")

# ─────────────── SESSION STATS ─────────────── #

_start_time      = time.monotonic()
_planes_seen     = 0
_last_seen_flight = None
_last_seen_time  = None

_last_msg_count  = None   # last raw message counter from local receiver
_last_msg_time   = None   # time.monotonic() when that count was sampled
_msg_rate        = None   # computed messages/sec (float)

_ac_msg_tracker  = {}     # icao -> (last_count, last_time) for per-aircraft msg/s

# ─────────────── DEBUG PRINT ─────────────── #

def debug_print(*args, **kwargs):
    if DEBUG_INFO:
        print(*args, **kwargs)

# ────────── WIFI & HTTP SESSION ────────── #

wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
pool = socketpool.SocketPool(wifi.radio)

if DATA_SOURCE == "api":
    import ssl
    ssl_ctx = ssl.create_default_context()
else:
    ssl_ctx = None
requests = adafruit_requests.Session(pool, ssl_ctx)

debug_print("Connected to Wi-Fi")
debug_print("My IP address:", wifi.radio.ipv4_address)
debug_print("Data source:", DATA_SOURCE)

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
    a = (math.sin((phi2 - phi1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(a))

def bearing_deg(lat1, lon1, lat2, lon2):
    if math.isnan(lat2) or math.isnan(lon2):
        return float('nan')
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda))
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def fmt_duration(seconds):
    minutes = int(seconds) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h{mins:02d}m"
    days = hours // 24
    hrs = hours % 24
    return f"{days}d{hrs}h"

def ft_to_m(ft):
    return ft * 0.3048

def kn_to_kmh(kn):
    return kn * 1.852

def api_url():
    return f"https://api.adsb.lol/v2/closest/{LATITUDE:.6f}/{LONGITUDE:.6f}/{API_RADIUS_KM}"

# ──────── LCD TEXT HELPERS (16x2) ───────── #

def pad16(text):
    text = "" if text is None else str(text)
    return (text + " " * 16)[:16]

# ───────── ALTITUDE TREND AWARE LCD FORMATTER ───────── #

_last_alt = None
_last_flight = None

def format_lcd(ac, ac_msg_rate=None):
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

    arrow = chr(2)  # default level
    if flt_raw != _last_flight:
        _last_alt = None
    elif _last_alt is not None:
        delta = alt_m - _last_alt
        if delta > 5:
            arrow = chr(0)  # up
        elif delta < -5:
            arrow = chr(1)  # down

    _last_alt = alt_m
    _last_flight = flt_raw

    if LOCAL_AC_MSG_RATE and ac_msg_rate is not None:
        if ac_msg_rate < 10:
            spd_str = f"{ac_msg_rate:.1f}msg/s"
        else:
            spd_str = f"{int(ac_msg_rate)}msg/s"
    else:
        spd_str = f"{int(gs_kmh + 0.5):3d}km/h"
    line2 = f"{int(alt_m + 0.5):5d}m{arrow} {spd_str}"
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

    brg = bearing_deg(LATITUDE, LONGITUDE, lat, lon)
    brg_str = "---" if math.isnan(brg) else f"{brg:05.1f}\u00b0"

    dst_str = fmt(dist_km) + " km"
    if not math.isnan(api_dst):
        dst_str += f" (API {fmt(api_dst)})"

    return (
        f"{flt:<8}  {type_str}{reg:<6}  "
      + f"{dst_str}  {brg_str}  "
      + f"{alt_ft:5.0f} ft ({alt_m:4.0f} m)  "
      + f"{gs_kn:3.0f} kn / {gs_kmh:3.0f} km/h"
    )

# ──────────────── DATA FETCHING ────────────────── #

def fetch_aircraft():
    """Fetch nearby aircraft, returned as a list (closest first)."""
    if DATA_SOURCE == "local":
        return _fetch_local()
    return _fetch_api()

def _fetch_api():
    url = api_url()
    debug_print("Fetching:", url)
    response = requests.get(url)
    debug_print("Status:", response.status_code)
    data = response.json()
    return data.get("ac") or []

def _fetch_local():
    global _last_msg_count, _last_msg_time, _msg_rate
    debug_print("Fetching:", LOCAL_ADSB_URL)
    response = requests.get(LOCAL_ADSB_URL)
    debug_print("Status:", response.status_code)
    data = response.json()
    aircraft_list = data.get("aircraft") or []

    # track message rate from the receiver's cumulative counter
    raw_count = data.get("messages")
    now = time.monotonic()
    if raw_count is not None:
        if _last_msg_count is not None and _last_msg_time is not None:
            elapsed = now - _last_msg_time
            if elapsed > 0:
                _msg_rate = (raw_count - _last_msg_count) / elapsed
        _last_msg_count = raw_count
        _last_msg_time = now

    # filter to aircraft with valid positions within range, sort by distance
    nearby = []
    for ac in aircraft_list:
        lat = to_float(ac.get("lat"))
        lon = to_float(ac.get("lon"))
        if math.isnan(lat) or math.isnan(lon):
            continue
        dist = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)
        if not math.isnan(dist) and dist <= DISPLAY_RADIUS_KM:
            nearby.append((dist, ac))

    nearby.sort(key=lambda x: x[0])
    return [ac for _, ac in nearby]

# ────────── DISPLAY HELPERS ────────── #

def show_no_planes():
    now = time.monotonic()
    uptime = now - _start_time

    if _last_seen_flight:
        ago = fmt_duration(now - _last_seen_time)
        left1 = f"Last:{_last_seen_flight}"
        gap1 = max(16 - len(left1) - len(ago), 1)
        line1 = (left1 + " " * gap1 + ago)[:16]
    else:
        line1 = "  Scanning...   "

    left2 = f"{_planes_seen} seen"
    if DATA_SOURCE == "local" and _msg_rate is not None:
        right2 = f"{_msg_rate:.1f}msg/s"
    else:
        right2 = f"Up:{fmt_duration(uptime)}"
    gap2 = max(16 - len(left2) - len(right2), 1)
    line2 = (left2 + " " * gap2 + right2)[:16]

    lcd.clear()
    lcd.print(pad16(line1))
    lcd.set_cursor_pos(1, 0)
    lcd.print(pad16(line2))

# ──────────────── MAIN LOOP ────────────────── #

while True:
    try:
        aircraft = fetch_aircraft()
        now = time.localtime()
        timestr = f"{now[3]:02d}:{now[4]:02d}:{now[5]:02d}"

        plane_displayed = False

        if aircraft:
            ac = aircraft[0]
            lat = to_float(ac.get("lat"))
            lon = to_float(ac.get("lon"))
            dist = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)

            if not math.isnan(dist) and dist <= DISPLAY_RADIUS_KM:
                ac_msg_rate = None
                if LOCAL_AC_MSG_RATE:
                    icao = ac.get("hex", "")
                    ac_count = ac.get("messages")
                    now_mono = time.monotonic()
                    if ac_count is not None and icao in _ac_msg_tracker:
                        prev_count, prev_time = _ac_msg_tracker[icao]
                        elapsed = now_mono - prev_time
                        if elapsed > 0:
                            ac_msg_rate = (ac_count - prev_count) / elapsed
                    if ac_count is not None:
                        _ac_msg_tracker[icao] = (ac_count, now_mono)
                line1, line2 = format_lcd(ac, ac_msg_rate)
                lcd.clear()
                lcd.print(line1)
                lcd.set_cursor_pos(1, 0)
                lcd.print(line2)
                print(timestr, format_console(ac))
                plane_displayed = True

                flt_name = (ac.get("flight") or "????").strip()
                if flt_name != _last_seen_flight:
                    _planes_seen += 1
                _last_seen_flight = flt_name
                _last_seen_time = time.monotonic()

        if not plane_displayed:
            show_no_planes()
            print(timestr, f"No aircraft within {DISPLAY_RADIUS_KM} km")

        next_poll = POLL_SEC if plane_displayed else NO_PLANE_POLL_SEC

    except Exception as err:
        debug_print("Exception:", repr(err))
        print("ERROR:", err)
        lcd.clear()
        lcd.print("Connection Err")
        lcd.set_cursor_pos(1, 0)
        lcd.print("Retrying...")
        next_poll = ERROR_POLL_SEC

    time.sleep(next_poll)
