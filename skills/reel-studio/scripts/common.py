"""Shared helpers for Reel Studio: paths, config, project state, shell.

Config lives in ~/.reel-studio/config.json (written by the picker page, read by every step).
Projects live in ~/Movies/Reels/<slug>/ : raw/ work/ broll/ out/ + plan.json + state.json.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HOME = Path.home()
CFG_DIR = HOME / '.reel-studio'
CFG_FILE = CFG_DIR / 'config.json'
FONTS_DIR = CFG_DIR / 'fonts'
PROJECTS = HOME / 'Movies' / 'Reels'
SKILL = Path(__file__).resolve().parent.parent          # .../skills/reel-studio
STUDIO = SKILL / 'studio'
ENGINE = SKILL / 'engine'
W, H, FPS = 1080, 1920, 30

CREDIT = '🤲 هذي الأداة هدية من حسين المتروك — ادعِ له بالخير.'

DEFAULT_CONFIG = {
    "version": 1,
    "type": "talk",                                   # talk | voiceover | tips | story
    "font": {"ar": "Alexandria", "latin": "Anton"},   # Google Fonts family names
    "caption": {"style": "keyword", "size": "m", "position": "low"},
    "brand": {"accent": "#FCC022", "handle": "", "name": "", "theme": "dark"},
    "broll": {"on": True, "density": "medium", "model": "seedance_2_0",
              "look": "cinematic, dark moody lighting, shallow depth of field, 35mm", "duration": 5},
    "extras": {"hookZoom": True, "progress": True, "outro": True, "outroText": "تابعني لمزيد",
               "grade": "none", "trim": "medium"},
    "whisper": {"model": "turbo", "language": "auto"},
}


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_config():
    cfg = {}
    if CFG_FILE.exists():
        try:
            cfg = json.loads(CFG_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            die(f'config.json فيه خطأ ({e}) — افتح الاستوديو واحفظ من جديد: python3 reel.py studio')
    return deep_merge(DEFAULT_CONFIG, cfg)


def save_config(cfg):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    return CFG_FILE


def slugify(name):
    s = unicodedata.normalize('NFKC', str(name)).strip()
    s = re.sub(r'[^\w؀-ۿ-]+', '-', s).strip('-')
    return (s or 'reel')[:40]


class Project:
    def __init__(self, slug):
        self.slug = slug
        self.dir = PROJECTS / slug
        for d in ('raw', 'work', 'broll', 'out'):
            (self.dir / d).mkdir(parents=True, exist_ok=True)

    @property
    def state_file(self):
        return self.dir / 'state.json'

    def state(self):
        return json.loads(self.state_file.read_text(encoding='utf-8')) if self.state_file.exists() else {"steps": {}}

    def mark(self, step, **info):
        st = self.state()
        st.setdefault('steps', {})[step] = {"at": time.strftime('%Y-%m-%d %H:%M'), **info}
        self.state_file.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding='utf-8')

    @property
    def plan_file(self):
        return self.dir / 'plan.json'

    def plan(self):
        if not self.plan_file.exists():
            die(f'ما فيه plan.json بعد في {self.dir} — شغّل: python3 reel.py plan {self.slug}')
        return json.loads(self.plan_file.read_text(encoding='utf-8'))

    def save_plan(self, plan):
        self.plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')

    @property
    def aroll(self):
        return self.dir / 'work' / 'aroll.mp4'


def latest_project():
    if not PROJECTS.exists():
        return None
    ps = [p for p in PROJECTS.iterdir() if p.is_dir() and (p / 'state.json').exists()]
    return max(ps, key=lambda p: p.stat().st_mtime).name if ps else None


def run(cmd, check=True, capture=False, **kw):
    kw.setdefault('text', True)
    if capture:
        kw.setdefault('stdout', subprocess.PIPE)
        kw.setdefault('stderr', subprocess.PIPE)
    return subprocess.run([str(c) for c in cmd], check=check, **kw)


def have(tool):
    return shutil.which(tool) is not None


def ffprobe(path):
    r = run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path], capture=True)
    return json.loads(r.stdout)


def duration(path):
    return float(ffprobe(path)['format']['duration'])


def video_size(path):
    for s in ffprobe(path)['streams']:
        if s.get('codec_type') == 'video':
            rot = 0
            for sd in s.get('side_data_list', []):
                rot = int(sd.get('rotation', 0) or 0)
            w, h = int(s['width']), int(s['height'])
            return (h, w) if rot % 180 else (w, h)
    die('الملف ما فيه فيديو')


def open_path(p):
    p = str(p)
    sysname = platform.system()
    try:
        if sysname == 'Darwin':
            subprocess.Popen(['open', p])
        elif sysname == 'Windows':
            os.startfile(p)  # noqa
        else:
            subprocess.Popen(['xdg-open', p])
    except Exception as e:  # pragma: no cover
        print(f'(ما قدرت أفتح {p}: {e})')


def say(msg):
    print(msg, flush=True)


def die(msg, code=1):
    print(f'✗ {msg}', file=sys.stderr, flush=True)
    sys.exit(code)


def is_arabic(text):
    return bool(re.search(r'[؀-ۿ]', text or ''))
