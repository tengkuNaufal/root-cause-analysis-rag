"""Expand returned YANG chunks to complete overlapping leaf blocks, never global search."""
from copy import deepcopy
import hashlib
import re
from knowledge.evidence import ROOT, verify


def leaf_spans(text):
    # Mask comments and strings while preserving offsets/newlines. Braces in
    # descriptions must not change structural nesting.
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:[^\'])*\'|//[^\n]*|/\*.*?\*/', re.S)
    masked = token.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text)
    spans = []
    for match in re.finditer(r'\bleaf\s+[\w-]+\s*\{', masked):
        depth = 1
        index = match.end()
        while index < len(masked) and depth:
            depth += (masked[index] == '{') - (masked[index] == '}')
            index += 1
        if depth:
            raise ValueError('Unclosed YANG leaf')
        spans.append((text.count('\n', 0, match.start())+1, text.count('\n',0,index)+1))
    return spans


def expand(hit, max_lines=120):
    m = hit['metadata']
    if m.get('format') != 'yang':
        return hit
    path = verify(ROOT/'host1/knowledge/sources'/m['filename'], m['sha256'])
    source = path.read_text(encoding='utf-8')
    start, end = m['line_start'], m['line_end']
    overlaps = [(a,b) for a,b in leaf_spans(source) if a <= end and b >= start]
    if not overlaps:
        return hit
    a = min([start] + [a for a,_ in overlaps])
    b = max([end] + [b for _,b in overlaps])
    if (a,b) == (start,end) or b-a+1 > max_lines:
        return hit
    result = deepcopy(hit)
    result['retrieval_anchor'] = dict(id=hit['id'], metadata=deepcopy(m))
    result['context_expansion'] = 'complete_overlapping_yang_leaves; original ranking scores retained'
    result['text'] = f"{m['platform']} {m['document_version']} {m['filename']}\n" + '\n'.join(source.splitlines()[a-1:b])
    result['id'] = hashlib.sha256(f"{m['sha256']}:{a}:{b}".encode()).hexdigest()
    result['metadata'].update(line_start=a,line_end=b,citation_url=m['source_url']+f'#L{a}-L{b}',
                              content_sha256=hashlib.sha256(result['text'].encode()).hexdigest())
    return result
