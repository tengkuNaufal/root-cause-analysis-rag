# Status kesiapan Host 1

Pembaruan 28 November 2026. Panduan dan bukti lengkap: [READINESS.md](READINESS.md).

| Bagian | Status |
|---|---|
| Integrasi | PR #12 monitoring/demo/regex sudah diintegrasikan; commit bertahap di ashkar/host1, tanpa push. |
| Baseline | Retransmit OSPF 1 detik pada 10 interface data, disetujui dan diredeploy. Enam FRR + Vector sehat, ping 120/120, marker 10/10, capture tanpa anomali. |
| API/model | Loopback live 8766, model 11434 dalam tmux, API ready/idle. Model terpin llama3.1:8b, temperature 0, seed 42, num_gpu 20. |
| Diagnosis/perbaikan | Smoke F01–F03 × 4 varian pulih 12/12 tanpa fallback. BGP F16 juga pernah berhasil; seluruh kelas belum diuji live. |
| Target <10 detik | Regex 3/3 lulus (2,018–4,300 dtk). Sesudah optimasi agen 3/9 lulus waktu; median zero-shot 10,056, text RAG 9,566, graph RAG 11,428 detik. Semua smoke akhir memulihkan lab. |
| Executor/monitoring | CLI berbagi lab lock; runner detached dan status held/run diuji. Tidak mengeksekusi diagnosis melalui dua executor. |
| Linter/evaluator | Policy v2 menolak MTU vtysh tidak didukung. Evaluator membaca 12 hasil nyata termasuk rule_based; laporan privat, bukan benchmark resmi. |
| Tes | 362 tes repo + 90 tes Host 1 = 452 lulus. |
| Akses | SSH/Tailscale Windows terpasang/otomatis, TCP22 lokal merespons. Docker user runner aktif atas izin pengguna. Login Tailscale ditunda; SSH dari laptop belum diuji. |
| Pilihan pengguna | Sleep/hibernate AC Never; Windows Update tetap aktif. Akses layar langsung dihentikan, setup aplikasi interaktif diserahkan pengguna. |
| Berikutnya | Optimasi latency agen, autentikasi/uji dua host, review, pilot semua fault/varian, lalu benchmark 600 run. |

Semua token, model, environment, runtime, alamat pribadi dan hasil mesin di-ignore. Ground truth katalog tidak dikirim ke agen. Hasil smoke development tidak menggantikan benchmark resmi.

Optimasi berbatas waktu dan hasil terbaru: [AGENT-OPTIMIZATION.md](AGENT-OPTIMIZATION.md).
