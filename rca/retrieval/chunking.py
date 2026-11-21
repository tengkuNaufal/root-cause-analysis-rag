"""Memecah dokumen Markdown menjadi chunk per bagian (heading ##), lalu per ukuran karakter."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    section: str


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def split_sections(md: str) -> tuple[str, list[tuple[str, str]]]:
    title, sections, cur, buf = "", [], "", []
    for line in md.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            if buf and "".join(buf).strip():
                sections.append((cur, "\n".join(buf).strip()))
            cur, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        sections.append((cur, "\n".join(buf).strip()))
    return title, sections


def _pieces(text: str, size: int, overlap: int) -> list[str]:
    """Potong per kalimat agar tidak memotong di tengah perintah."""
    if len(text) <= size:
        return [text]
    sents = _SENT.split(text)
    out, cur = [], ""
    for s in sents:
        if cur and len(cur) + 1 + len(s) > size:
            out.append(cur)
            # overlap: bawa kalimat terakhir sejauh <= overlap karakter
            tail = ""
            for prev in reversed(_SENT.split(cur)):
                if len(tail) + len(prev) + 1 > overlap:
                    break
                tail = (prev + " " + tail).strip()
            cur = (tail + " " + s).strip() if tail else s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        out.append(cur)
    return out


def chunk_file(path: Path, size: int, overlap: int) -> list[Chunk]:
    title, sections = split_sections(path.read_text(encoding="utf-8"))
    chunks = []
    for si, (section, body) in enumerate(sections):
        for pi, piece in enumerate(_pieces(body, size, overlap)):
            header = f"{title} > {section}" if section else title
            chunks.append(Chunk(id=f"{path.stem}#{si}.{pi}", text=f"{header}\n{piece}",
                                source=path.name, section=section))
    return chunks


def chunk_corpus(dirs: list[Path], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for d in dirs:
        for p in sorted(Path(d).rglob("*.md")):
            chunks.extend(chunk_file(p, size, overlap))
    return chunks
