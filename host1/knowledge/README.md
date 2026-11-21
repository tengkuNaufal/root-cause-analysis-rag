# Knowledge retriever Host 1

Retriever lokal menggunakan Chroma PersistentClient dan embedding all-MiniLM-L6-v2 ONNX di CPU. Tidak menggunakan API embedding cloud, model generatif, ataupun mengeksekusi konfigurasi router. Host 2 tidak termasuk scope.

## Alur

`fetch_sources.py` mengunduh dokumentasi sumber resmi FRR tag frr-10.7.1 dan tiga schema OpenConfig pada commit tetap. URL sumber, commit, versi/revisi, waktu unduh dan SHA-256 ada dalam sources-manifest.json. Source mentah termasuk catatan lisensi tetap disimpan di sources/. FRR lab melaporkan 10.7.1_git; dokumentasi tag 10.7.1 adalah rujukan versi, bukan bukti semua perintah kompatibel dengan build tersebut.

`retriever.py build` memverifikasi hash, memecah dokumen menjadi potongan berbasis baris dengan overlap tiga baris dan batas 230 token WordPiece termasuk prefix identitas. Baris tunggal terlalu panjang ditolak, bukan dipotong diam-diam. Ini menjaga input di bawah batas model 256 token. Setiap chunk menyimpan nomor baris, URL immutable, jenis konten, platform dan hash.

Embedding lokal menghasilkan vektor 384 dimensi. Chroma menyimpan vektor/dokumen/metadata di private/knowledge/chroma dengan cosine distance. Mode default `hybrid` menggabungkan 50 kandidat dense dari Chroma dengan 50 kandidat BM25 (k1=1.5, b=.75), melalui weighted reciprocal-rank fusion: .3/(60+rank_dense) + .7/(60+rank_lexical). Tidak ada aturan khusus per kasus atau query expansion. Mode `--mode dense` tersedia sebagai pembanding. Filter platform berlaku pada kedua pencarian; dokumen hasil akhir dibaca kembali dari Chroma.

Hasil berisi teks, cosine distance jika masuk kandidat dense, rank dense/lexical, BM25/RRF score, metadata serta citation_url ke baris sumber. Skor tersebut bukan probabilitas kebenaran atau confidence diagnosis. Bobot hybrid dipilih setelah melihat kegagalan acceptance set kecil, sehingga hasil akhir adalah pengembangan, bukan evaluasi held-out.

OpenConfig diberi `content_kind=yang_schema` dan keterangan bahwa schema bukan CLI FRR. Jangan menerjemahkan leaf OpenConfig langsung menjadi perintah router. Retriever juga belum memiliki linter atau daftar perintah aman. CLI meminta sumber bukti, bukan patch otomatis.

## Penyimpanan

- sources/ dan sources-manifest.json: sumber resmi yang dibekukan beserta provenance.
- chunks.jsonl: seluruh chunk yang diindeks.
- ../../private/knowledge/models/all-MiniLM-L6-v2/: model ONNX lokal, tokenizer, dan archive terverifikasi oleh embedding function Chroma.
- ../../private/knowledge/chroma/: database persisten, jangan hapus untuk rebuild tanpa kebutuhan.
- build.json: laporan build lokal berisi versi Chroma, jumlah chunk, durasi dan hash model; dibuat ulang oleh build dan diabaikan Git.
- requirements.lock.txt: versi dependensi aktual pada venv Linux proyek.
- ../../data/host1/retriever/: log instalasi/build, hasil query dan evaluasi.

Model ONNX adalah implementasi all-MiniLM-L6-v2 milik sentence-transformers yang digunakan Chroma; paket sentence-transformers/PyTorch tidak dipasang untuk pipeline ini. Belum ada GPU requirement. Query utama pengujian memakai bahasa Inggris karena model ini terutama ditujukan untuk bahasa Inggris; probe Indonesia disimpan terpisah dan bukan bukti kualitas multibahasa umum.

## Menjalankan

Dari root proyek, dalam WSL NetworkLab:

```bash
# Environment Linux khusus proyek sudah disiapkan; tidak mengubah Python sistem.
private/.venv-retriever-wsl/bin/python scripts/host1.py -m knowledge.retriever query --text 'OSPF database description packet MTU mismatch' --platform frr --top-k 5 --output data/host1/retriever/query-mtu.json
private/.venv-retriever-wsl/bin/python scripts/host1.py -m knowledge.retriever query --text 'BGP neighbor hold-time keepalive-interval' --platform openconfig --top-k 5 --output data/host1/retriever/query-bgp.json
```

Untuk instalasi baru, buat venv Python 3.10 dan pasang requirements.lock.txt. Jika ensurepip/pip tidak tersedia, bootstrap pip hanya pada venv; bukti setup ada di data/host1/retriever/setup/. Network diperlukan untuk instalasi dan unduh awal sumber/model. Setelah itu query menggunakan database/model lokal.

Urutan build baru adalah `python scripts/host1.py -m knowledge.fetch_sources`, lalu `python scripts/host1.py -m knowledge.retriever build`. Keduanya sengaja menolak source directory/collection yang sudah ada, agar tidak mencampur corpus lama dan baru. Jangan menjalankan build ulang untuk sekadar query. CLI tidak menyediakan delete/reset otomatis.

Evaluasi: `python scripts/host1.py -m knowledge.evaluate data/host1/retriever/ID-EVALUASI-BARU`. Direktori hasil harus baru. Enam kasus terarah memeriksa referensi MTU/TCP-MSS FRR, BGP timers, fast external failover, OpenConfig MTU/timers/session-state pada top-5. Setiap hit dicek kembali terhadap baris sumber lokal dan platform yang diminta. Ini acceptance test kecil berbasis keberadaan istilah dan provenance, bukan benchmark relevance, RCA, atau command correctness. Dokumentasi di luar enam sumber belum dicakup; pertanyaan di luar corpus tetap bisa mendapat tetangga terdekat yang tidak relevan.

Gap penting: ospfd.rst tag 10.7.1 tidak memuat `ip ospf mtu-ignore` maupun penjelasan MTU mismatch yang dicari. Probe khusus OSPF MTU mismatch dan probe Indonesia disimpan terpisah; hasil terdekat tidak boleh dinyatakan sebagai bukti solusi. Jangan menerapkan sintaks vendor lain untuk menutup gap ini. Penambahan referensi tepercaya tentang OSPF MTU dan validasi pada lab diperlukan sebelum klaim RCA MTU lengkap.

Retriever murni mengembalikan kandidat tanpa izin diagnosis. Integrasi evidence dan gate klaim dijelaskan di bawah. Neural reranker dan query translation belum tersedia; implementasi reasoning terpisah dijelaskan dalam [status Host 1](../../docs/host1/STATUS.md).

Referensi resmi: [Chroma Python client](https://docs.trychroma.com/reference/python), [ONNX embedding model Chroma](https://github.com/chroma-core/onnx-embedding), [FRR OSPF 10.7](https://docs.frrouting.org/en/stable-10.7/ospfd.html), [OpenConfig models](https://github.com/openconfig/public).

## Integrasi evidence terbaru

Builder paket log/telemetry/graf + knowledge tersedia di host1/knowledge/evidence.py. Baca [panduan integrasi](EVIDENCE.md) dan [laporan replay](../../docs/host1/VALIDATION.md). Integrasi ini batch terhadap graf/snapshot/log tersimpan; tidak mengubah model, koleksi, atau ranking yang ada.

## Quality gate terbaru

Integrasi evidence sekarang memiliki [quality gate dan abstention](QUALITY-GATE.md). CLI retriever murni tetap mengembalikan kandidat; gunakan knowledge.evidence atau knowledge.quality_gate untuk keputusan kelayakan konteks. Gate tidak mengizinkan diagnosis atau eksekusi CLI.

KonteksYANG kini dilengkapi sesudah ranking: hanya leaf yang overlap,maks120baris. retrieval_anchor menyimpan metadata asli; skor milik anchor,teks/citation expanded memakai hash/rentangbaru. Tidak reindex. Referensi MTU tambahan terpisah di supplemental-mtu/README.md,belum dimasukkan Chroma. Lihat ../../docs/host1/VALIDATION.md.
