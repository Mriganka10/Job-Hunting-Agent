# Job Sources and Pagination

## Source Strategy

The default search order (`DEFAULT_PORTALS` in `config.py`) is Himalayas, Remotive, Arbeitnow, LinkedIn, Naukri, Jobicy, Remote OK, Adzuna, Careerjet, Jooble and JSearch (Google for Jobs). Direct sources come first so that when the same job also appears on an aggregator, the original posting wins de-duplication.

| Source | Access | Coverage | Key |
| --- | --- | --- | --- |
| Himalayas, Remotive, Arbeitnow | Official JSON feeds | Remote jobs (filtered to India-eligible) | none |
| LinkedIn, Naukri | Best-effort public pages | Indian city jobs | none |
| Jobicy | Official API, fetched at most hourly | Remote jobs; kept only when open to India | none |
| Remote OK | Official API, fetched at most hourly; links back to Remote OK | Remote jobs; kept only when open to India | none |
| Adzuna (`in`) | Official API | Indian city and remote jobs aggregated from many boards | `JOB_AGENT_ADZUNA_APP_ID`, `JOB_AGENT_ADZUNA_APP_KEY` |
| Careerjet (`en_IN`) | Official v4 API (basic auth); needs the searching user's IP and browser | Indian city jobs | `JOB_AGENT_CAREERJET_API_KEY` |
| Jooble | Official API | Indian city jobs aggregated from many boards | `JOB_AGENT_JOOBLE_API_KEY` |
| JSearch (Google for Jobs) | Licensed API over the Google for Jobs index (RapidAPI or OpenWeb Ninja) | Indeed, Foundit, WorkIndia, Shine, Glassdoor, TimesJobs and company career sites in India; each lead is labelled with its original publisher | `JOB_AGENT_JSEARCH_API_KEY` |

### Indeed, Foundit and WorkIndia

None of these portals offers a job-search API to third parties, and their sites block automated access, so the agent does not scrape them. They are covered in two compliant ways:

1. **JSearch (Google for Jobs).** These portals publish their listings to Google for Jobs. With `JOB_AGENT_JSEARCH_API_KEY` set, the `jsearch` adapter returns those listings with the publisher as the portal (`indeed`, `foundit`, `workindia`, ...), the apply link, salary when given, required skills and experience, and "also listed on" publishers. Only India-based or remote listings are kept. Each query uses quota (free plan: 200 requests a month), so a run sends at most `JOB_AGENT_JSEARCH_QUERIES_PER_RUN` (default 3) queries and results are cached for six hours across users.
2. **Ready-made portal searches.** The dashboard shows "Search more portals directly" links that open the same role, city, recency and experience search on Indeed (`in.indeed.com`), Foundit (`foundit.in/srp/results`) and WorkIndia (`workindia.in/jobs-in-<city>/`).

Keyed sources switch on only when their key is set. All partner adapters (`partner_sources.py`) honour the run's search budget, stop after two failed requests, cache responses, never log URLs (which may contain keys), and keep the provider's attribution and canonical link. Adzuna, Careerjet and Jooble links are click-tracking redirects, so link validation skips them. Aggregator descriptions are short snippets, so those leads more often show "Experience requirement unverified".

- Remotive uses its documented remote-jobs JSON feed. Results retain the feed ID, publication date, salary text, job type, category, attribution, and the feed's documented delay metadata.
- Arbeitnow uses its documented paginated job-board JSON feed. Results retain the slug, creation date, remote flag, tags, and an expiry inferred from the board's 30-day removal policy.
- LinkedIn and Naukri remain best-effort public HTML adapters. They parse structured fields when present and fall back to portal search-result links when public markup is blocked or changed.

An adapter being marked `source_validated` means it uses a known structured source contract. It does not mean every employer claim has been independently verified.

## Lead Validation

`JobLead` carries source ID, posting and expiry timestamps, salary values/text, workplace mode, employment type, normalized company name, freshness evidence, destination-link state, source provenance, and source-specific metadata.

Before ranking, the validator:

1. Parses and normalizes dates, salary, workplace mode, and employment type.
2. Rejects postings older than `freshness_days` when a posting date is available.
3. Rejects jobs whose explicit or policy-inferred expiry is in the past.
4. Checks destination URLs with bounded concurrent requests when `validate_job_links = true`.
5. Removes links confirmed as expired while preserving protected or rate-limited links with an honest status.
6. Normalizes legal company suffixes and known aliases, then removes exact and conservative fuzzy duplicates across sources.

Unknown posting dates remain eligible but are labeled unverified. Link checks cannot guarantee that a still-open HTTP page is accepting applications; they prevent confirmed dead or expired destinations from being presented as active.

## Server-Side Show More

The database stores the complete ranked result set. The initial dashboard/run response exposes eight jobs, the total count, and an opaque next cursor. The browser calls:

```text
GET /api/runs/{run_id}/jobs?cursor={cursor}&limit=8
```

The endpoint requires the current authenticated user to own the run. Cursors contain only the run ID and next offset, are signed with the application secret, and cannot be reused for another run or modified without rejection. Page size is restricted to 1-25 jobs.

This is application-level server pagination over the persisted run result. Upstream source pagination happens inside each adapter during discovery; clicking `Show More` does not re-query external portals or send the complete job set to the browser.

## Configuration

```toml
[search]
max_jobs_per_portal = 10
freshness_days = 7
include_remote = true
validate_job_links = true
portals = ["remotive", "arbeitnow", "linkedin", "naukri"]
```

Disable link checks only in constrained development environments. Public feeds and HTML portals can change, rate-limit, or become unavailable, so adapters fail independently and the remaining sources continue to run.

## Recommendation Quality

`relevance_corpus.py` holds six labelled candidate profiles (fresher ML engineer, data analyst, Java backend, senior data engineer, fresher frontend, DevOps) and realistic postings, including traps: similar titles (Data Entry Operator), wrong city, wrong seniority, foreign-only remote, technology-named titles (React JS Developer, Power BI Developer). Run:

```bash
python scripts/evaluate_job_relevance.py
```

It reports precision, recall, nDCG@10 and leaks (postings that must never be recommended) and exits non-zero when a gate fails (precision ≥ 0.95, recall ≥ 0.9, nDCG@10 ≥ 0.9, zero leaks). `tests/test_relevance.py` enforces the same gates, repeats them with every LinkedIn description blocked, and runs the corpus through the real `JobHuntingAgent.search` pipeline. Add new labelled cases whenever a bad or missing recommendation is reported.

Role matching understands role families: a title naming a technology counts for the candidate's target role only when that technology is one of the candidate's own skills (a Frontend Developer with React matches "React JS Developer"; a Java backend candidate is not matched to "Python Developer").

## Additional Skills

Every lead gets an `additional_skills_status` in `source_metadata`: `added`, `already_listed`, `no_evidence`, `no_requirements` or `description_unavailable`, and the dashboard shows the matching explanation instead of a blank cell. An addition is a skill the posting asks for, that the candidate's own resume text supports, and that the base ATS resume's skills section does not already show. Resumes without a Skills heading are compared against the skills section the builder generates for them.
