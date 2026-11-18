"""Upload downloads/store/out/ (soil/ and wells/) to Cloudflare R2, only what changed.

Credentials stay on this PC, outside the repository, in %USERPROFILE%\\.landfinder\\r2.env:
    R2_ACCOUNT_ID=...
    R2_ACCESS_KEY_ID=...
    R2_SECRET_ACCESS_KEY=...
    R2_BUCKET=landfinder-data
Wiley creates the R2 API token in the Cloudflare dashboard and pastes the values there himself.

  python -I data/store/upload.py           # upload changes, remove objects no longer built
  python -I data/store/upload.py --cors    # (once) set the bucket's CORS rules for the website
"""
import hashlib, json, os, sys, time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(ROOT, 'downloads', 'store', 'out')
STATE = os.path.join(ROOT, 'downloads', 'store', 'uploaded.json')   # md5 of what is already up
PREFIXES = ('soil/', 'wells/', 'status.json')
ORIGINS = ['https://thelandfinder.org', 'https://www.thelandfinder.org', 'http://127.0.0.1:8791', 'http://localhost:8791']


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def creds():
    p = os.path.join(os.path.expanduser('~'), '.landfinder', 'r2.env')
    if not os.path.exists(p):
        raise SystemExit(f'Missing {p}. Create the R2 API token in Cloudflare and save the four values there.')
    env = {}
    for line in open(p, encoding='utf-8'):
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1); env[k.strip()] = v.strip()
    return env


def client(env):
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=env['R2_ACCESS_KEY_ID'], aws_secret_access_key=env['R2_SECRET_ACCESS_KEY'],
                        region_name='auto', config=Config(retries={'max_attempts': 8, 'mode': 'standard'}))


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def headers(key, path):
    gz = key.endswith('.json') and open(path, 'rb').read(2) == b'\x1f\x8b'
    h = {'ContentType': 'application/json' if key.endswith('.json') else 'image/tiff'}
    if gz:
        h['ContentEncoding'] = 'gzip'
    # the indexes change monthly; shards and grids change only when their content does
    h['CacheControl'] = 'public, max-age=3600' if key.endswith('index.json') or key == 'status.json' else 'public, max-age=86400'
    return h


def main(args):
    env = creds(); s3 = client(env); bucket = env.get('R2_BUCKET', 'landfinder-data')
    if '--cors' in args:
        s3.put_bucket_cors(Bucket=bucket, CORSConfiguration={'CORSRules': [{
            'AllowedOrigins': ORIGINS, 'AllowedMethods': ['GET', 'HEAD'], 'AllowedHeaders': ['Range', 'If-None-Match'],
            'ExposeHeaders': ['Content-Range', 'Content-Length', 'Accept-Ranges', 'ETag'], 'MaxAgeSeconds': 86400}]})
        log('CORS rules set for', ', '.join(ORIGINS)); return
    try:
        done = json.load(open(STATE, encoding='utf-8'))
    except FileNotFoundError:
        done = {}
    local = {}
    for base, _, files in os.walk(OUT):
        for f in files:
            key = os.path.relpath(os.path.join(base, f), OUT).replace('\\', '/')
            if key.startswith(PREFIXES) and not key.endswith('.part.tif'):
                local[key] = os.path.join(base, f)
    up = 0; nbytes = 0
    for key in sorted(local, key=lambda k: (k.endswith('index.json'), k)):     # indexes last
        path = local[key]; h = md5(path)
        if done.get(key) == h:
            continue
        s3.upload_file(path, bucket, key, ExtraArgs=headers(key, path))
        done[key] = h; up += 1; nbytes += os.path.getsize(path)
        if up % 200 == 0:
            json.dump(done, open(STATE, 'w', encoding='utf-8')); log(f'{up} uploaded')
    gone = [k for k in done if k not in local]
    for i in range(0, len(gone), 1000):
        s3.delete_objects(Bucket=bucket, Delete={'Objects': [{'Key': k} for k in gone[i:i + 1000]]})
    for k in gone:
        done.pop(k, None)
    json.dump(done, open(STATE, 'w', encoding='utf-8'))
    log(f'uploaded {up} files ({nbytes / 1e6:.0f} MB), removed {len(gone)}, {len(done)} in the bucket')


if __name__ == '__main__':
    main(sys.argv[1:])
