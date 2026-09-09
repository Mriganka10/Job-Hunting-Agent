# Mock Interview Code Editor

Coding and query prompts now carry `answer_mode` and `editor_language` metadata. The interview page uses that metadata to replace the spoken-response control with a dedicated code notepad in the right sidebar.

## Behavior

- Writing, implementation, debugging, refactoring, and pseudocode prompts open the editor automatically.
- Conceptual technical questions continue to use the existing speech and text response workflow.
- SQL, Python, C++, C, Java, JavaScript, TypeScript, C#, Go, Rust, PHP, Ruby, Kotlin, Swift, Scala, R, Shell, HTML/CSS, Dart, MATLAB, Perl, Lua, GraphQL, and MongoDB Query have named language options.
- Any other programming or query language can use `Other / Plain text` without losing formatting.
- The Tab key inserts two spaces in the editor.
- Submitted code is escaped and rendered in a preformatted transcript block with its selected language.

The editor is intentionally a notepad. The application does not execute, compile, evaluate, or send code to a runtime. Code is stored in the existing interview answer payload as plain text, alongside `answer_type` and `code_language` metadata.
