# Frequently Asked Questions

## What is AgentForge?

An open-source, multi-tenant AI SaaS platform for building conversational
assistants — chat and voice — backed by an organization's own documents.
An organization uploads knowledge, configures specialized AI agents, and
deploys the result through an embeddable widget. Chat and voice share the
same conversation, memory, and retrieval pipeline rather than being two
separate bots bolted together. See [`README.md`](README.md) for the
architecture diagram and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for full technical detail.

## Is there a hosted version, or do I have to run it myself?

Self-hosted only for now — no hosted/cloud offering exists yet. See
[`docs/self-hosted-deployment.md`](docs/self-hosted-deployment.md) for a
real, verified single-host deployment guide, or the README's
[Quickstart](README.md#quickstart-local-development) to run it locally
for development.

## Can I use this in production today?

It's pre-beta: every milestone through Infrastructure & Deployment
(Milestone 11) is complete — auth/RBAC, tenant isolation, the RAG
pipeline, the agent system, voice, an admin dashboard, security
hardening, observability, and real deployment tooling (Docker images,
CI/CD, staging/production workflows) all exist and are tested. What's
still missing is a tagged release, so version numbers aren't stable yet
and no compatibility guarantees exist between commits. See the
[Roadmap](README.md#roadmap) table in the README for exact status per
milestone.

## Which LLM providers are supported?

OpenAI and Anthropic today, behind a provider interface
(`apps/api/llm/base.py`) designed so a new provider is an additional
implementation, not a rewrite. Embeddings follow the same pattern
(`apps/api/embeddings/base.py`). Bring your own API key for either — no
key is bundled or proxied.

## Does voice work the same way as chat?

Yes — a voice call and a text conversation are the same underlying
`Conversation`, sharing memory, retrieval, and agent orchestration. A
caller can start on voice and continue the same thread over chat, or vice
versa. STT is Whisper, TTS is OpenAI's TTS API; both sit behind a
provider interface the same way the LLM and embedding layers do. Full
detail: the "Voice platform" section of
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How is one organization's data kept separate from another's?

Defense-in-depth, not a single layer: every tenant-scoped table carries a
`tenant_id` column enforced by Postgres Row-Level Security, the
application filters by tenant explicitly in its own repository layer on
top of that, and the app connects as a deliberately unprivileged Postgres
role (RLS can't be bypassed the way it can for a superuser connection).
The full reasoning, alternatives considered, and a real pitfall found and
fixed while building it are in
[`docs/adr/0003-multi-tenancy-isolation-strategy.md`](docs/adr/0003-multi-tenancy-isolation-strategy.md).

## What's the stack?

Python/FastAPI, Next.js/React, PostgreSQL with pgvector, Redis, Celery,
MinIO/S3, LangGraph, Docker Compose. Rationale for each choice:
[`docs/adr/0001-technology-stack.md`](docs/adr/0001-technology-stack.md).

## What license is this under?

[Apache 2.0](LICENSE).

## Can I contribute?

Not via pull request yet — Milestone 12 (the one in progress now) is
specifically about getting the project ready for that: issue templates,
labels, and a first tagged beta release. Bug reports and design feedback
on the roadmap/architecture direction are welcome via GitHub Issues in
the meantime. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the exact
current status and what changes once Milestone 12 closes, and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for community expectations.

## Where do I ask a question that isn't a bug report?

[GitHub Discussions](https://github.com/AhmedIrfan7/agentforge/discussions).

## Where do I report a security vulnerability?

Not through a public GitHub issue — see [`SECURITY.md`](SECURITY.md) for
the real reporting process.
