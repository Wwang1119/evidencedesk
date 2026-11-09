from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Plan(StrictModel):
    queries: list[str] = Field(min_length=1, max_length=2)
    facets: list[str] = Field(min_length=1, max_length=4)


class Citation(StrictModel):
    source_id: int = Field(ge=1)
    quote: str = Field(min_length=20, max_length=400)


class Claim(StrictModel):
    text: str = Field(min_length=10, max_length=650)
    kind: Literal["finding", "inference", "conflict"] = "finding"
    facet: str = Field(max_length=180)
    citations: list[Citation] = Field(min_length=1, max_length=3)


class Draft(StrictModel):
    claims: list[Claim] = Field(max_length=8)
    gaps: list[str] = Field(max_length=5)
    follow_up_query: str = Field(default="", max_length=300)


class Verdict(StrictModel):
    claim_index: int = Field(ge=0)
    supported: bool
    reason: str = Field(max_length=300)


class Review(StrictModel):
    verdicts: list[Verdict] = Field(max_length=8)


class Source(BaseModel):
    id: int
    title: str
    url: str
    final_url: str
    domain: str
    text: str = Field(exclude=True)
    text_sha256: str
    checked_at: str
    http_status: int
    published_date: str | None = None
    selection_note: str


class Evidence(StrictModel):
    source_id: int
    quote: str
    context: str


class PublishedClaim(BaseModel):
    text: str
    kind: str
    facet: str
    citations: list[Citation]
    evidence: list[Evidence]
    review_reason: str


class Brief(BaseModel):
    id: str
    question: str
    created_at: str
    status: Literal["complete", "partial", "insufficient_evidence"]
    claims: list[PublishedClaim]
    sources: list[Source]
    gaps: list[str]
    warnings: list[str]
    trace: list[dict]
    stats: dict
    markdown: str = ""
