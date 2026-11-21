"""Retriever dokumentasi berbasis ChromaDB (embedding lokal, CPU).

Pemakaian oleh agen (varian text RAG / graph RAG):
    from rca.retrieval import Retriever, RetrieverConfig
    r = Retriever(RetrieverConfig.improved())
    hits = r.search("OSPF neighbor stuck in ExStart on eth1", k=5)
    # -> [{"id", "text", "source", "section", "distance"}, ...]
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
from chromadb.config import Settings

from rca.retrieval.chunking import chunk_corpus
from rca.retrieval.translate import preprocess

CORPUS = Path(__file__).resolve().parents[2] / "docs" / "corpus"


@dataclass
class RetrieverConfig:
    name: str = "baseline"
    corpus_dirs: list[Path] = field(default_factory=lambda: [CORPUS / "base"])
    chunk_size: int = 2000
    overlap: int = 0
    translate: bool = False
    strip_details: bool = False
    # "default" = all-MiniLM-L6-v2 (ONNX, bawaan Chroma). Nama model sentence-transformers
    # lain (mis. paraphrase-multilingual-MiniLM-L12-v2) bisa dipakai bila paketnya terpasang.
    embedding: str = "default"

    @classmethod
    def improved(cls) -> "RetrieverConfig":
        """Konfigurasi terbaik hasil eksperimen (lihat results/retrieval/summary.md).

        Chunk kecil (400) justru menurunkan hit@5 pada korpus ini karena tiap bagian
        dokumen sudah pendek; ulangi eksperimen bila korpus diganti dokumentasi FRR yang panjang.
        """
        return cls(name="improved", corpus_dirs=[CORPUS / "base", CORPUS / "extra"], chunk_size=2000,
                   overlap=0, translate=True, strip_details=True)

    def key(self) -> str:
        raw = f"{sorted(map(str, self.corpus_dirs))}|{self.chunk_size}|{self.overlap}|{self.embedding}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _embedding_fn(name: str):
    from chromadb.utils import embedding_functions as ef
    if name == "default":
        return ef.DefaultEmbeddingFunction()
    return ef.SentenceTransformerEmbeddingFunction(model_name=name)


class Retriever:
    def __init__(self, config: RetrieverConfig | None = None, persist_dir: str | Path | None = None):
        self.config = config or RetrieverConfig()
        settings = Settings(anonymized_telemetry=False)
        self.client = (chromadb.PersistentClient(path=str(persist_dir), settings=settings) if persist_dir
                       else chromadb.EphemeralClient(settings=settings))
        self.collection = self.client.get_or_create_collection(
            name=f"frr-{self.config.key()}", embedding_function=_embedding_fn(self.config.embedding),
            metadata={"hnsw:space": "cosine"})
        if self.collection.count() == 0:
            self._index()

    def _index(self) -> None:
        chunks = chunk_corpus(self.config.corpus_dirs, self.config.chunk_size, self.config.overlap)
        self.collection.add(ids=[c.id for c in chunks], documents=[c.text for c in chunks],
                            metadatas=[{"source": c.source, "section": c.section} for c in chunks])

    def query_text(self, question: str) -> str:
        return preprocess(question, translate=self.config.translate, strip=self.config.strip_details)

    def search(self, question: str, k: int = 5) -> list[dict]:
        res = self.collection.query(query_texts=[self.query_text(question)], n_results=k)
        return [{"id": i, "text": d, "source": m["source"], "section": m["section"], "distance": dist}
                for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                         res["distances"][0])]
