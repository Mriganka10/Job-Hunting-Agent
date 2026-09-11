# Mock Interview Evaluation And Feedback

Every completed Quick, Standard, or Deep interview automatically produces a saved evaluation report. The evaluator works without an external service and can optionally blend its evidence-based baseline with a strict-JSON LLM assessment.

## Report contents

- Overall score and readiness level.
- Communication, technical accuracy, confidence, and problem-solving scores from 0 to 100.
- Strengths, weaknesses, and prioritized improvement areas.
- Per-answer scores and corrective feedback.
- A personalized four-step preparation plan based on the weakest dimensions and question categories.
- A measurable checkpoint for the next mock interview.

Confidence is inferred from answer completeness, direct wording, ownership, and hedging. It is not a voice-tone or biometric assessment. Code answers receive static checks for relevance, completeness, readability, basic structural balance, validation, and problem-solving signals; code is never executed.

## Optional AI assessment

Set `JOB_AGENT_LLM_API_KEY` to reuse the general configured model, or use the interview-specific overrides:

```env
JOB_AGENT_INTERVIEW_LLM_API_KEY=
JOB_AGENT_INTERVIEW_LLM_MODEL=
JOB_AGENT_INTERVIEW_LLM_ENDPOINT=
```

When configured, interview questions and submitted answers are sent to that endpoint. Its assessment is schema validated, sanitized, and blended at 35 percent with the deterministic baseline. A timeout, invalid response, or missing key automatically returns the complete evidence-based report instead.

The response field `evaluation_mode` is `hybrid_ai` when AI feedback was blended and `evidence_based` when the local evaluator was used alone.
