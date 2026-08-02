"""
Text extraction for uploaded documents. Not agent-specific — any agent's
RAG pipeline (Inventory's policy docs today, Sales/Marketing/whoever's own
knowledge base later) can use this.
"""
from __future__ import annotations

import io

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedDocumentType(ValueError):
    pass


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded file's raw bytes, dispatching on
    its extension."""
    ext = _extension(filename)

    if ext == ".pdf":
        return _extract_pdf(content)
    if ext == ".docx":
        return _extract_docx(content)
    if ext in (".txt", ".md"):
        return content.decode("utf-8", errors="replace")

    raise UnsupportedDocumentType(
        f"'{ext}' isn't supported. Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def _extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(content))
    return "\n\n".join(p.text for p in document.paragraphs if p.text.strip())
