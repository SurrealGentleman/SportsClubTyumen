from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Change the version whenever the consent text or operator details change.
CONSENT_VERSION = "2026-10-20-placeholder-v2"
CONSENT_DOCUMENT_TEMPLATE = "legal/documents/personal_data_consent_v2.html"


def consent_document_text() -> str:
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).parent.parent / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    return environment.get_template(CONSENT_DOCUMENT_TEMPLATE).render()
