/* ================================================================
   Vue Paramètres — 5 onglets de configuration
   ================================================================ */
import { showToast, setInputBarVisible } from '/static/core/core.js';

const _CSS = '/static/views/settings/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-settings')) {
    const l = document.createElement('link');
    l.id = 'css-settings'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── State ─────────────────────────────────────────────────────
let _cfg = {};
let _models = [];
let _saveTimer = null;

// ── Helpers ───────────────────────────────────────────────────
function _get(key) {
  const parts = key.split('.');
  let v = _cfg;
  for (const p of parts) { if (v == null) return ''; v = v[p]; }
  return v ?? '';
}

function _debounce(fn, ms = 600) {
  return (...args) => {
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => fn(...args), ms);
  };
}

async function _save(key, value) {
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value }),
    });
    if (!r.ok) throw new Error(await r.text());
    _showSaveDot();
    // update local cache
    const parts = key.split('.');
    let obj = _cfg;
    for (let i = 0; i < parts.length - 1; i++) {
      if (obj[parts[i]] == null) obj[parts[i]] = {};
      obj = obj[parts[i]];
    }
    obj[parts[parts.length - 1]] = value;
  } catch (e) {
    showToast('Erreur sauvegarde : ' + e.message);
  }
}

function _showSaveDot() {
  const dot = document.getElementById('s-savedot');
  if (!dot) return;
  dot.classList.add('show');
  setTimeout(() => dot.classList.remove('show'), 1800);
}

// ── Row builders ──────────────────────────────────────────────

function _mkToggle(key, label, desc = '') {
  const checked = _get(key) ? 'checked' : '';
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <label class="s-toggle">
      <input type="checkbox" ${checked} data-key="${key}" data-type="bool">
      <span class="s-toggle-track"></span>
    </label>
  </div>`;
}

function _mkText(key, label, desc = '', placeholder = '', type = 'text', extraClass = '') {
  const val = _get(key);
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <input class="s-input ${extraClass}" type="${type}" placeholder="${placeholder}"
      value="${String(val).replace(/"/g, '&quot;')}" data-key="${key}">
  </div>`;
}

function _mkSelect(key, label, desc = '', options = []) {
  const current = String(_get(key));
  const opts = options.map(o => {
    const v = typeof o === 'string' ? o : o.value;
    const l = typeof o === 'string' ? o : o.label;
    return `<option value="${v}" ${v === current ? 'selected' : ''}>${l}</option>`;
  }).join('');
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <select class="s-input narrow" data-key="${key}">${opts}</select>
  </div>`;
}

function _mkModelSelect(key, label, desc = '') {
  const current = String(_get(key));
  const opts = _models.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${m}</option>`).join('');
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <div class="s-model-row">
      <select class="s-input" data-key="${key}">${opts}</select>
    </div>
  </div>`;
}

function _mkUrlRow(key, label, desc = '', testId) {
  const val = _get(key);
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <div class="s-row-end">
      <input class="s-input wide" type="url" value="${String(val).replace(/"/g, '&quot;')}"
        data-key="${key}" placeholder="http://">
      <button class="s-btn" data-test="${testId}">Test</button>
    </div>
  </div>`;
}

function _mkNumber(key, label, desc = '', min = 0, max = 100, step = 1) {
  const val = _get(key);
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <input class="s-input narrow" type="number" min="${min}" max="${max}" step="${step}"
      value="${val}" data-key="${key}">
  </div>`;
}

function _sec(title, rows) {
  return `<div class="s-section"><h3 class="s-section-title">${title}</h3>${rows}</div>`;
}

// ── Module cards ──────────────────────────────────────────────
function _mkModules() {
  const mods = [
    { key: 'modules.domotique',    icon: '🏠', label: 'Domotique',     sub: 'HA, Kasa, Domoticz' },
    { key: 'modules.print3d',      icon: '🖨️', label: 'Impression 3D', sub: 'K1, OctoPrint…' },
    { key: 'modules.music',        icon: '🎵', label: 'Musique',       sub: 'Navidrome' },
    { key: 'modules.bibliotheque', icon: '📚', label: 'Bibliothèque',  sub: 'Calibre-Web' },
  ];
  const cards = mods.map(m => {
    const on = _get(m.key);
    return `
    <div class="s-module-card ${on ? 'enabled' : ''}" data-mod="${m.key}">
      <div class="mod-icon">${m.icon}</div>
      <div class="mod-label">${m.label}</div>
      <div class="mod-sub">${m.sub}</div>
      <div class="mod-badge">${on ? 'Activé' : 'Désactivé'}</div>
    </div>`;
  }).join('');
  return `<div class="s-section">
    <h3 class="s-section-title">Modules optionnels — menu &amp; onglets</h3>
    <div class="s-modules">${cards}</div>
  </div>`;
}

// ── Panels ────────────────────────────────────────────────────
function _panelAccueil() {
  return [
    _sec('Profil', [
      _mkText('user.name', 'Votre prénom', 'Utilisé dans les briefings et Telegram', 'Aurelien'),
      _mkSelect('language', 'Langue interface', '', [
        { value: 'fr', label: 'Français' },
        { value: 'en', label: 'English' },
      ]),
      _mkSelect('theme', 'Thème', 'Apparence de l\'application', ['Light','Dark','Auto']),
    ].join('')),

    _mkModules(),

    _sec('Météo', [
      _mkText('weather.city', 'Ville', 'Nom affiché dans le briefing', 'Paris, FR'),
      _mkNumber('weather.latitude', 'Latitude', '', -90, 90, 0.0001),
      _mkNumber('weather.longitude', 'Longitude', '', -180, 180, 0.0001),
    ].join('')),

    _sec('Général', [
      _mkNumber('general.max_history', 'Historique max', 'Nombre de messages conservés', 5, 100),
      _mkToggle('general.auto_fetch_news', 'Actualités auto', 'Charger les news au démarrage'),
    ].join('')),

    _sec('Telegram', [
      _mkToggle('telegram.enabled', 'Activer Telegram', 'Accès ADA via bot Telegram'),
      _mkText('telegram.token', 'Token bot', 'Obtenu via @BotFather', '123456:ABCdef…'),
      _mkText('telegram.owner_chat_id', 'Owner Chat ID', 'Votre identifiant Telegram', '123456789'),
    ].join('')),

    _sec('Briefing matinal', [
      _mkToggle('briefing.enabled', 'Activer le briefing', 'Résumé météo + news chaque matin'),
      _mkSelect('briefing.hour', 'Heure d\'envoi', '', [5,6,7,8,9,10].map(h => ({ value: h, label: `${h}h00` }))),
    ].join('')),
  ].join('');
}

function _panelLLM() {
  return [
    _sec('Connexion Ollama', [
      _mkUrlRow('ollama_url', 'URL Ollama', 'Serveur Ollama local ou distant', 'ollama'),
      `<div class="s-row"><div class="s-row-info"><div class="s-row-label">Modèles disponibles</div>
        <div class="s-row-desc" id="models-count">Chargement…</div></div>
        <button class="s-btn" id="refresh-models">↻ Actualiser</button></div>`,
    ].join('')),

    _sec('Modèles IA', [
      _mkModelSelect('models.chat', 'Modèle principal', 'Utilisé pour la discussion générale'),
      _mkModelSelect('models.web_agent', 'Modèle Web Agent', 'Modèle vision pour l\'agent web'),
    ].join('')),

    _sec('Routage sémantique', [
      _mkText('semantic_router.embedding_model', 'Modèle d\'embedding',
        'Pour le routeur Ollama (ex: nomic-embed-text)', 'nomic-embed-text'),
      _mkNumber('semantic_router.confidence_threshold', 'Seuil de confiance',
        'Minimum pour router (0.1 – 1.0)', 0, 1, 0.05),
    ].join('')),

    _sec('N8N (automatisation)', [
      _mkUrlRow('n8n.url', 'URL N8N', 'Serveur N8N local', 'n8n'),
      _mkToggle('n8n.fallback_enabled', 'Fallback N8N', 'Utiliser N8N si fonction locale échoue'),
    ].join('')),
  ].join('');
}

function _panelDomotique() {
  return [
    _sec('Home Assistant', [
      _mkToggle('home_assistant.enabled', 'Activer Home Assistant', ''),
      _mkUrlRow('home_assistant.url', 'URL Home Assistant', 'ex: http://homeassistant.local:8123', 'ha'),
      _mkText('home_assistant.token', 'Token long durée', 'Créé dans Profil → Tokens', '', 'password'),
      _mkText('home_assistant.tts_service', 'Service TTS', 'Entité TTS Home Assistant', 'tts.piper'),
      _mkToggle('home_assistant.door_alert_enabled', 'Alerte porte', 'Notifier via Telegram à l\'ouverture'),
      _mkText('home_assistant.door_entity', 'Entité porte', 'Entity ID du capteur de porte', 'binary_sensor.porte'),
      _mkText('home_assistant.door_message', 'Message alerte porte', '', '🚪 Un visiteur !'),
    ].join('')),

    _sec('Domoticz', [
      _mkToggle('domoticz.enabled', 'Activer Domoticz', ''),
      _mkUrlRow('domoticz.url', 'URL Domoticz', 'ex: http://192.168.1.10:8080', 'domoticz'),
      _mkText('domoticz.username', 'Utilisateur', 'Laisser vide si pas d\'auth', 'admin'),
      _mkText('domoticz.password', 'Mot de passe', '', '', 'password'),
    ].join('')),

    _sec('Kasa (TP-Link)', [
      _mkToggle('kasa.enabled', 'Activer Kasa', 'Découverte automatique des prises Kasa sur le réseau'),
    ].join('')),
  ].join('');
}

function _panelPrint3D() {
  return [
    _sec('Imprimante K1', [
      _mkText('k1.ip', 'Adresse IP', 'IP de l\'imprimante K1 sur le réseau', '192.168.1.xxx'),
      _mkText('k1.password', 'Mot de passe SSH', '', '', 'password'),
    ].join('')),

    _sec('CAD / Build123D', [
      `<div class="s-row"><div class="s-row-info">
        <div class="s-row-label">Modèle de génération 3D</div>
        <div class="s-row-desc">Utilise le modèle LLM configuré dans l'onglet LLM → Modèle principal</div>
      </div></div>`,
    ].join('')),
  ].join('');
}

function _panelMusique() {
  return [
    _sec('Navidrome', [
      _mkUrlRow('navidrome.url', 'URL Navidrome', 'ex: http://localhost:4533', 'navidrome'),
      _mkText('navidrome.user', 'Utilisateur', '', 'admin'),
      _mkText('navidrome.password', 'Mot de passe', '', '', 'password'),
    ].join('')),

  ].join('');
}

function _panelBibliotheque() {
  return [
    _sec('Calibre-Web', [
      _mkUrlRow('calibre.url', 'URL Calibre-Web', 'ex: http://192.168.1.70:8083', 'calibre'),
      _mkText('calibre.username', 'Nom d\'utilisateur', 'Identifiant Calibre-Web', ''),
      _mkText('calibre.password', 'Mot de passe', 'Mot de passe Calibre-Web', '', 'password'),
    ].join('')),
  ].join('');
}

// ── Build HTML ────────────────────────────────────────────────
function _buildHTML() {
  return `
<div class="settings-wrap">
  <div class="s-tabbar">
    <button class="s-tab active" data-panel="general">🏠 Accueil</button>
    <button class="s-tab" data-panel="llm">🤖 LLM</button>
    <button class="s-tab" data-panel="domotique">💡 Domotique</button>
    <button class="s-tab" data-panel="print3d">🖨 Impression 3D</button>
    <button class="s-tab" data-panel="music">🎵 Musique</button>
    <button class="s-tab" data-panel="bibliotheque">📚 Bibliothèque</button>
    <span class="s-save-dot" id="s-savedot"></span>
  </div>
  <div class="s-panels">
    <div class="s-panel active" id="panel-general">${_panelAccueil()}</div>
    <div class="s-panel" id="panel-llm">${_panelLLM()}</div>
    <div class="s-panel" id="panel-domotique">${_panelDomotique()}</div>
    <div class="s-panel" id="panel-print3d">${_panelPrint3D()}</div>
    <div class="s-panel" id="panel-music">${_panelMusique()}</div>
    <div class="s-panel" id="panel-bibliotheque">${_panelBibliotheque()}</div>
  </div>
</div>`;
}

// ── Events ────────────────────────────────────────────────────
const _debouncedSave = _debounce(_save, 700);

function _bindEvents(root) {
  // Tab switching
  root.querySelectorAll('.s-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      root.querySelectorAll('.s-tab').forEach(t => t.classList.remove('active'));
      root.querySelectorAll('.s-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      root.getElementById?.('panel-' + tab.dataset.panel)?.classList.add('active');
      // querySelector inside root (root is the viewport div)
      root.querySelector('#panel-' + tab.dataset.panel)?.classList.add('active');
    });
  });

  // Text / number inputs (debounced)
  root.querySelectorAll('input[data-key]').forEach(el => {
    el.addEventListener('input', () => {
      const type = el.dataset.type;
      const val = type === 'bool' ? el.checked : (el.type === 'number' ? Number(el.value) : el.value);
      _debouncedSave(el.dataset.key, val);
    });
  });

  // Checkboxes (immediate)
  root.querySelectorAll('input[data-type="bool"]').forEach(el => {
    el.addEventListener('change', () => _save(el.dataset.key, el.checked));
  });

  // Selects (immediate)
  root.querySelectorAll('select[data-key]').forEach(el => {
    el.addEventListener('change', () => {
      const v = el.type === 'number' || el.dataset.numtype ? Number(el.value) : el.value;
      // briefing.hour should be a number
      const val = (el.dataset.key === 'briefing.hour') ? Number(el.value) : el.value;
      _save(el.dataset.key, val);
    });
  });

  // Module cards
  root.querySelectorAll('.s-module-card').forEach(card => {
    card.addEventListener('click', () => {
      const key = card.dataset.mod;
      const current = _get(key);
      const next = !current;
      // Mise à jour immédiate du cache local (AVANT applyModuleVisibility)
      const parts = key.split('.');
      let obj = _cfg;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!obj[parts[i]]) obj[parts[i]] = {};
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = next;
      // UI
      card.classList.toggle('enabled', next);
      card.querySelector('.mod-badge').textContent = next ? 'Activé' : 'Désactivé';
      applyModuleVisibility();
      // Persistance asynchrone
      _save(key, next);
    });
  });

  // Test buttons
  root.querySelectorAll('[data-test]').forEach(btn => {
    btn.addEventListener('click', () => _testConnection(btn, root));
  });

  // Refresh models
  const refreshBtn = root.querySelector('#refresh-models');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => _loadModels(root));
  }
}

async function _testConnection(btn, root) {
  const testId = btn.dataset.test;
  btn.disabled = true;
  btn.textContent = '…';

  let url = '';
  let ok = false;
  try {
    if (testId === 'ollama') {
      url = _cfg.ollama_url || '';
      const base = url.replace(/\/api\/?$/, '');
      const r = await fetch('/api/status');
      ok = (await r.json()).ollama === 'online';
    } else if (testId === 'ha') {
      url = (_cfg.home_assistant?.url || '').rstrip('/') + '/api/';
      const r = await fetch(url, { headers: { Authorization: `Bearer ${_cfg.home_assistant?.token || ''}` }, signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    } else if (testId === 'domoticz') {
      url = (_cfg.domoticz?.url || '').replace(/\/$/, '') + '/json.htm?type=command&param=getversion';
      const r = await fetch(`/api/proxy/get?url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    } else if (testId === 'navidrome') {
      const base = (_cfg.navidrome?.url || '').replace(/\/$/, '');
      const u = _cfg.navidrome?.user || '';
      const p = _cfg.navidrome?.password || '';
      const testUrl = `${base}/rest/ping.view?u=${u}&p=${p}&v=1.16.0&c=ada&f=json`;
      const r = await fetch(testUrl, { signal: AbortSignal.timeout(5000) });
      const data = await r.json();
      ok = data?.['subsonic-response']?.status === 'ok';
    } else if (testId === 'calibre') {
      url = (_cfg.calibre?.url || '').replace(/\/$/, '') + '/ajax/library-info';
      const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    } else if (testId === 'n8n') {
      url = (_cfg.n8n?.url || '').replace(/\/$/, '') + '/healthz';
      const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    }
  } catch { ok = false; }

  btn.disabled = false;
  btn.textContent = ok ? '✓ OK' : '✗ Erreur';
  btn.style.color = ok ? '#4caf50' : '#ef5350';
  setTimeout(() => { btn.textContent = 'Test'; btn.style.color = ''; }, 3000);
}

async function _loadModels(root) {
  const countEl = root.querySelector('#models-count');
  if (countEl) countEl.textContent = 'Chargement…';
  try {
    const r = await fetch('/api/ollama/models');
    _models = await r.json();
    if (countEl) countEl.textContent = `${_models.length} modèle(s) disponible(s)`;
    // Refresh model selects
    ['models.chat', 'models.web_agent'].forEach(key => {
      const sel = root.querySelector(`select[data-key="${key}"]`);
      if (!sel) return;
      const current = _get(key);
      sel.innerHTML = _models.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${m}</option>`).join('');
    });
  } catch {
    if (countEl) countEl.textContent = 'Ollama inaccessible';
  }
}

// ── Nav module visibility ─────────────────────────────────────
export function applyModuleVisibility() {
  const map = {
    domotique:    ['[data-page="home"]', '[data-view="cameras"]'],
    print3d:      ['[data-page="printers"]', '[data-page="cad"]'],
    music:        ['[data-page="music"]'],
    bibliotheque: ['[data-page="library"]'],
  };
  Object.entries(map).forEach(([mod, selectors]) => {
    const on = _get(`modules.${mod}`);
    selectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = on ? '' : 'none';
      });
    });
  });
}

// ── mount / unmount ───────────────────────────────────────────
let _root = null;

export async function mount(container) {
  _ensureCSS();
  setInputBarVisible(false);

  // Load settings + models in parallel
  container.innerHTML = `<div class="s-loading">Chargement des paramètres…</div>`;
  try {
    const [cfgRes, modRes] = await Promise.all([
      fetch('/api/settings'),
      fetch('/api/ollama/models'),
    ]);
    _cfg = await cfgRes.json();
    _models = await modRes.json();
  } catch (e) {
    container.innerHTML = `<div class="s-loading">Erreur : ${e.message}</div>`;
    return;
  }

  container.innerHTML = _buildHTML();
  _root = container;
  _bindEvents(container);

  // Show models count
  const countEl = container.querySelector('#models-count');
  if (countEl) countEl.textContent = `${_models.length} modèle(s) disponible(s)`;
}

export function unmount() {
  _root = null;
}
