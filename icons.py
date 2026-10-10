"""Line-art weather icons drawn with Pillow primitives (e-paper style, ink on paper)."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

INK, PAPER = 0, 255

WMO_TEXT = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def describe(code) -> str:
    return WMO_TEXT.get(code, "Unknown")


def classify(code):
    """WMO code -> (kind, intensity 1..3, is_shower)."""
    c = code if code is not None else 0
    if c == 0:
        return "clear", 1, False
    if c == 1:
        return "mostly_clear", 1, False
    if c == 2:
        return "partly", 1, False
    if c == 3:
        return "overcast", 1, False
    if c in (45, 48):
        return "fog", 1, False
    if c in (51, 53, 55):
        return "drizzle", (51, 53, 55).index(c) + 1, False
    if c in (56, 57, 66, 67):
        return "sleet", 2, False
    if c in (61, 63, 65):
        return "rain", (61, 63, 65).index(c) + 1, False
    if c in (71, 73, 75, 77):
        return "snow", min((71, 73, 75, 77).index(c) + 1, 3), False
    if c in (80, 81, 82):
        return "rain", (80, 81, 82).index(c) + 1, True
    if c in (85, 86):
        return "snow", (85, 86).index(c) + 2, True
    if c >= 95:
        return "thunder", 3, False
    return "overcast", 1, False


def _circle(d, cx, cy, r, **kw):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), **kw)


def sun(d, cx, cy, r, lw):
    _circle(d, cx, cy, r, fill=PAPER, outline=INK, width=lw)
    for k in range(8):
        a = k * math.pi / 4
        ca, sa = math.cos(a), math.sin(a)
        d.line((cx + ca * r * 1.4, cy + sa * r * 1.4, cx + ca * r * 1.85, cy + sa * r * 1.85), fill=INK, width=lw)


def moon(img, cx, cy, r):
    """Solid crescent moon."""
    size = int(r * 2) + 2
    mask = Image.new("1", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((1, 1, size - 2, size - 2), fill=1)
    off_x, off_y, rr = r * 0.55, -r * 0.35, r * 0.85
    c = size / 2
    md.ellipse((c + off_x - rr, c + off_y - rr, c + off_x + rr, c + off_y + rr), fill=0)
    img.paste(INK, (int(cx - size / 2), int(cy - size / 2)), mask)


# Cloud silhouette in units of its width, centred on (0, 0).
_CLOUD = [
    ("c", -0.22, 0.05, 0.19),
    ("c", 0.06, -0.03, 0.25),
    ("c", 0.30, 0.09, 0.16),
    ("r", -0.48, 0.03, 0.48, 0.27, 0.12),
]


def cloud(d, cx, cy, w, lw, fill=PAPER):
    """Outlined cloud. Drawing a fat ink pass then a paper pass gives a clean outline of the union."""
    for grow, colour in ((lw, INK), (0, fill)):
        for shape in _CLOUD:
            if shape[0] == "c":
                _, x, y, r = shape
                _circle(d, cx + x * w, cy + y * w, r * w + grow, fill=colour)
            else:
                _, x0, y0, x1, y1, rad = shape
                d.rounded_rectangle((cx + x0 * w - grow, cy + y0 * w - grow, cx + x1 * w + grow, cy + y1 * w + grow),
                                    radius=rad * w + grow, fill=colour)


def _flake(d, x, y, f, lw):
    for k in range(3):
        a = k * math.pi / 3 + math.pi / 2
        d.line((x - math.cos(a) * f, y - math.sin(a) * f, x + math.cos(a) * f, y + math.sin(a) * f), fill=INK, width=lw)


def _precip(d, kind, intensity, cx, cy, s, lw):
    """Precipitation marks below a cloud whose bottom sits near cy + 0.09 s."""
    n = 2 + intensity if kind != "drizzle" else 3
    gap = s * 0.16
    xs = [cx + (k - (n - 1) / 2) * gap for k in range(n)]
    for k, x in enumerate(xs):
        y0 = cy + s * 0.17 + (k % 2) * s * 0.07
        if kind == "rain" or (kind == "sleet" and k % 2 == 0) or kind == "thunder":
            if kind == "thunder" and abs(x - cx) < gap * 0.6:
                continue
            d.line((x + s * 0.04, y0, x - s * 0.03, y0 + s * 0.15), fill=INK, width=lw)
        elif kind == "drizzle":
            for j in range(intensity if intensity > 1 else 1):
                _circle(d, x, y0 + j * s * 0.09 + s * 0.03, max(1.5, lw * 0.9), fill=INK)
        else:  # snow / sleet flakes
            _flake(d, x, y0 + s * 0.07, s * 0.055, max(1, lw - 1))
    if kind == "thunder":
        u = s
        pts = [(0.05, 0.02), (-0.07, 0.22), (0.0, 0.22), (-0.05, 0.42), (0.11, 0.16), (0.03, 0.16), (0.10, 0.02)]
        d.polygon([(cx + x * u, cy + y * u) for x, y in pts], fill=INK)


def draw_icon(img, code, cx, cy, s, is_day=True):
    """Draw the icon for WMO `code` centred at (cx, cy) inside an s x s box."""
    d = ImageDraw.Draw(img)
    lw = max(2, round(s / 28))
    kind, intensity, shower = classify(code)

    if kind == "clear":
        if is_day:
            sun(d, cx, cy, s * 0.2, lw)
        else:
            moon(img, cx, cy, s * 0.28)
    elif kind in ("mostly_clear", "partly"):
        if is_day:
            sun(d, cx - s * 0.12, cy - s * 0.12, s * 0.15, lw)
        else:
            moon(img, cx - s * 0.12, cy - s * 0.14, s * 0.2)
        cw = s * (0.5 if kind == "mostly_clear" else 0.68)
        cloud(d, cx + s * 0.1, cy + s * 0.14, cw, lw)
    elif kind == "overcast":
        cloud(d, cx + s * 0.14, cy - s * 0.1, s * 0.52, lw)
        cloud(d, cx - s * 0.06, cy + s * 0.08, s * 0.74, lw)
    elif kind == "fog":
        cloud(d, cx, cy - s * 0.14, s * 0.7, lw)
        for k, y in enumerate((0.16, 0.26, 0.36)):
            off = s * (0.06 if k % 2 else -0.04)
            d.line((cx - s * 0.32 + off, cy + y * s, cx + s * 0.28 + off, cy + y * s), fill=INK, width=lw)
    else:
        if shower:
            if is_day:
                sun(d, cx - s * 0.2, cy - s * 0.24, s * 0.12, lw)
            else:
                moon(img, cx - s * 0.2, cy - s * 0.24, s * 0.15)
        cloud(d, cx, cy - s * 0.12, s * 0.78, lw)
        _precip(d, kind, intensity, cx, cy, s, lw)


def eye(d, x, cy, w=22):
    h = w * 0.55
    d.ellipse((x, cy - h / 2, x + w, cy + h / 2), outline=INK, width=2)
    _circle(d, x + w / 2, cy, w * 0.18, fill=INK)


def moon_phase(img, cx, cy, r, phase, south=False):
    """Moon disc with the lit part in paper and the shadow in ink. phase: 0=new, .5=full."""
    d = ImageDraw.Draw(img)
    _circle(d, cx, cy, r, fill=INK)
    c = math.cos(2 * math.pi * phase)
    for yy in range(-r, r + 1):
        hw = math.sqrt(max(r * r - yy * yy, 0))
        xa, xb = (hw * c, hw) if phase <= 0.5 else (-hw, -hw * c)
        if south:
            xa, xb = -xb, -xa
        if xb > xa:
            d.line((cx + xa, cy + yy, cx + xb, cy + yy), fill=PAPER)
    _circle(d, cx, cy, r, outline=INK, width=2)
