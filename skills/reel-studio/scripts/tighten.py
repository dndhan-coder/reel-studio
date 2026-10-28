"""Cut the dead air out of a raw talking clip without dropping a word, and normalise it to a 1080x1920 30fps A-roll.

  python3 tighten.py <raw clip> <project dir> [--trim light|medium|strong|off]

Finds the stretches of sound, closes every pause longer than MAX_GAP to a breath, writes the kept pieces to
work/cuts.json (source seconds -> output seconds) and the result to work/aroll.mp4 with loudness-normalised audio.
Sources that are not 9:16 are scaled to cover and centre-cropped.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from common import W, H, FPS, duration, run, say

PRE, POST = 0.08, 0.14      # breath kept before the first sound / after the last one of every kept run
MIN_PIECE = 0.45            # a kept piece shorter than this is joined to its neighbour (no flash cuts)
MIN_RUN = 0.12              # sound shorter than this is a click, not speech
HOLD_END = 0.6              # the cut ends this long after the last sound
HEAD = 0.25                 # lead-in kept before the first sound
GAPS = {"light": 0.65, "medium": 0.40, "strong": 0.25}


def envelope(wav_path):
    with wave.open(str(wav_path)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop = int(sr * 0.01)
    n = max(1, len(x) // hop)
    rms = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    return 20 * np.log10(rms), 0.01


def sound_runs(db, dt, thr):
    on = db > thr
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start * dt, i * dt))
            start = None
    if start is not None:
        out.append((start * dt, len(on) * dt))
    return [(a, b) for a, b in out if b - a >= MIN_RUN]


def pieces_for(raw, wav, max_gap):
    total = duration(raw)
    if max_gap is None:
        return [[0.0, total]], total
    db, dt = envelope(wav)
    floor = np.percentile(db, 15)
    thr = max(floor + 12, -45)
    rr = sound_runs(db, dt, thr)
    if not rr:
        return [[0.0, total]], total
    pieces = []
    for a, b in rr:
        a0, b0 = max(0, a - PRE), min(total, b + POST)
        if pieces and a0 - pieces[-1][1] <= max_gap:
            pieces[-1][1] = b0
        else:
            pieces.append([a0, b0])
    pieces[0][0] = max(0, pieces[0][0] - HEAD)
    pieces[-1][1] = min(total, pieces[-1][1] + HOLD_END)
    merged = []
    for p in pieces:
        if merged and (p[1] - p[0] < MIN_PIECE or merged[-1][1] - merged[-1][0] < MIN_PIECE):
            merged[-1][1] = p[1]
        else:
            merged.append(p)
    return merged, total


def main():
    raw, proj = Path(sys.argv[1]), Path(sys.argv[2])
    trim = sys.argv[sys.argv.index('--trim') + 1] if '--trim' in sys.argv else 'medium'
    work = proj / 'work'
    work.mkdir(parents=True, exist_ok=True)
    wav = work / 'raw16k.wav'
    run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-vn', '-ac', '1', '-ar', '16000', '-f', 'wav', wav])
    pieces, total = pieces_for(raw, wav, GAPS.get(trim))
    kept = sum(b - a for a, b in pieces)
    tmap, t = [], 0.0
    for a, b in pieces:
        tmap.append({"src_in": round(a, 3), "src_out": round(b, 3), "out_in": round(t, 3)})
        t += b - a
    (work / 'cuts.json').write_text(json.dumps({"trim": trim, "source_seconds": round(total, 3),
                                                "kept_seconds": round(kept, 3), "pieces": tmap}, indent=1))
    say(f'{len(pieces)} قطعة · {total:.1f}ث → {kept:.1f}ث (انقصّ {total - kept:.1f}ث صمت)')
    vf = ';'.join(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]" for i, (a, b) in enumerate(pieces))
    af = ';'.join(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]" for i, (a, b) in enumerate(pieces))
    cat = ''.join(f"[v{i}][a{i}]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=1[vc][ac]"
    fc = (f"{vf};{af};{cat};[vc]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={W}:{H},format=yuv420p[vo];"
          f"[ac]highpass=f=80,afftdn=nf=-28,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ao]")
    out = work / 'aroll.mp4'
    run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-filter_complex', fc, '-map', '[vo]', '-map', '[ao]',
         '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-c:a', 'aac', '-b:a', '192k',
         '-movflags', '+faststart', out])
    say(str(out))


if __name__ == '__main__':
    main()
