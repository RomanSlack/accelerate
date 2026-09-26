"""Generate video clips from a prompts/*.jsonl file via fal.ai (Kling 2.5 Turbo Pro or Veo 3.1).

Each line: {"prompt", "model": "kling"|"veo", "name", "duration", "aspect", "resolution"?, "image"?}
A line with "image" runs image-to-video, otherwise text-to-video.
Clips land in assets/vid/<name>_0.mp4; existing clips are skipped, so reruns are safe.

usage:
  export FAL_KEY=...                                   # never commit this
  python scripts/gen_clips.py prompts/07_real_people_veo_kling.jsonl --dry-run
  python scripts/gen_clips.py prompts/07_real_people_veo_kling.jsonl --workers 6
"""
import argparse, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINTS = {
    ('kling', 't2v'): 'fal-ai/kling-video/v2.5-turbo/pro/text-to-video',
    ('kling', 'i2v'): 'fal-ai/kling-video/v2.5-turbo/pro/image-to-video',
    ('veo', 't2v'): 'fal-ai/veo3.1',
    ('veo', 'i2v'): 'fal-ai/veo3.1/image-to-video',
}
USD_PER_SEC = {'kling': 0.07, 'veo': 0.40}   # rough estimates, check fal.ai pricing

def arguments(row, image_url):
    model, dur = row.get('model', 'kling'), int(row.get('duration', 5))
    if model == 'veo':
        a = {'prompt': row['prompt'], 'duration': f'{dur}s', 'resolution': row.get('resolution', '1080p'), 'generate_audio': False}
        if image_url: a['image_url'] = image_url
        else: a['aspect_ratio'] = row.get('aspect', '16:9')
        return a
    a = {'prompt': row['prompt'], 'duration': str(dur)}
    if image_url: a['image_url'] = image_url
    else: a['aspect_ratio'] = row.get('aspect', '16:9')
    return a

def video_url(result):
    v = result.get('video')
    if isinstance(v, dict): return v.get('url', '')
    if isinstance(v, str): return v
    vs = result.get('videos') or []
    return vs[0].get('url', '') if vs else ''

def run(row, out_dir, dry):
    name = row['name']
    dst = os.path.join(out_dir, f'{name}_0.mp4')
    if os.path.exists(dst):
        return f'skip  {name} (exists)'
    mode = 'i2v' if row.get('image') else 't2v'
    endpoint = ENDPOINTS[(row.get('model', 'kling'), mode)]
    if dry:
        return f'dry   {name}: {endpoint} {json.dumps(arguments(row, "<uploaded " + row["image"] + ">" if row.get("image") else None))[:140]}'
    import fal_client
    image_url = fal_client.upload_file(row['image']) if row.get('image') else None
    result = fal_client.subscribe(endpoint, arguments=arguments(row, image_url))
    url = video_url(result)
    if not url:
        return f'ERR   {name}: no video in response {str(result)[:200]}'
    urllib.request.urlretrieve(url, dst)
    return f'ok    {name} -> {dst}'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl')
    ap.add_argument('--out', default='assets/vid')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true', help='print endpoints, payloads and estimated cost; spend nothing')
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.jsonl) if l.strip()]
    est = sum(USD_PER_SEC.get(r.get('model', 'kling'), 0.07) * int(r.get('duration', 5)) for r in rows)
    print(f'{len(rows)} clips, estimated ${est:.2f}', file=sys.stderr)
    if not a.dry_run and not os.environ.get('FAL_KEY'):
        sys.exit('set FAL_KEY first (https://fal.ai/dashboard/keys)')
    os.makedirs(a.out, exist_ok=True)
    def safe(r):
        try: return run(r, a.out, a.dry_run)
        except Exception as e: return f'ERR   {r.get("name")}: {e}'
    with ThreadPoolExecutor(a.workers) as ex:
        for line in ex.map(safe, rows):
            print(line)

if __name__ == '__main__':
    main()
