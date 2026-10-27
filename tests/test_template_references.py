"""Cleanup must not leave missing public templates or legal archive partials."""

from jinja2 import meta

from app.core.privacy import CONSENT_DOCUMENT_TEMPLATE
from app.core.templating import templates


def test_public_template_references_resolve():
    environment = templates.env
    for name in environment.list_templates():
        # SQLAdmin has its own loader with a sqladmin_original namespace.
        if name.startswith("sqladmin/"):
            continue
        source, _, _ = environment.loader.get_source(environment, name)
        for reference in meta.find_referenced_templates(environment.parse(source)):
            if reference is not None:
                environment.get_template(reference)
    # This include is dynamic, so Jinja's static reference finder returns None.
    environment.get_template(CONSENT_DOCUMENT_TEMPLATE)


def test_historical_consent_still_has_its_operator_partial():
    content = templates.env.get_template(
        "legal/documents/personal_data_consent_v1.html"
    ).render()
    assert "Оператор персональных данных" in content
    assert "[УКАЖИТЕ" in content
