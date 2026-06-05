# -*- coding: utf-8 -*-
"""Document loading for the standalone board."""

from __future__ import annotations

from io import BytesIO

from .core import PolicyDocument


def load_text_document(name: str, data: bytes) -> PolicyDocument:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = data.decode(encoding)
            return PolicyDocument(name=name, text=text)
        except UnicodeDecodeError:
            continue
    return PolicyDocument(name=name, text=data.decode("utf-8", errors="replace"))


def load_pdf_document(name: str, data: bytes) -> PolicyDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF 읽기에는 pypdf가 필요합니다. "
            "`pip install -r standalone_board/requirements.txt`를 실행해 주세요."
        ) from exc

    reader = PdfReader(BytesIO(data))
    pages: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((idx, text))
    full_text = "\n\n".join(text for _, text in pages)
    return PolicyDocument(name=name, text=full_text, pages=pages)


def load_uploaded_document(name: str, data: bytes) -> PolicyDocument:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix == "pdf":
        return load_pdf_document(name, data)
    return load_text_document(name, data)

