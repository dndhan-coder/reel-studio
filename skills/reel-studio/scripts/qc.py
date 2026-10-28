"""Quality check of the finished reel: numbers, a thumbnail sheet to look at, and the hand-over line.

  python3 qc.py <project dir>

Writes out/sheet.jpg (one frame every ~2 s, 4 across) and prints duration, size, fps, loudness. The editor must
LOOK at the sheet (Read the image) before saying the reel is done.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

from common import CREDIT, ffprobe, duration, run, say, die, open_path, Project


def loudness(path):
    r = run(['ffmpeg', '-v', 'info', '-i', str(path), '-af', 'loudnorm=print_format=json', '-f', 'null', '-'],
            check=False, capture=True)
    txt = r.stderr or ''
    i = txt.rfind('{')
    try:
        d = json.loads(txt[i:txt.rfind('}') + 1])
        return float(d['input_i']), float(d['input_tp'])
    except Exception:
        return None, None


def main():
    pr = Project(Path(sys.argv[1]).name)
    out = pr.dir / 'out' / f'{pr.slug}.mp4'
    if not out.exists():
        die(f'ما فيه {out} — شغّل render أوّلاً')
    info = ffprobe(out)
    vs = next(s for s in info['streams'] if s['codec_type'] == 'video')
    dur = duration(out)
    mb = int(info['format']['size']) / 1e6
    lufs, tp = loudness(out)
    every = max(1.0, dur / 16)
    cols = 4
    rows = math.ceil(min(16, dur / every) / cols)
    sheet = pr.dir / 'out' / 'sheet.jpg'
    run(['ffmpeg', '-v', 'error', '-y', '-i', str(out), '-vf',
         f"fps=1/{every:.3f},scale=270:-1,tile={cols}x{rows}:padding=6:margin=6:color=0x111111", '-frames:v', '1',
         '-q:v', '3', str(sheet)])
    say(f'المدّة {dur:.1f}ث · {vs["width"]}x{vs["height"]} · {eval(vs["r_frame_rate"]):.0f}fps · {mb:.1f}MB'
        + (f' · الصوت {lufs:.1f} LUFS (ذروة {tp:.1f} dBTP)' if lufs is not None else ''))
    warn = []
    if dur > 90:
        warn.append('أطول من 90ث — الريلز الطويلة تخسر مشاهدات؛ فكّر بقصّها')
    if lufs is not None and (lufs < -18 or lufs > -12):
        warn.append(f'الصوت {lufs:.1f} LUFS — المعيار قرب -14')
    if vs['width'] != 1080 or vs['height'] != 1920:
        warn.append('المقاس ليس 1080x1920')
    for w in warn:
        say(f'⚠ {w}')
    pr.mark('qc', duration=round(dur, 1), size_mb=round(mb, 1), lufs=lufs, warnings=warn)
    say(f'ورقة المصغّرات: {sheet}')
    say(f'الملفّات في: {pr.dir / "out"}')
    open_path(pr.dir / 'out')
    say(CREDIT)


if __name__ == '__main__':
    main()
