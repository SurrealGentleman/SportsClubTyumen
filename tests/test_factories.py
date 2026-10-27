"""Shared builders must remain isolated and avoid test-module dependencies."""

import ast
from pathlib import Path

from app.core.privacy import CONSENT_VERSION
from app.core.security import verify_password
from tests.factories import create_admin, team_payload, valid_payload


def test_admin_factory_preserves_default_credentials(db_session):
    admin = create_admin(db_session)
    assert admin.id is not None
    assert admin.login == "admin"
    assert admin.is_active is True
    assert verify_password("strong-admin-password", admin.password_hash)


def test_admin_factory_supports_inactive_accounts_and_custom_password(db_session):
    admin = create_admin(db_session, is_active=False, password="custom-test-password")
    assert admin.is_active is False
    assert verify_password("custom-test-password", admin.password_hash)


def test_registration_factories_return_fresh_mutable_data():
    first = valid_payload()
    second = valid_payload()
    first["full_name"] = "Changed"
    assert second["full_name"] == "Иван Иванов"
    assert second["consent_version"] == CONSENT_VERSION

    first_team = team_payload(["first@study.utmn.ru"])
    second_team = team_payload(["second@study.utmn.ru"])
    first_team["member_full_name"].append("Extra member")
    assert len(second_team["member_full_name"]) == 1
    assert second_team["member_university_email"] == ["second@study.utmn.ru"]


def test_test_files_do_not_import_other_test_modules():
    violations = []
    for path in Path(__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("tests.test_") or (
                    node.level and module.startswith("test_")
                ):
                    violations.append(f"{path.name}:{node.lineno}: {module}")
            elif isinstance(node, ast.Import):
                violations.extend(
                    f"{path.name}:{node.lineno}: {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("tests.test_")
                )
    assert not violations, violations
