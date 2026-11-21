# Bagian Naufal: Retrieval, Linter, Evaluasi

Draf untuk §3.4, §3.5, §4.3, §4.4, dan §5.1 laporan akhir. Angka retrieval di bawah adalah hasil
pengukuran nyata pada korpus di `docs/corpus/`; angka benchmark agen menunggu data pilot dan 450 run.

## A. Retriever dokumentasi (§3.4)

Retriever mengindeks dokumentasi FRR ke ChromaDB dengan embedding lokal `all-MiniLM-L6-v2` (ONNX, CPU),
jarak kosinus. Dokumen Markdown dipecah per bagian (heading `##`); bagian yang lebih panjang dari ukuran
chunk dipotong per kalimat dengan overlap. Setiap chunk diberi awalan `Judul dokumen > Judul bagian`
agar potongan kecil tidak kehilangan konteks. Agen varian text RAG dan graph RAG mengambil lima chunk
teratas.

Sebelum pencarian, pertanyaan diproses dua langkah: (1) **buang rincian** — alamat IP, prefix, timestamp,
tanggal log, nama router, dan nomor ASN dihapus karena tidak membantu pencarian semantik; (2) **terjemah
kata kunci** — jika pertanyaan terdeteksi berbahasa Indonesia, istilah jaringan dan kata gejala diganti
padanan bahasa Inggrisnya memakai glosarium (mis. *tetangga → neighbor*, *macet → stuck*,
*tidak cocok → mismatch*). Langkah ini diperlukan karena model embedding hanya dilatih bahasa Inggris
sedangkan dokumentasi FRR berbahasa Inggris.

### Set uji dan metrik

Set uji berisi satu pertanyaan per fault katalog (30) dalam bahasa Indonesia dan Inggris, total 60
pertanyaan. Sebagian sengaja ditulis dengan banyak rincian (IP, potongan log, timestamp) seperti gejala
yang diterima agen. Sebuah chunk dianggap relevan jika memuat semua istilah dalam salah satu grup kata
kunci kelas fault tersebut (mis. MTU: {mtu, mismatch} atau {mtu, exstart}). Relevansi berbasis kata kunci
dipilih agar set uji tetap bisa dipakai pada korpus lain. Metrik: **Hit@5** (jawaban muncul di lima hasil
teratas) dan **MRR@5**.

### Hasil (§5.1)

| Konfigurasi | Hit@5 ID | Hit@5 EN | Hit@5 total | MRR |
|---|---:|---:|---:|---:|
| Baseline (korpus awal, chunk per bagian) | 15/30 (50%) | 15/30 (50%) | 30/60 (50%) | 0.358 |
| + chunk kecil (400 karakter) | 14/30 (47%) | 14/30 (47%) | 28/60 (47%) | 0.339 |
| + dokumentasi FRR tambahan | 22/30 (73%) | 27/30 (90%) | 49/60 (82%) | 0.587 |
| + terjemah kata kunci ID→EN | 15/30 (50%) | 15/30 (50%) | 30/60 (50%) | 0.404 |
| + buang rincian | 14/30 (47%) | 16/30 (53%) | 30/60 (50%) | 0.376 |
| Dok tambahan + terjemah | 26/30 (87%) | 27/30 (90%) | 53/60 (88%) | 0.724 |
| **Dok tambahan + terjemah + buang rincian** | **26/30 (87%)** | **27/30 (90%)** | **53/60 (88%)** | **0.766** |

Tabel lengkap (11 konfigurasi): `results/retrieval/summary.md`.

Pembahasan:
1. **Dokumentasi tambahan** memberi kenaikan terbesar (+19 pertanyaan). Korpus awal tidak membahas
   timer OSPF, MTU, remote-as, prefix-list, dan route-map secara khusus, sehingga untuk fault tersebut
   memang tidak ada jawaban yang bisa ditemukan.
2. **Terjemahan** tidak berpengaruh saat korpus belum lengkap, tetapi setelah dokumentasi tambahan masuk,
   terjemahan menutup sebagian besar selisih bahasa: Hit@5 pertanyaan Indonesia naik dari 73% ke 87%,
   hampir menyamai bahasa Inggris (90%).
3. **Membuang rincian** tidak menambah Hit@5 tetapi menaikkan MRR (0.724 → 0.766): chunk yang benar
   naik ke peringkat lebih atas.
4. **Chunk kecil** justru menurunkan hasil pada korpus ini karena tiap bagian dokumen sudah pendek
   (±1.000–1.500 karakter); memotongnya memisahkan nama gejala dari penjelasannya. Ukuran chunk 800 sama
   baiknya dengan chunk per bagian. Eksperimen ini perlu diulang bila korpus diganti dokumentasi FRR asli
   yang bagiannya jauh lebih panjang.
5. Tujuh pertanyaan yang masih gagal umumnya ambigu (mis. "r4 dan r5 tidak bertukar Hello padahal ping
   lancar" tidak menyebut gejala area sama sekali), sehingga membutuhkan evidence dari graf, bukan hanya
   teks pertanyaan.

Ancaman validitas: glosarium dan dokumentasi tambahan ditulis oleh anggota yang sama dengan penyusun set
uji, sehingga hasil bisa optimistis. Untuk mengurangi bias, glosarium tidak diubah setelah melihat
pertanyaan yang gagal.

## B. Command linter (§3.5)

Linter berada di antara agen dan eksekusi: perintah hanya dijalankan jika linter menyatakan lolos.
Masukan berupa daftar perintah dengan router tujuan; keluaran `{"passed": bool, "violations": [...]}`
dengan setiap pelanggaran mencatat router, nomor baris, perintah, aturan, dan pesan.

Pemeriksaan:
1. **Keberadaan di topologi** — router, interface, dan alamat neighbor BGP harus ada
   (`unknown_router`, `unknown_interface`, `unknown_neighbor`). Aturan ini sekaligus dipakai evaluator
   untuk mendeteksi halusinasi perintah.
2. **Daftar izin (allowlist)** — hanya pola perbaikan yang dikenal: MTU (`ip link set dev X mtu N`),
   parameter OSPF di interface (timer, area, autentikasi, passive, network type, mtu-ignore),
   `no passive-interface`, konfigurasi neighbor BGP (remote-as, update-source, timers, password,
   prefix-list/route-map in/out), prefix-list dan route-map, `no shutdown`/`ip link set dev X up`,
   soft reset per neighbor, dan perintah `show`. Linter melacak mode vtysh (interface, router ospf,
   router bgp, address-family, route-map) termasuk perpindahan mode implisit seperti vtysh asli.
3. **Nilai masuk akal** — MTU 1280–9216, hello 1–300 s, dead 2–1200 s dan dead > hello, alamat IP harus
   sama dengan topologi, area OSPF sesuai topologi, `router bgp` dan `remote-as` sesuai ASN, prefix
   valid dengan ge/le konsisten, hold time BGP ≥ 3 dan > keepalive.
4. **Perintah berbahaya** — `no router ospf|bgp`, `reload`, `write erase`, `no interface`,
   `clear ip bgp *`, `clear ip ospf process`, `shutdown` interface/neighbor, `ip link ... down/delete`,
   perintah shell di luar izin (`rm`, `sudo`, `docker`, `systemctl`, …), dan karakter penyambung shell
   (`; & | $ \` < >`).

Pengujian: 141 unit test lulus, termasuk 30 perbaikan benar dari katalog (semuanya harus lolos),
58 contoh perintah berbahaya/salah (semuanya harus ditolak dengan aturan yang tepat), perbaikan
alternatif yang sah (mis. `ip ospf mtu-ignore`), dan bentuk masukan berbeda (`vtysh -c ...`, format datar).

## C. Evaluator dan metrik (§4.3)

Evaluator membaca file hasil run (JSON Lines) dan katalog (ground truth yang tidak pernah dikirim ke
agen), lalu menghitung per varian:

| Metrik | Definisi |
|---|---|
| Akurasi akar masalah | router **dan** kelas fault cocok dengan katalog; disertai interval kepercayaan Wilson 95% |
| Ketepatan perintah | perintah lolos linter **dan** jaringan terverifikasi pulih, dibagi semua run |
| Keberhasilan perbaikan | jaringan pulih di antara run yang perintahnya dijalankan |
| Waktu diagnosis | median dan persentil 90, sejak gejala terdeteksi sampai jawaban agen |
| Waktu pemulihan | median dan p90 sejak gejala terdeteksi sampai verifikasi pulih, plus proporsi < 10 s |
| Halusinasi | run dengan `evidence_ids` yang tidak dikirim ke agen, atau perintah ke router/interface/neighbor yang tidak ada di topologi |

Keluaran: `report.md`, `metrics_by_variant.csv`, `accuracy_by_class.csv`, `runs_scored.csv`, serta
boxplot waktu diagnosis dan waktu pemulihan per varian (dengan garis target 10 detik).

## D. Penilaian explainability (§4.4)

Rubrik lima dimensi dengan skor 0–2 (total 0–10): grounding evidence, rantai kausal, konsistensi,
justifikasi perbaikan, dan kejelasan (`docs/rubrik-explainability.md`). Sampel 90 penjelasan diambil
acak (satu trial per fault per varian), varian disembunyikan, dan dibagi ke tiga anggota; 9 item dinilai
ketiganya untuk mengukur kesepakatan antarpenilai.
