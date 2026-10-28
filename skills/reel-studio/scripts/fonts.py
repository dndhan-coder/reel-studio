"""Fonts for the renderer: Google Fonts families (the 123 in studio/fonts.json) downloaded once as TTF into
~/.reel-studio/fonts/<Family>/, plus any file the user drops into ~/.reel-studio/fonts/custom/ (his own licensed font).

  python3 fonts.py ensure "Alexandria" "Anton"     # download if missing, print the files
  python3 fonts.py css "Alexandria" "Anton"        # print @font-face CSS with the files embedded as data URIs
"""
import base64
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from common import FONTS_DIR, STUDIO, say

CSS2 = 'https://fonts.googleapis.com/css2?family={fam}:wght@300;400;500;600;700;800;900&display=block'
CUSTOM = FONTS_DIR / 'custom'
MIME = {'.ttf': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2', '.woff': 'font/woff'}


def catalog():
    return json.loads((STUDIO / 'fonts.json').read_text(encoding='utf-8'))


def custom_files(family):
    """A custom family = files in fonts/custom whose stem starts with the family name (e.g. MyFont-Bold.otf)."""
    if not CUSTOM.exists():
        return []
    key = family.lower().replace(' ', '')
    return sorted(p for p in CUSTOM.iterdir() if p.suffix.lower() in MIME and p.stem.lower().replace(' ', '').replace('-', '').startswith(key))


def weight_of(path):
    m = re.search(r'(\d{3})', path.stem)
    if m:
        return int(m.group(1))
    s = path.stem.lower()
    for k, v in (('black', 900), ('extrabold', 800), ('heavy', 900), ('bold', 700), ('semibold', 600),
                 ('medium', 500), ('light', 300), ('thin', 100)):
        if k in s:
            return v
    return 400


def ensure(family):
    """Return [(weight, path)] for the family, downloading from Google Fonts on first use."""
    cf = custom_files(family)
    if cf:
        return [(weight_of(p), p) for p in cf]
    d = FONTS_DIR / family.replace(' ', '_')
    have = sorted(d.glob('*.ttf')) if d.exists() else []
    if have:
        return [(weight_of(p), p) for p in have]
    d.mkdir(parents=True, exist_ok=True)
    url = CSS2.format(fam=urllib.parse.quote(family))
    # a plain (non-browser) user agent makes Google serve TrueType files
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/8.0'})
    try:
        css = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
    except Exception as e:
        say(f'(ما قدرت أنزّل خطّ {family}: {e} — سيُستعمل خطّ النظام)')
        return []
    out, seen = [], set()
    for block in css.split('@font-face')[1:]:
        w = re.search(r'font-weight:\s*(\d+)', block)
        u = re.search(r'url\((https://[^)]+\.ttf)\)', block)
        if not u:
            continue
        wt = int(w.group(1)) if w else 400
        if wt in seen:
            continue
        seen.add(wt)
        dst = d / f'{family.replace(" ", "_")}-{wt}.ttf'
        urllib.request.urlretrieve(u.group(1), dst)
        out.append((wt, dst))
    if out:
        say(f'نزّلت خطّ {family}: {sorted(w for w, _ in out)}')
    return out


def css_for(families):
    rules = []
    for fam in dict.fromkeys(f for f in families if f):
        for wt, p in ensure(fam):
            b64 = base64.b64encode(p.read_bytes()).decode('ascii')
            rules.append(f"@font-face{{font-family:'{fam}';font-weight:{wt};font-display:block;"
                         f"src:url(data:{MIME[p.suffix.lower()]};base64,{b64})}}")
    return '\n'.join(rules)


if __name__ == '__main__':
    cmd, fams = sys.argv[1], sys.argv[2:]
    if cmd == 'ensure':
        for f in fams:
            for wt, p in ensure(f):
                print(f'{f} {wt} {p}')
    elif cmd == 'css':
        print(css_for(fams))
