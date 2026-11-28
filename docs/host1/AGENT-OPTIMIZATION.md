# Optimasi agen dalam batas 30 menit

28 November 2026. Putaran ini dibatasi maksimal 30 menit. Semua operasi melalui terminal; tidak ada akses layar langsung atau push. Data model, prompt, hasil dan konfigurasi mesin disimpan di `private/agent-optimization/` yang di-ignore.

## Perubahan yang dipertahankan

1. **Transport model lebih ringkas untuk penyimpangan fisik.** Model mengeluarkan array dengan enam posisi tetap: class, router, confidence, explanation, evidence IDs, commands. Setiap command juga berupa tuple router/tool/args. Pydantic memeriksa panjang, posisi dan tipe secara ketat, lalu memproyeksikannya ke kontrak API bernama yang sama. Tidak mengarang label atau argumen. Jalur ini dipilih dari observasi physical tanpa perubahan setting, sama untuk ketiga varian, tanpa membaca fault ID/ground truth.
2. **Format konfigurasi tetap bernama.** Percobaan array untuk semua kasus menurunkan kualitas perintah BGP pada prompt beku dan ditolak sebelum apply. Perbaikan konfigurasi tetap memakai format lama. Decoder di kedua jalur hanya mengizinkan ID evidence yang benar-benar tersedia; pemeriksaan citation/support/linter setelah model tetap berlaku.
3. **Pembacaan konfigurasi enam router secara paralel.** Hanya perintah read-only `show running-config`. `map` mempertahankan urutan inventory/fakta walaupun router selesai dalam urutan berbeda. Batas timeout/skew/freshness, hash source, sanitasi dan penolakan capture parsial tetap dipertahankan. Baseline dibaca sebagai byte yang sama untuk hashing dan parsing.

Model terpin llama3.1:8b, temperature 0, seed 42, num_gpu 20, context 8192 dan output maksimum 768 tidak berubah. Tidak mengubah baseline router, polling kontrak, API publik, replay, katalog, linter, atau verifier.

## Bukti sebelum dan sesudah

Profil awal menunjukkan median capture sekitar 1,8 detik dan generasi 114–117 token sekitar 5,7–6,4 detik. Pada A/B tiga prompt MTU beku, transport akhir menghasilkan 63–81 token. Median waktu generasi turun dari 5,936 menjadi 3,841 detik (sekitar 35%). Prompt BGP tetap memakai format bernama dan mempertahankan label/router/perintah yang sama. Keempat kasus A/B akhir lolos pemeriksaan label, router, dukungan evidence, kesetaraan perintah dan lint. Ini pengujian prompt beku, bukan diagnosis evidence live baru.

Pada smoke akhir, capture median menjadi 0,861 / 0,911 / 0,953 detik untuk zero-shot / text RAG / graph RAG. Sembilan kasus MTU F01–F03 dan satu BGP F16 semuanya lolos schema/evidence/lint, diterapkan, diverifikasi pulih dan tidak memakai fallback.

| Varian | Median pemulihan sebelum | Median sesudah | Penurunan teramati | MTU <10 detik |
|---|---:|---:|---:|---:|
| zero_shot | 12,437 dtk | 10,056 dtk | 19,1% | 1/3 |
| text_rag | 13,601 dtk | 9,566 dtk | 29,7% | 2/3 |
| graph_rag | 14,739 dtk | 11,428 dtk | 22,5% | 0/3 |

F16 graph RAG pulih tanpa fallback dalam 14,727 detik. Baseline sehat setelahnya tetap abstain tanpa inferensi/perbaikan, satu evidence terverifikasi, executor not_requested. Verifier/capture/health akhir diperiksa kembali.

**Target <10 detik belum konsisten:** 3/9 run MTU agen lulus. Nilai 10,056 tetap gagal, tidak dibulatkan menjadi lulus. Tidak melemahkan pemeriksaan atau menonaktifkan validasi untuk memenuhi target.

Angka ini smoke development satu run per lokasi per varian, bukan benchmark resmi atau tiga trial independen per fault. Cache, warmup dan kondisi runtime tidak sepenuhnya terkontrol; persentase bukan estimasi statistik umum. Semua kelas belum diuji dengan model nyata. Aturan abstraksi, format bernama untuk konfigurasi dan tes sintetis menjaga kompatibilitas, tetapi tidak menggantikan pilot seluruh katalog.

## Validasi dan artefak

- 362 tes repo dan 90 tes Host 1/kontrak/agen/executor/workflow/replay lulus: total 452.
- Tes baru memeriksa preservasi field/perintah, posisi/tipe/length array, larangan evidence ID asing, urutan fakta saat read selesai berbeda, serta fail-closed jika salah satu read konfigurasi gagal. Delapan kelas konfigurasi tetap memakai format bernama dalam tes.
- Tidak menambah dependency atau mengubah schema wire/public examples. Uji regresi ekspor schema, client, evaluator dan replay tetap lulus.
- A/B akhir: `private/agent-optimization/ab-20261128T070919Z/`.
- Tahap format saja: `private/agent-optimization/live-20261128T071135Z/`.
- Smoke akhir dengan capture paralel: `private/agent-optimization/live-parallel-20261128T071512Z/`.
- BGP akhir: `private/host1-readiness/smoke-20261128T071712Z/`.
- Ringkasan perbandingan: `private/agent-optimization/live-comparison-summary.json`.
- Pointer verifikasi baseline akhir: `private/agent-optimization/final-latest.txt`.

Prompt provenance membedakan `live-5-physical-array` dan `live-4-named-bounded-ids`. Jangan menggabungkan hasil development ini dengan benchmark protokol final. Optimasi selanjutnya memerlukan putaran terpisah; batas waktu putaran ini tidak diperpanjang.
