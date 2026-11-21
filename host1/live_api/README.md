# Schema dan mock API live — revisi 2

Modul ini menyiapkan integrasi client Host 2 dengan **data sintetis saja**. Tidak mengambil telemetry, membaca katalog fault, memanggil Ollama, menjalankan linter nyata atau mengubah router. Kontrak aktif replay dan schema internal agen tetap utuh. Rancangan: [LIVE-API-DRAFT.md](../../docs/host1/LIVE-API-DRAFT.md).

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
| `requirements.txt` | Dependency minimum modul dan tes schema. |

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
