# Log ingestion FRR dengan Vector

Pipeline aktif: FRR → file bind mount di proyek → Vector file source → normalisasi → JSON Lines per tanggal/router. Vector 0.62.0 linux/amd64 dipin digest pada `image.txt`. Tidak ada port penerima, Docker socket, atau koneksi jaringan pada container Vector.

## Mengapa file source

Image FRR 10.7.1_git ini menjalankan daemon dalam mode daemonize: stdout bgpd teramati `/dev/null`. `log stdout informational` di konfigurasi bukan bukti event daemon masuk Docker logs. Preflight membuktikan `send log` tidak muncul di Docker logs, lalu berhasil lewat file logging. Karena itu implementasi final memakai file source, bukan docker_logs atau syslog UDP.

Enam startup config menambahkan:

```text
log file /var/log/frr/events.log informational
log record-priority
log timestamp precision 6
```

YAML Containerlab menambahkan bind mount `../../../data/host1/logs/raw/rN:/var/log/frr` untuk setiap router. Path relatif dari `lab/host1/frr/`. `prepare` membuat direktori sebelum deploy dan menyesuaikan UID/GID FRR image ini (100:101). Data mentah bertahan ketika direktori runtime `clab-rca` dibuat ulang. Konfigurasi IP/OSPF/BGP tidak berubah.

## File dan schema

- `vector.yaml`: enam file input eksplisit, transform VRL, file sink, dua unit test.
- `manage.sh`: prepare, validate, test, start, status; tidak otomatis redeploy router.
- `test_live.py`: mengirim marker melalui daemon FRR, memeriksa hasil, dan menguji stop/start Vector dengan log yang tertulis selama berhenti. Tidak mengubah link/routing.
- `../../data/host1/logs/raw/r1..r6/events.log`: log FRR asli, terus bertambah.
- `../../data/host1/logs/normalized/YYYY-MM-DD/rN.jsonl`: arsip JSON Lines aktif, tanggal pemrosesan Vector dalam UTC.
- `../../data/host1/logs/vector-data/`: checkpoint file source dan disk buffer; jangan hapus ketika melanjutkan ingestion.

Setiap event memuat `schema_version`, `lab`, `router`, `source_type`, `source_file`, `event_timestamp`, `ingested_at`, `daemon`, `severity`, `parse_status`, `message`, dan `raw_message`. Identitas router diturunkan dari file input yang dipetakan ke mount router, bukan ditebak dari pesan. `router=r1` cocok dengan identitas graph indexer, tetapi penggabungan graf/log belum dibuat.

`event_timestamp` berasal dari timestamp FRR; timezone container telah diverifikasi UTC. Jika timezone diubah, parser perlu disesuaikan. `ingested_at` merupakan waktu transform Vector. Kedua waktu ini berbeda dari waktu observasi snapshot collector. Pesan tak sesuai format dipertahankan sebagai `unparsed`, dengan timestamp event/daemon/severity null. `raw_message` selalu dipertahankan; multiline stack trace belum digabung.

File source menyimpan posisi baca dalam data_dir. Disk buffer sekitar 256 MiB menggunakan backpressure saat penuh. Uji graceful restart lulus tanpa duplikasi untuk marker pengujian, tetapi ini bukan jaminan exactly-once atau tahan pemadaman mendadak. Retensi, rotasi log raw, dan penghapusan arsip otomatis belum diterapkan. Jangan truncate/hapus log dan checkpoint sembarangan; itu dapat menyebabkan kehilangan atau pembacaan ulang.

## Menjalankan di NetworkLab

Dari root proyek dalam sesi WSL interaktif, gunakan root/sudo:

```bash
bash host1/log_ingestion/manage.sh prepare
bash host1/log_ingestion/manage.sh validate
bash host1/log_ingestion/manage.sh test
# Untuk instalasi awal, deploy topologi yang sudah memiliki bind log.
# Reconfigure mengganti container lab: jalankan hanya dalam scope pemulihan/deploy yang diotorisasi.
containerlab deploy -t lab/host1/frr/topology.clab.yml --reconfigure
bash host1/log_ingestion/manage.sh start
bash host1/log_ingestion/manage.sh status
python3 host1/log_ingestion/test_live.py
```

`start` membuat container bernama `rca-vector` dan sengaja gagal jika nama sudah ada, tanpa menghapusnya. Jika container yang sama sudah ada tetapi stopped, gunakan `docker start rca-vector` sesudah memeriksa state. Periksa kondisi aktual sebelum menjalankan start atau deploy; catatan keberhasilan lama tidak membuktikan container masih berjalan.

Setelah PC dimatikan, WSL/container ikut berhenti. Buka NetworkLab dan periksa kondisi; jika interface lab hilang, pulihkan topologi sesuai panduan recovery, kemudian start Vector yang ada. Restart policy tetap no. Pertahankan terminal selama eksperimen; tidak memasang service auto-start Windows.

Vector membaca input mount read-only, mempunyai output/state mount read-write, root filesystem read-only, seluruh Linux capabilities dilepas, no-new-privileges, network none, dan API nonaktif. Script tidak menjalankan prune atau menyentuh container lain.

## Bukti dan tahap berikutnya

Lihat `../../docs/host1/VALIDATION.md`. Pengujian mencakup marker nyata dari FRR dan graceful restart Vector, bukan fault link baru. Korelasi log dengan snapshot/graf sudah tersedia; pekerjaan lintasmodul dirangkum di [status Host 1](../../docs/host1/STATUS.md).

Referensi: [Vector file source dan checkpoint](https://vector.dev/docs/reference/configuration/sources/file/), [file sink](https://vector.dev/docs/reference/configuration/sinks/file/), [image Docker](https://vector.dev/docs/setup/installation/platforms/docker/), [logging FRR](https://docs.frrouting.org/en/latest/basic.html). Sintaks marker aktual FRR 10.7.1_git adalah `send log level informational PESAN`, hasil `vtysh -c list`; `logmsg` pada dokumentasi lama tidak tersedia pada image ini.

Update: korelasi event dengan snapshot/graf sudah dibuat dan diuji live. Baca ../graph_indexer/CORRELATION.md dan ../../docs/host1/VALIDATION.md. Proses korelasi batch, bukan diagnosis atau daemon graf. Host 2 ditangani teman; scope pengguna Host 1.

## Probe cepat setelah recovery

Gunakan python3 scripts/host1.py -m log_ingestion.check_live DIREKTORI_HASIL_BARU dari root proyek NetworkLab untuk memeriksa 10 marker FRR (6 BGP+4 OSPF) tanpa restart Vector. Output mencakup event, command, salinan sumber dan hash. Probe pascarestart PC lulus19November2026; lihat ../../docs/host1/VALIDATION.md. Jangan memakai ulang direktori hasil yang sudah ada.
