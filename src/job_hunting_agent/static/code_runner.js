/*
 * In-browser test runner for mock-interview coding problems.
 *
 * Code runs only in the candidate's own browser, inside a Web Worker (no access
 * to the page, cookies or DOM) with a time limit. Nothing is executed on the
 * server. Python uses Pyodide and SQL uses sql.js (SQLite compiled to
 * WebAssembly); both load from a CDN the first time they are needed.
 */
(function () {
  'use strict';

  var PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
  var SQLJS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/';
  var TIMEOUTS = { javascript: 4000, python: 45000, sql: 20000 };
  var workers = {};

  var JS_WORKER = [
    'self.onmessage = function (event) {',
    '  var data = event.data, results = [], fn;',
    '  try {',
    '    fn = new Function(data.code + "\\n;return (typeof " + data.entry + " !== \\"undefined\\") ? " + data.entry + " : undefined;")();',
    '  } catch (error) { self.postMessage({ fatal: String(error) }); return; }',
    '  if (typeof fn !== "function") { self.postMessage({ fatal: "Function " + data.entry + " was not found. Keep the function name from the starter code." }); return; }',
    '  data.tests.forEach(function (test) {',
    '    try {',
    '      var got = fn.apply(null, JSON.parse(JSON.stringify(test.args)));',
    '      var text = JSON.stringify(got === undefined ? null : got);',
    '      results.push({ ok: text === JSON.stringify(test.expected), got: String(text).slice(0, 300) });',
    '    } catch (error) { results.push({ ok: false, error: String(error).slice(0, 300) }); }',
    '  });',
    '  self.postMessage({ results: results });',
    '};'
  ].join('\n');

  var PY_HARNESS = [
    'import json, copy',
    '__ns = {}',
    'exec(__user_code, __ns)',
    '__fn = __ns.get(__entry)',
    'if not callable(__fn):',
    '    raise NameError(f"Function {__entry} was not found. Keep the function name from the starter code.")',
    '__out = []',
    'for __t in json.loads(__tests_json):',
    '    try:',
    '        __got = __fn(*copy.deepcopy(__t["args"]))',
    '        __text = json.dumps(json.loads(json.dumps(__got, default=str)))',
    '        __out.append({"ok": __text == json.dumps(__t["expected"]), "got": __text[:300]})',
    '    except Exception as __e:',
    '        __out.append({"ok": False, "error": f"{type(__e).__name__}: {__e}"[:300]})',
    'json.dumps(__out)'
  ].join('\n');

  var PY_WORKER = [
    'importScripts("' + PYODIDE_URL + 'pyodide.js");',
    'var pyodideReady = null;',
    'self.onmessage = async function (event) {',
    '  try {',
    '    if (!pyodideReady) pyodideReady = loadPyodide({ indexURL: "' + PYODIDE_URL + '" });',
    '    var py = await pyodideReady;',
    '    py.globals.set("__user_code", event.data.code);',
    '    py.globals.set("__tests_json", JSON.stringify(event.data.tests));',
    '    py.globals.set("__entry", event.data.entry);',
    '    var out = await py.runPythonAsync(event.data.harness);',
    '    self.postMessage({ results: JSON.parse(out) });',
    '  } catch (error) { self.postMessage({ fatal: String(error).split("\\n").slice(-3).join(" ").slice(0, 400) }); }',
    '};'
  ].join('\n');

  var SQL_WORKER = [
    'importScripts("' + SQLJS_URL + 'sql-wasm.js");',
    'var sqlReady = null;',
    'self.onmessage = async function (event) {',
    '  try {',
    '    if (!sqlReady) sqlReady = initSqlJs({ locateFile: function (file) { return "' + SQLJS_URL + '" + file; } });',
    '    var SQL = await sqlReady, db = new SQL.Database();',
    '    db.run(event.data.setup);',
    '    var result = db.exec(event.data.code);',
    '    var rows = result.length ? result[result.length - 1].values : [];',
    '    var expected = event.data.expected;',
    '    var key = function (list) { return list.map(function (row) { return JSON.stringify(row); }); };',
    '    var got = key(rows), want = key(expected);',
    '    if (!event.data.ordered) { got.sort(); want.sort(); }',
    '    self.postMessage({ results: [{ ok: JSON.stringify(got) === JSON.stringify(want), got: JSON.stringify(rows).slice(0, 400) }] });',
    '  } catch (error) { self.postMessage({ fatal: String(error).slice(0, 400) }); }',
    '};'
  ].join('\n');

  function workerFor(language) {
    if (workers[language]) return workers[language];
    var source = language === 'python' ? PY_WORKER : language === 'sql' ? SQL_WORKER : JS_WORKER;
    var url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
    workers[language] = new Worker(url);
    return workers[language];
  }

  function reset(language) {
    if (workers[language]) workers[language].terminate();
    delete workers[language];
  }

  function run(problem, code) {
    var language = problem.language;
    if (['python', 'javascript', 'sql'].indexOf(language) < 0) {
      return Promise.resolve({ unsupported: true, language: language });
    }
    if (language !== 'sql' && !/^[A-Za-z_$][\w$]*$/.test(problem.entry || '')) {
      return Promise.resolve({ fatal: 'This problem has no runnable entry point.' });
    }
    var worker = workerFor(language);
    return new Promise(function (resolve) {
      var timer = setTimeout(function () {
        reset(language);
        resolve({ fatal: 'Time limit exceeded. Check for an infinite loop or a very slow approach.', timeout: true });
      }, TIMEOUTS[language]);
      worker.onmessage = function (event) {
        clearTimeout(timer);
        var data = event.data || {};
        if (data.fatal) { resolve({ fatal: data.fatal, language: language }); return; }
        var results = data.results || [];
        resolve({
          language: language,
          results: results,
          passed: results.filter(function (item) { return item.ok; }).length,
          total: results.length
        });
      };
      worker.onerror = function (event) {
        clearTimeout(timer);
        reset(language);
        resolve({ fatal: (event && event.message) || 'The runner could not start. Check your internet connection.' });
      };
      if (language === 'sql') {
        worker.postMessage({ code: code, setup: problem.setup, expected: problem.expected_rows, ordered: problem.ordered !== false });
      } else if (language === 'python') {
        worker.postMessage({ code: code, entry: problem.entry, tests: problem.tests, harness: PY_HARNESS });
      } else {
        worker.postMessage({ code: code, entry: problem.entry, tests: problem.tests });
      }
    });
  }

  window.CodeRunner = { run: run, reset: reset };
})();
