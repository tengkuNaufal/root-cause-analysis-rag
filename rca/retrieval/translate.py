"""Pra-pemrosesan pertanyaan sebelum pencarian.

1. strip_details: buang rincian yang tidak membantu pencarian semantik
   (alamat IP, prefix, timestamp, tanggal, nama router/interface).
2. translate_id_en: terjemahkan kata kunci bahasa Indonesia ke bahasa Inggris
   memakai glosarium jaringan. Model embedding default (all-MiniLM-L6-v2) hanya
   dilatih bahasa Inggris, sehingga pertanyaan berbahasa Indonesia sulit dicocokkan
   dengan dokumentasi FRR yang berbahasa Inggris.

Glosarium sengaja berbasis aturan (deterministik, tanpa GPU). Alternatif yang bisa
dicoba kemudian: minta model Ollama menerjemahkan, atau ganti embedding ke model
multilingual (lihat RetrieverConfig.embedding).
"""
from __future__ import annotations

import re

# Frasa lebih panjang harus dicek lebih dulu; urutan diatur otomatis di bawah.
GLOSSARY: dict[str, str] = {
    # negasi dan keadaan
    "tidak pernah": "never", "tidak bisa": "cannot", "tidak dapat": "cannot", "tidak lagi": "no longer",
    "tidak sama": "mismatch", "tidak cocok": "mismatch", "tidak sesuai": "mismatch",
    "tidak terbentuk": "does not form", "tidak terjangkau": "unreachable", "tidak naik": "not up",
    "tidak ada": "no", "tidak": "not", "belum": "not yet",
    "berbeda dengan": "differs from mismatch", "berbeda": "different mismatch",
    # protokol dan objek
    "tetangga": "neighbor", "ketetanggaan": "adjacency", "antarmuka": "interface", "tautan": "link",
    "alamat ip": "ip address", "alamat": "address", "satu subnet": "same subnet", "jaringan": "network",
    "sumber": "source", "tujuan": "destination", "rute": "route", "tabel": "table", "sesi": "session",
    "ukuran paket": "packet size mtu", "paket besar": "large packet mtu", "paket": "packet", "ukuran": "size",
    "daftar prefix": "prefix-list", "filter prefix": "prefix-list filter", "awalan": "prefix",
    "kebijakan masuk": "inbound policy route-map", "kebijakan keluar": "outbound policy route-map",
    "kebijakan": "policy", "nomor as": "as number remote-as", "kunci": "key", "kata sandi": "password",
    "autentikasi": "authentication", "otentikasi": "authentication", "jenis": "type", "pesan": "message",
    "konfigurasi": "configuration", "perubahan": "change", "pengatur waktu": "timer", "waktu": "timer",
    "pasif": "passive", "jumlah": "number", "detik": "seconds", "menit": "minutes",
    # gejala
    "macet": "stuck", "tertahan": "stuck", "terjebak": "stuck", "status": "state", "gagal": "fails",
    "berhasil": "works", "lancar": "works", "putus": "down", "mati total": "down", "mati": "down",
    "turun dari": "dropped from", "turun": "down", "naik": "up", "menyala": "up",
    "menyalakan lagi": "bring up no shutdown", "menyalakan": "bring up no shutdown",
    "dimatikan": "shutdown", "hilang": "missing", "lenyap": "missing", "kosong": "empty",
    "bolak-balik": "flapping", "naik turun": "flapping", "aneh": "wrong", "salah": "wrong", "benar": "correct",
    "ditolak": "rejected", "menolak": "rejects", "menerima": "receives", "mengirim": "sends",
    "mengiklankan": "advertises", "berhenti": "stopped", "memblokir": "blocks", "diblokir": "blocked",
    "terpasang": "applied", "dipasang": "applied", "ditambahkan": "added", "dihapus": "removed",
    "diset": "set", "dipindah ke": "moved to", "berubah menjadi": "changed to", "berubah": "changed",
    "bertukar": "exchange", "menjadi": "become", "terbentuk": "form", "mencatat": "logs", "menulis": "says",
    "menyebut": "mentions", "menunjukkan": "shows", "terlihat": "looks",
    # pertanyaan
    "penyebabnya": "cause", "penyebab": "cause", "kenapa": "why", "mengapa": "why", "bagaimana": "how",
    "memperbaikinya": "fix", "memperbaiki": "fix", "perbaikan": "fix", "apa": "what",
    # kata sambung (dibuang atau diterjemahkan)
    "padahal": "although", "walaupun": "although", "meskipun": "although", "tetapi": "but", "tapi": "but",
    "sehingga": "so", "karena": "because", "lewat": "via", "melalui": "via", "antara": "between",
    "antar": "between", "menuju": "towards", "setelah": "after", "sebelum": "before", "sekitar": "about",
    "sementara": "while", "tetap": "stays", "masih": "still", "sudah": "already", "lagi": "again",
    "semua": "all", "apa pun": "any", "menurut": "according to", "sejak": "since", "jam": "", "pukul": "",
    "ke": "to", "dari": "from", "di": "on", "pada": "on", "dan": "and", "atau": "or", "dengan": "with",
    "kecil": "small", "besar": "large", "lebih": "more", "yang": "", "ini": "", "itu": "", "ada": "",
    "total": "", "juga": "", "saat": "when", "untuk": "for",
}
_ORDERED = sorted(GLOSSARY, key=len, reverse=True)
_PATTERN = re.compile(r"(?<![\w-])(" + "|".join(re.escape(k) for k in _ORDERED) + r")(?![\w-])", re.IGNORECASE)

_ID_MARKERS = {"yang", "tidak", "dan", "di", "ke", "dari", "tetapi", "tapi", "sehingga", "kenapa", "bagaimana",
               "apa", "tetangga", "padahal", "setelah", "lewat", "karena", "masih", "sudah", "dengan"}

_DETAIL_PATTERNS = [
    r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?(?:-\d{1,3})?\b",  # IP / prefix / rentang
    r"\b\d{4}/\d{2}/\d{2}\b",                                  # tanggal log
    r"\b\d{1,2}:\d{2}(?::\d{2})?\b",                            # jam
    r"\b[rR]\d+\b",                                             # nama router
    r"\b(?:AS\s?)?6\d{4}\b",                                    # nomor ASN privat
]


def is_indonesian(text: str) -> bool:
    words = set(re.findall(r"[a-z]+", text.lower()))
    return len(words & _ID_MARKERS) >= 2


def translate_id_en(text: str) -> str:
    if not is_indonesian(text):
        return text
    out = _PATTERN.sub(lambda m: GLOSSARY[m.group(1).lower()], text)
    return re.sub(r"\s+", " ", out).strip()


def strip_details(text: str) -> str:
    for p in _DETAIL_PATTERNS:
        text = re.sub(p, " ", text)
    text = re.sub(r"\(\s*\)|\[\s*:?\s*\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def preprocess(text: str, translate: bool = True, strip: bool = True) -> str:
    if strip:
        text = strip_details(text)
    if translate:
        text = translate_id_en(text)
    return text
