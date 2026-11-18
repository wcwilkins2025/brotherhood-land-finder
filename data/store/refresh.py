"""Monthly refresh of Land Finder's stored data. Run by a Windows scheduled task on the 1st.

  1. Soil: ask USDA's Box folder which state files changed; rebuild only those (a new USDA
     release is about once a year, so most months this does nothing).
  2. Rating reasons: fetch from Soil Data Access for any state that lacks them.
  3. Wells: pull the full USGS well list again (it changes a little every month).
  4. Upload whatever changed to Cloudflare R2, plus status.json saying when each was checked.
Log: downloads/store/refresh.log. A step that fails is logged and the others still run;
the website keeps serving last month's copy until the next good run.
"""
import datetime, json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
STORE = os.path.join(ROOT, 'downloads', 'store')
LOG = os.path.join(STORE, 'refresh.log')


class Tee:
    def __init__(self, *s): self.s = s
    def write(self, x):
        for f in self.s: f.write(x); f.flush()
    def flush(self):
        for f in self.s: f.flush()


def step(name, fn, status):
    print(f'\n=== {name} {datetime.datetime.now():%Y-%m-%d %H:%M}', flush=True)
    try:
        r = fn(); status[name] = {'ok': True, 'when': time.strftime('%Y-%m-%d'), 'result': r}
    except BaseException as e:
        traceback.print_exc(); status[name] = {'ok': False, 'when': time.strftime('%Y-%m-%d'), 'error': repr(e)[:300]}


def main():
    os.makedirs(STORE, exist_ok=True)
    log = open(LOG, 'a', encoding='utf-8'); sys.stdout = sys.stderr = Tee(sys.__stdout__, log)
    import build_soil, build_wells, upload
    status = {}
    step('soil', lambda: build_soil.main(['--changed']), status)
    step('reasons', lambda: build_soil.main(['--reasons']), status)
    step('wells', lambda: build_wells.main([]), status)
    m = build_soil.load_manifest()
    out = {'checked': time.strftime('%Y-%m-%d'),
           'soil': {'usda_checked': m.get('checked'), 'states': len(m.get('states', {})),
                    'releases': sorted({v.get('release') for v in m.get('states', {}).values() if v.get('release')})[-3:],
                    'reasons_missing': sorted(st for st, v in m.get('states', {}).items() if not v.get('reasons'))},
           'steps': status}
    os.makedirs(os.path.join(STORE, 'out'), exist_ok=True)
    json.dump(out, open(os.path.join(STORE, 'out', 'status.json'), 'w', encoding='utf-8'), indent=1, default=str)
    step('upload', lambda: upload.main([]), status)
    print('\nsummary:', json.dumps({k: v['ok'] for k, v in status.items()}), flush=True)


if __name__ == '__main__':
    main()
