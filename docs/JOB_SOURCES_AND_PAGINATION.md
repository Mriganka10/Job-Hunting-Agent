# Job Sources and Pagination

## Source Strategy

The default search order is Remotive, Arbeitnow, LinkedIn, and Naukri.

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
