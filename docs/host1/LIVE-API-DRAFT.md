# Draf kontrak API live Host 1–Host 2

Status kontrak: **revisi 2 setelah masukan Host 2, 21 November 2026**. Implementasi live sudah aktif dan diuji smoke nyata pada 28 November; status operasional ada di [READINESS.md](READINESS.md). Catatan historis penyusunan draf berikut tidak menggantikan status implementasi terbaru. Kesepakatan arah Host 2 sudah diterima melalui pengguna; format linter belum dikonfirmasi pembuat linter. Perubahan dari revisi 1: `run_id` → `job_id`, `symptom_detected_at` → `symptom_detected_at_utc`, polling client 1 detik dengan timeout 180 detik, dan proyeksi command wire sederhana. Dasar kebutuhan adalah dokumen pembagian tugas kelompok dan komponen repo saat ini. Instruksi deployment/SSH dalam dokumen kelompok merupakan konteks rencana, bukan tindakan yang dijalankan saat menyusun draf ini. Kontrak aktif tetap [API replay](../../host1/reasoning_agent/API.md) dan [model agen](../../host1/agent_contract/models.py).

## Ruang lingkup dan pemisahan layanan

Pembaruan implementasi 28 November: jalur capture/settings/agent/server kini mencakup observasi konfigurasi sepuluh kelas dan proposal unvalidated pada tiga varian. Lab/Ollama dipulihkan atas instruksi lanjutan pengguna; commissioning baseline sehat dengan model nyata lulus. Executor/workflow lokal berotorisasi diintegrasikan, sedangkan API diagnosis tetap tanpa endpoint apply. Repair MTU nyata sudah berhasil pada tiga varian, regex lokal terintegrasi, dan baseline OSPF diperbarui atas izin pengguna. Pilot/benchmark resmi belum dijalankan; target waktu agen belum lulus. Rincian terkini ada pada README modul dan STATUS.md.

Schema dan [mock API lokal](../../host1/live_api/README.md) kini tersedia sesuai permintaan pengguna untuk menyiapkan client. Diagnosis live nyata sudah tersedia; mock tetap terpisah dan sintetis. Mock menambahkan field wajib `simulation: true` pada envelope job, health/capabilities `mode: mock_live`, serta header `X-Live-API-Simulation: true`. Bentuk schema aktif replay tetap tidak berubah. Format linter pada schema baru adalah draf untuk pengujian, belum konfirmasi policy Naufal.

Usulan tahap integrasi awal adalah diagnosis live read-only: Host 1 mengambil evidence sendiri, menjalankan varian yang diminta dan mengembalikan usulan perbaikan. Linter, executor dan verifikasi memiliki artefak terpisah. `execution_allowed` tetap `false`; lulus linter tidak mengaktifkan eksekusi.

Layanan live kelak memakai proses, output directory dan listener tersendiri, dengan port kandidat `8766`. Port itu belum dibuka. Endpoint replay pada `8765`, katalog, format respons dan client `laptop/replay.ps1` tetap menggunakan kontrak lama. Versi wire usulan live adalah `live.v1-draft2`; ini berbeda dari `schema_version: 1` milik kontrak internal agen. Perubahan draf tidak mengganti schema aktif.

Pemisahan proses saja tidak mengisolasi GPU/Ollama. Selama Host 2 masih memakai replay, jangan mengaktifkan inferensi live paralel. Implementasi mendatang perlu pengaturan sesi atau admission lock lintas layanan sebelum kedua layanan memakai model yang sama. Jika belum tersedia, readiness live harus `false` dengan alasan `replay_session_reserved`.

## Pemilik data dan alur satu percobaan

| Bagian | Pemilik dan tanggung jawab |
|---|---|
| Runner | Host 2 mengelola jadwal, injeksi, deteksi gejala, fallback revert dan resume. Menurut laporan pengelola Host 2, adaptasi katalog/cek Host 1 sudah di-merge melalui PR #2; perlu sinkronisasi dan review sebelum uji di lab asli, bukan implementasi ulang. |
| Evidence/controller | Host 1 membekukan snapshot, log window, inventory dan evidence manifest; memeriksa hash, kelengkapan dan freshness sebelum reasoning. |
| Agen/retriever | Host 1 menjalankan varian; jalur retrieval dikembangkan bersama pemilik retrieval. Semua varian memakai profil model yang dibekukan operator. |
| Linter | Pemilik linter memeriksa usulan perintah; hasil diikat ke command digest dan inventory yang sama. |
| Executor/verifier | Host 1, tahap berikutnya; belum memiliki endpoint eksekusi pada draf ini. |
| Evaluator | Menggabungkan keluaran diagnosis/linter/verifikasi dengan ground truth lokal milik runner. |

Urutan: baseline sehat → runner inject → runner mendeteksi gejala → POST diagnosis → polling hasil → ambil evidence → linter → eksekusi/verifikasi melalui integrasi masa depan → catat JSONL → fallback revert bila perlu → buktikan baseline sebelum percobaan selanjutnya. Pada integrasi read-only, runner tetap wajib revert; menerima hipotesis tidak berarti jaringan pulih.

Pembaruan koordinasi: PR #2 sudah diverifikasi pada riwayat Git dan checkout disinkronkan ke `origin/main` (`a8ba75d`) melalui fast-forward tanpa commit baru. `faults/host1.yaml` dan cek berbasis `design-plan.json` sudah tersedia; 30/30 baris hasil lab tiruan mencatat observable dan recovered. Pemeriksaan read-only `check_lab.py` lulus pada lab asli, tetapi fault belum dijalankan di sana. Usulan transport adalah SSH untuk orkestrasi runner/inject/revert dan API live untuk diagnosis; keduanya melayani fungsi berbeda. Ini belum keputusan kelompok atau izin mengganggu lab. API replay tidak dapat dipakai untuk injeksi maupun diagnosis live.

### Catatan review historis sebelum perbaikan runner PR 8

Catatan berikut merekam temuan pada commit lama; runner 235fd05/PR 8 sudah memperbaiki held/404/Ctrl+C, evaluator 40e5f97 kini diintegrasikan lokal, dan POLICY_VERSION sudah tersedia. Bukti review lama tetap disimpan.

Review ini memakai runner `origin/fayyaz/host1-faults` pada `4536517` dan linter/evaluator `origin/naufal/retrieval-linter-eval` pada `cc38e2b` (sudah ada di main `af9840f`). Branch runner belum digabung ke checkout kerja. Salinan review, reproduksi stub dan JSONL mock berada privat di `private/branch-review-4536517/`. Tidak ada inject/revert/read router dari runner selama review.

- **P1 — job tidak diketahui masih bisa memicu revert:** `scripts/bench.py:159–196` hanya memasang hold_fault pada timeout polling yang berhasil direkonsiliasi sampai batas tertentu. Bila submit/lookup/polling melempar exception transport, jalur exception umum masuk finally dengan hold_fault=false dan menjalankan revert. Reproduksi stub: dua submit gagal transport, lookup belum menemukan job, revert tetap dipanggil dan completion_unknown=false. Backend mungkin sudah menerima POST. Sejak POST mungkin terkirim, tahan lab sampai status terminal/rejeksi admission yang pasti; error koneksi bukan bukti job belum dibuat. KeyboardInterrupt juga harus mempertahankan aturan ini.
- **P1 — mock belum diwajibkan no-lab:** `scripts/bench.py:298–303` hanya mencetak catatan mode selain live, lalu menjalankan Bench. Reproduksi CLI dengan capabilities mock dan tanpa --no-lab tetap mencapai Bench.run. Tolak mode/simulation mock sebelum baseline/inject kecuali --no-lab eksplisit; jangan mengandalkan ready mock sebagai izin gangguan.
- **P1 — evaluator dapat mengarang eksekusi/keberhasilan agen:** `rca/evaluator.py:97,114` mengisi applied dari lint bila field hilang, dan cmd_ok hanya bergantung lint+recovered. Reproduksi payload sintetis tanpa applied menghasilkan applied=true/cmd_ok=true. Wajib gunakan applied eksplisit (missing berarti tidak diketahui), serta pisahkan recovery akibat revert katalog dari repair agen, termasuk ketika applied=false.
- **P2 — pembacaan envelope evaluator belum cocok:** `rca/evaluator.py:76–85,125` belum membaca diagnosis.assessment maupun diagnosis.result; status lint passed tidak dibaca sebagai passed, dan simulation/provenance.synthetic pada respons tidak dikenali. Reproduksi contoh mock menghasilkan pred_router/pred_class null, lint_passed=false, synthetic=false meskipun payload memiliki diagnosis sintetis valid. Baca label eksplisit dari diagnosis.result atau assessment yang konsisten; jangan memakai patch[0].router. Verifikasi katalog melalui catalog_sha256 sebelum join ground truth. Evidence yang tersedia untuk model berasal dari provenance.model_evidence_ids, bukan otomatis seluruh manifest.
- **P2 — evidence check belum menjadi penghenti pipeline:** `scripts/bench.py:179–182` menyimpan problems tetapi tetap menjalankan lint dan mempertahankan status completed. Tandai kegagalan integritas sebagai error client dan jangan lanjutkan pipeline perbaikan. Validasi juga binding request_id/job_id, schema/version dan execution flag pada respons.

Linter mendukung bentuk internal, steps dan bentuk wire tanpa perlu mengubah katalog. Seluruh 259 tes kelompok lulus, termasuk 30 revert dan negative controls; belum ada konstanta POLICY_VERSION pada branch yang direview, sehingga runner mencatat null. Schema LintOutput adalah target envelope controller, bukan output langsung rca.linter: adapter perlu memetakan passed/violations dan menambahkan binding hash/versi, tidak mengarang versi policy.

Smoke integrasi sembilan baris dengan runner terbaru dan mock schema baru lulus pada --no-lab; resume tidak menambah job/hasil, seluruh applied=false dan recovered=null. Subprocess dan fungsi router dipasang guard yang menggagalkan pengujian bila dipanggil. Ini membuktikan alur mock normal tetap kompatibel, bukan bahwa temuan jalur error sudah diperbaiki atau pilot lab asli siap. Dependency review dipasang hanya di private/integration-review-deps; Python 3.10 memakai pandas 2.3.3/matplotlib 3.10.9/pytest 9.2.0, bukan reproduksi environment pin penuh requirements.txt root. Environment layanan aktif tidak diubah.

Host 2 tidak mengirim `fault_id`, label kelas, router yang disalahkan, langkah inject/revert, expected symptom dari katalog, ground truth, path file, evidence unggahan, prompt atau perintah ke endpoint diagnosis. ID korelasi harus acak/opaque, tidak menyandikan kelas atau lokasi fault. Diagnosis memakai pertanyaan tetap dari controller. Fakta gejala berasal dari observasi Host 1. Ground truth dan identitas jadwal hanya disimpan pada JSONL runner/evaluator.

## Endpoint yang diusulkan

Semua path di bawah hanya milik listener live mendatang. JSON UTF-8, `Content-Type: application/json`, field tambahan/key duplikat/non-finite number ditolak. Semua respons memakai `Cache-Control: no-store`.

| Method/path | Respons |
|---|---|
| GET `/health` | Liveness, `active` (true sejak admission sampai backend selesai), dan readiness; tidak memanggil model. `active: false` saja bukan jaminan lab sudah direservasi. |
| GET `/v1/capabilities` | Versi kontrak, lab, varian yang benar-benar tersedia, profile ID/digest model, inventory hash, limit body, timeout/retensi, freshness policy dan readiness per komponen. Tidak menjalankan inferensi. |
| POST `/v1/diagnoses` | Validasi/admission, simpan job secara durable, lalu `202` dengan `job_id`, `state: accepted`, `Location` dan `Retry-After: 1`. |
| GET `/v1/diagnoses/by-request/{request_id}` | Cari job dengan ID opaque untuk pemulihan setelah timeout POST; `404` jika belum tersimpan. Route ini diprioritaskan dari route run ID. |
| GET `/v1/diagnoses/{job_id}` | `200`, envelope job pending atau hasil terminal yang tersimpan. |
| GET `/v1/diagnoses/{job_id}/evidence/{evidence_id}` | Fragmen evidence yang sudah dibekukan dan diizinkan untuk integrasi; URL relatif same-origin. |

Tidak ada endpoint fault injection, upload, shell, pilihan model bebas atau apply pada tahap ini. Bind awal saat implementasi kelak adalah loopback; akses LAN live perlu konfigurasi tersendiri. Izin akses replay sebelumnya tidak diperlakukan sebagai izin membuka listener baru. Usulan Host 2: LAN/Tailscale, firewall hanya untuk laptop dan bearer token dari environment. Pilihan implementasi yang diusulkan: Tailscale dengan pembatasan peer atau HTTPS/tunnel berautentikasi untuk LAN, ditambah bearer token environment; HTTP LAN biasa dengan bearer saja belum disepakati karena token dapat terlihat pada transport. Nama environment usulan `LIVE_API_TOKEN`; token wajib pada seluruh endpoint live dan tidak dicatat di log. Jangan membuka listener baru sebelum transport final dipilih. Kredensial dan alamat mesin tetap di konfigurasi privat, bukan contoh repo.

## Request diagnosis

Semua enam field berikut wajib, tanpa default tersembunyi. UUID harus valid dan dibatasi 36 karakter. Batas body usulan 4096 byte. Timestamp RFC3339 dengan zona waktu; timestamp tanpa zona ditolak.

```json
{
  "contract_version": "live.v1-draft2",
  "request_id": "00000000-0000-4000-8000-000000000001",
  "lab": "rca",
  "variant": "graph_rag",
  "symptom_detected_at_utc": "2026-11-21T00:00:00Z",
  "execution_allowed": false
}
```

`variant` adalah `zero_shot`, `text_rag` atau `graph_rag`, hanya diterima bila tercantum tersedia di capabilities. Nama mengikuti `scripts/fault_runner.py`; belum membuktikan ketiganya sudah dibangun. Varian yang belum ada ditolak, bukan diam-diam dialihkan ke replay/hybrid. Timestamp deteksi adalah laporan runner untuk audit, bukan fakta freshness atau input model. Server menyimpan waktu penerimaan sendiri dan tidak mengklaim selisih clock lintas host sebagai latensi terukur.

Semua varian menerima observasi telemetry/log dengan pemilihan evidence mentah yang sama. `zero_shot` tanpa dokumentasi/graf; `text_rag` menambah dokumentasi; `graph_rag` menambah subgraf dan dokumentasi. Konfigurasi model, budget, versi retriever/prompt dan aturan seleksi dicatat server. Gate harus spesifik varian: ketiadaan dokumentasi pada zero-shot tidak otomatis dianggap kegagalan retrieval. Gate keselamatan, keaslian evidence dan validasi citation berlaku sama.

Satu request mengambil evidence baru setelah admission. Runner memeriksa readiness dan `active` sebelum inject, lalu baseline/route equality; jadwal ditunda dan dicatat bila gagal. Pengecekan health memiliki race, sehingga bukan mekanisme lock. Draf mengasumsikan satu runner pemilik sesi lab; admission server atomik menolak job kedua dan tidak mengizinkan penulis lab lain. Dukungan multi-runner memerlukan lease/reservasi tersendiri sebelum inject. Hanya satu job live aktif dan satu pemilik lab boleh mengubah konfigurasi. Runner menahan fault sampai capture/diagnosis selesai; tidak melakukan inject/revert pada capture aktif. Sebelum benchmark, kelompok harus memilih desain pasangan: reset/reinject untuk tiap varian atau snapshot beku yang sama. Draf ini memakai reset/reinject; replay snapshot yang sama kelak harus diberi mode berbeda, bukan diklaim live.

## State, idempotensi dan timeout

State: `accepted → collecting → reasoning → completed`; dari state nonterminal dapat berakhir `failed` atau `interrupted`. Tidak ada antrean. `completed` berisi hasil domain `hypothesis` atau `abstain`, bukan bukti perbaikan. `failed` berarti kegagalan operasional; `interrupted` berarti proses berhenti sebelum hasil terminal tersimpan.

`request_id` adalah idempotency key, dicatat atomik sebelum `202`. Perbandingan memakai payload tervalidasi yang dikanonisasi, bukan byte JSON mentah. ID+payload sama mengembalikan job semula (`202` bila pending, `200` bila terminal), tanpa pengambilan evidence/inferensi ulang. ID sama dengan payload berbeda menghasilkan `409 request_id_conflict`. Pengujian konkurensi wajib membuktikan dua POST serentak tidak membuat dua job. Admission busy tidak membuat job.

Usulan retensi job, evidence dan idempotency record: minimal tujuh hari. Capabilities memberi retensi efektif; jangan evict job aktif. Simpan indeks yang dapat dipulihkan setelah restart; job nonterminal saat crash menjadi `interrupted`, tidak dilanjutkan atau dieksekusi otomatis. Catatan/tombstone ID yang kedaluwarsa mengembalikan `410`, bukan membuat ulang job tanpa pemberitahuan.

Timeout transport tidak membatalkan job. Sesuai usulan Host 2, polling tiap 1 detik dan budget client 180 detik per job, diukur sejak sebelum POST (termasuk penerimaan HTTP). Host 2 menyimpan `status: timeout` dan `completion_unknown: true` ketika budget habis, tanpa POST ulang, revert atau inject berikutnya. Pemulihan lewat GET berdasarkan `request_id`/`job_id`; `active: false` tanpa hasil terminal yang dapat direkonsiliasi belum cukup untuk melanjutkan. Setelah job terminal atau operator memastikan backend berhenti, baru fallback revert dan baseline diverifikasi. Deadline server tetap usulan 600 detik dan diiklankan capabilities, terpisah dari timeout client 180 detik. Server tidak melepas slot selama inferensi backend masih berjalan, meskipun deadline lewat. Pembatalan backend belum dijanjikan; tidak ada retry inferensi tersembunyi. Ketidaksamaan dua budget ini sengaja dicatat: timeout client bukan pembatalan dan bukan bukti job gagal di server.

## Envelope dan pemetaan hasil

Envelope pending: `contract_version`, `request_id`, `job_id`, `mode: live`, `lab`, `variant`, `state`, `received_at`, `updated_at`, `execution_allowed: false`. Field `result`, `assessment`, `evidence`, `timing`, `provenance` dan `error` hanya hadir pada state terminal sesuai aturan di bawah. Semua timestamp UTC RFC3339. `job_id` opaque dari server; tidak boleh menjadi path yang disuplai klien.

Pada `completed`, `result` adalah `live_api.models.WireResponse`: kontrak dasar agen ditambah field wajib `root_cause_class` dan `root_cause_router`. `validate_live_pair` memvalidasi field live lalu menjalankan guard `agent_contract.validate_pair` pada proyeksi dasar tanpa kedua field tambahan. Model Response replay versi 1 tetap strict dan tidak berubah. Input internal dibuat Host 1 dari evidence/controller, dengan `mode: live`, ID request sama dan gate yang diverifikasi. `execution_allowed` selalu false di kedua lapisan. Schema aktif tidak diubah hanya demi draf ini.

| Field hasil terminal | Bentuk dan aturan |
|---|---|
| `result` | WireResponse live dengan label kelas/router eksplisit; `proposed_patch` tetap usulan `unvalidated`. |
| `result.root_cause_class` | Wajib hadir: salah satu 10 kelas katalog atau unknown pada hypothesis; null pada abstain. |
| `result.root_cause_router` | Wajib hadir: r1…r6 atau null jika lokasi belum cukup didukung; wajib null pada abstain. Tidak diturunkan dari tujuan command. |
| `assessment` | `{router, root_cause, confidence, evidence_ids, commands, explanation}` untuk runner/evaluator. |
| `assessment.router` | Harus sama dengan result.root_cause_router, terlepas dari router tujuan patch. |
| `assessment.root_cause` | Harus sama dengan result.root_cause_class; null dari abstain dipetakan menjadi `unknown`. Ketidaksesuaian ditolak validator. |
| `assessment.confidence` | Sama dengan `result.confidence`, angka finite 0…1 atau null; bukan skor terkalibrasi. |
| `assessment.evidence_ids` | Union ID pada claims dan patch; semuanya harus ada pada manifest. |
| `assessment.commands` | Proyeksi deterministik patch menjadi `{router, interpreter: "vtysh" atau "ip", args: [...]}`; bukan hasil parsing narasi. Aturan di bagian linter. |
| `assessment.explanation` | Penjelasan ringkas berdasarkan claims bercitation; tidak menambahkan fakta tanpa evidence. |
| `evidence` | Array manifest fragmen: `id`, `kind`, `source_id`, `source_sha256`, `locator`, `url`, `capture_started_at`, `capture_completed_at`. |
| `provenance` | ID/hash inventory dan capture, versi agent/gate/prompt/retriever, profil model+digest+options, varian aktual, daftar evidence yang benar-benar masuk model dan alasan truncation/abstain. |
| `timing` | Durasi monotonic nonnegatif: `collection_seconds`, `retrieval_seconds`, `reasoning_seconds`, `validation_seconds`, `total_seconds`; nol jika tahap dilewati, bukan estimasi tersembunyi. |

Dua field eksplisit sudah tersedia pada kontrak live, schema ekspor dan contoh mock. Keduanya bersumber dari output diagnosis yang tervalidasi, bukan lookup fault ID, parsing narasi atau patch pertama. Diagnosis tetap dapat dipertahankan saat patch kosong atau perbaikan ditujukan ke router seberang link. Model live nyata kelak wajib menghasilkan field tersebut; mock sekarang mengisinya dari fixture sintetis yang ditandai jelas. Request tetap live.v1-draft2 agar client runner yang direview kompatibel; pembaruan output ini wajib diambil bersama schema terbaru. Arsip mock lama yang belum mempunyai kedua field tidak otomatis dimigrasikan: gunakan output directory baru, pertahankan arsip lama.

Pada abstain: hipotesis/confidence internal serta kedua field label result null, `assessment.root_cause: unknown`; commands/patch kosong; `missing_evidence` menjelaskan kekurangan; explanation menerangkan abstention. Pada `failed/interrupted`, hasil domain tidak diisi; `error` memuat `code`, pesan aman dan `retryable`. Jangan menyamarkan timeout model, schema error atau kegagalan storage sebagai abstain yang sah. Confidence tinggi bukan izin eksekusi.

Vocabulary mengikuti katalog: `mtu_mismatch`, `link_down`, `ospf_hello_mismatch`, `ospf_area_mismatch`, `ospf_auth_mismatch`, `bgp_neighbor_shutdown`, `bgp_wrong_remote_as`, `bgp_inbound_filter`, `bgp_missing_network`, `wrong_ip_address`, serta `unknown`. Router null/kelas unknown dihitung tidak tepat pada akurasi, dan dilaporkan terpisah sebagai unknown/incomplete; tingkat abstain dihitung dari `result.status: abstain`, bukan menyamakan kegagalan operasional atau semua hipotesis parsial dengan abstain. Penyebut/exclusion operasional perlu dikonfirmasi evaluator.

## Evidence dan freshness

Host 1 menyimpan source bytes secara immutable sebelum membuat ID/hash. SHA-256 sumber adalah hash file utuh, bukan hash fragmen JSON yang dikirim. GET evidence mengembalikan `{id, kind, source_id, source_sha256, locator, content}` sesuai manifest dan melakukan pemeriksaan sumber lagi. Klien memeriksa identitas/hash/locator serta memakai parser locator yang sama; bila perlu membuktikan hash sumber sendiri, diperlukan ekspor sumber tersanitasi yang terpisah dan disepakati. Memiliki hash saja tidak membuktikan byte sumber bagi klien yang hanya menerima fragmen.

Path absolut host, konfigurasi akses, token, private key dan direktori `private/` tidak diekspor. URL hanya relatif same-origin di namespace run; tolak traversal dan ID tak dikenal. Evidence asli live disimpan lokal di output yang di-ignore. Jika disanitasi, buat artefak turunan dan hash baru; jangan memodifikasi sumber beku yang sudah bercitation.

Usulan kebijakan awal: seluruh sumber network wajib applicable berhasil, usia capture terakhir maksimal 15 detik saat mulai reasoning, dan skew antarsumber maksimal 5 detik. Usia dihitung dari selesainya capture sumber sampai mulai reasoning menggunakan monotonic Host 1; skew memakai window pengamatan sumber di Host 1. Capture wajib dimulai setelah request diterima. `symptom_detected_at_utc` Host 2 hanya untuk korelasi, tidak dikurangkan dari waktu Host 1 untuk menilai freshness. Sinkronisasi NTP membantu audit lintas host, bukan syarat penghitungan durasi ini. Partial/stale/inconsistent evidence menghasilkan abstain sebelum model dengan alasan spesifik, tanpa proposal. Timestamp dokumen historis tidak mengikuti TTL telemetry. Snapshot tetap tidak atomik; log hanya dipilih dari window capture yang dibatasi dan tercatat. Hasil harus menampilkan usia evidence saat jawaban selesai; jawaban diagnosis dapat menjadi historis saat inferensi lama. Sebelum eksekusi kelak, ambil ulang state dan tolak proposal yang precondition-nya berubah.

Jika tidak ada satu pun evidence sah untuk memenuhi Request internal yang mewajibkan evidence nonkosong, job menjadi `failed` dengan `evidence_unavailable`; jangan membuat evidence fiktif agar lolos schema. Abstain sebelum model memakai setidaknya satu observasi sah dan gate yang menyatakan kekurangan dukungan.

## Sambungan linter dan eksekusi berikutnya

Format wire usulan Host 2 yang menunggu konfirmasi Naufal: setiap command tepat `{router, interpreter, args}`, interpreter `vtysh` atau `ip`. Untuk vtysh, args adalah daftar baris command sesuai urutan (contoh di bawah). Untuk ip, args adalah argv setelah executable `ip`, tanpa nama binary. Router tetap r1…r6. String shell, pemisah shell dan interpreter lain tidak diteruskan.

```json
{
  "router": "r1",
  "interpreter": "ip",
  "args": ["link", "set", "eth1", "mtu", "1500"]
}
```

```json
{
  "router": "r2",
  "interpreter": "vtysh",
  "args": ["configure terminal", "interface eth1", "ip ospf hello-interval 1"]
}
```

Contoh di atas adalah fixture kontrak, bukan perintah yang dieksekusi. Adapter dari kontrak internal: `vtysh_commands` → `vtysh`, arguments disalin ke args; `linux_argv` hanya dapat diproyeksikan bila arguments[0] tepat `ip`, lalu elemen pertama dibuang. Target/evidence/rationale tetap ada pada patch internal yang utuh. Jika patch tidak dapat diproyeksikan atau tidak terikat evidence, job gagal validasi; jangan membuang command diam-diam. Perubahan format wire tidak mengganti model agen aktif.

Masukan linter: `contract_version`, `job_id`, `inventory_sha256`, `commands` hasil proyeksi dan `commands_sha256`. Digest dihitung atas UTF-8 JSON array commands dengan keys diurutkan, separator koma/titik-dua tanpa spasi, Unicode tanpa ASCII escaping, tanpa newline; urutan command/argument dipertahankan. Jangan menyambung arguments ke shell.

Keluaran linter terpisah: `job_id`, `commands_sha256`, `inventory_sha256`, `linter_version`, `policy_version`, `policy_sha256`, `status: passed|rejected|error`, `violations` dan `checked_at`. Violation memuat `command_index` (null untuk masalah global), `code`, `message`; passed memerlukan violations kosong dan semua command diperiksa. Patch kosong dicatat `not_requested` oleh runner dan tidak dianggap repair sukses. Status tersebut bukan hasil linter passed.

Executor mendatang harus memeriksa ulang hash, inventory, linter dipercaya, policy, freshness/precondition dan otorisasi lab. Hasil linter dari klien yang tidak dipercaya tidak boleh langsung menjadi izin. Respons model tidak bisa menyatakan lulus linter. Apply, rollback dan post-verification akan mendapat kontrak terpisah setelah pembahasan; tidak ada endpoint tersebut pada versi ini.

Tiga puluh revert pada katalog dapat menjadi kandidat positive fixtures linter setelah normalisasi format dan review policy, bukan otomatis dianggap aman. Tambahkan negative tests untuk router/interface asing, nilai di luar batas, shell injection, penghapusan konfigurasi luas dan command di luar allowlist. Digest dihitung atas bentuk wire hasil normalisasi yang persis diterima linter; setiap transformasi setelah lint membatalkan hasil. Persetujuan Naufal masih diperlukan untuk args vtysh, batas nilai, keluaran error serta versi policy.

## Error transport

Format: `{contract_version, request_id, error: {code, message, retryable}}`; `request_id` null bila body belum valid. Pesan tidak membocorkan traceback/path/token. GET job terminal failed tetap HTTP `200`; error berikut dipakai saat permintaan HTTP belum dapat diterima/dilayani.

| HTTP | Code/kondisi |
|---|---|
| 400 | `invalid_request`: JSON, duplicate key, UUID, timestamp, field tambahan, atau schema salah. |
| 401 / 403 | Autentikasi gagal / akses tidak diizinkan pada transport yang kelak dipilih. |
| 404 / 405 | Run/evidence/route tidak ditemukan / method tidak didukung. |
| 409 | `request_id_conflict` atau `lab_not_reserved`. |
| 410 | `run_expired`: record/evidence telah lewat masa retensi. |
| 413 / 415 | Body terlalu besar / media type selain JSON. |
| 422 | `unsupported_variant` atau versi kontrak tidak didukung. |
| 503 | `live_not_ready`, `agent_busy`, `replay_session_reserved`, storage tidak siap; beri Retry-After bila retry masuk akal. |
| 500 | Kegagalan internal sebelum job tercatat; client tetap lookup ID karena respons jaringan dapat hilang. |

Tidak ada fallback ke model, varian atau mode lain. HTTP accepted/completed tidak disamakan dengan diagnosis benar, linter passed atau repair berhasil.

## Catatan JSONL milik Host 2

Arsip utama ada di Host 2, satu baris hasil final per baris jadwal/attempt. Field yang diusulkan Host 2:

`plan_order`, `fault_id`, `variant`, `trial`, `catalog_sha256`, `request_id`, `job_id`, `timing`, `symptoms`, `diagnosis` (respons API utuh), `lint`, `execution` (null selama read-only), `verification`, `fallback_revert` (`performed` boolean + `reason`), `recovered`, `error`, `status`, `completion_unknown`. Lint mencakup status, violations, policy_version dan hash perintah. Versi kontrak/model/inventory dan varian aktual tersedia pada respons API yang diarsipkan; hasil evidence check ikut dicatat. Ground truth tidak masuk baris ini maupun request API: evaluator menggabungkan katalog melalui fault_id dan catalog_sha256. Token/header authorization tidak dicatat. File tetap di `data/host2/` yang di-ignore. Retensi tujuh hari pada server diterima Host 2 karena JSONL client menjadi arsip utama; evidence terpilih juga harus diambil sebelum expiry jika diperlukan untuk audit.

Request UUID acak dibuat sekali per baris jadwal (fault, varian, trial) dan disimpan durable sebelum POST; restart memakai UUID serta payload yang sama. Agar satu baris final per run tetap konsisten, simpan JSONL pending/journal terpisah dari hasil final. Timeout boleh difinalisasi sebagai timeout; rekonsiliasi hasil terlambat disimpan pada jurnal terpisah dengan request ID yang sama, bukan baris hasil run baru. Attempt ulang yang disengaja harus tercatat eksplisit setelah job lama terselesaikan dan baseline pulih. Sebelum melanjutkan jadwal, rekonsiliasi job belum diketahui dan verifikasi baseline serta equality tabel rute. Urutan memakai `data/benchmark_plan.csv` yang diacak seed, bukan mengelompokkan varian secara berurutan.

Titik waktu Host 2: `t_inject` (sebelum inject), `t_symptom` (saat observasi runner pertama mengonfirmasi gejala), `t_request` (sebelum POST), `t_diagnosis_done` (hasil terminal diterima), `t_lint_done`, `t_apply_done`, `t_verified`. Simpan UTC untuk korelasi dan elapsed monotonic dari origin percobaan untuk durasi. Deteksi = symptom − inject; diagnosis end-to-end = diagnosis_done − symptom; HTTP/job wait = diagnosis_done − request; pemulihan = verified − symptom. Server total_seconds tetap terpisah dan tidak mencakup seluruh transfer. Ukur fetch evidence terpisah; definisi diagnosis_done tidak menunggu fetch evidence/lint.

Resolusi deteksi dibatasi polling runner sekitar 2 detik ditambah durasi check; jangan mengklaim timestamp kejadian fault yang presisi. Monotonic dari proses/sesi sebelum dan setelah crash tidak boleh langsung dikurangkan: tandai durasi lintas restart tidak tersedia, atau gunakan checkpoint elapsed yang sah dan jelaskan bagian waktu yang tidak terukur.

Pada tahap read-only, apply_done null; verification/recovered dapat mencatat kondisi sesudah fallback revert katalog, dengan sumber pemulihan yang eksplisit. `agent_recovery_seconds` dan agent repair success tetap null/not_attempted; durasi fallback dicatat terpisah dan tidak dihitung keberhasilan agen. Cold/warm serta profil model dicatat. Error/abstain/timeout tidak otomatis berarti jaringan sudah pulih.

## Kriteria sebelum implementasi dianggap siap

1. Kelompok menyepakati field, vocabulary kelas, pilihan unknown/null, kebijakan TTL/skew, desain pasangan varian, autentikasi, retensi dan semantik timing.
2. Buat schema wire terpisah dari schema agen aktif, dengan contoh completed hypothesis, abstain, pending dan failed. Uji round-trip dan penolakan field ground truth/execution/path/extra serta referensi asing.
3. Uji idempotensi serentak, busy, timeout POST, restart/reload indeks, interrupted, expiry, traversal, evidence berubah dan model tidak sesuai, memakai model simulasi.
4. Uji pemetaan assessment dan linter digest yang deterministik; perubahan satu command membatalkan hasil lint. Tidak ada perintah yang dijalankan oleh tes kontrak.
5. Validasi capture live, stale/partial abstain, tiga varian yang benar-benar berbeda dan pin model. Capability tidak mengiklankan fitur yang belum tersedia.
6. Jadwalkan smoke live setelah sesi replay selesai; buktikan tidak ada kontensi inferensi yang tidak dikelola. Membuka listener LAN dan integrasi executor merupakan pekerjaan berikutnya.

Draf ini tidak mengubah `fault_runner.py`, katalog replika, schema agen, API replay, listener, firewall, proses model atau lab yang sedang berjalan. Penyusunan dokumen belum membuktikan kesiapan endpoint live ataupun keberhasilan smoke MTU.
