(function () {
  const W = 420, H = 720;
  const ROAD_L = 60, ROAD_R = 360;
  const lanes = [110, 210, 310];
  const PLAYER_Y = 560;
  const INK = '#160a2b';
  const BOOST_FRAMES = 240;
  const CAR_COLORS = ['#ff2fa8', '#a55bff', '#ff7a2f', '#1fd7a0', '#ffd23f'];
  const SHIRTS = ['#ff3d5a', '#27e6ff', '#ffd23f', '#a55bff', '#1fd7a0', '#ff7a2f'];
  const SKINS = ['#ffd9b3', '#e8b07a', '#b97a4b', '#7a4a2b', '#ffe6cc'];
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');
  const wrap = document.getElementById('wrap');
  const el = {
    score: document.getElementById('score'), best: document.getElementById('best'),
    kmh: document.getElementById('kmh'), speedfill: document.getElementById('speedfill'),
    boostfill: document.getElementById('boostfill'),
    start: document.getElementById('startScreen'), over: document.getElementById('overScreen'),
    finalScore: document.getElementById('finalScore'), finalNote: document.getElementById('finalNote'),
  };

  // ---- sizing ---------------------------------------------------------
  let k = 1;
  function resize() {
    const s = Math.min(window.innerWidth / W, (window.innerHeight - 8) / H);
    wrap.style.width = Math.floor(W * s) + 'px';
    wrap.style.height = Math.floor(H * s) + 'px';
    wrap.style.fontSize = (16 * s) + 'px';
    k = Math.min(Math.max(s * (window.devicePixelRatio || 1), 1), 3);
    canvas.width = Math.round(W * k); canvas.height = Math.round(H * k);
  }
  window.addEventListener('resize', resize);
  resize();

  let best = 0;
  try { best = parseInt(localStorage.getItem('neonracer-best') || '0', 10) || 0; } catch (e) {}
  el.best.textContent = best.toLocaleString();

  // ---- state (mirrors the Python variables) ---------------------------
  let lane, score, speed, boost, baseSpeed, boostTimer, frames;
  let traffic, pads, particles, fx, banners, spawnDist, padDist;
  let shake, flash, zoom, hitStop, combo, comboTimer, comboPulse, tick = 0, introT = 0;
  let dashOffset = 0, barOff = 0, crowdScroll = 0;
  let state = 'ready';
  const player = { x: lanes[1], w: 40, h: 76, tilt: 0, sq: 0, pop: 0 };

  function reset() {
    lane = 1; score = 0; speed = 6; boost = false; baseSpeed = 6; boostTimer = 0; frames = 0;
    traffic = []; pads = []; particles = []; fx = []; banners = [];
    spawnDist = 220; padDist = 900;
    shake = 0; flash = 0; zoom = 0; hitStop = 0; combo = 0; comboTimer = 0; comboPulse = 0; introT = 0;
    player.x = lanes[1]; player.tilt = 0; player.sq = 0; player.pop = 0;
  }
  reset();

  // ---- helpers ----------------------------------------------------------
  const rand = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function hash(n) { n = (n * 374761393) | 0; n = ((n ^ (n >>> 13)) * 1274126177) | 0; return (n ^ (n >>> 16)) >>> 0; }
  function shade(hex, amt) {
    const n = parseInt(hex.slice(1), 16);
    let r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    const t = amt < 0 ? 0 : 255, p = Math.abs(amt);
    r = Math.round((t - r) * p + r); g = Math.round((t - g) * p + g); b = Math.round((t - b) * p + b);
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }
  function overlaps(a, b, pad) {
    pad = pad || 0;
    return Math.abs(a.x - b.x) < (a.w + b.w) / 2 - pad && Math.abs(a.y - b.y) < (a.h + b.h) / 2 - pad;
  }
  function rr(x, y, w, h, r) { ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, w, h, r); else ctx.rect(x, y, w, h); }
  function fillStroke(fill, lw) { ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = lw; ctx.strokeStyle = INK; ctx.stroke(); }
  function outlined(text, x, y, size, fill, align) {
    ctx.font = 'italic 900 ' + size + 'px Impact, "Arial Black", sans-serif';
    ctx.textAlign = align || 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
    ctx.lineWidth = size * 0.24; ctx.strokeStyle = INK; ctx.strokeText(text, x, y);
    ctx.fillStyle = fill; ctx.fillText(text, x, y);
  }

  function addBanner(text, c1, c2, size) { banners.push({ text, c1, c2, size: size || 76, life: 70, max: 70 }); }
  function addPow(x, y, text, color) { fx.push({ kind: 'pow', x, y, text, color, life: 34, max: 34, rot: rand(-0.3, 0.3) }); }
  function addFloat(x, y, text, color) { fx.push({ kind: 'float', x, y, text, color, life: 44, max: 44 }); }
  function burst(x, y, n, colors, power, stars) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, s = rand(1.5, power);
      particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: rand(18, 44), max: 44,
                       c: colors[(Math.random() * colors.length) | 0], star: stars && Math.random() < 0.5, r: rand(2, 4.5) });
    }
  }

  // ---- input ------------------------------------------------------------
  function moveLane(d) {
    if (state !== 'play' && state !== 'intro') return;
    const old = lane;
    if (d < 0 && lane > 0) lane -= 1;
    if (d > 0 && lane < 2) lane += 1;
    if (lane !== old && state === 'play') {
      // dodge: a car in the lane you just left was about to hit you
      for (const car of traffic) {
        if (car.lane === old && !car.dodged && car.y > PLAYER_Y - 210 && car.y < PLAYER_Y + 10) {
          car.dodged = true; registerDodge(car);
        }
      }
    }
  }
  function registerDodge(car) {
    combo++; comboTimer = 150; comboPulse = 1;
    const pts = 50 * combo;
    score += pts;
    addPow(car.x, car.y - 20, combo >= 4 ? 'INSANE!' : combo >= 2 ? 'NICE!' : 'DODGE!', combo >= 4 ? '#ff3d5a' : '#27e6ff');
    addFloat(car.x, car.y - 60, '+' + pts, '#ffd23f');
    hitStop = 3; zoom = Math.max(zoom, 0.025);
  }
  window.addEventListener('keydown', function (e) {
    if (e.repeat) return;
    if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') { moveLane(-1); e.preventDefault(); }
    else if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') { moveLane(1); e.preventDefault(); }
    else if ((e.key === 'Enter' || e.key === ' ') && (state === 'ready' || state === 'over')) {
      if (document.activeElement && document.activeElement.tagName === 'BUTTON') return;
      e.preventDefault(); begin();
    }
  });
  function tap(e) {
    const r = e.currentTarget.getBoundingClientRect();
    moveLane(e.clientX < r.left + r.width / 2 ? -1 : 1);
  }
  document.getElementById('touch').addEventListener('pointerdown', tap);
  canvas.addEventListener('pointerdown', tap);
  document.getElementById('startBtn').addEventListener('click', begin);
  document.getElementById('retryBtn').addEventListener('click', begin);

  function begin() {
    reset();
    el.start.classList.add('hidden'); el.over.classList.add('hidden');
    state = 'intro';
  }

  // ---- spawning ---------------------------------------------------------
  function spawnTraffic() {
    const two = Math.random() < (boost ? 0.4 : 0.22);
    const order = [0, 1, 2].sort(() => Math.random() - 0.5);
    for (let i = 0; i < (two ? 2 : 1); i++) {
      traffic.push({ lane: order[i], x: lanes[order[i]], y: -60 - i * 6, w: 42, h: 78,
                     c: CAR_COLORS[(Math.random() * CAR_COLORS.length) | 0], dodged: false });
    }
  }
  function spawnPad() {
    const l = (Math.random() * 3) | 0;
    if (traffic.some(t => t.lane === l && t.y < 160)) return;
    pads.push({ x: lanes[l], y: -50, w: 60, h: 46 });
  }

  // ---- update -----------------------------------------------------------
  function easePlayer() {
    const before = player.x;
    player.x += (lanes[lane] - player.x) * 0.32;         // player.x = lanes[lane], eased
    const vx = player.x - before;
    player.tilt += (vx * 0.06 - player.tilt) * 0.3;
    player.sq += (Math.min(Math.abs(vx) * 0.03, 0.25) - player.sq) * 0.4;
  }
  function scenery(sp) {
    dashOffset = (dashOffset + sp) % 80;
    barOff = (barOff + sp) % 60;
    crowdScroll += sp;
  }
  function effectsTick() {
    if (flash > 0) flash -= 0.06;
    shake *= 0.86; zoom *= 0.85; player.pop *= 0.86; comboPulse *= 0.88;
    for (const p of particles) { p.x += p.vx; p.y += p.vy; p.vy += p.star ? 0.12 : 0; p.life--; }
    particles = particles.filter(p => p.life > 0);
    for (const f of fx) { f.life--; if (f.kind === 'float') f.y -= 1.1; }
    fx = fx.filter(f => f.life > 0);
    for (const b of banners) b.life--;
    banners = banners.filter(b => b.life > 0);
  }

  function step() {
    effectsTick();

    if (state === 'intro') {
      introT++; easePlayer(); scenery(6);
      if (introT === 2) addBanner('READY?', '#fff08a', '#ffd23f');
      if (introT === 58) { addBanner('GO!!', '#fff08a', '#ff5a1f', 96); state = 'play'; flash = 0.6; zoom = 0.05; }
      return;
    }
    if (state !== 'play') return;

    frames++;
    baseSpeed = Math.min(8, 6 + Math.floor(frames / 600) * 0.25);
    easePlayer();

    if (boost) { boostTimer--; if (boostTimer <= 0) boost = false; }
    else speed += (baseSpeed - speed) * 0.05;

    for (const car of traffic) car.y += speed;               // car.y += speed
    for (const p of pads) p.y += speed;
    traffic = traffic.filter(c => c.y < H + 100);
    pads = pads.filter(p => p.y < H + 100);

    spawnDist -= speed;
    if (spawnDist <= 0) { spawnTraffic(); spawnDist = boost ? rand(105, 175) : rand(170, 270); }
    padDist -= speed;
    if (padDist <= 0) { spawnPad(); padDist = rand(1300, 2200); }

    const pr = { x: player.x, y: PLAYER_Y, w: player.w, h: player.h };
    for (let i = pads.length - 1; i >= 0; i--) {              // player.colliderect(boost_pad)
      if (overlaps(pr, pads[i])) {
        boost = true; boostTimer = BOOST_FRAMES; speed = baseSpeed + 3;
        flash = 1; shake = 9; zoom = 0.07; hitStop = 5; player.pop = 0.35;
        addBanner('BOOST!!', '#fff08a', '#ff5a1f', 84);
        addPow(pads[i].x, PLAYER_Y - 70, 'WHOOSH!', '#ffd23f');
        burst(pads[i].x, PLAYER_Y, 26, ['#ffd23f', '#ff7a1a', '#ffffff'], 7, true);
        pads.splice(i, 1);
      }
    }
    for (const car of traffic) { if (overlaps(pr, car, 6)) { crash(car); return; } }

    score += Math.floor(speed);                               // score += int(speed)
    scenery(speed);
    if (comboTimer > 0) { comboTimer--; if (comboTimer === 0) combo = 0; }
    if (boost && frames % 2 === 0) {
      particles.push({ x: player.x + rand(-12, 12), y: PLAYER_Y + 44, vx: rand(-0.5, 0.5), vy: rand(2, 5),
                       life: 20, max: 44, c: Math.random() < 0.5 ? '#ffd23f' : '#ff5a1f', star: false, r: rand(2, 4) });
    }
    if (boost) shake = Math.max(shake, 1.8);
  }

  function crash(car) {
    state = 'over';
    hitStop = 16; shake = 16; flash = 1; zoom = 0.12;
    addPow(car.x, (car.y + PLAYER_Y) / 2, 'CRASH!', '#ff3d5a');
    burst(player.x, PLAYER_Y - 10, 70, ['#ff2fa8', '#ffd23f', '#ffffff', '#27e6ff'], 10, true);
    banners = [];
    addBanner('K.O.!!', '#ff9a9a', '#ff3d5a', 110); banners[banners.length - 1].life = banners[banners.length - 1].max = 150;
    let newBest = false;
    if (score > best) { best = score; newBest = true; try { localStorage.setItem('neonracer-best', String(best)); } catch (e) {} }
    el.best.textContent = best.toLocaleString();
    el.finalScore.textContent = score.toLocaleString();
    el.finalNote.textContent = (newBest ? 'New personal best! ' : 'Best: ' + best.toLocaleString() + '. ') +
      (combo > 1 ? 'Last combo: ' + combo + ' hits.' : 'Go again?');
    setTimeout(function () { if (state === 'over') el.over.classList.remove('hidden'); }, 1100);
  }

  // ---- drawing: pieces --------------------------------------------------
  function drawFlame(x, y, len, w) {
    const f = len * (0.85 + Math.random() * 0.3);
    ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(x - w, y); ctx.quadraticCurveTo(x - w * 1.3, y + f * 0.5, x, y + f);
    ctx.quadraticCurveTo(x + w * 1.3, y + f * 0.5, x + w, y); ctx.closePath(); fillStroke('#ff7a1a', 3);
    ctx.beginPath(); ctx.moveTo(x - w * 0.5, y); ctx.quadraticCurveTo(x - w * 0.6, y + f * 0.3, x, y + f * 0.6);
    ctx.quadraticCurveTo(x + w * 0.6, y + f * 0.3, x + w * 0.5, y); ctx.closePath(); ctx.fillStyle = '#ffe14a'; ctx.fill();
  }

  function drawCar(o) {
    const w = o.w, h = o.h;
    ctx.save();
    ctx.translate(o.x, o.y); ctx.rotate(o.tilt || 0); ctx.scale(o.sx || 1, o.sy || 1);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    if (o.flame > 0) { drawFlame(-10, h / 2 - 2, o.flame, 6); drawFlame(10, h / 2 - 2, o.flame, 6); }
    // wheels
    for (const [sx, wy] of [[-1, -h * 0.27], [1, -h * 0.27], [-1, h * 0.26], [1, h * 0.26]]) {
      rr(sx * (w / 2 + 1) - 4.5, wy - 10, 9, 20, 3); fillStroke('#2a1a44', 3);
    }
    // body with cel shading
    rr(-w / 2, -h / 2, w, h, 12); ctx.fillStyle = o.color; ctx.fill();
    ctx.save(); ctx.clip();
    ctx.fillStyle = shade(o.color, -0.32); ctx.fillRect(w * 0.14, -h / 2, w, h);
    ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.fillRect(-w / 2 + 5, -h / 2 + 22, 4, h * 0.5);
    if (o.player) { ctx.fillStyle = '#fff4d6'; ctx.fillRect(-7, -h / 2, 5, h); ctx.fillRect(2, -h / 2, 5, h); }
    ctx.restore();
    rr(-w / 2, -h / 2, w, h, 12); ctx.lineWidth = 4; ctx.strokeStyle = INK; ctx.stroke();
    // windshield + rear glass
    rr(-w * 0.34, -h * 0.03, w * 0.68, h * 0.2, 6); fillStroke('#bff3ff', 3);
    ctx.fillStyle = 'rgba(255,255,255,0.75)';
    ctx.beginPath(); ctx.moveTo(-w * 0.26, h * 0.15); ctx.lineTo(-w * 0.12, h * 0.15); ctx.lineTo(w * 0.02, -h * 0.01); ctx.lineTo(-w * 0.12, -h * 0.01); ctx.closePath(); ctx.fill();
    rr(-w * 0.28, h * 0.24, w * 0.56, h * 0.09, 4); fillStroke('#79c8e6', 2.5);
    // taillights
    ctx.fillStyle = '#ff3355';
    ctx.fillRect(-w / 2 + 4, h / 2 - 7, 10, 4); ctx.fillRect(w / 2 - 14, h / 2 - 7, 10, 4);
    // spoiler on the hero
    if (o.player) { rr(-w * 0.46, h / 2 - 2, w * 0.92, 7, 3); fillStroke(shade(o.color, -0.25), 3); }
    // cartoon eyes on the hood
    const ey = -h / 2 + 15;
    for (const s of [-1, 1]) {
      ctx.beginPath(); ctx.arc(s * 9, ey, 7.5, 0, Math.PI * 2); fillStroke('#ffffff', 2.5);
      ctx.beginPath(); ctx.arc(s * 9 + (o.look || 0) * 2.6, ey + (o.player ? -1.5 : 2), o.pupil || 3.4, 0, Math.PI * 2);
      ctx.fillStyle = INK; ctx.fill();
      ctx.beginPath(); ctx.lineWidth = 3; ctx.strokeStyle = INK;
      if (o.player) { ctx.moveTo(s * 16, ey - 12); ctx.lineTo(s * 3, ey - 7); }        // angry brows
      else { ctx.moveTo(s * 16, ey - 8); ctx.lineTo(s * 3, ey - 13); }                  // worried brows
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawPad(p) {
    const pulse = 1 + Math.sin(tick * 0.2) * 0.06;
    ctx.save(); ctx.translate(p.x, p.y); ctx.scale(pulse, pulse); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    rr(-p.w / 2, -p.h / 2, p.w, p.h, 9); fillStroke('#ffd23f', 4);
    for (let i = 0; i < 2; i++) {
      const o = i * 15 - 7;
      ctx.beginPath(); ctx.moveTo(-14, 9 + o); ctx.lineTo(0, -5 + o); ctx.lineTo(14, 9 + o);
      ctx.lineWidth = 9; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 4.5; ctx.strokeStyle = '#ff5a1f'; ctx.stroke();
    }
    ctx.restore();
    // twinkles
    for (let i = 0; i < 3; i++) {
      const a = tick * 0.08 + i * 2.1, sx = p.x + Math.cos(a) * 38, sy = p.y + Math.sin(a) * 28;
      star(sx, sy, 6, 4, '#ffffff', a, 2);
    }
  }

  function star(x, y, r, n, fill, rot, lw) {
    ctx.beginPath();
    for (let i = 0; i < n * 2; i++) {
      const rad = i % 2 ? r * 0.42 : r, a = rot + i * Math.PI / n;
      ctx.lineTo(x + Math.cos(a) * rad, y + Math.sin(a) * rad);
    }
    ctx.closePath(); ctx.lineJoin = 'round'; fillStroke(fill, lw);
  }

  function drawCrowd() {
    const rowH = 38, base = Math.floor(crowdScroll / rowH), frac = crowdScroll % rowH;
    const cheer = boost ? 1 : 0;
    for (let side = 0; side < 2; side++) {
      for (let j = 0; j < 22; j++) {
        const idx = j - base, hsh = hash(idx * 2 + side);
        const x = side === 0 ? 20 + (hsh % 3) * 8 : 400 - (hsh % 3) * 8;
        const y = j * rowH + frac - 60 + Math.sin(tick * 0.28 + hsh % 7) * (cheer ? 5 : 1.6);
        const shirt = SHIRTS[hsh % SHIRTS.length], skin = SKINS[(hsh >> 3) % SKINS.length];
        const armY = cheer ? -14 + Math.sin(tick * 0.5 + j) * 4 : 9;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        for (const s of [-1, 1]) {
          ctx.beginPath(); ctx.moveTo(x + s * 8, y + 4); ctx.lineTo(x + s * 15, y + armY);
          ctx.lineWidth = 7; ctx.strokeStyle = INK; ctx.stroke();
          ctx.lineWidth = 3.4; ctx.strokeStyle = skin; ctx.stroke();
        }
        rr(x - 9, y, 18, 17, 5); fillStroke(shirt, 2.5);
        ctx.beginPath(); ctx.arc(x, y - 8, 9, 0, Math.PI * 2); fillStroke(skin, 2.5);
        ctx.fillStyle = INK;
        ctx.beginPath(); ctx.arc(x - 3.4, y - 9, 1.5, 0, 6.3); ctx.arc(x + 3.4, y - 9, 1.5, 0, 6.3); ctx.fill();
        if (cheer) { ctx.beginPath(); ctx.ellipse(x, y - 3.5, 3, 2.5, 0, 0, Math.PI * 2); ctx.fill(); }
        else { ctx.fillRect(x - 2.5, y - 4, 5, 1.6); }
      }
    }
  }

  function drawScene() {
    // backdrop
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, boost ? '#3a0a3f' : '#1b0b3a'); g.addColorStop(1, boost ? '#5a1238' : '#2a0f4f');
    ctx.fillStyle = g; ctx.fillRect(-30, -30, W + 60, H + 60);
    // halftone dots
    ctx.fillStyle = 'rgba(255,47,168,0.28)';
    const off = crowdScroll % 16;
    for (let y = -16; y < H + 16; y += 16) {
      const r = 0.8 + (y / H) * 2.6;
      for (let x = 0; x < W + 16; x += 16) {
        ctx.beginPath(); ctx.arc(x + ((y / 16) % 2 ? 8 : 0), y + off, r, 0, 6.3); ctx.fill();
      }
    }
    drawCrowd();

    // barriers
    for (let i = -2; i < H / 30 + 2; i++) {
      const y = i * 30 + barOff;
      for (const bx of [44, 360]) {
        rr(bx, y, 16, 30, 3); fillStroke(i % 2 ? '#fff4d6' : '#ff3d5a', 3);
      }
    }
    // road
    ctx.fillStyle = boost ? '#5a2f6e' : '#3a2f6e'; ctx.fillRect(ROAD_L, -30, ROAD_R - ROAD_L, H + 60);
    ctx.fillStyle = 'rgba(255,255,255,0.05)';
    ctx.fillRect(160, -30, 100, H + 60);
    // edge stripes
    ctx.lineCap = 'butt';
    for (const x of [ROAD_L + 8, ROAD_R - 8]) {
      ctx.beginPath(); ctx.moveTo(x, -30); ctx.lineTo(x, H + 30);
      ctx.lineWidth = 9; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 4; ctx.strokeStyle = '#ffd23f'; ctx.stroke();
    }
    // lane dashes
    ctx.setLineDash([36, 44]); ctx.lineDashOffset = -dashOffset;
    for (const x of [160, 260]) {
      ctx.beginPath(); ctx.moveTo(x, -90); ctx.lineTo(x, H + 90);
      ctx.lineWidth = 10; ctx.strokeStyle = INK; ctx.stroke();
      ctx.lineWidth = 5; ctx.strokeStyle = '#fff4d6'; ctx.stroke();
    }
    ctx.setLineDash([]);

    // boost: radial speed rays + streaks
    if (boost) {
      ctx.save(); ctx.translate(W / 2, 260); ctx.rotate(tick * 0.012);
      ctx.fillStyle = 'rgba(255,220,90,0.17)';
      for (let i = 0; i < 16; i++) {
        const a = i * Math.PI / 8;
        ctx.beginPath(); ctx.moveTo(0, 0);
        ctx.lineTo(Math.cos(a - 0.11) * 900, Math.sin(a - 0.11) * 900);
        ctx.lineTo(Math.cos(a + 0.11) * 900, Math.sin(a + 0.11) * 900); ctx.fill();
      }
      ctx.restore();
      ctx.strokeStyle = 'rgba(255,244,214,0.55)'; ctx.lineWidth = 3; ctx.lineCap = 'round';
      for (let i = 0; i < 14; i++) {
        const x = ROAD_L + 14 + ((i * 53 + 17) % (ROAD_R - ROAD_L - 28));
        const y = ((i * 97 + tick * (16 + (i % 4) * 5)) % (H + 220)) - 110;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + 80 + (i % 3) * 34); ctx.stroke();
      }
    }

    for (const p of pads) drawPad(p);

    // traffic
    for (const c of traffic) {
      const near = clamp(1 - Math.abs(PLAYER_Y - c.y) / 300, 0, 1);
      drawCar({ x: c.x, y: c.y, w: c.w, h: c.h, color: c.c, look: clamp((player.x - c.x) / 110, -1, 1), pupil: 3.6 - near * 1.7 });
    }
    // player + afterimages
    if (state !== 'over') {
      const sq = player.sq, pop = player.pop + (boost ? 0.07 : 0);
      const base = { x: player.x, w: player.w, h: player.h, color: '#2f8bff', player: true, tilt: player.tilt,
                     sx: 1 - sq * 0.8 - pop * 0.45, sy: 1 + sq + pop, look: clamp((lanes[lane] - player.x) / 40, -1, 1) };
      if (boost) {
        ctx.globalAlpha = 0.16; drawCar(Object.assign({}, base, { y: PLAYER_Y + 58, color: '#ffd23f' }));
        ctx.globalAlpha = 0.28; drawCar(Object.assign({}, base, { y: PLAYER_Y + 30, color: '#ff8a3f' }));
        ctx.globalAlpha = 1;
      }
      drawCar(Object.assign({}, base, { y: PLAYER_Y, flame: boost ? 46 : 0 }));
    }

    // particles
    for (const p of particles) {
      ctx.globalAlpha = clamp(p.life / 18, 0, 1);
      if (p.star) star(p.x, p.y, p.r * 2.2, 4, p.c, p.life * 0.2, 2);
      else { ctx.fillStyle = p.c; ctx.fillRect(p.x - p.r / 2, p.y - p.r / 2, p.r, p.r); }
    }
    ctx.globalAlpha = 1;

    // comic impact bursts and floating numbers
    for (const f of fx) {
      const t = 1 - f.life / f.max;
      if (f.kind === 'pow') {
        const sc = t < 0.2 ? 0.4 + (t / 0.2) * 0.9 : 1.3 - (t - 0.2) * 0.25;
        ctx.globalAlpha = f.life < 8 ? f.life / 8 : 1;
        ctx.save(); ctx.translate(f.x, f.y); ctx.rotate(f.rot); ctx.scale(sc, sc);
        star(0, 0, 54, 9, f.color, 0, 4);
        star(0, 0, 34, 9, '#fff4d6', 0.2, 0);
        outlined(f.text, 0, 0, 22, f.color);
        ctx.restore(); ctx.globalAlpha = 1;
      } else {
        ctx.globalAlpha = f.life < 12 ? f.life / 12 : 1;
        outlined(f.text, f.x, f.y, 24, f.color);
        ctx.globalAlpha = 1;
      }
    }
  }

  function drawOverlayText() {
    // fighting-game combo counter
    if (combo >= 2 && state === 'play') {
      ctx.save(); ctx.translate(76, 168); ctx.rotate(-0.1); ctx.scale(1 + comboPulse * 0.5, 1 + comboPulse * 0.5);
      outlined(String(combo), 0, 0, 58, '#ffd23f', 'left');
      const nw = ctx.measureText(String(combo)).width;
      outlined('HIT COMBO!', nw + 8, 10, 20, '#fff4d6', 'left');
      ctx.restore();
    }
    // announcer banners
    for (const b of banners) {
      const t = b.max - b.life;
      const s = t < 7 ? 3.2 - (t / 7) * 2.2 : 1 + Math.sin(t * 0.3) * 0.02;
      ctx.save();
      ctx.globalAlpha = b.life < 12 ? b.life / 12 : 1;
      ctx.translate(W / 2, 270); ctx.rotate(-0.06); ctx.scale(s, s);
      outlined(b.text, 5, 6, b.size, '#ff2fa8');
      const gr = ctx.createLinearGradient(0, -b.size / 2, 0, b.size / 2);
      gr.addColorStop(0, b.c1); gr.addColorStop(1, b.c2);
      outlined(b.text, 0, 0, b.size, gr);
      ctx.restore();
    }
  }

  function draw() {
    ctx.setTransform(k, 0, 0, k, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    const sh = reduceMotion ? 0 : shake;
    ctx.translate(W / 2, H / 2); ctx.scale(1 + (reduceMotion ? 0 : zoom), 1 + (reduceMotion ? 0 : zoom));
    ctx.translate(-W / 2 + (sh > 0.3 ? rand(-sh, sh) : 0), -H / 2 + (sh > 0.3 ? rand(-sh, sh) : 0));
    drawScene();
    ctx.restore();

    if (boost) {
      const v = ctx.createRadialGradient(W / 2, H / 2, H * 0.28, W / 2, H / 2, H * 0.75);
      v.addColorStop(0, 'rgba(255,120,40,0)'); v.addColorStop(1, 'rgba(255,60,120,0.4)');
      ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
    }
    if (flash > 0) { ctx.fillStyle = 'rgba(255,255,255,' + clamp(flash * 0.5, 0, 0.5) + ')'; ctx.fillRect(0, 0, W, H); }
    drawOverlayText();
  }

  function hud() {
    el.score.textContent = score.toLocaleString();
    el.kmh.textContent = Math.round(speed * 30);
    el.speedfill.style.width = clamp(((speed - 4) / 6) * 100, 0, 100) + '%';
    el.boostfill.style.width = (boost ? (boostTimer / BOOST_FRAMES) * 100 : 0) + '%';
  }

  // ---- main loop (fixed 60 Hz, with hit-stop) ---------------------------
  let last = performance.now(), acc = 0;
  function loop(now) {
    acc += Math.min(now - last, 100); last = now;
    while (acc >= 1000 / 60) {
      tick++;
      if (hitStop > 0) hitStop--;
      else step();
      acc -= 1000 / 60;
    }
    draw(); hud();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
