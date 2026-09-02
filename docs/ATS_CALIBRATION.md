# ATS Calibration

The scorer ships with a versioned benchmark of 60 anonymized resume archetypes across ten role families and six quality tiers. The benchmark is a regression and calibration aid; it is not a claim that one vendor's proprietary ATS will produce the same score.

Run it with:

```bash
python scripts/calibrate_ats.py --output data/reports/ats_calibration.json
```

## Private External Validation

For market validation, collect 50-100 resumes with candidate consent, remove unnecessary personal data, and have at least two qualified reviewers independently assign expected score ranges. Keep those resumes outside Git. Create a JSON manifest beside the private files:

```json
{
  "cases": [
    {
      "case_id": "reviewed-001",
      "resume_path": "resumes/reviewed-001.pdf",
      "role_family": "data_engineering",
      "target_role": "Data Engineer",
      "quality_tier": "human_reviewed",
      "expected_min": 72,
      "expected_max": 82,
      "job_description": "The consented target job description"
    }
  ]
}
```

Then run:

```bash
python scripts/calibrate_ats.py --manifest private/calibration.json --output data/reports/private-calibration-result.json
```

The report includes expected-band coverage and mean absolute error by role. Treat coverage below 90% or mean absolute error above six points as a release blocker until the scoring rules or reviewer baselines are reconciled.

## Semantic Matching

Default installations use TF-IDF matching and disclose that fallback in the ATS report. For trained semantic embeddings, install:

```bash
pip install -e ".[semantic]"
```

Set `JOB_AGENT_ENABLE_LOCAL_EMBEDDINGS=true`. The default local model is `sentence-transformers/all-MiniLM-L6-v2`. An OpenAI-compatible embedding endpoint can be configured instead. Provider failures fall back safely and reduce the confidence value rather than silently presenting lexical matching as a model embedding.

## Layout Validation

PyMuPDF is a standard project dependency and provides pixel-level PDF rendering. DOCX files always receive OOXML checks for tables, columns, drawings, text boxes, page breaks, and header contact information. When LibreOffice is available, DOCX files are converted temporarily and rendered for the same pixel-level checks. The report explicitly states whether rendering occurred.
