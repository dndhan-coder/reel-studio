"""Transcribe the A-roll with word timings (Whisper) and group the words into caption sentences.

  python3 words.py <project dir> [--model turbo|medium|small] [--language auto|ar|en]

Writes work/words.json (every word with start/end, in A-roll seconds) and sentences.json at the project root:
short caption lines (<= MAX_WORDS words, split on punctuation or a pause) that the plan step turns into plan.json.
Transcription runs AFTER the cut, so the times already match the picture. Nothing here is "final text": the
transcript is a draft the editor (Claude) corrects word by word before anything is drawn.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from common import run, say, die, have

MAX_WORDS = 6
MIN_WORDS = 2
GAP = 0.55          # a pause longer than this starts a new line
END_PUNCT = re.compile(r'[.!?؟،,;:…]+$')


def transcribe(proj, model, language):
    work = proj / 'work'
    wav = work / 'aroll16k.wav'
    run(['ffmpeg', '-v', 'error', '-y', '-i', work / 'aroll.mp4', '-vn', '-ac', '1', '-ar', '16000', '-f', 'wav', wav])
    if not have('whisper'):
        die('whisper غير مثبّت — شغّل: python3 reel.py setup')
    cmd = ['whisper', str(wav), '--model', model, '--word_timestamps', 'True', '--output_format', 'json',
           '--output_dir', str(work), '--fp16', 'False', '--verbose', 'False']
    if language and language != 'auto':
        cmd += ['--language', language]
    say(f'whisper ({model}) يفرّغ الكلام… (أوّل مرّة ينزّل الموديل)')
    run(cmd)
    data = json.loads((work / 'aroll16k.json').read_text(encoding='utf-8'))
    words = []
    for seg in data.get('segments', []):
        for w in seg.get('words', []):
            text = (w.get('word') or '').strip()
            if not text:
                continue
            words.append({"w": text, "s": round(float(w['start']), 3), "e": round(float(w['end']), 3)})
    # whisper sometimes gives zero-length or overlapping words; make them monotonic and >= 60 ms
    for i, w in enumerate(words):
        if i and w['s'] < words[i - 1]['e']:
            w['s'] = words[i - 1]['e']
        if w['e'] < w['s'] + 0.06:
            w['e'] = round(w['s'] + 0.06, 3)
    (work / 'words.json').write_text(json.dumps({"language": data.get('language'), "words": words},
                                                ensure_ascii=False, indent=1), encoding='utf-8')
    return data.get('language'), words


def sentences(words):
    out, cur = [], []

    def flush():
        if cur:
            out.append(list(cur))
            cur.clear()

    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        punct = bool(END_PUNCT.search(w['w']))
        gap = nxt is not None and nxt['s'] - w['e'] > GAP
        if nxt is None or len(cur) >= MAX_WORDS or ((punct or gap) and len(cur) >= MIN_WORDS):
            flush()
    # a trailing one-word line joins the line before it
    if len(out) > 1 and len(out[-1]) < MIN_WORDS:
        out[-2].extend(out.pop())
    res = []
    for i, ws in enumerate(out, 1):
        res.append({"id": f"s{i:02d}", "start": ws[0]['s'], "end": ws[-1]['e'],
                    "text": ' '.join(w['w'] for w in ws), "words": ws})
    return res


def main():
    proj = Path(sys.argv[1])
    model = sys.argv[sys.argv.index('--model') + 1] if '--model' in sys.argv else 'turbo'
    language = sys.argv[sys.argv.index('--language') + 1] if '--language' in sys.argv else 'auto'
    lang, words = transcribe(proj, model, language)
    sents = sentences(words)
    (proj / 'sentences.json').write_text(json.dumps({"language": lang, "sentences": sents},
                                                     ensure_ascii=False, indent=1), encoding='utf-8')
    say(f'{len(words)} كلمة · {len(sents)} سطر كابشن · اللغة: {lang}')
    for s in sents:
        say(f"  {s['id']}  {s['start']:6.2f}–{s['end']:6.2f}  {s['text']}")
    say(str(proj / 'sentences.json'))


if __name__ == '__main__':
    main()
