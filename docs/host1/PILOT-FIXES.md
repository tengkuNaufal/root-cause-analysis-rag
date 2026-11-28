# Perbaikan offline sesudah pilot pertama

Pilot pertama berisi 120 run unik. Pada 90 run agen terdapat 58 job failed: 40 diagnosis
tidak didukung observasi, 9 usulan ditolak linter, 3 batas konteks, dan 6 pemeriksaan waktu
capture. Delapan usulan OSPF area gagal karena tidak menghapus konfigurasi area lama.
Hasil pilot tetap disimpan sebagai data development; jangan digabung dengan hasil versi baru.

## Retrieval

Kueri physical membandingkan admin state, alamat IPv4 dan MTU secara terpisah. Adanya
observasi physical tidak otomatis menambahkan topik MTU. Referensi CLI dari sumber FRR
yang sudah dipin dan diverifikasi hash diprioritaskan sesuai key konfigurasi teramati;
satu hasil pencarian Chroma tetap disertakan bila tersedia. Kasus network advertisement
mendapat referensi perintah network dasar, bukan hanya conditional advertisement.

Validasi tahap ini: 10 tes retrieval offline lulus menggunakan pencarian sintetis dan
sumber lokal. Tidak ada rebuild indeks, panggilan model, restart API atau perubahan router.
Kontrak wire API, model, sampling dan baseline tidak berubah. Aktivasi versi baru menunggu
pengujian offline selesai serta koordinasi dengan pengelola percobaan.

## Diagnosis dan usulan perbaikan

Prompt menyeimbangkan sepuluh kelas berdasarkan perbedaan nilai observed/expected, bukan
menyamakan semua gejala BGP dengan shutdown atau semua gejala interface dengan MTU.
Model tetap memilih label, router, sitasi dan perintah; controller tidak mengisi jawaban
atau menyalin revert katalog. Tidak ada akses katalog/ground truth dari modul runtime.

Sesudah validasi evidence dan linter, pemeriksaan semantik menolak proposal yang tidak
mengembalikan setting yang teramati: link down memerlukan up; perubahan area menghapus area
lama sebelum memasang baseline; no-auth baseline memerlukan penghapusan autentikasi dan
key ID yang teramati. Parser menyimpan hanya ID key berupa angka dan keberadaannya, bukan
nilai key. Kasus hello, alamat IP, BGP ASN/shutdown/network dan penghapusan entri inbound
baru juga dicocokkan dengan baseline. Penggantian policy existing atau pemulihan key rahasia
yang tidak dapat dibuktikan tetap ditolak. Pemeriksaan ini bukan simulator FRR dan tidak
membuktikan konvergensi; verifier live tetap diperlukan.

Prompt version baru adalah live-6-balanced-named/physical; retriever version host1-hybrid-3.
Model, temperature, seed, kontrak wire, policy linter dan batas freshness tidak diubah.
Validasi tahap kedua: 48 tes dan 47 subtest lulus, termasuk pipeline sintetis untuk sepuluh
kelas dan penolakan pola perintah gagal pada pilot. Readiness tes HTTP memakai artefak
sintetis sementara, bukan database operator. Belum ada inferensi model nyata untuk prompt baru;
kelulusan fixture tidak boleh dilaporkan sebagai kenaikan akurasi pilot live.
