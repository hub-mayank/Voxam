# Web Development question bank (team vivas): where it comes from

File: `config/question_bank.webd-team.csv` (30 questions, 23 concept and 7 applied, difficulty 1 to 3, all `source=ai-draft` until a person approves them).
Written on 19 Oct 2026 from the course notes Mayank shared (three Notion trees), with the choices he made: topic mix about 40% JavaScript, 37% Node/Express/Mongo,
23% React; course level; "explain and debug scenarios" style (nothing that needs code read aloud); left out the advanced JavaScript extras (Proxy, typed arrays, Canvas/SVG),
Redux Toolkit, Passport.js setup details and EJS syntax.

| Track | Questions | Notes they come from |
|---|---|---|
| JavaScript (12) | js01 to js12 | JavaScript Revision Lecture Plan: variables, operators, hoisting and TDZ, scope and closures, array methods, event loop and async, promises, storage, objects and copying, DOM events |
| Node, Express, Mongo (11) | be01 to be11 | Backend notes: starting backend, middleware (req.body), MVC, SSR and CSR, Database, Mongoose, cookies and sessions, authentication and authorization |
| React (7) | re01 to re07 | Front-End notes: React summary, useState and useEffect examples, debouncing and cleanup, React Router |

Limits to know:
- Some Notion pages only showed their first part when read (long pages load lazily), so deeper topics in those pages (for example the later sections on sessions, hashing and Mongoose queries) may be under-represented.
- The key points are private marking hints written from the notes and general knowledge; a subject expert should read them before the bank is used to judge people.
- `python scripts/check_bank.py config/question_bank.webd-team.csv` passes with no notes other than "ai-draft needs approval".
