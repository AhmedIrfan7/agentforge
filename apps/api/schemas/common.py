"""Shared response envelopes."""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    limit: int
    offset: int
    total: int


class PaginationParams(BaseModel):
    limit: Annotated[int, Query(ge=1, le=200)] = 50
    offset: Annotated[int, Query(ge=0)] = 0
