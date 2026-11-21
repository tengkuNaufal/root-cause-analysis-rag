"""Bounded, auditable question-to-claim rules; unknown requests abstain."""
import re


def requirements(question):
    q = question.lower()
    scoped_default = bool(re.search(r'mtu discovery', q) and re.search(r'and what is its default', q))
    if q.count('?') > 1 or re.search(r'and also|also tell|and (?:give|explain|describe|list|calculate)|serta jelaskan', q) or ('and what' in q and not scoped_default):
        return None  # Multiple requests require an explicit additional profile.
    if re.search(r'tls|certificate|sertifikat|powershell|windows|bypass|exstart|root cause|akar masalah|fix|perbaiki', q):
        return None
    if re.search(r'mtu|frame|ukuran frame', q) and not re.search(r'bgp|tcp|ospf', q):
        rules = [('mtu_definition', 'openconfig', r'leaf\s+mtu\s*\{')]
        if re.search(r'header|ethernet header', q):
            rules.append(('header_counting_explicit', 'openconfig', r'(?:includes?|excludes?|including|excluding).{0,80}(?:ethernet|layer.?2|frame).{0,30}header'))
        return rules
    if re.search(r'finite state|fsm|mesin status|session.state', q):
        rules = [('session_state_declaration', 'openconfig', r'leaf\s+session-state\s*\{')]
        if re.search(r'active.{0,20}(?:meaning|enum)|active enum meaning', q):
            rules.append(('active_state_meaning', 'openconfig', r'enum ACTIVE\s*\{.{0,250}awaiting.{0,80}remote peer'))
        return rules
    if 'bgp' not in q:
        return None
    if re.search(r'mtu discovery', q):
        rules = [('mtu_discovery_setting', 'openconfig', r'leaf\s+mtu-discovery\s*\{.{0,200}turns path mtu discovery')]
        if 'default' in q:
            rules.append(('mtu_discovery_default', 'openconfig', r'leaf\s+mtu-discovery\s*\{.{0,100}default false'))
        return rules
    if re.search(r'segment size|tcp.mss', q) and re.search(r'hard reset|takes effect|appl', q):
        return [('mss_activation', 'frr', r'configure the tcp-mss.{0,180}only after hard reset')]
    if 'keepalive' in q and re.search(r'hold|timeout|dead', q):
        return [('timer_parameters', 'frr', r'first value is keepalive.{0,70}second is hold time')]
    if re.search(r'link.{0,30}flap', q) and re.search(r'default|immediate', q):
        return [('external_link_flap_default', 'frr', r'bgp fast-external-failover.{0,200}take down ebgp peers immediately.{0,180}default')]
    return None


def check(question, verified_hits):
    rules = requirements(question)
    if not rules:
        return dict(question=question, supported=False, reason='unsupported_question_scope', claims=[])
    claims = []
    for name, platform, pattern in rules:
        matches = [dict(id=h['id'], citation_url=h['metadata']['citation_url']) for h in verified_hits
                   if h['metadata']['platform'] == platform and
                   re.search(pattern, h['text'].split('\n', 1)[-1], re.I | re.S)]
        claims.append(dict(claim=name, supported=bool(matches), citations=matches))
    return dict(question=question, supported=all(c['supported'] for c in claims),
                reason='claims_supported' if all(c['supported'] for c in claims) else 'missing_claim_support', claims=claims)
