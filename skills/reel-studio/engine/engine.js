/* Reel Studio engine — draws one 1080x1920 frame of captions, scenes and cards for a time t.
   Every frame is a pure function of (plan, config, t): no CSS transitions, no wall clock. The renderer
   (render.py) seeks frame by frame and screenshots; the picker page runs the same code in a loop for its previews.

   const eng = new ReelEngine(rootElement);  eng.load(plan, cfg, fontCss);  eng.seek(t) -> signature string
   window.rs = default instance on #root (overlay.html). ReelEngine.demo(cfg) -> a sample plan for previews. */
(function () {
  const W = 1080, H = 1920;
  const AR = /[؀-ۿ]/;
  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const outCubic = (p) => 1 - Math.pow(1 - p, 3);
  const inOutCubic = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  const outBack = (p) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); };
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const phase = (t, t0, dur) => clamp01((t - t0) / dur);
  const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36) + ':' + s.length; };
  const SIZES = { s: 62, m: 74, l: 88 };
  const POS_Y = { low: 1330, center: 980, high: 620 };

  function hexA(hex, a) {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(hex || '#ffffff');
    if (!m) return `rgba(255,255,255,${a})`;
    return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`;
  }

  class ReelEngine {
    constructor(root) {
      this.root = root;
      root.classList.add('rs-root');
      root.style.width = W + 'px'; root.style.height = H + 'px'; root.style.overflow = 'hidden'; root.style.background = 'transparent';
      root.style.direction = 'ltr';   // geometry is absolute; each text block carries its own dir
      if (getComputedStyle(root).position === 'static') root.style.position = 'relative';
      this._styleEl = null;
    }

    load(plan, cfg, fontCss) {
      this.plan = plan; this.cfg = cfg;
      const ar = cfg.font?.ar || 'Alexandria', lt = cfg.font?.latin || 'Anton';
      const dark = (cfg.brand?.theme || 'dark') !== 'light';
      this.theme = {
        accent: cfg.brand?.accent || '#FCC022',
        text: dark ? '#ffffff' : '#111318',
        ink: '#0b0b10',
        shadow: dark ? '0 2px 2px rgba(0,0,0,.7), 0 8px 26px rgba(0,0,0,.55)' : '0 1px 0 rgba(255,255,255,.9), 0 6px 22px rgba(255,255,255,.6)',
        fontAr: ar, fontLt: lt, dark,
      };
      const doc = this.root.ownerDocument;
      if (!this._styleEl) { this._styleEl = doc.createElement('style'); (doc.head || doc.body).appendChild(this._styleEl); }
      const id = 'rs' + Math.random().toString(36).slice(2, 7);
      this.root.dataset.rs = id;
      const r = `.rs-root[data-rs="${id}"]`;
      this._styleEl.textContent = `${fontCss || ''}
${r} *{box-sizing:border-box;margin:0;padding:0}
${r} .ar{font-family:'${ar}','Noto Sans Arabic','Tajawal',sans-serif}
${r} .lt{font-family:'${lt}','Inter','Helvetica Neue',sans-serif;unicode-bidi:isolate}
${r} .w{display:inline-block;white-space:pre;will-change:transform}
${r} .cap{position:absolute;left:60px;right:60px;text-align:center;line-height:1.22;text-shadow:${this.theme.shadow};color:${this.theme.text}}
${r} .pill{display:inline-block;padding:14px 34px;border-radius:999px;background:${hexA('#0b0b10', .62)};border:3px solid ${this.theme.accent};color:${this.theme.accent}}`;
      this.duration = plan.duration || (plan.sentences?.length ? plan.sentences[plan.sentences.length - 1].end + 0.5 : 10);
      this.sentences = plan.sentences || [];
    }

    /* ---------- helpers ---------- */
    span(word, cls, style) {
      const script = AR.test(word) ? 'ar' : 'lt';
      return `<span class="w ${script} ${cls || ''}" style="${style || ''}">${esc(word)}</span>`;
    }
    dirOf(text) { const a = (text.match(/[؀-ۿ]/g) || []).length, l = (text.match(/[A-Za-z]/g) || []).length; return a >= l ? 'rtl' : 'ltr'; }
    current(t) {
      const S = this.sentences;
      for (let i = 0; i < S.length; i++) {
        const s = S[i], next = S[i + 1];
        if (t >= s.start && (t < s.end || (next ? t < next.start : t < s.end + 0.6))) return [i, s];
      }
      return [-1, null];
    }
    wordIndex(s, t) {
      let wi = -1;
      s.words.forEach((w, i) => { if (t >= w.s) wi = i; });
      return wi;
    }

    /* ---------- captions ---------- */
    captions(t, out, capYOverride) {
      const cfg = this.cfg, th = this.theme;
      const [si, s] = this.current(t);
      if (!s) return;
      const style = cfg.caption?.style || 'keyword';
      const base = SIZES[cfg.caption?.size || 'm'] || 74;
      const em = new Set(s.em || []);
      const dir = this.dirOf(s.text);
      const y = capYOverride ?? (POS_Y[cfg.caption?.position || 'low'] || 1330);
      const wi = this.wordIndex(s, t);
      const pIn = phase(t, s.start, 0.22);
      const scaleIn = 0.86 + 0.14 * outBack(pIn);
      const wrap = (inner, extra = '', size = base) =>
        out.push(`<div class="cap" dir="${dir}" style="top:${y}px;transform:translateY(-50%) ${extra};font-size:${size}px;font-weight:700">${inner}</div>`);
      const badge = () => {
        if (this.plan.type !== 'tips' || !s.point) return '';
        const p = outBack(phase(t, s.start, 0.3));
        return `<div style="position:absolute;right:70px;top:${y - 230}px;width:150px;height:150px;border-radius:50%;background:${th.accent};color:#0b0b10;display:flex;align-items:center;justify-content:center;font-size:92px;font-weight:900;transform:scale(${p});box-shadow:0 10px 30px rgba(0,0,0,.4)" class="lt">${esc(s.point)}</div>`;
      };
      out.push(badge());

      if (style === 'oneword') {
        if (wi < 0) return;
        const w = s.words[wi];
        const p = outBack(phase(t, w.s, 0.16));
        const rot = ((wi * 7) % 5 - 2) * 0.8;
        const col = em.has(wi) ? th.accent : th.text;
        wrap(this.span(w.w, '', `color:${col};transform:scale(${0.7 + 0.3 * p}) rotate(${rot}deg);opacity:${clamp01(p * 2)};font-weight:900`), '', Math.round(base * 1.9));
        return;
      }
      if (style === 'karaoke') {
        const inner = s.words.map((w, i) => {
          const on = i === wi, done = i < wi;
          const col = on ? th.accent : th.text;
          const op = done || on ? 1 : 0.62;
          const sc = on ? 1.12 : 1;
          return this.span(w.w, '', `color:${col};opacity:${op};transform:scale(${sc});margin:0 10px;font-weight:${em.has(i) || on ? 900 : 700}`);
        }).join(' ');
        wrap(inner, `scale(${scaleIn})`);
        return;
      }
      if (style === 'weightshift' || style === 'boxed') {
        const inner = s.words.map((w, i) => {
          if (i > wi) return '';
          const p = outCubic(phase(t, w.s, 0.2));
          const isEm = em.has(i);
          let st = `transform:translateY(${(1 - p) * 34}px);opacity:${p};margin:0 10px;`;
          if (style === 'weightshift') st += `font-weight:${isEm ? 900 : 300};color:${isEm ? th.accent : th.text};`;
          else st += isEm ? `font-weight:900;color:#0b0b10;background:${th.accent};padding:4px 26px;border-radius:16px;text-shadow:none;` : `font-weight:700;color:${th.text};`;
          return this.span(w.w, '', st);
        }).join(' ');
        wrap(inner);
        return;
      }
      if (style === 'subtitle') {
        const inner = s.words.map((w, i) => this.span(w.w, '', `color:${em.has(i) ? th.accent : th.text};margin:0 6px;font-weight:${em.has(i) ? 700 : 500}`)).join(' ');
        out.push(`<div class="cap" dir="${dir}" style="top:1480px;font-size:${Math.round(base * .62)}px;letter-spacing:.5px;opacity:${phase(t, s.start, 0.2)};font-weight:500">${inner}</div>`);
        return;
      }
      if (style === 'outline') {
        const inner = s.words.map((w, i) => {
          const isEm = em.has(i);
          const st = isEm ? `color:transparent;-webkit-text-stroke:3px ${th.accent};text-shadow:none;margin:0 10px;font-weight:900` : `color:${th.text};margin:0 10px;font-weight:900`;
          return this.span(w.w, '', st);
        }).join(' ');
        wrap(inner, `scale(${scaleIn})`, Math.round(base * 1.08));
        return;
      }
      // keyword (default)
      const inner = s.words.map((w, i) => {
        const isEm = em.has(i);
        return this.span(w.w, '', `color:${isEm ? th.accent : th.text};font-weight:${isEm ? 900 : 700};margin:0 10px;transform:scale(${isEm ? 1.06 : 1})`);
      }).join(' ');
      wrap(inner, `scale(${scaleIn})`);
    }

    /* ---------- fixed furniture ---------- */
    furniture(t, out) {
      const cfg = this.cfg, th = this.theme, plan = this.plan;
      if (cfg.extras?.progress) {
        const p = clamp01(t / this.duration);
        out.push(`<div style="position:absolute;left:60px;right:60px;top:236px;height:8px;border-radius:4px;background:rgba(255,255,255,.18)"><div style="height:100%;width:${(p * 100).toFixed(2)}%;border-radius:4px;background:${th.accent}"></div></div>`);
      }
      if (cfg.brand?.handle) {
        out.push(`<div class="lt" dir="ltr" style="position:absolute;right:60px;top:268px;padding:8px 22px;border-radius:999px;background:rgba(11,11,16,.5);color:#fff;font-size:34px;letter-spacing:1px;opacity:.92">${esc(cfg.brand.handle)}</div>`);
      }
      if (plan.type === 'tips' && plan.title) {
        const p = outCubic(phase(t, 0.2, 0.45));
        out.push(`<div dir="${this.dirOf(plan.title)}" style="position:absolute;left:60px;right:60px;top:${330 - (1 - p) * 40}px;text-align:center;opacity:${p}"><span class="pill ${AR.test(plan.title) ? 'ar' : 'lt'}" style="font-size:48px;font-weight:800">${esc(plan.title)}</span></div>`);
      }
    }

    hookCard(t, out) {
      const plan = this.plan, th = this.theme;
      if (!plan.hook) return false;
      const dur = plan.hookSeconds || 2.2;
      if (t >= dur) return false;
      const fade = 1 - phase(t, dur - 0.3, 0.3);
      const words = plan.hook.split(/\s+/);
      const inner = words.map((w, i) => {
        const p = outBack(phase(t, 0.08 + i * 0.1, 0.4));
        const isLast = i >= words.length - 2;
        return this.span(w, '', `transform:translateY(${(1 - p) * 60}px);opacity:${clamp01(p * 1.5)};margin:0 12px;color:${isLast ? th.accent : '#fff'};font-weight:900`);
      }).join(' ');
      out.push(`<div style="position:absolute;inset:0;background:${hexA(th.ink, .96)};opacity:${fade}"></div>`);
      out.push(`<div class="cap" dir="${this.dirOf(plan.hook)}" style="top:50%;transform:translateY(-50%);font-size:96px;line-height:1.25;opacity:${fade};font-weight:900">${inner}</div>`);
      return true;
    }

    outro(t, out) {
      const o = this.plan.outro, th = this.theme, cfg = this.cfg;
      if (!o || !o.text) return false;
      const t0 = this.duration - (o.seconds || 2.4);
      if (t < t0) return false;
      const p = outCubic(phase(t, t0, 0.45));
      const y = 1920 - 560 * p;
      const handle = cfg.brand?.handle ? `<div class="lt" dir="ltr" style="font-size:52px;color:${th.accent};letter-spacing:2px;margin-bottom:22px">${esc(cfg.brand.handle)}</div>` : '';
      out.push(`<div style="position:absolute;left:0;right:0;top:${y}px;height:600px;background:${hexA(th.ink, .93)};border-top:6px solid ${th.accent};border-radius:48px 48px 0 0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 70px">
        ${handle}<div class="${AR.test(o.text) ? 'ar' : 'lt'}" dir="${this.dirOf(o.text)}" style="font-size:66px;font-weight:800;color:#fff;line-height:1.3">${esc(o.text)}</div></div>`);
      return true;
    }

    /* ---------- scenes ---------- */
    scenes(t, out) {
      const th = this.theme;
      for (const sc of this.plan.scenes || []) {
        if (t < sc.t0 || t >= sc.t1) continue;
        const pin = outBack(phase(t, sc.t0, sc.in || 0.35));
        const pout = 1 - phase(t, sc.t1 - 0.25, 0.25);
        const col = sc.color === 'accent' || !sc.color ? th.accent : sc.color;
        const op = `opacity:${Math.min(clamp01(pin * 1.6), pout)}`;
        const fontCls = (s) => (AR.test(s) ? 'ar' : 'lt');
        switch (sc.kind) {
          case 'card': {   // full-frame card with staggered lines
            out.push(`<div style="position:absolute;inset:0;background:${hexA(sc.bg || th.ink, .96)};${op}"></div>`);
            const lines = sc.lines || [];
            const total = lines.reduce((a, l) => a + (l.size || 110) * 1.25, 0);
            let y = H / 2 - total / 2;
            lines.forEach((l, i) => {
              const p = outBack(phase(t, sc.t0 + (sc.at || 0.25) * i, 0.45));
              const c = l.color === 'accent' ? th.accent : (l.color || '#fff');
              const words = String(l.text).split(/\s+/).map((w) => this.span(w, '', `margin:0 10px`)).join(' ');
              out.push(`<div class="cap" dir="${this.dirOf(l.text)}" style="top:${y}px;transform:translateY(${(1 - p) * 50}px) scale(${0.9 + 0.1 * p});font-size:${l.size || 110}px;color:${c};font-weight:900;${op};opacity:${Math.min(clamp01(p * 1.5), pout)}">${words}</div>`);
              y += (l.size || 110) * 1.25;
            });
            break;
          }
          case 'stamp': {  // rotated label that slams in
            const x = (sc.x ?? 0.5) * W, y = (sc.y ?? 0.3) * H;
            out.push(`<div class="${fontCls(sc.text)}" dir="${this.dirOf(sc.text)}" style="position:absolute;left:${x}px;top:${y}px;transform:translate(-50%,-50%) rotate(${sc.rot ?? -8}deg) scale(${0.6 + 0.4 * pin});padding:14px 44px;background:${col};color:${sc.textColor || '#0b0b10'};font-size:${sc.size || 84}px;font-weight:900;border-radius:18px;box-shadow:0 14px 40px rgba(0,0,0,.45);${op};white-space:nowrap">${esc(sc.text)}</div>`);
            break;
          }
          case 'counter': { // number rolling up
            const p = inOutCubic(phase(t, sc.t0, sc.roll || 1.2));
            const v = Math.round((sc.value || 0) * p);
            const num = (sc.format === 'plain' ? String(v) : v.toLocaleString('en-US'));
            const y = (sc.y ?? 0.42) * H;
            out.push(`<div style="position:absolute;left:60px;right:60px;top:${y}px;text-align:center;${op};transform:scale(${0.9 + 0.1 * pin})">
              <div class="lt" dir="ltr" style="font-size:${sc.size || 190}px;font-weight:900;color:${col};text-shadow:${th.shadow};letter-spacing:2px">${esc(sc.prefix || '')}${num}${esc(sc.suffix || '')}</div>
              ${sc.label ? `<div class="${fontCls(sc.label)}" dir="${this.dirOf(sc.label)}" style="font-size:54px;font-weight:700;color:#fff;text-shadow:${th.shadow};margin-top:8px">${esc(sc.label)}</div>` : ''}</div>`);
            break;
          }
          case 'list': {   // checklist, items appear at their own times
            const y0 = (sc.y ?? 0.3) * H;
            const items = sc.items || [];
            items.forEach((it, i) => {
              const at = sc.t0 + (it.at ?? i * 0.6);
              if (t < at) return;
              const p = outBack(phase(t, at, 0.4));
              out.push(`<div dir="${this.dirOf(it.text)}" style="position:absolute;left:90px;right:90px;top:${y0 + i * 118}px;display:flex;align-items:center;gap:26px;${op};transform:translateX(${(1 - p) * (this.dirOf(it.text) === 'rtl' ? 60 : -60)}px);opacity:${Math.min(clamp01(p * 1.5), pout)}">
                <div style="width:74px;height:74px;border-radius:50%;background:${col};color:#0b0b10;display:flex;align-items:center;justify-content:center;font-size:48px;font-weight:900;flex:none" class="lt">✓</div>
                <div class="${fontCls(it.text)}" style="font-size:${sc.size || 58}px;font-weight:700;color:#fff;text-shadow:${th.shadow};background:rgba(11,11,16,.45);padding:8px 24px;border-radius:16px">${esc(it.text)}</div></div>`);
            });
            break;
          }
          case 'bubble': {  // social comment with a typing effect
            const y = (sc.y ?? 0.6) * H;
            const n = Math.floor(phase(t, sc.t0 + 0.3, sc.type || 1.2) * String(sc.text).length);
            const typed = String(sc.text).slice(0, n);
            out.push(`<div dir="${this.dirOf(sc.text)}" style="position:absolute;left:80px;right:80px;top:${y + (1 - pin) * 40}px;${op};display:flex;gap:22px;align-items:flex-start">
              <div style="width:92px;height:92px;border-radius:50%;background:${col};flex:none;display:flex;align-items:center;justify-content:center;font-size:48px;font-weight:900;color:#0b0b10" class="lt">${esc((sc.name || '?')[0])}</div>
              <div style="background:#fff;color:#111;border-radius:30px;padding:22px 32px;box-shadow:0 14px 40px rgba(0,0,0,.4);max-width:820px">
                <div class="lt" dir="ltr" style="font-size:34px;font-weight:700;color:#555;margin-bottom:6px">${esc(sc.name || '')}</div>
                <div class="${fontCls(sc.text)}" style="font-size:${sc.size || 46}px;font-weight:600;line-height:1.3">${esc(typed)}<span style="opacity:${n < sc.text.length ? 1 : 0}">|</span></div></div></div>`);
            break;
          }
          case 'tag': {     // sticky label near the speaker
            const x = (sc.x ?? 0.5) * W, y = (sc.y ?? 0.62) * H;
            out.push(`<div class="${fontCls(sc.text)}" dir="${this.dirOf(sc.text)}" style="position:absolute;left:${x}px;top:${y}px;transform:translate(-50%,0) scale(${0.8 + 0.2 * pin});padding:12px 34px;background:${col};color:${sc.textColor || '#0b0b10'};font-size:${sc.size || 46}px;font-weight:800;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.4);${op};white-space:nowrap">${esc(sc.text)}
              <div style="position:absolute;left:50%;top:-18px;transform:translateX(-50%);border:12px solid transparent;border-bottom-color:${col};border-top:0"></div></div>`);
            break;
          }
          case 'dim': {     // spotlight: the room darkens, the face stays lit
            const a = (sc.amount ?? 0.6) * Math.min(clamp01(pin * 2), pout);
            const fx = (sc.x ?? 0.5) * 100, fy = (this.plan.zoomAnchor ?? 0.38) * 100;
            out.push(`<div style="position:absolute;inset:0;background:radial-gradient(ellipse ${sc.radius || 34}% ${(sc.radius || 34) * 0.7}% at ${fx}% ${fy}%,rgba(0,0,0,0) 0%,rgba(0,0,0,${a.toFixed(3)}) 100%)"></div>`);
            break;
          }
          case 'term': {    // a term in one language with its translation under it
            const y = (sc.y ?? 0.18) * H;
            out.push(`<div style="position:absolute;left:60px;right:60px;top:${y}px;text-align:center;${op};transform:translateY(${(1 - pin) * 30}px)">
              <div class="lt" dir="ltr" style="font-size:${sc.size || 96}px;font-weight:900;color:${col};letter-spacing:4px;text-shadow:${th.shadow}">${esc(sc.text)}</div>
              ${sc.sub ? `<div class="${fontCls(sc.sub)}" dir="${this.dirOf(sc.sub)}" style="font-size:54px;font-weight:700;color:#fff;text-shadow:${th.shadow};margin-top:4px">${esc(sc.sub)}</div>` : ''}</div>`);
            break;
          }
          case 'bars': {    // horizontal bars growing
            const y0 = (sc.y ?? 0.3) * H, items = sc.items || [];
            const max = Math.max(...items.map((i) => i.value || 0), 1);
            items.forEach((it, i) => {
              const p = outCubic(phase(t, sc.t0 + 0.15 * i, 0.9));
              const w = 760 * (it.value / max) * p;
              out.push(`<div dir="rtl" style="position:absolute;left:90px;right:90px;top:${y0 + i * 132}px;${op}">
                <div class="${fontCls(it.label)}" style="font-size:44px;font-weight:700;color:#fff;text-shadow:${th.shadow};margin-bottom:8px">${esc(it.label)} <span class="lt" dir="ltr" style="color:${col}">${esc(it.show ?? Math.round(it.value * p))}</span></div>
                <div style="height:30px;border-radius:15px;background:rgba(255,255,255,.18)"><div style="height:100%;width:${w}px;border-radius:15px;background:${i === (sc.highlight ?? 0) ? col : '#ffffff'};margin-right:0;float:right"></div></div></div>`);
            });
            break;
          }
          case 'versus': {  // two things face to face
            const y = (sc.y ?? 0.42) * H;
            const l = sc.left || '', r = sc.right || '';
            const pr = outBack(phase(t, sc.t0 + (sc.atRight ?? 0.5), 0.4));
            out.push(`<div style="position:absolute;left:60px;right:60px;top:${y}px;display:flex;align-items:center;justify-content:space-between;gap:20px;${op}">
              <div class="${fontCls(l)}" dir="${this.dirOf(l)}" style="flex:1;text-align:center;font-size:${sc.size || 72}px;font-weight:900;color:#fff;text-shadow:${th.shadow};transform:translateX(${(1 - pin) * -60}px)">${esc(l)}</div>
              <div class="lt" style="font-size:80px;color:${col};font-weight:900">${esc(sc.mid || 'VS')}</div>
              <div class="${fontCls(r)}" dir="${this.dirOf(r)}" style="flex:1;text-align:center;font-size:${sc.size || 72}px;font-weight:900;color:${col};text-shadow:${th.shadow};transform:translateX(${(1 - pr) * 60}px);opacity:${clamp01(pr * 1.5)}">${esc(r)}</div></div>`);
            break;
          }
          case 'flash': {   // a white flash on a beat
            const a = (1 - phase(t, sc.t0, sc.t1 - sc.t0)) * (sc.amount ?? 0.85);
            out.push(`<div style="position:absolute;inset:0;background:rgba(255,255,255,${a.toFixed(3)})"></div>`);
            break;
          }
          default: break;
        }
      }
    }

    seek(t) {
      const out = [];
      const inHook = this.hookCard(t, out);
      if (!inHook) {
        const outroOn = this.plan.outro && this.plan.outro.text && t >= this.duration - (this.plan.outro.seconds || 2.4);
        this.scenes(t, out);
        this.captions(t, out, outroOn && (this.cfg.caption?.position || 'low') === 'low' ? POS_Y.center : undefined);
        this.furniture(t, out);
        this.outro(t, out);
      }
      const html = out.join('');
      this.root.innerHTML = html;
      return hash(html);
    }

    static demo(cfg) {
      const type = cfg.type || 'talk';
      const mk = (id, start, end, text, em, extra) => {
        const ws = text.split(' '), d = (end - start) / ws.length;
        return Object.assign({ id, start, end, text, em, words: ws.map((w, i) => ({ w, s: +(start + i * d).toFixed(2), e: +(start + (i + 1) * d - 0.04).toFixed(2) })) }, extra || {});
      };
      const hookOff = type === 'story' ? 2.2 : 0;
      const S = [
        mk('s01', 0.25 + hookOff, 1.9 + hookOff, 'اليوم بعلّمك ثلاث أخطاء', [2]),
        mk('s02', 2.0 + hookOff, 3.7 + hookOff, 'يسوّيها كل مبتدئ في التداول', [4], type === 'tips' ? { point: 1 } : {}),
        mk('s03', 3.9 + hookOff, 5.9 + hookOff, 'الخطأ الأوّل ما عنده خطّة', [3], type === 'tips' ? { point: 2 } : {}),
        mk('s04', 6.1 + hookOff, 8.3 + hookOff, 'والثاني يدخل بدون وقف خسارة', [4, 5], type === 'tips' ? { point: 3 } : {}),
      ];
      return {
        type, duration: 11.2 + hookOff,
        title: type === 'tips' ? '٣ أخطاء المبتدئ' : '',
        hook: type === 'story' ? 'خسرت ٥٠٠٠ دولار في يوم واحد' : '', hookSeconds: 2.2,
        outro: cfg.extras?.outro ? { text: cfg.extras.outroText || 'تابعني لمزيد', seconds: 2.4 } : null,
        zoomAnchor: 0.38,
        scenes: type === 'voiceover' ? [] : [{ kind: 'stamp', t0: 4.6 + hookOff, t1: 6.0 + hookOff, text: 'خطأ!', x: 0.26, y: 0.56, rot: -10 }],
        sentences: S,
      };
    }
  }

  window.ReelEngine = ReelEngine;
  const root = document.getElementById('root');
  if (root) window.rs = new ReelEngine(root);
})();
