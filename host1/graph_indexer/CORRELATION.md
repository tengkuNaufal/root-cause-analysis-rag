# Korelasi log Vector, snapshot, dan graf — Host 1

Scope pengguna hanya Host 1. Host 2 ditangani teman pengguna; tidak ada perubahan atau deployment Host 2 pada tahap ini.

## Alur dan model

1. `telemetry.collector` mengambil snapshot JSON dari enam router.
2. Vector tetap membaca file FRR dan menulis JSONL. Setelah event yang diperlukan terkirim, JSONL disalin menjadi evidence tetap agar hasil dapat direproduksi.
3. `graph_indexer.correlate` membangun graf topologi dari snapshot, kemudian menambahkan node snapshot, observasi sumber, dan event log.
4. Setiap event mengarah ke router melalui `emitted_by`, ke snapshot melalui `temporal_context`, dan ke observasi `bgp`/`ospf` router yang sama melalui `protocol_context` jika daemon cocok.

Observasi sumber menyimpan status ok/error/not_applicable, waktu mulai/selesai, path snapshot, JSON pointer dan raw_file. Nilai telemetry tetap berada di snapshot dan graf topologi. Node event menyimpan event lengkap serta path JSONL, nomor baris 1-based, dan SHA-256 file. Metadata graf menyimpan hash snapshot/inventory/JSONL. Identitas router sama dengan collector dan Vector (`r1` sampai `r6`).

## Aturan waktu dan ketidakpastian

Default window inklusif: `[snapshot.started_at - 60 detik, snapshot.completed_at]`. Gunakan `--lookback` untuk mengubahnya. Seleksi memakai `event_timestamp` FRR, bukan `ingested_at` Vector; log terlambat dikirim masih dapat cocok pada snapshot yang benar. Timestamp wajib berzona waktu. Perbandingan memakai mikrodetik agar kompatibel Python 3.10; timestamp asli nanodetik ingestion tetap disimpan.

Edge snapshot membedakan `before` dan `during`. Edge observasi protokol memakai waktu sumber itu sendiri: before/during/after/unknown. Pengambilan sumber tidak atomik; event dalam jendela snapshot belum tentu terjadi sebelum pengamatan BGP router tersebut. `causal_claim=false`: hubungan ini konteks temporal, bukan diagnosis, bukti peer tertentu, atau perintah perbaikan.

Log terlalu lama/lebih baru, lab salah, router tak dikenal, schema salah, dan timestamp/message tak valid tidak dimasukkan ke graf; alasan serta evidence dicatat dalam correlation.json. Baris JSON rusak dicatat terpisah. Event unparsed dengan timestamp null tetap ada pada arsip Vector, tetapi tidak diberi waktu buatan untuk memaksanya cocok.

Deduplikasi memakai lab + router + event_timestamp + raw_message. Event identik digabung dengan seluruh pointer evidence tetap dipertahankan. Dua kejadian sah dengan seluruh field tersebut identik dapat tergabung; ini belum deduplikasi universal berbasis event ID dari FRR. Log tidak mengubah state telemetry: sumber gagal tetap unknown/error meskipun ada log BGP.

## Penggunaan

Gunakan virtual environment Windows `.venv-graph` dengan NetworkX 3.4.2 yang sudah tersedia. Contoh dari root proyek; output harus direktori baru:

```powershell
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m graph_indexer.correlate data/host1/integration/20261119T095707Z-b120b2/after/snapshot.json --inventory data/host1/integration/20261119T095707Z-b120b2/inventory.json --logs data/host1/integration/20261119T095707Z-b120b2/logs --output data/host1/integration/contoh-korelasi-baru --lookback 60
```

Hasil: `graph.json` dapat dimuat dengan `nx.node_link_graph(data, edges='edges')`; `correlation.json` berisi jendela waktu, jumlah event, alasan pengecualian, input hashes, dan ringkasan topologi.

Untuk mengulang uji live Host 1 ketika lab/Vector aktif, dari root di NetworkLab:

```bash
python3 scripts/host1.py -m graph_indexer.capture_live
```

Perintah tersebut mengambil snapshot before, mengirim 10 marker lewat `vtysh send log` (6 BGP + 4 OSPF), mengambil snapshot after, menunggu Vector maksimal 40 detik, dan membekukan JSONL. Tidak ada fault link atau perubahan konfigurasi. Hanya baris lengkap disalin; jika saat capture ada ekor parsial, jumlah byte dicatat di capture.json dan data asal tetap utuh.

Lalu dari PowerShell, gunakan direktori run baru yang dicetak (ubah path WSL menjadi path proyek Windows):

```powershell
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m graph_indexer.validate_live data/host1/integration/ID-RUN-BARU
```

Validator mengekspor graf before/after, menguji round-trip JSON, penempatan event, identitas router/protokol, dan baseline graf. `integration-validation.json` juga menyimpan contoh hasil penelusuran per router: event → evidence log → observasi telemetry.

Integrasi saat ini batch/on-demand, belum daemon pembaruan graf otomatis. Capture live berjalan di WSL dan korelasi diuji pada Python Windows, keduanya pada Host 1. NetworkX belum dipasang/dijalankan di WSL. Sinkronisasi clock antarhost, watermark event, query API, dan RAG belum diimplementasikan. Langkah berikutnya uji konteks saat gangguan berizin atau integrasi retrieval sesuai prioritas proyek.

## Uji fault live

Korelasi sudah diuji pada L12 internal dan L35 eBGP dengan event transisi FRR asli, bukan marker sebagai evidence fault. Lihat ../docs/VALIDATION.md. Script capture_faults.py mengubah kedua link dan memulihkannya; hanya jalankan dalam scope fault berizin. validate_faults.py memeriksa enam graf before/down/restored terhadap state dan event, tanpa mengubah lab.
