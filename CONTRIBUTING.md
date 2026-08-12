# Contributing to AgentForge

## Current status

AgentForge is in early, active foundational development (see
[`docs/ROADMAP.md`](docs/ROADMAP.md)). The project is **not yet open for
external pull requests** — the core architecture is still being laid down and
accepting contributions before that settles would create more churn than
value for everyone. This file will be expanded with full setup, workflow, and
review-process instructions once the project reaches the "Open Source
Readiness" milestone.

Until then:

- **Bug reports and design feedback** on the direction in `AGENTS.md` /
  `docs/ROADMAP.md` are welcome via GitHub Issues.
- **Pull requests** will start being accepted once local dev setup
  (Foundation milestone) is complete and documented end-to-end.

## Ground rules for this repository (apply now and later)

- **Commit discipline:** small, single-purpose commits; verify (build/tests)
  before committing; push immediately after committing. See `AGENTS.md` §10.
- **Document decisions, don't just implement them.** Non-trivial architectural
  choices get an ADR in `docs/adr/`.
- **Everything is tenant-aware.** Any change touching data access must
  preserve strict multi-tenant isolation — see `AGENTS.md` §7, §9.

## Coding standards

Formalized per-language linting/formatting/testing configuration is being
added as part of the Foundation milestone (`docs/ROADMAP.md` steps 009–011,
013–014). This section will link to the exact tool configs once they exist,
rather than describe standards that aren't enforced yet.

## Questions

Open a GitHub Discussion or Issue on this repository.
