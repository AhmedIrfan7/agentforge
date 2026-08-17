from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str


class ReadinessCheck(BaseModel):
    database: bool
    redis: bool


class ReadinessRead(BaseModel):
    status: str
    checks: ReadinessCheck
