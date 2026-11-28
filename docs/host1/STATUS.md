# Status Host 1 sebelum smoke test MTU

Pembaruan 28 November 2026. Scope pekerjaan berakhir sebelum smoke test MTU di bawah 10 detik, pilot dan benchmark. Tidak ada commit/push pada penyelesaian ini.

| Bagian | Status dan bukti |
|---|---|
| Lab enam FRR | Dipulihkan dari folder baru; enam router dan Vector berjalan. Baseline: 8 link, 5 OSPF FULL, 9 BGP Established, ping 30/30 arah dan 120/120 paket. |
| Telemetry, log, graf | Capture terbaru dan 10/10 marker Vector lulus. Graph RAG membangun neighborhood NetworkX dari snapshot yang sama. |
| Retrieval | Chroma Host 1 tetap utuh; konteks live memakai query setting yang dinormalisasi dan ekspansi sumber primer berhash. Set Host 1 60 pertanyaan ID/EN sudah dibekukan dan diukur; hasil proxy/batasnya di VALIDATION.md. |
| Katalog dan runner | Tetap memakai 30 fault/10 kelas pada faults/host1.yaml. Runner PR #8 menjaga held/reconcile/Ctrl+C; tidak ada fault nyata dijalankan pada tahap ini. Daftar final belum dibekukan untuk benchmark. |
| Linter | Format internal/steps/wire didukung; POLICY_VERSION=host1-policy-v1 dan hash source dicatat. Executor menolak policy yang berubah setelah dimuat. |
| Evaluator | File branch Naufal 40e5f97 diintegrasikan ke working tree, bukan merge commit. Membaca assessment/manifest/status lint/timing, applied default false, dan fallback/partial execution tidak dihitung sukses agen. Hash katalog diperiksa. |
| Ollama/model | Model lokal llama3.1:8b yang dipin dipakai untuk commissioning ketiga varian. Profil live sama: context 8192/output 768/seed 42/temperature 0/num_gpu 20. Bukan studi pemilihan model komparatif. |
| Agen live tiga varian | Zero-shot, text RAG dan graph RAG memiliki jalur konteks berbeda, label/router eksplisit dan proposal unvalidated. Dukungan observasi sepuluh kelas diuji dengan konfigurasi/model tiruan. Model nyata berhasil pada baseline sehat (3 completed/abstain), belum akurasi diagnosis fault live. |
| API/client | API live 127.0.0.1:8766 memakai token privat, persistent jobs, idempotensi dan evidence terverifikasi. HTTP graph RAG nyata lulus. Replay tidak diubah dan tidak dipakai paralel untuk inferensi. |
| Executor/verifier/workflow | Implementasi lokal tersedia: diagnose → evidence → lint → preview/apply berotorisasi → verifier. Apply default mati; hash/precondition/policy/ledger diperiksa. Dispatch diuji dengan router tiruan; verifier baseline nyata lulus. Belum ada apply repair ke router nyata. |

Panduan operasional: [API/agen/executor](../../host1/live_api/README.md). Bukti terperinci dan batas klaim: [VALIDATION.md](VALIDATION.md). Artefak mesin, token, log dan hasil tetap di private/ yang di-ignore.

## Tahap berikutnya, belum dijalankan

1. Smoke MTU end-to-end secara terkontrol, termasuk diagnosis, lint, apply dan verifikasi, baru ukur target di bawah 10 detik. Belum ada klaim target tersebut tercapai.
2. Setelah smoke lulus, selaraskan pemakaian receipt executor pada runner dan jalankan pilot yang disepakati sebelum benchmark.
3. Bekukan katalog/model/versi policy dan jadwal; putuskan apakah perlu pembanding regex. Perbandingan model dan pilihan kelas pengganti tetap keputusan kelompok.
4. Benchmark 450 run, analisis hasil, laporan akhir dan demo berada di luar pekerjaan ini.

Sukses baseline/abstain, unit test, dan hit@5 retrieval tidak boleh disebut sukses repair atau akurasi fault live. Eksekusi tidak pernah diaktifkan oleh model, hasil lint saja atau token API diagnosis.
