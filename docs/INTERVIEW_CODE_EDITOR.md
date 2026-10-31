# Mock Interview Code Editor

Coding and query prompts now carry `answer_mode` and `editor_language` metadata. The interview page uses that metadata to replace the spoken-response control with a dedicated code notepad in the right sidebar.

## Behavior

- Writing, implementation, debugging, refactoring, and pseudocode prompts open the editor automatically.
- Conceptual technical questions continue to use the existing speech and text response workflow.
- SQL, Python, C++, C, Java, JavaScript, TypeScript, C#, Go, Rust, PHP, Ruby, Kotlin, Swift, Scala, R, Shell, HTML/CSS, Dart, MATLAB, Perl, Lua, GraphQL, and MongoDB Query have named language options.
- Any other programming or query language can use `Other / Plain text` without losing formatting.
- The Tab key inserts two spaces in the editor.
- Submitted code is escaped and rendered in a preformatted transcript block with its selected language.

## Coding problems

Technical interviews (developer, engineer, data, QA, DevOps titles, or a profile with programming languages) reserve coding slots: 1 in quick, 2 in standard and 3 in deep mode (`interview_coding.py`). Problems come from `coding_problems.py` and follow the candidate's level: entry (0-2 years) gets mostly easy problems, mid gets medium, senior gets medium and hard. Data roles get one SQL problem; SQL-only profiles get SQL problems only.

Each problem shows a statement, examples and constraints, and pre-fills starter code in the candidate's language. "Run sample tests" executes the code **only in the candidate's browser**, in a Web Worker with a time limit: JavaScript natively, Python with Pyodide and SQL with sql.js (both loaded from a CDN on first use). Nothing is executed on the server. Java and C++ answers are reviewed statically.

The evaluator scores coding answers on reported test results (validated against the problem's test count), approach signals, edge-case handling, a stated complexity and clarity; unchanged starter code scores at most 30. The scorecard shows the candidate's code, test results and a model solution. Every model solution is run against its tests in `tests/test_question_quality.py`.

Code is stored in the interview answer payload as plain text, alongside `answer_type`, `code_language` and `test_results`.
