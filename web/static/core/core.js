/* ================================================================
   ADA Mobile — Core Module
   Sidebar, navigation, toast, status polling, view dispatcher.
   Chaque vue est un module ES importé dynamiquement.
   ================================================================ */

// ── Registre des vues ───────────────────────────────────────────
const VIEW_LOADERS = {
  dashboard: () => import('/static/views/dashboard/index.js'),
  chat:      () => import('/static/views/chat/index.js'),
  memory:    () => import('/static/views/memory/index.js'),
  page:      () => import('/static/views/page/index.js'),
  planner:   () => import('/static/views/planner/index.js'),
  briefing:  () => import('/static/views/briefing/index.js'),
  webagent:  () => import('/static/views/webagent/index.js'),
  cameras:   () => import('/static/views/cameras/index.js'),
  marketing: () => import('/static/views/marketing/index.js'),
  settings:  () => import('/static/views/settings/index.js?v=2'),
  auth:      () => import('/static/views/auth/index.js'),
  // MODULE_SOCIETE
  societe:   () => import('/static/views/societe/index.js?v=2'),
};

const VIEW_TITLES = {
  dashboard: 'Tableau de bord',
  chat:      'Discussion',
  memory:    'Mémoire',
  planner:   'Planificateur',
  briefing:  'Briefing',
  webagent:  'Agent Web',
  cameras:   'Caméras',
  marketing: 'Marketing',
  settings:  'Paramètres',
  auth:      'Connexion',
  // MODULE_SOCIETE
  societe:   'Sociétés',
};

// ── État global ─────────────────────────────────────────────────
export let currentView = '';
let _currentMod = null;

// ── Gestion du token d'authentification ─────────────────────────
export function getToken() { return localStorage.getItem('ada_token'); }

export function setToken(token) {
  localStorage.setItem('ada_token', token);
  document.cookie = `ada_token=${token}; path=/; SameSite=Strict; Max-Age=${30 * 86_400}`;
}

export function clearToken() {
  localStorage.removeItem('ada_token');
  document.cookie = 'ada_token=; path=/; SameSite=Strict; Max-Age=0';
}

// ── DOM ─────────────────────────────────────────────────────────
const sidebar        = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const menuBtn        = document.getElementById('menu-btn');
const sidebarClose   = document.getElementById('sidebar-close');
const navItems       = document.querySelectorAll('.nav-item');
const viewTitle      = document.getElementById('view-title');
const statusDot      = document.getElementById('status-dot');
const adminMenu      = document.getElementById('admin-menu');
const toastEl        = document.getElementById('toast');
const inputBar       = document.getElementById('input-bar');
export const viewport = document.getElementById('viewport');

// ── Menu admin ──────────────────────────────────────────────────
statusDot.addEventListener('click', (e) => {
  e.stopPropagation();
  adminMenu.classList.toggle('hidden');
});
document.addEventListener('click', () => adminMenu.classList.add('hidden'));
adminMenu.addEventListener('click', (e) => e.stopPropagation());

document.getElementById('admin-restart').addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  showToast('Redémarrage en cours…');
  try {
    await fetch('/api/admin/restart', { method: 'POST' });
    setTimeout(() => location.reload(), 2000);
  } catch { /* le process se coupe, c'est normal */ setTimeout(() => location.reload(), 2500); }
});

document.getElementById('admin-clear-cache').addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  if ('serviceWorker' in navigator && 'caches' in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    const reg = await navigator.serviceWorker.getRegistration();
    if (reg) await reg.unregister();
    showToast('Cache vidé — rechargement…');
    setTimeout(() => location.reload(true), 1000);
  } else {
    showToast('Cache SW non disponible.');
  }
});

// ── Utilitaires exportés ────────────────────────────────────────
let _toastTimer;
export function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2500);
}

export function escapeHtml(text = '') {
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Visibilité des modules nav (domotique / print3d / music) ────
export function applyModuleVisibility(modules = {}) {
  const map = {
    domotique: ['[data-page="home"]', '[data-view="cameras"]'],
    print3d:   ['[data-page="printers"]', '[data-page="cad"]'],
    music:     ['[data-page="music"]', '[data-page="library"]'],
  };
  for (const [mod, selectors] of Object.entries(map)) {
    const visible = modules[mod] !== false;
    selectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = visible ? '' : 'none';
      });
    });
  }
}

export async function fetchJSON(url, options = {}) {
  const token = getToken();
  const headers = {
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
  const r = await fetch(url, { ...options, headers });
  if (r.status === 401) {
    clearToken();
    switchView('auth');
    throw new Error('Non authentifié');
  }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function setInputBarVisible(v) {
  if (v) inputBar.classList.remove('hidden');
  else   inputBar.classList.add('hidden');
}

// ── Sidebar ─────────────────────────────────────────────────────
export function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('open');
}
function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('open');
}

menuBtn.addEventListener('click', openSidebar);
sidebarClose.addEventListener('click', closeSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

let _touchStartX = 0;
sidebar.addEventListener('touchstart', (e) => { _touchStartX = e.touches[0].clientX; }, { passive: true });
sidebar.addEventListener('touchend',   (e) => {
  if (e.changedTouches[0].clientX - _touchStartX < -60) closeSidebar();
}, { passive: true });

// ── Statut Ollama + barre hw ────────────────────────────────────
const _hwBar = {
  cpu:    document.getElementById('hw-cpu'),
  ram:    document.getElementById('hw-ram'),
  gpu:    document.getElementById('hw-gpu'),
  vram:   document.getElementById('hw-vram'),
  models: document.getElementById('hw-models'),
};

function _colorStat(el, pct) {
  if (!el) return;
  el.style.color = pct > 85 ? '#ff6b6b' : pct > 60 ? '#ffd166' : '#9de8b0';
}

async function _checkStatus() {
  try {
    const d = await (await fetch('/api/status')).json();
    statusDot.className = d.ollama === 'online' ? 'online' : 'offline';
  } catch { statusDot.className = 'offline'; }
}

async function _updateHwBar() {
  try {
    const d = await (await fetch('/api/dashboard')).json();
    if (_hwBar.cpu) {
      _hwBar.cpu.textContent = `${d.cpu_pct}%`;
      _colorStat(_hwBar.cpu, d.cpu_pct);
    }
    if (_hwBar.ram && d.ram) {
      _hwBar.ram.textContent = `${d.ram.pct}% (${d.ram.used_gb}/${d.ram.total_gb} GB)`;
      _colorStat(_hwBar.ram, d.ram.pct);
    }
    if (_hwBar.gpu) {
      _hwBar.gpu.textContent = d.vram ? `${Math.round((d.vram.used_gb / d.vram.total_gb) * 100)}%` : '—';
    }
    if (_hwBar.vram && d.vram) {
      _hwBar.vram.textContent = `${d.vram.used_gb}/${d.vram.total_gb} GB`;
      _colorStat(_hwBar.vram, (d.vram.used_gb / d.vram.total_gb) * 100);
    }
    if (_hwBar.models) {
      const names = (d.loaded_models || []).map((m) => m.split(':')[0]).join(', ') || (d.model ? d.model.split(':')[0] : '—');
      _hwBar.models.textContent = names;
    }
  } catch { /* silencieux */ }
}

_checkStatus();
_updateHwBar();
setInterval(_checkStatus, 30_000);
setInterval(_updateHwBar, 15_000);

// ── Navigation ──────────────────────────────────────────────────
function _updateNavActive(viewName, pageKey) {
  navItems.forEach((n) => n.classList.remove('active'));
  if (viewName === 'chat') {
    document.querySelector('[data-view="chat"]')?.classList.add('active');
  } else if (viewName === 'page' && pageKey) {
    document.querySelector(`[data-page="${pageKey}"]`)?.classList.add('active');
  } else {
    document.querySelector(`[data-view="${viewName}"]`)?.classList.add('active');
  }
}

export async function switchView(viewName, opts = {}) {
  closeSidebar();

  // Démonte la vue courante
  try { _currentMod?.unmount?.(); } catch { /* ignore */ }
  viewport.innerHTML = '';
  inputBar.classList.add('hidden');

  // Mise à jour état + UI immédiate (feedback avant import)
  currentView = viewName;
  _updateNavActive(viewName, opts.page);
  viewTitle.textContent = VIEW_TITLES[viewName] ?? opts.label ?? '';

  const loader = VIEW_LOADERS[viewName];
  if (!loader) { console.warn('[ADA core] vue inconnue :', viewName); return; }

  const mod = await loader();
  _currentMod = mod;
  await mod.mount(viewport, opts);
}

// ── Câblage clics nav ───────────────────────────────────────────
navItems.forEach((item) => {
  item.addEventListener('click', () => {
    const view  = item.dataset.view;
    const page  = item.dataset.page || '';
    const hint  = item.dataset.hint || '';
    const label = item.querySelector('span')?.textContent || '';

    if (view === 'page' && page) {
      switchView('page', { page, hint, label });
    } else if (hint) {
      switchView(view, { prefill: hint, label });
    } else {
      switchView(view, { label });
    }
  });
});

// ── Service Worker ──────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ── Auth — permissions nav ───────────────────────────────────────
// Mapping nav-item → menu_tag
function _navItemTag(item) {
  const view = item.dataset.view;
  const page = item.dataset.page;
  if (page) return page;  // home, cad, printers, skills, senses, music, library, infrastructure
  return view;            // dashboard, chat, memory, planner, briefing, webagent, cameras, marketing, settings, auth
}

export function applyPermissions(accessibleTags) {
  if (!accessibleTags) return;
  navItems.forEach(item => {
    const tag = _navItemTag(item);
    item.style.display = accessibleTags.includes(tag) ? '' : 'none';
  });
}

// ── Auth — gate de démarrage ─────────────────────────────────────
async function _authGate() {
  try {
    const cfg = await fetch('/api/auth/config').then(r => r.json());
    if (!cfg.enabled) return; // auth désactivée → tout accès autorisé

    const token = getToken();
    if (!token) { await switchView('auth'); return; }

    const r = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (r.status === 401) {
      clearToken();
      await switchView('auth');
      return;
    }

    if (r.ok) {
      const me = await r.json();
      applyPermissions(me.accessible_tags);
      // Synchronise aussi le cookie pour les requêtes sans header
      document.cookie = `ada_token=${token}; path=/; SameSite=Strict; Max-Age=${30 * 86_400}`;
      // Afficher le bouton logout dans le menu admin
      const logoutBtn = document.getElementById('admin-logout');
      if (logoutBtn) logoutBtn.style.display = '';
    }
  } catch { /* erreur réseau → ne pas bloquer l'app */ }
}

// ── Auth — confirmation QR (appareil authentifié scanne le QR) ──
async function _handleQRConfirm(code) {
  const token = getToken();
  if (!token) return; // non connecté → ne peut pas confirmer

  const modal = document.createElement('div');
  modal.id = 'qr-confirm-modal';
  modal.style.cssText = [
    'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.7)',
    'display:flex;align-items:center;justify-content:center;padding:1.5rem',
  ].join(';');
  modal.innerHTML = `
    <div style="background:#1e2330;border-radius:16px;padding:2rem;max-width:360px;width:100%;
                border:1px solid rgba(123,104,238,.3)">
      <h2 style="color:#c7d2fe;margin:0 0 .5rem;font-size:1.1rem">Nouveau appareil</h2>
      <p style="color:#94a3b8;font-size:.9rem;margin:0 0 1.25rem">
        Un nouvel appareil demande à accéder à ADA.<br>
        Voulez-vous l'autoriser ?
      </p>
      <div style="display:flex;gap:.75rem">
        <button id="qrc-cancel" style="flex:1;padding:.6rem;border:1px solid #374151;border-radius:8px;
                background:transparent;color:#94a3b8;cursor:pointer">Refuser</button>
        <button id="qrc-confirm" style="flex:1;padding:.6rem;border:none;border-radius:8px;
                background:#7b68ee;color:#fff;cursor:pointer">Autoriser</button>
      </div>
    </div>`;
  document.body.appendChild(modal);

  // Clean URL
  history.replaceState({}, '', window.location.pathname);

  document.getElementById('qrc-cancel').onclick = () => modal.remove();
  document.getElementById('qrc-confirm').onclick = async () => {
    const btn = document.getElementById('qrc-confirm');
    if (btn) btn.disabled = true;
    try {
      const r = await fetch('/api/auth/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ code }),
      });
      const data = await r.json();
      if (r.ok) {
        showToast('✅ ' + (data.message || 'Appareil autorisé'));
      } else {
        showToast('Erreur : ' + (data.detail || 'Code invalide'));
      }
    } catch { showToast('Erreur réseau'); }
    modal.remove();
  };
}

// ── Logout ───────────────────────────────────────────────────────
document.getElementById('admin-logout')?.addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  await fetch('/api/auth/logout', { method: 'POST' });
  clearToken();
  location.reload();
});

// ── Démarrage ────────────────────────────────────────────────────
(async () => {
  // 1. Vérifier si un QR de confirmation est dans l'URL
  const urlParams = new URLSearchParams(window.location.search);
  const confirmCode = urlParams.get('confirm');

  // 2. Auth gate
  await _authGate();

  // 3. Si la vue auth a été montée → s'arrêter
  if (currentView === 'auth') return;

  // 4. Visibilité des modules (settings)
  try {
    const cfg = await fetch('/api/settings').then(r => r.json());
    applyModuleVisibility(cfg.modules || {});
  } catch {}

  // 5. Vue initiale
  switchView('dashboard');

  // 6. Confirmation QR (si présente dans l'URL, APRÈS être authentifié)
  if (confirmCode) _handleQRConfirm(confirmCode);
})();
