from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.registration import Registration


class RegistrationType(str, Enum):
    individual = "individual"
    team = "team"

    def __str__(self) -> str:
        return {
            self.individual: "Индивидуальная",
            self.team: "Командная",
        }[self]


class Competition(TimestampMixin, Base):
    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_competitions_date_range"),
        CheckConstraint(
            "(registration_type = 'individual' AND min_team_size IS NULL "
            "AND max_team_size IS NULL) OR "
            "(registration_type = 'team' AND min_team_size >= 1 "
            "AND max_team_size >= min_team_size)",
            name="ck_competitions_team_size",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    registration_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    registration_type: Mapped[RegistrationType] = mapped_column(
        SqlEnum(RegistrationType, name="registration_type"),
        nullable=False,
    )
    min_team_size: Mapped[int | None]
    max_team_size: Mapped[int | None]
    is_registration_open: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    registrations: Mapped[list[Registration]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
    )

    def __str__(self) -> str:
        return self.title
