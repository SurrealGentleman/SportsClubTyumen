from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.slugs import create_unique_slug
from app.models.admin import Admin
from app.models.login_attempt import LoginAttempt
from app.models.request_limit import RequestLimit
from app.models.competition import Competition, RegistrationType
from app.models.registration import Registration, RegistrationMember
from app.models.sport import Sport
from app.models.training import Training, TrainingGroup

__all__ = (
    "Admin",
    "LoginAttempt",
    "RequestLimit",
    "Competition",
    "Registration",
    "RegistrationMember",
    "RegistrationType",
    "Sport",
    "Training",
    "TrainingGroup",
)


@event.listens_for(Session, "before_flush")
def assign_automatic_slugs(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    configurations = (
        (Sport, "name", 120),
        (Competition, "title", 255),
    )
    for model, source_attribute, max_length in configurations:
        new_items = [
            item for item in session.new if isinstance(item, model) and not item.slug
        ]
        if not new_items:
            continue
        existing = set(session.scalars(select(model.slug)))
        for item in new_items:
            item.slug = create_unique_slug(
                getattr(item, source_attribute),
                existing,
                max_length=max_length,
            )
            existing.add(item.slug)
