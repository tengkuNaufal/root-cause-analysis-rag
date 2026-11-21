# Status dan pekerjaan berikutnya

Pembaruan 21 November 2026. Hasil berikut berasal dari pengujian tersimpan pada 19–21 November, bukan pemeriksaan bahwa layanan sedang aktif saat dokumen dibaca.

## Kemampuan yang tersedia

| Bagian | Status dan batas |
|---|---|
| Lab Host 1 | Enam FRR, delapan link, lima adjacency OSPF dan sembilan sesi BGP pernah lulus baseline serta failover L12/L35 |
| Telemetry dan log | Collector, Vector, graf NetworkX dan korelasi per router/window tersedia dan pernah diuji live |
| Retrieval | Chroma dengan embedding lokal, hybrid dense/BM25, provenance, ekspansi YANG dan gate klaim terbatas tersedia |
| Kontrak | Input/output Pydantic dan JSON Schema, pemeriksaan evidence/citation serta flag eksekusi tersedia |
| Ollama | Instalasi lokal dan profil llama3.1:8b sudah diuji; belum ada perbandingan model yang memenuhi rencana kelompok |
| Reasoning | Adapter dokumentasi, replay administratif DOWN, temporal bound dan observasi MTU tersedia; bukan diagnosis umum |
| API | Enam belas skenario replay terdaftar, loopback, satu inferensi aktif, tanpa collector live atau executor |
| Migrasi | Kode dan data dipindahkan ke repo kelompok; path, import dan storage privat disesuaikan; 179 eksekusi tes lulus |
| Kerapian repositori | 310 file konten terlihat Git; tiga panduan temporal digabung, dua skrip satu eksperimen dan latihan Alpine awal di-ignore; peta fungsi file tersedia; 179 tes dan 16 replay simulasi tetap lulus |
| Privasi sebelum commit | Path mesin dan login pribadi dibersihkan; fixture memakai MAC/IPv6 link-local sintetis dengan rantai hash baru; evidence asli tetap privat; 179 tes dan 16 replay simulasi lulus |

Semua jalur replay mempertahankan patch kosong dan eksekusi dinonaktifkan. Perbedaan MTU sintetis belum membuktikan dampak routing, penyebab awal gangguan atau keberhasilan repair. Angka validasi dan keterbatasannya ada di [VALIDATION.md](VALIDATION.md).

## Pembagian pekerjaan kelompok

Jalur Host 1 menangani agen dan lab, eksekusi terkontrol serta verifikasi jaringan. Jalur Host 2 menangani akses, adaptasi katalog dan runner, pilot serta benchmark. Jalur retrieval/linter/evaluasi menangani relevansi dokumentasi, pemeriksaan perintah dan metrik. Kontrak pada titik sambung dibahas bersama sebelum diubah; ground truth katalog hanya untuk runner/evaluator.

## Urutan pekerjaan berikutnya

1. Periksa runtime setelah migrasi. Container lama dapat masih menunjuk bind mount ke `Tubes`; ikuti [catatan operasional](OPERATIONS.md#pemulihan-runtime-setelah-migrasi) sebelum sesi live.
2. Sepakati format evidence, jawaban, daftar perintah, hasil linter dan catatan run. API sekarang menerima ID replay, sehingga belum memenuhi kontrak agen live untuk runner.
3. Lengkapi evidence dampak protokol MTU dan negatif baru sebelum menyatakan hubungan sebab terhadap kegagalan OSPF/BGP.
4. Bangun varian zero-shot, text RAG dan graph RAG serta pemilihan model berdasarkan eksperimen yang disepakati.
5. Integrasikan linter, executor dan verifikasi. Perintah hanya diterapkan jika pemeriksaan linter lolos; keputusan allowlist adalah komponen terpisah dari gate evidence.
6. Adaptasi dan validasi katalog replika di Host 1, lalu jalankan smoke test MTU end-to-end. Target pemulihan di bawah 10 detik belum terbukti.
7. Jalankan pilot dan evaluator sebelum benchmark 450 run. Katalog final, kemungkinan pembanding regex, model bersama dan tenggat tetap perlu keputusan kelompok.

Kode dikerjakan pada branch masing-masing dan digabung melalui PR yang dibaca minimal satu anggota lain. Pengaturan SSH/firewall, fault injection, deploy dan perbaikan jaringan tidak dijalankan hanya karena disebut sebagai langkah berikutnya.
