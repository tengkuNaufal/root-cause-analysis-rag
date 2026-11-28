# Dokumentasi Host 1

Host 1 menyediakan lab FRR, telemetry/Vector/NetworkX, retrieval Chroma, agen tiga varian, API diagnosis live dan executor lokal berotorisasi. Kesiapan lokal diperbarui pada 28 November 2026. Tiga varian berhasil memperbaiki fault MTU F01 nyata; target pemulihan di bawah 10 detik belum lulus. Akses Windows sudah dipasang, login Tailscale ditunda pengguna. Status aktual ada pada [STATUS.md](STATUS.md).

| Dokumen | Kegunaan |
|---|---|
| [Kesiapan dua host](READINESS.md) | Hasil smoke nyata, layanan persisten, akses dan pekerjaan tersisa |
| [Status](STATUS.md) | Kemampuan yang tersedia, pembagian kerja, dan pekerjaan berikutnya |
| [Operasional](OPERATIONS.md) | Struktur file, environment, menjalankan modul, dan pemulihan setelah migrasi |
| [Validasi](VALIDATION.md) | Hasil pengujian, asal kesimpulan, dan batas klaim |
| [Topologi](TOPOLOGY-DESIGN.md) | Router, link, addressing, AS, OSPF, BGP dan policy Host 1 |
| [Peta folder dan file](REPOSITORY.md) | Penjelasan fungsi setiap file kandidat Git dan kelompok file lokal yang di-ignore |

Panduan penggunaan dan opsi CLI berada bersama modulnya:

| Modul | Panduan |
|---|---|
| Lab FRR | [lab/host1/frr](../../lab/host1/frr/README.md) |
| Telemetry dan graf | [collector](../../host1/telemetry/README.md), [graf](../../host1/graph_indexer/README.md), [korelasi](../../host1/graph_indexer/CORRELATION.md) |
| Ingestion log | [Vector](../../host1/log_ingestion/README.md) |
| Retrieval dan evidence | [retriever](../../host1/knowledge/README.md), [evidence](../../host1/knowledge/EVIDENCE.md), [quality gate](../../host1/knowledge/QUALITY-GATE.md) |
| Kontrak dan model | [kontrak agen](../../host1/agent_contract/README.md), [Ollama](../../host1/ollama_host/README.md) |
| Reasoning dan API | [adapter](../../host1/reasoning_agent/README.md), [temporal](../../host1/reasoning_agent/TEMPORAL.md), [MTU](../../host1/reasoning_agent/MTU.md), [API](../../host1/reasoning_agent/API.md) |

Lab replika, katalog fault dan runner kelompok dijelaskan di [fault harness](../fault-harness.md). Akses laptop dijelaskan di [panduan SSH](../akses-dari-laptop.md). Konfigurasi replika berbeda dari Host 1.

Client HTTP untuk menjalankan 16 replay dari Host 2 tersedia pada [panduan replay dan JSONL](../host2-replay.md); client ini tidak memerlukan SSH atau instalasi model di Host 2.

Rencana integrasi berikutnya ada di [draf kontrak API live](LIVE-API-DRAFT.md). [Schema, contoh payload dan mock lokal](../../host1/live_api/README.md) sudah tersedia untuk pengembangan client Host 2 tanpa router/model. API live loopback sudah aktif untuk commissioning; kontrak replay tetap berlaku.

Pembaruan 28 November: [jalur diagnosis live read-only](../../host1/live_api/README.md#agen-diagnosis-live-read-only) sudah diimplementasikan dengan capture baru, evidence beku dan tiga jalur konteks, dengan observasi konfigurasi sepuluh kelas serta proposal yang diperiksa linter. Cakupan pengujian dipisahkan antara unit/simulasi, commissioning model pada baseline sehat, dan fault live yang belum dijalankan.

Laporan per tahap, catatan progres berulang dan panduan migrasi lama digabung menjadi dokumen di atas. Salinan lengkapnya tetap disimpan lokal di `private/docs-history/host1/`, yang diabaikan Git. Data yang dibagikan mengikuti [kebijakan fixture](../../data/host1/README.md).
