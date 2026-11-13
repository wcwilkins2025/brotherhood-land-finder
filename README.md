# Brotherhood Land Finder

A free, public, static web page that scores every US county (3,144 counties and
equivalents in the 50 states and DC) for a self-sustaining rural life, and gives a
per-county link kit for the records check you must do before you sign.

Live page: https://wcwilkins2025.github.io/brotherhood-land-finder/

- No login, no tracking, nothing stored about anyone. No member data of any kind.
- One HTML file plus the data files it loads. Hosted on GitHub Pages. Free forever.
- Every number comes from a public dataset; every county panel names its source.
  Where a source has no figure, the page says "no data". Nothing is estimated.

## What is in it

| Piece | Where |
|---|---|
| The page | `index.html` (sliders, "near me" search, US county map, ranked list, county detail, link kit, "Read this before you sign") |
| County data | `data/counties.json` (one row per county, ~50 fields, plus a state-law block) |
| Map shapes | `data/counties.geojson` (Census cartographic boundaries, 1:20m, 3-decimal coordinates) |
| Town and ZIP lookups for "near me" | `data/places.json`, `data/zips.json` |
| Build pipeline | `data/fetch_all.sh` (downloads), `data/build.py` (joins everything on FIPS) |
| Hand-gathered inputs | `data/manual/` (state laws, zoning by state and county, Amish settlements, public land) |
| Every dataset, date and URL | `data/sources.md` |

## Rebuilding the data

```bash
sh data/fetch_all.sh       # downloads ~600 MB of public files into ./downloads (gitignored)
python -I data/build.py    # writes data/counties.json, counties.geojson, places.json, zips.json
python -m http.server 8000 # then open http://localhost:8000/
```

Only the Python standard library is needed, plus `pyshp` for the boundary file.
No API keys and no accounts; anything that needed one was left out and is listed
in `data/sources.md` under "Not included".

## How the score works

Each factor becomes a 0 to 1 score per county (for example land under $2,000 an
acre scores 1 and land over $10,000 scores 0). The sliders weight the factors
Off / Low / Medium / High (0 / 1 / 2 / 3). The county score is the weighted
average times 100. A factor with no data for a county is left out of that
county's average rather than counted as zero, and the panel says which ones.

Zoning is scored three ways: counties confirmed from the county's own site or
an official state list (checkmark), counties settled by state law (Texas
counties cannot zone; Oregon and Washington require zoning everywhere), and
everything else marked "verify" and scored from the state's general pattern.

## Contributing a correction

Open an issue with the county, what is wrong, and a link to the county's own
page that shows the right answer. Zoning corrections go in
`data/manual/zoning_XX.json` with the URL you confirmed from.

## License

Code: MIT. Data: each source keeps its own terms; all are US government or
publicly posted academic datasets. See `data/sources.md`.
