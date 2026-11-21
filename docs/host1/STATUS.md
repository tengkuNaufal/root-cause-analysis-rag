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
| Mock API live | Schema draft2, bundle contoh sintetis, job async/SQLite, pencarian request ID dan mock loopback tersedia; 19 tes baru lulus, tanpa collector/model/router |
| Client Host 2 | Client PowerShell 5.1/7 menjalankan 16 skenario berurutan dan menyimpan JSONL; delapan tes pada tiap runtime lulus, serta smoke API nyata 16/16 dari Host 1; belum runner benchmark live |
| Migrasi | Kode dan data dipindahkan ke repo kelompok; path, import dan storage privat disesuaikan; 179 eksekusi tes lulus |
| Kerapian repositori | Fixture dibatasi ke manifest; panduan temporal digabung dan artefak historis di-ignore; peta fungsi file tersedia; hasil client Host 2 di data/host2/ juga di-ignore |
| Privasi sebelum commit | Path mesin dan login pribadi dibersihkan; fixture memakai MAC/IPv6 link-local sintetis dengan rantai hash baru; evidence asli tetap privat; 179 tes dan 16 replay simulasi lulus |

Semua jalur replay mempertahankan patch kosong dan eksekusi dinonaktifkan. Perbedaan MTU sintetis belum membuktikan dampak routing, penyebab awal gangguan atau keberhasilan repair. Angka validasi dan keterbatasannya ada di [VALIDATION.md](VALIDATION.md).

## Pembagian pekerjaan kelompok

Jalur Host 1 menangani agen dan lab, eksekusi terkontrol serta verifikasi jaringan. Jalur Host 2 menangani akses, adaptasi katalog dan runner, pilot serta benchmark. Jalur retrieval/linter/evaluasi menangani relevansi dokumentasi, pemeriksaan perintah dan metrik. Kontrak pada titik sambung dibahas bersama sebelum diubah; ground truth katalog hanya untuk runner/evaluator.

## Urutan pekerjaan berikutnya

1. Pemulihan runtime setelah migrasi lulus pada 21 November 2026: enam router dan Vector memakai mount baru; baseline routing/ping, telemetry dan ingestion sehat. Periksa kembali state aktual sebelum sesi live melalui [catatan operasional](OPERATIONS.md#pemulihan-runtime-setelah-migrasi).
2. [Draf kontrak API live revisi 2](LIVE-API-DRAFT.md) sudah memiliki [schema/contoh/mock](../../host1/live_api/README.md) untuk tes client Host 2. Format linter masih menunggu Naufal; transport aman dan koordinasi timeout perlu dikonfirmasi. Diagnosis live nyata belum diimplementasikan; API replay tetap memakai kontrak lama.
3. Lengkapi evidence dampak protokol MTU dan negatif baru sebelum menyatakan hubungan sebab terhadap kegagalan OSPF/BGP.
4. Bangun varian zero-shot, text RAG dan graph RAG serta pemilihan model berdasarkan eksperimen yang disepakati.
5. Integrasikan linter, executor dan verifikasi. Perintah hanya diterapkan jika pemeriksaan linter lolos; keputusan allowlist adalah komponen terpisah dari gate evidence.
6. PR #2 sudah tersedia lokal setelah fast-forward ke `main` (`a8ba75d`); audit target katalog dan cek baseline read-only dari runner lulus. Sebelum validasi fault di lab asli, selesaikan cleanup pada exception, exit code kegagalan dan transport SSH yang belum siap; temuan ada pada [review runner](LIVE-API-DRAFT.md#hasil-review-runner-sebelum-integrasi). Tidak perlu mengulang adaptasi katalog. Uji fault dan smoke MTU tetap memerlukan koordinasi/izin gangguan; target pemulihan di bawah 10 detik belum terbukti.
7. Jalankan pilot dan evaluator sebelum benchmark 450 run. Katalog final, kemungkinan pembanding regex, model bersama dan tenggat tetap perlu keputusan kelompok.

Kode dikerjakan pada branch masing-masing dan digabung melalui PR yang dibaca minimal satu anggota lain. Pengaturan SSH/firewall, fault injection, deploy dan perbaikan jaringan tidak dijalankan hanya karena disebut sebagai langkah berikutnya.
