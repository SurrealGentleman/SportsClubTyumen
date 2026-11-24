import html
import re
from hashlib import sha256
from pathlib import Path

DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "documents"


def consent_document_text() -> str:
    return (
        (DOCUMENTS_DIR / "personal_data_consent.txt")
        .read_text(encoding="utf-8-sig")
        .strip()
    )


def privacy_policy_text() -> str:
    return (
        (DOCUMENTS_DIR / "privacy_policy.txt").read_text(encoding="utf-8-sig").strip()
    )


def consent_document_hash(document_text: str | None = None) -> str:
    """Identify the accepted text automatically; no manual versions to maintain."""
    if document_text is None:
        document_text = consent_document_text()
    return sha256(document_text.encode("utf-8")).hexdigest()


_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def linkify_text(text: str) -> str:
    """Escape the document text and turn bare URLs into clickable links."""
    parts: list[str] = []
    position = 0
    for match in _URL_RE.finditer(text):
        parts.append(html.escape(text[position : match.start()]))
        url = html.escape(match.group(0), quote=True)
        parts.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
        )
        position = match.end()
    parts.append(html.escape(text[position:]))
    return "".join(parts)


def consent_document_html() -> str:
    return linkify_text(consent_document_text())


def privacy_policy_html() -> str:
    return linkify_text(privacy_policy_text())
