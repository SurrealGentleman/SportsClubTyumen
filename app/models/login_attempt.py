from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginAttempt(Base):
    """Shared fixed-window counters; identifiers are keyed hashes, not raw PII."""

    __tablename__ = "admin_login_attempts"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
