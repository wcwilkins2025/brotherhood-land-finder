"""Cloudflare R2 helpers for Land Finder's stored data.

Credentials come from environment variables (GitHub Actions secrets) or, on a PC, from
%USERPROFILE%\\.landfinder\\r2.env:  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
Uploads are single PUTs, so an object's ETag is its MD5 and unchanged files are skipped.
"""
import hashlib, json, os, time

KEYS = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')
ORIGINS = ['https://thelandfinder.org', 'https://www.thelandfinder.org', 'http://127.0.0.1:8791', 'http://localhost:8791']


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def creds():
    env = {k: os.environ.get(k) for k in KEYS if os.environ.get(k)}
    p = os.path.join(os.path.expanduser('~'), '.landfinder', 'r2.env')
    if len(env) < 3 and os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                if v.strip():
                    env.setdefault(k.strip(), v.strip())
    missing = [k for k in KEYS[:3] if not env.get(k)]
    if missing:
        raise SystemExit('Missing R2 credentials: ' + ', '.join(missing))
    env.setdefault('R2_BUCKET', 'landfinder-data')
    return env


class R2:
    def __init__(self):
        import boto3
        from botocore.config import Config
        from boto3.s3.transfer import TransferConfig
        env = creds(); self.bucket = env['R2_BUCKET']
        self.s3 = boto3.client('s3', endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                               aws_access_key_id=env['R2_ACCESS_KEY_ID'], aws_secret_access_key=env['R2_SECRET_ACCESS_KEY'],
                               region_name='auto', config=Config(retries={'max_attempts': 10, 'mode': 'standard'}))
        self.tx = TransferConfig(multipart_threshold=4 * 1024 ** 3)   # single PUT up to 4 GB, so ETag == MD5

    def etags(self, prefix):
        out = {}
        for page in self.s3.get_paginator('list_objects_v2').paginate(Bucket=self.bucket, Prefix=prefix):
            for o in page.get('Contents', []):
                out[o['Key']] = o['ETag'].strip('"')
        return out

    def put(self, path, key):
        self.s3.upload_file(path, self.bucket, key, ExtraArgs=headers(key, path), Config=self.tx)

    def get(self, key, path):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.s3.download_file(self.bucket, key, path)

    def get_json(self, key, default=None):
        try:
            return json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)['Body'].read())
        except self.s3.exceptions.NoSuchKey:
            return default

    def put_json(self, obj, key):
        b = json.dumps(obj, separators=(',', ':'), default=str).encode()
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=b, ContentType='application/json', CacheControl='public, max-age=3600')

    def sync_up(self, local_dir, prefix, delete=False):
        """upload files under local_dir to prefix whose MD5 differs; optionally remove objects not present locally"""
        have = self.etags(prefix); seen = set(); up = 0; nbytes = 0
        files = []
        for base, _, fs in os.walk(local_dir):
            for f in fs:
                if f.endswith('.part.tif'):
                    continue
                path = os.path.join(base, f); key = prefix + os.path.relpath(path, local_dir).replace('\\', '/')
                files.append((key, path))
        for key, path in sorted(files, key=lambda kp: (kp[0].endswith('index.json'), kp[0])):   # indexes last
            seen.add(key)
            if have.get(key) == md5(path):
                continue
            self.put(path, key); up += 1; nbytes += os.path.getsize(path)
            if up % 250 == 0:
                log(f'{prefix}: {up} uploaded')
        gone = [k for k in have if k not in seen] if delete else []
        for i in range(0, len(gone), 1000):
            self.s3.delete_objects(Bucket=self.bucket, Delete={'Objects': [{'Key': k} for k in gone[i:i + 1000]]})
        log(f'{prefix}: uploaded {up} ({nbytes / 1e6:.0f} MB), removed {len(gone)}, {len(seen)} present')
        return up

    def sync_down(self, prefix, local_dir):
        n = 0
        for key in self.etags(prefix):
            self.get(key, os.path.join(local_dir, key[len(prefix):])); n += 1
        return n

    def set_cors(self):
        self.s3.put_bucket_cors(Bucket=self.bucket, CORSConfiguration={'CORSRules': [{
            'AllowedOrigins': ORIGINS, 'AllowedMethods': ['GET', 'HEAD'], 'AllowedHeaders': ['Range', 'If-None-Match'],
            'ExposeHeaders': ['Content-Range', 'Content-Length', 'Accept-Ranges', 'ETag'], 'MaxAgeSeconds': 86400}]})


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def headers(key, path):
    with open(path, 'rb') as f:
        gz = f.read(2) == b'\x1f\x8b'
    h = {'ContentType': 'application/json' if key.endswith('.json') else 'image/tiff' if key.endswith('.tif') else 'application/octet-stream'}
    if gz and key.endswith('.json'):
        h['ContentEncoding'] = 'gzip'
    h['CacheControl'] = 'public, max-age=3600' if key.endswith('index.json') or key.endswith('status.json') else 'public, max-age=86400'
    return h
