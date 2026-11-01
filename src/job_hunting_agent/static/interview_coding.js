/*
 * Mock-interview coding problems: shows the problem, pre-fills starter code,
 * runs the sample tests in the browser (code_runner.js) and adds the model
 * solution and a feedback rating to the scorecard.
 */
(function () {
  'use strict';

  var current = null;
  var resultsByQuestion = {};
  var panel = null;

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function injectStyles() {
    if (document.getElementById('interview-coding-styles')) return;
    var style = el('style', { id: 'interview-coding-styles' });
    style.textContent = [
      '.run-panel{margin:10px 0 0;padding:10px;border:1px solid rgba(148,163,184,.3);border-radius:8px;background:rgba(2,6,23,.55)}',
      '.run-panel .run-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}',
      '.run-panel ul{margin:8px 0 0;padding-left:18px;font-size:12px;line-height:1.5}',
      '.run-panel li.ok{color:#86efac}.run-panel li.fail{color:#fca5a5}',
      '.run-status{font-size:12px;color:#cbd5e1}',
      '.problem-meta{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px}',
      '.problem-meta span{padding:2px 8px;border-radius:999px;background:rgba(37,99,235,.2);color:#bfdbfe;font-size:11px;font-weight:800}',
      '.model-solution{margin:8px 0 0;max-height:260px;overflow:auto;padding:10px;border:1px solid rgba(148,163,184,.25);border-radius:6px;background:#050b16;color:#bbf7d0;font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;white-space:pre}',
      '.rating-box{margin-top:22px;padding-top:16px;border-top:1px solid rgba(148,163,184,.25)}',
      '.rating-box .stars{display:flex;gap:6px;margin:8px 0}',
      '.rating-box .stars button{min-height:36px;min-width:42px;background:#1f2937;color:#fde68a;border-radius:7px}',
      '.rating-box .stars button[aria-pressed=true]{background:#f59e0b;color:#111827}'
    ].join('');
    document.head.appendChild(style);
  }

  function ensurePanel() {
    if (panel) return panel;
    injectStyles();
    var host = document.getElementById('code-answer');
    if (!host) return null;
    panel = el('div', { class: 'run-panel hidden', id: 'run-panel' });
    var row = el('div', { class: 'run-row' });
    var button = el('button', { type: 'button', class: 'ghost', id: 'run-tests' }, 'Run sample tests');
    var reset = el('button', { type: 'button', class: 'dark', id: 'reset-starter' }, 'Reset starter code');
    var status = el('span', { class: 'run-status', id: 'run-status', role: 'status', 'aria-live': 'polite' });
    var list = el('ul', { id: 'run-results' });
    row.appendChild(button);
    row.appendChild(reset);
    row.appendChild(status);
    panel.appendChild(row);
    panel.appendChild(list);
    host.appendChild(panel);
    button.addEventListener('click', runTests);
    reset.addEventListener('click', function () {
      if (!current) return;
      document.getElementById('code-editor').value = current.coding.starter_code || '';
    });
    return panel;
  }

  function describeProblem(problem) {
    var lines = [problem.title + ' (' + problem.difficulty + ')', '', problem.statement, ''];
    (problem.examples || []).forEach(function (example, index) {
      lines.push('Example ' + (index + 1) + ':');
      lines.push('  Input:  ' + example.input);
      lines.push('  Output: ' + example.output);
      if (example.explanation) lines.push('  Why:    ' + example.explanation);
    });
    if ((problem.constraints || []).length) {
      lines.push('', 'Constraints:');
      problem.constraints.forEach(function (item) { lines.push('  - ' + item); });
    }
    if (problem.language === 'sql') {
      lines.push('', 'Sample data used by the test:', problem.setup);
    }
    lines.push('', problem.runnable
      ? 'Write your solution, press "Run sample tests", then Submit. ' + problem.complexity_hint
      : 'This language is reviewed without running. Explain your approach in comments. ' + problem.complexity_hint);
    return lines.join('\n');
  }

  function render(item) {
    var box = ensurePanel();
    var editor = document.getElementById('code-editor');
    var codeBox = document.getElementById('code-box');
    current = item && item.coding ? item : null;
    if (!box) return;
    box.classList.toggle('hidden', !current);
    document.getElementById('run-results').innerHTML = '';
    document.getElementById('run-status').textContent = '';
    if (!current) return;
    codeBox.textContent = describeProblem(current.coding);
    if (!editor.value.trim()) editor.value = current.coding.starter_code || '';
    var button = document.getElementById('run-tests');
    button.disabled = !current.coding.runnable;
    button.textContent = current.coding.runnable ? 'Run sample tests' : 'Tests run for Python, JavaScript and SQL only';
  }

  function runTests() {
    if (!current || !window.CodeRunner) return;
    var problem = current.coding;
    var code = document.getElementById('code-editor').value;
    var status = document.getElementById('run-status');
    var list = document.getElementById('run-results');
    var button = document.getElementById('run-tests');
    var questionId = current.id;
    button.disabled = true;
    list.innerHTML = '';
    status.textContent = problem.language === 'python' ? 'Starting Python (first run downloads about 10 MB)...' : 'Running tests...';
    window.CodeRunner.run(problem, code).then(function (outcome) {
      button.disabled = false;
      if (outcome.unsupported) { status.textContent = 'Tests are not available for this language.'; return; }
      if (outcome.fatal) {
        status.textContent = 'Could not run: ' + outcome.fatal;
        resultsByQuestion[questionId] = { passed: 0, total: problem.language === 'sql' ? 1 : (problem.tests || []).length, language: problem.language };
        return;
      }
      resultsByQuestion[questionId] = { passed: outcome.passed, total: outcome.total, language: outcome.language };
      status.textContent = outcome.passed + ' of ' + outcome.total + ' tests passed';
      outcome.results.forEach(function (result, index) {
        var test = (problem.tests || [])[index];
        var label = problem.language === 'sql'
          ? (result.ok ? 'Query result matches' : 'Query result differs: got ' + (result.got || ''))
          : 'Test ' + (index + 1) + ': ' + (result.ok ? 'passed' : (result.error || ('expected ' + JSON.stringify(test.expected) + ', got ' + result.got)));
        list.appendChild(el('li', { class: result.ok ? 'ok' : 'fail' }, label));
      });
    });
  }

  function results(questionId) {
    return resultsByQuestion[questionId] || null;
  }

  function reviewHtml(item, escapeHtml) {
    var parts = [];
    if (item.test_results) {
      parts.push('<p class="muted">Sample tests (run in your browser): ' + escapeHtml(item.test_results.passed) + ' of ' + escapeHtml(item.test_results.total) + ' passed.</p>');
    }
    if (item.answer_type === 'code' && item.answer) {
      parts.push('<p class="muted"><strong>Your code</strong></p><pre class="transcript-code"><code>' + escapeHtml(item.answer) + '</code></pre>');
    }
    if (item.model_solution) {
      parts.push('<p class="muted"><strong>One model solution</strong> (compare the approach, not the exact code)</p><pre class="model-solution">' + escapeHtml(item.model_solution) + '</pre>');
    }
    return parts.join('');
  }

  function renderRating(container, sessionId) {
    injectStyles();
    var box = el('section', { class: 'rating-box' });
    box.appendChild(el('h3', {}, 'Was this feedback useful?'));
    var stars = el('div', { class: 'stars', role: 'group', 'aria-label': 'Rate the feedback from 1 to 5' });
    var unfairLabel = el('label', {});
    var unfair = el('input', { type: 'checkbox', id: 'feedback-unfair' });
    unfairLabel.appendChild(unfair);
    unfairLabel.appendChild(document.createTextNode(' The score or feedback seems unfair'));
    var comment = el('textarea', { id: 'feedback-comment', rows: '2', placeholder: 'Optional: what was wrong or missing?', style: 'min-height:60px' });
    var status = el('p', { class: 'muted', role: 'status' });
    for (var value = 1; value <= 5; value += 1) {
      (function (rating) {
        var button = el('button', { type: 'button', 'aria-pressed': 'false', 'data-rating': String(rating) }, rating + '★');
        button.addEventListener('click', function () {
          stars.querySelectorAll('button').forEach(function (node) { node.setAttribute('aria-pressed', String(Number(node.dataset.rating) <= rating)); });
          fetch('/api/mock-interview/' + encodeURIComponent(sessionId) + '/rating', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating: rating, unfair: unfair.checked, comment: comment.value })
          }).then(function (response) {
            status.textContent = response.ok ? 'Thanks - your rating helps us improve the evaluator.' : 'Could not save your rating.';
          });
        });
        stars.appendChild(button);
      })(value);
    }
    box.appendChild(stars);
    box.appendChild(unfairLabel);
    box.appendChild(comment);
    box.appendChild(status);
    container.appendChild(box);
  }

  window.InterviewCoding = { render: render, results: results, reviewHtml: reviewHtml, renderRating: renderRating };
})();
