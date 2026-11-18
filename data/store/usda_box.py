"""USDA NRCS publishes the gSSURGO state soil databases in a public Box folder.
This lists that folder (all pages) and downloads one file, politely: browser-like headers,
a pause between requests, and retries, because Box answers 404 to scripts that ask too fast.
"""
import json, re, time, urllib.request, urllib.error

FOLDER = 'https://nrcs.app.box.com/v/soils/folder/233398887779'   # gSSURGO (File Geodatabases) / State
SHARED = 'ug97v4dro9huoc16pima6xi86d606l3e'                       # the public share the folder belongs to
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _get(url, tries=5, pause=20):
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r:
                return r.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(pause * (k + 1))
    raise RuntimeError(f'Box listing failed after {tries} tries: {last}')


def list_states():
    """{'TX': {'id':..., 'name': 'gSSURGO_TX.7z', 'size': bytes, 'updated': 'YYYY-MM-DD...'}, ...}"""
    out, page, pages = {}, 1, 1
    while page <= pages:
        html = _get(f'{FOLDER}?page={page}')
        m = re.search(r'Box\.postStreamData\s*=\s*(\{.*?\});\s*</script>', html, re.S)
        if not m:
            raise RuntimeError('Box page layout changed: no folder data found')
        f = json.loads(m.group(1))['/app-api/enduserapp/shared-folder']
        pages = int(f.get('pageCount') or 1)
        for i in f['items']:
            mm = re.fullmatch(r'gSSURGO_([A-Z]{2})\.7z', i.get('name', ''))
            if mm:
                upd = i.get('contentUpdated') or i.get('dateModified') or i.get('date')
                if isinstance(upd, (int, float)):
                    upd = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(upd))
                out[mm.group(1)] = {'id': str(i['id']), 'name': i['name'], 'size': int(i.get('itemSize') or 0), 'updated': upd}
        page += 1
        time.sleep(3)
    return out


def download(file_id, dest, expect_size=None, tries=4):
    url = f'https://nrcs.app.box.com/index.php?rm=box_download_shared_file&shared_name={SHARED}&file_id=f_{file_id}'
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=600) as r, open(dest, 'wb') as out:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
            import os
            got = os.path.getsize(dest)
            if expect_size and got != expect_size:
                raise RuntimeError(f'size {got} != listed {expect_size}')
            with open(dest, 'rb') as fh:
                if fh.read(6) != b"7z\xbc\xaf'\x1c":
                    raise RuntimeError('not a 7z file')
            return got
        except Exception as e:
            last = e
            time.sleep(30 * (k + 1))
    raise RuntimeError(f'download {file_id} failed: {last}')


if __name__ == '__main__':
    s = list_states()
    print(len(s), 'state files', round(sum(v['size'] for v in s.values()) / 1e9, 1), 'GB')
    print(json.dumps({k: s[k] for k in sorted(s)[:3]}, indent=1))
