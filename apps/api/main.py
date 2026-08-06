from fastapi import FastAPI

app = FastAPI(title="AgentForge API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
