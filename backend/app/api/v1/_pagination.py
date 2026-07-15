from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.schemas.common import Page


async def paginate[T](
    session: AsyncSession,
    stmt: Select,
    *,
    schema: type[T],
    limit: int,
    offset: int,
    order_by: ColumnElement | None = None,
) -> Page[T]:
    """Run a filtered query twice: once for the page, once for the total count.

    The count reuses the caller's WHERE clause via a subquery, so `total` always
    agrees with the filter that produced `items`.
    """
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if order_by is not None:
        stmt = stmt.order_by(order_by)

    rows = await session.scalars(stmt.limit(limit).offset(offset))
    items = [schema.model_validate(row) for row in rows]  # type: ignore[attr-defined]

    return Page[schema](items=items, total=total, limit=limit, offset=offset)  # type: ignore[valid-type]
