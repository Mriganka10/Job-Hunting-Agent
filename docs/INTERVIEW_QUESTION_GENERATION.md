# Dynamic Mock Interview Questions

The mock interview keeps a persistent question history for each authenticated user. Starting a session reads that user's recent interview records, selects unseen questions first, and stores the new set before returning it.

## Round behavior

- **Quick Confidence Round:** starts with behavioral, role, stakeholder, and delivery questions.
- **Standard Round:** balances role evidence, technical judgment, system design, quality, communication, and delivery.
- **Deep Practice Round:** prioritizes system design, technical depth, troubleshooting, and relevant specialist topics.

Selection rotates across categories before taking a second question from any category. Within each category, never-asked questions rank ahead of previously asked questions. If the available bank is exhausted, the least-used and least-recently-used questions are selected first.

## Question bank

Every profile receives seven broad competency categories. Data engineering, cloud, and AI categories are added when the user's target roles or skills support them. Role and skill names are inserted only into questions where they provide useful interview context.

The start-session response includes a `selection` object with `new_questions`, `reused_questions`, and `history_questions_considered`. Each question also includes a stable topic and a `previously_asked` flag.

Question history uses the existing `mock_interview_records.questions` data, so no migration is required and history survives application restarts.
