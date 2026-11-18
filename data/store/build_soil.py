"""Build Land Finder's own copy of the USDA soil survey (gSSURGO, one file per state).

For each state:
  1. download gSSURGO_<ST>.7z from USDA's public Box folder (only if new or changed),
  2. unpack it,
  3. resample the 10 m map-unit grid to a 1 arc-second (about 30 m) Cloud-Optimized GeoTIFF
     in lat/lon, so a web page can read one spot with an HTTP range request,
  4. pull, for every map unit, exactly what parcel.html shows: map unit facts, major components,
     the 12 NRCS ratings with their reasons, and the soil layers of the main component,
  5. delete the unpacked database and the download.
Then `assemble` writes the per-unit facts as 2,048 small gzip JSON shards plus an index.

Output goes to downloads/store/out/soil/ (git-ignored); upload.py sends it to Cloudflare R2.

  python -I data/store/build_soil.py DC VT        # build these states
  python -I data/store/build_soil.py --changed    # build every state whose USDA file changed
  python -I data/store/build_soil.py --assemble   # rebuild shards and index from built states
"""
import gzip, io, json, os, shutil, sys, time
import numpy as np
import py7zr, pyogrio, rasterio
import rasterio.shutil, rasterio.errors
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usda_box, sda_reasons

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STORE = os.environ.get('LF_STORE') or os.path.join(ROOT, 'downloads', 'store')   # LF_STORE: a separate folder for tests
RAW, WORK, OUT = (os.path.join(STORE, d) for d in ('raw', 'work', os.path.join('out', 'soil')))
UNITS = os.path.join(STORE, 'units')          # per-state intermediate facts, not uploaded
REASONS = os.path.join(STORE, 'reasons')      # rating reasons from Soil Data Access, per state
MANIFEST = os.path.join(STORE, 'soil_manifest.json')
SHARDS = 2048
RES = 1 / 3600                                  # 1 arc-second

# the NRCS ratings parcel.html shows, in a fixed order (index used in the shards)
INTERPS = [
    'ENG - Dwellings W/O Basements', 'ENG - Septic Tank Absorption Fields',
    'NCCPI - National Commodity Crop Productivity Index (Ver 3.0)', 'AGR - Pasture Productivity Index',
    'AGR - Hay Productivity Index', 'WMS - Pond Reservoir Area', 'WMS - Embankments, Dikes, and Levees',
    'ENG - Dwellings With Basements', 'ENG - Unpaved Local Roads and Streets', 'ENG - Shallow Excavations',
    'GRL - Fencing, Post Depth =<36 inches', 'URB/REC - Camp Areas',
]
MU_COLS = ['musym', 'muname', 'farmlndcl']
AGG_COLS = ['slopegraddcp', 'drclassdcd', 'hydgrpdcd', 'flodfreqdcd', 'pondfreqprs', 'wtdepannmin', 'brockdepmin', 'aws0100wta', 'niccdcd', 'hydclprs']
CO_COLS = ['cokey', 'compname', 'comppct_r', 'drainagecl', 'hydgrp', 'slope_r', 'taxorder', 'taxsubgrp', 'corsteel', 'corcon']
HZ_COLS = ['hzname', 'hzdept_r', 'hzdepb_r', 'sandtotal_r', 'claytotal_r', 'ph1to1h2o_r', 'awc_r', 'ksat_r', 'om_r']


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def clean(v):
    if v is None:
        return None
    if isinstance(v, (bytes,)):
        v = v.decode('utf-8', 'ignore')
    if isinstance(v, (np.floating, float)):
        if np.isnan(v):
            return None
        v = float(v)
        return int(v) if v.is_integer() else round(v, 3)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def table(gdb, layer, cols, where=None):
    """rows as dicts, without geometry"""
    meta, _, _, data = pyogrio.raw.read(gdb, layer=layer, columns=cols, where=where, read_geometry=False)
    names = list(meta['fields'])
    n = len(data[0]) if data else 0
    return [{names[j]: clean(data[j][i]) for j in range(len(names))} for i in range(n)]


def load_manifest():
    try:
        return json.load(open(MANIFEST, encoding='utf-8'))
    except FileNotFoundError:
        return {'states': {}}


def save_manifest(m):
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)      # a fresh GitHub runner starts with no store folder
    json.dump(m, open(MANIFEST, 'w', encoding='utf-8'), indent=1)


def build_grid(gdb, st):
    src_path = f'OpenFileGDB:{gdb}:MURASTER_10m'
    dst = os.path.join(OUT, 'grid', f'{st}.tif')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.part.tif'
    try:
        src_test = rasterio.open(src_path); src_test.close()
    except rasterio.errors.RasterioIOError:
        if not has_raster(gdb):
            # the Pacific island files (AS, FM, GU, MH, MP, PW) ship soil map shapes but no grid
            return build_grid_from_polygons(gdb, dst, tmp)
        # the rasterio wheels for Linux lack the FileGDB raster reader; GitHub's runner uses GDAL's own tools
        return build_grid_cli(src_path, dst, tmp)
    with rasterio.open(src_path) as src:
        with WarpedVRT(src, crs='EPSG:4326', resampling=Resampling.mode, nodata=0, dtype='int32',
                       **_target(src)) as vrt:
            rasterio.shutil.copy(vrt, tmp, driver='COG', COMPRESS='DEFLATE', LEVEL='9', BLOCKSIZE='256',
                                 OVERVIEWS='NONE', BIGTIFF='IF_SAFER', NUM_THREADS='ALL_CPUS')
    os.replace(tmp, dst)
    with rasterio.open(dst) as g:
        b = g.bounds
        return {'w': round(b.left, 5), 's': round(b.bottom, 5), 'e': round(b.right, 5), 'n': round(b.top, 5),
                'width': g.width, 'height': g.height, 'bytes': os.path.getsize(dst)}


def has_raster(gdb, name='MURASTER_10m'):
    """the geodatabase's own catalog (a00000001) lists every table and raster by name"""
    with open(os.path.join(gdb, 'a00000001.gdbtable'), 'rb') as f:
        cat = f.read()
    return any(('fras_ras_' + name).encode(enc) in cat for enc in ('ascii', 'utf-16-le'))


def build_grid_from_polygons(gdb, dst, tmp, block=4096):
    """burn the MUPOLYGON map-unit shapes into the same 1 arc-second grid, one block at a time"""
    import shapely
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from rasterio.warp import transform_geom
    from rasterio.windows import Window, transform as win_transform
    meta, _, geoms, fields = pyogrio.raw.read(gdb, layer='MUPOLYGON', columns=['MUKEY'])
    keys = np.array([int(k) for k in fields[0]], dtype=np.int64)
    shapes = shapely.from_wkb(geoms)
    crs = meta['crs']
    if crs and crs.upper() not in ('EPSG:4326', 'OGC:CRS84'):
        shapes = np.array([shapely.geometry.shape(transform_geom(crs, 'EPSG:4326', shapely.geometry.mapping(g))) for g in shapes])
    w, s_, e, n = shapely.total_bounds(shapes)
    w = np.floor(w / RES) * RES; n = np.ceil(n / RES) * RES
    e = np.ceil(e / RES) * RES; s_ = np.floor(s_ / RES) * RES
    width = int(round((e - w) / RES)); height = int(round((n - s_) / RES))
    tr = from_origin(w, n, RES, RES)
    tree = shapely.STRtree(shapes)
    part = tmp + '.raw.tif'
    with rasterio.open(part, 'w', driver='GTiff', width=width, height=height, count=1, dtype='int32', nodata=0,
                       crs='EPSG:4326', transform=tr, tiled=True, blockxsize=256, blockysize=256,
                       compress='DEFLATE', SPARSE_OK='TRUE', BIGTIFF='IF_SAFER') as out:
        for row in range(0, height, block):
            for col in range(0, width, block):
                win = Window(col, row, min(block, width - col), min(block, height - row))
                wt = win_transform(win, tr)
                x0, y1 = wt * (0, 0); x1, y0 = wt * (win.width, win.height)
                hits = tree.query(shapely.box(x0, y0, x1, y1))
                if len(hits) == 0:
                    continue
                arr = rasterize(zip(shapes[hits], keys[hits].astype('int32').tolist()), out_shape=(win.height, win.width),
                                transform=wt, fill=0, dtype='int32')
                if arr.any():
                    out.write(arr, 1, window=win)
    with rasterio.open(part) as src:
        rasterio.shutil.copy(src, tmp, driver='COG', COMPRESS='DEFLATE', LEVEL='9', BLOCKSIZE='256',
                             OVERVIEWS='NONE', BIGTIFF='IF_SAFER', NUM_THREADS='ALL_CPUS')
    os.remove(part)
    os.replace(tmp, dst)
    with rasterio.open(dst) as g:
        b = g.bounds
        return {'w': round(b.left, 5), 's': round(b.bottom, 5), 'e': round(b.right, 5), 'n': round(b.top, 5),
                'width': g.width, 'height': g.height, 'bytes': os.path.getsize(dst)}


def build_grid_cli(src_path, dst, tmp):
    import subprocess
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds
    info = json.loads(subprocess.run(['gdalinfo', '-json', src_path], check=True, capture_output=True, text=True).stdout)
    gt = info['geoTransform']; w, h = info['size']
    xs = (gt[0], gt[0] + gt[1] * w); ys = (gt[3], gt[3] + gt[5] * h)
    bw, bs, be, bn = transform_bounds(CRS.from_wkt(info['coordinateSystem']['wkt']), 'EPSG:4326', min(xs), min(ys), max(xs), max(ys), densify_pts=21)
    if be < bw or be - bw > 180:
        bw, be = -180.0, -129.0
    bw = np.floor(bw / RES) * RES; bn = np.ceil(bn / RES) * RES; be = np.ceil(be / RES) * RES; bs = np.floor(bs / RES) * RES
    width = int(round((be - bw) / RES)); height = int(round((bn - bs) / RES))
    subprocess.run(['gdalwarp', '-overwrite', '-multi', '-wo', 'NUM_THREADS=ALL_CPUS', '-t_srs', 'EPSG:4326',
                    '-te', f'{float(bw):.10f}', f'{float(bs):.10f}', f'{float(be):.10f}', f'{float(bn):.10f}', '-ts', str(width), str(height), '-r', 'mode',
                    '-dstnodata', '0', '-ot', 'Int32', '-of', 'COG', '-co', 'COMPRESS=DEFLATE', '-co', 'LEVEL=9',
                    '-co', 'BLOCKSIZE=256', '-co', 'OVERVIEWS=NONE', '-co', 'BIGTIFF=IF_SAFER', '-co', 'NUM_THREADS=ALL_CPUS',
                    src_path, tmp], check=True)
    os.replace(tmp, dst)
    with rasterio.open(dst) as g:
        b = g.bounds
        return {'w': round(b.left, 5), 's': round(b.bottom, 5), 'e': round(b.right, 5), 'n': round(b.top, 5),
                'width': g.width, 'height': g.height, 'bytes': os.path.getsize(dst)}


def _target(src):
    """a lat/lon grid at exactly 1 arc-second covering the source"""
    from rasterio.warp import transform_bounds
    from rasterio.transform import from_origin
    w, s, e, n = transform_bounds(src.crs, 'EPSG:4326', *src.bounds, densify_pts=21)
    if e < w or e - w > 180:          # wraps the antimeridian (Alaska): keep the western hemisphere part
        w, e = -180.0, -129.0
    w = np.floor(w / RES) * RES; n = np.ceil(n / RES) * RES
    e = np.ceil(e / RES) * RES; s = np.floor(s / RES) * RES
    width = int(round((e - w) / RES)); height = int(round((n - s) / RES))
    return {'transform': from_origin(w, n, RES, RES), 'width': width, 'height': height}


def build_units(gdb, st):
    mu = {r['mukey']: r for r in table(gdb, 'mapunit', ['mukey'] + MU_COLS)}
    for r in table(gdb, 'muaggatt', ['mukey'] + AGG_COLS):
        if r['mukey'] in mu:
            mu[r['mukey']].update(r)
    comps = [r for r in table(gdb, 'component', ['mukey', 'majcompflag'] + CO_COLS) if (r.get('majcompflag') or '').startswith('Yes')]
    major = {}
    for c in comps:
        major.setdefault(c['mukey'], []).append(c)
    for v in major.values():
        v.sort(key=lambda c: -(c['comppct_r'] or 0))
    cokeys = {c['cokey'] for c in comps}
    names = ','.join("'" + n.replace("'", "''") + "'" for n in INTERPS)
    idx = {n: i for i, n in enumerate(INTERPS)}
    ratings = {}
    for r in table(gdb, 'cointerp', ['cokey', 'mrulename', 'ruledepth', 'seqnum', 'interphr', 'interphrc'], where=f'ruledepth <= 1 AND mrulename IN ({names})'):
        if r['cokey'] in cokeys:
            ratings.setdefault(r['cokey'], []).append(r)
    dom = {v[0]['cokey'] for v in major.values() if v}
    hz = {}
    tex = {r['chkey']: r['texture'] for r in table(gdb, 'chtexturegrp', ['chkey', 'texture', 'rvindicator']) if (r.get('rvindicator') or '').startswith('Yes')}
    for r in table(gdb, 'chorizon', ['cokey', 'chkey'] + HZ_COLS):
        if r['cokey'] in dom:
            hz.setdefault(r['cokey'], []).append(r)
    units = {}
    for k, m in mu.items():
        cs = major.get(k, [])
        rr = []
        for c in cs:
            for r in sorted(ratings.get(c['cokey'], []), key=lambda r: (r['ruledepth'], r['seqnum'] or 0)):
                rr.append([c['cokey'], idx[r['mrulename']], r['ruledepth'], r['interphr'], r['interphrc']])
        layers = []
        if cs:
            for h in sorted(hz.get(cs[0]['cokey'], []), key=lambda h: h['hzdept_r'] or 0):
                layers.append([h[c] for c in HZ_COLS] + [tex.get(h['chkey'])])
        units[str(k)] = {'m': [m.get(c) for c in MU_COLS + AGG_COLS], 'c': [[c[x] for x in CO_COLS] for c in cs], 'r': rr, 'h': layers}
    release, areas = None, []
    try:
        cat = table(gdb, 'sacatalog', ['areasymbol', 'saverest'])
        release = max(str(r['saverest'])[:10] for r in cat if r['saverest'])
        areas = sorted(r['areasymbol'] for r in cat if r['areasymbol'])
    except Exception:
        pass
    return units, release, areas


def build_state(st, meta, keep_raw=False):
    os.makedirs(RAW, exist_ok=True); os.makedirs(UNITS, exist_ok=True)
    raw = os.path.join(RAW, f'{st}.7z')
    if not (os.path.exists(raw) and os.path.getsize(raw) == meta['size']):
        log(st, f'downloading {meta["size"] / 1e6:.0f} MB')
        usda_box.download(meta['id'], raw, meta['size'])
    work = os.path.join(WORK, st)
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    log(st, 'unpacking')
    with py7zr.SevenZipFile(raw) as z:
        z.extractall(work)
    gdb = next(os.path.join(work, d) for d in os.listdir(work) if d.endswith('.gdb'))
    log(st, 'grid')
    grid = build_grid(gdb, st)
    log(st, f'grid {grid["width"]}x{grid["height"]} {grid["bytes"] / 1e6:.1f} MB; tables')
    units, release, areas = build_units(gdb, st)
    json.dump(units, open(os.path.join(UNITS, f'{st}.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    shutil.rmtree(work, ignore_errors=True)
    if not keep_raw:
        os.remove(raw)
    log(st, f'{len(units)} map units; release {release}; {len(areas)} survey areas')
    reasons_ok = fetch_reasons(st, areas)
    return {'areas': areas, 'reasons': reasons_ok, 'box_id': meta['id'], 'box_updated': meta['updated'], 'box_size': meta['size'], 'release': release,
            'units': len(units), 'grid': grid, 'built': time.strftime('%Y-%m-%d')}


SDA_DOWN = False


def fetch_reasons(st, areas):
    global SDA_DOWN
    if SDA_DOWN:
        log(st, 'reasons skipped this run (Soil Data Access was down earlier in the run)')
        return None
    try:
        n = sda_reasons.fetch(st, areas, INTERPS, REASONS)
        log(st, f'reasons for {n} components from Soil Data Access')
        return time.strftime('%Y-%m-%d')
    except Exception as e:
        log(st, 'reasons not fetched (kept any earlier copy):', str(e)[:120])
        SDA_DOWN = True
        return None


def merge_reasons(st, units):
    try:
        rs = json.load(open(os.path.join(REASONS, f'{st}.json'), encoding='utf-8'))
    except FileNotFoundError:
        return 0
    n = 0
    for u in units.values():
        have = {(r[0], r[1]) for r in u['r'] if r[2] == 1}
        for c in u['c']:
            for idx, seq, hr, hrc in rs.get(str(c[0]), []):
                if (c[0], idx) not in have:
                    u['r'].append([c[0], idx, 1, hr, hrc]); n += 1
    return n


def assemble():
    """shards of unit facts (mukey mod 2048, gzip JSON) and the grid index the page reads"""
    allu = {}
    for f in sorted(os.listdir(UNITS)):
        if f.endswith('.json'):
            u = json.load(open(os.path.join(UNITS, f), encoding='utf-8'))
            merge_reasons(f[:-5], u)
            allu.update(u)
    d = os.path.join(OUT, 'mu'); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shards = {}
    for k, v in allu.items():
        shards.setdefault(int(k) % SHARDS, {})[k] = v
    total = 0
    for i, part in shards.items():
        b = gzip.compress(json.dumps(part, separators=(',', ':')).encode('utf-8'), 9)
        open(os.path.join(d, f'{i}.json'), 'wb').write(b)
        total += len(b)
    m = load_manifest()
    index = {'version': 1, 'built': time.strftime('%Y-%m-%d'), 'shards': SHARDS, 'interps': INTERPS,
             'cols': {'m': MU_COLS + AGG_COLS, 'c': CO_COLS, 'h': HZ_COLS + ['texture']},
             'grids': {st: dict(v['grid'], release=v['release']) for st, v in sorted(m['states'].items()) if 'grid' in v}}
    json.dump(index, open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    log(f'assembled {len(allu)} map units into {len(shards)} shards, {total / 1e6:.1f} MB gzip')


def main(args):
    m = load_manifest()
    if '--assemble' in args:
        assemble(); return
    if '--reasons' in args:
        # refetch reasons for built states that lack them (or all named states), then reassemble
        named = [a.upper() for a in args if not a.startswith('--')]
        for st, v in sorted(m['states'].items()):
            if (named and st in named) or (not named and not v.get('reasons')):
                v['reasons'] = fetch_reasons(st, v.get('areas', [])) or v.get('reasons')
                save_manifest(m)
        assemble(); return
    listing = usda_box.list_states()
    m['checked'] = time.strftime('%Y-%m-%d')
    if '--changed' in args:
        todo = [st for st, v in sorted(listing.items())
                if m['states'].get(st, {}).get('box_updated') != v['updated'] or m['states'].get(st, {}).get('box_size') != v['size']]
    else:
        todo = [a.upper() for a in args if not a.startswith('--')]
    log('to build:', ' '.join(todo) or 'nothing (no USDA file changed)')
    done = []
    for st in todo:
        if st not in listing:
            log(st, 'not in USDA listing'); continue
        try:
            m['states'][st] = build_state(st, listing[st], keep_raw='--keep' in args)
            save_manifest(m); done.append(st)
        except Exception as e:
            log(st, 'FAILED', repr(e)[:300])
            m.setdefault('failed', {})[st] = {'when': time.strftime('%Y-%m-%d'), 'error': repr(e)[:300]}
            save_manifest(m)
    save_manifest(m)
    if done:
        assemble()
    return done


if __name__ == '__main__':
    main(sys.argv[1:])
