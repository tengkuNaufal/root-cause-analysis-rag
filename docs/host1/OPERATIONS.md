# Panduan operasional Host 1

Jalankan Host 1 dari root repositori `root-cause-analysis-rag`. Docker Engine dan Containerlab berada di distro WSL `NetworkLab`; konfigurasi lab replika dipisahkan dari lab Host 1.

## Struktur dan penyimpanan

| Lokasi | Isi |
|---|---|
| `host1/` | Modul Python, konfigurasi ingestion, requirements dan panduan CLI |
| `lab/host1/` | Topologi sumber, konfigurasi router dan pemeriksa lab |
| `docs/host1/` | Dokumentasi gabungan |
| `data/host1/` | Fixture replay yang dibagikan serta hasil eksperimen lokal yang disaring `.gitignore` |
| `private/runtime/ollama/` | Binary, library, arsip, bobot model dan home Ollama |
| `private/knowledge/` | Model embedding ONNX dan database Chroma |
| `private/.venv-retriever-wsl/`, `private/.venv-graph/` | Environment Linux dan Windows lokal |
| `private/.ai/`, `private/config/`, `private/docs-history/` | Konteks AI, snapshot lingkungan dan arsip dokumentasi lokal |

Hasil kerja dipindahkan dari `Tubes` pada 21 November 2026. Folder sumber sudah kosong. `private/.gitignore` berisi `*`, dan `.gitignore` root juga mengabaikan `/private/`. Private key, kredensial, model, database, cache dan environment tidak dibagikan melalui Git.

## Menjalankan modul

Contoh Linux berikut memakai environment lokal yang sudah tersedia. Clone baru harus menyiapkan environment dan model sesuai requirements serta [panduan retrieval](../../host1/knowledge/README.md) dan [Ollama](../../host1/ollama_host/README.md).

```bash
cd '/path/to/root-cause-analysis-rag'
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.api --help
mkdir -p data/host1/local-runs
private/.venv-retriever-wsl/bin/python scripts/host1.py -m knowledge.retriever query \
  --text 'OSPF database description packet MTU mismatch' --platform frr --top-k 5 \
  --output data/host1/local-runs/query.json
```

`scripts/host1.py` memakai interpreter pemanggil, mengatur direktori kerja ke root repo dan menambahkan `host1/` pada `PYTHONPATH`. Nama import Python tetap sama. Jalankan layanan model hanya ketika diperlukan dan pertahankan sesi WSL:

```bash
bash host1/ollama_host/serve.sh
```

Ollama memakai loopback `127.0.0.1:11434`. Panduan [API replay](../../host1/reasoning_agent/API.md) menjelaskan startup foreground pada `127.0.0.1:8765` dengan folder output baru. API tidak memiliki autostart, antrean, cancel atau pemuatan ulang indeks run setelah restart.

Di Windows, tes collector/graf memakai environment Windows:

```powershell
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m unittest discover -s host1/tests -v
```

## Pemulihan runtime setelah migrasi

Memindahkan file tidak mengubah bind mount absolut dalam metadata container Docker lama. Sebelum sesi live, periksa mount dan kondisi container proyek. Pemulihan terkontrol harus memakai `lab/host1/frr/topology.clab.yml` dan konfigurasi Vector di `host1/log_ingestion/`; jangan menganggap container lama sudah membaca file dari lokasi baru.

Topologi sumber menunjuk log router ke `data/host1/logs/raw/`. Skrip `host1/log_ingestion/manage.sh` memakai direktori log/checkpoint baru, dan `serve.sh` membaca storage Ollama di `private/`. Konfigurasi sumber telah diperiksa, tetapi tidak ada redeploy, fault injection atau perbaikan jaringan pada migrasi maupun konsolidasi dokumentasi.

Baseline live yang perlu diperiksa kembali: delapan link data, lima adjacency OSPF FULL, sembilan sesi BGP Established, service routes, ping 30 pasangan berarah dan ingestion log keenam router. Prosedur detail ada di [panduan lab](../../lab/host1/frr/README.md). Hindari prune global atau operasi pada container di luar proyek.

## Evidence dan file Git

Fixture publik merupakan turunan yang disanitasi: path mesin menjadi relatif, sedangkan MAC dan IPv6 link-local terekam menjadi sintetis. Evidence asli disimpan privat. Hash salinan publik beserta seluruh referensinya dihitung ulang tanpa mengubah state routing IPv4, MTU atau label kasus. `knowledge.evidence.local_path` tetap dapat merebase arsip Windows/Linux lama berdasarkan nama folder proyek, tanpa menanam lokasi komputer seseorang dalam kode. Perbandingan konteks tetap memeriksa hash, nilai observasi dan batas repositori. Hash kode pada laporan eksperimen lama menunjuk versi historis.

[Manifest fixture](../../data/host1/fixtures-manifest.json) menetapkan 148 file input yang dibaca oleh tes dan seluruh katalog replay, termasuk 133 JSON. Log instalasi, checkpoint Vector, dump debug, percobaan lama, laporan build/migrasi, keluaran tes sementara serta hasil run baru tetap lokal dan di-ignore. `host1/knowledge/build.json` adalah laporan yang dibuat ulang oleh build, bukan konfigurasi atau input tes. Gunakan folder output baru; jangan menimpa fixture atau mengubah allowlist hanya untuk memasukkan hasil eksperimen sementara.
