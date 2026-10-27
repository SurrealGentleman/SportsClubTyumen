from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session
from markupsafe import escape

from app.admin.views import format_admin_datetime
from app.core import privacy
from app.core.privacy import consent_document_hash, consent_document_text
from app.models import Competition, Registration, RegistrationType


class ConsentMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name"):
            self.inputs[str(attributes["name"])] = attributes


@pytest.fixture()
def legal_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(privacy, "DOCUMENTS_DIR", tmp_path)
    (tmp_path / "personal_data_consent.txt").write_text(
        'Текст согласия.\n\nВторой абзац. <script>alert("x")</script> {{ 7 * 7 }}',
        encoding="utf-8",
    )
    (tmp_path / "privacy_policy.txt").write_text(
        "Текст политики.\n\nКонтакты оператора.", encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize(
    "path,filename",
    [
        ("/legal/personal-data-consent", "personal_data_consent.txt"),
        ("/legal/privacy-policy", "privacy_policy.txt"),
    ],
)
def test_legal_pages_display_plain_text_without_executing_markup(
    client, legal_documents, path, filename
):
    document = (legal_documents / filename).read_text(encoding="utf-8")
    response = client.get(path)
    assert response.status_code == 200
    assert str(escape(document)) in response.text
    assert '<script>alert("x")</script>' not in response.text
    assert 'class="legal-document-text"' in response.text


def test_editing_consent_automatically_invalidates_open_forms_and_preserves_records(
    client, db_session, registration_form, legal_documents
):
    path, payload = registration_form
    payload["consent_version"] = consent_document_hash()
    old_hash = payload["consent_version"]
    document = legal_documents / "personal_data_consent.txt"
    document.write_text("Новый утверждённый текст согласия.", encoding="utf-8")
    assert consent_document_hash() != old_hash

    rejected = client.post(path, data=payload)
    markup = ConsentMarkup()
    markup.feed(rejected.text)
    assert rejected.status_code == 422
    assert "checked" not in markup.inputs["personal_data_consent"]
    assert markup.inputs["consent_version"]["value"] == consent_document_hash()
    assert db_session.scalar(select(Registration)) is None

    payload["consent_version"] = consent_document_hash()
    assert client.post(path, data=payload).status_code == 201
    registration = db_session.scalar(select(Registration))
    saved_text = registration.consent_document_text
    saved_hash = registration.consent_document_version
    assert saved_text == "Новый утверждённый текст согласия."
    assert saved_hash == consent_document_hash(saved_text)

    document.write_text("Ещё одно изменение документа.", encoding="utf-8")
    db_session.refresh(registration)
    assert registration.consent_document_text == saved_text
    assert registration.consent_document_version == saved_hash


def test_consent_changed_during_captcha_cannot_save_a_different_document(
    client, db_session, registration_form, legal_documents, monkeypatch
):
    path, payload = registration_form
    payload["consent_version"] = consent_document_hash()

    def change_document(token, host):
        (legal_documents / "personal_data_consent.txt").write_text(
            "Документ изменился во время проверки CAPTCHA.", encoding="utf-8"
        )

    monkeypatch.setattr(
        "app.routers.registrations.verify_smartcaptcha", change_document
    )
    response = client.post(path, data=payload)
    markup = ConsentMarkup()
    markup.feed(response.text)
    assert response.status_code == 409
    assert "Документ согласия изменился" in response.text
    assert "checked" not in markup.inputs["personal_data_consent"]
    assert db_session.scalar(select(Registration)) is None


@pytest.fixture(params=[RegistrationType.individual, RegistrationType.team])
def registration_form(
    request: pytest.FixtureRequest, db_session: Session
) -> tuple[str, dict[str, str | list[str]]]:
    registration_type = request.param
    competition = Competition(
        title="Турнир для проверки согласия",
        slug="consent-cup",
        location="ТюмГУ",
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=20),
        registration_deadline=datetime.now(UTC) + timedelta(days=10),
        registration_type=registration_type,
        min_team_size=2 if registration_type == RegistrationType.team else None,
        max_team_size=3 if registration_type == RegistrationType.team else None,
        is_registration_open=True,
        is_published=True,
    )
    db_session.add(competition)
    db_session.commit()
    participant = {
        "full_name": "Иван Иванов",
        "university_email": "student@study.utmn.ru",
        "institute": "ИМиКН",
        "course": "2",
        "group_name": "01",
        "phone": "+7 900 000-00-00",
        "personal_data_consent": "on",
        "consent_version": consent_document_hash(),
    }
    payload: dict[str, str | list[str]] = dict(participant)
    if registration_type == RegistrationType.team:
        payload = {
            "team_name": "Команда",
            "captain_name": participant["full_name"],
            "captain_email": participant["university_email"],
            "captain_institute": participant["institute"],
            "captain_course": participant["course"],
            "captain_group_name": participant["group_name"],
            "captain_phone": participant["phone"],
            "personal_data_consent": "on",
            "consent_version": consent_document_hash(),
            "members_consents_confirmed": "on",
            "member_full_name": ["Пётр Петров"],
            "member_university_email": ["member@study.utmn.ru"],
            "member_institute": ["ИМиКН"],
            "member_course": ["2"],
            "member_group_name": ["02"],
        }
    return "/competitions/consent-cup/register", payload


def test_forms_show_unchecked_consent_and_document_links(
    client: TestClient,
    registration_form: tuple[str, dict[str, str | list[str]]],
) -> None:
    path, payload = registration_form
    response = client.get(path)
    markup = ConsentMarkup()
    markup.feed(response.text)

    assert response.status_code == 200
    checkbox = markup.inputs["personal_data_consent"]
    assert checkbox["type"] == "checkbox"
    assert "required" in checkbox
    assert "checked" not in checkbox
    assert markup.inputs["consent_version"]["value"] == consent_document_hash()
    assert "/legal/personal-data-consent" in response.text
    assert "/legal/personal-data-consent/download" not in response.text
    assert "/legal/privacy-policy" in response.text
    expected_checkboxes = {"personal_data_consent"}
    if "team_name" in payload:
        expected_checkboxes.add("members_consents_confirmed")
        assert "checked" not in markup.inputs["members_consents_confirmed"]
        assert "required" in markup.inputs["members_consents_confirmed"]
    assert {
        name
        for name, attributes in markup.inputs.items()
        if attributes.get("type") == "checkbox"
    } == expected_checkboxes


@pytest.mark.parametrize("value", [None, "", "false", "off", "1"])
def test_server_rejects_missing_or_false_consent(
    client: TestClient,
    db_session: Session,
    registration_form: tuple[str, dict[str, str | list[str]]],
    value: str | None,
) -> None:
    path, payload = registration_form
    if value is None:
        payload.pop("personal_data_consent")
    else:
        payload["personal_data_consent"] = value
    response = client.post(path, data=payload)

    assert response.status_code == 422
    assert "Дайте согласие на обработку персональных данных" in response.text
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0


def test_server_rejects_outdated_document_and_resets_checkbox(
    client: TestClient,
    db_session: Session,
    registration_form: tuple[str, dict[str, str | list[str]]],
) -> None:
    path, payload = registration_form
    payload["consent_version"] = "outdated-document"
    response = client.post(path, data=payload)
    markup = ConsentMarkup()
    markup.feed(response.text)

    assert response.status_code == 422
    assert "Документ согласия изменился" in response.text
    assert "checked" not in markup.inputs["personal_data_consent"]
    assert markup.inputs["consent_version"]["value"] == consent_document_hash()
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0


def test_new_registration_records_consent_and_exact_document(
    client: TestClient,
    db_session: Session,
    registration_form: tuple[str, dict[str, str | list[str]]],
) -> None:
    path, payload = registration_form
    before = datetime.now(UTC)
    response = client.post(path, data=payload)
    after = datetime.now(UTC)
    registration = db_session.scalar(select(Registration))

    assert response.status_code == 201
    assert registration is not None
    assert registration.personal_data_consent_at is not None
    accepted_at = registration.personal_data_consent_at.replace(tzinfo=UTC)
    assert before <= accepted_at <= after
    assert registration.consent_document_version == consent_document_hash()
    assert registration.consent_document_text == consent_document_text()
    if "team_name" in payload:
        assert (
            registration.members_consents_confirmed_at
            == registration.personal_data_consent_at
        )
    else:
        assert registration.members_consents_confirmed_at is None


@pytest.mark.parametrize("registration_form", [RegistrationType.team], indirect=True)
@pytest.mark.parametrize("value", [None, "false"])
def test_team_requires_separate_confirmation_of_member_consents(
    client: TestClient,
    db_session: Session,
    registration_form: tuple[str, dict[str, str | list[str]]],
    value: str | None,
) -> None:
    path, payload = registration_form
    if value is None:
        payload.pop("members_consents_confirmed")
    else:
        payload["members_consents_confirmed"] = value
    response = client.post(path, data=payload)

    assert response.status_code == 422
    assert "Подтвердите получение согласий всех участников команды" in response.text
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0


def test_consent_migration_preserves_legacy_applications() -> None:
    migration_path = (
        Path(__file__).parent.parent
        / "migrations/versions/20261013_03_registration_consent.py"
    )
    spec = spec_from_file_location("registration_consent_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE registrations (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO registrations (id) VALUES (1)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        legacy = (
            connection.execute(text("SELECT * FROM registrations WHERE id = 1"))
            .mappings()
            .one()
        )
        assert legacy["personal_data_consent_at"] is None
        assert legacy["consent_document_version"] is None
        assert legacy["consent_document_text"] is None
        assert legacy["members_consents_confirmed_at"] is None
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert [
            column["name"]
            for column in inspect(connection).get_columns("registrations")
        ] == ["id"]
    engine.dispose()


def test_admin_handles_legacy_applications_without_consent() -> None:
    registration = Registration(personal_data_consent_at=None)

    assert (
        format_admin_datetime(registration, "personal_data_consent_at")
        == "Не зафиксировано"
    )
