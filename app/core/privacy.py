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
