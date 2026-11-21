# Explainable Agentic RAG for Root-Cause Analysis and Telemetry Remediation in NetDevOps

Laporan Akhir Tugas Besar Otomasi Jaringan dan SDN — Topik 08

- Muhammad Ashkar — 13524007
- Tengku Naufal Saqib — 13524012
- Fayyaz Akmal Lauda — 13524076

> Kerangka penyatuan. Setiap anggota menulis bagian jalurnya di file terpisah di folder ini, lalu Naufal
> menyalin, menyatukan gaya bahasa, dan menyamakan istilah. Tanda **[PEMILIK]** menunjukkan penulis bagian.
> Istilah baku: *akar masalah* (root cause), *evidence*, *varian* (zero-shot / text RAG / graph RAG),
> *run*, *trial*, *pulih* (recovered), *linter*.

## Abstrak — [Naufal, setelah hasil final]

## 1. Pendahuluan — [Naufal]
1.1 Latar belakang: RCA manual di NetDevOps lambat; LLM berpotensi mempercepat tetapi rawan halusinasi.
1.2 Rumusan masalah dan tujuan.
1.3 Batasan: lab 6 router FRR, 30 fault, model lokal Ollama.

## 2. Tinjauan Pustaka — [semua, 1–2 paragraf per topik]
RAG, GraphRAG, agen LLM untuk operasi jaringan, explainability.

## 3. Arsitektur Sistem — [Ashkar]
3.1 Topologi Host 1 (6 router, 8 link, OSPF + BGP) — gambar topologi.
3.2 Telemetry, collector, Vector, graf NetworkX dan format evidence.
3.3 Agen dan tiga varian; kontrak input/output JSON.
3.4 Retriever dan quality gate — *ambil dari `bagian-naufal.md` §A*.
3.5 Command linter — *ambil dari `bagian-naufal.md` §B*.
3.6 Eksekusi perbaikan dan verifikasi.

## 4. Metodologi Eksperimen — [Fayyaz]
4.1 Katalog 30 fault (10 kelas × 3 lokasi), versi beku (tag Git).
4.2 Runner, jadwal 450 run, mekanisme revert dan resume.
4.3 Metrik dan evaluator — *ambil dari `bagian-naufal.md` §C*.
4.4 Penilaian explainability — *ambil dari `bagian-naufal.md` §D*.

## 5. Hasil dan Pembahasan — [Naufal menyusun, semua membahas]
5.1 Kualitas retrieval sebelum/sesudah perbaikan.
5.2 Akurasi akar masalah per varian dan per kelas fault (tabel dari `results/eval/<run>/report.md`).
5.3 Ketepatan perintah, keberhasilan perbaikan, dan pelanggaran linter.
5.4 Waktu diagnosis dan pemulihan (boxplot), pencapaian target < 10 detik pada smoke test MTU.
5.5 Halusinasi.
5.6 Skor explainability.
5.7 Ancaman validitas.

## 6. Kesimpulan dan Saran — [Naufal]

## Lampiran
A. Katalog fault lengkap. B. Rubrik explainability. C. Contoh jawaban agen dan hasil linter.
D. Cara menjalankan ulang eksperimen.
