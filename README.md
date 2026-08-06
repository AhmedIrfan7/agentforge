# AgentForge

Enterprise-grade, open-source, multi-tenant AI SaaS platform for building and deploying AI chatbots **and** AI voice bots that share one intelligence layer.

> Status: early development. Not yet usable. Following the roadmap in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What this is

AgentForge lets an organization upload knowledge, configure specialized AI agents, and deploy conversational assistants (chat + voice) through a simple embeddable widget — with real multi-tenant isolation, intelligent document chunking, explainable retrieval, and layered memory, not a thin wrapper around a single LLM call.

See [`AGENTS.md`](AGENTS.md) for the full product/engineering constitution this project is built against, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the technical design as it's implemented.

## Repository layout

```
apps/
  api/      FastAPI backend — multi-agent orchestrator, RAG pipeline, REST API
  web/      Next.js admin dashboard
  widget/   Embeddable chat/voice widget (vanilla TS, framework-free)
packages/
  shared/   Cross-app TypeScript types/contracts
infra/      Docker, deployment, infrastructure-as-code
docs/       Architecture docs, ADRs, roadmap
```

## Stack

Python + FastAPI · Next.js/React · PostgreSQL + pgvector · Redis + Celery · MinIO/S3 · LangGraph · Docker Compose.

Rationale for each choice: [`docs/adr/0001-technology-stack.md`](docs/adr/0001-technology-stack.md).

## Local development

Local dev setup instructions land as the roadmap's Foundation milestone completes (`docs/ROADMAP.md`, steps 001–034). This section will be filled in with real, verified steps as they're built — not written ahead of what actually works.

## Contributing

Not yet open for external contributions — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the current status and plan.

## License

[Apache 2.0](LICENSE)
