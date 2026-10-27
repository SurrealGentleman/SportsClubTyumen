from typing import Literal, Self

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.config import settings
from app.core.privacy import CONSENT_VERSION


def validate_email_domain(value: EmailStr) -> EmailStr:
    email_domain = str(value).rsplit("@", maxsplit=1)[-1].lower()
    expected_domain = settings.university_email_domain.strip().lower()
    if email_domain != expected_domain:
        raise ValueError(f"Используйте университетскую почту @{expected_domain}")
    return value


class ParticipantCreate(BaseModel):
    full_name: str = Field(min_length=3, max_length=255)
    university_email: EmailStr
    institute: str = Field(min_length=2, max_length=255)
    course: int = Field(ge=1, le=6)
    group_name: str = Field(min_length=1, max_length=120)

    @field_validator("full_name", "institute", "group_name", mode="before")
    @classmethod
    def strip_text_fields(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("university_email")
    @classmethod
    def validate_university_email_domain(cls, value: EmailStr) -> EmailStr:
        return validate_email_domain(value)


def parse_consent_checkbox(value: object) -> bool:
    return value is True or (isinstance(value, str) and value in {"on", "true"})


class ConsentCreate(BaseModel):
    personal_data_consent: Literal[True]
    consent_version: str

    @field_validator("personal_data_consent", mode="before")
    @classmethod
    def validate_consent_checkbox(cls, value: object) -> bool:
        return parse_consent_checkbox(value)

    @field_validator("consent_version")
    @classmethod
    def validate_consent_version(cls, value: str) -> str:
        if value != CONSENT_VERSION:
            raise ValueError(
                "Документ согласия изменился. Прочитайте актуальную версию."
            )
        return value


class IndividualRegistrationCreate(ParticipantCreate, ConsentCreate):
    phone: str = Field(min_length=5, max_length=50)

    @field_validator("phone", mode="before")
    @classmethod
    def strip_phone(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TeamRegistrationCreate(ConsentCreate):
    team_name: str = Field(min_length=2, max_length=255)
    captain_name: str = Field(min_length=3, max_length=255)
    captain_email: EmailStr
    captain_phone: str = Field(min_length=5, max_length=50)
    captain_institute: str = Field(min_length=2, max_length=255)
    captain_course: int = Field(ge=1, le=6)
    captain_group_name: str = Field(min_length=1, max_length=120)
    members: list[ParticipantCreate] = Field(default_factory=list)
    members_consents_confirmed: Literal[True]

    @field_validator("members_consents_confirmed", mode="before")
    @classmethod
    def validate_members_consents(cls, value: object) -> bool:
        return parse_consent_checkbox(value)

    @field_validator(
        "team_name",
        "captain_name",
        "captain_phone",
        "captain_institute",
        "captain_group_name",
        mode="before",
    )
    @classmethod
    def strip_text_fields(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("captain_email")
    @classmethod
    def validate_captain_email_domain(cls, value: EmailStr) -> EmailStr:
        return validate_email_domain(value)

    @model_validator(mode="after")
    def validate_unique_emails(self) -> Self:
        emails = [str(self.captain_email).lower()]
        emails.extend(str(member.university_email).lower() for member in self.members)
        if len(emails) != len(set(emails)):
            raise ValueError("Почты участников внутри команды не должны повторяться")
        return self
