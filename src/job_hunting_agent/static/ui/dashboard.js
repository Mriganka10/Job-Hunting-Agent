/*
 * Dashboard: overview, run form, job leads, resume and ATS, approvals.
 * Uses only the existing JSON APIs; every value from the server is escaped.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => UI.escape(value);
  const form = $('agent-form');
  const timezoneInput = $('daily_timezone');
  const VIEWS = { overview: 'Overview', run: 'Run & profile', jobs: 'Job leads', resume: 'Resume & ATS', approvals: 'Approvals' };
  const PORTAL_LABELS = { linkedin: 'LinkedIn', naukri: 'Naukri', himalayas: 'Himalayas', remotive: 'Remotive', arbeitnow: 'Arbeitnow', jobicy: 'Jobicy', remoteok: 'Remote OK', adzuna: 'Adzuna', careerjet: 'Careerjet', jooble: 'Jooble', jsearch: 'Google for Jobs', indeed: 'Indeed', foundit: 'Foundit', workindia: 'WorkIndia', shine: 'Shine', glassdoor: 'Glassdoor', timesjobs: 'TimesJobs', apna: 'apna', instahyre: 'Instahyre', cutshort: 'Cutshort', wellfound: 'Wellfound', internshala: 'Internshala', freshersworld: 'Freshersworld', hirist: 'Hirist', iimjobs: 'iimjobs', ziprecruiter: 'ZipRecruiter' };
  const FEEDBACK_REASONS = [['role', 'Wrong role'], ['location', 'Wrong location'], ['seniority', 'Wrong seniority'], ['skills', 'Skills do not match'], ['salary', 'Salary'], ['company', 'Company'], ['duplicate', 'Duplicate'], ['expired', 'Expired / closed'], ['other', 'Other']];
  const ADDITIONS_LABELS = {
    already_listed: 'All supported job skills are already listed',
    no_evidence: 'No resume evidence for the remaining job skills',
    no_requirements: 'No specific skills found in this posting',
    description_unavailable: 'Description unavailable, check the posting',
  };

  let activeResult = { key: '', generatedAt: '', source: '' };
  let activePayload = null;
  let activeFeedback = {};
  let activeFeedbackRun = null;
  let portalLinks = [];
  let scheduler = null;
  let hasConsent = true;
  let approvals = { items: [] };
  let approvalTimer = null;
  let resumeStatusTimer = null;
  let running = false;
  let templateCatalog = null;
  let templateRun = null;
  const filters = { text: '', portal: '', minScore: 0, sort: 'match', layout: readPref('jha-leads-layout', 'list') };

  function readPref(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; } }
  function writePref(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* optional */ } }

  // ------------------------------------------------------------ helpers
  async function responsePayload(response) { return UI.payloadOf(response); }
  function jobKey(job) { return `${job.portal || ''}:${job.source_id || job.url || ''}`.toLowerCase(); }
  function portalName(portal) { return PORTAL_LABELS[portal] || portal || 'Job board'; }
  function scoreClass(score) { return score >= 70 ? '' : score >= 50 ? 'mid' : 'low'; }
  function meter(score) {
    const filled = Math.round(Math.max(0, Math.min(100, Number(score) || 0)) / 10);
    return `<span class="meter ${scoreClass(score)}" role="img" aria-label="Match ${escapeHtml(score || 0)} percent">${Array.from({ length: 10 }, (_, i) => `<i class="${i < filled ? 'on' : ''}"></i>`).join('')}</span>`;
  }
  function when(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(UI.locale, { dateStyle: 'medium', timeStyle: 'short' });
  }
  function ago(value) {
    const date = new Date(value);
    if (!value || Number.isNaN(date.getTime())) return '';
    const minutes = Math.round((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    const days = Math.round(hours / 24);
    return `${days} day${days === 1 ? '' : 's'} ago`;
  }
  function enrichFormData() {
    timezoneInput.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const data = new FormData(form);
    data.set('daily_timezone', timezoneInput.value);
    return data;
  }
  function setCount(id, value) {
    const node = $(id);
    if (!node) return;
    node.textContent = value;
    node.classList.toggle('hidden', !value);
  }

  // ------------------------------------------------------------- router
  function currentView() {
    const name = (location.hash || '#overview').slice(1);
    return VIEWS[name] ? name : 'overview';
  }
  function showView(focus) {
    const view = currentView();
    document.querySelectorAll('[data-view]').forEach((section) => { section.hidden = section.dataset.view !== view; });
    $('page-title').textContent = VIEWS[view];
    document.title = `${VIEWS[view]} · Job Hunting Agent`;
    if (focus) { $('content').focus({ preventScroll: true }); window.scrollTo(0, 0); }
  }
  window.addEventListener('hashchange', () => showView(true));

  // --------------------------------------------------------- run & schedule
  const STAGES = [
    [0, 'Scoring your resume'],
    [8, 'Searching LinkedIn, Naukri and job boards'],
    [40, 'Ranking jobs and preparing application drafts'],
  ];
  function renderStages(seconds, finished) {
    const list = $('run-stages');
    list.innerHTML = STAGES.map(([start, label], index) => {
      const next = STAGES[index + 1] ? STAGES[index + 1][0] : Infinity;
      const state = finished || seconds >= next ? 'done' : seconds >= start ? 'active' : '';
      return `<li class="${state}">${escapeHtml(label)}</li>`;
    }).join('') + `<li class="${finished ? 'done' : ''}">Results ready</li>`;
  }
  function setRunning(value) {
    running = value;
    ['run-submit', 'schedule-run'].forEach((id) => { $(id).disabled = value; });
    form.setAttribute('aria-busy', String(value));
    $('run-submit').textContent = value ? 'Running…' : 'Run agent';
  }
  function showRunCard(stateText, kind) {
    const card = $('run-progress');
    card.classList.remove('hidden');
    const status = $('run-status');
    status.textContent = stateText;
    status.className = kind === 'bad' ? 'notice bad' : 'muted';
  }

  // ------------------------------------------------------ required fields
  // Every field marked * must be filled before a run or a schedule. LinkedIn,
  // Naukri and the job description are optional. The server checks the same.
  function clearFieldError(el) {
    el.removeAttribute('aria-invalid');
    const note = document.getElementById(`err-${el.id}`);
    if (note) note.remove();
    if (el.id === 'resume') el.closest('.dropzone').classList.remove('invalid');
  }
  function showFieldError(el, message) {
    el.setAttribute('aria-invalid', 'true');
    let note = document.getElementById(`err-${el.id}`);
    if (!note) {
      note = document.createElement('span');
      note.className = 'field-error';
      note.id = `err-${el.id}`;
      const anchor = el.id === 'resume' ? el.closest('.dropzone') : el.id === 'consent' ? el.closest('.check') : el;
      anchor.insertAdjacentElement('afterend', note);
      el.setAttribute('aria-describedby', note.id);
    }
    note.textContent = message;
    if (el.id === 'resume') el.closest('.dropzone').classList.add('invalid');
  }
  function validateForm(forSchedule) {
    const problems = [];
    const add = (el, label, message) => problems.push({ el, label, message: message || label });
    form.querySelectorAll('[aria-invalid="true"]').forEach(clearFieldError);
    if (form.dataset.hasResume !== 'true' && !(resumeInput.files && resumeInput.files.length)) add(resumeInput, 'Resume', 'Upload your resume');
    form.querySelectorAll('[required][data-label]').forEach((el) => {
      if (!String(el.value || '').trim()) add(el, el.dataset.label, `Fill in ${el.dataset.label}`);
    });
    const phone = $('phone');
    const digits = phone.value.replace(/\D/g, '');
    if (phone.value.trim() && (!/^\+?[0-9][0-9 ()-]{5,20}$/.test(phone.value.trim()) || digits.length < 7 || digits.length > 15)) {
      add(phone, 'Phone', 'Enter a valid phone number (7 to 15 digits, for example +91 98765 43210)');
    }
    const years = $('experience_years');
    if (years.value.trim() && !(Number(years.value) >= 0 && Number(years.value) <= 50)) add(years, 'Experience (years)', 'Experience (years) must be a number from 0 to 50');
    const maxJobs = $('max_jobs_per_portal');
    if (maxJobs.value.trim() && !(Number(maxJobs.value) >= 1 && Number(maxJobs.value) <= 50)) add(maxJobs, 'Max jobs per source', 'Max jobs per source must be from 1 to 50');
    if (forSchedule && !$('daily_at').value) add($('daily_at'), 'Daily time', 'Daily time is required to schedule a daily run');
    if (!$('consent').checked) add($('consent'), 'Privacy notice consent', 'Accept the privacy notice to continue');
    problems.forEach((item) => showFieldError(item.el, item.message));
    if (problems.length) {
      $('missing-list').innerHTML = problems.map((item) => `<li>${escapeHtml(item.message)}</li>`).join('');
      $('missing-dialog').showModal();
      $('missing-dialog').dataset.first = problems[0].el.id;
    }
    return !problems.length;
  }
  $('missing-ok').addEventListener('click', () => $('missing-dialog').close());
  $('missing-dialog').addEventListener('close', () => {
    const first = $($('missing-dialog').dataset.first || '');
    if (!first) return;
    first.scrollIntoView({ block: 'center' });
    first.focus({ preventScroll: true });
  });
  form.addEventListener('input', (event) => { if (event.target.getAttribute('aria-invalid') === 'true') clearFieldError(event.target); });
  form.addEventListener('change', (event) => { if (event.target.getAttribute('aria-invalid') === 'true') clearFieldError(event.target); });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (running) return;
    if (!validateForm(false)) return;
    setRunning(true);
    const runStarted = Date.now();
    const tick = () => {
      const seconds = Math.round((Date.now() - runStarted) / 1000);
      renderStages(seconds, false);
      showRunCard(`${seconds}s elapsed. Usually under a minute; you can keep browsing.`);
    };
    tick();
    const runTimer = setInterval(tick, 1000);
    try {
      const response = await fetch('/api/run', { method: 'POST', body: enrichFormData() });
      clearInterval(runTimer);
      const payload = await responsePayload(response);
      if (!response.ok) throw new Error(payload.detail || 'Run failed.');
      form.dataset.hasResume = 'true';
      renderStages(0, true);
      showRunCard(`Finished in ${Math.round((Date.now() - runStarted) / 1000)}s.`);
      hasConsent = true;
      render(payload, 'manual');
      UI.toast(`Run complete: ${payload.job_count ?? payload.jobs.length} job leads found.`, 'good');
      refreshDashboard();
      location.hash = '#overview';
    } catch (error) {
      clearInterval(runTimer);
      showRunCard(error instanceof Error && error.message ? error.message : 'Run failed. Check the server log and try again.', 'bad');
      UI.toast(error.message || 'Run failed.', 'bad');
    } finally {
      setRunning(false);
    }
  });

  $('schedule-run').addEventListener('click', async () => {
    if (!validateForm(true)) return;
    const button = $('schedule-run');
    button.disabled = true;
    try {
      const response = await fetch('/api/scheduler/start', { method: 'POST', body: enrichFormData() });
      const payload = await responsePayload(response);
      if (!response.ok) throw new Error(payload.detail || 'Schedule failed.');
      form.dataset.hasResume = 'true';
      renderScheduler(payload.scheduler);
      UI.toast(`Daily run scheduled for ${payload.scheduler?.daily_at || 'the chosen time'}.`, 'good');
      refreshDashboard();
    } catch (error) {
      UI.toast(error.message || 'Scheduling failed.', 'bad');
    } finally {
      button.disabled = running;
    }
  });

  $('stop-scheduler').addEventListener('click', async () => {
    try {
      const payload = await UI.api('/api/scheduler/stop', { method: 'POST' });
      renderScheduler(payload);
      UI.toast(payload.running ? 'The daily run is still active.' : 'Daily run stopped.', payload.running ? 'warn' : 'good');
    } catch (error) {
      UI.toast(error.message, 'bad');
    }
  });

  // Resume drop zone
  const resumeInput = $('resume');
  const dropzone = resumeInput.closest('.dropzone');
  resumeInput.addEventListener('change', () => {
    const file = resumeInput.files && resumeInput.files[0];
    $('dropzone-title').textContent = file ? file.name : 'Drop your resume here or choose a file';
    $('dropzone-hint').textContent = file ? `${Math.max(1, Math.round(file.size / 1024))} KB, ready to upload with the next run` : 'PDF, DOCX, TXT or Markdown';
  });
  ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, () => dropzone.classList.add('dragging')));
  ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, () => dropzone.classList.remove('dragging')));

  // ----------------------------------------------------------- dashboard
  async function refreshDashboard() {
    let latestResult = null;
    try {
      const response = await fetch('/api/dashboard');
      if (response.ok) {
        const payload = await response.json();
        portalLinks = payload.portal_search_links || [];
        hasConsent = payload.has_consent !== false;
        renderScheduler(payload.scheduler);
        latestResult = newerResult(latestResult, payload.scheduler?.last_result);
        const latestStoredRun = payload.latest_run?.payload;
        latestResult = newerResult(latestResult, latestStoredRun);
      }
    } catch (_) { /* offline: keep the current view */ }
    if (shouldRenderResult(latestResult)) {
      render(latestResult, latestResult.trigger || 'manual');
    } else if (!activePayload) {
      renderOverview(null);
    }
  }
  function newerResult(current, candidate) {
    if (!candidate?.generated_at) return current;
    if (!current?.generated_at) return candidate;
    return candidate.generated_at > current.generated_at ? candidate : current;
  }
  function resultKey(result) {
    return result?.generated_at || result?.run_id || '';
  }
  function shouldRenderResult(result) {
    const key = resultKey(result);
    if (!key || key === activeResult.key) return false;
    if (!activeResult.generatedAt || !result.generated_at) return true;
    return result.generated_at > activeResult.generatedAt;
  }

  function renderScheduler(snapshot) {
    scheduler = snapshot || null;
    const isRunning = scheduler && scheduler.running;
    const error = scheduler && scheduler.last_error;
    const pill = $('scheduler-pill');
    pill.className = `badge ${error ? 'bad' : isRunning ? 'good' : ''}`;
    pill.textContent = error ? 'Last run failed' : isRunning ? 'Scheduled' : 'Off';
    const rows = [
      ['Daily time', scheduler?.daily_at || 'Not set'],
      ['Timezone', scheduler?.timezone || timezoneInput.value || 'UTC'],
      ['Next run', when(scheduler?.next_run_at) || 'Not scheduled'],
      ['Last run', when(scheduler?.last_run_at) || 'No run yet'],
    ];
    let html = `<dl class="kv">${rows.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join('')}</dl>`;
    if (error) html += `<div class="notice bad" style="margin-top:12px"><span>Last scheduled run failed: ${escapeHtml(error)}</span></div>`;
    if (scheduler?.history?.length) {
      const item = scheduler.history[0];
      html += `<p class="faint" style="margin-top:12px">Latest ${escapeHtml(item.trigger)} run: ${escapeHtml(when(item.finished_at))}, ${escapeHtml(item.jobs ?? 'n/a')} jobs</p>`;
    }
    $('scheduler-status').innerHTML = html;
    $('stop-scheduler').disabled = !isRunning;
    renderOverview(activePayload);
  }

  function render(payload, source = 'manual') {
    const key = resultKey(payload);
    activeResult = { key, generatedAt: payload.generated_at || activeResult.generatedAt, source };
    activePayload = payload;
    renderOverview(payload);
    renderJobs();
    renderResume(payload);
    scheduleResumeStatusPoll();
    if (payload.run_id && payload.run_id !== activeFeedbackRun) { activeFeedbackRun = payload.run_id; loadFeedback(payload.run_id); }
    if (payload.run_id && payload.run_id !== templateRun) { templateRun = payload.run_id; loadTemplates(payload.run_id); }
    loadApprovals();
  }

  // ------------------------------------------------------------- overview
  function nextActions(payload) {
    const items = [];
    if (!payload) {
      items.push(['warn', 'Upload your resume and run the agent', 'It scores your resume and finds matching jobs in about a minute.', '#run', 'Start a run']);
      return items;
    }
    const report = payload.ats_report || {};
    const pending = (approvals.items || []).filter((item) => item.status === 'pending_approval').length;
    if (!hasConsent) items.push(['bad', 'Accept the privacy notice', 'Runs need your consent before your resume is processed.', '/privacy', 'Review notice']);
    if (pending) items.push(['warn', `Review ${pending} email${pending === 1 ? '' : 's'} waiting for your approval`, 'Nothing reaches a recruiter until you approve it.', '#approvals', 'Review']);
    if ((report.score || 0) < 75 && (report.improvements || []).length) items.push(['warn', `Raise your ATS score from ${report.score}`, `${report.improvements.length} specific improvements are ready.`, '#resume', 'See fixes']);
    const top = [...(payload.jobs || [])].sort((a, b) => (b.match_score || 0) - (a.match_score || 0))[0];
    if (top) items.push(['good', `Practise for ${top.title}`, `${top.company || 'Top match'}: take a job-specific mock test.`, `/mock-test?job=${encodeURIComponent(jobKey(top))}`, 'Mock Test']);
    if (!scheduler?.running) items.push(['', 'Schedule a daily run', 'Fresh leads and drafts every day at a time you choose.', '#run', 'Schedule']);
    if ((payload.jobs || []).length && !Object.keys(activeFeedback).length) items.push(['', 'Rate a few leads', 'Marking leads relevant or not sharpens your matches.', '#jobs', 'Rate leads']);
    return items.slice(0, 4);
  }

  function renderOverview(payload) {
    const report = payload?.ats_report;
    const jobs = payload?.jobs || [];
    const total = payload ? (payload.job_count ?? payload.job_page?.total ?? jobs.length) : 0;
    const strong = jobs.filter((job) => (job.match_score || 0) >= 70).length;
    const pending = (approvals.items || []).filter((item) => item.status === 'pending_approval').length;
    const first = ($('name').value || '').trim().split(/\s+/)[0];
    const hour = new Date().getHours();
    const greeting = `${hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'}${first ? `, ${first}` : ''}`;
    const ring = $('overview-ring');
    if (report) {
      ring.style.setProperty('--value', report.score || 0);
      ring.style.setProperty('--ring-color', report.score >= 75 ? 'var(--good)' : report.score >= 55 ? 'var(--accent)' : 'var(--bad)');
      ring.innerHTML = `<span>${escapeHtml(report.score)}<small>ATS score</small></span>`;
      ring.setAttribute('aria-label', `ATS score ${report.score} out of 100`);
    } else {
      ring.style.setProperty('--value', 0);
      ring.innerHTML = '<span>–<small>No score yet</small></span>';
      ring.setAttribute('aria-label', 'No ATS score yet');
    }
    $('overview-greeting').textContent = greeting;
    const scheduledLabel = activeResult.source === 'scheduled' && payload
      ? ` Showing latest scheduled run from ${when(payload.generated_at) || 'the scheduler'}.`
      : '';
    // Separate sentences, so each one can be translated whole.
    $('overview-lede').innerHTML = payload
      ? `<span>${escapeHtml(ago(payload.generated_at) ? `Your last run ${ago(payload.generated_at)} found ${total} job leads, ${strong} of them strong matches.` : `Your last run found ${total} job leads, ${strong} of them strong matches.`)}</span>${scheduledLabel ? ` <span>${escapeHtml(scheduledLabel.trim())}</span>` : ''}`
      : '<span>Upload your resume to get an ATS score, matched job leads, a tailored resume for every lead and recruiter-ready drafts.</span>';
    $('overview-primary').textContent = payload ? 'Run again' : 'Upload resume and run';
    $('overview-secondary').classList.toggle('hidden', !payload);

    const appSummary = payload?.application_summary || {};
    $('stat-jobs').textContent = payload ? total : '–';
    $('stat-strong').textContent = payload ? strong : '–';
    $('stat-drafts').textContent = payload ? (appSummary.drafted || 0) : '–';
    $('stat-approvals').textContent = pending;
    setCount('nav-jobs-count', payload ? total : '');

    $('next-actions').innerHTML = nextActions(payload).map(([kind, title, hint, href, cta]) =>
      `<li><span class="dot ${kind}" aria-hidden="true"></span><div class="grow"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(hint)}</span></div><a class="btn btn-sm" href="${escapeHtml(href)}">${escapeHtml(cta)}</a></li>`).join('');

    const top = [...jobs].sort((a, b) => (b.match_score || 0) - (a.match_score || 0)).slice(0, 4);
    $('top-matches').innerHTML = top.length
      ? top.map((job) => `<div class="mini-lead"><span class="mini-score">${escapeHtml(job.match_score || 0)}</span><div style="min-width:0"><strong title="${escapeHtml(job.title)}">${escapeHtml(job.title)}</strong><span>${escapeHtml(job.company || '')}${job.location ? `, ${escapeHtml(job.location)}` : ''}</span></div><a class="btn btn-sm btn-quiet open-job" data-job="${escapeHtml(jobKey(job))}" data-portal="${escapeHtml(job.portal || '')}" data-rank="${jobs.indexOf(job) + 1}" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">Open<span class="sr-only"> ${escapeHtml(job.title)} (opens in a new tab)</span></a></div>`).join('')
      : `<div class="empty"><strong>No leads yet</strong><p class="muted">Run the agent to see your best matches here.</p><a class="btn btn-primary btn-sm" href="#run">Start a run</a></div>`;

    $('overview-schedule').innerHTML = scheduler?.running
      ? `<p><span class="badge good">Scheduled</span></p><p style="margin-top:10px">${escapeHtml(`Runs daily at ${scheduler.daily_at} (${scheduler.timezone || 'UTC'}).`)}</p><p class="faint" style="margin-top:4px">Next run ${escapeHtml(when(scheduler.next_run_at) || 'soon')}</p>`
      : `<p><span class="badge">Off</span></p><p class="muted" style="margin-top:10px">Set a daily time on Run &amp; profile to get fresh leads every day.</p>`;
  }

  // ------------------------------------------------------------- job leads
  function filteredJobs() {
    const jobs = (activePayload?.jobs || []).map((job, index) => ({ job, rank: index + 1 }));
    const text = filters.text.trim().toLowerCase();
    let list = jobs.filter(({ job }) => {
      if (filters.portal && job.portal !== filters.portal) return false;
      if ((job.match_score || 0) < filters.minScore) return false;
      if (!text) return true;
      return [job.title, job.company, job.location, ...(job.match_reasons || []), ...(job.source_metadata?.matched_skills || [])]
        .join(' ').toLowerCase().includes(text);
    });
    if (filters.sort === 'match') list.sort((a, b) => (b.job.match_score || 0) - (a.job.match_score || 0) || a.rank - b.rank);
    if (filters.sort === 'newest') list.sort((a, b) => String(b.job.posted_at || '').localeCompare(String(a.job.posted_at || '')));
    if (filters.sort === 'company') list.sort((a, b) => String(a.job.company || '').localeCompare(String(b.job.company || '')));
    return list;
  }

  function tailoredInfo(job) {
    return activePayload?.improved_resume?.tailored_statuses?.[job.tailored_resume_id] || {};
  }

  function tailoredControl(job) {
    if (!job.tailored_resume_id || !activePayload?.run_id) return '';
    const info = tailoredInfo(job);
    const state = info.status || 'idle';
    const base = `/api/runs/${encodeURIComponent(activePayload.run_id)}/tailored-resumes/${encodeURIComponent(job.tailored_resume_id)}`;
    if (state === 'ready') {
      return `<span class="faint">Tailored resume</span><div class="btn-row" style="gap:8px"><a class="btn btn-sm" style="flex:1" href="${base}/docx">DOCX</a><a class="btn btn-sm" style="flex:1" href="${base}/pdf">PDF</a></div>`
        + `<button type="button" class="btn btn-sm btn-quiet show-changes" data-artifact-id="${escapeHtml(job.tailored_resume_id)}" data-job="${escapeHtml(jobKey(job))}">What changed in this resume</button>`;
    }
    const label = state === 'preparing' ? 'Preparing resume…' : state === 'failed' ? 'Retry tailored resume' : 'Prepare tailored resume';
    return `<button type="button" class="btn btn-sm prepare-tailored" data-artifact-id="${escapeHtml(job.tailored_resume_id)}" ${state === 'preparing' ? 'disabled aria-busy="true"' : ''}>${label}</button>`
      + (state === 'failed' && info.error ? `<span class="faint">${escapeHtml(info.error)}</span>` : '');
  }

  function feedbackControl(job, rank) {
    if (!activePayload?.run_id) return '';
    const key = jobKey(job);
    const saved = activeFeedback[key] || {};
    return `<div class="feedback-row" data-job="${escapeHtml(key)}" data-rank="${rank}"><button type="button" class="btn btn-sm fb-yes" aria-pressed="${saved.verdict === 'relevant'}">Relevant</button><select class="fb-no" aria-label="Mark ${escapeHtml(job.title)} as not relevant"><option value="">Not relevant…</option>${FEEDBACK_REASONS.map(([value, label]) => `<option value="${value}" ${saved.verdict === 'not_relevant' && saved.reason === value ? 'selected' : ''}>${label}</option>`).join('')}</select><span class="saved" aria-live="polite">${saved.verdict ? 'Saved' : ''}</span></div>`;
  }

  function experienceLabel(job) {
    const low = job.required_experience;
    if (low === null || low === undefined) return 'Experience not stated';
    const high = job.source_metadata?.experience_max_years;
    const fmt = (years) => (years < 1 && years > 0 ? `${Math.round(years * 12)} months` : `${years} yr${years === 1 ? '' : 's'}`);
    if (low === 0 && (high === null || high === undefined)) return 'Entry level';
    return high !== null && high !== undefined && high > low ? `Needs ${low}-${fmt(high)}` : `Needs ${fmt(low)}+`;
  }

  function jobDetails(job) {
    return [experienceLabel(job), job.workplace_mode, job.employment_type, job.salary_text, job.posted_at ? `Posted ${String(job.posted_at).slice(0, 10)}` : '', job.freshness_verified ? 'date verified' : 'date unverified']
      .filter((item) => item && item !== 'unknown');
  }

  function additionalSkills(job) {
    const hint = job.source_metadata?.additional_skills_message || '';
    if ((job.additional_skills || []).length) {
      return `<span class="chips" title="${escapeHtml(hint)}">${job.additional_skills.map((skill) => `<span class="chip added">${escapeHtml(skill)}</span>`).join('')}</span>`;
    }
    return `<span class="faint" title="${escapeHtml(hint)}">${escapeHtml(ADDITIONS_LABELS[job.source_metadata?.additional_skills_status] || 'No source-backed additions')}</span>`;
  }

  function practiceLinks(job) {
    const key = encodeURIComponent(jobKey(job));
    return `<div class="lead-links"><a href="/mock-test?job=${key}">Mock Test</a><a href="/mock-interview?job=${key}">Mock Interview</a><span class="faint">Link ${escapeHtml(job.link_status || 'unchecked')}</span></div>`;
  }

  function sourceState(job) {
    const attribution = job.source_metadata?.source_type === 'partner_api' ? job.source_metadata?.source_attribution : '';
    return attribution || (job.source_validated ? 'Validated API' : 'Public discovery');
  }

  function leadCard({ job, rank }) {
    const reasons = (job.match_reasons || []).map((reason) => `<span class="chip">${escapeHtml(reason)}</span>`).join('');
    const matched = job.source_metadata?.matched_skills || [];
    const missing = job.source_metadata?.missing_required_skills || [];
    const company = job.normalized_company && job.normalized_company !== job.company ? ` (${escapeHtml(job.normalized_company)})` : '';
    return `<article class="lead" aria-labelledby="lead-${rank}">
      <div class="lead-score"><b>${escapeHtml(job.match_score || 0)}<span class="faint" style="font:500 13px var(--body)">%</span></b>${meter(job.match_score)}<span class="badge" title="${escapeHtml(sourceState(job))}">${escapeHtml(portalName(job.portal))}</span></div>
      <div class="lead-main">
        <h3 id="lead-${rank}"><a class="open-job" data-job="${escapeHtml(jobKey(job))}" data-portal="${escapeHtml(job.portal || '')}" data-rank="${rank}" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">${escapeHtml(job.title)}</a></h3>
        <p class="lead-sub">${escapeHtml(job.company || '')}${company}${job.location ? ` · ${escapeHtml(job.location)}` : ''}</p>
        <p class="faint">${jobDetails(job).map((item) => `<span>${escapeHtml(item)}</span>`).join(', ')}</p>
        ${reasons ? `<div class="chips">${reasons}</div>` : ''}
        <div class="lead-skills">
          ${matched.length ? `<div><span class="k">Matched</span>${matched.map((s) => `<span class="chip">${escapeHtml(s)}</span>`).join('')}</div>` : ''}
          ${missing.length ? `<div><span class="k">Missing</span>${missing.map((s) => `<span class="chip missing">${escapeHtml(s)}</span>`).join('')}</div>` : ''}
          <div><span class="k">Additional Skills</span>${additionalSkills(job)}</div>
        </div>
      </div>
      <div class="lead-actions">
        <a class="btn btn-primary btn-sm open-job" data-job="${escapeHtml(jobKey(job))}" data-portal="${escapeHtml(job.portal || '')}" data-rank="${rank}" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">Open job<span class="sr-only"> (opens in a new tab)</span></a>
        ${tailoredControl(job)}
        ${practiceLinks(job)}
        ${feedbackControl(job, rank)}
      </div>
    </article>`;
  }

  function leadRow({ job, rank }) {
    const reasons = (job.match_reasons || []).map((reason) => `<span class="chip">${escapeHtml(reason)}</span>`).join(' ');
    const matched = (job.source_metadata?.matched_skills || []).length ? `<br><span class="faint">Matched skills: ${job.source_metadata.matched_skills.map(escapeHtml).join(', ')}</span>` : '';
    const missing = (job.source_metadata?.missing_required_skills || []).length ? `<br><span class="faint">Missing required skills: ${job.source_metadata.missing_required_skills.map(escapeHtml).join(', ')}</span>` : '';
    return `<tr><td>${escapeHtml(portalName(job.portal))}<br><span class="faint">${escapeHtml(sourceState(job))}</span></td>`
      + `<td><strong>${escapeHtml(job.title)}</strong><br><span class="muted">${escapeHtml(job.location || '')}</span><br><span class="faint">${jobDetails(job).map((item) => `<span>${escapeHtml(item)}</span>`).join(', ')}</span></td>`
      + `<td>${escapeHtml(job.company)}</td>`
      + `<td><strong>${escapeHtml(job.match_score || 0)}%</strong><br>${meter(job.match_score)}<div class="chips" style="margin-top:6px">${reasons}</div>${matched}${missing}</td>`
      + `<td>${additionalSkills(job)}</td>`
      + `<td style="min-width:200px;display:grid;gap:8px"><a class="open-job" data-job="${escapeHtml(jobKey(job))}" data-portal="${escapeHtml(job.portal || '')}" data-rank="${rank}" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer">Open job</a>${tailoredControl(job)}${practiceLinks(job)}${feedbackControl(job, rank)}</td></tr>`;
  }

  function renderJobs() {
    const host = $('jobs-list');
    const payload = activePayload;
    const portalSelect = $('filter-portal');
    if (!payload) {
      host.innerHTML = `<div class="empty"><strong>No job leads yet</strong><p class="muted">Run the agent with your resume and target roles to see matched postings here.</p><a class="btn btn-primary" href="#run">Start a run</a></div>`;
      $('jobs-count').textContent = '';
      $('jobs-more').innerHTML = '';
      $('portal-links').innerHTML = portalLinksHtml();
      return;
    }
    const portals = [...new Set(payload.jobs.map((job) => job.portal).filter(Boolean))];
    const selected = portalSelect.value;
    portalSelect.innerHTML = `<option value="">All sources</option>${portals.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(portalName(p))}</option>`).join('')}`;
    portalSelect.value = portals.includes(selected) ? selected : '';
    filters.portal = portalSelect.value;

    const jobPage = payload.job_page || { total: payload.jobs.length, has_more: false, next_cursor: '' };
    const totalJobs = payload.job_count ?? jobPage.total ?? payload.jobs.length;
    const list = filteredJobs();
    $('jobs-count').textContent = `Showing ${list.length} of ${payload.jobs.length} loaded leads (${totalJobs} found in this run).`;
    if (!payload.jobs.length) {
      host.innerHTML = `<div class="empty"><strong>No matching postings in this run</strong><p class="muted">Try a broader role or location, or search the portals below.</p><a class="btn" href="#run">Edit search</a></div>`;
    } else if (!list.length) {
      host.innerHTML = `<div class="empty"><strong>No leads match these filters</strong><p class="muted">Lower the minimum match or clear the search.</p><button class="btn" type="button" id="clear-filters">Clear filters</button></div>`;
    } else if (filters.layout === 'table') {
      host.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Portal</th><th>Role & Location</th><th>Company</th><th>Match</th><th>Additional Skills</th><th>Actions</th></tr></thead><tbody>${list.map(leadRow).join('')}</tbody></table></div>`;
    } else {
      host.innerHTML = `<div class="lead-list">${list.map(leadCard).join('')}</div>`;
    }
    const remainingJobs = Math.max(0, (jobPage.total || totalJobs) - payload.jobs.length);
    $('jobs-more').innerHTML = jobPage.has_more
      ? `<button class="btn" id="show-more-jobs" type="button">Show more jobs (${remainingJobs} remaining)</button>`
      : '';
    $('portal-links').innerHTML = portalLinksHtml();
    document.querySelectorAll('#layout-toggle button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.layout === filters.layout)));
  }

  function portalLinksHtml() {
    if (!portalLinks.length) return '';
    const names = { indeed: 'Indeed', foundit: 'Foundit', workindia: 'WorkIndia' };
    return `<section class="panel"><h3>Search more portals directly</h3><p class="muted" style="margin:6px 0 12px;max-width:72ch">Indeed, Foundit and WorkIndia have no public job API, so these open the same search on their sites. With a Google for Jobs (JSearch) key their listings also appear above.</p><div class="btn-row">${portalLinks.map((link) => `<a class="btn btn-sm" href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer">${escapeHtml(names[link.portal] || link.portal)}: ${escapeHtml(link.label)}</a>`).join('')}</div></section>`;
  }

  $('filter-text').addEventListener('input', (event) => { filters.text = event.target.value; renderJobs(); });
  $('filter-portal').addEventListener('change', (event) => { filters.portal = event.target.value; renderJobs(); });
  $('filter-score').addEventListener('input', (event) => { filters.minScore = Number(event.target.value) || 0; $('filter-score-value').textContent = `${filters.minScore}%`; renderJobs(); });
  $('filter-sort').addEventListener('change', (event) => { filters.sort = event.target.value; renderJobs(); });
  document.querySelectorAll('#layout-toggle button').forEach((button) => button.addEventListener('click', () => {
    filters.layout = button.dataset.layout;
    writePref('jha-leads-layout', filters.layout);
    renderJobs();
  }));

  // -------------------------------------------------------- resume & ATS
  function renderResume(payload) {
    const report = payload?.ats_report;
    if (!report) {
      $('resume-body').innerHTML = `<div class="empty"><strong>No ATS report yet</strong><p class="muted">Your score, the fixes that raise it and the ATS-ready resume downloads appear after your first run.</p><a class="btn btn-primary" href="#run">Start a run</a></div>`;
      $('draft-host').innerHTML = '<p class="muted">No draft message was generated yet.</p>';
      return;
    }
    const confidencePercent = Math.round((report.score_confidence || 0) * 100);
    const extractionPercent = Math.round((report.extraction_confidence || 0) * 100);
    const scoreRange = report.score_range || [report.score, report.score];
    const layout = report.layout_analysis || {};
    const breakdown = (report.score_breakdown || []).map(([label, points, max]) => {
      const percent = max ? Math.round((points / max) * 100) : 0;
      return `<div class="breakdown-row"><span>${escapeHtml(label)}</span><div class="bar"><i class="${percent >= 75 ? 'good' : percent >= 50 ? 'mid' : 'low'}" style="width:${percent}%"></i></div><b>${escapeHtml(points)}/${escapeHtml(max)}</b></div>`;
    }).join('');
    const improvements = (report.improvements || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const strengths = (report.strengths || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const missing = (report.missing_keywords || []).map((item) => `<span class="chip missing">${escapeHtml(item)}</span>`).join('');
    $('resume-body').innerHTML = `
      <section class="panel">
        <div style="display:flex;flex-wrap:wrap;gap:24px;align-items:center">
          <div class="ring" style="--value:${Number(report.score) || 0};--ring-color:${report.score >= 75 ? 'var(--good)' : report.score >= 55 ? 'var(--accent)' : 'var(--bad)'}" role="img" aria-label="ATS score ${escapeHtml(report.score)} out of 100"><span>${escapeHtml(report.score)}<small>of 100</small></span></div>
          <div style="flex:1;min-width:240px;display:grid;gap:10px">
            <h2>${escapeHtml(report.role_profile || 'General Professional')} profile</h2>
            <dl class="kv">
              <div><dt>Confidence</dt><dd>${confidencePercent}% (${escapeHtml(report.confidence_label || 'Low')})</dd></div>
              <div><dt>Estimated range</dt><dd>${escapeHtml(scoreRange[0])} to ${escapeHtml(scoreRange[1])}</dd></div>
              <div><dt>Text extraction</dt><dd>${extractionPercent}%</dd></div>
              <div><dt>Layout</dt><dd>${escapeHtml(layout.score ?? 'not verified')}${layout.score !== undefined ? '/100' : ''}</dd></div>
            </dl>
            <p class="faint">Semantic provider: ${escapeHtml(report.semantic_provider || 'not applicable')}</p>
          </div>
        </div>
        <hr class="divider">
        ${improvedResumeDownload(payload)}
      </section>
      <section class="panel" id="templates-panel" aria-labelledby="templates-title">${templatesHtml()}</section>
      ${screeningCheck(report)}
      <section class="split">
        <div class="panel"><h3 style="margin-bottom:12px">Resume improvements</h3><ul class="plain">${improvements || '<li>No major improvements found.</li>'}</ul></div>
        <div class="panel"><h3 style="margin-bottom:12px">Score breakdown</h3><div class="breakdown">${breakdown || '<p class="muted">No breakdown available.</p>'}</div></div>
      </section>
      <section class="split">
        <div class="panel"><h3 style="margin-bottom:12px">Missing keywords</h3>${missing ? `<div class="chips">${missing}</div>` : '<p class="muted">No configured keywords are missing.</p>'}</div>
        <div class="panel"><h3 style="margin-bottom:12px">Strengths</h3><ul class="plain">${strengths || '<li>Run with a job description for a sharper read.</li>'}</ul></div>
      </section>`;
    const draftTemplate = buildDraftTemplate(payload.applications || []);
    $('draft-host').innerHTML = draftTemplate ? draftCard(draftTemplate) : '<p class="muted">No draft message was generated for this run.</p>';
  }

  function screeningCheck(report) {
    const req = report.category_details?.job_requirements || {};
    if (!req.required_skills?.length && !req.screening_risks?.length && !req.experience_required_years) return '';
    const titleLabels = { exact: 'Job title appears in your resume', partial: 'Job title partly matches', missing: 'Job title missing from your resume' };
    const expLabels = { met: 'Experience requirement met', close: 'Experience slightly below the requirement', below: 'Experience below the requirement' };
    const facts = [
      req.required_skills?.length ? `Must-have skills found: ${req.required_skills.length - (req.required_missing || []).length}/${req.required_skills.length}` : '',
      req.preferred_skills?.length ? `Nice-to-have skills found: ${req.preferred_skills.length - (req.preferred_missing || []).length}/${req.preferred_skills.length}` : '',
      titleLabels[req.title_match] || '',
      req.experience_required_years ? `${expLabels[req.experience_status] || 'Experience'} (${req.experience_required_years}+ years asked)` : '',
      req.education_required ? `Degree asked: ${req.education_required} (${req.education_status})` : '',
    ].filter(Boolean);
    const risky = (req.screening_risks || []).length;
    return `<section class="notice ${risky ? 'warn' : 'good'}"><div><strong>ATS screening check against your job description</strong><ul class="plain">${facts.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}${(req.screening_risks || []).map((item) => `<li><strong>Risk:</strong> ${escapeHtml(item)}</li>`).join('')}</ul></div></section>`;
  }

  function improvedResumeDownload(payload) {
    if (!payload.improved_resume || !payload.run_id) return '<p class="muted">Run the agent to prepare a final ATS-friendly resume download.</p>';
    const status = payload.improved_resume.status || 'preparing';
    if (status === 'preparing') return `<div class="btn-row"><span class="skeleton" style="width:220px;height:42px"></span><span class="muted">Preparing the validated base resume…</span></div>`;
    if (status === 'failed') return `<div class="notice bad"><span>Resume preparation failed: ${escapeHtml(payload.improved_resume.error || 'unknown error')}</span></div>`;
    const validation = payload.improved_resume.validation || {};
    const validationLabel = validation.passed
      ? `${validation.page_count || '?'} page PDF, render and factual checks passed`
      : `Validation needs review${validation.issues?.length ? `: ${validation.issues[0]}` : ''}`;
    return `<div class="btn-row">
        <a class="btn btn-primary" href="/api/runs/${encodeURIComponent(payload.run_id)}/improved-resume">Download ATS Resume DOCX</a>
        <a class="btn" href="/api/runs/${encodeURIComponent(payload.run_id)}/improved-resume.pdf">Download ATS Resume PDF</a>
        <span class="badge ${validation.passed ? 'good' : 'warn'}">${escapeHtml(validationLabel)}</span>
      </div><p class="faint" style="margin-top:10px">${payload.improved_resume.template_name ? `<span>${escapeHtml(`Template: ${payload.improved_resume.template_name}`)}</span> ` : ''}<span>Each job lead also has its own tailored resume.</span></p>`;
  }

  // ------------------------------------------------------- resume templates
  async function loadTemplates(runId) {
    try {
      templateCatalog = await UI.api(`/api/resume-templates?run_id=${encodeURIComponent(runId)}`);
      if (activePayload?.improved_resume && templateCatalog.statuses) {
        activePayload.improved_resume.template_statuses = { ...templateCatalog.statuses, ...(activePayload.improved_resume.template_statuses || {}) };
      }
    } catch (_) { templateCatalog = null; }
    const panel = $('templates-panel');
    if (panel) panel.innerHTML = templatesHtml();
  }

  // A drawn miniature of the layout, shown until the real page preview exists.
  function templateSketch(item) {
    const align = item.header_align === 'center' ? 'center' : 'start';
    const line = (width) => `<i style="width:${width}%"></i>`;
    const block = () => `<span class="sk-head" style="--accent:#${escapeHtml(item.accent)}">${item.heading_rule ? '<b></b>' : ''}</span>${line(92)}${line(84)}${line(70)}`;
    return `<div class="tpl-sketch" style="--accent:#${escapeHtml(item.accent)};text-align:${align}" aria-hidden="true">
      <span class="sk-name" style="margin-inline:${align === 'center' ? 'auto' : '0'}"></span>
      <span class="sk-contact" style="margin-inline:${align === 'center' ? 'auto' : '0'}"></span>
      ${block()}${block()}${block()}</div>`;
  }

  function templatesHtml() {
    const runId = activePayload?.run_id;
    if (!templateCatalog || !runId) return '<h3 id="templates-title">Resume templates</h3><div class="skeleton" style="height:180px;margin-top:12px"></div>';
    const improved = activePayload.improved_resume || {};
    const statuses = improved.template_statuses || {};
    const preferred = improved.preferred_template || templateCatalog.preferred_template;
    const recommended = templateCatalog.templates.find((item) => item.recommended);
    const cards = templateCatalog.templates.map((item) => {
      const key = item.key;
      const state = statuses[key] || {};
      const base = `/api/runs/${encodeURIComponent(runId)}/resume-templates/${encodeURIComponent(key)}`;
      const ready = state.status === 'ready';
      const badges = [
        item.recommended ? '<span class="badge warn">Recommended</span>' : '',
        key === improved.template ? '<span class="badge info">Your main resume</span>' : '',
        ready && state.passed ? '<span class="badge good">ATS check passed</span>' : '',
        key === preferred ? '<span class="badge">Used for tailored resumes</span>' : '',
      ].join('');
      const preview = ready
        ? `<button class="tpl-preview" type="button" data-preview="${escapeHtml(key)}" aria-label="Preview ${escapeHtml(item.name)}"><img src="${base}/preview" alt="" loading="lazy" onerror="this.parentElement.classList.add('no-image')">${templateSketch(item)}</button>`
        : `<div class="tpl-preview">${templateSketch(item)}</div>`;
      let actions;
      if (ready) {
        actions = `<div class="btn-row" style="gap:8px"><a class="btn btn-sm btn-primary" href="${base}/docx">DOCX</a><a class="btn btn-sm" href="${base}/pdf">PDF</a>`
          + (key !== preferred ? `<button class="btn btn-sm btn-quiet use-template" type="button" data-template="${escapeHtml(key)}">Use for tailored resumes</button>` : '') + '</div>';
      } else if (state.status === 'preparing') {
        actions = '<button class="btn btn-sm" type="button" disabled aria-busy="true">Building this template…</button>';
      } else {
        actions = `<button class="btn btn-sm prepare-template" type="button" data-template="${escapeHtml(key)}">${state.status === 'failed' ? 'Retry this template' : 'Build in this template'}</button>`
          + (state.status === 'failed' && state.error ? `<span class="faint">${escapeHtml(state.error)}</span>` : '');
      }
      return `<article class="tpl-card${item.recommended ? ' recommended' : ''}" aria-labelledby="tpl-${escapeHtml(key)}">
        ${preview}
        <div class="tpl-body">
          <div class="chips">${badges}</div>
          <h4 id="tpl-${escapeHtml(key)}">${escapeHtml(item.name)}</h4>
          <p class="faint">${escapeHtml(item.best_for)}</p>
          <p class="tpl-desc">${escapeHtml(item.description)}</p>
          ${actions}
        </div>
      </article>`;
    }).join('');
    return `<div class="panel-head"><div><h3 id="templates-title">Resume templates</h3>
        <p class="muted" style="max-width:72ch">Every template is a single text column with standard headings and no tables, icons or photos, so applicant tracking systems read it correctly. Each one is checked after it is built.</p></div></div>
      ${recommended ? `<div class="notice good" style="margin-bottom:16px"><span><strong>Recommended for you: ${escapeHtml(recommended.name)}.</strong> ${escapeHtml(recommended.reason || '')}</span></div>` : ''}
      <div class="tpl-grid">${cards}</div>`;
  }

  function openTemplatePreview(key) {
    const item = (templateCatalog?.templates || []).find((entry) => entry.key === key);
    const base = `/api/runs/${encodeURIComponent(activePayload.run_id)}/resume-templates/${encodeURIComponent(key)}`;
    $('drawer-title').textContent = item ? item.name : 'Resume template';
    $('drawer-body').innerHTML = `<img class="tpl-full" src="${base}/preview" alt="Page 1 of your resume in this template">
      <div class="btn-row"><a class="btn btn-primary" href="${base}/docx">Download DOCX</a><a class="btn" href="${base}/pdf">Download PDF</a></div>`;
    $('changes-drawer').showModal();
  }

  function buildDraftTemplate(applications) {
    const firstDraft = applications.find((item) => item.draft_message);
    if (!firstDraft) return '';
    const company = firstDraft.job?.company || '';
    let message = firstDraft.draft_message
      .split('\n')
      .filter((line) => !line.toLowerCase().startsWith('job link:'))
      .join('\n')
      .trim();
    if (company) message = message.split(company).join('[Company Name]');
    return message;
  }

  function draftCard(message) {
    return `<div class="panel-head" style="margin-bottom:12px"><p class="muted">Replace [Company Name] before applying to a selected job.</p><button class="btn btn-sm copy-draft" type="button">Copy template</button></div>
      <label class="sr-only" for="draft-message">Reusable recruiter message</label>
      <textarea id="draft-message" class="draft-message" readonly>${escapeHtml(message)}</textarea>`;
  }

  // ------------------------------------------------------ "what changed"
  function openChanges(artifactId, key) {
    const job = (activePayload?.jobs || []).find((item) => jobKey(item) === key);
    const info = activePayload?.improved_resume?.tailored_statuses?.[artifactId] || {};
    const changes = info.change_summary?.changes || [];
    const added = (info.change_summary?.added_skills || []).filter((item) => item.evidence);
    const base = `/api/runs/${encodeURIComponent(activePayload.run_id)}/tailored-resumes/${encodeURIComponent(artifactId)}`;
    $('drawer-title').textContent = job ? `Resume for ${job.title}` : 'Tailored resume';
    $('drawer-body').innerHTML = `
      ${job ? `<p class="muted">${escapeHtml(job.company || '')}${job.location ? `, ${escapeHtml(job.location)}` : ''}</p>` : ''}
      <section><h3 style="margin-bottom:8px">What changed</h3>${changes.length ? `<ul class="plain">${changes.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '<p class="muted">No changes were recorded.</p>'}</section>
      ${added.length ? `<section><h3 style="margin-bottom:8px">Added skills and their evidence</h3><ul class="list">${added.map((item) => `<li><span class="chip added">${escapeHtml(item.skill)}</span><p class="muted" style="margin-top:6px">Supported by: “${escapeHtml(item.evidence)}”</p></li>`).join('')}</ul></section>` : ''}
      <div class="notice good"><span>No employers, dates, degrees or metrics were changed.</span></div>
      <div class="btn-row"><a class="btn btn-primary" href="${base}/docx">Download DOCX</a><a class="btn" href="${base}/pdf">Download PDF</a></div>`;
    $('changes-drawer').showModal();
  }
  $('drawer-close').addEventListener('click', () => $('changes-drawer').close());
  $('changes-drawer').addEventListener('click', (event) => { if (event.target === $('changes-drawer')) $('changes-drawer').close(); });

  // ----------------------------------------------------------- feedback
  async function loadFeedback(runId) {
    if (!runId) return;
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/feedback`);
      if (!response.ok) return;
      activeFeedback = (await response.json()).feedback || {};
      document.querySelectorAll('.feedback-row').forEach((row) => {
        const saved = activeFeedback[row.dataset.job] || {};
        row.querySelector('.fb-yes').setAttribute('aria-pressed', String(saved.verdict === 'relevant'));
        if (saved.verdict === 'not_relevant') row.querySelector('.fb-no').value = saved.reason || 'other';
        row.querySelector('.saved').textContent = saved.verdict ? 'Saved' : '';
      });
      renderOverview(activePayload);
    } catch (_) { /* feedback is optional */ }
  }
  async function sendFeedback(row, verdict, reason) {
    const runId = activePayload?.run_id;
    if (!runId) return;
    const saved = row.querySelector('.saved');
    saved.textContent = 'Saving…';
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job_id: row.dataset.job, verdict, reason }) });
      const data = await responsePayload(response);
      if (!response.ok) throw new Error(data.detail || 'Could not save.');
      activeFeedback[row.dataset.job] = { verdict, reason };
      row.querySelector('.fb-yes').setAttribute('aria-pressed', String(verdict === 'relevant'));
      if (verdict === 'relevant') row.querySelector('.fb-no').value = '';
      saved.textContent = 'Saved. Thanks, this improves your matches.';
    } catch (error) {
      saved.textContent = error.message;
    }
  }

  // ----------------------------------------------------------- approvals
  function statusTag(status) {
    const labels = { pending_approval: ['Waiting for approval', 'warn'], scheduled: ['Sending soon, undo available', 'info'], sending: ['Sending', 'info'], sent: ['Sent', 'good'], rejected: ['Rejected', 'bad'], failed: ['Failed', 'bad'], undone: ['Undone', ''] };
    const [label, kind] = labels[status] || [status, ''];
    return `<span class="badge ${kind}">${escapeHtml(label)}</span>`;
  }
  async function loadApprovals() {
    try {
      const response = await fetch('/api/approvals');
      if (!response.ok) return;
      approvals = await response.json();
    } catch (_) { return; }
    const items = approvals.items || [];
    const pending = items.filter((item) => item.status === 'pending_approval');
    setCount('nav-approvals-count', pending.length || '');
    $('stat-approvals').textContent = pending.length;
    $('approvals-summary').textContent = `Approved emails go out after ${approvals.undo_seconds ?? 60} seconds unless you press Undo. Today: ${approvals.sent_today ?? 0} of ${approvals.daily_cap ?? 0} sent. The same recruiter is not emailed twice within ${approvals.duplicate_window_days ?? 30} days.`;
    const host = $('approvals-list');
    if (!items.length) {
      host.innerHTML = `<div class="empty"><strong>No emails to review</strong><p class="muted">Set Application mode to “Email recruiters after my approval” on Run &amp; profile. Drafts appear here and nothing is sent until you approve.</p><a class="btn" href="#run">Open Run &amp; profile</a></div>`;
    } else {
      // Keep any edits the user is typing: only re-render cards whose status changed.
      const focused = document.activeElement && document.activeElement.closest('.approval-card');
      if (focused && host.querySelector(`.approval-card[data-id="${CSS.escape(focused.dataset.id)}"][data-status="pending_approval"]`) && items.some((i) => String(i.id) === focused.dataset.id && i.status === 'pending_approval')) {
        // user is editing a pending card; skip this refresh
      } else {
        host.innerHTML = items.slice(0, 20).map((item) => `
          <article class="approval-card" data-id="${escapeHtml(item.id)}" data-status="${escapeHtml(item.status)}" aria-labelledby="ap-${escapeHtml(item.id)}">
            <header><div><h3 id="ap-${escapeHtml(item.id)}">${escapeHtml(item.title)}${item.company ? `, ${escapeHtml(item.company)}` : ''}</h3><p class="muted" style="margin-top:4px">To ${escapeHtml(item.recipient)}${item.has_attachment ? ', resume attached' : ''}</p></div>${statusTag(item.status)}</header>
            ${item.status === 'pending_approval' ? `
              <label class="field">Subject<input class="ap-subject" value="${escapeHtml(item.subject)}" maxlength="200"></label>
              <label class="field">Message<textarea class="ap-body">${escapeHtml(item.body)}</textarea></label>
              <div class="btn-row"><button type="button" class="btn btn-primary ap-approve">Approve and send</button><button type="button" class="btn btn-danger ap-reject">Reject</button><span class="muted ap-status" aria-live="polite"></span></div>`
            : item.status === 'scheduled' ? `<div class="btn-row"><button type="button" class="btn ap-undo">Undo (${escapeHtml(item.undo_seconds_left)}s)</button><span class="muted ap-status" aria-live="polite"></span></div>`
            : item.error ? `<p class="muted">${escapeHtml(item.error)}</p>` : ''}
          </article>`).join('');
      }
    }
    clearTimeout(approvalTimer);
    if (items.some((item) => item.status === 'scheduled' || item.status === 'sending')) approvalTimer = setTimeout(loadApprovals, 3000);
    renderOverview(activePayload);
  }
  async function approvalAction(card, action) {
    const statusNode = card.querySelector('.ap-status');
    const body = action === 'approve'
      ? { subject: card.querySelector('.ap-subject').value, body: card.querySelector('.ap-body').value, confirm: true }
      : action === 'reject' ? { reason: 'user_rejected' } : {};
    try {
      await UI.api(`/api/approvals/${encodeURIComponent(card.dataset.id)}/${action}`, { method: 'POST', body });
      UI.toast({ approve: 'Approved. Sending after the undo window.', reject: 'Rejected. This email will not be sent.', undo: 'Undone. The email is back in your queue.' }[action], action === 'reject' ? 'warn' : 'good');
      if (document.activeElement) document.activeElement.blur();
      loadApprovals();
    } catch (error) {
      if (statusNode) statusNode.textContent = error.message;
      const approve = card.querySelector('.ap-approve');
      if (approve) approve.disabled = false;
    }
  }

  // ------------------------------------------------------ resume status
  function scheduleResumeStatusPoll(immediate = false) {
    if (resumeStatusTimer) clearTimeout(resumeStatusTimer);
    const improved = activePayload?.improved_resume || {};
    const tailored = Object.values(improved.tailored_statuses || {});
    const templates = Object.values(improved.template_statuses || {});
    const pending = improved.status === 'preparing' || [...tailored, ...templates].some((item) => item.status === 'preparing');
    if (!pending || !activePayload?.run_id) return;
    resumeStatusTimer = setTimeout(refreshResumeStatus, immediate ? 100 : 1500);
  }
  async function refreshResumeStatus() {
    if (!activePayload?.run_id) return;
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(activePayload.run_id)}/resume-status`);
      const status = await responsePayload(response);
      if (!response.ok) throw new Error(status.detail || 'Unable to read resume status.');
      const snapshot = (improved) => JSON.stringify([improved?.tailored_statuses || {}, improved?.template_statuses || {}, improved?.preferred_template || '']) + (improved?.status || '');
      const before = snapshot(activePayload.improved_resume);
      activePayload.improved_resume = {
        ...activePayload.improved_resume,
        status: status.base?.status || activePayload.improved_resume?.status,
        validation: status.base?.validation || activePayload.improved_resume?.validation,
        error: status.base?.error || '',
        tailored_statuses: status.tailored || {},
        template_statuses: status.templates || {},
        template: status.template || activePayload.improved_resume?.template,
        preferred_template: status.preferred_template || activePayload.improved_resume?.preferred_template,
      };
      const after = snapshot(activePayload.improved_resume);
      if (before !== after) { renderJobs(); renderResume(activePayload); }
      scheduleResumeStatusPoll();
    } catch (_) {
      resumeStatusTimer = setTimeout(refreshResumeStatus, 3000);
    }
  }

  // ----------------------------------------------------- event delegation
  document.addEventListener('change', (event) => {
    const select = event.target.closest('.fb-no');
    if (select && select.value) sendFeedback(select.closest('.feedback-row'), 'not_relevant', select.value);
  });
  document.addEventListener('click', async (event) => {
    const openJob = event.target.closest('.open-job');
    if (openJob && activePayload?.run_id) {
      const beacon = JSON.stringify({ run_id: activePayload.run_id, job_id: openJob.dataset.job, rank: Number(openJob.dataset.rank || 0), portal: openJob.dataset.portal });
      try { navigator.sendBeacon('/api/events/lead-click', new Blob([beacon], { type: 'application/json' })); } catch (_) { /* tracking is best effort */ }
    }
    const yes = event.target.closest('.fb-yes');
    if (yes) { sendFeedback(yes.closest('.feedback-row'), 'relevant', ''); return; }
    if (event.target.closest('#clear-filters')) {
      Object.assign(filters, { text: '', portal: '', minScore: 0 });
      $('filter-text').value = ''; $('filter-score').value = '0'; $('filter-score-value').textContent = '0%';
      renderJobs();
      return;
    }
    const prepareTemplate = event.target.closest('.prepare-template');
    if (prepareTemplate && activePayload?.run_id) {
      const key = prepareTemplate.dataset.template;
      prepareTemplate.disabled = true;
      try {
        const result = await UI.api(`/api/runs/${encodeURIComponent(activePayload.run_id)}/resume-templates/${encodeURIComponent(key)}/prepare`, { method: 'POST' });
        const improved = activePayload.improved_resume || (activePayload.improved_resume = {});
        improved.template_statuses = { ...(improved.template_statuses || {}), [key]: { status: result.status } };
        $('templates-panel').innerHTML = templatesHtml();
        if (result.status === 'ready') refreshResumeStatus(); else scheduleResumeStatusPoll(true);
      } catch (error) {
        prepareTemplate.disabled = false;
        UI.toast(error.message, 'bad');
      }
      return;
    }
    const useTemplate = event.target.closest('.use-template');
    if (useTemplate && activePayload?.run_id) {
      try {
        const result = await UI.api(`/api/runs/${encodeURIComponent(activePayload.run_id)}/resume-template`, { method: 'POST', body: { template: useTemplate.dataset.template } });
        activePayload.improved_resume.preferred_template = result.preferred_template;
        $('templates-panel').innerHTML = templatesHtml();
        UI.toast(`Tailored resumes will use ${result.name}.`, 'good');
      } catch (error) {
        UI.toast(error.message, 'bad');
      }
      return;
    }
    const previewTemplate = event.target.closest('[data-preview]');
    if (previewTemplate) { openTemplatePreview(previewTemplate.dataset.preview); return; }
    const changes = event.target.closest('.show-changes');
    if (changes) { openChanges(changes.dataset.artifactId, changes.dataset.job); return; }
    const approvalCard = event.target.closest('.approval-card');
    if (approvalCard) {
      const approveButton = event.target.closest('.ap-approve');
      if (approveButton) {
        // Two-step confirmation instead of a blocking browser dialog.
        if (approveButton.dataset.confirm !== 'yes') {
          approveButton.dataset.confirm = 'yes';
          approveButton.textContent = 'Confirm: send to this recruiter';
          approvalCard.querySelector('.ap-status').textContent = 'Check the recipient and message, then confirm.';
          return;
        }
        approveButton.disabled = true;
        approvalAction(approvalCard, 'approve');
        return;
      }
      if (event.target.closest('.ap-reject')) { approvalAction(approvalCard, 'reject'); return; }
      if (event.target.closest('.ap-undo')) { approvalAction(approvalCard, 'undo'); return; }
    }
    const prepareButton = event.target.closest('.prepare-tailored');
    if (prepareButton) {
      if (!activePayload?.run_id) return;
      const artifactId = prepareButton.dataset.artifactId;
      prepareButton.disabled = true;
      prepareButton.textContent = 'Preparing resume…';
      const statuses = { ...(activePayload.improved_resume?.tailored_statuses || {}) };
      statuses[artifactId] = { status: 'preparing' };
      activePayload.improved_resume = { ...activePayload.improved_resume, tailored_statuses: statuses };
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(activePayload.run_id)}/tailored-resumes/${encodeURIComponent(artifactId)}/prepare`, { method: 'POST' });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(payload.detail || 'Unable to prepare resume.');
        scheduleResumeStatusPoll(true);
      } catch (error) {
        statuses[artifactId] = { status: 'failed', error: error.message };
        renderJobs();
        UI.toast(error.message, 'bad');
      }
      return;
    }
    const showMoreButton = event.target.closest('#show-more-jobs');
    if (showMoreButton) {
      if (!activePayload?.run_id || !activePayload?.job_page?.next_cursor) return;
      showMoreButton.disabled = true;
      showMoreButton.textContent = 'Loading jobs…';
      try {
        const query = new URLSearchParams({ cursor: activePayload.job_page.next_cursor, limit: '8' });
        const response = await fetch(`/api/runs/${encodeURIComponent(activePayload.run_id)}/jobs?${query.toString()}`);
        const page = await response.json();
        if (!response.ok) throw new Error(page.detail || 'Unable to load more jobs.');
        const known = new Set(activePayload.jobs.map(jobKey));
        const additions = page.jobs.filter((job) => !known.has(jobKey(job)));
        activePayload = { ...activePayload, jobs: [...activePayload.jobs, ...additions], job_page: page.page };
        renderJobs();
        renderOverview(activePayload);
      } catch (error) {
        showMoreButton.disabled = false;
        showMoreButton.textContent = error.message;
      }
      return;
    }
    const copy = event.target.closest('.copy-draft');
    if (copy) {
      const textarea = $('draft-message');
      try {
        await navigator.clipboard.writeText(textarea.value);
        UI.toast('Template copied.', 'good');
      } catch (_) {
        textarea.select();
        UI.toast('Press Ctrl+C (or Cmd+C) to copy the selected text.', 'warn');
      }
    }
  });

  // --------------------------------------------------------------- boot
  timezoneInput.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  $('filter-score-value').textContent = '0%';
  showView(false);
  renderOverview(null);
  renderJobs();
  renderResume(null);
  refreshDashboard();
  loadApprovals();
  setInterval(refreshDashboard, 15000);
})();
