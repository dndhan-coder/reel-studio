"""Poster-style cover for the reel: a real frame of the speaker (or a B-roll frame), dark gradients, a pill line,
two or three huge glossy title lines with one coloured word, an optional English tag, the handle.

  python3 cover.py <project dir> [--at 1.4] [--bg broll/s03.mp4]

plan.cover = {"pill": "الحلقة 3", "lines": [["حسابك صار", ""], ["صفر؟", "accent"]], "tag": "DISCIPLINE", "at": 1.4}
 - a line is [text, colour] where colour is "" (white), "accent" (the brand colour) or any #hex; a line can also be
   a list of such pairs so one word in it takes its own colour.
Without plan.cover the title/hook/first sentence is used. Output: out/cover.png and out/cover.jpg.
"""
import base64
import json
import sys
from pathlib import Path

from common import W, H, ENGINE, load_config, run, say, duration, is_arabic, Project
import fonts


def grab(video, t, dst):
    run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', str(video), '-frames:v', '1', '-q:v', '2',
         '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}', str(dst)])


def main():
    pr = Project(Path(sys.argv[1]).name)
    cfg, plan = load_config(), pr.plan()
    cover = plan.get('cover') or {}
    accent = cfg['brand']['accent']
    src = pr.dir / (sys.argv[sys.argv.index('--bg') + 1] if '--bg' in sys.argv else cover.get('bg') or 'work/aroll.mp4')
    at = float(sys.argv[sys.argv.index('--at') + 1]) if '--at' in sys.argv else float(cover.get('at') or min(1.4, duration(src) / 3))
    frame = pr.dir / 'work' / 'cover-bg.jpg'
    grab(src, at, frame)
    lines = cover.get('lines')
    if not lines:
        text = plan.get('title') or plan.get('hook') or plan['sentences'][0]['text']
        ws = text.split()
        half = max(1, len(ws) // 2)
        lines = [[' '.join(ws[:half]), ''], [' '.join(ws[half:]), 'accent']] if len(ws) > 2 else [[text, 'accent']]
    pill = cover.get('pill') or cfg['brand'].get('name') or ''
    tag = cover.get('tag') or ''
    handle = cfg['brand'].get('handle') or ''
    fam_ar, fam_lt = cfg['font']['ar'], cfg['font']['latin']
    font_css = fonts.css_for([fam_ar, fam_lt])

    def colour(c):
        if c in ('', None):
            return 'linear-gradient(180deg,#ffffff 0%,#f1f1f6 45%,#b8b8c8 100%)'
        c = accent if c == 'accent' else c
        return f'linear-gradient(180deg,{c}dd 0%,{c} 45%,{c}99 100%)'

    def seg(t, c):
        fam = fam_ar if is_arabic(t) else fam_lt
        return f"<span class='l' style=\"background-image:{colour(c)};font-family:'{fam}'\">{t}</span>"

    body = ''.join(f"<div>{''.join(seg(*p) for p in (ln if isinstance(ln[0], list) else [ln]))}</div>" for ln in lines)
    n = sum(1 for _ in lines)
    size = 200 if n <= 2 else 160
    bg64 = base64.b64encode(frame.read_bytes()).decode('ascii')
    html = f"""<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><style>{font_css}
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#0b0b10}}
.bg{{position:absolute;inset:0;background:url(data:image/jpeg;base64,{bg64}) center/cover;filter:saturate(1.05)}}
.top{{position:absolute;inset:0 0 auto 0;height:980px;background:linear-gradient(180deg,rgba(8,8,14,.82) 0%,rgba(8,8,14,.45) 55%,rgba(8,8,14,0) 100%)}}
.bot{{position:absolute;inset:auto 0 0 0;height:420px;background:linear-gradient(0deg,rgba(8,8,14,.85),rgba(8,8,14,0))}}
.wrap{{position:absolute;left:44px;right:44px;top:200px;text-align:center}}
.pill{{display:inline-block;padding:12px 36px;border-radius:40px;background:rgba(8,8,14,.6);border:2px solid {accent};color:{accent};font-family:'{fam_ar}';font-weight:700;font-size:40px}}
.t{{margin-top:26px}}.t div{{white-space:nowrap;overflow:visible}}
.l{{display:inline-block;white-space:pre;font-weight:900;font-size:{size}px;line-height:1.1;-webkit-background-clip:text;background-clip:text;color:transparent;
   filter:drop-shadow(0 6px 0 rgba(0,0,0,.55)) drop-shadow(0 14px 0 rgba(0,0,0,.45)) drop-shadow(0 22px 40px rgba(0,0,0,.7))}}
.en{{display:inline-block;margin-top:22px;font-family:'{fam_lt}';font-weight:700;font-size:46px;letter-spacing:6px;color:#fff;direction:ltr;padding:8px 28px;background:rgba(8,8,14,.55);border-radius:12px}}
.h{{position:absolute;bottom:150px;left:0;right:0;text-align:center;font-family:'{fam_lt}';font-size:44px;color:#fff;letter-spacing:2px;direction:ltr;opacity:.9}}
</style></head><body><div class='bg'></div><div class='top'></div><div class='bot'></div>
<div class='wrap'><div class='pill'>{pill}</div><div class='t'>{body}</div>{f"<div class='en'>{tag}</div>" if tag else ''}</div>
{f"<div class='h'>{handle}</div>" if handle else ''}
<script>
// shrink every title line until it fits the frame width (long Arabic words at 200px overflow otherwise)
document.querySelectorAll('.t > div').forEach(function (line) {{
  var max = {W} - 88, size = parseFloat(getComputedStyle(line.querySelector('.l')).fontSize);
  while (line.scrollWidth > max && size > 60) {{ size -= 6; line.querySelectorAll('.l').forEach(function (s) {{ s.style.fontSize = size + 'px'; }}); }}
}});
</script></body></html>"""
    hp = pr.dir / 'work' / 'cover.html'
    hp.write_text(html, encoding='utf-8')
    from playwright.sync_api import sync_playwright
    out_png = pr.dir / 'out' / 'cover.png'
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={'width': W, 'height': H})
        pg.goto(hp.as_uri())
        pg.evaluate('document.fonts.ready')
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(out_png))
        br.close()
    run(['ffmpeg', '-v', 'error', '-y', '-i', str(out_png), '-q:v', '2', str(pr.dir / 'out' / 'cover.jpg')])
    pr.mark('cover', png=str(out_png))
    say(str(out_png))


if __name__ == '__main__':
    main()
