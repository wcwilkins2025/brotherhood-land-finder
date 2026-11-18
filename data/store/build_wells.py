"""Land Finder's own copy of the USGS well list, refreshed monthly.

Pulls every groundwater monitoring location (well depth, aquifer) and the latest depth-to-water
measurement (parameter 72019) for each state from the USGS Water Data API, plus the aquifer code
names, and writes 1-degree cells as gzip JSON so the parcel check reads only the cells near a spot.

  python -I data/store/build_wells.py            # all states
  python -I data/store/build_wells.py 48 29      # these state FIPS codes (testing)

Output: downloads/store/out/wells/<lat>_<lon>.json (gzip), index.json, aquifers.json (gzip).
"""
import gzip, json, math, os, shutil, sys, time, urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(ROOT, 'downloads', 'store', 'out', 'wells')
API = 'https://api.waterdata.usgs.gov/ogcapi/v0/collections'
STATES = ['01', '02', '04', '05', '06', '08', '09', '10', '11', '12', '13', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26',
          '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '40', '41', '42', '44', '45', '46', '47', '48', '49', '50',
          '51', '53', '54', '55', '56']


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def pages(url):
    while url:
        for k in range(5):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'land-finder-data (monthly well refresh)'})
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                break
            except Exception as e:
                if k == 4:
                    raise
                time.sleep(15 * (k + 1))
        yield d.get('features') or []
        url = next((l['href'] for l in d.get('links', []) if l.get('rel') == 'next'), None)
        time.sleep(0.5)


def num(v):
    try:
        x = float(v)
        return None if math.isnan(x) else (int(x) if x.is_integer() else round(x, 1))
    except (TypeError, ValueError):
        return None


def main(args):
    states = [a for a in args if a.isdigit()] or STATES
    wells = {}
    for st in states:
        n0 = len(wells)
        props = 'monitoring_location_number,monitoring_location_name,well_constructed_depth,hole_constructed_depth,aquifer_code,county_name,state_code'
        for feats in pages(f'{API}/monitoring-locations/items?site_type_code=GW&state_code={st}&limit=10000&f=json&properties={props}'):
            for f in feats:
                g = f.get('geometry') or {}
                c = g.get('coordinates')
                if not c:
                    continue
                p = f['properties']
                wells[p['monitoring_location_number']] = [p['monitoring_location_number'], p.get('monitoring_location_name'), round(c[1], 5), round(c[0], 5),
                                                          num(p.get('well_constructed_depth')), num(p.get('hole_constructed_depth')), p.get('aquifer_code'),
                                                          p.get('county_name'), p.get('state_code'), None, None]
        levels = 0
        for feats in pages(f'{API}/latest-field-measurements/items?parameter_code=72019&state_code={st}&limit=10000&f=json&properties=monitoring_location_id,value,time&skipGeometry=true'):
            for f in feats:
                p = f['properties']
                wid = (p.get('monitoring_location_id') or '').split('-', 1)[-1]
                w = wells.get(wid)
                v = num(p.get('value'))
                if w is not None and v is not None and (w[10] is None or (p.get('time') or '') > w[10]):
                    w[9] = v; w[10] = (p.get('time') or '')[:10]; levels += 1
        log(f'state {st}: {len(wells) - n0} wells, {levels} with a water level')
    # aquifer code names
    names = {}
    for feats in pages(f'{API}/aquifer-codes/items?limit=10000&f=json'):
        for f in feats:
            names[f['properties']['id']] = f['properties'].get('aquifer_name')
    used = {w[6] for w in wells.values() if w[6]}
    # 1-degree cells
    cells = {}
    for w in wells.values():
        cells.setdefault(f'{math.floor(w[2])}_{math.floor(w[3])}', []).append(w)
    tmp = OUT + '.part'
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    total = 0
    for k, ws in cells.items():
        b = gzip.compress(json.dumps(ws, separators=(',', ':')).encode(), 9)
        open(os.path.join(tmp, f'{k}.json'), 'wb').write(b); total += len(b)
    open(os.path.join(tmp, 'aquifers.json'), 'wb').write(gzip.compress(json.dumps({k: v for k, v in names.items() if k in used}, separators=(',', ':')).encode(), 9))
    json.dump({'version': 1, 'built': time.strftime('%Y-%m-%d'), 'source': 'USGS Water Data API (monitoring-locations GW, latest-field-measurements 72019, aquifer-codes)',
               'cols': ['id', 'name', 'lat', 'lon', 'depth', 'hole', 'aquifer', 'county', 'state', 'level_ft', 'level_date'],
               'wells': len(wells), 'cells': sorted(cells)}, open(os.path.join(tmp, 'index.json'), 'w'), separators=(',', ':'))
    dest = OUT if states == STATES else OUT + '.test'   # only a full run replaces the published set
    shutil.rmtree(dest, ignore_errors=True); shutil.copytree(tmp, dest); shutil.rmtree(tmp, ignore_errors=True)
    log(f'{len(wells)} wells in {len(cells)} cells, {total / 1e6:.1f} MB gzip')


if __name__ == '__main__':
    main(sys.argv[1:])
