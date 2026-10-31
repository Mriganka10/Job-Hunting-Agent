"""Shared app shell plus the progress, privacy and admin metrics pages.

Every signed-in page uses ``app_shell``: one sidebar, one top bar, one design
system (``/static/ui/app.css``) and one helper script (``/static/ui/shell.js``).
Pages are static HTML plus a small script that calls the JSON APIs;
user-controlled values are always inserted escaped, never as raw HTML.
"""

from __future__ import annotations

from html import escape

ASSET_VERSION = "20261031b"
# Devanagari and Arabic faces are loaded by unicode-range, so English pages
# download only the Latin files.
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800"
    "&family=Public+Sans:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600;700"
    "&family=Noto+Sans+Arabic:wght@400;500;600;700&display=swap"
)

# code: (name shown in the picker, text direction)
LANGUAGES = {"en": ("English", "ltr"), "hi": ("हिन्दी", "ltr"), "ar": ("العربية", "rtl")}


def normalize_lang(value: str | None) -> str:
    value = (value or "").strip().lower()
    return value if value in LANGUAGES else "en"


def language_picker(extra_class: str = "") -> str:
    """The language menu. i18n.js selects the current language and saves a change."""
    options = "".join(f'<option value="{code}" lang="{code}">{name}</option>' for code, (name, _) in LANGUAGES.items())
    return (
        f'<label class="lang-picker {extra_class}"><span class="sr-only">Language</span>'
        f'<select data-lang-picker aria-label="Language">{options}</select></label>'
    )


def localize_document(html: str, lang: str) -> str:
    """Set <html lang dir> and load the language pack and translator.

    Works on every page (dashboard, auth, reports and the practice studios),
    so the page builders stay language-neutral.
    """
    lang = normalize_lang(lang)
    direction = LANGUAGES[lang][1]
    html = __import__("re").sub(r"<html lang=\"en\"", f'<html lang="{lang}" dir="{direction}"', html, count=1)
    pack = f'<script src="/static/ui/i18n/{lang}.js?v={ASSET_VERSION}"></script>' if lang != "en" else ""
    tags = f'{pack}<script src="/static/ui/i18n.js?v={ASSET_VERSION}"></script>'
    head_end = html.find("</head>")
    return html[:head_end] + tags + html[head_end:] if head_end != -1 else tags + html

# Simple 24px stroke icons, drawn for this app.
_ICONS = {
    "overview": '<path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 4v4h6V4z"/>',
    "run": '<circle cx="12" cy="12" r="8"/><path d="M10 8.5v7l5.5-3.5z"/>',
    "jobs": '<rect x="3.5" y="7" width="17" height="12" rx="2"/><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3.5 12.5h17"/>',
    "resume": '<path d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10A.5.5 0 0 1 7 20z" transform="translate(-1 0)"/><path d="M9 12h6M9 15.5h6M13 3.5v4h4"/>',
    "approvals": '<path d="M4 6.5h16v11H4z"/><path d="m4.5 7 7.5 6 7.5-6"/>',
    "test": '<path d="M8 4h8M9 4v5l-4.5 8.5A1.5 1.5 0 0 0 5.8 20h12.4a1.5 1.5 0 0 0 1.3-2.5L15 9V4"/><path d="M7.5 14h9"/>',
    "interview": '<path d="M12 4a3 3 0 0 1 3 3v4a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z"/><path d="M6 11a6 6 0 0 0 12 0M12 17v3M9 20h6"/>',
    "progress": '<path d="M4 19h16"/><path d="m5 15 4-4 3 3 6-7"/><path d="M15 7h3v3"/>',
    "privacy": '<path d="M12 3.5 5 6v5.5c0 4.2 3 7.5 7 9 4-1.5 7-4.8 7-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "admin": '<path d="M5 19V11M10 19V5M15 19v-6M20 19V8"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "theme": '<path d="M12 4a8 8 0 1 0 8 8 6 6 0 0 1-8-8z"/>',
    "out": '<path d="M14 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h9"/>',
}


def icon(name: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICONS[name]}</svg>'
    )


def _nav_link(href: str, label: str, icon_name: str, active: str, key: str, extra: str = "") -> str:
    current = ' aria-current="page"' if active == key else ""
    return f'<a class="nav-link" href="{href}"{current}>{icon(icon_name)}<span>{label}</span>{extra}</a>'


def head(title: str) -> str:
    """Document head shared by every page; the theme is applied before paint."""
    return (
        '<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="dark light">'
        f"<title>{escape(title)} · Job Hunting Agent</title>"
        "<script>try{var t=localStorage.getItem('jha-theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>"
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{FONTS_URL}">'
        f'<link rel="stylesheet" href="/static/ui/app.css?v={ASSET_VERSION}">'
    )


def app_shell(
    title: str,
    user_email: str,
    body: str,
    *,
    active: str = "",
    script: str = "",
    scripts: tuple[str, ...] = (),
    is_admin: bool = False,
    actions: str = "",
    extra_head: str = "",
) -> str:
    """The signed-in layout: sidebar navigation, top bar and page content."""
    signed_in = bool(user_email)
    if signed_in:
        workspace = "".join([
            _nav_link("/#overview", "Overview", "overview", active, "overview"),
            _nav_link("/#run", "Run &amp; profile", "run", active, "run"),
            _nav_link("/#jobs", "Job leads", "jobs", active, "jobs", '<span class="nav-count hidden" id="nav-jobs-count"></span>'),
            _nav_link("/#resume", "Resume &amp; ATS", "resume", active, "resume"),
            _nav_link("/#approvals", "Approvals", "approvals", active, "approvals", '<span class="nav-count attention hidden" id="nav-approvals-count"></span>'),
        ])
        practice = "".join([
            _nav_link("/mock-test", "Mock Test", "test", active, "mock-test"),
            _nav_link("/mock-interview", "Mock Interview", "interview", active, "mock-interview"),
            _nav_link("/progress", "Progress reports", "progress", active, "progress"),
        ])
        account = _nav_link("/privacy", "Privacy &amp; my data", "privacy", active, "privacy")
        if is_admin:
            account += _nav_link("/admin/metrics", "Admin metrics", "admin", active, "admin")
        initial = escape((user_email[:1] or "?").upper())
        foot = (
            f'<div class="user-line"><span class="avatar" aria-hidden="true">{initial}</span><span>Signed in as {escape(user_email)}</span></div>'
            '<form method="post" action="/api/auth/logout"><button class="btn btn-quiet" type="submit" style="width:100%;justify-content:flex-start">'
            f'{icon("out")}Sign out</button></form>'
        )
        nav = (
            f'<nav class="nav-group" aria-label="Workspace"><span class="nav-heading">Workspace</span>{workspace}</nav>'
            f'<nav class="nav-group" aria-label="Practice"><span class="nav-heading">Practice</span>{practice}</nav>'
            f'<nav class="nav-group" aria-label="Account"><span class="nav-heading">Account</span>{account}</nav>'
        )
    else:
        nav = (
            '<nav class="nav-group" aria-label="Account">'
            + _nav_link("/privacy", "Privacy &amp; my data", "privacy", active, "privacy")
            + '<a class="nav-link" href="/login">' + icon("out") + "<span>Sign in</span></a></nav>"
        )
        foot = ""
    script_tags = "".join(f'<script src="{src}?v={ASSET_VERSION}" defer></script>' for src in scripts)
    return (
        head(title) + extra_head + "</head>"
        '<body class="ux"><a class="skip-link" href="#content">Skip to content</a>'
        '<div class="shell">'
        '<aside class="sidebar" id="sidebar" aria-label="Main navigation">'
        '<a class="brand" href="/"><span class="brand-mark" aria-hidden="true">J</span>'
        "<span>Job Hunting Agent<small>Resume to offer</small></span></a>"
        f'{nav}<div class="sidebar-foot">{foot}</div></aside>'
        '<div class="main"><header class="topbar">'
        f'<button class="btn btn-icon menu-button" id="menu-button" type="button" aria-controls="sidebar" aria-expanded="false" aria-label="Open navigation">{icon("menu")}</button>'
        f'<h1 class="topbar-title" id="page-title">{escape(title)}</h1>'
        f'<div class="topbar-actions">{actions}{language_picker()}'
        f'<button class="btn btn-icon btn-quiet" type="button" data-theme-toggle aria-label="Switch to light theme">{icon("theme")}</button></div>'
        '</header>'
        f'<main class="content" id="content" tabindex="-1">{body}</main></div></div>'
        f'<script src="/static/ui/shell.js?v={ASSET_VERSION}"></script>{script_tags}'
        + (f"<script>{script}</script>" if script else "")
        + "</body></html>"
    )


def practice_nav(active: str, user_email: str) -> str:
    """Compact top navigation for the full-screen practice studios."""
    links = [("/", "Dashboard", ""), ("/#jobs", "Job leads", ""), ("/mock-test", "Mock Test", "mock-test"),
             ("/mock-interview", "Mock Interview", "mock-interview"), ("/progress", "Progress reports", "progress")]
    current = ' aria-current="page"'
    items = "".join(
        f'<a href="{href}"{current if key and key == active else ""}>{label}</a>' for href, label, key in links
    )
    return (
        f'<link rel="stylesheet" href="{FONTS_URL}">'
        f'<link rel="stylesheet" href="/static/ui/app.css?v={ASSET_VERSION}">'
        '<nav class="ux-nav" aria-label="Main navigation">'
        '<a class="ux-nav-brand" href="/"><b aria-hidden="true">J</b>Job Hunting Agent</a>'
        f'{items}<span class="ux-nav-end">{language_picker("ux-nav-lang")}<span style="color:#a3b1d6;font-weight:500">Signed in as {escape(user_email)}</span>'
        '<form method="post" action="/api/auth/logout"><button type="submit">Sign out</button></form></span></nav>'
    )


# Styles for the report pages that the design system does not already cover.
_PAGE_STYLE = r"""<style>
  .ux .kpis { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:0; border:1px solid var(--line); border-radius:var(--r-lg); background:var(--panel); overflow:hidden; }
  .ux .kpi { padding:16px 18px; border-left:1px solid var(--line); min-width:0; }
  .ux .kpi:first-child { border-left:0; }
  .ux .kpi > span { color:var(--muted); font-size:13px; }
  .ux .kpi strong { display:block; margin-top:6px; font:800 26px/1.1 var(--display); }
  .ux .kpi small { display:block; margin-top:6px; color:var(--muted); font-size:12px; }
  .ux .up { color:var(--good); } .ux .down { color:var(--bad); }
  .ux .two { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:16px; }
  .ux .controls { display:flex; gap:14px; flex-wrap:wrap; align-items:end; }
  .ux .control-label { display:block; font-size:13px; font-weight:600; color:var(--muted); margin-bottom:6px; }
  .ux .chart { width:100%; height:220px; }
  .ux .chart text { fill:var(--muted); font-size:10px; }
  .ux .legend { display:flex; gap:14px; font-size:13px; color:var(--muted); margin-top:8px; }
  .ux .legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:-1px; }
  .ux ul.steps { margin:6px 0 0; padding-left:20px; }
  .ux ul.steps li { margin:6px 0; }
  .ux .bar { min-width:80px; }
  .ux .panel h2 { margin-bottom:12px; font-size:18px; }
  .ux .kpi strong { font-size:24px; }
  .ux .panel table td, .ux .panel table th { padding:8px 10px; }
  .ux .metric-card { overflow-wrap:anywhere; overflow-x:auto; }
  .ux .metric-card table { font-size:13px; }
  .ux .metric-card table table { margin:2px 0; }
  @media (max-width: 1080px) { .ux .kpis { grid-template-columns:repeat(3, minmax(0,1fr)); } .ux .kpi:nth-child(4) { border-left:0; } .ux .kpi:nth-child(n+4) { border-top:1px solid var(--line); } }
  @media (max-width: 860px) { .ux .two { grid-template-columns:1fr; } }
  @media (max-width: 560px) { .ux .kpis { grid-template-columns:1fr 1fr; } .ux .kpi { border-left:0; border-top:1px solid var(--line); } .ux .kpi:nth-child(even) { border-left:1px solid var(--line); } .ux .kpi:first-child, .ux .kpi:nth-child(2) { border-top:0; } }
</style>"""


_ESCAPE_JS = r"""
    const escapeHtml = UI.escape;
    const api = UI.api;
"""


# ---------------------------------------------------------------------------
# Progress reports
# ---------------------------------------------------------------------------
_PROGRESS_BODY = r"""
  <section>
    <p class="muted" style="max-width:68ch">Daily and weekly trends for your mock tests and mock interviews, for all practice or one job.</p>
    <div class="controls" style="margin-top:14px">
      <div><span class="control-label" id="period-label">Period</span>
        <div class="segmented" id="period" role="group" aria-labelledby="period-label"><button type="button" data-period="daily" aria-pressed="false">Daily (14 days)</button><button type="button" data-period="weekly" aria-pressed="true">Weekly (8 weeks)</button></div></div>
      <label style="min-width:260px"><span class="control-label">Job</span><select id="job"><option value="">All practice</option></select></label>
      <span class="muted" id="status" role="status"></span>
    </div>
  </section>
  <section class="kpis" id="kpis" aria-label="Summary"></section>
  <section class="panel" id="next-steps"><h2>What to do next</h2><ul class="steps" id="steps"></ul></section>
  <section class="two">
    <div class="panel"><h2>Mock Test scores</h2><div id="test-chart"></div><div class="legend"><span><i style="background:var(--info)"></i>Attempts</span><span><i style="background:var(--good)"></i>Average score %</span></div></div>
    <div class="panel"><h2>Mock Interview scores</h2><div id="interview-chart"></div><div class="legend"><span><i style="background:var(--info)"></i>Sessions</span><span><i style="background:var(--accent)"></i>Average score</span></div></div>
  </section>
  <section class="two">
    <div class="panel"><h2>Topic accuracy (Mock Test)</h2><div id="topics"></div></div>
    <div class="panel"><h2>Interview skills</h2><div id="dimensions"></div></div>
  </section>
  <section class="two">
    <div class="panel"><h2>By difficulty and coding</h2><div id="difficulty"></div></div>
    <div class="panel"><h2>Interview question types</h2><div id="categories"></div></div>
  </section>
  <section class="two">
    <div class="panel"><h2>Recent tests</h2><div id="recent-tests"></div></div>
    <div class="panel"><h2>Recent interviews</h2><div id="recent-interviews"></div></div>
  </section>
"""

_PROGRESS_SCRIPT = _ESCAPE_JS + r"""
    const state = { period: 'weekly', job: new URLSearchParams(location.search).get('job') || '', jobsLoaded: false };
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';
    function change(value, unit) {
      if (value === null || value === undefined) return '<small>No earlier data to compare</small>';
      const cls = value > 0 ? 'up' : value < 0 ? 'down' : '';
      return `<small class="${cls}">${value > 0 ? '+' : ''}${escapeHtml(value)}${unit} vs previous period</small>`;
    }
    function kpi(label, value, extra) {
      return `<div class="kpi"><span>${escapeHtml(label)}</span><strong>${value === null || value === undefined ? '-' : escapeHtml(value)}</strong>${extra || ''}</div>`;
    }
    function chart(buckets, countKey, valueKey, color, max) {
      if (!buckets.length) return '<p class="muted">No data yet.</p>';
      const width = 560, height = 210, pad = 28, n = buckets.length, slot = (width - pad * 2) / n;
      const maxCount = Math.max(1, ...buckets.map((b) => b[countKey] || 0));
      let bars = '', points = [], labels = '';
      buckets.forEach((b, i) => {
        const x = pad + i * slot;
        const h = ((b[countKey] || 0) / maxCount) * (height - pad * 2) * 0.55;
        bars += `<rect x="${x + slot * 0.2}" y="${height - pad - h}" width="${slot * 0.6}" height="${h}" rx="2" fill="var(--info)" opacity=".4"><title>${escapeHtml(b.label)}: ${b[countKey] || 0}</title></rect>`;
        if (b[valueKey] !== null && b[valueKey] !== undefined) {
          const y = height - pad - (Math.min(max, b[valueKey]) / max) * (height - pad * 2);
          points.push([x + slot / 2, y, b[valueKey], b.label]);
        }
        if (n <= 8 || i % 2 === 0) labels += `<text x="${x + slot / 2}" y="${height - 8}" text-anchor="middle">${escapeHtml(b.label.replace('Week of ', ''))}</text>`;
      });
      const line = points.length > 1 ? `<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${points.map((p) => p[0] + ',' + p[1]).join(' ')}"/>` : '';
      const dots = points.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="${color}"><title>${escapeHtml(p[3])}: ${escapeHtml(p[2])}</title></circle>`).join('');
      const grid = [0, 50, 100].map((v) => { const y = height - pad - (v / 100) * (height - pad * 2) * (100 / max); return `<line x1="${pad}" x2="${width - pad}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="4" y="${y + 3}">${v}</text>`; }).join('');
      return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Score trend">${grid}${bars}${line}${dots}${labels}</svg>`;
    }
    function bar(percent, status) {
      return `<div class="bar"><i class="${escapeHtml(status || '')}" style="width:${Math.max(0, Math.min(100, Number(percent) || 0))}%"></i></div>`;
    }
    function render(report) {
      const t = report.mock_test, iv = report.mock_interview;
      document.getElementById('kpis').innerHTML = [
        kpi('Readiness index', report.readiness_index === null ? '-' : report.readiness_index + '/100', `<small>${escapeHtml(report.readiness_label || 'Practise to see your readiness')}</small>`),
        kpi('Practice streak', report.streak_days + (report.streak_days === 1 ? ' day' : ' days'), `<small>${escapeHtml(report.practice_days_in_window)} practice days in this window</small>`),
        kpi('Mock Test average', t.summary.avg_percent === null ? '-' : t.summary.avg_percent + '%', change(t.summary.change, ' pts')),
        kpi('Interview average', iv.summary.avg_score === null ? '-' : iv.summary.avg_score + '/100', change(iv.summary.change, ' pts')),
        kpi('Completed', `${t.summary.completed} tests, ${iv.summary.completed} interviews`, `<small>Completion: tests ${t.summary.completion_rate === null ? '-' : Math.round(t.summary.completion_rate * 100) + '%'}, interviews ${iv.summary.completion_rate === null ? '-' : Math.round(iv.summary.completion_rate * 100) + '%'}</small>`),
      ].join('');
      document.getElementById('steps').innerHTML = report.next_steps.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
      document.getElementById('test-chart').innerHTML = chart(t.buckets, 'attempts', 'avg_percent', 'var(--good)', 100);
      document.getElementById('interview-chart').innerHTML = chart(iv.buckets, 'sessions', 'avg_score', 'var(--accent)', 100);
      document.getElementById('topics').innerHTML = t.topics.length ? `<table><thead><tr><th>Topic</th><th>Accuracy</th><th></th><th>Change</th></tr></thead><tbody>${t.topics.map((row) => `<tr><td>${escapeHtml(row.label)}<br><span class="faint">${escapeHtml(row.correct)}/${escapeHtml(row.answered)} correct</span></td><td>${escapeHtml(row.percent)}%</td><td>${bar(row.percent, row.status)}</td><td class="${row.change > 0 ? 'up' : row.change < 0 ? 'down' : ''}">${row.change === null ? '-' : (row.change > 0 ? '+' : '') + row.change}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">Complete a mock test to see topic accuracy.</p>';
      document.getElementById('dimensions').innerHTML = iv.dimensions.some((row) => row.avg !== null) ? `<table><tbody>${iv.dimensions.map((row) => `<tr><td>${escapeHtml(row.name)}</td><td>${row.avg === null ? '-' : escapeHtml(row.avg)}</td><td>${bar(row.avg, row.avg >= 75 ? 'strong' : row.avg >= 55 ? 'developing' : 'weak')}</td><td class="${row.change > 0 ? 'up' : row.change < 0 ? 'down' : ''}">${row.change === null ? '-' : (row.change > 0 ? '+' : '') + row.change}</td></tr>`).join('')}</tbody></table>${iv.coding.answers ? `<p class="muted">Coding answers: ${escapeHtml(iv.coding.answers)}, average ${escapeHtml(iv.coding.avg_score)}/100</p>` : ''}` : '<p class="muted">Complete a mock interview to see skill scores.</p>';
      document.getElementById('difficulty').innerHTML = t.difficulty.length ? `<table><tbody>${t.difficulty.map((row) => `<tr><td style="text-transform:capitalize">${escapeHtml(row.difficulty)}</td><td>${row.percent === null ? '-' : escapeHtml(row.percent) + '%'}</td><td>${bar(row.percent)}</td><td class="faint">${escapeHtml(row.answered)} answered</td></tr>`).join('')}${t.coding.questions ? `<tr><td>Code questions</td><td>${escapeHtml(t.coding.percent)}%</td><td>${bar(t.coding.percent)}</td><td class="faint">${escapeHtml(t.coding.correct)}/${escapeHtml(t.coding.questions)}</td></tr>` : ''}</tbody></table>` : '<p class="muted">No graded questions yet.</p>';
      document.getElementById('categories').innerHTML = iv.categories.length ? `<table><tbody>${iv.categories.map((row) => `<tr><td>${escapeHtml(row.category)}</td><td>${escapeHtml(row.avg)}</td><td>${bar(row.avg, row.avg >= 75 ? 'strong' : row.avg >= 55 ? 'developing' : 'weak')}</td><td class="faint">${escapeHtml(row.answers)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No interview answers yet.</p>';
      document.getElementById('recent-tests').innerHTML = t.recent.length ? `<table><thead><tr><th>Job</th><th>Score</th><th>Date</th></tr></thead><tbody>${t.recent.map((row) => `<tr><td><a href="/mock-test?test=${encodeURIComponent(row.test_id)}">${escapeHtml(row.job_title || 'General practice')}</a><br><span class="faint">${escapeHtml(row.length)}, ${escapeHtml(row.difficulty)}</span></td><td>${escapeHtml(row.percent)}%</td><td class="faint">${escapeHtml(String(row.completed_at || '').slice(0, 10))}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No tests in this window. <a href="/mock-test">Start a mock test</a>.</p>';
      document.getElementById('recent-interviews').innerHTML = iv.recent.length ? `<table><thead><tr><th>Interview</th><th>Score</th><th>Date</th></tr></thead><tbody>${iv.recent.map((row) => `<tr><td>${escapeHtml(row.job_title || 'General practice')}</td><td>${escapeHtml(row.score)}/100</td><td class="faint">${escapeHtml(String(row.completed_at || '').slice(0, 10))}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No interviews in this window. <a href="/mock-interview">Start a mock interview</a>.</p>';
      if (!state.jobsLoaded) {
        state.jobsLoaded = true;
        const select = document.getElementById('job');
        report.jobs.forEach((job) => {
          const option = document.createElement('option');
          option.value = job.job_id;
          option.textContent = `${job.title}${job.company ? ', ' + job.company : ''} (${job.tests} tests, ${job.interviews} interviews)`;
          select.appendChild(option);
        });
        select.value = state.job;
      }
    }
    async function load() {
      const status = document.getElementById('status');
      status.textContent = 'Loading…';
      try {
        const query = new URLSearchParams({ period: state.period, job_id: state.job, tz });
        render(await api('/api/progress/report?' + query.toString()));
        status.textContent = '';
      } catch (error) {
        status.textContent = error.message;
      }
    }
    document.querySelectorAll('#period button').forEach((button) => button.addEventListener('click', () => {
      state.period = button.dataset.period;
      document.querySelectorAll('#period button').forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
      load();
    }));
    document.getElementById('job').addEventListener('change', (event) => { state.job = event.target.value; load(); });
    load();
"""


def progress_page(user_email: str, is_admin: bool = False) -> str:
    return app_shell("Progress reports", user_email, _PROGRESS_BODY, active="progress", script=_PROGRESS_SCRIPT,
                     is_admin=is_admin, extra_head=_PAGE_STYLE)


# ---------------------------------------------------------------------------
# Privacy and my data
# ---------------------------------------------------------------------------
_PRIVACY_SCRIPT = _ESCAPE_JS + r"""
    async function loadPrivacy() {
      try {
        const data = await api('/api/account/privacy');
        document.getElementById('consent-state').innerHTML = data.has_consent
          ? `<div class="notice good">You accepted this notice (version ${escapeHtml(data.consent.version)}) on ${escapeHtml(String(data.consent.at).slice(0, 10))}.</div>`
          : `<div class="notice warn">You have not accepted the current notice (version ${escapeHtml(data.current_version)}). Resume processing starts only after you accept it.</div><button class="btn btn-primary" id="accept" type="button" style="margin-top:12px">Accept the notice</button>`;
        const accept = document.getElementById('accept');
        if (accept) accept.addEventListener('click', async () => { await api('/api/account/consent', { method: 'POST' }); UI.toast('Notice accepted.', 'good'); loadPrivacy(); });
        const audit = await api('/api/account/audit');
        document.getElementById('audit').innerHTML = audit.entries.length ? `<div class="table-wrap"><table><thead><tr><th>When</th><th>Action</th><th>Details</th></tr></thead><tbody>${audit.entries.map((row) => `<tr><td class="faint">${escapeHtml(new Date(row.ts * 1000).toLocaleString())}</td><td>${escapeHtml(row.action.replace(/_/g, ' '))}</td><td class="faint">${escapeHtml(row.detail && (row.detail.recipient || row.detail.version || row.detail.reason || ''))}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">No recorded actions yet.</p>';
      } catch (error) {
        document.getElementById('consent-state').innerHTML = `<div class="notice bad">${escapeHtml(error.message)}</div>`;
      }
    }
    document.getElementById('delete').addEventListener('click', async () => {
      const status = document.getElementById('delete-status');
      const email = document.getElementById('confirm-email').value;
      status.textContent = 'Deleting…';
      try {
        await api('/api/account/delete', { method: 'POST', body: JSON.stringify({ confirm_email: email }) });
        status.textContent = 'Your account and data were deleted. Redirecting…';
        setTimeout(() => { location.href = '/login'; }, 1500);
      } catch (error) {
        status.textContent = error.message;
      }
    });
    if (document.getElementById('consent-state')) loadPrivacy();
"""


def privacy_page(user_email: str, purpose: str, retention_days: int, version: str, is_admin: bool = False) -> str:
    signed_in = bool(user_email)
    controls = (
        f"""
  <section class="panel"><h2>Your consent</h2><div id="consent-state"><div class="skeleton" style="height:44px"></div></div></section>
  <section class="two">
    <div class="panel"><h2>Download my data</h2><p class="muted" style="margin-bottom:14px">A JSON file with your profile, runs, job leads, tests, interviews, approval queue and activity log.</p>
      <a class="btn" href="/api/account/export">Download my data</a></div>
    <div class="panel"><h2>Delete my account</h2><p class="muted" style="margin-bottom:14px">Permanently removes your resume, profile, runs, tailored resumes, tests, interviews, drafts and schedule. This cannot be undone.</p>
      <label class="field" for="confirm-email">Type your email to confirm
      <input id="confirm-email" type="email" autocomplete="off" placeholder="{escape(user_email)}"></label>
      <div class="btn-row" style="margin-top:12px"><button class="btn btn-danger" id="delete" type="button">Delete everything</button><span class="muted" id="delete-status" role="status"></span></div></div>
  </section>
  <section class="panel"><h2>Activity log</h2><p class="muted" style="margin-bottom:12px">Consents, approvals, sent emails and data exports for your account.</p><div id="audit"></div></section>
"""
        if signed_in else '<div class="notice"><span><a href="/login">Sign in</a> to download or delete your data.</span></div>'
    )
    body = f"""
  <section class="panel">
    <p class="faint">Notice version {escape(version)}. Digital Personal Data Protection Act, 2023 (India)</p>
    <h2 style="margin:8px 0 10px">How we use your data</h2>
    <p style="max-width:72ch">{escape(purpose)}</p>
    <ul class="steps" style="max-width:76ch">
      <li><strong>What we store:</strong> your resume file and text, profile (roles, skills, locations, links), job leads found for you, tailored resumes, mock test and interview answers and scores, and approval decisions.</li>
      <li><strong>What we never use:</strong> age, gender, religion, caste, marital status, photo or other personal attributes are not used for matching or scoring, and are removed before any AI review.</li>
      <li><strong>AI services:</strong> when enabled, parts of your resume or answers are sent to an AI provider for feedback, without storing them at the provider.</li>
      <li><strong>Retention:</strong> accounts with no sign-in for {int(retention_days)} days are deleted automatically.</li>
      <li><strong>Your rights:</strong> download or delete your data below at any time, or withdraw consent by deleting your account.</li>
    </ul>
  </section>
  {controls}
"""
    return app_shell("Privacy & my data", user_email, body, active="privacy",
                     script=_PRIVACY_SCRIPT if signed_in else "", is_admin=is_admin, extra_head=_PAGE_STYLE)


# ---------------------------------------------------------------------------
# Admin metrics
# ---------------------------------------------------------------------------
_ADMIN_BODY = r"""
  <section>
    <p class="muted" style="max-width:72ch">Quality, coverage, human-in-the-loop, practice, operations, AI cost and business metrics. CloudWatch receives the same events as Embedded Metric Format logs.</p>
    <div class="controls" style="margin-top:14px"><label><span class="control-label">Window</span>
      <select id="days"><option value="1">Last 24 hours</option><option value="7" selected>Last 7 days</option><option value="30">Last 30 days</option></select></label>
      <button class="btn" id="refresh" type="button">Refresh</button><span class="muted" id="status" role="status"></span></div>
  </section>
  <section id="alerts" style="display:grid;gap:10px"></section>
  <section class="two" id="sections"></section>
"""

_ADMIN_SCRIPT = _ESCAPE_JS + r"""
    const TITLES = { recommendation_quality: 'Recommendation quality', coverage: 'Coverage', resume: 'Resume and ATS', human_in_the_loop: 'Human in the loop',
      practice: 'Mock tests and interviews', operations: 'Operations', llm: 'AI usage and cost', business: 'Business' };
    function fmt(value) {
      if (value === null || value === undefined) return '-';
      if (typeof value === 'number') return Number.isInteger(value) ? value : value.toFixed(3);
      if (Array.isArray(value)) return value.length ? value.slice(0, 8).map((item) => typeof item === 'object' ? fmt(item) : escapeHtml(item)).join('') : '-';
      if (typeof value === 'object') return '<table>' + Object.entries(value).map(([k, v]) => `<tr><td class="faint">${escapeHtml(k.replace(/_/g, ' '))}</td><td>${fmt(v)}</td></tr>`).join('') + '</table>';
      return escapeHtml(value);
    }
    async function load() {
      const status = document.getElementById('status');
      status.textContent = 'Loading…';
      try {
        const data = await api('/api/admin/metrics?days=' + document.getElementById('days').value);
        document.getElementById('alerts').innerHTML = data.alerts.length
          ? data.alerts.map((alert) => `<div class="notice ${alert.severity === 'high' ? 'bad' : 'warn'}"><span><strong>${escapeHtml(alert.severity === 'high' ? 'High' : 'Medium')}:</strong> ${escapeHtml(alert.message)}</span></div>`).join('')
          : '<div class="notice good">No alerts in this window.</div>';
        document.getElementById('sections').innerHTML = Object.keys(TITLES).map((key) => `<div class="panel metric-card"><h2>${escapeHtml(TITLES[key])}</h2>${fmt(data[key])}</div>`).join('');
        status.textContent = '';
      } catch (error) {
        status.textContent = error.message;
      }
    }
    document.getElementById('refresh').addEventListener('click', load);
    document.getElementById('days').addEventListener('change', load);
    load();
"""


def admin_metrics_page(user_email: str) -> str:
    return app_shell("Admin metrics", user_email, _ADMIN_BODY, active="admin", script=_ADMIN_SCRIPT,
                     is_admin=True, extra_head=_PAGE_STYLE)
