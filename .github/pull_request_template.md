## What changed and why

<!-- The PR title/diff already show WHAT changed -- explain the "why":
     what real problem this solves, what gap it closes, or what
     roadmap step it implements. -->

## How was this verified?

<!-- Real verification, not "should work" -- what commands did you run,
     what did you actually check. -->

- [ ] Tests pass locally (`make api-test` / `pnpm --filter <package> run test:e2e` as relevant)
- [ ] Linted/formatted (`make api-lint` / `make web-lint`, or the equivalent for the package touched)
- [ ] Manually verified the actual behavior (not just "tests pass") where the change is user-visible

## Checklist

- [ ] One focused change (see `CONTRIBUTING.md`'s own PR process — avoid bundling unrelated changes)
- [ ] Any change touching data access preserves real multi-tenant isolation (`AGENTS.md` §7/§9) — no query that could leak across tenants
- [ ] A non-trivial architectural decision here has a real ADR in `docs/adr/`, or doesn't need one and this box is just unchecked because none applies
- [ ] Docs updated if this changes documented behavior (`README.md`, `docs/ARCHITECTURE.md`, or elsewhere)

## Related issue(s)

<!-- Closes #... / Relates to #... -->
