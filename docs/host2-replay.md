# Menjalankan 16 replay dari Host 2

Client `laptop/replay.ps1` menjalankan 16 skenario API secara berurutan dan menyimpan satu baris JSONL per percobaan. Host 2 cukup memakai Windows PowerShell 5.1 atau PowerShell 7; Python, Docker, WSL, dan Ollama tidak perlu dipasang di Host 2 untuk client ini.

Hasilnya adalah pengujian API dan evidence historis/sintetis. Client tidak menyuntikkan fault, memilih varian benchmark, menjalankan perbaikan router, atau menggantikan benchmark live 450 run.

## Persiapan

1. Ambil versi repositori yang memuat `laptop/replay.ps1` ini. Jika belum dibagikan lewat Git, file script dapat disalin langsung; tentukan `-OutputFile` ke folder hasil lokal. Tidak ada modul tambahan yang harus disalin untuk menjalankan client.
2. Minta alamat API dari operator Host 1. Ganti `<HOST1_IP>` pada contoh dengan IP yang diberikan; script tidak menyimpan IP pribadi di kode.
3. Pastikan Ollama, API, dan jalur LAN Host 1 tetap berjalan selama sesi. Jalur lintas host yang disiapkan pada sesi awal bersifat sementara dan dapat dibatasi ke IP Host 2 tertentu.
4. Koordinasikan sesi agar hanya satu client mengirim inferensi. Server melayani satu inferensi aktif; health dan pengambilan evidence tetap tersedia saat server sibuk.

Dari PowerShell Host 2, uji koneksi terlebih dahulu:

```powershell
Test-NetConnection <HOST1_IP> -Port 8765
Invoke-RestMethod 'http://<HOST1_IP>:8765/health'
```

Harapannya `TcpTestSucceeded: True`, `status: ok`, `mode: replay_only`, dan `active: False`. `model_readiness: not_probed` berarti health tidak menguji model. Keberhasilan inferensi baru terbukti melalui respons replay yang memanggil model.

## Menjalankan client

Jalankan dari root repositori:

```powershell
.\laptop\replay.ps1 -BaseUrl 'http://<HOST1_IP>:8765'
```

Client membuat file unik di `data/host2/replay-<waktu-UTC>-<ID>.jsonl`. Lokasi output ditampilkan di terminal. Folder `data/host2/` di-ignore Git karena berisi hasil run dan alamat koneksi lokal.

Untuk menentukan nama file dan timeout:

```powershell
.\laptop\replay.ps1 `
  -BaseUrl 'http://<HOST1_IP>:8765' `
  -OutputFile '.\data\host2\smoke-session-01.jsonl' `
  -TimeoutSec 600

$LASTEXITCODE
```

`TimeoutSec` berlaku untuk setiap request HTTP, bukan batas seluruh sesi, dan tidak mengubah timeout proxy/jaringan yang mungkin lebih singkat. File output harus baru; client menolak menimpa atau menambahkan hasil ke file lama. Jika memakai path custom di luar `data/host2/`, pastikan file tersebut juga di-ignore sebelum membagikan perubahan repo.

## Urutan yang dijalankan

Client membaca `/health`, mengambil `/v1/scenarios`, lalu memastikan ada tepat 16 ID unik dengan metadata replay yang sesuai. Urutan dipertahankan seperti katalog server; tidak diacak dan tidak dijalankan paralel.

Untuk setiap ID, client:

1. Mengirim tepat satu POST `/v1/replays` dengan body `scenario_id`.
2. Menyimpan respons lengkap dan memeriksa ID, profil, status, timing serta flag eksekusi.
3. Mengambil semua URL evidence dari respons dan mencocokkan ID, jenis, hash, locator, content dan URL-nya.
4. Memeriksa bahwa citation menunjuk evidence yang tersedia dan route yang sesuai.
5. Menulis satu baris JSONL UTF-8 tanpa BOM dan melakukan flush sebelum skenario berikutnya.

Client hanya mengambil route evidence relatif yang cocok dengan run/ID pada server yang sama. Redirect HTTP tidak diikuti. Hash evidence adalah hash file sumber; client memeriksa konsistensi response/GET, sedangkan validasi byte sumber dilakukan Host 1. Menghitung hash teks fragmen sebagai pengganti hash file sumber akan menghasilkan pemeriksaan yang keliru.

## Membaca JSONL

Setiap baris menggunakan `schema_version: host2-replay-client-1.0` dan memuat:

| Field | Arti |
|---|---|
| `client_session_id`, `sequence`, `scenario_count` | Identitas sesi, nomor percobaan dan target 16 skenario |
| `scenario_id`, `profile`, `synthetic` | Metadata kasus dari katalog, termasuk pemisahan MTU sintetis |
| `base_url`, `catalog_sha256` | Endpoint yang digunakan dan fingerprint respons katalog |
| `started_at_utc`, `finished_at_utc` | Waktu kalender UTC untuk pencocokan log |
| `first_request_in_session` | Menandai request pertama; **tidak membuktikan model cold** |
| `client_response_seconds` | Stopwatch POST sampai seluruh body respons diterima/didekode; tidak mencakup fetch evidence atau penulisan JSONL |
| `server_agent_seconds`, `server_total_seconds` | Timing yang dilaporkan server; bukan pengukuran jaringan Host 2 |
| `evidence_fetch_seconds` | Waktu pengambilan dan pencocokan evidence setelah POST |
| `client_total_seconds` | Waktu percobaan termasuk validasi/fetch evidence, sebelum penulisan JSONL |
| `http_status`, `outcome`, `client_checks_passed` | Hasil transport dan pemeriksaan client |
| `evidence_verified` | Jumlah fragmen evidence yang berhasil diambil ulang dan cocok |
| `response` | Respons API lengkap: run_id, kontrak agen, fase, model, evidence, citation, origins dan batas hasil |
| `raw_error_body`, `error` | Body HTTP error/JSON tidak valid dan kategori kegagalan; null pada hasil normal |
| `server_completion_unknown` | POST mengalami gangguan transport; server mungkin masih menjalankan inferensi |

Contoh membaca hasil:

```powershell
$rows = Get-Content '.\data\host2\smoke-session-01.jsonl' |
  ForEach-Object { $_ | ConvertFrom-Json }

$rows | Format-Table sequence, scenario_id, outcome, client_response_seconds, server_total_seconds
$rows.Count
$rows | Where-Object { -not $_.client_checks_passed }
```

Sesi lengkap memiliki 16 baris. `outcome: success` berarti pemeriksaan client lolos, bukan skor ketepatan diagnosis. `outcome: abstain` adalah hasil domain yang valid dan tetap dilanjutkan ke kasus berikutnya. Menilai akurasi fase/root cause memerlukan evaluator terpisah.

## Error, timeout dan penghentian

| Exit code | Arti |
|---|---|
| `0` | Seluruh 16 respons dan evidence lolos pemeriksaan; dapat mencakup abstain |
| `1` | Preflight, HTTP, JSON, kontrak, evidence atau penulisan file gagal |
| `2` | POST mengalami kegagalan transport/timeout; penyelesaian server belum diketahui |

Jika preflight gagal, belum ada POST atau file hasil yang dibuat. Jika kegagalan terjadi dalam satu percobaan, baris error disimpan bersama hasil sebelumnya lalu client berhenti. Tidak ada retry POST atau resume otomatis. Penghentian paksa saat menulis satu baris dapat menyisakan baris terakhir yang tidak lengkap; baris sebelumnya sudah di-flush.

- HTTP `503 agent_busy`: tunggu `/health` menunjukkan `active: False`; pastikan tidak ada client lain.
- HTTP `503 model_unavailable`: operator Host 1 perlu memeriksa Ollama.
- HTTP `409`: operator perlu memeriksa perubahan katalog atau hash sumber.
- Timeout/putus koneksi setelah POST: jangan langsung mengulang. Putusnya koneksi tidak membatalkan inferensi; periksa health dan log Host 1 terlebih dahulu.
- Fetch evidence gagal: respons POST sudah tersimpan pada `response`; periksa `error.stage` dan `response.evidence` sebelum memutuskan tindakan berikutnya.

Setelah penyebab diperbaiki, mulai sesi baru dengan file baru. Jangan menggabungkan run ulang sebagai trial yang sama tanpa penandaan pada analisis.

## Pencatatan waktu eksperimen

Client tidak melakukan warm-up atau menambah request inferensi di luar 16 kasus. Request pertama dapat cold atau warm bergantung pada penggunaan Host 1 sebelumnya. Catat kondisi model/beban GPU secara terpisah, dan gunakan file baru untuk setiap sesi pengulangan. Waktu client mencakup transfer jaringan serta overhead client; selisih terhadap timing server bukan pengukuran murni latensi jaringan.

Untuk pilot berikutnya, kirim JSONL ke penanggung jawab evaluasi melalui jalur berbagi yang disepakati kelompok. File ini adalah log client replay versi awal, belum kontrak hasil benchmark live. Data lokal hasil run tetap di-ignore.

## Pemeriksaan untuk pengembang

Tes memakai HTTP server simulasi localhost dan menjalankan file PowerShell yang sama:

```powershell
python -m unittest discover -s laptop/tests -p test_replay_client.py -v
```

Python hanya diperlukan untuk tes pengembang tersebut. Pengujian client tidak menyentuh router atau memanggil Ollama asli kecuali client secara terpisah diarahkan ke API Host 1 yang aktif.
