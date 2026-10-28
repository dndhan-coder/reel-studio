"""Draw the reel: captions, scenes and cards from plan.json through the HTML engine (Playwright + Chromium), the
speaker with zooms and grade, B-roll cutaways, music, in one ffmpeg pass.

  python3 render.py <project dir> [--overlay-only] [--compose-only] [--preview 12]

Pass 1  engine/overlay.html seeks frame by frame (deterministic: every frame is a pure function of t) and the
        screenshots stream into work/overlay.mov (QuickTime RLE with alpha). Frames whose picture did not change are
        reused, so still stretches cost nothing.
Pass 2  ffmpeg: A-roll (zoompan for the hook/punch zooms, grade) + B-roll cutaways + overlay + audio -> out/<slug>.mp4,
        plus out/<slug>.srt and out/cover.jpg.
--preview N renders only the first N seconds (fast check of the look).
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import W, H, FPS, ENGINE, load_config, run, say, die, duration, Project
import fonts

GRADES = {
    'none': '',
    'warm': 'colorbalance=rs=.06:gs=.01:bs=-.07:rm=.03:bm=-.04,eq=saturation=1.08:contrast=1.04',
    'cool': 'colorbalance=rs=-.05:gs=0:bs=.08:rm=-.02:bm=.04,eq=saturation=0.95:contrast=1.06',
    'film': 'curves=preset=vintage,eq=saturation=0.88:contrast=1.05,vignette=PI/5',
    'punch': 'eq=saturation=1.18:contrast=1.1:brightness=0.01,unsharp=5:5:0.6',
}


def render_overlay(pr, plan, cfg, seconds):
    from playwright.sync_api import sync_playwright
    font_css = fonts.css_for([cfg['font']['ar'], cfg['font']['latin']])
    out = pr.dir / 'work' / 'overlay.mov'
    n = int(round(seconds * FPS))
    ff = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'png',
                           '-i', 'pipe:0', '-c:v', 'qtrle', '-pix_fmt', 'argb', str(out)], stdin=subprocess.PIPE)
    t0 = time.time()
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--allow-file-access-from-files', '--disable-gpu-vsync'])
        pg = br.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        pg.goto((ENGINE / 'overlay.html').as_uri())
        pg.wait_for_function('() => !!window.rs')
        pg.evaluate('([plan, cfg, css]) => window.rs.load(plan, cfg, css)', [plan, cfg, font_css])
        pg.evaluate('document.fonts.ready')
        pg.wait_for_timeout(300)
        last_sig, last_png, drawn = None, None, 0
        for i in range(n):
            t = i / FPS
            sig = pg.evaluate('t => window.rs.seek(t)', t)
            if sig != last_sig:
                last_png = pg.screenshot(omit_background=True, type='png')
                last_sig = sig
                drawn += 1
            ff.stdin.write(last_png)
            if i % (FPS * 5) == 0:
                say(f'  overlay {t:5.1f}/{seconds:.1f}ث  (رُسم {drawn} إطار من {i + 1})')
        br.close()
    ff.stdin.close()
    ff.wait()
    if ff.returncode:
        die('ffmpeg فشل في كتابة overlay.mov')
    say(f'overlay: {n} إطار، رُسم {drawn} فعلياً، {time.time() - t0:.0f}ث → {out.name}')
    return out


def zoom_expr(plan, cfg):
    """zoompan zoom expression in terms of the input frame index `in` (t = in/FPS)."""
    terms = []
    for s in plan['sentences']:
        z = s.get('zoom')
        if not z:
            continue
        amt = 0.08 if z is True else float(z)
        a, b = s['start'], s['end']
        # ease in over 0.35 s, hold to the end of the sentence
        terms.append(f"if(between(in/{FPS},{a:.3f},{b:.3f}),{amt:.3f}*min(1,(in/{FPS}-{a:.3f})/0.35),0)")
    if cfg['extras'].get('hookZoom') and plan['sentences'] and not plan['sentences'][0].get('zoom'):
        s0 = plan['sentences'][0]
        terms.append(f"if(lt(in/{FPS},{s0['end']:.3f}),0.06*min(1,(in/{FPS})/{max(0.6, s0['end']):.3f}),0)")
    return '1+' + '+'.join(terms) if terms else None


def compose(pr, plan, cfg, overlay, seconds):
    aroll = pr.aroll
    inputs = ['-i', str(aroll), '-i', str(overlay)]
    chain = []
    # --- speaker: zoom + grade
    v = '[0:v]'
    zx = zoom_expr(plan, cfg)
    if zx:
        anchor = plan.get('zoomAnchor', 0.38)      # where the face is, as a fraction of the height
        chain.append(f"{v}zoompan=z='{zx}':x='iw/2-iw/zoom/2':y='ih*{anchor}-ih/zoom*{anchor}':d=1:s={W}x{H}:fps={FPS}[zv]")
        v = '[zv]'
    grade = GRADES.get(cfg['extras'].get('grade', 'none'), '')
    if grade:
        chain.append(f"{v}{grade}[gv]")
        v = '[gv]'
    chain.append(f"{v}trim=0:{seconds:.3f},setpts=PTS-STARTPTS,format=yuv420p[base]")
    v = '[base]'
    # --- b-roll cutaways
    k = 2
    for s in plan['sentences']:
        f = (s.get('broll') or {}).get('file')
        if not f or not (pr.dir / f).exists() or s['start'] >= seconds:
            continue
        a, b = s['start'], min(s['end'] + 0.25, seconds)
        if plan.get('type') == 'voiceover':
            b = min(s['end'] + 0.35, seconds)
        inputs += ['-i', str(pr.dir / f)]
        chain.append(f"[{k}:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                     f"setpts=PTS-STARTPTS+{a:.3f}/TB[b{k}]")
        chain.append(f"{v}[b{k}]overlay=eof_action=pass:enable='between(t,{a:.3f},{b:.3f})'[c{k}]")
        v = f'[c{k}]'
        k += 1
    # --- captions and scenes on top
    chain.append(f"{v}[1:v]overlay=format=auto:eof_action=pass[vout]")
    # --- audio: voice (+ music under it)
    music = plan.get('music') or cfg['extras'].get('music')
    if music and Path(music).expanduser().exists():
        inputs += ['-stream_loop', '-1', '-i', str(Path(music).expanduser())]
        gain = float(plan.get('musicGain', -20))
        chain.append(f"[{k}:a]volume={gain}dB,atrim=0:{seconds:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0, seconds - 1.5):.3f}:d=1.5[m]")
        chain.append(f"[0:a]atrim=0:{seconds:.3f},asetpts=PTS-STARTPTS[vo];[vo][m]amix=inputs=2:duration=first:dropout_transition=0,"
                     f"alimiter=limit=0.95[aout]")
    else:
        chain.append(f"[0:a]atrim=0:{seconds:.3f},asetpts=PTS-STARTPTS[aout]")
    out = pr.dir / 'out' / f'{pr.slug}.mp4'
    cmd = ['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(chain), '-map', '[vout]', '-map', '[aout]',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS),
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', str(out)]
    t0 = time.time()
    run(cmd)
    say(f'compose: {time.time() - t0:.0f}ث → {out}')
    return out


def write_srt(pr, plan):
    def ts(t):
        h, r = divmod(t, 3600)
        m, s = divmod(r, 60)
        return f'{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}'
    lines = []
    for i, s in enumerate(plan['sentences'], 1):
        lines += [str(i), f"{ts(s['start'])} --> {ts(s['end'])}", s['text'], '']
    p = pr.dir / 'out' / f'{pr.slug}.srt'
    p.write_text('\n'.join(lines), encoding='utf-8')
    return p


def cover_frame(pr, plan, out_video):
    t = plan.get('coverAt', min(0.8, max(0.2, duration(out_video) * 0.1)))
    cover = pr.dir / 'out' / 'cover.jpg'
    run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', str(out_video), '-frames:v', '1', '-q:v', '2', str(cover)])
    return cover


def main():
    proj_dir = Path(sys.argv[1])
    pr = Project(proj_dir.name)
    cfg = load_config()
    plan = pr.plan()
    if not pr.aroll.exists():
        die('ما فيه work/aroll.mp4 — شغّل cut أوّلاً')
    total = duration(pr.aroll)
    seconds = min(total, float(sys.argv[sys.argv.index('--preview') + 1])) if '--preview' in sys.argv else total
    plan['duration'] = total
    overlay = pr.dir / 'work' / 'overlay.mov'
    if '--compose-only' not in sys.argv:
        overlay = render_overlay(pr, plan, cfg, seconds)
    if '--overlay-only' in sys.argv:
        return
    out = compose(pr, plan, cfg, overlay, seconds)
    if '--preview' not in sys.argv:
        srt = write_srt(pr, plan)
        cover = cover_frame(pr, plan, out)
        pr.mark('render', out=str(out), srt=str(srt), cover=str(cover), font=cfg['font'], caption=cfg['caption'])
    say(str(out))


if __name__ == '__main__':
    main()
