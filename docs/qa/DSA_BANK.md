# DSA question bank (team vivas): where it comes from

File: `config/question_bank.dsa-team.csv` (30 questions, 23 concept and 7 applied, all `source=ai-draft` until a person approves them).
Written on 20 Oct 2026 from Devesh Singh's course repository `devesh95official/MSOT_DSA301_2026` (DSA 301, Design and Analysis of Algorithms in C++): the README, the full
`DSA301HandBook.pdf` (78 pages, 28 chapters), the Hashing and Heap notes, `BST_Basic.md`, the homework list and the comments of the 40 topic programs.

Choices Mayank made: only the topics the repository has folders for (modules 1 to 5, plus the Hashing and Heap notes); mostly concepts with a few spoken STL/C++ questions;
30 questions; left out Morris traversal, tree serialization, backtracking puzzles and the CSES contest problems.

| Area | Questions | Source in the repository |
|---|---|---|
| STL and C++ (lambdas, containers, comparators, binary search, heaps) | ds01 to ds07, ds24 | chapters 1 to 3, Heap notes |
| Core revision (recursion, stack, linked list) | ds08 to ds11, ds29 | chapter 4 |
| Binary trees (traversals, height and depth, diameter, LCA, construction, min depth) | ds12 to ds16, ds27, ds30 | chapters 5 to 10 |
| Binary search trees | ds17, ds18, ds26 | chapters 11 to 13, `BST_Basic.md` |
| Greedy | ds19 to ds21, ds28 | chapters 14 to 16 |
| Hashing | ds22, ds23, ds25 | Hashing and Collision notes |

Limits to know:
- The handbook also covers dynamic programming, graphs, tree DP, backtracking and sliding windows (chapters 17 to 28), but the repository has no folders for them yet and they were left out on purpose; a student who has studied them is not tested on them.
- Difficulty is higher than the Web Development bank (more 3s, including five applied ones), because the course is an algorithms course; check that this suits the volunteers.
- The key points are written from the course material and general knowledge; a subject expert (Devesh Singh is the instructor) should read them before the bank judges anyone but ourselves.
- `python scripts/check_bank.py config/question_bank.dsa-team.csv` passes with no notes except "ai-draft needs approval".
