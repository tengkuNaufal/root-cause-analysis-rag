"""Local Chroma dense retriever, with explicit embeddings and source provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import re
import math
from collections import Counter
from functools import lru_cache

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'host1/knowledge'
MODEL = ROOT / 'private/knowledge/models/all-MiniLM-L6-v2'
COLLECTION = 'frr-openconfig-v1'


@lru_cache(maxsize=1)
def embedder():
    ONNXMiniLM_L6_V2.DOWNLOAD_PATH = MODEL
    return ONNXMiniLM_L6_V2(preferred_providers=['CPUExecutionProvider'])


def client():
    return chromadb.PersistentClient(path=str(ROOT / 'private/knowledge/chroma'), settings=Settings(anonymized_telemetry=False))


def chunks(manifest, tokenizer):
    result = []
    for source in manifest:
        path = BASE / 'sources' / source['filename']
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError('Source hash mismatch: ' + str(path))
        lines = content.decode('utf-8').splitlines()
        prefix = f"{source['platform']} {source['document_version']} {source['filename']}\n"
        start = 0
        while start < len(lines):
            end = start
            while end < len(lines) and len(tokenizer.encode(prefix + '\n'.join(lines[start:end+1])).ids) <= 230:
                end += 1
            if end == start:
                raise ValueError(f'Single source line exceeds embedding limit: {path}:{start+1}')
            body = '\n'.join(lines[start:end])
            text = prefix + body
            if body.strip():
                ident = hashlib.sha256(f"{source['sha256']}:{start+1}:{end}".encode()).hexdigest()
                metadata = {k: v for k, v in source.items() if isinstance(v, (str, int, float, bool))}
                metadata.update(line_start=start+1, line_end=end,
                    citation_url=source['source_url'] + f'#L{start+1}-L{end}',
                    embedding_model='all-MiniLM-L6-v2 ONNX', content_sha256=hashlib.sha256(text.encode()).hexdigest())
                result.append(dict(id=ident, text=text, metadata=metadata))
            start = max(start + 1, end - 3) if end < len(lines) else end
    return result


def build():
    ef = embedder()
    ef(['initialize local embedding model'])
    tokenizer = Tokenizer.from_file(str(MODEL / 'onnx/tokenizer.json'))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    manifest = json.loads((BASE / 'sources-manifest.json').read_text())
    docs = chunks(manifest, tokenizer)
    # New collection fails on an existing name, avoiding stale mixed corpus contents.
    collection = client().create_collection(COLLECTION, embedding_function=None, metadata={'hnsw:space': 'cosine'})
    tick = time.monotonic()
    for i in range(0, len(docs), 32):
        batch = docs[i:i+32]
        vectors = ef([d['text'] for d in batch])
        collection.add(ids=[d['id'] for d in batch], documents=[d['text'] for d in batch],
            metadatas=[d['metadata'] for d in batch], embeddings=vectors)
        print(json.dumps({'indexed': min(i+32, len(docs)), 'total': len(docs)}), flush=True)
    (BASE / 'chunks.jsonl').write_text(''.join(json.dumps(d) + '\n' for d in docs))
    summary = dict(collection=COLLECTION, chunks=collection.count(), sources=len(manifest),
        model='all-MiniLM-L6-v2 ONNX', dimensions=384, distance='cosine',
        seconds=time.monotonic()-tick, chromadb_version=chromadb.__version__,
        model_files={str(p.relative_to(MODEL)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in MODEL.rglob('*') if p.is_file()})
    (BASE / 'build.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


def lexical_ranking(text, documents):
    """BM25 (k1=1.5, b=.75) over source chunks, without query-specific rules."""
    tokenize = lambda value: re.findall(r'[a-z0-9]+', value.lower())
    terms = set(tokenize(text))
    tokens = [tokenize(d['text']) for d in documents]
    average = sum(map(len, tokens)) / max(1, len(tokens))
    frequencies = Counter(t for row in tokens for t in set(row))
    scored = []
    for document, row in zip(documents, tokens):
        counts = Counter(row)
        score = 0.0
        for term in terms:
            tf = counts[term]
            if tf:
                idf = math.log(1 + (len(tokens) - frequencies[term] + .5) / (frequencies[term] + .5))
                score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * len(row) / average))
        if score:
            scored.append((document['id'], score))
    return sorted(scored, key=lambda x: (-x[1], x[0]))


def query(text, platform=None, top_k=5, mode='hybrid'):
    if not text.strip() or not 1 <= top_k <= 20 or platform not in (None, 'frr', 'openconfig'):
        raise ValueError('Require nonempty query, top_k 1..20, and valid platform')
    if mode not in ('dense', 'hybrid'):
        raise ValueError('Mode must be dense or hybrid')
    collection = client().get_collection(COLLECTION, embedding_function=None)
    ef = embedder()
    tick = time.monotonic()
    result = collection.query(query_embeddings=ef([text]), n_results=min(50 if mode == 'hybrid' else top_k, collection.count()),
        where={'platform': platform} if platform else None, include=['documents', 'metadatas', 'distances'])
    hits = [dict(rank=i+1, id=ident, text=doc, metadata=meta, cosine_distance=float(distance))
            for i, (ident, doc, meta, distance) in enumerate(zip(result['ids'][0], result['documents'][0],
                    result['metadatas'][0], result['distances'][0]))]
    if mode == 'hybrid':
        documents = [json.loads(line) for line in (BASE / 'chunks.jsonl').read_text().splitlines()]
        if len(documents) != collection.count():
            raise ValueError('Lexical corpus and Chroma collection count mismatch')
        documents = [d for d in documents if platform is None or d['metadata']['platform'] == platform]
        lexical = lexical_ranking(text, documents)[:50]
        dense_rank = {h['id']: h['rank'] for h in hits}
        distances = {h['id']: h['cosine_distance'] for h in hits}
        lexical_rank = {ident: i+1 for i, (ident, _) in enumerate(lexical)}
        bm25 = dict(lexical)
        ids = set(dense_rank) | set(lexical_rank)
        scores = {ident: (.3 / (60 + dense_rank[ident]) if ident in dense_rank else 0) +
                         (.7 / (60 + lexical_rank[ident]) if ident in lexical_rank else 0) for ident in ids}
        chosen = sorted(ids, key=lambda ident: (-scores[ident], ident))[:top_k]
        stored = collection.get(ids=chosen, include=['documents', 'metadatas'])
        lookup = {ident: (doc, meta) for ident, doc, meta in zip(stored['ids'], stored['documents'], stored['metadatas'])}
        hits = [dict(rank=i+1, id=ident, text=lookup[ident][0], metadata=lookup[ident][1],
                     cosine_distance=distances.get(ident), dense_rank=dense_rank.get(ident),
                     lexical_rank=lexical_rank.get(ident), bm25=bm25.get(ident), rrf_score=scores[ident])
                for i, ident in enumerate(chosen)]
    from knowledge.yang_context import expand
    hits = [expand(hit) for hit in hits]
    return dict(query=text, platform_filter=platform, top_k=top_k, mode=mode, hits=hits,
                seconds=time.monotonic()-tick, semantics='Ranked documentation evidence, not diagnosis/confidence or validated CLI patch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'query'])
    parser.add_argument('--text')
    parser.add_argument('--platform', choices=['frr', 'openconfig'])
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--mode', choices=['dense', 'hybrid'], default='hybrid')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'build':
        build()
    else:
        value = query(args.text or '', args.platform, args.top_k, args.mode)
        output = json.dumps(value, indent=2)
        if args.output:
            args.output.write_text(output + '\n')
        print(output)


if __name__ == '__main__':
    main()
