# Mock Interview Evaluation

Each quick, standard, or deep interview section produces a feedback report when the user finishes it. The report includes:

- an overall score and readiness label;
- communication, technical accuracy, confidence, and problem-solving scores;
- strengths, weaknesses, and prioritized improvement areas;
- feedback for each submitted answer; and
- a four-step preparation plan for the next interview.

## Cost Model

The evidence-based evaluator runs locally and requires no API key. It scores the submitted text using question alignment, clarity, reasoning, ownership, validation, and outcome signals. Code answers receive static checks for relevant structure, logic, validation, readability, and incomplete placeholders. Code is never compiled or executed.

An optional LLM can refine the report. To control cost, the app makes at most one request after a complete interview section and makes no request for very short submissions. The LLM scores are blended 35 percent with the 65 percent local baseline, so an external response cannot fully replace the transparent evidence score. A timeout, provider error, invalid schema, or missing key falls back to the local report.

Configure either the shared `JOB_AGENT_LLM_*` variables or the interview-only overrides:

```env
JOB_AGENT_INTERVIEW_LLM_API_KEY=
JOB_AGENT_INTERVIEW_LLM_MODEL=gpt-4o-mini
JOB_AGENT_INTERVIEW_LLM_ENDPOINT=https://api.openai.com/v1/responses
```

## Privacy And Interpretation

Only questions, categories, submitted answers, and answer types are included in an enabled LLM request. Profile contact fields, camera frames, and audio are excluded. Confidence measures directness, ownership, completeness, and hedging in the submitted wording; it is not an emotion, facial, voice, or personality assessment.
