"""B-roll from Higgsfield, with the user's OWN Higgsfield account (higgsfield CLI, `higgsfield auth login`).

  python3 broll.py <project dir> [--dry] [--only s03,s07] [--model seedance_2_0]

Reads plan.json: every sentence with "broll": {"prompt": "..."} and no "file" yet gets one vertical clip.
The prompt sent = the sentence prompt + the look tail from config + a no-text guard. The clip is downloaded,
trimmed to the sentence length (+0.3 s), silenced and normalised to 1080x1920 30 fps into broll/<id>.mp4, and the
path is written back into the plan. A sentence whose generation fails keeps "file": null and the render shows the
speaker instead (a weak shot is worse than no shot).

Nothing of anyone else's account is used: the CLI reads the login the user made on this machine.
"""
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from common import W, H, FPS, load_config, run, say, die, have, Project

GUARD = 'vertical 9:16, no text, no letters, no captions, no watermark, no logo'


def check_cli():
    if not have('higgsfield'):
        die('أمر higgsfield غير مثبّت. ثبّته بهذا الأمر ثمّ سجّل دخولك:\n'
            '  curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh | sh\n'
            '  higgsfield auth login')
    r = run(['higgsfield', 'account', 'status'], check=False, capture=True)
    if r.returncode != 0:
        die('هيغسفيلد يطلب تسجيل الدخول بحسابك أنت (مرّة واحدة):\n  higgsfield auth login\n' + (r.stderr or '').strip())
    return (r.stdout or '').strip()


def find_url(text):
    m = re.findall(r'https?://[^\s"\'\\]+?\.(?:mp4|mov|webm)(?:\?[^\s"\'\\]*)?', text or '')
    return m[-1] if m else None


def generate(model, prompt, duration, dry=False):
    """Submit one job and return the media URL. Tries the full flag set first, then drops flags the model rejects."""
    ladders = [['--aspect_ratio', '9:16', '--duration', str(duration)], ['--aspect_ratio', '9:16'], []]
    last = ''
    for extra in ladders:
        cmd = ['higgsfield', 'generate', 'create', model, '--prompt', prompt, *extra, '--wait', '--wait-timeout', '15m', '--json']
        if dry:
            say('  $ ' + ' '.join(f'"{c}"' if ' ' in c else c for c in cmd))
            return None
        r = run(cmd, check=False, capture=True)
        url = find_url(r.stdout) or find_url(r.stderr)
        if r.returncode == 0 and url:
            return url
        last = (r.stderr or r.stdout or '').strip()
        if r.returncode != 0 and extra and re.search(r'unknown|invalid|unexpected|not (a )?valid|param', last, re.I):
            continue        # the model does not take that flag: try the next ladder step
        break
    raise RuntimeError(last[-600:] or 'لا رابط في جواب هيغسفيلد')


def fetch(url, dst):
    req = urllib.request.Request(url, headers={'User-Agent': 'reel-studio/1.0'})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, 'wb') as f:
        shutil.copyfileobj(r, f)


def conform(src, dst, seconds):
    vf = f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},format=yuv420p'
    run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-t', f'{seconds:.3f}', '-an', '-vf', vf,
         '-c:v', 'libx264', '-preset', 'fast', '-crf', '17', dst])


def main():
    proj_dir = Path(sys.argv[1])
    dry = '--dry' in sys.argv
    only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
    cfg = load_config()
    model = sys.argv[sys.argv.index('--model') + 1] if '--model' in sys.argv else cfg['broll']['model']
    look = cfg['broll'].get('look', '')
    dur_cfg = int(cfg['broll'].get('duration', 5))
    pr = Project(proj_dir.name)
    plan = pr.plan()
    todo = [s for s in plan['sentences'] if (s.get('broll') or {}).get('prompt') and not (s['broll'].get('file'))
            and (only is None or s['id'] in only)]
    if not todo:
        say('ما فيه لقطات مطلوبة (كل سطر عليه prompt صار له ملف، أو ما فيه prompts).')
        return
    if not dry:
        say(check_cli())
    say(f'{len(todo)} لقطة بموديل {model}:')
    ok = 0
    for s in todo:
        seconds = (s['end'] - s['start']) + 0.3
        prompt = f"{s['broll']['prompt'].strip().rstrip('.')}, {look}, {GUARD}" if look else f"{s['broll']['prompt']}, {GUARD}"
        say(f"• {s['id']} ({seconds:.1f}ث): {s['broll']['prompt']}")
        try:
            url = generate(model, prompt, max(dur_cfg, 4), dry=dry)
            if dry:
                continue
            raw = pr.dir / 'broll' / f"{s['id']}.src.mp4"
            fetch(url, raw)
            out = pr.dir / 'broll' / f"{s['id']}.mp4"
            conform(raw, out, seconds)
            s['broll']['file'] = f"broll/{s['id']}.mp4"
            s['broll']['url'] = url
            s['broll']['model'] = model
            pr.save_plan(plan)
            ok += 1
            say(f"  ✓ {out.name}")
        except Exception as e:
            s['broll']['error'] = str(e)[-300:]
            pr.save_plan(plan)
            say(f"  ✗ فشلت: {str(e)[-200:]}")
    if not dry:
        pr.mark('broll', done=ok, asked=len(todo), model=model)
        say(f'{ok}/{len(todo)} لقطة جاهزة في {pr.dir / "broll"}')


if __name__ == '__main__':
    main()
