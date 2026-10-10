"""Renders a Weather object into a 1200x825 black & white e-paper style frame."""
from __future__ import annotations

import datetime as dt
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

import icons
from weather import Weather

W, H = 1200, 825
INK, PAPER = 0, 255
M = 8  # outer margin

_REGULAR = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
_BOLD = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]

COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


# ---------------------------------------------------------------- helpers

@lru_cache(maxsize=None)
def F(size: int, bold: bool = False):
    for name in (_BOLD if bold else _REGULAR):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def text_w(d, s, font):
    l, _, r, _ = d.textbbox((0, 0), s, font=font)
    return r - l


def fit(d, s, max_w, size, bold=False, min_size=9):
    while size > min_size and text_w(d, s, F(size, bold)) > max_w:
        size -= 1
    return F(size, bold)


def panel(d, box, title=None, th=28):
    """Bordered box with optional title bar; returns the inner content box."""
    x0, y0, x1, y1 = box
    d.rectangle(box, outline=INK, width=2)
    if not title:
        return box
    d.line((x0, y0 + th, x1, y0 + th), fill=INK, width=2)
    d.text(((x0 + x1) / 2, y0 + th / 2 + 1), title, font=F(17, True), fill=INK, anchor="mm")
    return (x0, y0 + th, x1, y1)


@lru_cache(maxsize=None)
def _pattern(density: int):
    """Full-canvas ordered dither pattern: 2 = 50% grey, 4 = 25% grey."""
    rows = []
    for y in range(H):
        if density == 2:
            row = (b"\x00\xff" if y % 2 == 0 else b"\xff\x00") * (W // 2)
        else:
            row = (b"\x00\xff" * (W // 2)) if y % 2 == 0 else b"\xff" * W
        rows.append(row)
    return Image.frombytes("L", (W, H), b"".join(rows))


def hatch(img, polygon, density=2):
    mask = Image.new("1", img.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=1)
    img.paste(_pattern(density), (0, 0), mask)


def dashed_h(d, x0, x1, y, dash=4, gap=4, width=1):
    x = x0
    while x < x1:
        d.line((x, y, min(x + dash, x1), y), fill=INK, width=width)
        x += dash + gap


def dotted_v(d, x, y0, y1, step=4):
    for y in range(int(y0), int(y1), step):
        d.point((x, y), fill=INK)


def nice_ticks(lo, hi, n=4):
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 5, 10) if s * mag >= raw)
    v, end, ticks = math.floor(lo / step) * step, math.ceil(hi / step) * step, []
    while v <= end + step * 1e-6:
        ticks.append(round(v, 6))
        v += step
    return ticks, step


def compass_name(deg):
    return COMPASS16[int((deg % 360) / 22.5 + 0.5) % 16]


def fmt_num(v, nd=0, dash="--"):
    return dash if v is None else f"{v:.{nd}f}"


def moon_info(when: dt.datetime):
    ref = dt.datetime(2000, 1, 6, 18, 14)  # a known new moon (UTC)
    p = ((when - ref).total_seconds() / 86400 % 29.530588853) / 29.530588853
    names = [(0.0339, "New Moon"), (0.216, "Waxing Crescent"), (0.284, "First Quarter"),
             (0.466, "Waxing Gibbous"), (0.534, "Full Moon"), (0.716, "Waning Gibbous"),
             (0.784, "Last Quarter"), (0.966, "Waning Crescent"), (1.01, "New Moon")]
    return p, next(n for lim, n in names if p < lim)


def uv_label(uv):
    if uv is None:
        return ""
    return ("Low" if uv < 3 else "Moderate" if uv < 6 else "High" if uv < 8
            else "Very high" if uv < 11 else "Extreme")


# ---------------------------------------------------------------- sections

def header(d, wx: Weather, status):
    box = (M, M, W - M, 44)
    d.rectangle(box, outline=INK, width=2)
    loc = wx.location
    city = loc.name.upper() + (f", {loc.country}" if loc.country else "")
    d.text((W / 2, 27), city, font=fit(d, city, 600, 22, True), fill=INK, anchor="mm")
    d.text((M + 10, 27), "[Open-Meteo]", font=F(14, True), fill=INK, anchor="lm")
    right = status or f"{abs(loc.lat):.2f}°{'N' if loc.lat >= 0 else 'S'}  {abs(loc.lon):.2f}°{'E' if loc.lon >= 0 else 'W'}"
    d.text((W - M - 10, 27), right, font=F(14, True), fill=INK, anchor="rm")


def wind_panel(img, d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box, "Wind Speed/Direction")
    cur, u = wx.current, wx.units
    cx, cy, R = (x0 + x1) / 2, (y0 + y1) / 2 + 2, 100

    def pt(deg, r):
        a = math.radians(deg)
        return cx + r * math.sin(a), cy - r * math.cos(a)

    d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=INK, width=3)
    d.ellipse((cx - R * 0.74, cy - R * 0.74, cx + R * 0.74, cy + R * 0.74), outline=INK, width=1)
    for deg in range(0, 360, 10):
        big, mid = deg % 90 == 0, deg % 45 == 0
        d.line((*pt(deg, R - (14 if big else 9 if mid else 5)), *pt(deg, R)), fill=INK, width=2 if mid else 1)
    for k, lab in enumerate(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]):
        d.text(pt(k * 45, R + 17), lab, font=F(16 if k % 2 == 0 else 14, True), fill=INK, anchor="mm")

    direction = cur.get("wind_direction_10m")
    if direction is not None:
        tip, b1, b2 = pt(direction, R * 0.76), pt(direction - 8, R * 0.99), pt(direction + 8, R * 0.99)
        d.polygon([tip, b1, b2], fill=INK)
        d.text((cx, cy - 42), compass_name(direction), font=F(18, True), fill=INK, anchor="mm")
    speed = cur.get("wind_speed_10m")
    d.text((cx, cy - 4), fmt_num(speed), font=F(46, True), fill=INK, anchor="mm")
    d.text((cx, cy + 28), u["wind"], font=F(16), fill=INK, anchor="mm")
    gust = cur.get("wind_gusts_10m")
    extra = f"{fmt_num(direction)}°  gust {fmt_num(gust)}"
    d.text((cx, cy + 50), extra, font=F(14), fill=INK, anchor="mm")


def conditions_panel(img, d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box, "Conditions")
    cur, u = wx.current, wx.units
    cx = (x0 + x1) / 2
    ty = y0 + 20
    icons.eye(d, x0 + 14, ty)
    vis = cur.get("visibility")
    d.text((x0 + 42, ty), f"{fmt_num(vis, 0 if (vis or 0) >= 10 else 1)} {u['vis']}", font=F(16, True), fill=INK, anchor="lm")
    icons.cloud(d, x1 - 92, ty, 30, 2)
    d.text((x1 - 72, ty), f"{fmt_num(cur.get('cloud_cover'))}%", font=F(16, True), fill=INK, anchor="lm")

    icons.draw_icon(img, cur.get("weather_code"), cx, y0 + 110, 142, bool(cur.get("is_day", 1)))

    hum = f"{fmt_num(cur.get('relative_humidity_2m'))}%"
    f = F(34, True)
    hw = text_w(d, hum, f)
    d.text((cx - 12, y1 - 50), hum, font=f, fill=INK, anchor="mm")
    d.text((cx - 12 + hw / 2 + 8, y1 - 44), "RH", font=F(16, True), fill=INK, anchor="lm")
    d.text((cx, y1 - 18), f"Dew point {fmt_num(cur.get('dew_point'))}°", font=F(14), fill=INK, anchor="mm")


def temperature_cell(d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box, "Temperature")
    cur, day = wx.current, wx.daily
    cx = (x0 + x1) / 2
    t = f"{fmt_num(cur.get('temperature_2m'), 1)}°"
    f = F(52, True)
    tw = text_w(d, t, f)
    d.text((cx - 10, y0 + 42), t, font=f, fill=INK, anchor="mm")
    d.text((cx - 10 + tw / 2 + 6, y0 + 52), wx.units["temp"], font=F(22), fill=INK, anchor="lm")
    hi, lo = day["temperature_2m_max"][0], day["temperature_2m_min"][0]
    d.text((cx, y0 + 88), f"{fmt_num(hi)}°  |  {fmt_num(lo)}°", font=F(20, True), fill=INK, anchor="mm")
    d.text((cx, y0 + 114), f"Feels like {fmt_num(cur.get('apparent_temperature'))}°", font=F(15), fill=INK, anchor="mm")


def pressure_cell(d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box, "Pressure")
    cx = (x0 + x1) / 2
    p = wx.current.get("pressure_msl")
    d.text((cx - 18, y0 + 42), fmt_num(p), font=F(48, True), fill=INK, anchor="mm")
    d.text((x1 - 12, y0 + 52), "hPa", font=F(16), fill=INK, anchor="rm")
    old = wx.pressure_3h_ago
    delta = None if (p is None or old is None) else p - old
    if delta is None:
        word = "--"
    else:
        word = "Rising" if delta > 0.5 else "Falling" if delta < -0.5 else "Steady"
    tx = cx + 10
    d.text((tx, y0 + 88), word, font=F(20, True), fill=INK, anchor="mm")
    ax = tx - text_w(d, word, F(20, True)) / 2 - 16
    ay = y0 + 88
    if word == "Rising":
        d.polygon([(ax, ay - 8), (ax - 7, ay + 5), (ax + 7, ay + 5)], fill=INK)
    elif word == "Falling":
        d.polygon([(ax, ay + 8), (ax - 7, ay - 5), (ax + 7, ay - 5)], fill=INK)
    elif word == "Steady":
        d.polygon([(ax + 8, ay), (ax - 5, ay - 7), (ax - 5, ay + 7)], fill=INK)
    if delta is not None:
        d.text((cx, y0 + 114), f"{delta:+.1f} hPa in 3 h", font=F(15), fill=INK, anchor="mm")


def precip_cell(d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box, "Precipitation")
    cx = (x0 + x1) / 2
    u = wx.units
    total = wx.daily["precipitation_sum"][0]
    nd = 2 if u["rain"] == "in" else 1
    val = fmt_num(total, nd)
    f = F(44, True)
    vw = text_w(d, val, f)
    d.text((cx - 14, y0 + 42), val, font=f, fill=INK, anchor="mm")
    d.text((cx - 14 + vw / 2 + 6, y0 + 52), f"{u['rain']} today", font=F(15), fill=INK, anchor="lm")
    prob = wx.daily["precipitation_probability_max"][0]
    d.text((cx, y0 + 88), f"Chance {fmt_num(prob)}%", font=F(20, True), fill=INK, anchor="mm")

    rain, pp = wx.hourly["precipitation"][:24], wx.hourly["precipitation_probability"][:24]
    threshold = 0.004 if u["rain"] == "in" else 0.1
    nxt = next((i for i, (r, q) in enumerate(zip(rain, pp)) if (r or 0) >= threshold and (q or 0) >= 40), None)
    msg = "Dry next 24 h" if nxt is None else "Rain now" if nxt == 0 else f"Rain expected in {nxt} h"
    d.text((cx, y0 + 114), msg, font=F(15), fill=INK, anchor="mm")


def summary_bar(d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box)
    cy = (y0 + y1) / 2
    desc = icons.describe(wx.current.get("weather_code"))
    uv = wx.current.get("uv_index")
    right = f"UV {uv:g} {uv_label(uv)}" if uv is not None else ""
    rf = F(18, True)
    d.text((x1 - 14, cy), right, font=rf, fill=INK, anchor="rm")
    d.text((x0 + 14, cy), desc, font=fit(d, desc, x1 - x0 - text_w(d, right, rf) - 50, 28, True), fill=INK, anchor="lm")


def date_block(d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box)
    cx = (x0 + x1) / 2
    d.text((cx, y0 + 30), wx.now.strftime("%a %d-%b-%Y"), font=F(30, True), fill=INK, anchor="mm")
    d.text((cx, y1 - 22), f"Updated: {wx.fetched_at:%H:%M:%S}", font=F(19), fill=INK, anchor="mm")


def sun_moon_block(img, d, wx: Weather, box):
    x0, y0, x1, y1 = panel(d, box)
    rise, sset = wx.daily["sunrise"][0], wx.daily["sunset"][0]
    phase, name = moon_info(wx.now)
    length = sset - rise
    hrs, mins = divmod(int(length.total_seconds() // 60), 60)
    f = F(15, True)
    for k, line in enumerate([f"{rise:%H:%M}  Sunrise", f"{sset:%H:%M}  Sunset", f"{hrs}h {mins:02d}m  Daylight", name]):
        d.text((x0 + 12, y0 + 14 + k * 19), line, font=f, fill=INK, anchor="lm")
    icons.moon_phase(img, x1 - 44, (y0 + y1) / 2, 30, phase, south=wx.location.lat < 0)


def hourly_strip(img, d, wx: Weather, y0, y1, n=12, step=3):
    hr, u = wx.hourly, wx.units
    gap = 4
    cw = (W - 2 * M - gap * (n - 1)) / n
    for k in range(n):
        i = 1 + k * step
        if i >= len(hr["time"]):
            break
        x0 = M + k * (cw + gap)
        x1 = x0 + cw
        d.rectangle((x0, y0, x1, y1), outline=INK, width=2)
        d.line((x0, y0 + 24, x1, y0 + 24), fill=INK, width=2)
        cx = (x0 + x1) / 2
        d.text((cx, y0 + 13), hr["time"][i].strftime("%H:%M"), font=F(16, True), fill=INK, anchor="mm")
        icons.draw_icon(img, hr["weather_code"][i], cx, y0 + 57, 62, bool(hr["is_day"][i]))
        d.text((cx, y1 - 32), f"{fmt_num(hr['temperature_2m'][i])}°", font=F(19, True), fill=INK, anchor="mm")
        rain = hr["precipitation"][i]
        rain_s = fmt_num(rain, 2 if u["rain"] == "in" else 1)
        line = f"{rain_s}{u['rain']}  {fmt_num(hr['precipitation_probability'][i])}%"
        d.text((cx, y1 - 13), line, font=fit(d, line, cw - 8, 13), fill=INK, anchor="mm")


def daily_strip(img, d, wx: Weather, y0, y1):
    dy, u = wx.daily, wx.units
    n = min(7, len(dy["time"]))
    gap = 4
    cw = (W - 2 * M - gap * (n - 1)) / n
    for k in range(n):
        x0 = M + k * (cw + gap)
        x1 = x0 + cw
        d.rectangle((x0, y0, x1, y1), outline=INK, width=2)
        d.line((x0, y0 + 24, x1, y0 + 24), fill=INK, width=2)
        day = dy["time"][k]
        label = "Today" if k == 0 else "Tomorrow" if k == 1 else day.strftime("%A")
        d.text(((x0 + x1) / 2, y0 + 13), label, font=F(16, True), fill=INK, anchor="mm")
        icons.draw_icon(img, dy["weather_code"][k], x0 + 44, (y0 + 24 + y1) / 2, 70, True)
        tx, tw = x0 + 86, cw - 92
        hl = f"{fmt_num(dy['temperature_2m_max'][k])}° / {fmt_num(dy['temperature_2m_min'][k])}°"
        d.text((tx, y0 + 48), hl, font=fit(d, hl, tw, 22, True), fill=INK, anchor="lm")
        rain = f"{fmt_num(dy['precipitation_sum'][k], 2 if u['rain'] == 'in' else 1)} {u['rain']}  {fmt_num(dy['precipitation_probability_max'][k])}%"
        d.text((tx, y0 + 76), rain, font=fit(d, rain, tw, 15), fill=INK, anchor="lm")
        extra = f"UV {fmt_num(dy['uv_index_max'][k])}  {fmt_num(dy['wind_speed_10m_max'][k])} {u['wind']}"
        d.text((tx, y0 + 98), extra, font=fit(d, extra, tw, 14), fill=INK, anchor="lm")


def chart(img, d, box, title, times, values, mode="line", fixed=None, decimals=None, avg_decimals=0):
    x0, y0, x1, y1 = box
    px0, py0, px1, py1 = x0 + 44, y0 + 24, x1 - 10, y1 - 24
    n = len(values)
    vals = [v for v in values if v is not None]
    if mode == "bars":
        sums = [sum(v or 0 for v in values[g:g + 3]) for g in range(0, n, 3)]
        vals = sums
        lo, hi = 0, max(max(sums or [0]), fixed or 1)
        ticks, step = nice_ticks(lo, hi)
    elif fixed:
        ticks, step = list(range(fixed[0], fixed[1] + 1, (fixed[1] - fixed[0]) // 4)), (fixed[1] - fixed[0]) // 4
    else:
        ticks, step = nice_ticks(min(vals or [0]), max(vals or [1]))
    lo, hi = ticks[0], ticks[-1]
    nd = decimals if decimals is not None else next(k for k in range(4) if abs(step * 10 ** k - round(step * 10 ** k)) < 1e-6)

    def X(i):
        return px0 + (px1 - px0) * i / max(n - 1, 1)

    def Y(v):
        return py1 - (py1 - py0) * (v - lo) / (hi - lo)

    # title with the average of the plotted period
    avg = sum(vals) / len(vals) if vals else None
    label = f"{title}  avg {fmt_num(avg, avg_decimals)}"
    d.text(((x0 + x1) / 2, y0 + 9), label, font=fit(d, label, x1 - x0 - 8, 15, True), fill=INK, anchor="mm")

    lf = F(13)
    for t in ticks:
        y = Y(t)
        if t not in (lo, hi):
            dashed_h(d, px0, px1, y)
        d.text((px0 - 5, y), f"{t:.{nd}f}", font=lf, fill=INK, anchor="rm")
    for i, t in enumerate(times[:n]):
        if t.hour == 0 and 0 < i:
            dotted_v(d, X(i), py0, py1)
            d.line((X(i), py1, X(i), py1 + 5), fill=INK, width=2)
        if t.hour == 12:
            d.text((X(i), py1 + 12), t.strftime("%a"), font=lf, fill=INK, anchor="mm")

    if mode == "bars":
        bw = (px1 - px0) / len(sums)
        for g, s in enumerate(sums):
            if s <= 0:
                continue
            bx0, bx1, by = px0 + g * bw + 1, px0 + (g + 1) * bw - 1, Y(s)
            hatch(img, [(bx0, by), (bx1, by), (bx1, py1), (bx0, py1)], 2)
            d.rectangle((bx0, by, bx1, py1), outline=INK, width=1)
    else:
        pts = [(X(i), Y(v)) for i, v in enumerate(values) if v is not None]
        if mode == "area" and len(pts) > 1:
            hatch(img, [(pts[0][0], py1), *pts, (pts[-1][0], py1)], 4)
        if len(pts) > 1:
            d.line(pts, fill=INK, width=2, joint="curve")

    # average line + tag
    if avg is not None:
        ay = Y(avg)
        dashed_h(d, px0, px1, ay, dash=10, gap=5, width=2)
        tf = F(11, True)
        tw = text_w(d, "avg", tf) + 8
        ty = min(max(ay, py0 + 8), py1 - 8)
        d.rectangle((px1 - 2 - tw, ty - 7, px1 - 2, ty + 7), fill=INK)
        d.text((px1 - 2 - tw / 2, ty), "avg", font=tf, fill=PAPER, anchor="mm")
    d.rectangle((px0, py0, px1, py1), outline=INK, width=2)


def charts(img, d, wx: Weather, y0, y1, hours=72):
    hr, u = wx.hourly, wx.units
    d.text((W / 2, y0 + 10), f"{hours // 24}-Day Forecast Values", font=F(19, True), fill=INK, anchor="mm")
    times = hr["time"][:hours]
    specs = [
        (f"Temp (°{u['temp']})", hr["temperature_2m"], "line", None, None, 1),
        ("Humidity (%)", hr["relative_humidity_2m"], "line", (0, 100), 0, 0),
        ("Pressure (hPa)", hr["pressure_msl"], "line", None, 0, 0),
        (f"Rain ({u['rain']}/3h)", hr["precipitation"], "bars", 0.04 if u["rain"] == "in" else 1, None, 2),
        ("Clouds (%)", hr["cloud_cover"], "area", (0, 100), 0, 0),
    ]
    cw = (W - 2 * M) / len(specs)
    for k, (title, values, mode, fixed, nd, avg_nd) in enumerate(specs):
        x0 = M + k * cw
        chart(img, d, (x0, y0 + 24, x0 + cw, y1), title, times, values[:hours], mode, fixed, nd, avg_nd)


# ---------------------------------------------------------------- entry points

def render(wx: Weather, status: str | None = None) -> Image.Image:
    img = Image.new("L", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    header(d, wx, status)
    wind_panel(img, d, wx, (M, 44, 300, 340))
    conditions_panel(img, d, wx, (300, 44, 556, 340))
    temperature_cell(d, wx, (556, 44, 776, 204))
    pressure_cell(d, wx, (776, 44, 984, 204))
    precip_cell(d, wx, (984, 44, W - M, 204))
    summary_bar(d, wx, (556, 204, W - M, 254))
    date_block(d, wx, (556, 254, 912, 340))
    sun_moon_block(img, d, wx, (912, 254, W - M, 340))
    hourly_strip(img, d, wx, 348, 476)
    daily_strip(img, d, wx, 484, 612)
    charts(img, d, wx, 616, H - M)
    return img


def render_message(title: str, detail: str = "") -> Image.Image:
    img = Image.new("L", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle((M, M, W - M, H - M), outline=INK, width=2)
    icons.draw_icon(img, 3, W / 2, H / 2 - 120, 160)
    d.text((W / 2, H / 2 + 10), title, font=F(34, True), fill=INK, anchor="mm")
    for k, line in enumerate(detail.splitlines()[:6]):
        d.text((W / 2, H / 2 + 60 + k * 26), line, font=fit(d, line, W - 80, 18), fill=INK, anchor="mm")
    return img


def to_1bit(img: Image.Image) -> Image.Image:
    """Hard threshold for real e-paper hardware (keeps text crisp, patterns intact)."""
    return img.point(lambda v: 255 if v > 140 else 0).convert("1", dither=Image.Dither.NONE)
