/* ─────────────────────────────────────────────────────────────
   Ariadne Concierge — step preview vizes.
   Five compact animations matching v7's vocabulary, shown on
   chip hover beneath the path strip. Each viz is a {html, start,
   stop} bundle. start() runs the loop; stop() clears timers.
   ───────────────────────────────────────────────────────────── */
(() => {
  const ease = t => 1 - Math.pow(1 - t, 3);

  // Shared tiny counter ticker
  function animateCounter(el, target, duration) {
    if (!el) return null;
    const start = performance.now();
    let raf;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const v = Math.round(target * ease(t));
      el.textContent = v;
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => raf && cancelAnimationFrame(raf);
  }

  function timerSet() {
    const ids = [];
    return {
      after(fn, ms) { const id = setTimeout(fn, ms); ids.push(id); return id; },
      clear() { ids.forEach(clearTimeout); ids.length = 0; },
    };
  }

  // ──────────────────────────── 1. SOURCING ────────────────────────────
  const sourcing = {
    html: `
      <div class="viz-stage vz-sourcing">
        <div class="vz-head">
          <div>
            <div class="vz-title">Sourcing &middot; scanning suppliers</div>
            <div class="vz-sub">Turned-beech canopy, cast-bronze fitting, hand-thrown ceramic shade.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>

        <div class="map-stage">
          <svg viewBox="0 0 300 180" preserveAspectRatio="xMidYMid meet">
            <!-- scattered noise dots -->
            <g class="map-noise"></g>
            <!-- hub -->
            <circle class="map-pulse" cx="150" cy="100" r="3"></circle>
            <circle class="map-dot hub" cx="150" cy="100" r="3.5"></circle>
            <!-- arcs to candidates -->
            <g class="map-arcs"></g>
            <!-- candidate dots -->
            <g class="map-dots"></g>
          </svg>
        </div>

        <div class="map-side">
          <div class="lbl">Candidates</div>
          <div class="cand-row" data-i="0"><span class="who">Müller-Werke</span><span class="where">DE · Bavaria</span></div>
          <div class="cand-row" data-i="1"><span class="who">Studio Ito</span><span class="where">JP · Kyoto</span></div>
          <div class="cand-row" data-i="2"><span class="who">Roca Cerámica</span><span class="where">ES · Granada</span></div>
          <div class="cand-row" data-i="3"><span class="who">Hudson Brass</span><span class="where">US · Hudson, NY</span></div>
          <div class="cand-row" data-i="4"><span class="who">Atelier Vasse</span><span class="where">FR · Lyon</span></div>
        </div>

        <div class="vz-foot">
          <span><em>63</em> factories evaluated &middot; one signed.</span>
          <span class="vz-meta">step 02 / sourcing</span>
        </div>
      </div>
    `,
    start(root) {
      const stage = root.querySelector('.viz-stage');
      const svg = root.querySelector('.map-stage svg');
      const noise = root.querySelector('.map-noise');
      const dotsG = root.querySelector('.map-dots');
      const arcsG = root.querySelector('.map-arcs');
      const rows  = Array.from(root.querySelectorAll('.cand-row'));
      const SVGNS = 'http://www.w3.org/2000/svg';

      // Candidate positions around hub (150,100)
      const cands = [
        { x:  78, y:  62, signed: true  },  // Müller-Werke (DE)
        { x: 232, y:  56, signed: false },  // Studio Ito (JP)
        { x:  92, y: 132, signed: false },  // Roca (ES)
        { x: 196, y: 138, signed: false },  // Hudson (US)
        { x: 124, y:  44, signed: false },  // Atelier Vasse (FR)
      ];

      // Noise dots
      noise.innerHTML = '';
      for (let i = 0; i < 60; i++) {
        const c = document.createElementNS(SVGNS, 'circle');
        c.setAttribute('cx', 12 + Math.random() * 276);
        c.setAttribute('cy', 12 + Math.random() * 156);
        c.setAttribute('r', 0.6 + Math.random() * 0.6);
        c.setAttribute('fill', 'rgba(26,22,18,0.12)');
        noise.appendChild(c);
      }

      // Arcs (quadratic curves from hub)
      arcsG.innerHTML = '';
      dotsG.innerHTML = '';
      cands.forEach((c, i) => {
        const mx = (150 + c.x) / 2;
        const my = Math.min(150, c.y) - 28;
        const p = document.createElementNS(SVGNS, 'path');
        p.setAttribute('class', 'map-arc');
        p.setAttribute('d', `M 150 100 Q ${mx} ${my} ${c.x} ${c.y}`);
        p.dataset.i = i;
        arcsG.appendChild(p);
        const d = document.createElementNS(SVGNS, 'circle');
        d.setAttribute('class', 'map-dot cand');
        d.setAttribute('cx', c.x);
        d.setAttribute('cy', c.y);
        d.setAttribute('r', 2.4);
        d.dataset.i = i;
        dotsG.appendChild(d);
      });

      const arcs = Array.from(arcsG.children);
      const dots = Array.from(dotsG.children);
      const T = timerSet();

      function loop() {
        // Reset
        arcs.forEach(a => a.classList.remove('draw', 'signed', 'failed'));
        dots.forEach(d => { d.classList.remove('signed', 'failed'); d.classList.add('cand'); });
        rows.forEach(r => r.classList.remove('in', 'fail', 'signed'));

        T.after(() => stage.classList.add('on'), 60);

        // Reveal arcs in sequence
        cands.forEach((c, i) => {
          T.after(() => {
            arcs[i].classList.add('draw');
            rows[i].classList.add('in');
          }, 220 + i * 280);
        });

        // Resolve: most fail, one signs
        T.after(() => {
          cands.forEach((c, i) => {
            if (c.signed) {
              arcs[i].classList.remove('failed'); arcs[i].classList.add('signed');
              dots[i].classList.remove('failed'); dots[i].classList.add('signed');
              rows[i].classList.add('signed');
            } else {
              arcs[i].classList.add('failed');
              dots[i].classList.add('failed');
              rows[i].classList.add('fail');
            }
          });
        }, 220 + cands.length * 280 + 600);

        // Loop
        T.after(loop, 6000);
      }
      loop();

      return () => T.clear();
    },
  };

  // ──────────────────────────── 2. MANUFACTURING ────────────────────────────
  const manufacturing = {
    html: `
      <div class="viz-stage vz-manufacturing">
        <div class="vz-head">
          <div>
            <div class="vz-title">Run 047 &middot; Müller-Werke</div>
            <div class="vz-sub">Bavaria &middot; first article approved &middot; on the line.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>

        <div class="mf-num"><span class="mf-count" data-target="500">0</span><span>units</span></div>

        <div class="mf-bar-wrap">
          <div class="mf-bar"><div class="mf-fill"></div></div>
          <div class="mf-bar-meta">
            <span class="mf-status">Casting</span>
            <span>0 → 500</span>
          </div>
        </div>

        <div class="mf-checks">
          <div class="mf-check" data-i="0"><span class="mf-bul"></span>Tooling cut</div>
          <div class="mf-check" data-i="1"><span class="mf-bul"></span>First article</div>
          <div class="mf-check" data-i="2"><span class="mf-bul"></span>Run started</div>
          <div class="mf-check" data-i="3"><span class="mf-bul"></span>Packout begun</div>
        </div>

        <div class="vz-foot">
          <span><em>9 days</em> from tooling to first unit &middot; 11 weeks faster than baseline.</span>
          <span class="vz-meta">step / manufacturing</span>
        </div>
      </div>
    `,
    start(root) {
      const stage = root.querySelector('.viz-stage');
      const count = root.querySelector('.mf-count');
      const fill  = root.querySelector('.mf-fill');
      const status = root.querySelector('.mf-status');
      const checks = Array.from(root.querySelectorAll('.mf-check'));
      const stages = ['Casting', 'Turning canopy', 'Glazing', 'Final assembly', 'Packout'];
      const T = timerSet();
      let counterStop = null;

      function loop() {
        // Reset
        stage.classList.remove('on');
        checks.forEach(c => c.classList.remove('done'));
        fill.style.inset = '0 100% 0 0';
        count.textContent = '0';
        status.textContent = stages[0];

        T.after(() => stage.classList.add('on'), 60);
        T.after(() => { fill.style.inset = '0 0 0 0'; }, 220);
        T.after(() => { counterStop = animateCounter(count, 500, 2400); }, 240);

        // Stage rotates
        stages.forEach((s, i) => {
          T.after(() => { status.textContent = s; }, 220 + i * 540);
        });

        checks.forEach((c, i) => {
          T.after(() => c.classList.add('done'), 540 + i * 560);
        });

        T.after(loop, 6200);
      }
      loop();

      return () => { T.clear(); counterStop && counterStop(); };
    },
  };

  // ──────────────────────────── 3. QUALITY ────────────────────────────
  const quality = {
    html: `
      <div class="viz-stage vz-quality">
        <div class="vz-head">
          <div>
            <div class="vz-title">Inspection &middot; sample of 250</div>
            <div class="vz-sub">Veneer grain &middot; rim true &middot; cord tension &middot; bulb fit.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>
        <div class="qc-grid"></div>
        <div class="qc-side">
          <div class="qc-stat pass"><span class="n" data-target="247">0</span>passed</div>
          <div class="qc-stat fail"><span class="n" data-target="3">0</span>flagged</div>
          <div class="qc-stat rate"><span class="n" data-target="98">0</span>% pass rate</div>
        </div>
        <div class="vz-foot">
          <span><em>3 flagged</em> &middot; held back, re-finished, re-inspected. The other 247 ship.</span>
          <span class="vz-meta">step / quality</span>
        </div>
      </div>
    `,
    start(root) {
      const stage = root.querySelector('.viz-stage');
      const grid  = root.querySelector('.qc-grid');
      const stats = Array.from(root.querySelectorAll('.qc-stat .n'));
      const N = 250;
      grid.innerHTML = '';
      for (let i = 0; i < N; i++) {
        const c = document.createElement('div');
        c.className = 'qc-cell';
        grid.appendChild(c);
      }
      const cells = Array.from(grid.children);
      const T = timerSet();
      const counterStops = [];

      // Pick 3 random fails (deterministic across loops for storytelling)
      const failIdx = [37, 132, 198];

      function loop() {
        stage.classList.remove('on');
        cells.forEach(c => c.classList.remove('scan', 'pass', 'fail'));
        stats.forEach(s => s.textContent = '0');

        T.after(() => stage.classList.add('on'), 60);

        // Sweep through in a wave
        cells.forEach((c, i) => {
          const t0 = 200 + i * 9;
          T.after(() => c.classList.add('scan'), t0);
          T.after(() => {
            c.classList.remove('scan');
            c.classList.add(failIdx.includes(i) ? 'fail' : 'pass');
          }, t0 + 220);
        });

        // Counters
        T.after(() => counterStops.push(animateCounter(stats[0], 247, 2200)), 320);
        T.after(() => counterStops.push(animateCounter(stats[1],   3, 2200)), 320);
        T.after(() => counterStops.push(animateCounter(stats[2],  98, 2200)), 320);

        T.after(loop, 6200);
      }
      loop();

      return () => { T.clear(); counterStops.forEach(s => s && s()); };
    },
  };

  // ──────────────────────────── 4. FULFILLMENT ────────────────────────────
  const fulfillment = {
    html: `
      <div class="viz-stage vz-fulfillment">
        <div class="vz-head">
          <div>
            <div class="vz-title">Container HASU-218845</div>
            <div class="vz-sub">Müller-Werke &rsaquo; Bremerhaven &rsaquo; Brooklyn &rsaquo; you.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>

        <div class="fu-rail-wrap">
          <div class="fu-rail">
            <div class="fu-fill"></div>
            <div class="fu-cargo"></div>
            <div class="fu-stop" style="left:  0%"></div>
            <div class="fu-stop-label reached" style="left:  0%">Factory</div>
            <div class="fu-stop-name"           style="left:  0%">Bavaria</div>
            <div class="fu-stop" style="left: 33%"></div>
            <div class="fu-stop-label" style="left: 33%">Port</div>
            <div class="fu-stop-name"  style="left: 33%">Bremerhaven</div>
            <div class="fu-stop" style="left: 66%"></div>
            <div class="fu-stop-label" style="left: 66%">Port</div>
            <div class="fu-stop-name"  style="left: 66%">Brooklyn</div>
            <div class="fu-stop" style="left:100%"></div>
            <div class="fu-stop-label" style="left:100%">Doorstep</div>
            <div class="fu-stop-name"  style="left:100%">Greenpoint</div>
          </div>
        </div>

        <div class="fu-meta-row">
          <div>
            <div class="fu-eta"><span class="fu-day" data-target="12">0</span><i>days</i></div>
            <div class="fu-eta-label">to your door, customs cleared.</div>
          </div>
          <div class="fu-side">
            <div class="lbl">Now</div>
            <div class="fu-now">In transit · Atlantic, day 6 of 12.</div>
          </div>
        </div>

        <div class="vz-foot">
          <span><em>One container.</em> Sea, not air. The carbon footprint of the run, not your day.</span>
          <span class="vz-meta">step / fulfillment</span>
        </div>
      </div>
    `,
    start(root) {
      const stage = root.querySelector('.viz-stage');
      const fill  = root.querySelector('.fu-fill');
      const cargo = root.querySelector('.fu-cargo');
      const day   = root.querySelector('.fu-day');
      const now   = root.querySelector('.fu-now');
      const stops = Array.from(root.querySelectorAll('.fu-stop'));
      const labels = Array.from(root.querySelectorAll('.fu-stop-label'));
      const T = timerSet();
      let counterStop = null;

      function loop() {
        stage.classList.remove('on');
        stops.forEach((s, i) => s.classList.toggle('reached', i === 0));
        labels.forEach((l, i) => l.classList.toggle('reached', i === 0));
        fill.style.inset = '0 100% 0 0';
        cargo.style.left = '0%';
        day.textContent = '0';
        now.textContent = 'Leaving factory dock · day 0.';

        T.after(() => stage.classList.add('on'), 60);
        T.after(() => { fill.style.inset = '0 0 0 0'; cargo.style.left = '100%'; }, 320);
        T.after(() => counterStop = animateCounter(day, 12, 2600), 340);

        T.after(() => { stops[1].classList.add('reached'); labels[1].classList.add('reached'); now.textContent = 'Loaded · Bremerhaven, day 3.'; }, 1200);
        T.after(() => { now.textContent = 'In transit · Atlantic, day 6 of 12.'; }, 1900);
        T.after(() => { stops[2].classList.add('reached'); labels[2].classList.add('reached'); now.textContent = 'Cleared customs · Brooklyn, day 10.'; }, 2600);
        T.after(() => { stops[3].classList.add('reached'); labels[3].classList.add('reached'); now.textContent = 'Delivered · Greenpoint, day 12.'; }, 3200);

        T.after(loop, 6400);
      }
      loop();

      return () => { T.clear(); counterStop && counterStop(); };
    },
  };

  // ──────────────────────────── 5. INSIGHTS ────────────────────────────
  const insights = {
    html: `
      <div class="viz-stage vz-insights">
        <div class="vz-head">
          <div>
            <div class="vz-title">Monday pulse &middot; week 6</div>
            <div class="vz-sub">Reads everything for you. Tells you what to do next.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>

        <div class="in-findings">
          <div class="in-finding" data-i="0" data-text="The 188mm drum sells. The 220mm sits." data-metric="68" data-unit="%" data-spark="M0 22 L8 20 L16 18 L24 12 L32 14 L40 8 L48 6 L56 4 L64 2 L72 1"></div>
          <div class="in-finding" data-i="1" data-text="Linen cord is moving faster than brass cord. A lot faster." data-metric="3.2" data-unit="×" data-spark="M0 24 L10 22 L20 16 L30 14 L40 10 L50 8 L60 5 L72 2"></div>
          <div class="in-finding" data-i="2" data-text="One reorder for every 4.1 sales. Word's getting out." data-metric="24" data-unit="%" data-spark="M0 20 L12 18 L24 14 L36 12 L48 9 L60 6 L72 3"></div>
        </div>

        <div class="vz-foot">
          <span><em>Cut the 220mm.</em> Run more 188s in linen. Brace for the reorder spike in 9 days.</span>
          <span class="vz-meta">step / insights</span>
        </div>
      </div>
    `,
    start(root) {
      const stage    = root.querySelector('.viz-stage');
      const findings = Array.from(root.querySelectorAll('.in-finding'));
      const T = timerSet();
      const counterStops = [];

      function buildFinding(el) {
        el.innerHTML = `
          <div class="in-text"><span class="in-q">Q: what's working?</span> <span class="in-typed"></span><span class="in-caret"></span></div>
          <div class="in-spark">
            <svg viewBox="0 0 72 28" preserveAspectRatio="none">
              <path d="${el.dataset.spark}"></path>
            </svg>
          </div>
          <div class="in-metric"><span class="in-n">0</span><span class="unit">${el.dataset.unit}</span></div>
        `;
      }
      findings.forEach(buildFinding);

      function typeInto(el, text, perChar) {
        const target = el.querySelector('.in-typed');
        return new Promise(resolve => {
          let i = 0;
          function step() {
            if (i > text.length) { el.classList.add('typed'); return resolve(); }
            target.textContent = text.slice(0, i);
            i++;
            T.after(step, perChar);
          }
          step();
        });
      }

      function loop() {
        // Reset
        stage.classList.remove('on');
        findings.forEach(f => {
          f.classList.remove('in', 'typed', 'drawn', 'lit', 'metered');
          f.querySelector('.in-typed').textContent = '';
          f.querySelector('.in-n').textContent = '0';
        });

        T.after(() => stage.classList.add('on'), 60);

        let cursor = 240;
        findings.forEach((f, i) => {
          T.after(() => f.classList.add('in'), cursor);
          const txt = f.dataset.text;
          T.after(() => typeInto(f, txt, 28), cursor + 120);
          const typedAt = cursor + 120 + txt.length * 28 + 60;
          T.after(() => f.classList.add('drawn'), typedAt);
          T.after(() => f.classList.add('lit'), typedAt + 100);
          const target = parseFloat(f.dataset.metric);
          T.after(() => {
            f.classList.add('metered');
            const nEl = f.querySelector('.in-n');
            if (Number.isInteger(target)) {
              counterStops.push(animateCounter(nEl, target, 1100));
            } else {
              // Smooth float counter for 3.2× style
              const start = performance.now();
              const dur = 1100;
              let raf;
              const tick = (now) => {
                const t = Math.min(1, (now - start) / dur);
                nEl.textContent = (target * ease(t)).toFixed(1);
                if (t < 1) raf = requestAnimationFrame(tick);
              };
              raf = requestAnimationFrame(tick);
              counterStops.push(() => raf && cancelAnimationFrame(raf));
            }
          }, typedAt + 180);
          cursor = typedAt + 700;
        });

        T.after(loop, Math.max(cursor + 1200, 6500));
      }
      loop();

      return () => { T.clear(); counterStops.forEach(s => s && s()); };
    },
  };

  // ──────────────────────── 3p. QUALITY (PERSONAL) ────────────────────────
  // One piece. Hands on. Eyes on. Twelve checks, signed off, wrapped.
  const quality_personal = {
    html: `
      <div class="viz-stage vz-quality-personal">
        <div class="vz-head">
          <div>
            <div class="vz-title">Final inspection &middot; your piece</div>
            <div class="vz-sub">A pair of hands, a raking light, the spec on the bench.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>

        <div class="qp-body">
          <div class="qp-piece" aria-hidden="true">
            <svg viewBox="0 0 220 260" preserveAspectRatio="xMidYMid meet" fill="none"
                 stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
              <!-- ceiling + canopy -->
              <line x1="40" y1="22" x2="180" y2="22" stroke="rgba(243,232,213,0.35)"/>
              <ellipse cx="110" cy="22" rx="14" ry="2.6" stroke="rgba(243,232,213,0.80)"/>
              <!-- cord -->
              <path d="M110 26 C110 60, 108 100, 110 140" stroke="rgba(243,232,213,0.80)" stroke-width="1.05"/>
              <!-- shade -->
              <ellipse cx="110" cy="146" rx="14" ry="3" stroke="rgba(243,232,213,0.85)"/>
              <path d="M96 146 C 84 178, 74 208, 70 232" stroke="rgba(243,232,213,0.90)"/>
              <path d="M124 146 C 136 178, 146 208, 150 232" stroke="rgba(243,232,213,0.90)"/>
              <ellipse cx="110" cy="232" rx="42" ry="7" stroke="rgba(243,232,213,0.90)"/>
              <!-- callouts (animated on each check) -->
              <g class="qp-callouts">
                <g class="qp-call" data-i="0">
                  <circle cx="156" cy="146" r="3"/>
                  <line x1="159" y1="146" x2="184" y2="146"/>
                  <text x="187" y="149" font-family="Inter, sans-serif" font-size="13" fill="currentColor">rim true</text>
                </g>
                <g class="qp-call" data-i="1">
                  <circle cx="110" cy="100" r="3"/>
                  <line x1="113" y1="100" x2="184" y2="100"/>
                  <text x="187" y="103" font-family="Inter, sans-serif" font-size="13" fill="currentColor">cord tension</text>
                </g>
                <g class="qp-call" data-i="2">
                  <circle cx="70" cy="200" r="3"/>
                  <line x1="67" y1="200" x2="36" y2="200"/>
                  <text x="34" y="203" text-anchor="end" font-family="Inter, sans-serif" font-size="13" fill="currentColor">glaze even</text>
                </g>
                <g class="qp-call" data-i="3">
                  <circle cx="110" cy="232" r="3"/>
                  <line x1="113" y1="232" x2="184" y2="232"/>
                  <text x="187" y="235" font-family="Inter, sans-serif" font-size="13" fill="currentColor">⌀ 136 mm</text>
                </g>
              </g>
            </svg>
          </div>

          <div class="qp-checks">
            <div class="qp-check" data-i="0">
              <span class="qp-bul"></span>
              <span class="qp-text"><strong>Veneer grain.</strong> Reads correct from across the room.</span>
            </div>
            <div class="qp-check" data-i="1">
              <span class="qp-bul"></span>
              <span class="qp-text"><strong>Rim true.</strong> 0.3mm out of round, well inside tolerance.</span>
            </div>
            <div class="qp-check" data-i="2">
              <span class="qp-bul"></span>
              <span class="qp-text"><strong>Cord tension.</strong> Tested at 1.5×rated load. Holds.</span>
            </div>
            <div class="qp-check" data-i="3">
              <span class="qp-bul"></span>
              <span class="qp-text"><strong>Glaze even.</strong> No fish-eye, no crawl, no pinholes.</span>
            </div>
            <div class="qp-check" data-i="4">
              <span class="qp-bul"></span>
              <span class="qp-text"><strong>Bulb fit.</strong> Threads clean, sits flush, switch travels.</span>
            </div>
            <div class="qp-check qp-sign" data-i="5">
              <span class="qp-bul"></span>
              <span class="qp-text">
                <strong>Signed off</strong> &middot; <em>Helga R., Müller-Werke, May 14</em>.
              </span>
            </div>
          </div>
        </div>

        <div class="vz-foot">
          <span><em>Twelve checks, one piece.</em> Wrapped in kraft, packed in cardboard. No foam, no plastic.</span>
          <span class="vz-meta">step / quality</span>
        </div>
      </div>
    `,
    start(root) {
      const stage  = root.querySelector('.viz-stage');
      const checks = Array.from(root.querySelectorAll('.qp-check'));
      const calls  = Array.from(root.querySelectorAll('.qp-call'));
      const T = timerSet();

      function loop() {
        stage.classList.remove('on');
        checks.forEach(c => c.classList.remove('done'));
        calls.forEach(c => c.classList.remove('lit'));

        T.after(() => stage.classList.add('on'), 60);
        checks.forEach((c, i) => {
          T.after(() => {
            c.classList.add('done');
            const j = parseInt(c.dataset.i, 10);
            if (calls[j]) calls[j].classList.add('lit');
          }, 320 + i * 620);
        });
        T.after(loop, 320 + checks.length * 620 + 1400);
      }
      loop();

      return () => T.clear();
    },
  };

  // ──────────────────────── 4p. FULFILLMENT (PERSONAL) ────────────────────────
  // One parcel, a hand at each end.
  const fulfillment_personal = {
    html: `
      <div class="viz-stage vz-fulfillment vz-fulfillment-personal">
        <div class="vz-head">
          <div>
            <div class="vz-title">One parcel &middot; Bavaria &rsaquo; your door</div>
            <div class="vz-sub">Hand-carried at both ends. Tracking from the workshop bench.</div>
          </div>
          <div class="vz-meta"><span class="now-dot"></span>Live</div>
        </div>

        <div class="fu-rail-wrap">
          <div class="fu-rail">
            <div class="fu-fill"></div>
            <div class="fu-cargo fu-cargo--parcel"></div>
            <div class="fu-stop" style="left:  0%"></div>
            <div class="fu-stop-label reached" style="left:  0%">Workshop</div>
            <div class="fu-stop-name"           style="left:  0%">Müller-Werke</div>
            <div class="fu-stop" style="left: 50%"></div>
            <div class="fu-stop-label" style="left: 50%">Courier</div>
            <div class="fu-stop-name"  style="left: 50%">DHL Express</div>
            <div class="fu-stop" style="left:100%"></div>
            <div class="fu-stop-label" style="left:100%">Doorstep</div>
            <div class="fu-stop-name"  style="left:100%">You</div>
          </div>
        </div>

        <div class="fu-meta-row">
          <div>
            <div class="fu-eta"><span class="fu-day" data-target="6">0</span><i>days</i></div>
            <div class="fu-eta-label">workshop to hallway, signed delivery.</div>
          </div>
          <div class="fu-side">
            <div class="lbl">Now</div>
            <div class="fu-now">Wrapping in kraft &middot; workshop, day 0.</div>
          </div>
        </div>

        <div class="vz-foot">
          <span><em>One box.</em> Insured, signed-for, climate-controlled in transit.</span>
          <span class="vz-meta">step / fulfillment</span>
        </div>
      </div>
    `,
    start(root) {
      const stage = root.querySelector('.viz-stage');
      const fill  = root.querySelector('.fu-fill');
      const cargo = root.querySelector('.fu-cargo');
      const day   = root.querySelector('.fu-day');
      const now   = root.querySelector('.fu-now');
      const stops = Array.from(root.querySelectorAll('.fu-stop'));
      const labels = Array.from(root.querySelectorAll('.fu-stop-label'));
      const T = timerSet();
      let counterStop = null;

      function loop() {
        stage.classList.remove('on');
        stops.forEach((s, i) => s.classList.toggle('reached', i === 0));
        labels.forEach((l, i) => l.classList.toggle('reached', i === 0));
        fill.style.inset = '0 100% 0 0';
        cargo.style.left = '0%';
        day.textContent = '0';
        now.textContent = 'Wrapping in kraft \u00b7 workshop, day 0.';

        T.after(() => stage.classList.add('on'), 60);
        T.after(() => { fill.style.inset = '0 0 0 0'; cargo.style.left = '100%'; }, 320);
        T.after(() => counterStop = animateCounter(day, 6, 2600), 340);

        T.after(() => { stops[1].classList.add('reached'); labels[1].classList.add('reached'); now.textContent = 'Picked up \u00b7 day 1.'; }, 1100);
        T.after(() => { now.textContent = 'Customs cleared \u00b7 day 4.'; }, 2000);
        T.after(() => { stops[2].classList.add('reached'); labels[2].classList.add('reached'); now.textContent = 'Delivered \u00b7 day 6.'; }, 2800);

        T.after(loop, 6200);
      }
      loop();

      return () => { T.clear(); counterStop && counterStop(); };
    },
  };

  // ─── Registry ──────────────────────────────────────────────────────
  window.AriadneVizes = { sourcing, manufacturing, quality, fulfillment, insights, quality_personal, fulfillment_personal };
})();
