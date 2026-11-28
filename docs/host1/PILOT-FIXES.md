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

Prompt seimbang diperkenalkan sebagai live-6; versi konteks final memakai
live-7-focused-named/physical, dengan retriever version host1-hybrid-3.
Model, temperature, seed, kontrak wire, policy linter dan batas freshness tidak diubah.
Validasi tahap kedua: 48 tes dan 47 subtest lulus, termasuk pipeline sintetis untuk sepuluh
kelas dan penolakan pola perintah gagal pada pilot. Readiness tes HTTP memakai artefak
sintetis sementara, bukan database operator. Belum ada inferensi model nyata untuk prompt baru;
kelulusan fixture tidak boleh dilaporkan sebagai kenaikan akurasi pilot live.

## Konteks

Semua penyimpangan langsung dari setting/physical dipertahankan. Gejala protokol downstream
dibatasi satu yang paling dekat dengan router terdampak; bila budget masih tidak cukup, hanya
evidence protokol opsional itu yang boleh dihilangkan. Lebih dari enam penyimpangan langsung
ditolak, bukan dipotong diam-diam. Dokumentasi dan graf tetap hadir pada varian masing-masing;
tidak ada fallback graph RAG menjadi text RAG/zero-shot.

Graf model memakai tabel columns/rows tanpa kehilangan edge, state atau metadata derivasi.
Dokumen model mempertahankan konten, jenis dan versi; URL/hash/citation lengkap tetap berada
di arsip sumber. Kedua proyeksi disimpan dalam JSON sumber dan direferensikan melalui JSON
pointer, sehingga content endpoint evidence tetap dapat diverifikasi terhadap byte sumber.
`context-selection.json` privat mencatat kebijakan, ID protokol yang dihilangkan dan ukuran.

Guard konservatif tetap `len(prompt UTF-8) + 768 + 128 <= 8192`; panjang byte adalah upper bound,
bukan jumlah token tokenizer yang sebenarnya. Num_ctx, num_predict, model dan sampling tidak
diperbesar. Marker kontrol, hash, freshness 15 detik dan skew 5 detik tetap diperiksa.

Audit lokal tanpa inferensi atas 84 capture pilot yang sudah tersimpan menghasilkan budget
maksimal 8092. Tiga kasus yang sebelumnya gagal konteks menjadi 8092, 7807 dan 7807; perhitungan
memakai capture/graf historis dan kandidat referensi CLI lokal ditambah hit arsip, bukan hasil
pencarian atau jawaban model baru. Guard proposal menerima kembali 15 proposal lama yang pulih,
dan menolak 15 proposal lama yang gagal memulihkan lab. Ini menguji preservasi/perlindungan,
bukan menunjukkan bahwa model sudah menghasilkan perintah yang benar dengan prompt baru.

Pembersihan prefix-list hanya boleh menghapus seluruh list bila baseline membuktikan list itu
tidak memiliki entri; bila ada entri baseline lain, hapus sequence yang diperkenalkan saja.
Nilai rahasia autentikasi tidak dicatat, diteruskan, atau ditebak.

Verifikasi akhir: 458 tes dan 63 subtest lulus pada suite `tests/` serta `host1/live_api/`.
Capture, model, executor dan readiness menggunakan fixture; server HTTP uji memakai port
acak dan direktori sementara. Tidak ada paket baru dipasang atau layanan produksi diakses.

## Aktivasi dan pekerjaan berikutnya

Perubahan berada di worktree terpisah; checkout/API/router percobaan tidak diubah. Setelah review
dan persetujuan aktivasi di chat percobaan, uji live terarah seluruh kelas lalu ulangi pilot ke
folder baru. Jangan menggabungkan benchmark dengan pilot versi lama. Masalah jam Windows/WSL
yang menyebabkan enam kegagalan capture tetap perlu diselidiki; perbaikan ini tidak mengubah jam
atau menonaktifkan guard capture. Tes offline tidak membuktikan akurasi maupun latency model baru.
