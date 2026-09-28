from __future__ import annotations

from datetime import time
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SqlEnum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.sport import Sport


class TrainingGroup(str, Enum):
    men = "Мужчины"
    women = "Девушки"
    mixed = "Общая группа"

    def __str__(self) -> str:
        return self.value


WEEKDAY_CHOICES = (
    (0, "Понедельник"),
    (1, "Вторник"),
    (2, "Среда"),
    (3, "Четверг"),
    (4, "Пятница"),
    (5, "Суббота"),
    (6, "Воскресенье"),
)
WEEKDAY_NAMES = tuple(label for _, label in WEEKDAY_CHOICES)


class Training(Base):
    __tablename__ = "trainings"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_trainings_weekday"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(
        ForeignKey("sports.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    group_name: Mapped[TrainingGroup] = mapped_column(
        SqlEnum(
            TrainingGroup,
            name="training_group",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=True,
        ),
        nullable=False,
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    coach_name: Mapped[str] = mapped_column(String(255), nullable=False)
    coach_email: Mapped[str | None] = mapped_column(String(320))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sport: Mapped[Sport] = relationship(back_populates="trainings")
