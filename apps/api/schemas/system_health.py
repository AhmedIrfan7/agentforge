from pydantic import BaseModel


class ProviderStatusRead(BaseModel):
    name: str
    configured: bool


class SystemHealthRead(BaseModel):
    queue_depth: int
    worker_count: int
    workers: list[str]
    providers: list[ProviderStatusRead]
