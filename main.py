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

API_RADIUS_KM     = 7   # how far (km) to ask the API
DISPLAY_RADIUS_KM = 10  # how far (km) to accept & show

WIFI_SSID       = "CHANGEME"
WIFI_PASSWORD   = "CHANGEME"

LATITUDE        = CHANGEME
LONGITUDE       = CHANGEME
POLL_SEC        = 3.0     # seconds between polls

LCD_I2C_ADDRESS = 0x27
PLANE_TYPES_FILE = "/plane_types.json"

# ─────────────── LCD SETUP ─────────────── #

i2c       = board.I2C()  # default 100 kHz on board.SCL & board.SDA
interface = I2CPCF8574Interface(i2c, LCD_I2C_ADDRESS)
lcd       = LCD(interface, num_rows=2, num_cols=16)

lcd.clear()
lcd.print("    ADSBnear")
lcd.set_cursor_pos(1, 0)
lcd.print("  Connecting..")

# ────────── WIFI & HTTP SESSION ────────── #

wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
pool     = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

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

def format_lcd(ac):
    # raw & sanitize
    lat    = to_float(ac.get("lat"))
    lon    = to_float(ac.get("lon"))
    gs_kn  = to_float(ac.get("gs"))
    alt_ft = to_float(ac.get("alt_geom") or ac.get("alt_baro"))

    if math.isnan(gs_kn):
        gs_kn = 0.0
    if math.isnan(alt_ft):
        alt_ft = 0.0

    # integer km distance string
    dist = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)
    dist_str = "--" if math.isnan(dist) else str(int(dist + 0.5))

    # callsign (up to 7 raw chars)
    flt_raw = (ac.get("flight") or "????").strip()[:7]

    # 4-char type code
    raw_type = (ac.get("t") or "").strip().upper()
    if not raw_type:
        type_code = "????"
    elif len(raw_type) >= 4:
        type_code = raw_type[:4]
    else:
        type_code = raw_type + "?" * (4 - len(raw_type))

    # Base string
    base = f"{flt_raw} {dist_str}km {type_code}"

    # If too long, truncate callsign until fits
    while len(base) > 16 and len(flt_raw) > 1:
        flt_raw = flt_raw[:-1]
        base = f"{flt_raw} {dist_str}km {type_code}"

    # If shorter than 16 → center it
    if len(base) < 16:
        pad_total = 16 - len(base)
        left_pad = pad_total // 2
        right_pad = pad_total - left_pad
        line1 = " " * left_pad + base + " " * right_pad
    else:
        line1 = base[:16]

    # metric altitude & speed (always left aligned)
    alt_m  = ft_to_m(alt_ft)
    gs_kmh = kn_to_kmh(gs_kn)
    line2  = f"{int(alt_m+0.5):5d}m {int(gs_kmh+0.5):3d}km/h"
    line2  = pad16(line2)

    return line1, line2



def format_console(ac):
    # unchanged verbose log
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
    return requests.get(api_url()).json()

while True:
    try:
        data = fetch_closest()
        now  = time.localtime()
        timestr = f"{now[3]:02d}:{now[4]:02d}:{now[5]:02d}"

        if data and data.get("ac"):
            ac = data["ac"][0]
            lat = to_float(ac.get("lat"))
            lon = to_float(ac.get("lon"))
            dist = gc_distance_km(LATITUDE, LONGITUDE, lat, lon)

            if math.isnan(dist) or dist > DISPLAY_RADIUS_KM:
                # no aircraft in display range
                lcd.clear()
                lcd.print("No planes within")
                lcd.set_cursor_pos(1, 0)
                lcd.print(f"{DISPLAY_RADIUS_KM}km | Scanning")
                print(timestr, f"No aircraft within {DISPLAY_RADIUS_KM} km")
            else:
                # show the nearest
                line1, line2 = format_lcd(ac)
                lcd.clear()
                lcd.print(line1)
                lcd.set_cursor_pos(1, 0)
                lcd.print(line2)
                print(timestr, format_console(ac))

        else:
            lcd.clear()
            lcd.print("No planes within")
            lcd.set_cursor_pos(1, 0)
            lcd.print(f"{DISPLAY_RADIUS_KM}km | Scanning")
            print(timestr, f"No aircraft within {DISPLAY_RADIUS_KM} km")

    except Exception as err:
        print("ERROR:", err)
        lcd.clear()
        lcd.print("API / Wi-Fi Err")
        lcd.set_cursor_pos(1, 0)
        lcd.print("Retrying...")
        time.sleep(5)

    time.sleep(POLL_SEC)
