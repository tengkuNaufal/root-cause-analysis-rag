# Schema, mock dan agen API live — revisi 2

Status operasional terbaru: [kesiapan Host 1](../../docs/host1/READINESS.md). Smoke F01 nyata sudah berhasil pada tiga varian, sedangkan target pemulihan <10 detik belum lulus. Bagian riwayat pra-smoke di bawah bukan batas scope terbaru.

Mock pada modul ini menyiapkan integrasi client Host 2 dengan **data sintetis saja**; jalur agen/live dan executor lokal dijelaskan pada bagian akhir. Tidak mengambil telemetry, membaca katalog fault, memanggil Ollama, menjalankan linter nyata atau mengubah router. Kontrak aktif replay dan schema internal agen tetap utuh. Rancangan: [LIVE-API-DRAFT.md](../../docs/host1/LIVE-API-DRAFT.md).

## File yang dipakai bersama

| File | Fungsi |
|---|---|
| `models.py` | Sumber schema wire dan validator lint/ID/citation/proyeksi command. |
| `schema.json` | JSON Schema Draft 2020-12, definisi bersama di `$defs`. |
| `examples.json` | Satu bundle contoh request, pending, hypothesis, abstain, failed, interrupted, evidence, lint input/output dan error; seluruhnya sintetis. |
| `examples.py` | Generator deterministik kedua artefak, sekaligus pembuat fixture mock. |
| `mock.py` | Server HTTP loopback dengan job async, autentikasi, admission dan SQLite lokal. |
| `test_mock.py` | Tes kontrak, schema, konkurensi, persistence dan HTTP pada port sementara. |
| `test_diagnosis.py` | Tes label diagnosis eksplisit, pemetaan assessment, patch kosong/target berbeda, guard live dan kompatibilitas linter. |
| `requirements.txt` | Dependency minimum modul dan tes schema; retrieval memakai environment Host 1. |
| `capture.py`, `settings.py` | Capture terbaru, proyeksi privat dan perbedaan konfigurasi baseline/runtime. |
| `agent.py`, `server.py` | Diagnosis/proposal tiga varian dan listener loopback live. |
| `executor.py` | Dry-run/apply lokal berotorisasi, source/precondition/policy guard dan verifikasi. |
| `test_agent.py`, `test_executor.py`, `test_retrieval_host1.py` | Tes integrasi/model/router tiruan dan set retrieval Host 1. |
| `evaluate_retrieval.py` | Pembuat/evaluator set retrieval Host 1 offline; tidak dipakai runtime agen. |

Untuk validator selain Python, gunakan `$ref` ke definisi yang sesuai, misalnya `schema.json#/$defs/DiagnosisRequest`, `Job`, `EvidencePayload`, `LintInput`, `LintOutput`, `ErrorResponse`, `Health` atau `Capabilities`. `x-payload-schemas` mencatat entry point. **Root bundle saja bukan schema satu payload**; pilih `$ref` tersebut. JSON Schema memeriksa bentuk; aturan lint digest, citation, proyeksi patch, waktu kalender dan keterikatan antarfield tetap membutuhkan validator aplikasi pada `models.py`. Ini bukan command linter/allowlist.

`Job` berupa union berdasarkan `state`; pending tidak memuat hasil terminal. Semua job mock memiliki `mode: live` untuk menguji envelope rencana, tetapi selalu **`simulation: true`**. Health/capabilities memakai `mode: mock_live`. Capabilities menyatakan `real_variants_available: []` serta collector/model/linter/executor tidak siap; `variants` hanya pilihan varian yang disimulasikan. Semua varian mengembalikan fixture, bukan perbandingan kemampuan model.

`result` memakai `WireResponse`, dengan dua field wajib `root_cause_class` dan `root_cause_router`. Hypothesis memakai kelas katalog/unknown dan router r1…r6 atau null bila belum diketahui; abstain mewajibkan keduanya null. `assessment.router` harus sama dengan router diagnosis, dan `assessment.root_cause` sama dengan kelas diagnosis (null abstain dipetakan ke unknown). Validator menolak mismatch. Lokasi diagnosis tetap ada saat patch kosong dan boleh berbeda dari router target patch. Gunakan `validate_live_pair` untuk memvalidasi pasangan input/output live; kontrak replay lama tetap strict tanpa kedua field tambahan.

Entry schema output eksplisit: `schema.json#/$defs/WireResponse`. Request tetap `live.v1-draft2`; client harus mengambil schema output terbaru. Gunakan output directory mock baru untuk revisi ini: arsip job mock lama tanpa kedua field tidak dimigrasikan otomatis agar label tidak diisi dengan dugaan dari command.

## Menjalankan di Host 1 atau laptop Host 2

Python 3.10+ dan dependency pada requirements diperlukan. Gunakan environment lokal yang tersedia, atau siapkan venv sendiri di folder privat dengan requirements minimum. Dari root repo, contoh WSL Host 1:

```bash
# Isi token lokal tanpa echo; jangan masukkan token ke file repo atau log.
read -rsp 'Mock token: ' LIVE_API_TOKEN
export LIVE_API_TOKEN
private/.venv-retriever-wsl/bin/python scripts/host1.py -m live_api.mock \
  --output private/live-mock/session-1 --port 8766 --outcome hypothesis --delay 2
```

Pada laptop Host 2 dengan environment sendiri, ganti interpreter dengan Python venv tersebut. Mock hanya bind `127.0.0.1`, sehingga client dijalankan pada mesin yang sama; endpoint LAN Host 1 belum dibuka. Port 8765 dan 11434 ditolak oleh CLI; `--port 0` memilih port sementara. Startup mencetak port terpilih tanpa token. Ctrl+C menghentikan mock; tidak menghentikan API replay.

Contoh panggilan pada terminal lain yang memiliki token environment sama:

```bash
curl -sS http://127.0.0.1:8766/health \
  -H "Authorization: Bearer $LIVE_API_TOKEN"
curl -sS http://127.0.0.1:8766/v1/capabilities \
  -H "Authorization: Bearer $LIVE_API_TOKEN"
```

Kirim field pada `examples.json.request` sebagai body JSON, bukan seluruh bundle. UUID contoh hanya untuk satu contoh; runner membuat UUID acak per baris jadwal dan menyimpannya sebelum POST. Request tetap enam field wajib: versi kontrak, request_id, lab, variant, symptom_detected_at_utc dan execution_allowed=false. Jangan kirim fault_id/ground_truth/prompt/commands. Authorization diperlukan juga untuk health, polling dan evidence.

Endpoint:

| Method/path | Pemakaian |
|---|---|
| GET `/health`, GET `/v1/capabilities` | Keaktifan dan kemampuan mock, tanpa model probe. |
| POST `/v1/diagnoses` | HTTP 202 + Location untuk job baru/pending; HTTP 200 untuk duplikat yang sudah terminal. |
| GET `/v1/diagnoses/by-request/{request_id}` | Rekonsiliasi setelah respons POST hilang. |
| GET `/v1/diagnoses/{job_id}` | HTTP 200, baca state sampai completed/failed/interrupted. |
| GET `/v1/diagnoses/{job_id}/evidence/{evidence_id}` | Fragmen sintetis yang hash sumbernya diperiksa kembali. |

HTTP 202 bukan hasil diagnosis. Polling 1 detik, timeout client 180 detik sesuai draf. Timeout client tidak membatalkan job: jangan POST ulang atau menyentuh lab sampai job terminal/diresolusikan. **Jangan inject fault nyata untuk menguji mock**, walaupun health mock menyatakan ready/active=false.

## Menguji kondisi client

Outcome dan delay dikonfigurasi operator saat startup, bukan field request. Hentikan instance lalu gunakan direktori sesi baru untuk kasus berikutnya (atau direktori sama untuk menguji restart/resume):

| Opsi | Kondisi yang disimulasikan |
|---|---|
| `--outcome hypothesis` | Hasil sintetis dengan proposal IP; tidak pernah diterapkan. |
| `--outcome abstain` | Completed dengan abstain yang sah, unknown/null dan patch kosong. |
| `--outcome failed` / `interrupted` | Terminal operasional, tanpa result. |
| `--delay 190` | Job melewati budget client 180 detik; temukan hasil lewat request ID tanpa POST baru. |
| `--delay 2 --deadline 0.1` | Deadline server menghasilkan failed/mock_deadline. |
| `--not-ready` | POST 503 live_not_ready. |
| `--variants zero_shot` | Varian lain mendapat 422 unsupported_variant. |

POST UUID lain saat job aktif mendapat 503 agent_busy dengan Retry-After; duplikat UUID+payload mendapat job yang sama. Payload berbeda dengan UUID sama mendapat 409. Kegagalan admission tidak membuat job. Transport JSON/shape/flag/key duplikat yang salah mendapat 400; ukuran di atas 4096 byte mendapat 413, media type salah 415. Tidak ada endpoint apply, fault atau upload.

SQLite menyimpan request, hasil dan source sintetis sebelum acceptance. Satu output directory hanya boleh dimiliki satu proses mock. Restart mempertahankan indeks completed dan mengubah job nonterminal menjadi interrupted; tidak menjalankan ulang job. Graceful shutdown juga menandai pekerjaan yang belum selesai interrupted. HTTP/job expiry tujuh hari mempertahankan record ID sebagai tombstone, lalu GET/POST duplikat mengembalikan 410; mock tidak menghapus byte record otomatis. Gunakan sesi baru untuk pengujian baru. DB/lock berada di `private/`, token hanya di environment. Jangan menambahkan output ke Git.

Hash evidence adalah hash canonical JSON sumber sintetis (UTF-8, sort keys, separators koma/titik dua tanpa spasi, Unicode tidak di-escape, tanpa newline), bukan hash string content yang dipresentasikan. Fixture mock mengirim keseluruhan sumber pada locator `/`, jadi client dapat merekonstruksi hash melalui canonicalization tersebut. Endpoint live nyata kelak boleh hanya mengirim fragmen: jangan mengasumsikan hash fragmen sama dengan hash file sumber. Lint input/output contoh adalah fixture format, bukan keputusan linter yang dipercaya.

## Pengujian dan regenerasi

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m live_api.examples
private/.venv-retriever-wsl/bin/python scripts/host1.py -m unittest live_api.test_mock live_api.test_diagnosis -v
```

Tes memakai TemporaryDirectory, server 127.0.0.1 pada port OS sementara dan token sintetis. Tidak ada port replay yang di-bind atau request inferensi nyata. Tes regresi replay terpisah dapat memakai `-m unittest live_api.test_mock reasoning_agent.test_api -v`; transport model pada suite replay juga simulasi. Hasil ini tidak membuktikan TTL/skew collector, tiga varian agen nyata, linter, repair atau benchmark live.

## Agen live dan executor lokal

Implementasi berjalan melalui `capture.py` → `settings.py` → `agent.py` → `server.py`. API diagnosis tetap read-only terhadap router: model boleh mengusulkan perintah, tetapi tidak dapat menjalankannya. Eksekusi bukan endpoint API: benchmark memakai executor runner, sedangkan `executor.py` adalah alternatif lokal berotorisasi hash. Jangan menjalankan keduanya untuk diagnosis yang sama; semua CLI perubahan lab berbagi lock. Katalog/ground truth/revert tidak pernah dibaca runtime agen atau executor.

### Evidence dan tiga varian

Capture mengambil telemetry dan `show running-config` keenam router, membandingkan semantic settings dengan konfigurasi baseline sumber, lalu membekukan proyeksi JSON dengan hash/locator. Material autentikasi direduksi menjadi mode/presence; raw MAC, IPv6 link-local dan path komputer tidak diekspor. Source asli tetap privat. Snapshot lengkap wajib berhasil, durasi/skew capture maksimal 5 detik dan umur konservatif sebelum model maksimal 15 detik. Semua durasi memakai monotonic Host 1. Perubahan source hash, partial/stale capture dan referensi asing ditolak.

- `zero_shot`: observasi terbaru dan expected settings baseline, tanpa dokumentasi/graf.
- `text_rag`: evidence yang sama ditambah retrieval hybrid dari `host1/knowledge/`, dengan citation diverifikasi terhadap manifest FRR yang dipin. Query berasal dari nama setting yang diamati, bukan label fault. Sumber primer MTU/BGP yang sudah dipin diekspansi hanya pada konteks live; tipe RFC/source C tetap dipertahankan dan Chroma replay tidak di-rebuild.
- `graph_rag`: konteks text RAG ditambah neighborhood NetworkX dari snapshot yang sama, termasuk observasi protokol berarah.

Cakupan konfigurasi mengikuti sepuluh kelas katalog: MTU, admin-down, hello/area/auth OSPF, shutdown/remote-AS BGP, filter inbound, missing network dan alamat IPv4 salah. Controller memeriksa dukungan label/router dari setting yang benar-benar berubah atau physical observation yang bercitation; bukan mengambil label dari ID fault. Filter inbound harus terikat pada policy inbound, bukan sembarang route-map. Diagnosis tetap hipotesis; controller support check bukan skor akurasi LLM. Belum ada pembuktian diagnosis sepuluh kelas lewat fault live.

Model lokal yang dipakai commissioning adalah llama3.1:8b dengan digest yang sudah dipin. Semua varian memakai profil sama: konteks 8192, output 768, seed 42, temperature 0 dan num_gpu 20; batas prompt memakai upper bound byte UTF-8 dan cadangan 128. Profil setup/replay lama tidak diubah. Pilihan ini belum studi komparatif model atau model final benchmark kelompok. Agen commissioning juga menganalisis baseline sehat dan wajib abstain bila tidak ada dukungan fault. Proposal dibatasi delapan command blocks, divalidasi kontrak/citation dan linter; flag eksekusi model selalu false.

### Layanan

API hanya bind `127.0.0.1:8766`, memakai `LIVE_API_TOKEN` dari environment dan output di `private/`. Startup memeriksa baseline dengan `verify-runtime.py` bila router sudah berjalan; tidak menyalakan/redeploy container secara otomatis. Identitas container atau inventory berubah membuat readiness batal. Token diagnosis tidak memberi akses apply.

```bash
export PYTHONPATH="$PWD/private/live-agent-deps${PYTHONPATH:+:$PYTHONPATH}"
private/.venv-retriever-wsl/bin/python scripts/host1.py -m live_api.server \
  --output private/live-agent/session-baru --port 8766 --exclusive-model-session
```

`--exclusive-model-session` adalah reservasi operator untuk Ollama. Listener replay 8765 yang terdeteksi tetap memblokir admission live meskipun idle; layanan tidak menghentikan replay. Jalankan satu layanan live saja. Marker `backend-completion-unknown` menahan readiness setelah timeout/crash sampai operator memastikan backend selesai. Tidak ada inferensi retry otomatis. Mock dan live harus memakai output directory berbeda.

Pada sesi penyelesaian 28 November, lab serta Ollama dipulihkan sesuai instruksi pengguna. Live server yang berjalan dicatat di `private/live-agent/latest.txt`; direktori itu menyimpan `process.json`, log dan `token.txt` privat. Root/runner dapat membaca token ke environment secara lokal, tanpa menyalinnya ke repo atau log:

```bash
LIVE_SESSION=$(cat private/live-agent/latest.txt)
export LIVE_API_TOKEN=$(cat "$LIVE_SESSION/token.txt")
```

Runner lokal memakai WSL NetworkLab. User runner sudah mendapat akses grup Docker dengan persetujuan eksplisit; tidak melonggarkan mode socket. SSH/Tailscale Windows juga sudah dipasang melalui skrip setup yang disetujui; login Tailscale ditunda pengguna. Tidak perlu membuka API live ke LAN untuk runner yang berjalan di Host 1.

### Executor dan verifikasi

Executor menerima artefak `response.json` non-synthetic yang selesai. Default adalah dry-run: schema, proposal, lint dan hash diperiksa tanpa mengirim command. Contoh:

```bash
python scripts/host1.py -m live_api.executor private/live-agent/session/jobs/JOB/response.json \
  --output private/live-execution/preview-JOB
```

Apply adalah langkah lokal terpisah, dengan hash dari hasil preview:

```bash
python scripts/host1.py -m live_api.executor private/live-agent/session/jobs/JOB/response.json \
  --output private/live-execution/apply-JOB --apply --expected-diagnosis-sha256 SHA_DARI_PREVIEW
```

Jangan memakai placeholder JOB/SHA secara literal. Apply memeriksa source/hash manifest, baseline config fingerprint, ulang capture precondition yang stabil dan policy source digest sebelum dispatch. `POLICY_VERSION` dan hash source linter dicatat; policy yang berubah setelah di-import ditolak. Shared lab lock dan ledger privat mencegah dua executor atau pengulangan job yang completion-nya tidak diketahui. Semua perintah memakai argv `docker exec` langsung, tidak disambung ke shell.

Verifier memeriksa interface/MTU/address, OSPF/BGP, routes, forwarding dan ping service 30 arah, lalu semantic config drift. Ada batas tunggu konvergensi 60 detik; ini bukan target waktu pemulihan. Hasil command, partial failure, application unknown saat timeout, dan verifikasi tersimpan dalam receipt. Tidak ada catalog revert tersembunyi. Executor gagal/partial walaupun jaringan tampak sehat tidak otomatis dihitung sukses agen oleh evaluator. Runner default read-only; --execute mengaktifkan executor runner dan mencatat apply/verifikasi/fallback terpisah. Executor standalone memakai receipt sendiri. Satu run hanya memakai salah satu jalur.

### Retrieval dan status validasi

`evaluate_retrieval.py` adalah alat offline terpisah. Set `data/retrieval_host1_testset.yaml` berisi 60 pertanyaan ID/EN untuk 30 lokasi fault dengan hash katalog. Hanya question dikirim ke retriever Host 1; kelas/relevance adalah metadata evaluator. Baseline full chunks: dense 43/60 dan hybrid 46/60. Verified expansion setelah koreksi locator RFC dan potongan FRR adalah 52/60 hit@5. Angka 58/60 sebelum koreksi locator tidak mewakili versi saat ini. Ekspansi dikembangkan setelah hasil awal terlihat; ini hasil pengembangan, bukan held-out evaluation. Skor ekspansi awal berbasis excerpt 46/60 tetap disimpan, tetapi tidak dibandingkan langsung dengan baseline full chunks. Prompt tetap memakai excerpt berbudget dan skor ini tidak mengukur kualitas excerpt tersebut. Angka tersebut bukan penilaian manusia independen atau akurasi diagnosis; retrieval belum sempurna.

Tiga varian telah memakai capture baseline terbaru dan Ollama asli: seluruhnya completed/abstain, tanpa patch/apply karena baseline sehat. Jalur HTTP graph RAG dan empat evidence juga berhasil; verifier baseline nyata lulus. Unit tests mencakup sepuluh kelas melalui konfigurasi/router/model tiruan, serta executor dispatch/precondition/partial failure/idempotency. Baseline historis tersebut bukan bukti repair; smoke F01 nyata terbaru terpisah sudah berhasil pada ketiga varian, seperti dijelaskan di READINESS.md.

Batas kerja tahap pra-smoke sebelumnya adalah tidak melakukan injection/apply. Pada tahap kesiapan berikutnya, smoke nyata sudah dilakukan; pilot dan benchmark resmi tetap belum dijalankan. Semua itu merupakan tahap sesudah komponen yang disiapkan di sini. Model comparison, daftar fault final dan kemungkinan varian regex tetap keputusan kelompok sebelum benchmark.

### Workflow satu diagnosis dan perbaikan

`workflow.py` menyediakan sambungan otomatis API diagnosis → evidence check → executor lokal → verifier. Tidak pernah inject fault atau membaca katalog. Default preview; `--apply` adalah otorisasi operator untuk satu workflow, bukan flag dari model/token API. Request ID disimpan dengan fsync sebelum POST; timeout/404 lookup tidak menyebabkan POST ulang atau apply. Output yang sama bisa dipakai untuk resume. Contoh setelah token dimuat dari sesi privat:

```bash
LIVE_SESSION=$(cat private/live-agent/latest.txt)
python scripts/host1.py -m live_api.workflow --session "$LIVE_SESSION/jobs" \
  --output private/live-workflow/nama-run --variant graph_rag
```

Tambahkan `--apply` hanya pada langkah eksekusi yang memang diotorisasi. Pada penyelesaian pra-smoke ini workflow nyata hanya dijalankan tanpa apply pada baseline sehat. Fault injection, smoke MTU dan benchmark tidak dijalankan. Laporan executor (termasuk policy/hash, precondition dan verification) tersedia pada `workflow.json`; ledger yang completion-nya tidak diketahui harus diperiksa operator, bukan diulang otomatis.


### Draft model ringkas dan layanan persisten

Model sekarang mengeluarkan class/router/confidence/explanation/evidence_ids/commands saja. Adapter memproyeksikannya tanpa mengarang label atau argumen ke claims/proposed_patch dan assessment kontrak yang sama. Abstain dengan class null/unknown dan confidence null/0 diproyeksikan menjadi confidence null; proposal/label/router yang bertentangan tetap ditolak. Raw model decision disimpan privat. Untuk penyimpangan physical tanpa perubahan setting, decoder membatasi tool ke ip karena kernel MTU/admin bukan perintah vtysh build ini. Keputusan diagnosis dan seluruh argumen tetap berasal dari model. Policy host1-policy-v2 juga menolak MTU via vtysh; tidak menormalisasi command yang salah menjadi command benar.

Gunakan `bash host1/live_api/manage.sh status`, `start-model` atau `start-api` ketika belum ada listener. Launcher tmux memakai proses API langsung agar signal dan metadata PID benar. SIGINT/SIGTERM memicu graceful shutdown; jangan stop saat job aktif. `scripts/start-benchmark.sh` menyediakan runner detached yang tidak bergantung pada terminal SSH, dengan output wajib di private/ atau data/host2/. Lihat READINESS.md untuk resume dan pemakaian executor tunggal.


### Optimasi transport dan capture

[Putaran optimasi 30 menit](../../docs/host1/AGENT-OPTIMIZATION.md) menambahkan transport array berposisi tetap hanya untuk penyimpangan fisik tanpa perubahan setting. Konfigurasi tetap memakai format bernama yang sudah diuji. Array didekode ketat dan diproyeksikan ke wire contract yang sama; semua citation, label/router, lint dan flags otorisasi tetap diperiksa. ID evidence pada grammar dibatasi ke ID input yang tersedia. Capture konfigurasi berjalan paralel dengan hasil tetap diurutkan menurut inventory. Tidak menyimpan cache evidence jaringan atau mengurangi source pemeriksaan. Lihat laporan untuk hasil smoke, kegagalan kandidat yang ditolak, dan batas kualitas/latency yang diuji.
