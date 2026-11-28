# Status kesiapan Host 1

Pembaruan 28 November 2026. Detail operasi, bukti dan batas klaim ada di [READINESS.md](READINESS.md).

| Bagian | Status |
|---|---|
| Integrasi kode | Branch monitoring/demo Fayyaz diintegrasikan; commit bertahap pada branch ashkar/host1, tanpa push. |
| Lab/telemetry | Enam FRR dan Vector berjalan; baseline diperiksa kembali setelah smoke. |
| API/model | Live loopback 8766 dan Ollama 11434 dalam tmux; kontrak live.v1-draft2, replay terpisah. |
| Tiga varian | F01 nyata berhasil didiagnosis dan dipulihkan oleh zero-shot, text RAG dan graph RAG tanpa fallback. Bukan bukti akurasi seluruh katalog. |
| Executor/lock | Benchmark memakai executor runner; standalone alternatif. Semua CLI perubahan lab berbagi lock. |
| Linter | POLICY_VERSION=host1-policy-v2; menolak MTU vtysh yang tidak didukung build nyata. |
| Evaluator/retrieval | Format live terintegrasi; retrieval corrected expansion 52/60 keyword hit@5, bukan akurasi agen. |
| Monitoring/persistence | Status run/held attempt tersedia; satu smoke detached tetap selesai setelah launcher terminal berakhir. |
| Akses Windows | SSH dan Tailscale terpasang, service otomatis, port 22 lokal merespons. Login Tailscale ditunda pengguna; authentication dari Host 2 belum diuji. |
| Daya/update | Sleep dan hibernate AC Never. Windows Update tetap aktif sesuai pilihan pengguna. |
| Smoke MTU <10 detik | Belum lulus. Pemulihan development F01: 19,448 / sekitar 22,8 / 37,635 detik; cache/warmup tidak seragam, bukan perbandingan varian. |
| Pilot/benchmark | Belum dijalankan. Regex dan protokol 600 run perlu integrasi/keputusan kelompok. |

Token, hasil dan data mesin tetap privat/di-ignore. Ground truth katalog tidak dikirim ke model. Setup aplikasi yang membutuhkan login/interaksi diserahkan kepada pengguna. Pengujian dua host, seluruh fault, benchmark resmi dan presentasi bukan hasil yang sudah terbukti dari smoke lokal ini.
