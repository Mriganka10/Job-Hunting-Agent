/* Shared app shell: theme, mobile navigation, toasts and small helpers. */
(function () {
  'use strict';
  const root = document.documentElement;
  const THEME_KEY = 'jha-theme';

  function storedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (_) { return null; }
  }
  function saveTheme(value) {
    try { localStorage.setItem(THEME_KEY, value); } catch (_) { /* private mode: keep the in-memory choice */ }
  }
  function applyTheme(value) {
    root.setAttribute('data-theme', value === 'light' ? 'light' : 'dark');
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const light = value === 'light';
      button.setAttribute('aria-pressed', String(light));
      button.setAttribute('aria-label', light ? 'Switch to dark theme' : 'Switch to light theme');
      button.title = light ? 'Dark theme' : 'Light theme';
    });
  }
  applyTheme(storedTheme() || 'dark');

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));
  }

  async function payloadOf(response) {
    const type = response.headers.get('content-type') || '';
    if (type.includes('application/json')) return response.json();
    const text = (await response.text()).trim();
    return { detail: text || `Request failed with status ${response.status}.` };
  }

  async function api(url, options) {
    const init = Object.assign({}, options || {});
    if (init.body && typeof init.body !== 'string' && !(init.body instanceof FormData) && !(init.body instanceof Blob)) {
      init.body = JSON.stringify(init.body);
    }
    if (typeof init.body === 'string') init.headers = Object.assign({ 'Content-Type': 'application/json' }, init.headers || {});
    const response = await fetch(url, init);
    const data = await payloadOf(response);
    if (!response.ok) {
      const error = new Error(data.detail || 'Request failed.');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  let toastHost = null;
  function toast(message, kind, timeout) {
    if (!toastHost) {
      toastHost = document.createElement('div');
      toastHost.className = 'toasts';
      toastHost.setAttribute('role', 'status');
      toastHost.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastHost);
    }
    const node = document.createElement('div');
    node.className = `toast ${kind || ''}`;
    const text = document.createElement('span');
    text.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn btn-quiet btn-sm';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '×';
    close.style.marginLeft = 'auto';
    close.addEventListener('click', () => node.remove());
    node.append(text, close);
    toastHost.appendChild(node);
    setTimeout(() => node.remove(), timeout || (kind === 'bad' ? 8000 : 4500));
  }

  function setupNav() {
    const sidebar = document.querySelector('.sidebar');
    const menu = document.getElementById('menu-button');
    if (!sidebar || !menu) return;
    let scrim = null;
    const close = () => {
      sidebar.classList.remove('open');
      menu.setAttribute('aria-expanded', 'false');
      if (scrim) { scrim.remove(); scrim = null; }
    };
    menu.addEventListener('click', () => {
      if (sidebar.classList.contains('open')) { close(); return; }
      sidebar.classList.add('open');
      menu.setAttribute('aria-expanded', 'true');
      scrim = document.createElement('div');
      scrim.className = 'scrim';
      scrim.addEventListener('click', close);
      document.body.appendChild(scrim);
      const first = sidebar.querySelector('a, button');
      if (first) first.focus();
    });
    sidebar.addEventListener('click', (event) => { if (event.target.closest('a')) close(); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && sidebar.classList.contains('open')) { close(); menu.focus(); } });
  }

  function markCurrent() {
    const here = location.pathname + (location.pathname === '/' ? (location.hash || '#overview') : '');
    document.querySelectorAll('.nav-link').forEach((link) => {
      const url = new URL(link.href, location.href);
      const target = url.pathname + (url.pathname === '/' ? (url.hash || '#overview') : '');
      if (target === here) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }

  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-theme-toggle]');
    if (!toggle) return;
    const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    applyTheme(next);
    saveTheme(next);
  });
  window.addEventListener('hashchange', markCurrent);
  document.addEventListener('DOMContentLoaded', () => { applyTheme(root.getAttribute('data-theme')); setupNav(); markCurrent(); });

  window.UI = { escape: escapeHtml, api, payloadOf, toast, markCurrent, locale: (window.JHA_LANG && window.JHA_LANG.locale) || undefined };
})();
