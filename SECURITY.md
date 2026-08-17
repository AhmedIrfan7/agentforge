# Security Policy

## Supported versions

AgentForge has no versioned releases yet (roadmap step 293 tags the first
`v0.1.0-beta`) — only the `main` branch is maintained and monitored for
security issues. If you're running a fork or an old commit, please update to
the latest `main` before reporting, since the issue may already be fixed.

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security vulnerability.**

Preferred: use GitHub's private vulnerability reporting for this repository —
go to the [Security tab](https://github.com/AhmedIrfan7/agentforge/security)
and click **Report a vulnerability**. This opens a private advisory only
visible to the maintainer, with no public disclosure until a fix is ready.

If you'd rather not use GitHub, email **ahmedirfancodes@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce it (a minimal example is ideal).
- Which part of the codebase is affected (`apps/api`, `apps/web`,
  `apps/widget`, or infrastructure config).

### What's in scope

Vulnerabilities in this repository's own code: authentication/authorization
bypass, cross-tenant data access (a real, hard failure — see
[`docs/adr/0003-multi-tenancy-isolation-strategy.md`](docs/adr/0003-multi-tenancy-isolation-strategy.md)
for why Row-Level Security has no bypass mechanism anywhere in this
codebase), injection attacks, secret/credential exposure, and anything
letting one tenant see or affect another's data.

### What's out of scope

- Vulnerabilities in third-party dependencies — report those upstream, or to
  this repo's own automated dependency scanning
  ([`.github/workflows/dependency-audit.yml`](.github/workflows/dependency-audit.yml),
  which already runs `pip-audit`/`pnpm audit` on every push and weekly).
- Findings that require physical access to a user's device, or social
  engineering.
- This project has no live production deployment yet (Milestone 11 of
  [`docs/ROADMAP.md`](docs/ROADMAP.md) builds that) — there is no hosted
  instance to test against beyond your own local setup.

## Response expectations

This is a solo-maintained project, not a team with a formal SLA. I'll
acknowledge a report within a few days and aim to have a fix or a clear
timeline within two weeks for anything credible. Coordinated disclosure is
welcome — I'll credit reporters (unless you'd prefer to stay anonymous) once
a fix ships.

## Related documents

- [`docs/runbooks/incident-response.md`](docs/runbooks/incident-response.md) —
  what happens internally once a security incident is confirmed.
- [`docs/adr/0004-secrets-management.md`](docs/adr/0004-secrets-management.md) —
  how secrets are handled today.
