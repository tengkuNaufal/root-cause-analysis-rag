# API replay agent Host 1

Layanan sinkron ini memakai agent temporal `bound` dan profil observasi MTU yang sudah ada. Hanya menerima scenario_id terdaftar, menjalankan ulang analisis terhadap evidence historis, dan menyimpan artefak baru. Tidak menerima path bebas, upload, prompt bebas, mode live, model pilihan klien atau perintah perbaikan.

Implementasi menggunakan HTTP server bawaan Python; tidak menambah dependency. Bind tahap ini tetap **127.0.0.1:8765** pada NetworkLab, untuk pengujian lokal. Tidak mengubah firewall, Ollama bind atau setup Host 2.

## Menjalankan

Pada terminal NetworkLab di root proyek, gunakan folder output baru dan port yang tersedia:

```bash
private/.venv-retriever-wsl/bin/python -u scripts/host1.py -m reasoning_agent.api \
  --output data/host1/agent-api/nama-sesi-baru --port 8765
```

Jangan menjalankan instance kedua pada port yang sama. Mode foreground dapat dihentikan dengan Ctrl+C. Dalam sesi setup, server sudah dijalankan dan log/PID disimpan di folder hasil milestone. Pertahankan terminal WSL interaktif saat lab dan layanan aktif.

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/v1/scenarios
curl -s -X POST http://127.0.0.1:8765/v1/replays \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"mtu.l35.fault"}'
```

Dari PowerShell Host 1:

```powershell
$answer = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/v1/replays' `
  -Method Post -ContentType 'application/json' `
  -Body '{"scenario_id":"mtu.l35.fault"}' -TimeoutSec 1200
$answer.phase
$answer.timing
Invoke-RestMethod -Uri ('http://127.0.0.1:8765' + $answer.evidence[0].url)
```

## Endpoint

| Method/path | Isi |
| --- | --- |
| GET /health | Status listener HTTP dan active; model_readiness=not_probed |
| GET /v1/scenarios | ID/profil/deskripsi/synthetic untuk 16 skenario |
| POST /v1/replays | Body tepat satu field scenario_id; hasil selesai dengan HTTP 201 |
| GET /v1/runs/{run_id} | Hasil lengkap yang selesai pada proses layanan ini |
| GET /v1/runs/{run_id}/evidence/{id} | Evidence terpilih beserta locator dan hash sumber |

Contoh ID temporal: temporal.l12.baseline, temporal.l12.fault, temporal.l12.recovered dan padanannya untuk l35. ID MTU: mtu.l12.baseline/fault/recovered/partial/invalid-mtu dan padanannya untuk l35. Daftar lengkap berada di replay-scenarios.json; input serta hash dipilih operator, bukan klien.

HTTP 201 dapat berisi status hypothesis **atau abstain yang valid**. Abstain karena evidence kurang adalah hasil domain, bukan gangguan HTTP. Phase hanya diisi jika hasil diterima kontrak; model salah yang ditahan tidak ditampilkan sebagai fase valid.

Respons memuat run_id, scenario_id, profile, synthetic, mode=replay, phase, kontrak agent asli pada result, evidence terpilih, citation per klaim dan URL evidence, origins serta jumlah request model. diagnosis_allowed/execution_allowed selalu false dan patch kosong. Hasil disimpan pada folder sesi/{run_id}/response.json; artefak inferensi ada di agent/.

Citation URL bersifat relatif agar klien dapat memakai base URL layanan. Payload evidence memuat source_id berbasis sha256, kind, locator, content dan sha256 **file sumber**. Hash tersebut bukan hash fragmen content; server memeriksa ulang file asal sebelum melayani evidence. Ini antarmuka fragmen terpilih, bukan browser filesystem atau ekspor seluruh file sumber. Path filesystem Host 1 tidak menjadi field evidence publik.

## Waktu, konkurensi dan error

timing.agent_seconds mengukur pemanggilan agent termasuk source gate/inferensi/kontrak; total_seconds mencakup verifikasi katalog/input dan penyusunan response evidence. Total tidak mencakup seluruh serialisasi/network transfer. Client harus mengukur wall time sendiri untuk eksperimen lintas host; smoke menyimpan client_seconds terpisah. Cold start dapat lebih lambat daripada request warm; angka ini bukan benchmark target diagnosis/remediation di bawah 10 detik.

Satu inferensi aktif per layanan. Request kedua mendapat 503 agent_busy dengan Retry-After, sementara GET tetap dapat dilayani. API belum memakai job queue, pembatalan atau hasil streaming. Timeout klien harus memperhitungkan inferensi beberapa tahap. Putusnya koneksi klien tidak membatalkan inferensi yang sudah berjalan.

| HTTP | Alasan |
| --- | --- |
| 400 | JSON/shape/field tidak sah, key duplikat atau encoding request tidak didukung |
| 404 | Skenario, run, evidence atau route tidak ditemukan |
| 405 | Method tidak tersedia |
| 409 | Katalog/input terdaftar atau sumber evidence berubah |
| 413 / 415 | Body lebih dari 4096 byte / bukan application/json |
| 502 / 503 | Identitas model tidak sesuai / model tidak tersedia atau agent sibuk |
| 500 | Kontrak eksekusi, validasi layanan atau internal error |

Riwayat URL run yang dapat diakses berada di memori proses saat ini. File hasil tetap tersimpan setelah proses berhenti, tetapi proses baru tidak otomatis memuat indeks run lama. /health hanya memeriksa layanan HTTP; keberhasilan inferensi dibuktikan melalui replay, bukan status health saja.

## Batas evidence

Temporal memakai snapshot historis link fokus, bukan kondisi jaringan sekarang. MTU memakai fixture sintetis dan membandingkan nilai saja; mismatch tidak membuktikan dampak routing, penyebab awal atau keberhasilan repair. Origins membedakan fase model dari ekstraksi/perbandingan/renderer controller. Semua gate, pin model, budget dan kontrak agent tetap berlaku.

Pengujian kontrak HTTP dengan model simulasi: `python scripts/host1.py -m unittest reasoning_agent.test_api`. Smoke HTTP dengan Ollama asli: `python host1/tools/smoke_agent_api.py data/host1/agent-api/folder-smoke-baru`. Lihat [hasil milestone](../../docs/host1/VALIDATION.md) untuk bukti aktual dan batas verifikasi lintas host.
