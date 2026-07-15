from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base for responses read straight off SQLAlchemy instances."""

    model_config = ConfigDict(from_attributes=True)


class PageParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page[T](BaseModel):
    items: list[T]
    total: int = Field(description="Total rows matching the filter, ignoring pagination.")
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
