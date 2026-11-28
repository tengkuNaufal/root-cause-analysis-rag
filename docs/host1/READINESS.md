# Kesiapan Host 1 untuk pengujian bersama

Pembaruan 28 November 2026. Kode dan baseline lokal siap untuk uji integrasi terkontrol. Target pemulihan agen <10 detik belum lulus. Login Tailscale ditunda pengguna, Windows Update tetap aktif, dan akses layar langsung dihentikan sesuai permintaan pengguna.

## Kondisi akhir yang diperiksa

- Enam FRR dan Vector berjalan; delapan link, lima adjacency OSPF FULL, sembilan sesi BGP Established. Verifier baseline lulus termasuk ping 30/30 arah, 120/120 paket; capture akhir tidak menemukan anomali.
- Baseline baru memakai `ip ospf retransmit-interval 1` pada sepuluh interface data OSPF r1–r4, setelah persetujuan pengguna dan redeploy terkontrol. Hello/dead tetap 1/4 detik. `design-plan.json` dan konfigurasi sumber konsisten. Vector dipertahankan dan menerima 10/10 marker dari enam router.
- API loopback 8766 melaporkan mode live, simulation=false, ready=true, active=false. Ollama loopback 11434 dan API berada di tmux `rca-model`/`rca-api`. Replay tidak diubah atau dinyalakan paralel.
- Branch monitoring/demo dan regex PR #12 sudah diintegrasikan. Jadwal tersedia untuk 450 run agen ditambah 150 rule_based. Benchmark resmi belum dijalankan.
- Shared lock privat dipakai CLI benchmark, demo, fault runner/revert dan executor standalone. Benchmark memakai executor runner; jangan menjalankan standalone --apply lagi untuk diagnosis yang sama.
- Runner detached diuji sebagai user Linux yang memiliki akses Docker: launcher selesai lebih dahulu, runner tetap berjalan di tmux hingga exit 0. Ini detachment lokal, belum uji putus SSH dari laptop asli.
- OpenSSH Server dan Tailscale Windows terpasang dengan service otomatis. Port 22 loopback merespons; firewall dibatasi LAN/rentang Tailscale. Sleep/hibernate AC Never; baterai tidak diubah.
- Token, alamat/koneksi pribadi, PID/log instalasi, model, environment, runtime dan hasil run tetap di private/ atau data/host2/ yang di-ignore. Fixture baru rca-sim adalah data sintetis upstream yang dipakai tes, bukan hasil lokal mesin ini.

## Model dan kontrak

Ketiga varian memakai llama3.1:8b dengan digest terpin, temperature 0, seed 42, context 8192, output maksimum 768, num_gpu 20. Profil replay/setup tidak diubah. Profil full GPU 33 diuji pada prompt beku tanpa fault/apply, terlalu lambat, dibatalkan dan tidak diadopsi. Backend profil stabil sudah dipulihkan dan inferensi diverifikasi ulang.

Keputusan model ringkas diproyeksikan secara deterministik ke kontrak live.v1-draft2: label/router, penjelasan, evidence IDs dan seluruh argumen berasal dari model. Tidak mengarang command yang ditolak. Tool ip memakai argv, vtysh memakai baris CLI lengkap dengan mode konfigurasi. Policy host1-policy-v2 menolak MTU melalui vtysh yang terbukti tidak didukung build Host 1. Saat tidak ada penyimpangan yang didukung, gate baseline abstain tanpa memanggil model. API tetap tanpa endpoint apply. Katalog/ground truth/revert tidak dibaca runtime agen.

Rule_based adalah pembanding lokal di runner, bukan varian endpoint API dan bukan job yang lolos schema Live Job. Evaluator membaca assessment/label/timing yang sama. Aturan ditulis dengan pengetahuan kelas/kondisi katalog, sehingga bukan evaluasi generalisasi terhadap fault tak dikenal.

## Hasil smoke pada baseline baru

F01/F02/F03 dijalankan sekali per varian sebagai pengembangan, bukan benchmark final. Model dipreload di luar pengukuran fault; keadaan cache retrieval tidak sepenuhnya seragam. Semua 12 diagnosis/command lolos lint, diterapkan, dan lab pulih tanpa fallback.

| Varian | Run pulih tanpa fallback | Pemulihan min–max dari gejala | Median | Lulus <10 detik |
|---|---|---|---|---|
| rule_based | 3/3 | 2,018–4,300 dtk | 4,141 dtk | 3/3 |
| zero_shot | 3/3 | 12,301–13,944 dtk | 12,437 dtk | 0/3 |
| text_rag | 3/3 | 13,484–18,064 dtk | 13,601 dtk | 0/3 |
| graph_rag | 3/3 | 12,534–15,985 dtk | 14,739 dtk | 0/3 |

**Pemulihan fungsional lulus 12/12; target waktu agen belum lulus.** Jangan menyatakan semua varian sudah mencapai <10 detik. Inferensi/collection/polling masih membatasi. Tidak menonaktifkan validasi MTU atau melemahkan verifier untuk mengejar angka.

Sebelum baseline baru, ketiga varian juga berhasil memperbaiki F01; satu smoke BGP F16 berhasil melalui vtysh tanpa fallback. Kegagalan development sebelumnya (abstain keliru, format command salah) tetap disimpan dan tidak dihitung sebagai sukses atau benchmark. Pilot seluruh kelas belum dilakukan.

Tes akhir: 362 tes repo dan 85 tes Host 1/kontrak/agen/executor/workflow/replay lulus, total 447. Evaluator berhasil membaca 12 hasil nyata termasuk regex dan menghasilkan laporan privat. Ini validasi format/metrik pada smoke terbatas, bukan angka akurasi untuk seluruh katalog.

Retrieval corrected expansion adalah 52/60 keyword hit@5 setelah perbaikan locator RFC (form feed bukan newline) dan potongan source FRR. Angka lama 58/60 tidak mewakili versi ini. Ini bukan akurasi diagnosis atau penilaian relevansi manusia.

Bukti privat utama:

- `private/host1-readiness/baseline-rto1-20261128T063352Z/`: redeploy, baseline, timer, capture dan marker Vector.
- `private/host1-readiness/matrix-rto1-20261128T063655Z/`: 12 hasil, preload, ringkasan dan evaluasi development.
- `private/host1-readiness/final-20261128T064630Z/`: verifier/capture/health akhir, hash konfigurasi dan inventory.
- `private/host1-readiness/model-profile-recovery.json`: pemulihan profil stabil setelah profiling GPU.
- `private/host1-access/`: instalasi/konfigurasi Windows lokal; tanpa kredensial di Git.

## Operasi dari terminal

Di WSL, dari root repo, gunakan user layanan yang sama untuk memeriksa tmux API/model:

```bash
bash host1/live_api/manage.sh status
# Hanya jika belum ada listener di port bersangkutan:
bash host1/live_api/manage.sh start-model
bash host1/live_api/manage.sh start-api
```

Startup API mengecek baseline dan tidak me-redeploy lab. Jangan restart saat job aktif. Jika ada marker backend completion unknown, pastikan backend selesai sebelum clear dan rekonsiliasi request; jangan menghapus checkpoint untuk memaksa lanjut.

Perintah berikut benar-benar inject dan apply, bukan monitoring. Gunakan sesi output baru dan pastikan lab idle:

```bash
bash scripts/start-benchmark.sh --out data/host2/demo/nama-sesi-baru \
  --execute --faults F01 --variants graph_rag --trials 1 --limit 1
tmux attach -r -t bench
python3 scripts/bench_status.py data/host2/demo/nama-sesi-baru --show last
# Tiga lokasi MTU, verdict target diperiksa ketat:
bash scripts/smoke_mtu.sh rule_based
```

Launcher regex-only tidak membutuhkan API/token. Untuk agen, token dibaca lokal dari private/live-agent/latest.txt. Sesi bench selesai tetap dapat dilihat. Periksa process.json melalui private/live-runner/latest.txt: exit_code terisi, hasil lengkap, tidak ada held attempt dan lab sehat. Baru tutup pane selesai sebelum sesi baru. Jangan kill runner aktif. Resume memakai output/argumen sama dan tidak POST ulang request yang completion-nya belum jelas.

## Langkah yang perlu pengguna/Host 2

1. Untuk LAN yang sama, gunakan SSH ke IP Windows dan akun yang sah. Uji autentikasi dari Host 2; port 22 terbuka saja belum membuktikannya. Public key laptop boleh dipasang pengguna, private key/password jangan dibagikan ke repo/chat.
2. Untuk luar rumah, selesaikan login aplikasi Tailscale sendiri, pilih tailnet bersama Fayyaz, lalu tailscale ip -4. Login ditunda pengguna; belum ada alamat Tailscale yang bisa dipakai. Tidak membuka port API atau port forwarding router.
3. Windows Update tetap aktif sesuai keputusan pengguna. Akses layar langsung dihentikan; setup aplikasi/login interaktif diserahkan ke pengguna.
4. Review commit lokal sebelum PR/push; tidak ada push pada pekerjaan ini. Sepakati model/profil/policy final, perbaiki latency agen bila target <10 wajib, lalu pilot semua fault/varian sebelum benchmark 600 run.
