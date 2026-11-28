# Kesiapan Host 1 untuk pengujian bersama

Pembaruan 28 November 2026. Semua hasil berikut adalah commissioning/pengembangan, bukan benchmark resmi. Login Tailscale ditunda pengguna; Windows Update tetap aktif sesuai pilihan pengguna.

## Yang sudah disiapkan

- Branch monitoring/demo Fayyaz sudah diintegrasikan lokal, termasuk status per run dan monitoring tmux.
- Satu lock `private/lab-locks/rca.lock` dipakai CLI benchmark, demo, fault runner/revert, dan executor standalone. Monitoring tidak mengambil lock.
- API diagnosis tetap loopback `127.0.0.1:8766`, tanpa endpoint apply. Ollama hanya di loopback `11434`. Replay tidak dibuka atau dipakai paralel.
- API dan model berjalan dalam tmux milik user layanan; sesi benchmark detached dapat berjalan sebagai user Linux yang memiliki akses Docker. Nama sesi layanan `rca-api`/`rca-model`, runner `bench`.
- OpenSSH Server dan Tailscale Windows terpasang, service otomatis berjalan. TCP 22 lokal merespons. Firewall SSH dibatasi LAN dan rentang Tailscale; API live tidak dibuka ke LAN.
- User Linux runner diberi akses Docker dengan persetujuan pengguna. Sleep/hibernate AC dinonaktifkan; pengaturan baterai tidak diubah. Kapasitas disk diperiksa sebelum uji.
- Token, konfigurasi mesin, log instalasi, hasil run dan process metadata berada di `private/` atau `data/host2/` yang di-ignore.

## Hasil live yang sudah ada

Tiga varian memakai model terpin `llama3.1:8b`, temperature 0, seed 42, context 8192, output maksimum 768 dan num_gpu 20. Format keputusan model diringkas lalu diproyeksikan secara deterministik ke kontrak `live.v1-draft2`; label, router, penjelasan, citation dan argumen tetap berasal dari model. Tidak membaca katalog/revert/ground truth di runtime agen.

| Smoke F01 | Diagnosis | Pemulihan oleh agen dari gejala | Fallback |
|---|---:|---:|---|
| zero_shot | 9,587 dtk | 19,448 dtk | tidak |
| text_rag | 11,673 dtk | 22,758 dtk | tidak |
| graph_rag | 24,070 dtk | 37,635 dtk | tidak |

Ketiganya mengidentifikasi MTU r1 dan mengusulkan `ip link set dev eth1 mtu 1500`. Evidence/schema/lint lulus, apply berhasil, verifier runner menyatakan lab pulih. Run text RAG diluncurkan lewat `start-benchmark.sh` sebagai user runner; perintah peluncur sudah selesai sebelum runner selesai, sedangkan proses tmux tetap berjalan hingga exit 0. Ini menguji detachment lokal, bukan putusnya SSH dari laptop nyata.

**Target pemulihan <10 detik belum lulus.** Inferensi, retrieval awal, pemeriksaan precondition dan konvergensi OSPF masih memakan waktu. Angka di tabel tidak dapat dipakai untuk membandingkan varian: hanya satu sampel per varian, keadaan cache/warmup berbeda, dan prompt masih dikembangkan. Tidak mengubah timer baseline atau menonaktifkan pengecekan MTU untuk mengejar angka.

Percobaan pengembangan sebelumnya juga disimpan: abstain keliru dan command vtysh yang tidak didukung menyebabkan fallback; semuanya kembali sehat. Jangan menghitung run tersebut sebagai benchmark final atau sukses repair agen. Policy `host1-policy-v2` sekarang menolak MTU melalui vtysh; perbaikan kernel menggunakan interpreter ip. Blok vtysh proposal harus masuk mode konfigurasi terlebih dahulu.

Retrieval terbaru menggunakan locator baris newline yang benar untuk RFC (form feed bukan baris baru), dan potongan FRR yang benar-benar memeriksa MTU. Hasil proxy pengembangan corrected expansion adalah 52/60 hit@5. Hasil lama 58/60 sebelum koreksi locator tidak mewakili implementasi saat ini. Ini bukan akurasi diagnosis atau evaluasi relevansi manusia.

F16 BGP neighbor shutdown juga berhasil diperbaiki tanpa fallback dalam 29,597 detik, memakai konteks ASN dari telemetry dan baris vtysh lengkap. Baseline sehat menggunakan gate abstain tanpa inferensi, sehingga model tidak menuduh router saat tidak ada penyimpangan yang didukung.

## Menjalankan layanan

Di WSL dari root repo, dengan user layanan yang sama:

```bash
bash host1/live_api/manage.sh status
# Hanya bila belum ada listener/proses yang memakai port tersebut:
bash host1/live_api/manage.sh start-model
bash host1/live_api/manage.sh start-api
```

Startup API mengecek baseline dan tidak me-redeploy lab. Jangan restart layanan di tengah job. Setelah crash/timeout, periksa marker backend dan rekonsiliasi request sebelum mengubah lab; jangan menghapus checkpoint untuk memaksa lanjut.

## Menjalankan satu uji lokal yang persisten

Perintah berikut benar-benar inject dan apply satu fault. Jalankan hanya setelah baseline/API siap dan lab sedang tidak dipakai:

```bash
bash scripts/start-benchmark.sh --out data/host2/demo/nama-sesi-baru \
  --execute --faults F01 --variants graph_rag --trials 1 --limit 1
tmux attach -r -t bench
python3 scripts/bench_status.py data/host2/demo/nama-sesi-baru --show last
```

Sesi `bench` yang selesai tetap dapat dilihat. Periksa `private/live-runner/latest.txt` dan `process.json`: exit_code harus sudah terisi, hasil final lengkap, tidak ada held attempt dan lab sehat. Baru tutup pane selesai dengan `tmux kill-session -t bench` sebelum sesi baru. Jangan memakai perintah itu pada runner aktif. Resume memakai argumen/output yang sama; runner tidak mengirim ulang request yang belum jelas selesai.

Benchmark memakai executor di `scripts/bench.py`. Jangan menjalankan `live_api.executor --apply` lagi untuk diagnosis yang sudah dieksekusi runner. Executor standalone adalah jalur alternatif dan berbagi lock yang sama, bukan langkah kedua benchmark.

## Akses dari Host 2

`scripts/prepare-host1-access.ps1` dapat dijalankan Administrator untuk setup Windows yang sudah disetujui. Token/pengaturan pribadi tidak ditanam di script. Detail instalasi ada di `private/host1-access/`.

Untuk LAN yang sama, gunakan IP Windows Host 1 dan akun Windows yang sah. Public key laptop dapat dipasang oleh pengguna melalui panduan SSH. Jangan kirim private key atau password ke repo/chat. Authentication SSH dan akses dari laptop asli masih harus diuji bersama Host 2; port yang terbuka saja tidak membuktikannya.

Untuk akses luar rumah, pengguna menyelesaikan login Tailscale sendiri, memilih tailnet bersama Fayyaz, lalu menjalankan `tailscale ip -4`. Saat ini NeedsLogin; belum ada IP Tailscale yang dapat dipakai. Tidak perlu membuka port API, port forwarding router atau mematikan firewall.

## Syarat sebelum benchmark resmi

1. Review commit lokal dan integrasikan lewat PR saat pengguna mengizinkan push. Tidak ada push pada tahap ini.
2. Selesaikan login/uji SSH Host 2 bila akses luar rumah dibutuhkan.
3. Optimalkan dan ulang smoke MTU secara jujur; target <10 detik masih terbuka.
4. Sepakati katalog/model/profil/policy final, varian regex dan format evaluator. Regex/600 run belum dijalankan di sini.
5. Pilot seluruh fault/varian dan review hasil sebelum benchmark penuh. Jangan menggabungkan hasil pengembangan dengan hasil resmi.
