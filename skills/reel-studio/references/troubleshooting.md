# تشخيص سريع

| العرض | السبب | الحلّ |
|---|---|---|
| `ffmpeg: command not found` | ffmpeg غير مثبّت | ماك: `brew install ffmpeg` (يحتاج Homebrew من brew.sh). ويندوز: `winget install ffmpeg` ثمّ افتح نافذة جديدة. |
| `whisper غير مثبّت` | `setup` ما قدر يثبّته | `uv tool install openai-whisper` أو `python3 -m pip install --user openai-whisper`. |
| التفريغ بطيء جداً | موديل كبير على جهاز ضعيف | في الاستوديو اختر `small`، أو `reel.py words <slug> --model small`. |
| كلمات إنجليزية صارت عربية أو العكس | اللغة تلقائيّ خمّن غلط | `--language ar` أو `en`، أو ثبّتها في الاستوديو. المختلط: دع auto وصحّح يدوياً. |
| `Session expired` / `Not authenticated` من هيغسفيلد | لم يسجّل دخوله على هذا الجهاز | هو ينفّذ `higgsfield auth login` بنفسه (تفاعليّ). لا تطلب مفتاحاً في المحادثة. |
| `higgsfield: command not found` | الأداة غير مثبّتة | `curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh \| sh` ثمّ نافذة جديدة. |
| B-roll فشل بـ`unknown flag` | الموديل لا يقبل `--duration` | broll.py يعيد تلقائياً بلا الفلاق؛ إن استمرّ: `higgsfield model get <model> --json` واقرأ الحقول. |
| `ما قدرت أنزّل خطّ …` | بلا إنترنت أو اسم خطّ غلط | اتّصل وأعد `render`، أو تأكّد من الاسم كما في الاستوديو. بلا إنترنت يُرسم بخطّ النظام. |
| الكابشن فوق وجهه | وجهه منخفض في الكادر | في الاستوديو: الموضع «الوسط» أو «فوق»؛ أو للريل هذا فقط غيّر `caption.position` في config. و`zoomAnchor` في الخطّة لموضع وجهه. |
| مشهد فوق الكابشن | `y` المشهد في منطقة الكابشن | انظر جدول المواضع في plan-format.md؛ ارفعه (`y: 0.2`) أو انقل الكابشن. |
| الفيديو أفقيّ | صُوِّر بالعرض | يُقصّ من الجوانب إلى 9:16 تلقائياً؛ الأفضل التصوير عمودياً. |
| Playwright: `Executable doesn't exist` | Chromium غير منزَّل | `python3 -m playwright install chromium`. |
| الرسم بطيء | كل إطار يُرسم | طبيعيّ ~2–3× مدّة الريل. `--preview 8` للمعاينة. أطفئ شريط التقدّم في الاستوديو ليعاد استعمال الإطارات الثابتة. |
| الصوت ضعيف/قويّ | — | `cut` يطبّع الصوت إلى ‑16 LUFS؛ `qc` يحذّر إن خرج عن ‑18…‑12. |
| ملفّ من Google Drive / iCloud «فارغ» | ملفّ سحابيّ غير منزَّل | `reel.py new` ينسخه فيُنزَّل؛ إن فشل افتحه مرّة في Finder ليتنزّل. |
| الاستوديو لا يفتح | المنفذ 7788 مشغول | `reel.py studio --stop` ثمّ `reel.py studio`؛ أو افتح `http://127.0.0.1:7788/` يدوياً. |

**ويندوز:** الأوامر نفسها بـ`python` بدل `python3`، والمسارات بـ`\`. `open` يُستبدل تلقائياً. Chromium من Playwright يعمل.
**الخطّ الخاصّ:** ملفّات ttf/otf في `~/.reel-studio/fonts/custom/` باسم يبدأ باسم العائلة (`MyFont-Bold.otf`)، واكتب
الاسم في الاستوديو؛ `fonts.py` يفضّله على Google Fonts.
