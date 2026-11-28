# Hasil validasi dan batas kesimpulan

Dokumen ini membedakan validasi terbaru dan laporan historis. Laporan lengkap serta artefak mesin tetap lokal di `private/` yang di-ignore.

## Penyelesaian komponen sebelum smoke MTU — 28 November 2026

Setelah scope diperluas pengguna, lab dipulihkan dari konfigurasi Host 1 di repositori baru. Enam router dan Vector berjalan, restart count 0. Baseline lulus: 8 link/16 endpoint MTU 1500, 5 OSPF FULL, 9 BGP Established, 6 prefix service per router, ping 30/30 arah dan 120/120 paket. Vector menerima 10/10 marker dari enam router. Capture aktual 1,795 detik tidak menemukan anomali. Bukti: `private/pre-mtu-setup/20261128T045119Z/` dan direktori capture pada folder yang sama.

Model lokal terpin llama3.1:8b dipakai untuk baseline sehat melalui ketiga varian: zero-shot, text RAG dan graph RAG semuanya completed/abstain. Ini memverifikasi jalur inferensi dan abstention; bukan akurasi diagnosis fault. API loopback 8766 memakai token privat, evidence berhash, penyimpanan job dan pencarian request_id. Replay 8765 sudah tidak aktif sejak awal tahap ini dan tidak dinyalakan atau diubah. Model live tidak dipakai bersamaan dengan replay.

Tes akhir: 282 tes repo dan 80 tes Host 1/kontrak/agen/executor/workflow/regresi replay lulus, total 362. Router, model dan dispatch pada unit test adalah tiruan. Dukungan observasi sepuluh kelas diuji dari perbedaan konfigurasi/physical facts, tanpa membaca ground truth di runtime. Executor default preview; apply lokal memerlukan otorisasi dan hash diagnosis, lint, policy fingerprint, evidence/precondition serta ledger idempotensi. Verifier baseline nyata lulus. Belum ada command repair dikirim ke router nyata.

Commissioning workflow nyata pada kode terakhir lulus: graph RAG completed/abstain, 4/4 evidence terverifikasi, executor not_requested/applied=false. Bukti: `private/pre-mtu-setup/workflow-8f65e1e8446d44f29db32158ef25ace5/`. Percobaan sebelumnya ditolak karena model mengisi confidence=0 ketika abstain; grammar kini mewajibkan null, ditambah regresi schema. Kegagalan awal tetap tersimpan privat dan tidak dihitung sebagai run sukses.

Set retrieval Host 1 berisi 60 pertanyaan ID/EN untuk 30 lokasi fault. Pengukuran full chunks: dense 43/60, hybrid 46/60, hybrid dengan verified expansion 58/60 hit@5 menggunakan keyword proxy. Ekspansi dikembangkan setelah hasil awal; ini hasil pengembangan, bukan evaluasi held-out atau penilaian manusia. Skor excerpt awal 46/60 tidak dibandingkan langsung dengan baseline full chunks. Skor full chunks tidak membuktikan kualitas excerpt prompt atau akurasi agen. Artefak: `private/pre-mtu-setup/retrieval-host1-evaluation/` dan `retrieval-host1-expanded-full/`.

Linter memiliki POLICY_VERSION dan fingerprint source. Evaluator branch Naufal 40e5f97 disalin ke working tree untuk integrasi; format assessment/evidence/lint/timing, default applied=false, fallback dan partial execution dijaga oleh tes. Runner PR #8 tetap utuh. Tidak ada commit, push, fault injection, apply nyata, smoke MTU <10 detik, pilot atau benchmark 450 run pada tahap ini.

## Riwayat tahap read-only sebelum perluasan scope — 28 November 2026

Implementasi capture/agent/server tersedia, terbatas pada interface administratively down dan MTU unequal yang didukung observasi dan inventory. Tiga jalur konteks memakai observasi, observasi+dokumentasi, serta observasi+dokumentasi+graf. Proposal perbaikan selalu kosong. Model/fault catalog/ground truth runner tidak digunakan sebagai sumber pengganti telemetry. Belum ada klaim dukungan sepuluh kelas, akurasi atau perbaikan jaringan live.

Sebanyak 60 tes agen/mock/kontrak/replay lulus, termasuk 17 tes baru dengan transport capture/model sintetis. Sebanyak 265 tes repo juga lulus, termasuk regresi runner terbaru pada main 99f6f0d: total 325 tes. Dependency NetworkX untuk sesi ini dipasang ke private/live-agent-deps, tidak mengubah venv replay. Tes memakai port sementara dan data sementara; tidak ada inferensi Ollama asli atau perintah router nyata pada tes tersebut. Main diambil melalui fast-forward tanpa membuat commit baru; perubahan agen berada pada branch codex/host1-live-readonly-agent.

Preflight aktual mendapati keenam router dan Vector exited; port replay 8765 dan model 11434 tidak merespons sejak awal pekerjaan. CLI live dijalankan sementara di loopback port OS terpilih untuk negative-admission smoke: health ready=false (lab_unavailable/baseline_not_confirmed/model_session_not_reserved), POST ditolak HTTP 503 dan tidak membuat inferensi. Listener baru dihentikan. Status/start/restart/hash konfigurasi container dan kondisi kedua port lama sama sebelum/sesudah. Bukti privat: private/live-agent-preflight/75a95f8bf31d4d6eb8256ffab6923c1f/summary.json.

Baseline sehat belum dapat dibuktikan; pengguna melarang perubahan router sehingga tidak dilakukan pemulihan, deploy/reconfigure, fault, startup model atau startup replay. Validasi sumber/model nyata harus dilakukan setelah lab/model dipulihkan dengan izin terpisah. Hasil negative-admission dan simulasi bukan hasil diagnosis live nyata.

## Lab dan telemetry

| Pengujian historis | Hasil |
|---|---|
| Baseline enam router | Delapan link, lima OSPF FULL, sembilan BGP Established, ping 30/30 arah dan 120/120 paket |
| Fault/pemulihan L12 dan L35 | Dua belas snapshot lengkap; perubahan interface, peer dan rute tercatat; baseline pulih |
| Graph indexer | Replay 15 snapshot dan lima unit test lulus |
| Korelasi log dan graf | Uji live 10 marker, dua snapshot, 16 unit test dan baseline 120/120 paket |
| Pemulihan setelah restart | Baseline routing/ping lulus dan 10/10 marker Vector dari enam router |

Snapshot collector tidak atomik. Event log, status interface dan peer dapat berasal dari waktu pengamatan berbeda. Korelasi window dan transisi link tidak membuktikan pelaku, perintah pemicu, kerusakan perangkat atau sebab awal. Status container running pada laporan lama bukan bukti bahwa layanan masih hidup sekarang.

## Pemulihan lab dari lokasi baru — 21 November 2026

Enam router dan Vector yang berhenti dengan mount ke lokasi lama dibuat ulang dari konfigurasi sumber di repositori baru. Ketujuh container berjalan dengan restart count 0; seluruh bind mount menunjuk repositori baru. Pemeriksaan baseline lulus: 16 endpoint pada delapan link UP/LOWER_UP dengan alamat sesuai desain dan MTU 1500, lima adjacency OSPF FULL, sembilan sesi BGP Established, enam prefix service per router, forwarding aktif dan tanpa default route management. Ping service lulus 30/30 arah, 120/120 paket; route-get memakai interface data.

Satu snapshot collector lengkap memiliki 28 sumber sukses, dua not applicable dan nol error, serta lolos validator baseline. Vector menerima tepat 10 marker (enam BGP dan empat OSPF) dari enam router. Tidak ada fault injection atau pengujian repair pada tahap ini.

API replay tetap memakai proses API/Ollama dan katalog 16 skenario yang sama. Selama pemulihan, 21 sampel health berhasil tanpa error; 11 sampel menunjukkan request sedang aktif. Sesudah deploy, health melalui loopback dan listener LAN tetap `ok`, dengan eksekusi dinonaktifkan. Ini memverifikasi kesinambungan layanan dari Host 1; hasil akhir eksperimen Host 2 tetap perlu diperiksa dari JSONL milik Host 2. Tidak ada inferensi tambahan yang dipicu untuk pemeriksaan ini. Bukti lengkap tersimpan lokal di `private/recovery/20261121T135741Z/` dan di-ignore Git.

## Review integrasi katalog Host 1 — 21 November 2026

Referensi `origin/main` telah diambil dan checkout di-fast-forward ke `a8ba75d`, yang memuat merge PR #2 (adaptasi katalog) dan PR #3 (client replay), tanpa membuat commit baru. Audit offline katalog mendapati 30 ID unik dan 10 kelas masing-masing tiga kasus; pemeriksaan target interface/peer/ASN terhadap `design-plan.json` tanpa error. Seluruh 30 baris hasil tersimpan pada `data/rca-sim/` memiliki observable dan recovered true; ini hasil lab tiruan, bukan eksekusi ulang di Host 1.

`scripts/check_lab.py --lab rca` yang baru dijalankan read-only pada lab asli dan lulus, dengan enam router dan ping service 30/30 arah. Snapshot lokal: `private/integration-review/baseline/rca_20261121T140839Z.json`; audit: `private/integration-review/catalog-audit.json`. Health API replay loopback dan LAN tetap ok. Tidak ada fault, restart layanan atau inferensi tambahan. Temuan cleanup/exit code runner dan kesiapan SSH dicatat pada draf API live; tidak ada klaim bahwa pilot diagnosis/perbaikan siap.

## Schema dan mock API live revisi 2 — 21 November 2026

Modul `host1/live_api/` memiliki schema terpisah, satu bundle contoh sintetis dan mock server loopback; tidak mengubah schema agen atau kode API replay. Sebanyak 19 tes baru lulus: validasi Pydantic dan JSON Schema Draft 2020-12, kecocokan artefak ekspor, bindings evidence/proyeksi patch/hash linter, auth, konkurensi/idempotensi, busy, respons POST hilang, client berhenti polling, deadline server, restart/reload indeks, interrupted, expiry dan evidence berubah. Tes tidak mengimplementasikan linter/allowlist dan tidak membuktikan freshness telemetry atau kemampuan agen live.

Bersama 16 tes regresi API replay dengan transport model simulasi, total 35 tes lulus. Server tes memakai port OS sementara dan output sementara; tidak memanggil model asli atau router. Smoke CLI terpisah juga lulus: startup port sementara, health/capabilities, POST/poll/evidence, lalu SIGINT menghentikan hanya mock. Sebelum/sesudah smoke, metadata container/PID/start/restart serta hash konfigurasi FRR sama; proses API/Ollama tetap sama dan health replay tetap ok. Bukti smoke lokal di `private/live-mock/last-smoke.json`, di-ignore. Mock tidak ditinggalkan berjalan dan listener LAN baru belum dibuka.

## Review runner/linter/evaluator dan label diagnosis live

Review memakai runner origin/fayyaz/host1-faults pada 4536517 serta linter/evaluator cc38e2b yang sudah di-merge ke main af9840f. Runner direview dari salinan privat, tidak digabung. Kontrak live sekarang memiliki root_cause_class dan root_cause_router wajib pada WireResponse; keduanya null saat abstain, dan assessment ditolak jika tidak konsisten. Guard gate/evidence tetap dijalankan melalui validate_live_pair tanpa mengubah model aktif agent_contract.Response maupun API replay.

Sebanyak 43 tes lulus (27 live/mock, termasuk delapan tes diagnosis baru; 16 regresi replay dengan model simulasi). Suite kelompok juga lulus 259 tes pada dependency review terisolasi: pandas 2.3.3, matplotlib 3.10.9 dan pytest 9.2.0 di Python 3.10; ini bukan reproduksi penuh pin requirements.txt root. Tidak ada perubahan dependency environment layanan aktif. Total kedua suite 302 tes lulus.

Smoke runner terbaru ke mock dengan no-lab menghasilkan sembilan baris dari tiga varian dan tiga ID jadwal; semuanya sintetis, lint passed, applied=false dan recovered=null. Resume tidak membuat job/hasil ganda. Subprocess dan fungsi router diganti guard yang menggagalkan tes bila dipanggil. ID fault hanya metadata runner, tidak dikirim ke API. Hasil ini menguji interoperabilitas format, bukan akurasi agen atau pemulihan fault tersebut.

Reproduksi stub mengonfirmasi temuan terbuka: runner dapat revert setelah error transport dengan penyelesaian job tidak diketahui, CLI belum menolak mock tanpa no-lab, serta evaluator mengabaikan envelope assessment/status lint/simulation dan dapat mengasumsikan applied dari lint. Linter belum mengekspor POLICY_VERSION. Detail dan prioritas ada pada LIVE-API-DRAFT.md; tes yang lulus tidak menutup kekurangan integrasi yang belum diuji suite kelompok. Tidak ada perbaikan kode branch teman yang digabung atau diterapkan pada review ini.

Smoke CLI mock dengan kontrak baru juga lulus dan dihentikan. Pemeriksaan read-only sebelum/sesudah menunjukkan state/PID/restart/hash konfigurasi router dan proses API/Ollama tetap sama; health replay tetap ok. Bukti privat pada private/branch-review-4536517/ dan private/live-mock/last-smoke.json, seluruhnya di-ignore.

## Retrieval dan quality gate

Retriever memakai 739 chunk dari enam sumber FRR/OpenConfig yang dipin, embedding MiniLM ONNX lokal dan Chroma. Hybrid dense/BM25 pernah lulus 6/6 acceptance terarah. Gate memeriksa provenance dan dukungan klaim pertanyaan yang dikenali; bukan semantic entailment umum atau izin mengeksekusi perintah.

Evaluasi 12 query baru pada implementasi awal menemukan reference anchor pada 6/8 pertanyaan yang diperkirakan didukung dan kesepakatan keputusan gate 8/12. Dua distraktor dapat lolos ketika intent eksplisit `network_context` diberikan. Gate v2 memperketat dukungan pertanyaan. Evaluasi berikutnya membekukan delapan query sebelum pengujian, mendapat 6/8 sesuai ekspektasi, lalu memperbaiki compound request dan ekspansi YANG. Regresi setelah perbaikan 10/10 merupakan hasil pengembangan pada kasus yang telah terbuka.

Relevansi bahasa Indonesia, pertanyaan bebas dengan banyak rincian dan cakupan remedy MTU tetap terbatas. Chunk YANG adalah schema, bukan CLI FRR. Definisi MTU tidak otomatis membuktikan penghitungan header atau konfigurasi knob pada jaringan live. Pertanyaan yang tidak dikenali tetap abstain.

## Ollama dan reasoning

Ollama lokal 0.40.16 memakai llama3.1:8b Q4_K_M. Profil `num_gpu=20`, konteks 2048 pernah menghasilkan cold wall sekitar 68 detik dan warm JSON sekitar 0,65 detik. Percobaan berbagi GPU dengan aplikasi lain; ini bukan perbandingan model terkontrol atau target pemulihan jaringan di bawah 10 detik.

Adapter dokumentasi membatasi token, memilih kutipan dan memvalidasi kontrak. Replay RCA hybrid pada L12/L35 menghasilkan dua kasus administratif DOWN dari Ollama dan empat state sehat dari controller. Percobaan LLM-only sebelumnya hanya 1/6 dan tidak disembunyikan. Hasil hybrid tidak boleh dilaporkan sebagai akurasi LLM 6/6.

## Temporal dan penjelasan

| Evaluasi historis | Hasil dan interpretasi |
|---|---|
| Temporal awal | 6/6 pengembangan; 10/12 variasi diterima dan dua abstain karena ekstraksi endpoint salah |
| Pemetaan endpoint | Grouped 5/8; bound 8/8 dan empat kontrol baseline/pemulihan lulus |
| Negatif/parsial | 26/26: 20 guard abstain sebelum model, enam history parsial menghasilkan fase undetermined dari LLM |
| Penjelasan | Delapan laporan, 60 klaim dengan binding evidence/citation; 41 eksekusi tes lulus |

Bound mengikat identitas endpoint/citation melalui controller, sedangkan model menyalin observasi dan memilih fase. Nilai salah ditolak. Empat request per kasus bukan bukti model memetakan identitas arbitrer. Penjelasan memisahkan kondisi lokal, gejala dan riwayat; penyebab awal tetap `not_established`. Penilaian ini bukan skor manusia independen atas narasi bebas LLM.

## MTU sintetis

Replay akhir 28/28 lulus, dengan 35 tes; variasi nilai/urutan berikutnya 36/36 lulus, 104 binding citation dan sembilan tes harness. Dua percobaan MTU awal masing-masing 24/28 dipertahankan sebagai hasil yang gagal pada beberapa fase.

Fixture mengubah nilai MTU pada salinan snapshot/graf secara konsisten. Peer dan physical state tetap sehat. Controller menghitung EQUAL/UNEQUAL, model memilih fase, dan renderer controller membentuk penjelasan. Dua puluh delapan panggilan pada suite variasi hanya memuat empat pola input LLM unik setelah normalisasi. Hasil ini bukan kemampuan aritmetika LLM, 28 gangguan independen, dampak routing terbukti atau repair MTU live.

## API replay

API memuat 16 skenario historis/sintetis. Enam belas tes HTTP dengan model simulasi lulus. Pengujian historis terpisah dengan Ollama asli lulus 9/9, dengan 20 request model dan 49 pengambilan evidence bercitation. Waktu cold/warm tidak diisolasi dan bukan benchmark latensi.

API hanya menerima `scenario_id`, memeriksa hash dan citation, mengizinkan satu inferensi aktif dan tidak mengembalikan patch yang dapat dieksekusi. Health endpoint tidak membuktikan kesiapan model. Belum ada collector live, executor, antrean, pembatalan, autostart atau reload indeks run setelah restart. Akses lintas Host 2 belum dibuktikan oleh hasil ini.

## Migrasi dan pemeriksaan repositori

Pada 21 November 2026, 141 tes gate/replay/penjelasan/API, 22 tes adapter dan 16 tes graf/collector lulus: total 179 eksekusi tes, termasuk tes turunan yang diulang. Tujuh file embedding dan enam blob Ollama cocok dengan hash tersimpan. Satu query lokal menghasilkan lima hit dari storage baru; ini memverifikasi akses database/model, bukan relevansi. Parser PowerShell, tiga skrip shell, enam startup config dan enam path bind log lolos pemeriksaan.

Ringkasan JSON migrasi tetap disimpan lokal dan di-ignore karena hasilnya sudah dirangkum di atas. Fixture yang dibagikan didaftarkan dalam [manifest](../../data/host1/fixtures-manifest.json). Seluruh jalur yang dijelaskan masih menggunakan patch kosong dan eksekusi dinonaktifkan. Smoke test MTU end-to-end, benchmark kelompok dan validasi perbaikan jaringan tetap pekerjaan berikutnya.

Penyaringan awal mempertahankan 1.161 fixture dan lulus 163 tes Linux serta 16 tes graf/collector Windows ketika akses ke data yang di-ignore diblokir. Jumlah itu membuktikan kecukupan fixture, bukan bahwa seluruh file diperlukan.

Peninjauan berikutnya mencatat file yang benar-benar dibaca tes dan seluruh 16 skenario replay dengan model simulasi. Daftar dirampingkan menjadi 148 file (133 JSON), sekitar 12,67 MiB; sebelumnya 1.161 file (1.014 JSON), sekitar 25,39 MiB. Pada tahap penyaringan tersebut snapshot belum disanitasi; tahap privasi di bawah menghasilkan salinan publik dengan hash baru. Konfigurasi, schema kontrak, inventaris topologi, manifest sumber dan katalog replay tetap dibagikan; laporan build serta artefak eksperimen yang tidak dibaca di-ignore.

Verifikasi setelah perampingan: 163 tes Linux lulus dari salinan terisolasi yang secara fisik hanya berisi kandidat file Git, tanpa arsip data lokal; 16 tes graf/collector Windows juga lulus dengan data di luar daftar diblokir. Semua 16 skenario replay berhasil memakai transport model simulasi, dengan pemeriksaan fase, patch kosong dan pengambilan ulang setiap evidence. Gabungan akses baca kedua suite dan semua skenario tepat mencakup 148 fixture yang dipertahankan. Tidak ada inferensi model nyata atau pengujian jaringan live pada pemeriksaan ini.

Konsolidasi lanjutan menggabungkan tiga panduan ke TEMPORAL.md serta mengabaikan dua skrip khusus eksperimen lama dan latihan Alpine awal. Dengan tambahan peta fungsi file, seluruh konten repositori yang terlihat Git berkurang dari 315 menjadi 310 file. Verifikasi diulang setelah perubahan tersebut: 163 tes Linux dan 16 tes Windows lulus, serta semua 16 replay simulasi tetap sesuai ekspektasi. Daftar fixture tidak dikurangi lagi karena semua 148 file masih dibaca pada cakupan ini.

## Sanitasi sebelum staging akhir

Audit isi file menemukan path absolut mesin pada field JSON, termasuk JSON yang dienkode sebagai string di dalam kontrak, serta identitas login pada template/panduan. Salinan asli disimpan di private/privacy-originals/. Salinan publik mengganti path mesin dengan path relatif, 44 MAC terekam dan 33 IPv6 link-local dengan nilai sintetis yang konsisten. Sebanyak 82 file input/registri berubah; seluruh referensi hash serta ID snapshot terkait dihitung ulang. Metadata sanitasi dicatat pada manifest fixture; ukuran fixture publik menjadi sekitar 12,34 MiB.

Pengujian setelah sanitasi lulus 163 tes Linux pada salinan terisolasi dan 16 tes graf/collector Windows. Semua 16 skenario replay simulasi tetap memenuhi fase, kontrak tanpa patch dan pengambilan ulang evidence. Sanitasi tidak mengubah MTU, state routing IPv4 atau label kasus, dan bukan pengujian jaringan live baru. Nama login/path pribadi pada kode serta template diganti dengan aturan portabel dan placeholder.

## Client JSONL Host 2

Laporan pengelola Host 2 yang diteruskan pengguna: sesi replay lintas LAN selesai 16/16, exit code 0, semua HTTP 201, 14 success dan dua abstain yang diharapkan (`mtu.l12.invalid-mtu`, `mtu.l35.invalid-mtu`), dengan 88 evidence lolos pemeriksaan client. Median POST client 5,4 detik (min 0,9; max 11,5), median temporal-bound 9,5 detik dan mtu-observation 3,2 detik; median waktu agen server 5,1 detik, total fetch evidence 5,8 detik, sesi sekitar 98 detik. Angka ini merupakan laporan Host 2, belum dihitung ulang dari JSONL di Host 1. File resmi berada di `data/host2/replay-20261121T140113730Z-09e2e3d2.jsonl` pada Host 2, 16 baris, tetap privat/di-ignore.

Runtime sesi tersebut adalah PowerShell 7 di lingkungan Linux pada laptop Host 2; jalur jaringan tetap lintas host melalui LAN. Pernyataan client tidak berjalan di Windows PowerShell 5.1 pada lingkungan mereka belum disertai error untuk menentukan penyebab, dan tidak menggantikan hasil tes simulasi 5.1 di Host 1. Dua sesi sebelumnya terputus karena batas durasi perintah alat pengelola, menghasilkan total 16 request replay tambahan menurut laporannya. File terputus dipisahkan dari sesi resmi; jangan mencampur request tersebut dalam statistik sesi resmi. Model sudah dipakai sebelum sesi resmi, sehingga hasil latensi tersebut bukan pengukuran cold start yang terisolasi.

`laptop/replay.ps1` diuji dengan delapan tes HTTP simulasi pada Windows PowerShell 5.1 dan delapan tes yang sama pada PowerShell 7. Cakupannya: tepat 16 POST berurutan, abstain valid, UTF-8 tanpa BOM, timing dan respons lengkap pada JSONL, larangan overwrite, error/busy tanpa retry, timeout dengan penyelesaian server tidak diketahui, katalog tidak valid, JSON rusak serta evidence/URL yang tidak sesuai.

Smoke terpisah memakai client PowerShell tersebut terhadap API Host 1 dengan Ollama asli. Seluruh 16 baris selesai: 14 hasil hypothesis dan dua abstain MTU tidak valid, dengan 88 fragmen evidence diambil ulang dan cocok. File JSONL dapat dibaca saat sesi masih berlangsung. Pengujian ini dijalankan dari Windows Host 1 melalui localhost, sehingga tidak menetapkan latensi client pada mesin Host 2. Keluaran lengkap berada lokal di data/host2/ dan di-ignore Git. Ini tetap replay evidence historis/sintetis, tanpa fault atau perbaikan router.
