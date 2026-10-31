/*
 * Interface translation (English, Hindi, Arabic).
 *
 * The pages are written in English. For another language the server sets
 * <html lang dir> and loads /static/ui/i18n/<lang>.js (window.JHA_I18N)
 * before this script. Interface text, placeholders, tooltips and labels are
 * then swapped in place, including text the page scripts add later (a
 * MutationObserver watches for it). Job data, resumes, questions, code and
 * anything the user types are never translated: they are not in the
 * dictionary, and inputs, textareas, code and [data-no-i18n] are skipped.
 *
 * This script also wires every language picker (select[data-lang-picker]):
 * the choice is kept in a cookie the server reads, so the next page is
 * rendered in that language from the first paint.
 */
(function () {
  'use strict';
  const root = document.documentElement;
  const LANGS = ['en', 'hi', 'ar'];
  const LOCALES = { en: 'en-IN', hi: 'hi-IN', ar: 'ar-u-nu-latn' };
  const lang = LANGS.includes(root.lang) ? root.lang : 'en';

  function setLanguage(next) {
    if (!LANGS.includes(next)) return;
    document.cookie = `jha_lang=${next}; path=/; max-age=31536000; samesite=lax`;
    try { localStorage.setItem('jha-lang', next); } catch (_) { /* cookie is enough */ }
    location.reload();
  }

  function wirePickers() {
    document.querySelectorAll('select[data-lang-picker]').forEach((select) => {
      select.value = lang;
      if (select.dataset.wired) return;
      select.dataset.wired = '1';
      select.addEventListener('change', () => setLanguage(select.value));
    });
  }

  window.JHA_LANG = { lang, locale: LOCALES[lang], set: setLanguage, t: (text) => text };
  if (window.UI) window.UI.locale = LOCALES[lang];

  const pack = lang === 'en' ? null : window.JHA_I18N;
  if (!pack) {
    document.addEventListener('DOMContentLoaded', wirePickers);
    return;
  }

  const exact = pack.strings || {};
  const patterns = (pack.patterns || []).map(([source, template]) => [new RegExp(`^${source}$`, 'i'), template]);
  const htmlBlocks = pack.html || {};
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE', 'KBD', 'SAMP', 'NOSCRIPT', 'TEMPLATE']);
  const ATTRIBUTES = ['placeholder', 'title', 'aria-label', 'alt'];

  function translate(text) {
    const key = text.replace(/\s+/g, ' ').trim();
    if (!key || !/[A-Za-z]/.test(key)) return null;
    if (Object.prototype.hasOwnProperty.call(exact, key)) return exact[key];
    for (const [pattern, template] of patterns) {
      const match = key.match(pattern);
      if (match) {
        // $1 = a captured value, translated if it is itself interface text;
        // $L1 = a comma-separated list, each item translated.
        const part = (value) => { const result = value ? translate(value) : null; return result === null ? (value || '') : result; };
        return template.replace(/\$L(\d)|\$(\d)/g, (_, list, index) => (list
          ? (match[Number(list)] || '').split(/,\s*/).map(part).join(pack.listSeparator || ', ')
          : part(match[Number(index)])));
      }
    }
    return null;
  }
  window.JHA_LANG.t = (text) => translate(text) || text;

  function skipped(element) {
    for (let node = element; node && node !== document; node = node.parentElement) {
      if (SKIP.has(node.tagName) || node.isContentEditable || (node.hasAttribute && node.hasAttribute('data-no-i18n'))) return true;
    }
    return false;
  }

  function translateTextNode(node) {
    const value = node.nodeValue;
    const result = translate(value);
    if (result === null || result === value.trim()) return;
    const lead = value.match(/^\s*/)[0];
    const tail = value.match(/\s*$/)[0];
    node.nodeValue = lead + result + tail;
  }

  function translateAttributes(element) {
    for (const name of ATTRIBUTES) {
      const value = element.getAttribute && element.getAttribute(name);
      if (!value) continue;
      const result = translate(value);
      if (result !== null && result !== value) element.setAttribute(name, result);
    }
  }

  function translateTree(start) {
    if (!start) return;
    if (start.nodeType === Node.TEXT_NODE) {
      if (start.parentElement && !skipped(start.parentElement)) translateTextNode(start);
      return;
    }
    if (start.nodeType !== Node.ELEMENT_NODE || skipped(start)) return;
    if (start.dataset && start.dataset.i18n && htmlBlocks[start.dataset.i18n]) {
      // Our own sentences that contain links; the HTML is from the language pack.
      if (start.dataset.i18nDone !== lang) {
        start.innerHTML = htmlBlocks[start.dataset.i18n];
        start.dataset.i18nDone = lang;
      }
      return;
    }
    translateAttributes(start);
    const walker = document.createTreeWalker(start, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.hasAttribute('data-no-i18n') || node.isContentEditable) return NodeFilter.FILTER_REJECT;
          if (SKIP.has(node.tagName)) {
            // A text box keeps what the user typed, but its placeholder and label are interface.
            if (node.tagName !== 'SCRIPT' && node.tagName !== 'STYLE') translateAttributes(node);
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
      else if (node.dataset && node.dataset.i18n && htmlBlocks[node.dataset.i18n]) translateTree(node);
      else translateAttributes(node);
      node = walker.nextNode();
    }
  }

  function translateTitle() {
    const parts = document.title.split(/\s+[·-]\s+/);
    const translated = parts.map((part) => translate(part) || part).join(' · ');
    if (translated !== document.title) document.title = translated;
  }

  let queued = new Set();
  let scheduled = false;
  function flush() {
    scheduled = false;
    const nodes = queued;
    queued = new Set();
    nodes.forEach((node) => { if (node.isConnected) translateTree(node); });
    translateTitle();
  }
  function queue(node) {
    queued.add(node);
    if (!scheduled) { scheduled = true; requestAnimationFrame(flush); }
  }

  function start() {
    translateTree(document.body);
    translateTitle();
    wirePickers();
    new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') queue(mutation.target);
        else if (mutation.type === 'attributes') queue(mutation.target);
        else mutation.addedNodes.forEach(queue);
        if (mutation.target === document.querySelector('title') || (mutation.target.parentNode && mutation.target.parentNode.nodeName === 'TITLE')) queue(document.body);
      }
    }).observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRIBUTES });
  }

  // Dialogs raised by page scripts (confirm/alert) are translated too.
  const nativeConfirm = window.confirm.bind(window);
  const nativeAlert = window.alert.bind(window);
  window.confirm = (message) => nativeConfirm(translate(String(message)) || message);
  window.alert = (message) => nativeAlert(translate(String(message)) || message);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
