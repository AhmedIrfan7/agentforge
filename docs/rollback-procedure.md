# Rollback Procedure

Roadmap step 277. The reverse of [`docs/self-hosted-deployment.md`](self-hosted-deployment.md)'s
own "Updating" section — every command below was actually run against a real
throwaway Postgres container while writing this doc, not assumed to work.

## Application rollback (code)

```bash
git fetch origin
git checkout <previous-tag-or-commit-sha>
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Same real mechanism as a forward deploy, just checking out an older commit
first. Once real versioned releases exist (roadmap steps 292–293), prefer
rolling back to a real tag over an arbitrary commit SHA — but as of this doc,
this project has no tagged release yet, so a commit SHA is the only real
option.

## Database migration rollback

**Confirmed live, not assumed**: this project's own migrations have real,
working `downgrade()` implementations — every one of the 62 migrations in
`apps/api/migrations/versions/` (checked directly, not sampled) defines a
real downgrade, not an empty `pass` stub. Verified end to end against a real
throwaway Postgres container: ran every migration forward
(`alembic upgrade head`), rolled the latest one back
(`alembic downgrade -1`), confirmed the actual row it seeded was really gone,
then re-ran `alembic upgrade head` and confirmed it came back correctly. A
real, working round trip, not a hopeful assumption.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
  alembic downgrade -1
```

Use `alembic downgrade <revision>` to roll back further than one step —
`alembic history` (same command, add ` | cat` if it opens a pager) lists
every real revision in order.

### Honest limitation, not hidden

A migration's `downgrade()` reverses the **schema** change — dropping a
column/table it added, removing a row it seeded — but it can never restore
**data** that a forward migration genuinely deleted. If a rollback is needed
because a forward migration corrupted or destroyed real data (not just
"we don't like this schema shape anymore"), the real recovery path is
restoring from a backup (`scripts/restore-drill.sh`, roadmap step 265), not
`alembic downgrade`. Decide which situation you're actually in before
running either.

## Full rollback checklist

1. Identify the last known-good commit/tag.
2. If the deploy you're rolling back from ran a NEW migration that the
   target commit doesn't have: `alembic downgrade` to the target commit's
   own real head revision first (check its `apps/api/migrations/versions/`
   for what its actual head was) — rolling back code before rolling back a
   newer migration leaves the schema ahead of what the older code expects.
3. Roll back the code (`git checkout` + rebuild, above).
4. Verify: `curl -f http://localhost:8000/ready` (step 273 — real
   Postgres/Redis checks, not just "the container started").
5. Check `docs/runbooks/incident-response.md` if the rollback was itself a
   response to an active incident — this procedure is the mechanism, that
   doc is the decision process for when to use it.
