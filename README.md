# WeatherPanel

**Live demo:** https://gleisoncs.github.io/weatherPanel/

E-paper style weather station in Python. Draws a 1200x825 black & white frame
(boxed panels, line-art icons, dithered charts) and shows it in a window that
looks and refreshes like an e-paper display. Data comes from
[Open-Meteo](https://open-meteo.com), which is free and needs no API key.

## Panels
- Wind compass: speed, direction, gusts
- Conditions: icon, visibility, cloud cover, humidity, dew point
- Temperature (now, max/min, feels like), pressure with 3 h trend, precipitation (today's total, chance, next rain)
- Description and UV index, date, last update time, sunrise/sunset, day length, moon phase
- Hourly strip: 36 h in 3 h steps (icon, temperature, rain mm, rain chance)
- 7-day forecast: icon, max/min, rain, chance, UV, max wind
- 3-day charts: temperature, humidity, pressure, rainfall (mm per 3 h), cloud cover,
  each with its average over the period (in the title and as a dashed `avg` line)

## Web version (index.html)
`index.html` is a standalone page with the same layout, drawn on a canvas. The browser fetches
Open-Meteo directly, so no server code is needed: upload the file to any static host
(GitHub Pages, Netlify, Cloudflare Pages, nginx, ...) or run locally with
`python -m http.server` and open http://localhost:8000.

URL parameters: `?city=Lisbon`, `?lat=-23.55&lon=-46.63&name=Sao%20Paulo`, `&units=imperial`,
`&refresh=10` (minutes), `&demo=1`. The page also has a city box, a "My location" button
and a units selector. Keys: `R` refresh, `F` fullscreen.

## Run
```
pip install -r requirements.txt
python app.py --city "Berlin"
python app.py --lat -23.55 --lon -46.63 --name "Sao Paulo" --units imperial
python app.py --demo                         # offline, synthetic data
python app.py --city Lisbon --once out.png   # one frame to a file
python app.py --city Lisbon --once out.png --bw   # 1-bit PNG for real e-paper hardware
```
Window keys: `R` refresh now, `S` save PNG, `F`/`F11` fullscreen, `Q`/`Esc` quit.
Options: `--refresh MIN` (default 15), `--no-flash`.

## Files
- `weather.py`: geocoding, forecast fetch and parse, demo data
- `icons.py`: weather icons drawn with Pillow (WMO codes)
- `render.py`: layout and drawing of the frame
- `app.py`: command line and Tkinter viewer
- `index.html`: web version (HTML + JavaScript, no dependencies)
