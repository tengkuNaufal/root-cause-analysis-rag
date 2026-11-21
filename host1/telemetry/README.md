# Telemetry collector FRR — versi awal

Collector read-only berbasis Python standard library untuk lab `rca` di WSL `NetworkLab`. Tidak memerlukan pip install, tidak mengubah konfigurasi router, dan tidak menjalankan diagnosis/remediation.

## Cara menjalankan

Buka dan pertahankan sesi Ubuntu NetworkLab. Dari root proyek:

```bash
cd '/path/to/root-cause-analysis-rag'
sudo python3 scripts/host1.py -m telemetry.collector
```

Default mengambil satu snapshot. Untuk polling berulang:

```bash
sudo python3 scripts/host1.py -m telemetry.collector --count 10 --interval 5
```

Parameter:

| Parameter | Default | Arti |
|---|---|---|
| `--count` | 1 | Jumlah snapshot, harus positif |
| `--interval` | 5 | Interval minimum antarmulai snapshot, dalam detik |
| `--timeout` | 5 | Timeout setiap command, dalam detik |
| `--workers` | 6 | Maksimum router yang dibaca bersamaan |
| `--inventory` | `lab/host1/frr/design-plan.json` | Identitas lab/router dan pemetaan protokol |
| `--output-root` | `data/host1/telemetry` | Root penyimpanan hasil |

Siklus tidak tumpang tindih. Jika pengambilan melebihi interval, siklus berikutnya dimulai sesudah siklus sebelumnya selesai. Jadi interval merupakan target minimum, bukan jaminan real-time. Jumlah count membatasi penggunaan disk; saat ini belum ada retention/rotasi otomatis atau daemon background.

## Alur kerja

1. Baca inventory untuk membentuk nama container `clab-rca-r1` sampai `clab-rca-r6` dan menentukan router yang menjalankan OSPF.
2. Ambil data keenam router secara paralel; dalam satu router, command dijalankan berurutan dengan argument list tanpa shell interpolation.
3. Catat UTC start/end dan durasi monotonic setiap command, beserta return code dan error.
4. Simpan stdout/stderr asli, lalu parse JSON dan normalisasi ke schema versi 1.
5. Simpan snapshot seluruh router dan manifest run. Kegagalan satu sumber tidak menghapus data sumber lain.

Inventory memberi identitas dan applicability, bukan nilai pengganti untuk telemetri yang gagal. IP/MTU/state/rute di snapshot berasal dari observasi, bukan disalin dari rancangan.

## Data yang diambil

| Sumber | Command read-only di container | Data normalisasi |
|---|---|---|
| `interfaces` | `ip -j -s addr show` | Nama/index/peer index, role management/data/loopback, admin/lower state, operstate, MTU, MAC, IP, counters RX/TX |
| `ospf` | `vtysh -c 'show ip ospf neighbor json'` | Router-ID neighbor, state, interface/alamat peer, uptime dan sisa dead timer |
| `bgp` | `vtysh -c 'show bgp ipv4 unicast summary json'` | AS, router-ID, peer/state, prefix/message counters, uptime, jumlah koneksi established/dropped |
| `routes` | `vtysh -c 'show ip route json'` | Semua kandidat route FRR: prefix, protocol, selected/installed, distance, metric, uptime, next hop termasuk recursive/resolver |
| `kernel_routes` | `ip -j -4 route show` | Route IPv4 kernel untuk pembanding forwarding |

Interface mencakup eth0 dan lo selain 16 endpoint data. Counter disimpan kumulatif; belum dihitung delta/rate. Counter yang tidak tersedia bernilai `null`, bukan dianggap nol. Routing saat ini IPv4; alamat interface dapat memuat IPv6 dari Linux.

OSPF R5/R6 berstatus `not_applicable` karena inventory tidak menugaskan link OSPF. Collector tidak mengasumsikan daemon tersedia di router lain: gagal command/JSON dilaporkan sebagai error.

## Bentuk output dan timestamp

```text
data/host1/telemetry/<UTC-run-id>-<id-acak>/
  inventory.json
  manifest.json
  0001/
    snapshot.json
    raw/
      r1-interfaces.json
      r1-ospf.json
      r1-bgp.json
      ...
  0002/
    ...
```

`snapshot.json` memuat `schema_version`, `lab`, `started_at`, `completed_at`, `duration_seconds`, `status`, `source_counts`, dan `routers`. Tiap router memiliki `container`, `inventory_asn`, dan `sources`. Tiap sumber yang diambil mempunyai status, window timestamp, command, returncode, error, `raw_file`, dan `data` normalisasi. Path `raw_file` relatif terhadap direktori snapshot.

Semua timestamp adalah **waktu observasi collector dalam UTC** (`+00:00`), bukan timestamp kejadian di router. Data antarrouter/sumber tidak atomik. Timestamp per sumber memungkinkan analisis skew; perubahan singkat di antara polling mungkin tidak tertangkap. Uptime/dead timer dari FRR tetap disimpan sebagai nilai observasi, tidak dikonversi menjadi waktu kejadian yang dianggap pasti.

Status sumber:

- `ok`: command dan payload valid. State interface DOWN atau BGP Idle tetap merupakan observasi valid, bukan kegagalan collector.
- `error`: command gagal, timeout, executable tidak tersedia, atau schema/JSON tidak valid. `data` menjadi `null`; output mentah dan rincian error dipertahankan.
- `not_applicable`: sumber tidak digunakan menurut inventory, contohnya OSPF R5/R6.

Status snapshot `complete` berarti sumber yang berlaku berhasil dibaca, **bukan berarti jaringan sehat**. `partial` berarti ada sumber gagal. Manifest mencatat `running`, `complete`, `partial`, `interrupted`, atau `failed`. Exit code CLI 0 hanya untuk run lengkap; status lain exit nonzero. Run terputus mungkin hanya memiliki file raw atau manifest running apabila proses dimatikan paksa.

## Pengujian

```bash
python3 scripts/host1.py -m unittest discover -s host1/tests -p 'test_telemetry.py' -v
python3 host1/tests/validate_live_telemetry.py data/host1/telemetry/<run-id>
```

Validator live adalah pemeriksaan **baseline sehat**, bukan bagian collector dan bukan detektor fault umum. Collector tetap dapat menyimpan snapshot kondisi tidak sehat secara sah.

Uji langsung 19 November 2026: tiga snapshot, interval 2 detik, run `20261119T050248Z-fbeea22b`. Masing-masing 28 sumber sukses, 2 not applicable, 0 error; durasi 0,733272 / 0,718694 / 0,763417 detik. Semua snapshot mempunyai 16 interface data sesuai addressing/MTU 1500, 10 entri OSPF FULL (5 adjacency), 18 entri BGP Established (9 sesi), dan semua route service terpasang. Enam unit test lulus. Detail: `../../docs/host1/VALIDATION.md`.

## Batas tahap ini

Update: collector juga sudah diuji live saat L12 internal dan L35 eBGP down, lalu dipulihkan. Semua 12 snapshot complete tanpa error; perubahan interface, OSPF/BGP dan next hop terverifikasi. Baseline akhir lulus 120/120 paket; konfigurasi aktif tidak berubah. Lihat `../../docs/host1/VALIDATION.md` dan `data/host1/telemetry-faults/20261119T052911130023Z/` relatif root proyek. Script berizin `python3 scripts/host1.py -m telemetry.test_link_faults` mengubah status link; CLI collector sendiri tetap read-only.

Timeout/error payload diuji melalui unit test. Validasi L12/L35 bukan bukti bahwa semua jenis fault tertangani. Integrasi Vector, graf dan reasoning dijelaskan dalam [status Host 1](../../docs/host1/STATUS.md).
