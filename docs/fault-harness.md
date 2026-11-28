# Katalog fault dan runner

Bagian ini dipakai untuk menyuntikkan gangguan ke lab, menunggu gejalanya muncul, lalu memulihkan lab ke kondisi awal. Semua skrip jalan di Ubuntu yang menjalankan containerlab. Dari laptop, skrip yang sama dipanggil lewat SSH (lihat [akses-dari-laptop.md](akses-dari-laptop.md)).

## Isi

| Path | Isi |
|---|---|
| `faults/host1.yaml` | 30 fault untuk lab `rca` (Host 1): langkah inject, langkah revert, gejala yang diharapkan, ground truth |
| `faults/replica.yaml` | 30 fault untuk lab replika `topik8` |
| `scripts/check_lab.py` | cek interface, MTU, OSPF, BGP, dan ping antar-router, lalu simpan snapshot JSON |
| `scripts/fault_runner.py` | jalankan fault dari katalog, revert manual, dan buat jadwal benchmark |
| `scripts/bench.py` | jalankan jadwal benchmark: inject, minta diagnosis ke API live Host 1, cek evidence dan linter, revert |
| `scripts/live_client.py` | client HTTP untuk API live (kontrak `live.v1-draft2`) |
| `scripts/bench_status.py` | ringkasan progres sesi benchmark dan detail satu run, cuma baca file hasil |
| `scripts/demo.sh` | satu run live lengkap untuk demo, hasilnya di `data/host2/demo/` |
| `lab/replica/` | lab replika enam router yang dipakai sebelum topologi Host 1 tersedia |
| `data/rca-sim/` | hasil uji 30 fault Host 1 di lab tiruan topologi `rca` |
| `data/replica/` | hasil uji 30 fault di lab replika |
| `data/benchmark_plan.csv` | jadwal 450 run (30 fault x 3 varian x 5 trial), urutan acak dengan seed 42 |

Ground truth di katalog hanya dibaca runner dan evaluator. Jangan dikirim ke agen.

## Cek lab

```bash
python3 scripts/check_lab.py              # lab rca (default)
python3 scripts/check_lab.py --lab topik8 # lab replika
```

Untuk lab `rca`, kondisi normal dibaca langsung dari `lab/host1/frr/design-plan.json`: interface tiap router, tetangga OSPF di link OSPF, peer eBGP, dan iBGP full mesh r1-r4. Ping memakai alamat service `10.100.N.1` sebagai sumber dan tujuan, karena r5 dan r6 tidak punya rute ke loopback `10.255.0.N`. Kalau lab normal, hasilnya:

```text
Lab rca: 6 router, ping 30/30 berhasil
SEMUA CEK LOLOS
```

`check_lab.py` hanya membaca state. Untuk pemeriksaan baseline yang lebih lengkap, tetap pakai `lab/host1/frr/verify-runtime.py`.

## Menjalankan fault

```bash
python3 scripts/fault_runner.py list
python3 scripts/fault_runner.py run F01 F16
python3 scripts/fault_runner.py run --all
python3 scripts/fault_runner.py --catalog faults/replica.yaml run --all
python3 scripts/fault_runner.py plan --seed 42
```

Untuk tiap fault, runner mengecek kondisi awal, menyuntikkan fault, menunggu gejala, menyimpan evidence, menjalankan revert, lalu menunggu sampai semua cek lolos dan rute ke alamat ping sama lagi dengan kondisi awal. Gejala dihitung dari cek yang gagal ditambah rute yang berubah. Revert selalu dijalankan, termasuk kalau inject atau observasi gagal di tengah. Hasilnya satu baris JSON per fault di `data/runs/` dengan `status`: `ok`, `not_observable`, `error`, atau `not_recovered`. Run berhenti pada `error` dan `not_recovered`, dan exit code-nya 0, 1, 2, atau 3 sesuai status terburuk.

Kalau run berhenti dengan fault masih terpasang, kembalikan manual dengan `python3 scripts/fault_runner.py revert F07`, lalu cek dengan `check_lab.py`.

Runner mengubah konfigurasi router yang sedang jalan. Jalankan hanya kalau kelompok sudah sepakat lab boleh diganggu.

## Benchmark dengan API live

`bench.py` menjalankan baris `data/benchmark_plan.csv` mengikuti [draf kontrak API live](host1/LIVE-API-DRAFT.md). Token dibaca dari environment `LIVE_API_TOKEN` dan tidak pernah ditulis ke file.

```bash
read -rsp 'Token: ' LIVE_API_TOKEN; export LIVE_API_TOKEN
python3 scripts/bench.py --api http://127.0.0.1:8766 --out data/host2/pilot --faults F01,F16,F22 --trials 1
python3 scripts/bench.py --api http://127.0.0.1:8766 --out data/host2/mock-test --no-lab --limit 5
```

Alur satu baris jadwal:

1. Cek API `ready` dan tidak `active`, lalu cek lab dan tabel rute sama dengan baseline sesi. Kalau gagal, fault tidak di-inject.
2. Inject, tunggu gejala, lalu kirim request diagnosis. Request hanya berisi versi kontrak, `request_id` acak, lab, varian, waktu gejala, dan `execution_allowed: false`. ID fault dan ground truth tidak dikirim.
3. Polling tiap 1 detik dengan batas 180 detik sejak sebelum POST. Kalau respons POST hilang, job dicari lewat `request_id`.
4. Kalau job selesai, cek dulu jawabannya terikat ke request yang dikirim (`request_id`, `job_id`, varian, lab), `execution_allowed` tetap false, dan label `result.root_cause_class`/`root_cause_router` sama dengan `assessment`. Kalau model pydantic Host 1 bisa di-import, job juga divalidasi ke schema. Gagal di sini dicatat `invalid_response`.
5. Cek setiap evidence di manifest. Kalau ada yang tidak cocok, baris dicatat `evidence_error` dan perintah agen tidak di-lint. Kalau cocok, jalankan linter Naufal (`rca.linter`) ke `assessment.commands` dan simpan hash perintahnya. Patch kosong dicatat `not_requested`.
6. Tanpa `--execute`, perintah agen tidak pernah diterapkan (`applied: false`). Dengan `--execute`, perintah yang lolos linter diterapkan, lalu runner menunggu lab pulih sampai `--agent-verify-timeout` (default 60 detik).
7. Kalau agen tidak memulihkan lab atau perintahnya tidak diterapkan, runner menjalankan revert katalog, lalu me-reset router yang konfigurasi FRR-nya beda dari baseline. Kalau lab masih belum sehat, semua router di-reset.

### Eksekusi perintah agen (`--execute`)

```bash
python3 scripts/bench.py --api http://127.0.0.1:8766 --out data/host2/smoke --execute --faults F01 --variants graph_rag --trials 1
```

Sebelum menerapkan, runner memastikan hash perintah masih sama dengan yang di-lint dan gejala fault masih ada. Kalau tidak, perintah dilewati (`precondition_changed` atau `commands_changed_after_lint`). Perintah `ip` dijalankan sebagai `docker exec <router> ip <args>` dan perintah `vtysh` sebagai `vtysh -c <baris>` per baris, tanpa shell. Perintah berhenti di kegagalan pertama.

Kalau lab pulih setelah perintah agen, hasilnya `verification.source: agent`, `fallback_revert.performed: false`, dan `timing.agent_recovery_s` diisi (gejala terdeteksi sampai lab terverifikasi pulih). Sisa perubahan agen yang membuat konfigurasi beda dari baseline dibersihkan di `cleanup` dan tidak dihitung sebagai fallback. Kalau agen gagal, `fallback_revert.reason` berisi `agent_fix_failed`.

Baseline konfigurasi diambil di awal sesi sebagai hash `show running-config` tiap router (`<out>/baseline_configs.json`). Reset router memakai `ip link set <iface> mtu 1500 up` dan `frr-reload.py --reload /etc/frr/frr.conf`, jadi `/etc/frr/frr.conf` di container harus tetap sama dengan startup-config (jangan `write memory` selama benchmark).

Di lab tiruan dengan agen tiruan yang langsung memberi perbaikan benar, `agent_recovery_s` berkisar 5 sampai 11 detik untuk F01, F07, F16, F25, dan F28. Angka ini belum termasuk waktu diagnosis model, jadi target di bawah 10 detik sulit tercapai untuk fault OSPF dan alamat IP yang butuh adjacency terbentuk ulang.

Sejak POST dikirim sampai job jelas terminal, runner tidak menyentuh lab. Satu-satunya kondisi yang dianggap penolakan pasti adalah respons POST pertama berupa 4xx atau kode admission (`agent_busy`, `live_not_ready`, `replay_session_reserved`). Job berarti tidak pernah dibuat, jadi fault langsung di-revert. Error transport, 5xx, atau 404 saat mencari job lewat `request_id` belum berarti ditolak, karena request mungkin masih diproses. Runner terus mencari job tanpa POST ulang sampai batas `--reconcile`.

Kalau job tetap tidak jelas, termasuk kalau batas 180 detik dan `--reconcile` (default 600 detik) habis atau operator menekan Ctrl+C setelah POST, runner menulis checkpoint `held` di `journal.jsonl` (request_id, job_id, alasan), membiarkan fault terpasang, tidak menulis hasil final, dan berhenti dengan exit code 4. Ctrl+C sebelum POST tetap me-revert fault, dicatat `interrupted_operator`. Kalau job selesai terlambat tapi masih dalam batas `--reconcile`, baris dicatat `timeout` dan hasilnya masuk `journal.jsonl`.

Hasil ada di `<out>/results.jsonl`, satu baris per baris jadwal per attempt, dengan field sesuai bagian "Catatan JSONL milik Host 2" di draf kontrak. Kejadian perantara ada di `<out>/journal.jsonl`, dan tabel rute baseline sesi di `<out>/baseline_routes.json`. Menjalankan ulang perintah yang sama akan melewati baris yang sudah punya hasil, tetapi sebelumnya merekonsiliasi baris yang ditahan atau terputus: job dicari lewat `request_id` dan harus terminal dulu, baru fault-nya di-revert dan hasil finalnya ditulis. Kalau job tidak ditemukan sama sekali, runner tetap berhenti. Setelah dipastikan ke Host 1 bahwa job itu tidak ada, lepas barisnya dengan `--release <order>`. Baris hasil rekonsiliasi tidak diulang otomatis, ulangi secara eksplisit dengan `--retry <order>`.

Tes regresi untuk perilaku ini ada di `tests/test_bench_runner.py` (lab dan API tiruan, tanpa Docker).

Setiap titik waktu di `timing` (`t_inject`, `t_symptom`, `t_request`, `t_diagnosis_done`, `t_lint_done`, `t_apply_done`, `t_revert`, `t_verified`) berbentuk `{"utc": ..., "elapsed_s": ...}`. `elapsed_s` diukur monotonic dari awal baris, UTC hanya untuk korelasi. Durasi turunannya ikut ditulis: `detection_s`, `diagnosis_s`, `job_wait_s`, `fallback_recovery_s`, dan `agent_recovery_s` (selalu null selama read-only).

Kalau API melapor `simulation` atau mode selain `live`, runner menolak jalan sebelum menyentuh lab, kecuali dengan `--no-lab`. Mode itu hanya untuk menguji client ke mock: tidak ada inject, revert, atau cek lab.

Satu lab cuma boleh dipakai satu proses `bench.py`. Runner memegang lock `/tmp/bench-<lab>.lock` selama jalan, jadi demo atau benchmark kedua langsung ditolak dengan exit code 1 tanpa menyentuh lab.

Progres sesi bisa dicek kapan saja tanpa mengganggu runner:

```bash
python3 scripts/bench_status.py data/host2/bench            # progres per varian, baris bermasalah, 5 run terakhir
python3 scripts/bench_status.py data/host2/bench --show 12  # detail baris jadwal 12
bash scripts/demo.sh F01 graph_rag                          # satu run live untuk demo
```

Dari laptop, perintah yang sama tersedia lewat `laptop\lab.ps1 status`, `watch`, dan `demo` (lihat [akses-dari-laptop.md](akses-dari-laptop.md)).

## Katalog Host 1

| Kelas | Lokasi |
|---|---|
| MTU tidak sama | L12, L34, L23 |
| Interface mati | L13, L35, L56 |
| Hello timer OSPF beda (2 detik vs 1) | L12, L24, L34 |
| Area OSPF beda | L13, L24, L23 |
| Autentikasi OSPF tidak cocok | L12, L13, L23 |
| Neighbor BGP di-shutdown | iBGP r1-r4, eBGP L35, eBGP L56 |
| Remote-AS BGP salah | iBGP r2-r3, eBGP L46, eBGP L56 |
| Prefix ditolak filter inbound | r3 dari r5, r4 dari r6, r5 dari r6 |
| Network BGP tidak diiklankan | r1, r5, r6 |
| Alamat IP interface salah | L12, L35, L46 |

## Hasil uji di lab tiruan Host 1

Katalog `faults/host1.yaml` sudah dijalankan di lab tiruan yang dibuat dari `topology.clab.yml` dan `configs/` Host 1, dengan image FRR yang sama (`containerlab-10.7.1`). Ke-30 fault menimbulkan gejala dan pulih ke kondisi awal (`data/rca-sim/`). Belum dijalankan di Host 1 yang asli.

- Gejala muncul dalam 4 sampai 12 detik, jauh lebih cepat dari lab replika, karena Host 1 memakai OSPF hello 1 / dead 4 dan BGP 3 / 9.
- Hanya 9 dari 30 fault yang bikin ping gagal: L56 mati, neighbor shutdown dan remote-AS salah di iBGP r1-r4/r2-r3 dan L56, filter di r5, dan ketiga network yang hilang. Sisanya tertutup jalur cadangan di inti r1-r4 atau di segitiga eBGP, jadi cuma kelihatan dari state OSPF/BGP dan perubahan rute.
- Ketiga hello timer, dua autentikasi OSPF, filter inbound di r3/r4, dan IP salah di link eBGP pada saat terdeteksi hanya menyisakan perubahan rute. Agen perlu membaca state protokol dan tabel rute, hasil ping saja tidak cukup.
- Waktu yang tercatat ikut menghitung lamanya pengecekan, jadi angkanya kasar.

## Lab replika

Lab replika (`lab/replica/`) dipakai sebelum topologi Host 1 tersedia: tiga AS, masing-masing dua router, eBGP segitiga di antara r2, r4, r6.

```bash
docker pull quay.io/frrouting/frr:10.4.1
cd lab/replica/six-node
sudo containerlab deploy -t topik8.clab.yml
cd ../../..
python3 scripts/check_lab.py --lab topik8
```

Ke-30 fault di `faults/replica.yaml` juga sudah lolos di lab ini (`data/replica/`).
