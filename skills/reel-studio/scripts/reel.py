#!/usr/bin/env python3
"""Reel Studio — one command per step. Run from anywhere:  python3 <skill>/scripts/reel.py <command> ...

  setup                         check and install what is missing (ffmpeg, whisper, Playwright Chromium, numpy)
  studio [--stop]               open the picker page (fonts, caption style, reel type, brand, B-roll, extras)
  config                        print the saved choices
  new <clip> [--name <slug>]    start a project from a phone clip -> ~/Movies/Reels/<slug>/
  cut <slug>                    cut the dead air, normalise to 1080x1920 30fps  -> work/aroll.mp4
  words <slug>                  transcribe with word timings -> sentences.json (a DRAFT the editor corrects)
  plan <slug>                   build plan.json from sentences.json + config (keywords, B-roll slots, cards)
  broll <slug> [--dry]          generate the B-roll slots on the user's own Higgsfield account
  render <slug> [--preview N]   draw everything -> out/<slug>.mp4 (+ .srt, cover.jpg)
  cover <slug>                  poster-style cover from plan.cover -> out/cover.png
  qc <slug>                     numbers + thumbnail sheet + open the folder
  status [slug]                 where the project stands
  open <slug>                   open the project folder
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import (CFG_DIR, CFG_FILE, CREDIT, PROJECTS, DEFAULT_CONFIG, Project, die, duration, have, latest_project,  # noqa: E402
                    load_config, open_path, run, save_config, say, slugify, video_size)

PY = sys.executable


def sh(script, *args, **kw):
    return run([PY, str(HERE / script), *args], **kw)


def cmd_setup(args):
    rows = []

    def row(name, ok, fix=''):
        rows.append((name, ok, fix))

    row('ffmpeg', have('ffmpeg') and have('ffprobe'), 'brew install ffmpeg   (ويندوز: winget install ffmpeg)')
    try:
        import numpy  # noqa
        row('numpy', True)
    except ImportError:
        r = run([PY, '-m', 'pip', 'install', '--quiet', '--user', 'numpy'], check=False)
        row('numpy', r.returncode == 0, f'{PY} -m pip install numpy')
    try:
        import playwright  # noqa
        ok = True
    except ImportError:
        ok = run([PY, '-m', 'pip', 'install', '--quiet', '--user', 'playwright'], check=False).returncode == 0
    if ok:
        r = run([PY, '-m', 'playwright', 'install', 'chromium'], check=False, capture=True)
        ok = r.returncode == 0
    row('Playwright + Chromium', ok, f'{PY} -m pip install playwright && {PY} -m playwright install chromium')
    if not have('whisper'):
        if have('uv'):
            run(['uv', 'tool', 'install', 'openai-whisper'], check=False)
        else:
            run([PY, '-m', 'pip', 'install', '--quiet', '--user', 'openai-whisper'], check=False)
    row('whisper', have('whisper'), 'uv tool install openai-whisper   أو   pip install openai-whisper')
    hf = have('higgsfield')
    hf_ok = hf and run(['higgsfield', 'account', 'status'], check=False, capture=True).returncode == 0
    row('higgsfield CLI (للـB-roll، اختياري)', hf, 'curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh | sh')
    row('higgsfield login (حسابك أنت)', hf_ok, 'higgsfield auth login')
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    (CFG_DIR / 'fonts' / 'custom').mkdir(parents=True, exist_ok=True)
    if not CFG_FILE.exists():
        save_config(DEFAULT_CONFIG)
    PROJECTS.mkdir(parents=True, exist_ok=True)
    say('\n'.join(f"{'✓' if ok else '✗'} {name}" + ('' if ok else f'   ← {fix}') for name, ok, fix in rows))
    say(f'الإعدادات: {CFG_FILE}\nالمشاريع: {PROJECTS}\nخطوط خاصّة (اختياري): {CFG_DIR / "fonts" / "custom"}')
    missing = [n for n, ok, _ in rows if not ok and 'higgsfield' not in n]
    say('كل شيء جاهز. الخطوة الجاية: python3 reel.py studio' if not missing else f'ناقص: {", ".join(missing)}')


def cmd_studio(args):
    pid = CFG_DIR / 'studio.pid'
    if '--stop' in args:
        if pid.exists():
            try:
                os.kill(int(pid.read_text()), 15)
            except Exception:
                pass
            pid.unlink(missing_ok=True)
        say('وقف الاستوديو.')
        return
    port = 7788
    url = f'http://127.0.0.1:{port}/'
    alive = False
    if pid.exists():
        try:
            os.kill(int(pid.read_text()), 0)
            alive = True
        except Exception:
            alive = False
    if not alive:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(CFG_DIR / 'studio.log', 'a')
        subprocess.Popen([PY, str(HERE / 'studio_server.py'), str(port)], stdout=log, stderr=log,
                         start_new_session=True)
        time.sleep(0.8)
    open_path(url)
    say(f'الاستوديو مفتوح: {url}\nاختر، ثمّ اضغط «احفظ الإعدادات» — تنحفظ في {CFG_FILE}')


def cmd_config(args):
    cfg = load_config()
    say(json.dumps(cfg, ensure_ascii=False, indent=2))
    say(str(CFG_FILE))


def cmd_new(args):
    if not args:
        die('استعمال: reel.py new <ملف الفيديو> [--name اسم]')
    clip = Path(args[0]).expanduser()
    if not clip.exists():
        die(f'ما وجدت الملف {clip}')
    name = args[args.index('--name') + 1] if '--name' in args else clip.stem
    slug = slugify(name)
    pr = Project(slug)
    dst = pr.dir / 'raw' / f'raw{clip.suffix.lower()}'
    if not dst.exists():
        shutil.copy2(clip, dst)        # Drive/iCloud "dataless" files are materialised by the copy
    w, h = video_size(dst)
    d = duration(dst)
    pr.mark('new', source=str(clip), raw=str(dst), size=f'{w}x{h}', seconds=round(d, 1))
    if w > h:
        say('⚠ الفيديو أفقي — سيُقصّ من الجوانب إلى 9:16؛ الأفضل تصوير عمودي.')
    say(f'المشروع: {slug}\n{pr.dir}\n{w}x{h} · {d:.1f}ث')


def _proj(args):
    slug = args[0] if args and not args[0].startswith('--') else latest_project()
    if not slug:
        die('حدّد اسم المشروع')
    return Project(slug), [a for a in args if a != slug]


def cmd_cut(args):
    pr, rest = _proj(args)
    cfg = load_config()
    raw = next(pr.dir.joinpath('raw').glob('raw.*'), None) or die('ما فيه ملف خام في raw/')
    trim = rest[rest.index('--trim') + 1] if '--trim' in rest else cfg['extras'].get('trim', 'medium')
    sh('tighten.py', str(raw), str(pr.dir), '--trim', trim)
    pr.mark('cut', trim=trim, seconds=round(duration(pr.aroll), 1))


def cmd_words(args):
    pr, rest = _proj(args)
    cfg = load_config()
    model = rest[rest.index('--model') + 1] if '--model' in rest else cfg['whisper']['model']
    lang = rest[rest.index('--language') + 1] if '--language' in rest else cfg['whisper']['language']
    sh('words.py', str(pr.dir), '--model', model, '--language', lang)
    pr.mark('words', model=model, language=lang)


DENSITY = {'off': 0, 'light': 4, 'medium': 2, 'heavy': 1}


def cmd_plan(args):
    pr, rest = _proj(args)
    cfg = load_config()
    sf = pr.dir / 'sentences.json'
    if not sf.exists():
        die('ما فيه sentences.json — شغّل words أوّلاً')
    data = json.loads(sf.read_text(encoding='utf-8'))
    every = DENSITY.get(cfg['broll'].get('density', 'medium'), 2) if cfg['broll'].get('on') else 0
    if cfg['type'] == 'voiceover' and cfg['broll'].get('on'):
        every = 1
    sents = []
    for i, s in enumerate(data['sentences']):
        words = [w['w'] for w in s['words']]
        cand = [j for j, w in enumerate(words) if len(w.strip('.,،؟?!')) >= 4]
        em = [max(cand, key=lambda j: len(words[j]))] if cand else []
        want = every and ((i + 1) % every == 0 if every > 1 else i > 0 or cfg['type'] == 'voiceover')
        sents.append({"id": s['id'], "start": s['start'], "end": s['end'], "text": s['text'], "words": s['words'],
                      "em": em, "zoom": False, "point": None,
                      "broll": {"prompt": "", "file": None} if want else None})
    plan = {
        "slug": pr.slug, "type": cfg['type'], "language": data.get('language'),
        "title": "", "hook": "", "hookSeconds": 2.2,
        "outro": {"text": cfg['extras'].get('outroText', ''), "seconds": 2.4} if cfg['extras'].get('outro') else None,
        "scenes": [], "cover": None, "zoomAnchor": 0.38, "music": None, "musicGain": -20,
        "sentences": sents, "caption": "",
        "_help": "em = أرقام الكلمات المهمّة في السطر (من 0) · zoom = true لزوم ضربة على السطر · point = رقم النقطة (نوع tips) · "
                 "broll.prompt = وصف اللقطة بالإنجليزي، فارغ = بلا لقطة · scenes = مشاهد المحرّك (انظر references/plan-format.md)",
    }
    pr.save_plan(plan)
    pr.mark('plan', sentences=len(sents), broll_slots=sum(1 for s in sents if s['broll']))
    say(f'plan.json: {len(sents)} سطر · {sum(1 for s in sents if s["broll"])} خانة B-roll · النوع {cfg["type"]}')
    say(str(pr.plan_file))


def cmd_broll(args):
    pr, rest = _proj(args)
    sh('broll.py', str(pr.dir), *rest)


def cmd_render(args):
    pr, rest = _proj(args)
    sh('render.py', str(pr.dir), *rest)


def cmd_cover(args):
    pr, rest = _proj(args)
    sh('cover.py', str(pr.dir), *rest)


def cmd_qc(args):
    pr, rest = _proj(args)
    sh('qc.py', str(pr.dir))


def cmd_status(args):
    pr, _ = _proj(args)
    st = pr.state()
    order = ['new', 'cut', 'words', 'plan', 'broll', 'render', 'cover', 'qc']
    say(f'المشروع {pr.slug} — {pr.dir}')
    for k in order:
        v = st.get('steps', {}).get(k)
        say(f"  {'✓' if v else '·'} {k:7s} " + (json.dumps({a: b for a, b in v.items() if a != 'at'}, ensure_ascii=False)[:110] if v else ''))
    nxt = next((k for k in order if k not in st.get('steps', {})), None)
    say(f'الجاي: {nxt}' if nxt else 'خلص. ' + CREDIT)


def cmd_open(args):
    pr, _ = _proj(args)
    open_path(pr.dir)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    fn = globals().get('cmd_' + sys.argv[1].replace('-', '_'))
    if not fn:
        die(f'أمر غير معروف: {sys.argv[1]}\n{__doc__}')
    fn(sys.argv[2:])


if __name__ == '__main__':
    main()
