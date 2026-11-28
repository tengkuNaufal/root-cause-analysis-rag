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
