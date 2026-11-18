"""Steps of the monthly data refresh (.github/workflows/data-refresh.yml), runnable on a PC too.

  python -I data/store/ci.py plan [ST ...|ALL]   which soil states to rebuild (changed at USDA, or named)
  python -I data/store/ci.py soil ST             build one state and upload its pieces
  python -I data/store/ci.py assemble            merge states, fill missing rating reasons, publish shards
  python -I data/store/ci.py wells               refresh the USGS well list and publish it
  python -I data/store/ci.py status [results]    write status.json
  python -I data/store/ci.py seed                (once, from the PC) upload a full local build

Bucket layout: soil/ and wells/ are what the website reads; build/ holds the per-state pieces
and the manifest that the next month's run compares against.
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_soil, build_wells, usda_box
from r2 import R2, log

OUT = os.path.join(build_soil.STORE, 'out')


def gh_output(name, value):
    line = f'{name}={value}'
    if os.environ.get('GITHUB_OUTPUT'):
        open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8').write(line + '\n')
    print(line, flush=True)


def plan(r2, args):
    listing = usda_box.list_states()
    r2.put_json(listing, 'build/listing.json')
    m = r2.get_json('build/soil_manifest.json', {'states': {}})
    named = [a.upper() for a in args if a.strip()]
    if named == ['ALL']:
        todo = sorted(listing)
    elif named:
        todo = [st for st in named if st in listing]
    else:
        todo = sorted(st for st, v in listing.items()
                      if m['states'].get(st, {}).get('box_updated') != v['updated'] or m['states'].get(st, {}).get('box_size') != v['size'])
    log(f'{len(listing)} state files at USDA; to rebuild: {" ".join(todo) or "none"}')
    gh_output('states', json.dumps(todo))


def soil(r2, st):
    listing = r2.get_json('build/listing.json') or usda_box.list_states()
    entry = build_soil.build_state(st, listing[st])
    r2.put(os.path.join(OUT, 'soil', 'grid', f'{st}.tif'), f'soil/grid/{st}.tif')
    r2.put(os.path.join(build_soil.UNITS, f'{st}.json'), f'build/units/{st}.json')
    rp = os.path.join(build_soil.REASONS, f'{st}.json')
    if os.path.exists(rp):
        r2.put(rp, f'build/reasons/{st}.json')
    r2.put_json(entry, f'build/manifest/{st}.json')
    log(st, 'uploaded')


def assemble(r2):
    m = r2.get_json('build/soil_manifest.json', {'states': {}})
    for key in r2.etags('build/manifest/'):
        st = key.rsplit('/', 1)[1][:-5]; m['states'][st] = r2.get_json(key)
    m['checked'] = time.strftime('%Y-%m-%d')
    build_soil.save_manifest(m)
    log('units', r2.sync_down('build/units/', build_soil.UNITS), 'reasons', r2.sync_down('build/reasons/', build_soil.REASONS))
    for st, v in sorted(m['states'].items()):           # fill reasons USDA's live service could not give before
        if not v.get('reasons') and v.get('areas'):
            v['reasons'] = build_soil.fetch_reasons(st, v['areas'])
            if v['reasons']:
                r2.put(os.path.join(build_soil.REASONS, f'{st}.json'), f'build/reasons/{st}.json')
    build_soil.save_manifest(m)
    build_soil.assemble()
    r2.sync_up(os.path.join(OUT, 'soil', 'mu'), 'soil/mu/', delete=True)
    r2.put(os.path.join(OUT, 'soil', 'index.json'), 'soil/index.json')
    r2.put_json(m, 'build/soil_manifest.json')
    old = list(r2.etags('build/manifest/'))
    for i in range(0, len(old), 1000):
        r2.s3.delete_objects(Bucket=r2.bucket, Delete={'Objects': [{'Key': k} for k in old[i:i + 1000]]})


def wells(r2):
    build_wells.main(['--fresh'])
    r2.sync_up(os.path.join(OUT, 'wells'), 'wells/', delete=True)


def status(r2, args):
    m = r2.get_json('build/soil_manifest.json', {'states': {}})
    wi = r2.get_json('wells/index.json', {})
    r2.put_json({'checked': time.strftime('%Y-%m-%d'), 'results': args,
                 'soil': {'usda_checked': m.get('checked'), 'states': len(m['states']),
                          'releases': sorted({v.get('release') for v in m['states'].values() if v.get('release')})[-3:],
                          'reasons_missing': sorted(st for st, v in m['states'].items() if not v.get('reasons'))},
                 'wells': {'built': wi.get('built'), 'count': wi.get('wells')}}, 'status.json')


def seed(r2):
    """first upload of a build made on the PC"""
    r2.set_cors()
    m = build_soil.load_manifest()
    r2.sync_up(os.path.join(OUT, 'soil', 'grid'), 'soil/grid/', delete=True)
    r2.sync_up(build_soil.UNITS, 'build/units/', delete=True)
    if os.path.isdir(build_soil.REASONS):
        r2.sync_up(build_soil.REASONS, 'build/reasons/', delete=True)
    r2.sync_up(os.path.join(OUT, 'soil', 'mu'), 'soil/mu/', delete=True)
    r2.put(os.path.join(OUT, 'soil', 'index.json'), 'soil/index.json')
    r2.put_json(m, 'build/soil_manifest.json')
    if os.path.isdir(os.path.join(OUT, 'wells')):
        r2.sync_up(os.path.join(OUT, 'wells'), 'wells/', delete=True)
    status(r2, ['seeded from PC'])


if __name__ == '__main__':
    cmd, rest = sys.argv[1], sys.argv[2:]
    r2 = R2()
    {'plan': lambda: plan(r2, rest), 'soil': lambda: soil(r2, rest[0].upper()), 'assemble': lambda: assemble(r2),
     'wells': lambda: wells(r2), 'status': lambda: status(r2, rest), 'seed': lambda: seed(r2)}[cmd]()
