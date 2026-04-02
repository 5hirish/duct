/* ────────────────────────────────────────────────────────────────
   demo.js — shared interactive demo engine
   Each for-*.html page loads a small demo-<variant>.js first, which
   sets window.DUCT_DEMO_CONFIG, then loads this file.

   DUCT_DEMO_CONFIG shape:
   {
     cfg: {
       min: 2,               // platforms needed to enable Next (default 1)
       src: {},              // platform name -> source label
       defs: {},             // metric key -> { hero, fmt, label, bar, ths, hide }
       cross: {},            // metric key -> [level, pill, title, body, owner, assignee, followUp]
       kpiKeys: [],          // ordered KPI keys e.g. ['retention','dau',...]
       kpiDefs: {},          // key -> { fmt: 'p1'|'p0'|'n1'|'k'|'int', sum: bool }
       defaultMetric: '',
       defaultPlatforms: [],
       sparkColor: '#2563eb'
     },
     data: {},               // D[platform][metric].{hero, k, r, s, sp, u}
     fill: function(S) {},   // optional override: replace default fill entirely
     minHint: 2              // platforms needed to hide #plat-hint (default: never hide)
   }
   All innerHTML assignments use esc() on data or are static strings.
   Content comes from hardcoded data constants, never from user input.
   ──────────────────────────────────────────────────────────────── */
(function () {
  var DCFG = window.DUCT_DEMO_CONFIG || {};
  var D    = DCFG.data || {};
  var CFG  = DCFG.cfg  || {};

  var S    = { step: 1, platforms: [], metric: null };
  var skip = false;
  var last = null;
  var sev  = { red: 0, yellow: 1, green: 2, grey: 3 };
  var svgT = {
    up:   '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m18 15-6-6-6 6"/></svg>',
    down: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>',
    flat: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 12h14"/></svg>'
  };

  /* -- URL / GTM helpers -- */
  function base() { return location.pathname + location.search; }
  function push(f) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event: 'demo_fragment_view', demo_fragment: f, page_location: base() + '#' + f });
  }
  function frag(f) {
    if (location.hash === '#' + f) { return; }
    history.replaceState(null, '', base() + '#' + f);
    push(f);
  }

  /* -- Report DOM mount / modal helpers -- */
  function mount(id) {
    var h = document.getElementById(id);
    var r = document.getElementById('duct-report-root');
    if (h && r && r.parentNode !== h) { h.appendChild(r); }
  }
  function hideModal() {
    mount('report-preview-host');
    var m = document.getElementById('report-modal');
    if (!m) { return; }
    m.style.display = 'none';
    document.body.style.overflow = '';
    if (last && last.focus) { last.focus(); }
    var topbar = m.querySelector('.modal-topbar');
    if (topbar) { topbar.classList.remove('modal-topbar--scrolled'); }
  }
  function syncTopbarElevation() {
    var sc = document.getElementById('modal-report-scroll-host');
    var tb = document.querySelector('#report-modal .modal-topbar');
    if (sc && tb) { tb.classList.toggle('modal-topbar--scrolled', sc.scrollTop > 2); }
  }
  function showModal() {
    last = document.activeElement;
    mount('modal-report-scroll-host');
    var m  = document.getElementById('report-modal');
    var sc = document.getElementById('modal-report-scroll-host');
    m.style.display = 'block';
    document.body.style.overflow = 'hidden';
    m.scrollTop = 0;
    if (sc) {
      sc.scrollTop = 0;
      if (!sc._ductScrollBound) {
        sc._ductScrollBound = true;
        sc.addEventListener('scroll', syncTopbarElevation, { passive: true });
      }
    }
    requestAnimationFrame(syncTopbarElevation);
    var cb = document.getElementById('modal-close-btn');
    if (cb) { setTimeout(function () { cb.focus(); }, 10); }
  }

  /* -- Progress dots -- */
  function prog() {
    for (var i = 1; i <= 4; i++) {
      var d = document.getElementById('prog-' + i);
      if (!d) { continue; }
      d.className = 'wt-dot';
      if (i < S.step) { d.classList.add('done'); }
      else if (i === S.step) { d.classList.add('active'); }
    }
  }

  /* -- Height animation -- */
  function pad(st) {
    var cs = getComputedStyle(st);
    return parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  }
  function prep() {
    var st = document.querySelector('.wt-steps-stage');
    if (!st || skip || matchMedia('(prefers-reduced-motion: reduce)').matches) { return; }
    var h = st.offsetHeight;
    if (h > 0) { st.style.height = h + 'px'; }
  }
  function runh() {
    var st = document.querySelector('.wt-steps-stage');
    var a  = document.getElementById('demo-step-' + S.step);
    if (!st || !a) { return; }
    if (skip || matchMedia('(prefers-reduced-motion: reduce)').matches) {
      st.style.height = '';
      return;
    }
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        st.style.height = (a.offsetHeight + pad(st)) + 'px';
        setTimeout(function () { st.style.height = 'auto'; }, 440);
      });
    });
  }

  /* -- Step sync -- */
  function syncSteps(n) {
    for (var i = 1; i <= 4; i++) {
      var e = document.getElementById('demo-step-' + i);
      if (!e) { continue; }
      var on = i === n;
      e.classList.toggle('active', on);
      if (on) { e.removeAttribute('inert'); } else { e.setAttribute('inert', ''); }
    }
  }
  function parseHash(raw) {
    if (raw.indexOf('demo-step-') !== 0) { return null; }
    var n = parseInt(raw.slice(10), 10);
    return n >= 1 && n <= 4 ? n : null;
  }
  function gotoStep(n, skipHash) {
    if (n < 1 || n > 4) { return; }
    var prev = S.step;
    if (n !== prev) { prep(); S.step = n; syncSteps(n); prog(); }
    if (!skipHash) { frag('demo-step-' + n); }
    if (n === 3 && prev !== 3) { analyse(); }
    if (n === 4) { doFill(); }
    if (n !== prev) { runh(); }
  }
  window.wtGoTo = function (n) { gotoStep(n, false); };

  /* -- Hash routing -- */
  function onHash() {
    var raw = location.hash.replace(/^#/, '');
    if (raw === 'demo-report') { gotoStep(4, true); showModal(); push('demo-report'); return; }
    hideModal();
    var n = parseHash(raw);
    if (n !== null) { gotoStep(n, true); }
  }
  function initHash() {
    var raw = location.hash.replace(/^#/, '');
    if (!raw) { return; }
    skip = true;
    try {
      if (raw === 'demo-report') { gotoStep(4, true); showModal(); push('demo-report'); return; }
      var n = parseHash(raw);
      if (n !== null) { gotoStep(n, true); }
    } finally { skip = false; }
  }

  /* -- Platform + metric interaction -- */
  window.wtTogglePlatform = function (name, btn) {
    var i = S.platforms.indexOf(name);
    if (i === -1) {
      S.platforms.push(name);
      btn.classList.add('selected');
      btn.setAttribute('aria-pressed', 'true');
    } else {
      S.platforms.splice(i, 1);
      btn.classList.remove('selected');
      btn.setAttribute('aria-pressed', 'false');
    }
    document.getElementById('wt-next-1').disabled = S.platforms.length < (CFG.min || 1);
    var hint = document.getElementById('plat-hint');
    if (hint && DCFG.minHint) {
      hint.style.opacity = S.platforms.length >= DCFG.minHint ? '0' : '1';
    }
  };
  window.wtSelectMetric = function (key, card) {
    S.metric = key;
    var cs = document.querySelectorAll('.metric-card');
    for (var i = 0; i < cs.length; i++) {
      cs[i].classList.remove('selected');
      cs[i].setAttribute('aria-pressed', 'false');
    }
    card.classList.add('selected');
    card.setAttribute('aria-pressed', 'true');
    document.getElementById('wt-next-2').disabled = false;
  };

  /* -- Analysis animation -- */
  function analyse() {
    var ls = document.querySelectorAll('.analyzing-line');
    var d  = 0;
    for (var i = 0; i < ls.length; i++) {
      (function (l, t) {
        setTimeout(function () { l.classList.add('visible'); }, t);
        setTimeout(function () { l.classList.add('done'); }, t + 380);
      })(ls[i], d);
      d += 450;
    }
    setTimeout(function () { gotoStep(4, false); }, d + 200);
  }

  /* -- Report helpers -- */
  /* esc() escapes all data before insertion; content is from static constants, not user input */
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
  function fmtVal(v, t) {
    if (t === 'p1') { return v.toFixed(1) + '%'; }
    if (t === 'p0') { return Math.round(v) + '%'; }
    if (t === 'n1') { return v.toFixed(1); }
    if (t === 'k')  { return v >= 1000 ? (v / 1000).toFixed(1) + 'K' : String(Math.round(v)); }
    return String(Math.round(v));
  }
  function trend(el, obj) {
    if (!el || !obj) { return; }
    el.className = 'kpi-trend tone-' + (obj.dot || 'grey');
    el.innerHTML = svgT[obj.trend] || svgT.flat; /* static SVG string, no user data */
  }
  function avgSpark(m) {
    var t = [0, 0, 0, 0, 0, 0, 0], c = 0;
    for (var i = 0; i < S.platforms.length; i++) {
      var pd = D[S.platforms[i]];
      if (!pd || !pd[m] || !pd[m].sp) { continue; }
      for (var j = 0; j < pd[m].sp.length; j++) { t[j] += pd[m].sp[j]; }
      c++;
    }
    if (!c) { return [0.4, 0.44, 0.48, 0.52, 0.56, 0.60, 0.64]; }
    for (var k = 0; k < t.length; k++) { t[k] = parseFloat((t[k] / c).toFixed(3)); }
    return t;
  }
  /* buildSparkSVG: output is a static SVG string; stop-color is a hardcoded hex from config */
  function buildSparkSVG(points) {
    var w = 130, h = 44, px = 4, py = 6;
    var mn  = Math.min.apply(null, points);
    var mx  = Math.max.apply(null, points);
    var rng = mx - mn || 1;
    var pts = [];
    for (var i = 0; i < points.length; i++) {
      var x = px + (i / (points.length - 1)) * (w - 2 * px);
      var y = h - py - ((points[i] - mn) / rng) * (h - 2 * py);
      pts.push(x.toFixed(1) + ',' + y.toFixed(1));
    }
    var dFill = 'M ' + pts.join(' L ') +
      ' L ' + pts[pts.length - 1].split(',')[0] + ',' + (h - py) +
      ' L ' + pts[0].split(',')[0] + ',' + (h - py) + ' Z';
    var col = esc(CFG.sparkColor || '#2563eb'); /* hex colour from config constant */
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg">' +
      '<defs><linearGradient id="sparkGradModal" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + col + '" stop-opacity="0.4"/>' +
      '<stop offset="100%" stop-color="' + col + '" stop-opacity="0"/>' +
      '</linearGradient></defs>' +
      '<path class="spark-fill" d="' + dFill + '" fill="url(#sparkGradModal)"/>' +
      '<polyline class="spark-line" points="' + pts.join(' ') + '"/></svg>';
  }
  function rows(m) {
    var out = [];
    for (var i = 0; i < S.platforms.length; i++) {
      var pd = D[S.platforms[i]];
      if (pd && pd[m] && pd[m].r) { out = out.concat(pd[m].r); }
    }
    out.sort(function (a, b) { return b[1] - a[1]; });
    return out.slice(0, 4);
  }
  function signals(m) {
    var out = [];
    for (var i = 0; i < S.platforms.length; i++) {
      var pd = D[S.platforms[i]];
      if (pd && pd[m] && pd[m].s) { out = out.concat(pd[m].s); }
    }
    out.sort(function (a, b) { return (sev[a[0]] || 9) - (sev[b[0]] || 9); });
    out = out.slice(0, 2);
    if (S.platforms.length >= 2 && CFG.cross && CFG.cross[m]) {
      var cx = CFG.cross[m];
      if (!Array.isArray(cx)) { /* normalise object to array */
        cx = [cx.level, cx.pill, cx.title, cx.body, cx.ownerName, cx.assignee, cx.followUp];
      }
      out.push(cx);
    }
    return out;
  }
  function aggK(m) {
    var keys = CFG.kpiKeys || [];
    var defs = CFG.kpiDefs || {};
    var out  = {};
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i], sum = 0, c = 0, samp = null;
      for (var j = 0; j < S.platforms.length; j++) {
        var pd = D[S.platforms[j]];
        if (!pd || !pd[m] || !pd[m].k || !pd[m].k[k]) { continue; }
        var src = pd[m].k[k];
        sum += src[0]; c++;
        if (!samp || (sev[src[3]] || 9) < (sev[samp[3]] || 9)) { samp = src; }
      }
      var kd  = defs[k] || {};
      var raw = kd.sum ? sum : (c ? sum / c : 0);
      out[k]  = { val: fmtVal(raw, kd.fmt || 'int'), delta: samp ? samp[1] : 'No change', trend: samp ? samp[2] : 'flat', dot: samp ? samp[3] : 'grey' };
    }
    return out;
  }
  /* buildBlock: all string values are run through esc(); avatar URL uses encodeURIComponent */
  function buildBlock(a) {
    return '<div class="signal-block signal-level-' + esc(a[0]) + '">' +
      '<span class="signal-pill ' + esc(a[0]) + '">' + esc(a[1]) + '</span>' +
      '<p class="signal-title">' + esc(a[2]) + '</p>' +
      '<p class="signal-body">' + esc(a[3]) + '</p>' +
      '<div class="signal-action"><div class="signal-action-row">' +
        '<div class="signal-action-cell">' +
          '<span class="signal-action-label">Who owns it</span>' +
          '<div class="signal-owner-block">' +
            '<img class="signal-owner-avatar" src="https://api.dicebear.com/9.x/notionists/svg?seed=' +
              encodeURIComponent(a[4] || a[5] || 'Duct') +
            '" width="40" height="40" alt="" loading="lazy" decoding="async"/>' +
            '<div class="signal-owner-text">' +
              '<span class="signal-owner-name">' + esc(a[4] || a[5]) + '</span>' +
              '<span class="signal-owner-role">' + esc(a[5] || '') + '</span>' +
            '</div></div></div>' +
        '<div class="signal-action-cell">' +
          '<span class="signal-action-label">Follow-up</span>' +
          '<span class="signal-action-value">' + esc(a[6] || '') + '</span>' +
        '</div></div></div></div>';
  }
  function buildSigHTML(arr) {
    var html = '';
    for (var i = 0; i < arr.length && i < 2; i++) { html += buildBlock(arr[i]); }
    if (arr.length > 2) {
      html += '<div id="modal-signal-extra" class="rpt-signal-extra-wrap" hidden>' + buildBlock(arr[2]) + '</div>';
      html += '<button type="button" class="rpt-show-more-signals" id="modal-signal-more">Show 1 more signal</button>';
    }
    return html;
  }
  function bindSignalMore() {
    var b = document.getElementById('modal-signal-more');
    var e = document.getElementById('modal-signal-extra');
    if (!b || !e) { return; }
    b.onclick = function () {
      if (e.hasAttribute('hidden')) { e.removeAttribute('hidden'); b.textContent = 'Show less'; }
      else { e.setAttribute('hidden', ''); b.textContent = 'Show 1 more signal'; }
    };
  }

  /* -- Default fill (Engine B -- used by organic and product variants) -- */
  function defaultFill() {
    if (!S.metric)           { S.metric    = CFG.defaultMetric    || (CFG.kpiKeys && CFG.kpiKeys[0]) || ''; }
    if (!S.platforms.length) { S.platforms = CFG.defaultPlatforms || []; }
    var m   = S.metric;
    var def = (CFG.defs && CFG.defs[m]) || {};
    var pd0 = D[S.platforms[0]] && D[S.platforms[0]][m];
    var rs  = rows(m);
    var sg  = signals(m);
    var ks  = aggK(m);
    var i, srcs = [];
    for (i = 0; i < S.platforms.length; i++) {
      srcs.push((CFG.src && CFG.src[S.platforms[i]]) || S.platforms[i]);
    }

    var subEl = document.getElementById('wt-brief-sub');
    if (subEl) { subEl.textContent = 'Optimised for ' + (def.label || m) + ' \u00B7 ' + S.platforms.join(' \u00B7 '); }
    var metaEl = document.getElementById('rpt-meta');
    if (metaEl) { metaEl.textContent = 'Example data \u00B7 ' + S.platforms.join(' \u00B7 '); }

    if (sg.length) {
      var rv = document.getElementById('rpt-verdict');
      if (rv) { rv.className = 'rpt-verdict rpt-verdict--modal ' + esc(sg[0][0]); rv.textContent = sg[0][2]; }
    }
    if (pd0) {
      var heroLbl = document.getElementById('rpt-hero-label');
      var heroVal = document.getElementById('rpt-hero-val');
      var heroRow = document.getElementById('rpt-hero-delta-row');
      if (heroLbl) { heroLbl.textContent = def.hero || m; }
      if (heroVal) { heroVal.textContent = fmtVal(pd0.hero[0], def.fmt || 'int'); }
      if (heroRow) {
        heroRow.innerHTML = ''; /* cleared before repopulation with safe DOM nodes */
        var ht = document.createElement('span'); trend(ht, { trend: pd0.hero[2], dot: pd0.hero[3] }); heroRow.appendChild(ht);
        var hs = document.createElement('span'); hs.textContent = pd0.hero[1]; heroRow.appendChild(hs);
      }
    }

    var sparkEl = document.getElementById('rpt-sparkline');
    if (sparkEl) { sparkEl.innerHTML = buildSparkSVG(avgSpark(m)); /* static SVG string */ }

    var barLbl = document.getElementById('rpt-bar-label-text');
    if (barLbl) { barLbl.textContent = def.bar || ''; }

    var barsEl = document.getElementById('rpt-roas-bars');
    if (barsEl) {
      var max = 1;
      for (i = 0; i < rs.length; i++) { max = Math.max(max, rs[i][1]); }
      var bh = '';
      for (i = 0; i < rs.length; i++) {
        /* rs[i][0] and rs[i][2] are data strings, escaped with esc() */
        bh += '<div class="rpt-bar-row">' +
          '<div class="rpt-bar-top"><span class="rpt-bar-name">' + esc(rs[i][0]) + '</span>' +
          '<span class="rpt-bar-val">' + esc(rs[i][2]) + '</span></div>' +
          '<div class="rpt-bar-track"><div class="rpt-bar-fill" style="width:' +
            Math.round((rs[i][1] / max) * 100) + '%"></div></div></div>';
      }
      barsEl.innerHTML = bh;
    }

    var ths = def.ths || [];
    var thEls = document.querySelectorAll('#rpt-camp-panel thead th');
    for (i = 0; i < ths.length; i++) { if (thEls[i]) { thEls[i].textContent = ths[i]; } }
    var tb = '';
    for (i = 0; i < rs.length; i++) {
      /* all cell values escaped with esc() */
      tb += '<tr class="' + (i % 2 ? 'camp-row--alt' : '') + '">' +
        '<td>' + esc(rs[i][0]) + '</td><td>' + esc(rs[i][3]) + '</td>' +
        '<td>' + esc(rs[i][4]) + '</td><td>' + esc(rs[i][5]) + '</td>' +
        '<td>' + esc(rs[i][6]) + '</td></tr>';
    }
    var tbEl = document.getElementById('rpt-camp-tbody');
    if (tbEl) { tbEl.innerHTML = tb; }
    var campMeta = document.getElementById('rpt-camp-meta');
    if (campMeta) { campMeta.textContent = ' \u00B7 ' + rs.length + ' rows'; }

    var sigEl = document.getElementById('rpt-signals');
    if (sigEl) { sigEl.innerHTML = buildSigHTML(sg); }
    bindSignalMore();

    var hintEl = document.getElementById('rpt-kpi-hint');
    if (hintEl) { hintEl.textContent = CFG.kpiHint || 'Cross-tool snapshot from your selected tools. Example data only.'; }

    if (pd0 && pd0.u) {
      var ueIds = ['rpt-ue-cps', 'rpt-ue-ltv', 'rpt-ue-verdict', 'rpt-ue-summary'];
      for (i = 0; i < ueIds.length; i++) {
        var el = document.getElementById(ueIds[i]);
        if (el) { el.textContent = pd0.u[i] || ''; }
      }
    }
    var footerEl = document.getElementById('rpt-footer-sources');
    if (footerEl) {
      footerEl.textContent = 'Data: ' + srcs.join(' \u00B7 ') + ' \u00B7 Example data \u00B7 Optimised for ' + (def.label || m);
    }

    var keys = CFG.kpiKeys || [];
    for (i = 0; i < keys.length; i++) {
      var key  = keys[i];
      var kdat = ks[key];
      var b    = 'rpt-kpi-' + key;
      var valE = document.getElementById(b + '-val');
      var dltE = document.getElementById(b + '-delta');
      var trdE = document.getElementById(b + '-trend');
      if (valE) { valE.textContent = kdat.val; }
      if (dltE) { dltE.textContent = kdat.delta; }
      if (trdE) { trend(trdE, kdat); }
      var chip = valE && valE.closest('.kpi-chip');
      if (chip) {
        chip.classList.remove('kpi-chip--accent-red', 'kpi-chip--accent-yellow', 'kpi-chip--accent-green', 'kpi-chip--accent-grey', 'kpi-chip--modal-hidden');
        chip.classList.add('kpi-chip--accent-' + kdat.dot);
        if (key === def.hide) { chip.classList.add('kpi-chip--modal-hidden'); }
      }
    }
    var cp = document.getElementById('rpt-camp-panel'), ct = document.getElementById('rpt-camp-toggle');
    var up = document.getElementById('rpt-ue-panel'),   ut = document.getElementById('rpt-ue-toggle');
    if (cp) { cp.setAttribute('hidden', ''); } if (ct) { ct.setAttribute('aria-expanded', 'false'); }
    if (up) { up.setAttribute('hidden', ''); } if (ut) { ut.setAttribute('aria-expanded', 'false'); }
  }

  function doFill() {
    if (DCFG.fill) { DCFG.fill(S); return; }
    defaultFill();
  }

  /* -- Disclosure accordions -- */
  function disc(btnId, panelId) {
    var b = document.getElementById(btnId), p = document.getElementById(panelId);
    if (!b || !p || b._bound) { return; }
    b._bound = true;
    b.addEventListener('click', function () {
      var open = p.hasAttribute('hidden');
      if (open) { p.removeAttribute('hidden'); b.setAttribute('aria-expanded', 'true'); }
      else       { p.setAttribute('hidden', ''); b.setAttribute('aria-expanded', 'false'); }
    });
  }

  /* -- Modal open / close -- */
  window.openReportModal = function () {
    if (location.hash !== '#demo-report') { location.hash = 'demo-report'; }
    else { gotoStep(4, true); showModal(); push('demo-report'); }
  };
  window.closeReportModal = function () {
    hideModal();
    if (location.hash === '#demo-report') { history.replaceState(null, '', base() + '#demo-step-4'); }
  };

  /* -- Restart -- */
  window.wtRestart = function () {
    prep();
    S.step = 1; S.platforms = []; S.metric = null;
    var bs = document.querySelectorAll('.plat-btn'), cs = document.querySelectorAll('.metric-card'), ls = document.querySelectorAll('.analyzing-line');
    for (var i = 0; i < bs.length; i++) { bs[i].classList.remove('selected'); bs[i].setAttribute('aria-pressed', 'false'); }
    for (i = 0; i < cs.length; i++) { cs[i].classList.remove('selected'); cs[i].setAttribute('aria-pressed', 'false'); }
    for (i = 0; i < ls.length; i++) { ls[i].classList.remove('visible', 'done'); }
    document.getElementById('wt-next-1').disabled = true;
    document.getElementById('wt-next-2').disabled = true;
    var hint = document.getElementById('plat-hint');
    if (hint && DCFG.minHint) { hint.style.opacity = '1'; }
    syncSteps(1); prog(); runh();
    hideModal();
    document.body.style.overflow = '';
    frag('demo-step-1');
  };

  /* -- Keyboard: Escape + focus trap -- */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeReportModal(); }
    var m = document.getElementById('report-modal');
    if (!m || m.style.display !== 'block' || e.key !== 'Tab') { return; }
    var focusable = m.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])');
    var arr = [];
    for (var i = 0; i < focusable.length; i++) { if (focusable[i].offsetParent !== null) { arr.push(focusable[i]); } }
    if (!arr.length) { return; }
    var first = arr[0], lastEl = arr[arr.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastEl.focus(); }
    else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); first.focus(); }
  });

  /* -- Click outside modal sheet to close -- */
  var modalEl = document.getElementById('report-modal');
  if (modalEl) { modalEl.addEventListener('click', function (e) { if (e.target === this) { closeReportModal(); } }); }

  /* -- Init -- */
  window.addEventListener('hashchange', onHash);
  disc('rpt-camp-toggle', 'rpt-camp-panel');
  disc('rpt-ue-toggle', 'rpt-ue-panel');
  syncSteps(1);
  prog();
  initHash();
})();
