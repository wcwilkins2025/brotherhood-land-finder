"""Principal aquifers of the United States (USGS, 2003 edition, shapefile dated 2015-03-16)
-> data/aquifers.json, a simplified GeoJSON the parcel page uses for a point-in-polygon lookup.

Source: https://water.usgs.gov/GIS/dsdl/aquifers_us.zip (unzipped into downloads/aquifers/).
Polygons named "Other rocks" are where no principal aquifer is mapped; they are dropped, so a point
that matches nothing means "no principal aquifer mapped here".

Run:  python -I data/build_aquifers.py
"""
import json, os, sys
import shapefile  # pyshp

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'downloads', 'aquifers', 'us_aquifers.shp')
OUT = os.path.join(HERE, 'aquifers.json')
TOL = 0.01  # degrees, about 1 km; the source map is 1:2,500,000, so this loses nothing real


def dp(points, tol):
    """Douglas-Peucker on a ring of (x, y)."""
    if len(points) < 5:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    best, bi = 0.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if L == 0:
            d = (px - x1) ** 2 + (py - y1) ** 2
        else:
            t = ((px - x1) * dx + (py - y1) * dy) / L
            t = 0 if t < 0 else 1 if t > 1 else t
            d = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
        if d > best:
            best, bi = d, i
    if best > tol * tol:
        return dp(points[:bi + 1], tol)[:-1] + dp(points[bi:], tol)
    return [points[0], points[-1]]


def simplify_ring(ring):
    pts = [(round(x, 3), round(y, 3)) for x, y in ring]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    # split the closed ring at a far point so DP keeps its shape
    mid = len(pts) // 2
    a = dp(pts[:mid + 1], TOL)
    b = dp(pts[mid:], TOL)
    out = a[:-1] + b
    return out if len(out) >= 4 else None


def main():
    r = shapefile.Reader(SRC)
    feats, dropped = [], 0
    for sr in r.iterShapeRecords():
        rec = sr.record
        name = (rec['AQ_NAME'] or '').strip()
        if not name or name == 'Other rocks':
            dropped += 1
            continue
        shp = sr.shape
        parts = list(shp.parts) + [len(shp.points)]
        rings = []
        for i in range(len(parts) - 1):
            ring = simplify_ring(shp.points[parts[i]:parts[i + 1]])
            if ring:
                rings.append([[x, y] for x, y in ring])
        if not rings:
            continue
        # pyshp gives outer rings clockwise and holes counter-clockwise; keep them all in one
        # MultiPolygon-like list and let the point test count crossings over every ring.
        feats.append({'type': 'Feature', 'properties': {'name': name, 'rock': (rec['ROCK_NAME'] or '').strip(), 'code': rec['AQ_CODE']},
                      'geometry': {'type': 'Polygon', 'coordinates': rings}})
    out = {'type': 'FeatureCollection', 'source': 'USGS Principal Aquifers of the United States, aquifers_us.zip (2003 edition; file dated 2015-03-16)',
           'url': 'https://water.usgs.gov/GIS/dsdl/aquifers_us.zip', 'simplified_deg': TOL, 'features': feats}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f'{len(feats)} aquifer polygons kept, {dropped} "Other rocks" dropped, {os.path.getsize(OUT)//1024} KB')


if __name__ == '__main__':
    main()
