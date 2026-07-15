from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum


def enum_type(enum_cls: type[StrEnum], *, length: int = 32) -> SAEnum:
    """A VARCHAR-backed enum storing the member *value*, guarded by a CHECK constraint."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda e: [member.value for member in e],
        name=f"ck_{enum_cls.__name__.lower()}",
    )


def str_col(length: int, **kwargs: Any) -> Any:
    from sqlalchemy import String
    from sqlalchemy.orm import mapped_column

    return mapped_column(String(length), **kwargs)
