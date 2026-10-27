from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RequestLimit(Base):
    __tablename__ = "request_limits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
