# Hasil validasi dan batas kesimpulan

Ringkasan ini menggabungkan laporan Host 1 tanggal 19–21 November 2026. Angka berasal dari pengujian yang sudah dilakukan; konsolidasi dokumen tidak menjalankan benchmark baru atau memeriksa ulang jaringan live. Laporan lengkap dan seluruh percobaan tetap tersedia lokal di `private/docs-history/host1/` dan arsip data yang di-ignore.

## Lab dan telemetry

| Pengujian historis | Hasil |
|---|---|
| Baseline enam router | Delapan link, lima OSPF FULL, sembilan BGP Established, ping 30/30 arah dan 120/120 paket |
| Fault/pemulihan L12 dan L35 | Dua belas snapshot lengkap; perubahan interface, peer dan rute tercatat; baseline pulih |
| Graph indexer | Replay 15 snapshot dan lima unit test lulus |
| Korelasi log dan graf | Uji live 10 marker, dua snapshot, 16 unit test dan baseline 120/120 paket |
| Pemulihan setelah restart | Baseline routing/ping lulus dan 10/10 marker Vector dari enam router |

Snapshot collector tidak atomik. Event log, status interface dan peer dapat berasal dari waktu pengamatan berbeda. Korelasi window dan transisi link tidak membuktikan pelaku, perintah pemicu, kerusakan perangkat atau sebab awal. Status container running pada laporan lama bukan bukti bahwa layanan masih hidup sekarang.

## Retrieval dan quality gate

Retriever memakai 739 chunk dari enam sumber FRR/OpenConfig yang dipin, embedding MiniLM ONNX lokal dan Chroma. Hybrid dense/BM25 pernah lulus 6/6 acceptance terarah. Gate memeriksa provenance dan dukungan klaim pertanyaan yang dikenali; bukan semantic entailment umum atau izin mengeksekusi perintah.

Evaluasi 12 query baru pada implementasi awal menemukan reference anchor pada 6/8 pertanyaan yang diperkirakan didukung dan kesepakatan keputusan gate 8/12. Dua distraktor dapat lolos ketika intent eksplisit `network_context` diberikan. Gate v2 memperketat dukungan pertanyaan. Evaluasi berikutnya membekukan delapan query sebelum pengujian, mendapat 6/8 sesuai ekspektasi, lalu memperbaiki compound request dan ekspansi YANG. Regresi setelah perbaikan 10/10 merupakan hasil pengembangan pada kasus yang telah terbuka.

Relevansi bahasa Indonesia, pertanyaan bebas dengan banyak rincian dan cakupan remedy MTU tetap terbatas. Chunk YANG adalah schema, bukan CLI FRR. Definisi MTU tidak otomatis membuktikan penghitungan header atau konfigurasi knob pada jaringan live. Pertanyaan yang tidak dikenali tetap abstain.

## Ollama dan reasoning

Ollama lokal 0.40.16 memakai llama3.1:8b Q4_K_M. Profil `num_gpu=20`, konteks 2048 pernah menghasilkan cold wall sekitar 68 detik dan warm JSON sekitar 0,65 detik. Percobaan berbagi GPU dengan aplikasi lain; ini bukan perbandingan model terkontrol atau target pemulihan jaringan di bawah 10 detik.

Adapter dokumentasi membatasi token, memilih kutipan dan memvalidasi kontrak. Replay RCA hybrid pada L12/L35 menghasilkan dua kasus administratif DOWN dari Ollama dan empat state sehat dari controller. Percobaan LLM-only sebelumnya hanya 1/6 dan tidak disembunyikan. Hasil hybrid tidak boleh dilaporkan sebagai akurasi LLM 6/6.

## Temporal dan penjelasan

| Evaluasi historis | Hasil dan interpretasi |
|---|---|
| Temporal awal | 6/6 pengembangan; 10/12 variasi diterima dan dua abstain karena ekstraksi endpoint salah |
| Pemetaan endpoint | Grouped 5/8; bound 8/8 dan empat kontrol baseline/pemulihan lulus |
| Negatif/parsial | 26/26: 20 guard abstain sebelum model, enam history parsial menghasilkan fase undetermined dari LLM |
| Penjelasan | Delapan laporan, 60 klaim dengan binding evidence/citation; 41 eksekusi tes lulus |

Bound mengikat identitas endpoint/citation melalui controller, sedangkan model menyalin observasi dan memilih fase. Nilai salah ditolak. Empat request per kasus bukan bukti model memetakan identitas arbitrer. Penjelasan memisahkan kondisi lokal, gejala dan riwayat; penyebab awal tetap `not_established`. Penilaian ini bukan skor manusia independen atas narasi bebas LLM.

## MTU sintetis

Replay akhir 28/28 lulus, dengan 35 tes; variasi nilai/urutan berikutnya 36/36 lulus, 104 binding citation dan sembilan tes harness. Dua percobaan MTU awal masing-masing 24/28 dipertahankan sebagai hasil yang gagal pada beberapa fase.

Fixture mengubah nilai MTU pada salinan snapshot/graf secara konsisten. Peer dan physical state tetap sehat. Controller menghitung EQUAL/UNEQUAL, model memilih fase, dan renderer controller membentuk penjelasan. Dua puluh delapan panggilan pada suite variasi hanya memuat empat pola input LLM unik setelah normalisasi. Hasil ini bukan kemampuan aritmetika LLM, 28 gangguan independen, dampak routing terbukti atau repair MTU live.

## API replay

API memuat 16 skenario historis/sintetis. Enam belas tes HTTP dengan model simulasi lulus. Pengujian historis terpisah dengan Ollama asli lulus 9/9, dengan 20 request model dan 49 pengambilan evidence bercitation. Waktu cold/warm tidak diisolasi dan bukan benchmark latensi.

API hanya menerima `scenario_id`, memeriksa hash dan citation, mengizinkan satu inferensi aktif dan tidak mengembalikan patch yang dapat dieksekusi. Health endpoint tidak membuktikan kesiapan model. Belum ada collector live, executor, antrean, pembatalan, autostart atau reload indeks run setelah restart. Akses lintas Host 2 belum dibuktikan oleh hasil ini.

## Migrasi dan pemeriksaan repositori

Pada 21 November 2026, 141 tes gate/replay/penjelasan/API, 22 tes adapter dan 16 tes graf/collector lulus: total 179 eksekusi tes, termasuk tes turunan yang diulang. Tujuh file embedding dan enam blob Ollama cocok dengan hash tersimpan. Satu query lokal menghasilkan lima hit dari storage baru; ini memverifikasi akses database/model, bukan relevansi. Parser PowerShell, tiga skrip shell, enam startup config dan enam path bind log lolos pemeriksaan.

Ringkasan JSON migrasi tetap disimpan lokal dan di-ignore karena hasilnya sudah dirangkum di atas. Fixture yang dibagikan didaftarkan dalam [manifest](../../data/host1/fixtures-manifest.json). Seluruh jalur yang dijelaskan masih menggunakan patch kosong dan eksekusi dinonaktifkan. Smoke test MTU end-to-end, benchmark kelompok dan validasi perbaikan jaringan tetap pekerjaan berikutnya.

Penyaringan awal mempertahankan 1.161 fixture dan lulus 163 tes Linux serta 16 tes graf/collector Windows ketika akses ke data yang di-ignore diblokir. Jumlah itu membuktikan kecukupan fixture, bukan bahwa seluruh file diperlukan.

Peninjauan berikutnya mencatat file yang benar-benar dibaca tes dan seluruh 16 skenario replay dengan model simulasi. Daftar dirampingkan menjadi 148 file (133 JSON), sekitar 12,67 MiB; sebelumnya 1.161 file (1.014 JSON), sekitar 25,39 MiB. Pada tahap penyaringan tersebut snapshot belum disanitasi; tahap privasi di bawah menghasilkan salinan publik dengan hash baru. Konfigurasi, schema kontrak, inventaris topologi, manifest sumber dan katalog replay tetap dibagikan; laporan build serta artefak eksperimen yang tidak dibaca di-ignore.

Verifikasi setelah perampingan: 163 tes Linux lulus dari salinan terisolasi yang secara fisik hanya berisi kandidat file Git, tanpa arsip data lokal; 16 tes graf/collector Windows juga lulus dengan data di luar daftar diblokir. Semua 16 skenario replay berhasil memakai transport model simulasi, dengan pemeriksaan fase, patch kosong dan pengambilan ulang setiap evidence. Gabungan akses baca kedua suite dan semua skenario tepat mencakup 148 fixture yang dipertahankan. Tidak ada inferensi model nyata atau pengujian jaringan live pada pemeriksaan ini.

Konsolidasi lanjutan menggabungkan tiga panduan ke TEMPORAL.md serta mengabaikan dua skrip khusus eksperimen lama dan latihan Alpine awal. Dengan tambahan peta fungsi file, seluruh konten repositori yang terlihat Git berkurang dari 315 menjadi 310 file. Verifikasi diulang setelah perubahan tersebut: 163 tes Linux dan 16 tes Windows lulus, serta semua 16 replay simulasi tetap sesuai ekspektasi. Daftar fixture tidak dikurangi lagi karena semua 148 file masih dibaca pada cakupan ini.

## Sanitasi sebelum staging akhir

Audit isi file menemukan path absolut mesin pada field JSON, termasuk JSON yang dienkode sebagai string di dalam kontrak, serta identitas login pada template/panduan. Salinan asli disimpan di private/privacy-originals/. Salinan publik mengganti path mesin dengan path relatif, 44 MAC terekam dan 33 IPv6 link-local dengan nilai sintetis yang konsisten. Sebanyak 82 file input/registri berubah; seluruh referensi hash serta ID snapshot terkait dihitung ulang. Metadata sanitasi dicatat pada manifest fixture; ukuran fixture publik menjadi sekitar 12,34 MiB.

Pengujian setelah sanitasi lulus 163 tes Linux pada salinan terisolasi dan 16 tes graf/collector Windows. Semua 16 skenario replay simulasi tetap memenuhi fase, kontrak tanpa patch dan pengambilan ulang evidence. Sanitasi tidak mengubah MTU, state routing IPv4 atau label kasus, dan bukan pengujian jaringan live baru. Nama login/path pribadi pada kode serta template diganti dengan aturan portabel dan placeholder.

## Client JSONL Host 2

`laptop/replay.ps1` diuji dengan delapan tes HTTP simulasi pada Windows PowerShell 5.1 dan delapan tes yang sama pada PowerShell 7. Cakupannya: tepat 16 POST berurutan, abstain valid, UTF-8 tanpa BOM, timing dan respons lengkap pada JSONL, larangan overwrite, error/busy tanpa retry, timeout dengan penyelesaian server tidak diketahui, katalog tidak valid, JSON rusak serta evidence/URL yang tidak sesuai.

Smoke terpisah memakai client PowerShell tersebut terhadap API Host 1 dengan Ollama asli. Seluruh 16 baris selesai: 14 hasil hypothesis dan dua abstain MTU tidak valid, dengan 88 fragmen evidence diambil ulang dan cocok. File JSONL dapat dibaca saat sesi masih berlangsung. Pengujian ini dijalankan dari Windows Host 1 melalui localhost, sehingga tidak menetapkan latensi client pada mesin Host 2. Keluaran lengkap berada lokal di data/host2/ dan di-ignore Git. Ini tetap replay evidence historis/sintetis, tanpa fault atau perbaikan router.
