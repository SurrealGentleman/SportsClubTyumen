from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.privacy import consent_document_hash, consent_document_text
from app.models import (
    Competition,
    Registration,
    RegistrationMember,
    RegistrationType,
)
from app.schemas.registration import (
    IndividualRegistrationCreate,
    TeamRegistrationCreate,
)


class RegistrationError(Exception):
    message = "Не удалось отправить заявку"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class RegistrationTypeError(RegistrationError):
    message = "Для этого соревнования требуется командная заявка"


class ConsentChangedError(RegistrationError):
    message = "Документ согласия изменился. Прочитайте актуальный текст и подтвердите согласие заново."


def accepted_consent_text(document_hash: str) -> str:
    # Recheck after CAPTCHA and persist this exact snapshot, not a second read.
    text = consent_document_text()
    if consent_document_hash(text) != document_hash:
        raise ConsentChangedError
    return text


class RegistrationClosedError(RegistrationError):
    message = "Приём заявок на это соревнование закрыт"


class RegistrationDeadlineError(RegistrationError):
    message = "Срок подачи заявок уже истёк"


class DuplicateRegistrationError(RegistrationError):
    message = "Участник с этой почтой уже зарегистрирован на соревнование"


class DuplicateTeamNameError(RegistrationError):
    message = "Команда с таким названием уже зарегистрирована на соревнование"


class TeamTooSmallError(RegistrationError):
    message = "В команде недостаточно участников"


class TeamTooLargeError(RegistrationError):
    message = "В команде слишком много участников"


class RegistrationConfigurationError(RegistrationError):
    message = "Организатор ещё не указал допустимый размер команды. Регистрация временно недоступна."


def ensure_registration_available(competition: Competition) -> None:
    if not competition.is_registration_open:
        raise RegistrationClosedError

    deadline = competition.registration_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if datetime.now(UTC) > deadline:
        raise RegistrationDeadlineError
    if competition.registration_type == RegistrationType.team:
        if not competition.has_valid_team_size:
            raise RegistrationConfigurationError


def ensure_individual_registration_available(competition: Competition) -> None:
    if competition.registration_type != RegistrationType.individual:
        raise RegistrationTypeError
    ensure_registration_available(competition)


def find_registered_emails(
    db: Session,
    *,
    competition_id: int,
    emails: list[str],
) -> list[str]:
    if not emails:
        return []
    statement = (
        select(RegistrationMember.university_email)
        .join(Registration)
        .where(
            Registration.competition_id == competition_id,
            func.lower(RegistrationMember.university_email).in_(emails),
        )
    )
    return list(db.scalars(statement))


def create_individual_registration(
    db: Session,
    *,
    competition: Competition,
    registration_in: IndividualRegistrationCreate,
) -> Registration:
    ensure_individual_registration_available(competition)
    accepted_text = accepted_consent_text(registration_in.consent_version)

    normalized_email = str(registration_in.university_email).lower()
    registered_emails = find_registered_emails(
        db,
        competition_id=competition.id,
        emails=[normalized_email],
    )
    if registered_emails:
        raise DuplicateRegistrationError

    registration = Registration(
        competition=competition,
        team_name=None,
        captain_name=registration_in.full_name,
        captain_email=normalized_email,
        captain_phone=registration_in.phone,
        personal_data_consent_at=datetime.now(UTC),
        consent_document_version=registration_in.consent_version,
        consent_document_text=accepted_text,
    )
    registration.members.append(
        RegistrationMember(
            full_name=registration_in.full_name,
            university_email=normalized_email,
            institute=registration_in.institute,
            course=registration_in.course,
            group_name=registration_in.group_name,
            phone=registration_in.phone,
            is_captain=True,
        )
    )

    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


def create_team_registration(
    db: Session,
    *,
    competition: Competition,
    registration_in: TeamRegistrationCreate,
) -> Registration:
    if competition.registration_type != RegistrationType.team:
        raise RegistrationTypeError
    ensure_registration_available(competition)

    team_size = 1 + len(registration_in.members)
    accepted_text = accepted_consent_text(registration_in.consent_version)
    min_team_size = competition.min_team_size
    max_team_size = competition.max_team_size
    assert min_team_size is not None and max_team_size is not None
    if team_size < min_team_size:
        raise TeamTooSmallError(
            f"В команде должно быть не менее {min_team_size} участников"
        )
    if team_size > max_team_size:
        raise TeamTooLargeError(
            f"В команде должно быть не более {max_team_size} участников"
        )

    existing_team_names = db.scalars(
        select(Registration.team_name).where(
            Registration.competition_id == competition.id,
            Registration.team_name.is_not(None),
        )
    )
    normalized_team_name = registration_in.team_name.casefold()
    if any(
        team_name is not None and team_name.casefold() == normalized_team_name
        for team_name in existing_team_names
    ):
        raise DuplicateTeamNameError

    normalized_captain_email = str(registration_in.captain_email).lower()
    normalized_member_emails = [
        str(member.university_email).lower() for member in registration_in.members
    ]
    registered_emails = find_registered_emails(
        db,
        competition_id=competition.id,
        emails=[normalized_captain_email, *normalized_member_emails],
    )
    if registered_emails:
        raise DuplicateRegistrationError(
            "Один или несколько участников уже зарегистрированы на соревнование"
        )

    consent_accepted_at = datetime.now(UTC)
    registration = Registration(
        competition=competition,
        team_name=registration_in.team_name,
        captain_name=registration_in.captain_name,
        captain_email=normalized_captain_email,
        captain_phone=registration_in.captain_phone,
        personal_data_consent_at=consent_accepted_at,
        consent_document_version=registration_in.consent_version,
        consent_document_text=accepted_text,
        members_consents_confirmed_at=consent_accepted_at,
    )
    registration.members.append(
        RegistrationMember(
            full_name=registration_in.captain_name,
            university_email=normalized_captain_email,
            institute=registration_in.captain_institute,
            course=registration_in.captain_course,
            group_name=registration_in.captain_group_name,
            phone=registration_in.captain_phone,
            is_captain=True,
        )
    )
    registration.members.extend(
        RegistrationMember(
            full_name=member.full_name,
            university_email=str(member.university_email).lower(),
            institute=member.institute,
            course=member.course,
            group_name=member.group_name,
            phone=None,
            is_captain=False,
        )
        for member in registration_in.members
    )

    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration
