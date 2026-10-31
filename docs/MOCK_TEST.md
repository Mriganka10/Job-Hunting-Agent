# Mock Test

The Mock Test section (`/mock-test`) sits beside the Mock Interview studio. A signed-in user picks a job lead from their recent runs (or general practice from their profile), takes a timed multiple-choice test, and receives a scorecard.

## How a test is built

File: `src/job_hunting_agent/mock_test.py`, question bank in `src/job_hunting_agent/mock_test_bank.py`.

1. **Topics come from the job lead.** The title, description, Matched skills, Additional Skills, missing required skills and Naukri key skills are scored against 22 technical topics (Python, SQL, ML, Deep Learning, NLP, Computer Vision, LLMs/RAG, Data Engineering, Cloud, Docker/Kubernetes, React, Java, DSA and more). Title keywords count three times as much as description keywords, and role patterns (for example "Data Engineer") add their core topics.
2. **About 20% of each test is aptitude and logical reasoning**, matching typical campus and screening rounds.
3. **Lengths:** quick (10), standard (20) and full (30) questions. Difficulty can be mixed (about 30% easy / 50% medium / 20% hard) or skewed towards easy, medium or hard.
4. **Fresh questions on retake:** questions the user has already seen are used only to fill gaps.
5. **Question order and option order are shuffled** for every test.
6. **Time limit:** 60 seconds per easy question, 75 per medium and 90 per hard, rounded up to the minute.

### Optional AI-written questions

For job skills the bank does not cover (for example "Great Expectations"), up to four extra MCQs can be generated when `JOB_AGENT_MOCK_TEST_LLM_API_KEY` or `JOB_AGENT_LLM_API_KEY` is set. Each item must have four distinct options, exactly one valid answer index and no "all/none of the above"; anything else is discarded. Generated questions are labelled "AI-generated" in the test and the review. Set `JOB_AGENT_MOCK_TEST_LLM=off` to use only the curated bank. Without a key the feature works fully offline.

## Integrity

- The answer key is stored in `mock_test_records` and is never sent to the browser before submission.
- Elapsed time is measured on the server from the stored start time. Late submissions are graded but flagged in the scorecard.
- A test can be graded once; resubmitting returns the original scorecard.
- Every record is scoped to the signed-in email address.

## Scorecard

Score and percentage, accuracy on attempted questions, correct/incorrect/unanswered counts, grade (Excellent ≥ 85%, Good ≥ 70%, Average ≥ 50%), a readiness verdict for the job, topic and difficulty breakdowns with study tips, strengths, improvement against the user's previous best for the same job, time used, and a full review with the correct answer and an explanation for every question. There is no negative marking.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/mock-test` | Mock Test page (supports `?job=<portal:id>` and `?test=<id>`) |
| GET | `/api/mock-test/options` | Job leads from the user's three most recent runs |
| POST | `/api/mock-test/start` | `{job_id, run_id, length, difficulty}` → test without the answer key |
| POST | `/api/mock-test/submit` | `{test_id, answers: {question_id: option_index}, question_seconds}` → scorecard |
| GET | `/api/mock-test/history` | Last 10 completed tests |
| GET | `/api/mock-test/{id}` | Resume an in-progress test or reopen a scorecard |

## Adding questions

Add tuples to a topic in `mock_test_bank.py` as `(difficulty, question, (four options), correct_index, explanation)`. The correct option can be listed in any position because options are shuffled. `tests/test_mock_test.py` checks every bank question for shape and uniqueness.


## Question standards (October 2026)

- **Code questions.** Technical roles get at least 40% code-reading questions among the technical questions (predict the output, find the bug, estimate complexity) in Python, SQL, JavaScript, Java, C/C++, DSA and pandas (`mock_test_code_bank.py`). Code is shown in a monospaced block; SQL questions show the sample table. Every answer key is checked by running the snippet with the real interpreter or compiler (`python scripts/verify_code_questions.py`, also in CI). Code questions get 30 extra seconds.
- **Exact difficulty mix.** The chosen mix (Mixed, Mostly easy/medium/hard) is applied to the whole test exactly when the bank allows, with nearest-level fallback. "Mixed" follows the candidate's level: entry 40/45/15, mid 25/50/25, senior 15/45/40 (easy/medium/hard). The test header shows the actual mix.
- **Difficulty measured from real attempts.** Once a question has 30+ graded attempts, its level follows its measured p-value (over 0.85 easy, 0.45-0.85 medium, under 0.45 hard).
- **Non-technical roles** (HR, sales, operations) get aptitude, reasoning and verbal-ability questions instead of programming topics.
- **Feedback.** Every reviewed question has "Report a problem with this question"; reports and item-analysis flags appear on `/admin/metrics`.
- **Progress Reports.** `/progress` shows daily and weekly trends per job.
