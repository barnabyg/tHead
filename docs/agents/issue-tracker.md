# Issue tracker: GitHub

Issues and specs live in GitHub Issues for `barnabyg/tHead`.

Prefer the connected GitHub app for supported operations.
Use `gh` for operations the app cannot perform.

## Conventions

- Verify the repository before creating issues; target `barnabyg/tHead`.
- Publishing to the issue tracker means creating a GitHub issue.
- Fetching a ticket means reading its body, labels, and comments.
- Use native GitHub sub-issues for parent-child relationships.
  If unavailable, add `Part of #<parent>` to the child and link
  the child in the parent's task list.
- Use native issue dependencies for blockers. If unavailable,
  add `Blocked by: #<number>` to the dependent issue.
  Work is unblocked when every blocker is closed.
- Post the resolution before closing an issue.
- For multiline CLI bodies, write a UTF-8 file and use
  `--body-file`.

## Pull requests as a triage surface

**PRs as a request surface: no.**
