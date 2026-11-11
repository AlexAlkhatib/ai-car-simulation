/* ---------------------------------------------------------------------------
 * Client de la simulation : reçoit l'état par Server-Sent Events et dessine
 * la scène sur un canvas 1920x1080 (mêmes coordonnées que la version Pygame).
 * Aucune dépendance externe.
 * ------------------------------------------------------------------------- */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const els = {
    canvas: $('sim-canvas'),
    statusPill: $('status-pill'),
    statusLabel: $('status-label'),
    connectionPill: $('connection-pill'),
    connectionLabel: $('connection-label'),
    stageBadge: $('stage-badge'),
    btnPlay: $('btn-play'),
    btnReset: $('btn-reset'),
    speedSelect: $('speed-select'),
    mapSelect: $('map-select'),
    radarsToggle: $('radars-toggle'),
    genomeLink: $('genome-link'),
    genomeHint: $('genome-hint'),
    errorPanel: $('error-panel'),
    errorText: $('error-text'),
    kpiGeneration: $('kpi-generation'),
    kpiGenerationSub: $('kpi-generation-sub'),
    kpiAlive: $('kpi-alive'),
    kpiAliveSub: $('kpi-alive-sub'),
    kpiFitness: $('kpi-fitness'),
    kpiRecord: $('kpi-record'),
    kpiRecordSub: $('kpi-record-sub'),
    kpiFps: $('kpi-fps'),
    kpiFpsSub: $('kpi-fps-sub'),
    progressBar: $('progress-bar'),
    progressLabel: $('progress-label'),
    progressTrack: $('progress-track'),
    chart: $('chart'),
    chartMeta: $('chart-meta'),
    cfgPopulation: $('cfg-population'),
    cfgSensors: $('cfg-sensors'),
    cfgActions: $('cfg-actions'),
    cfgFrames: $('cfg-frames'),
    cfgFps: $('cfg-fps'),
    cfgTrack: $('cfg-track'),
  };

  const ctx = els.canvas.getContext('2d');
  const chartCtx = els.chart.getContext('2d');

  const STATUS_LABELS = {
    idle: 'Prêt',
    running: 'En cours',
    paused: 'En pause',
    finished: 'Terminé',
    error: 'Erreur',
  };

  const state = {
    config: null,
    snapshot: null,
    mapImage: null,
    mapUrl: null,
    carImage: new Image(),
    history: [],
    showRadars: true,
    lastGeneration: -1,
    historyTimer: null,
    frameCount: 0,
    fpsStamp: performance.now(),
    busy: false,
    source: null,
    polling: false,
  };

  /* --- Réseau ----------------------------------------------------------- */

  async function api(path, options) {
    const response = await fetch(path, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      ...options,
    });
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        if (payload && payload.error) message = payload.error;
      } catch (_) { /* corps non JSON */ }
      throw new Error(message);
    }
    return response.json();
  }

  const post = (path, body) =>
    api(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  function setConnection(online, label) {
    els.connectionPill.dataset.state = online ? 'live' : 'offline';
    els.connectionLabel.textContent = label;
  }

  function setBusy(busy) {
    state.busy = busy;
    els.btnPlay.disabled = busy;
    els.btnReset.disabled = busy;
    els.mapSelect.disabled = busy;
  }

  /* --- Configuration ---------------------------------------------------- */

  function mapLabel(name, index) {
    const digits = name.match(/(\d+)/);
    return digits ? `Piste ${digits[1]}` : `Piste ${index + 1}`;
  }

  async function loadConfig() {
    const config = await api('/api/config');
    state.config = config;

    els.mapSelect.innerHTML = '';
    config.maps.forEach((name, index) => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = mapLabel(name, index);
      els.mapSelect.append(option);
    });

    els.speedSelect.innerHTML = '';
    config.speeds.forEach((speed) => {
      const option = document.createElement('option');
      option.value = String(speed);
      option.textContent = `${speed}×`;
      els.speedSelect.append(option);
    });

    els.cfgPopulation.textContent = String(config.population);
    els.cfgSensors.textContent = `${config.sensor_count} (${config.radar_angles.join('°, ')}°)`;
    els.cfgActions.textContent = `${config.sensor_count ? config.actions.length : 4} · ${config.actions.join(', ')}`;
    els.cfgFrames.textContent = String(config.frame_limit);
    els.cfgFps.textContent = `${config.fps} fps`;
    els.cfgTrack.textContent = `${config.track.width} × ${config.track.height}`;

    if (state.snapshot) syncControls(state.snapshot);
  }

  /* --- Flux temps réel -------------------------------------------------- */

  function connect() {
    if (!('EventSource' in window)) {
      startPolling();
      return;
    }
    if (state.source) state.source.close();
    const source = new EventSource('/api/stream');
    state.source = source;
    source.onopen = () => setConnection(true, 'Temps réel');
    source.onerror = () => setConnection(false, 'Reconnexion…');
    source.onmessage = (event) => {
      if (!event.data) return;
      try {
        applySnapshot(JSON.parse(event.data));
      } catch (error) {
        console.error('Frame illisible', error);
      }
    };
  }

  async function startPolling() {
    if (state.polling) return;
    state.polling = true;
    const tick = async () => {
      try {
        applySnapshot(await api('/api/state'));
        setConnection(true, 'Sondage');
      } catch (_) {
        setConnection(false, 'Hors ligne');
      }
      setTimeout(tick, 120);
    };
    tick();
  }

  /* --- Application d'un instantané -------------------------------------- */

  function applySnapshot(snapshot) {
    state.snapshot = snapshot;
    syncMap(snapshot.map);
    draw(snapshot);
    syncControls(snapshot);
    updateKpis(snapshot);
    countFrame();

    if (snapshot.generation !== state.lastGeneration) {
      state.lastGeneration = snapshot.generation;
      scheduleHistory();
    }
  }

  function syncMap(map) {
    if (!map || !map.url || map.url === state.mapUrl) return;
    state.mapUrl = map.url;
    const image = new Image();
    image.onload = () => {
      state.mapImage = image;
      if (state.snapshot) draw(state.snapshot);
    };
    image.onerror = () => { state.mapImage = null; };
    image.src = map.url;
  }

  function syncControls(snapshot) {
    const status = snapshot.status;
    els.statusPill.dataset.state = status;
    els.statusLabel.textContent = STATUS_LABELS[status] || status;

    const labels = {
      running: 'Pause',
      paused: 'Reprendre',
      idle: 'Démarrer',
      finished: 'Relancer',
      error: 'Relancer',
    };
    els.btnPlay.textContent = labels[status] || 'Démarrer';
    els.btnPlay.classList.toggle('btn-primary', status !== 'running');

    els.stageBadge.hidden = status !== 'paused';

    if (document.activeElement !== els.mapSelect) {
      els.mapSelect.value = snapshot.map.name;
    }
    if (document.activeElement !== els.speedSelect) {
      els.speedSelect.value = String(snapshot.speed);
    }

    if (snapshot.error) {
      els.errorPanel.hidden = false;
      els.errorText.textContent = snapshot.error;
    } else {
      els.errorPanel.hidden = true;
    }

    const genome = snapshot.best_genome;
    els.genomeLink.hidden = !genome;
    if (genome) {
      els.genomeLink.textContent = `Meilleur génome (gén. ${genome.generation} · ${formatNumber(genome.fitness)})`;
    }
  }

  function updateKpis(snapshot) {
    els.kpiGeneration.textContent = String(snapshot.generation);
    els.kpiGenerationSub.textContent = `sur ${snapshot.max_generations}`;

    els.kpiAlive.textContent = String(snapshot.alive);
    els.kpiAliveSub.textContent = `population ${snapshot.population}`;

    els.kpiFitness.textContent = formatNumber(snapshot.current_best);
    els.kpiRecord.textContent = formatNumber(snapshot.best_fitness);
    els.kpiRecordSub.textContent = snapshot.best_genome
      ? `génération ${snapshot.best_genome.generation}`
      : 'meilleur génome';

    const limit = snapshot.frame_limit || 1;
    const ratio = Math.min(1, snapshot.frame / limit);
    els.progressBar.style.width = `${(ratio * 100).toFixed(1)}%`;
    els.progressTrack.setAttribute('aria-valuemax', String(limit));
    els.progressTrack.setAttribute('aria-valuenow', String(snapshot.frame));
    els.progressLabel.textContent = `${snapshot.frame} / ${limit} frames`;
  }

  function countFrame() {
    state.frameCount += 1;
    const now = performance.now();
    const elapsed = now - state.fpsStamp;
    if (elapsed >= 500) {
      const fps = (state.frameCount * 1000) / elapsed;
      els.kpiFps.textContent = fps.toFixed(0);
      els.kpiFpsSub.textContent = `${state.snapshot ? state.snapshot.speed : 1}× vitesse`;
      state.frameCount = 0;
      state.fpsStamp = now;
    }
  }

  function formatNumber(value) {
    const number = Number(value) || 0;
    if (Math.abs(number) >= 10000) return `${(number / 1000).toFixed(1)}k`;
    return number.toFixed(number >= 100 ? 0 : 1);
  }

  /* --- Dessin de la scène ----------------------------------------------- */

  function draw(snapshot) {
    const width = els.canvas.width;
    const height = els.canvas.height;

    ctx.clearRect(0, 0, width, height);
    if (state.mapImage) {
      ctx.drawImage(state.mapImage, 0, 0, width, height);
    } else {
      ctx.fillStyle = '#0b1118';
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = 'rgba(147, 164, 189, 0.7)';
      ctx.font = '28px Arial, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Chargement de la piste…', width / 2, height / 2);
    }

    const [carWidth, carHeight] = snapshot.car_size || [60, 60];
    const halfWidth = carWidth / 2;
    const halfHeight = carHeight / 2;
    const carReady = state.carImage.complete && state.carImage.naturalWidth > 0;

    for (const car of snapshot.cars || []) {
      if (!car.alive) continue; // comme l'original : seules les vivantes sont dessinées
      const centerX = car.x + halfWidth;
      const centerY = car.y + halfHeight;

      if (state.showRadars) {
        ctx.strokeStyle = '#00ff00';
        ctx.fillStyle = '#00ff00';
        ctx.lineWidth = 1;
        for (const radar of car.radars || []) {
          ctx.beginPath();
          ctx.moveTo(centerX, centerY);
          ctx.lineTo(radar[0], radar[1]);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(radar[0], radar[1], 5, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      if (carReady) {
        ctx.save();
        ctx.translate(centerX, centerY);
        // pygame.transform.rotate tourne dans le sens anti-horaire.
        ctx.rotate((-car.angle * Math.PI) / 180);
        ctx.drawImage(state.carImage, -halfWidth, -halfHeight, carWidth, carHeight);
        ctx.restore();
      } else {
        ctx.fillStyle = '#2ee6a8';
        ctx.fillRect(car.x, car.y, carWidth, carHeight);
      }
    }

    // Textes de la version d'origine (mêmes coordonnées et tailles).
    ctx.fillStyle = '#000000';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '30px Arial, sans-serif';
    ctx.fillText(`Génération : ${snapshot.generation}`, 900, 450);
    ctx.font = '20px Arial, sans-serif';
    ctx.fillText(`Toujours en vie : ${snapshot.alive}`, 900, 490);
  }

  /* --- Graphique de fitness --------------------------------------------- */

  function scheduleHistory() {
    clearTimeout(state.historyTimer);
    state.historyTimer = setTimeout(loadHistory, 400);
  }

  async function loadHistory() {
    try {
      const data = await api('/api/history');
      state.history = data.history || [];
      drawChart();
    } catch (_) {
      /* silencieux : le flux principal reste prioritaire */
    }
  }

  function drawChart() {
    const width = els.chart.width;
    const height = els.chart.height;
    const pad = { left: 52, right: 14, top: 16, bottom: 28 };
    const innerWidth = width - pad.left - pad.right;
    const innerHeight = height - pad.top - pad.bottom;

    chartCtx.clearRect(0, 0, width, height);
    chartCtx.fillStyle = 'rgba(0, 0, 0, 0.22)';
    chartCtx.fillRect(0, 0, width, height);

    const series = state.history;
    if (!series.length) {
      chartCtx.fillStyle = 'rgba(147, 164, 189, 0.65)';
      chartCtx.font = '16px system-ui, sans-serif';
      chartCtx.textAlign = 'center';
      chartCtx.textBaseline = 'middle';
      chartCtx.fillText('En attente de la première génération…', width / 2, height / 2);
      els.chartMeta.textContent = '—';
      return;
    }

    const maxValue = Math.max(1, ...series.map((point) => point.best));
    const paddedMax = maxValue * 1.08;
    const xFor = (index) =>
      series.length === 1 ? pad.left : pad.left + (index / (series.length - 1)) * innerWidth;
    const yFor = (value) => pad.top + innerHeight - (value / paddedMax) * innerHeight;

    // Grille horizontale
    chartCtx.strokeStyle = 'rgba(148, 175, 210, 0.12)';
    chartCtx.lineWidth = 1;
    chartCtx.font = '12px system-ui, sans-serif';
    chartCtx.fillStyle = 'rgba(147, 164, 189, 0.75)';
    chartCtx.textAlign = 'right';
    chartCtx.textBaseline = 'middle';
    for (let step = 0; step <= 4; step += 1) {
      const value = (paddedMax / 4) * step;
      const y = yFor(value);
      chartCtx.beginPath();
      chartCtx.moveTo(pad.left, y);
      chartCtx.lineTo(width - pad.right, y);
      chartCtx.stroke();
      chartCtx.fillText(formatNumber(value), pad.left - 8, y);
    }

    // Axe des générations
    chartCtx.textAlign = 'center';
    chartCtx.textBaseline = 'top';
    const first = series[0].generation;
    const last = series[series.length - 1].generation;
    chartCtx.fillText(`gén. ${first}`, pad.left, height - pad.bottom + 8);
    if (last !== first) {
      chartCtx.fillText(`gén. ${last}`, width - pad.right, height - pad.bottom + 8);
    }

    const meanPath = new Path2D();
    const bestPath = new Path2D();
    series.forEach((point, index) => {
      const x = xFor(index);
      if (index === 0) {
        meanPath.moveTo(x, yFor(point.mean));
        bestPath.moveTo(x, yFor(point.best));
      } else {
        meanPath.lineTo(x, yFor(point.mean));
        bestPath.lineTo(x, yFor(point.best));
      }
    });

    // Aire sous la meilleure fitness
    const area = new Path2D(bestPath);
    area.lineTo(xFor(series.length - 1), yFor(0));
    area.lineTo(xFor(0), yFor(0));
    area.closePath();
    const gradient = chartCtx.createLinearGradient(0, pad.top, 0, height - pad.bottom);
    gradient.addColorStop(0, 'rgba(46, 230, 168, 0.28)');
    gradient.addColorStop(1, 'rgba(46, 230, 168, 0.01)');
    chartCtx.fillStyle = gradient;
    chartCtx.fill(area);

    chartCtx.lineWidth = 2.5;
    chartCtx.strokeStyle = '#2ee6a8';
    chartCtx.stroke(bestPath);
    chartCtx.lineWidth = 1.6;
    chartCtx.strokeStyle = 'rgba(139, 157, 255, 0.9)';
    chartCtx.stroke(meanPath);

    // Dernier point
    const lastPoint = series[series.length - 1];
    chartCtx.fillStyle = '#2ee6a8';
    chartCtx.beginPath();
    chartCtx.arc(xFor(series.length - 1), yFor(lastPoint.best), 3.5, 0, Math.PI * 2);
    chartCtx.fill();

    els.chartMeta.textContent = `${series.length} gén. · record ${formatNumber(lastPoint.best)}`;
  }

  /* --- Contrôles --------------------------------------------------------- */

  async function withBusy(action) {
    if (state.busy) return;
    setBusy(true);
    try {
      applySnapshot(await action());
    } catch (error) {
      els.errorPanel.hidden = false;
      els.errorText.textContent = error.message;
    } finally {
      setBusy(false);
    }
  }

  function togglePlay() {
    const status = state.snapshot ? state.snapshot.status : 'idle';
    if (status === 'running') {
      withBusy(() => post('/api/pause'));
    } else if (status === 'paused') {
      withBusy(() => post('/api/resume'));
    } else {
      withBusy(() => post('/api/start'));
    }
  }

  function bindControls() {
    els.btnPlay.addEventListener('click', togglePlay);
    els.btnReset.addEventListener('click', () => {
      withBusy(async () => {
        const snapshot = await post('/api/reset');
        state.lastGeneration = -1;
        state.history = [];
        drawChart();
        return snapshot;
      });
    });

    els.speedSelect.addEventListener('change', () => {
      withBusy(() => post('/api/settings', { speed: Number(els.speedSelect.value) }));
    });

    els.mapSelect.addEventListener('change', () => {
      withBusy(async () => {
        const snapshot = await post('/api/settings', { map: els.mapSelect.value });
        state.mapImage = null;
        state.mapUrl = null;
        state.lastGeneration = -1;
        return snapshot;
      });
    });

    els.radarsToggle.addEventListener('change', () => {
      state.showRadars = els.radarsToggle.checked;
      if (state.snapshot) draw(state.snapshot);
    });

    document.addEventListener('keydown', (event) => {
      const tag = (event.target && event.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      if (event.code === 'Space') {
        event.preventDefault();
        togglePlay();
      } else if (event.key === 'r' || event.key === 'R') {
        els.btnReset.click();
      }
    });

    window.addEventListener('beforeunload', () => {
      if (state.source) state.source.close();
    });
  }

  /* --- Démarrage -------------------------------------------------------- */

  async function boot() {
    state.carImage.src = '/media/car.png';
    bindControls();
    try {
      await loadConfig();
      setConnection(true, 'Connecté');
    } catch (error) {
      setConnection(false, 'Hors ligne');
      els.errorPanel.hidden = false;
      els.errorText.textContent = error.message;
    }
    loadHistory();
    connect();
  }

  boot();
})();
