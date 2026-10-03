"""Local bounded extraction, lexical retrieval and page rendering."""
import base64
import io
import re
import warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from fastapi import HTTPException
from PIL import Image, ImageOps
import pypdfium2 as pdfium

MAX_BYTES = 8 * 1024 * 1024
MAX_CHARS = 200000
Image.MAX_IMAGE_PIXELS = 20_000_000


def image_jpeg(raw):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            image.seek(0)
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1120, 1120))
            result = io.BytesIO()
            image.save(result, "JPEG", quality=85)
            return result.getvalue()


def extract(name, raw):
    suffix = Path(name).suffix.lower()
    sections = []
    try:
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "image", 1, [], image_jpeg(raw)
        if suffix == ".pdf":
            with pdfium.PdfDocument(raw) as pdf:
                if len(pdf) > 100:
                    raise HTTPException(422, "PDF exceeds 100 pages; split it into smaller files")
                pages = len(pdf)
                total = 0
                for number in range(pages):
                    page = pdf[number]
                    textpage = page.get_textpage()
                    try:
                        if total + textpage.count_chars() > MAX_CHARS:
                            raise HTTPException(422, "Document exceeds 200,000 extracted characters; split it")
                        text = textpage.get_text_range()
                    finally:
                        textpage.close()
                        page.close()
                    total += len(text)
                    if total > MAX_CHARS:
                        raise HTTPException(422, "Document exceeds 200,000 extracted characters; split it")
                    if text.strip():
                        sections.extend(split(text, number + 1))
            return "pdf", pages, sections, raw
        if suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(f.file_size for f in archive.infolist()) > 32 * 1024 * 1024:
                    raise HTTPException(422, "Expanded DOCX exceeds 32 MB")
                xml = archive.read("word/document.xml")
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ValueError("XML entities are unsupported")
                root = ElementTree.fromstring(xml)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                text = "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
        elif suffix in {".txt", ".md", ".csv"}:
            text = raw.decode("utf-8-sig")
        else:
            raise HTTPException(422, "Supported files: PDF, DOCX, TXT, MD, CSV, PNG, JPG and WebP")
        if len(text) > MAX_CHARS or not text.strip():
            raise HTTPException(422, "Document is empty or exceeds 200,000 extracted characters")
        return "text", 0, split(text, None), raw
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "File could not be decoded; use an unencrypted valid document or image")


def split(text, page):
    text = text.replace("\x00", "").strip()
    return [{"text": text[i:i + 1000], "page": page} for i in range(0, len(text), 1000)]


def retrieve(attachments, query, limit=6, overview=False):
    words = set(re.findall(r"\w+", query.casefold()))
    all_chunks = [{**chunk, "attachment_id": a["id"], "name": a["name"], "chunk": i + 1}
                  for a in attachments for i, chunk in enumerate(a["sections"])]
    if overview and all_chunks:
        # Spread coverage over the available chunks, preserving file/page labels.
        indices = sorted({round(i * (len(all_chunks) - 1) / max(1, limit - 1)) for i in range(limit)})
        return [all_chunks[i] for i in indices]
    scored = sorted(all_chunks, key=lambda c: len(words & set(re.findall(r"\w+", c["text"].casefold()))), reverse=True)
    # Include representative coverage for each document, then fill with matches.
    # This is bounded excerpt retrieval, not a claim to have read every page.
    chosen = []
    for a in attachments:
        chunks = [c for c in all_chunks if c["attachment_id"] == a["id"]]
        if chunks:
            chosen.append(chunks[0])
    for c in scored:
        if c not in chosen:
            chosen.append(c)
        if len(chosen) >= limit:
            break
    return chosen[:limit]


def visual_inputs(attachments, query, enabled, max_images=2):
    if not enabled:
        return [], []
    images, sources = [], []
    requested = [int(n) for n in re.findall(r"(?:page|halaman)\s+(\d+)", query.casefold())]
    for a in attachments:
        if len(images) >= max_images:
            break
        if a["kind"] == "image":
            images.append(a["raw"])
            sources.append({"attachment_id": a["id"], "name": a["name"], "page": None})
        elif a["kind"] == "pdf":
            # Explicit page references win; otherwise first pages containing
            # relevant text, or the first two pages for a scanned PDF.
            available = requested or [c["page"] for c in retrieve([a], query) if c["page"]]
            available = list(dict.fromkeys(available)) or list(range(1, min(a["pages"], 2) + 1))
            with pdfium.PdfDocument(a["raw"]) as pdf:
                for number in available:
                    if not 1 <= number <= len(pdf):
                        raise HTTPException(422, "Requested PDF page is out of range")
                    page = pdf[number - 1]
                    try:
                        scale = min(2.0, 1120 / max(page.get_size()))
                        bitmap = page.render(scale=scale)
                        try:
                            image = bitmap.to_pil()
                            output = io.BytesIO()
                            image.convert("RGB").save(output, "JPEG", quality=85)
                            images.append(output.getvalue())
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                    sources.append({"attachment_id": a["id"], "name": a["name"], "page": number})
                    if len(images) >= max_images:
                        break
    return ["data:image/jpeg;base64," + base64.b64encode(raw).decode() for raw in images], sources
