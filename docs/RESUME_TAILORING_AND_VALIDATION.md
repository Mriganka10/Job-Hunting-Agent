# Resume Tailoring and Render Validation

## Artifact Model

Every full run creates:

- One profile-aware base resume in DOCX and PDF.
- One separately tailored DOCX/PDF pair for every ranked job lead when `tailor_each_job = true`.
- A JSON validation report and rasterized PNG pages for each artifact.

The web dashboard exposes the base pair above the results and a tailored DOCX/PDF link in each job row. All download routes verify that the authenticated user owns the run and artifact.

## Evidence-Preserving Tailoring

Tailoring uses the job title, description, and optional pasted job description to rank existing evidence. It may:

1. Target the professional summary to the job title.
2. Move supported skills and skill categories nearer the beginning.
3. Reorder bullets within their original experience entry.
4. Reorder projects by relevance.

It does not add missing technologies, employers, degrees, certifications, dates, metrics, or outcomes. The tailoring report lists matched evidence, unsupported JD terms that were not inserted, and weak bullets that need additional truthful evidence from the user.

## Factual and Semantic Gates

Before writing an artifact, the consistency validator compares output claims with the uploaded resume and explicit profile values. Unsupported numeric claims, low-source-support factual entries, and high-confidence cross-section mismatches block generation. Each accepted experience, project, education, certification, achievement, publication, and volunteering entry receives a source-token coverage measurement.

This gate intentionally cannot invent missing scale or impact. A weak bullet remains truthful and is reported as weak evidence until the candidate supplies a real quantity, outcome, or scope.

## Page Budget

`resume_page_target` accepts 1, 2, or 3 and defaults to 2. The builder tries four levels:

1. Full supported content.
2. Reduced optional-item counts and up to six bullets per role.
3. Shorter summary, fewer optional sections, and up to four bullets per role.
4. Compact spacing, essential optional evidence, and up to three bullets per role.

Experience roles, education, and contact details are not removed merely to satisfy the page target. If the target still cannot be met, the artifact is returned with `page_target_met = false` and a validation issue rather than silently deleting core history.

## Render Validation

The final PDF is rasterized page by page with PyMuPDF, with `pdftoppm` as a fallback renderer. Validation checks page count, page boxes, blank or over-dense pages, out-of-bounds text blocks, PDF text recovery, ATS-hostile DOCX structures, semantic section consistency, and source fidelity.

If LibreOffice is available, the DOCX is converted to the final PDF and `pdf_strategy` is `libreoffice_docx_render`. Without LibreOffice, ReportLab builds a PDF from the same structured sections and `pdf_strategy` is `parallel_semantic_render`; `docx_rendered` remains false so DOCX/PDF render parity is never implied.

## Configuration

```toml
[application]
mode = "draft"
cover_letter_tone = "concise"
data_dir = "data"
resume_page_target = 2
tailor_each_job = true
```

Install document dependencies with:

```powershell
pip install -e ".[docs]"
```

Install LibreOffice on production workers when the final PDF must be a direct rendering of the DOCX rather than a parallel semantic render.
