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
OUT = os.path.join(os.environ.get('LF_STORE') or os.path.join(ROOT, 'downloads', 'store'), 'out', 'wells')
API = 'https://api.waterdata.usgs.gov/ogcapi/v0/collections'
STATES = ['01', '02', '04', '05', '06', '08', '09', '10', '11', '12', '13', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26',
          '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '40', '41', '42', '44', '45', '46', '47', '48', '49', '50',
          '51', '53', '54', '55', '56']


def api_key():
    """the free USGS Water Data API key, if Wiley saved one in %USERPROFILE%\\.landfinder\\usgs.env"""
    if os.environ.get('USGS_API_KEY'):          # GitHub Actions secret
        return os.environ['USGS_API_KEY'].strip()
    p = os.path.join(os.path.expanduser('~'), '.landfinder', 'usgs.env')
    try:
        for line in open(p, encoding='utf-8'):
            if line.strip().startswith('USGS_API_KEY='):
                return line.split('=', 1)[1].strip() or None
    except FileNotFoundError:
        pass
    return None


KEY = api_key()


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def pages(url):
    import urllib.error
    while url:
        for k in range(12):
            try:
                hdr = {'User-Agent': 'land-finder-data (monthly well refresh)'}
                if KEY:
                    hdr['X-Api-Key'] = KEY      # higher rate limits; sent as a header, never in the URL
                req = urllib.request.Request(url, headers=hdr)
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if k == 11:
                    raise
                wait = int(e.headers.get('Retry-After') or 0) if e.code == 429 else 0
                wait = max(wait, 60 * (k + 1) if e.code == 429 else 15 * (k + 1))
                log(f'USGS answered {e.code}; waiting {wait}s'); time.sleep(min(wait, 900))
            except Exception:
                if k == 11:
                    raise
                time.sleep(15 * (k + 1))
        yield d.get('features') or []
        url = next((l['href'] for l in d.get('links', []) if l.get('rel') == 'next'), None)
        time.sleep(0.5 if KEY else 2)


def num(v):
    try:
        x = float(v)
        return None if math.isnan(x) else (int(x) if x.is_integer() else round(x, 1))
    except (TypeError, ValueError):
        return None


def main(args):
    states = [a for a in args if a.isdigit()] or STATES
    log('USGS API key: ' + ('yes' if KEY else 'none (anonymous limits, slower)'))
    wells = {}
    part_dir = os.path.join(os.path.dirname(OUT), 'wells_states'); os.makedirs(part_dir, exist_ok=True)
    if '--fresh' in args:
        for f in os.listdir(part_dir):
            os.remove(os.path.join(part_dir, f))
    for st in states:
        part = os.path.join(part_dir, f'{st}.json')
        if os.path.exists(part):
            wells.update(json.load(open(part, encoding='utf-8'))); log(f'state {st}: kept from earlier in this run'); continue
        n0 = len(wells); mine = {}
        props = 'monitoring_location_number,monitoring_location_name,well_constructed_depth,hole_constructed_depth,aquifer_code,county_name,state_code'
        for feats in pages(f'{API}/monitoring-locations/items?site_type_code=GW&state_code={st}&limit=10000&f=json&properties={props}'):
            for f in feats:
                g = f.get('geometry') or {}
                c = g.get('coordinates')
                if not c:
                    continue
                p = f['properties']
                mine[p['monitoring_location_number']] = [p['monitoring_location_number'], p.get('monitoring_location_name'), round(c[1], 5), round(c[0], 5),
                                                          num(p.get('well_constructed_depth')), num(p.get('hole_constructed_depth')), p.get('aquifer_code'),
                                                          p.get('county_name'), p.get('state_code'), None, None]
        levels = 0
        for feats in pages(f'{API}/latest-field-measurements/items?parameter_code=72019&state_code={st}&limit=10000&f=json&properties=monitoring_location_id,value,time&skipGeometry=true'):
            for f in feats:
                p = f['properties']
                wid = (p.get('monitoring_location_id') or '').split('-', 1)[-1]
                w = mine.get(wid)
                v = num(p.get('value'))
                if w is not None and v is not None and (w[10] is None or (p.get('time') or '') > w[10]):
                    w[9] = v; w[10] = (p.get('time') or '')[:10]; levels += 1
        json.dump(mine, open(part, 'w', encoding='utf-8'), separators=(',', ':')); wells.update(mine)
        log(f'state {st}: {len(mine)} wells, {levels} with a water level')
        time.sleep(1 if KEY else 5)
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
