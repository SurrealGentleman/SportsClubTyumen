from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.competition import Competition


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    team_name: Mapped[str | None] = mapped_column(String(255))
    captain_name: Mapped[str] = mapped_column(String(255), nullable=False)
    captain_email: Mapped[str] = mapped_column(String(320), nullable=False)
    captain_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    competition: Mapped[Competition] = relationship(back_populates="registrations")
    members: Mapped[list[RegistrationMember]] = relationship(
        back_populates="registration",
        cascade="all, delete-orphan",
    )

    def __str__(self) -> str:
        return self.team_name or self.captain_name


class RegistrationMember(Base):
    __tablename__ = "registration_members"
    __table_args__ = (
        UniqueConstraint(
            "registration_id",
            "university_email",
            name="uq_registration_members_registration_email",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    university_email: Mapped[str] = mapped_column(
        String(320), index=True, nullable=False
    )
    institute: Mapped[str] = mapped_column(String(255), nullable=False)
    course: Mapped[int] = mapped_column(nullable=False)
    group_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    registration: Mapped[Registration] = relationship(back_populates="members")

    def __str__(self) -> str:
        return self.full_name


Index(
    "uq_registrations_competition_team_name_ci",
    Registration.competition_id,
    func.lower(Registration.team_name),
    unique=True,
    postgresql_where=Registration.team_name.is_not(None),
    sqlite_where=Registration.team_name.is_not(None),
)
