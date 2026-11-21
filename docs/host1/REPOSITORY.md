# Peta folder dan fungsi file repositori

Dokumen ini menjelaskan **setiap file kandidat Git** satu per satu. File dengan pola yang sama tetap dicatat dengan path masing-masing. Library pihak ketiga, model dan cache di folder lokal dijelaskan per kelompok, karena bukan kode yang diserahkan kelompok.

## Cara membaca alur proyek

`lab/` menyediakan konfigurasi router. `scripts/` dan `faults/` menyediakan cek serta eksperimen replika. Pada Host 1, `telemetry/` membaca state dan `log_ingestion/` mengumpulkan log; `graph_indexer/` menyusun relasi dan `knowledge/` mengikat fakta ke dokumentasi serta gate. `reasoning_agent/` memanggil model untuk lingkup yang didukung, lalu `agent_contract/` memvalidasi input/output. API saat ini hanya replay, belum executor perbaikan jaringan.

`data/host1/` adalah input pengujian terpilih, bukan seluruh hasil eksperimen. `docs/` menjelaskan cara kerja, status dan batas pengujian. `laptop/` adalah jalur SSH dari laptop menuju host lab. Konfigurasi replika dan Host 1 berbeda dan harus disesuaikan sebelum integrasi benchmark.

Fixture publik telah disanitasi: path mesin menjadi relatif, MAC terekam menjadi sintetis, dan referensi hash dihitung ulang. Evidence asli tetap di `private/privacy-originals/`. Data rancangan lab seperti IP router, ASN, state routing, MTU dan waktu eksperimen tetap diperlukan oleh pengujian.

## Mengapa sebagian file tetap dipertahankan

Tes dan API replay membutuhkan 148 fixture yang benar-benar dibaca, termasuk 133 JSON. Mengurangi kumpulan tersebut tanpa menyesuaikan desain/kontrak pengujian akan menghilangkan input yang dipakai saat ini. Menggabungkan JSON ke satu arsip hanya mengubah kemasan, bukan mengurangi dependensi. Schema, inventory dan manifest sumber tetap diperlukan untuk kontrak kelompok, reproducibility dan validasi citation. Evaluator serta harness yang dapat digunakan ulang tetap dibagikan meskipun bukan bagian server API.

Panduan endpoint, negatif/history parsial dan penjelasan sudah digabung ke `host1/reasoning_agent/TEMPORAL.md`. Dua skrip review/perbaikan satu eksperimen dan latihan Alpine awal tetap lokal dan di-ignore.

## Folder lokal yang tidak masuk Git

| Folder atau pola | Fungsi |
|---|---|
| `.git/` | Riwayat, index dan metadata kontrol versi; dikelola Git dan tidak di-commit sebagai isi proyek. |
| `private/.ai/` | Handoff dan arsip konteks AI lokal. |
| `private/original/`, `private/docs-history/` | Salinan README/aturan lama dan laporan/panduan sebelum konsolidasi. |
| `private/config/` | Snapshot lingkungan WSL untuk diagnosis lokal. |
| `private/runtime/ollama/dist/` | Binary/library Ollama. |
| `private/runtime/ollama/models/` | Manifest dan bobot model generatif. |
| `private/runtime/ollama/home/` | Home/cache proses Ollama, dapat berisi identitas privat; jangan dibagikan. |
| `private/knowledge/models/` | Bobot dan tokenizer embedding ONNX. |
| `private/knowledge/chroma/` | Database vektor Chroma lokal. |
| `private/.venv-graph/`, `private/.venv-retriever-wsl/` | Interpreter/dependensi Python terinstal; dibuat ulang dari requirements. |
| `private/lab-runtime/`, `clab-*/` | State/containerlab hasil deploy dan konfigurasi runtime yang dapat berubah saat fault. |
| `private/output/`, `private/tmp/` | Laporan keluaran lokal dan file render sementara. |
| `private/*.py`, `private/*.ps1`, `private/*.json`, `private/json-review-*/` | Utilitas migrasi/audit, hasil pencatatan input dan salinan uji kandidat Git lokal. |
| `data/host1/` di luar manifest | Hasil run, dump debug, log instalasi, checkpoint dan percobaan historis yang di-ignore. |
| `data/host2/` | JSONL hasil client replay dan waktu respons, termasuk endpoint lokal; seluruhnya di-ignore. |
| `AGENTS.md` | Instruksi kerja agen lokal; bukan keluaran tugas. |
| `laptop/config.ps1` | Alamat/user/konfigurasi koneksi pribadi. |
| `host1/knowledge/build.json` | Laporan build Chroma yang dapat dibuat ulang. |
| `host1/knowledge/review_unseen.py` | Review asisten yang di-hardcode untuk 12 query eksperimen lama; bukan evaluator umum. |
| `host1/tools/refreeze_mtu_audit.py` | Perbaikan registrasi untuk satu run audit MTU lama; bukan jalur agent. |
| `lab/host1/smoke-test/` | Latihan awal dua node Alpine yang sudah digantikan pengujian lab FRR. |
| `__pycache__/`, cache tool, `*.pyc`, log baru | Keluaran otomatis yang dapat dibuat ulang. |

## Daftar file kandidat Git

### File di root

| File | Fungsi |
|---|---|
| `.gitattributes` | Menyamakan line ending kode ke LF dan mempertahankan byte fixture/corpus agar hash evidence tidak berubah saat staging atau checkout. |
| `.gitignore` | Mencegah file privat, cache, keluaran eksperimen dan latihan lama masuk daftar Git. |
| `README.md` | Pintu masuk proyek: topik tugas, struktur, panduan dan aturan kerja kelompok. |

### data/

| File | Fungsi |
|---|---|
| `data/benchmark_plan.csv` | Jadwal 450 run: 30 fault × tiga varian × lima trial, dengan urutan acak tetap. |
| `data/replica/faults_20261119T155409Z.jsonl` | Hasil pengujian katalog di lab replika; setiap baris adalah satu hasil fault. |

### data/host1/

| File | Fungsi |
|---|---|
| `data/host1/.gitignore` | Daftar izin tepat per file: data lain dan seluruh keluaran run baru tetap di-ignore. |
| `data/host1/README.md` | Kebijakan pemilihan fixture, cakupan tes dan penjelasan arsip data lokal. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c1/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c2/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c3/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/endpoint-mapping/20261120T135238Z/controls-bound/c4/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f1/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/endpoint-mapping/20261120T135238Z/factorial-bound/f5/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/evidence-retrieval/replay-final-20261119/L12-before.json` | Bundle L12-before: evidence snapshot/graf/log dan dokumentasi terpilih beserta referensi hash/pointer. |
| `data/host1/evidence-retrieval/replay-final-20261119/L12-down.json` | Bundle L12-down: evidence snapshot/graf/log dan dokumentasi terpilih beserta referensi hash/pointer. |
| `data/host1/evidence-retrieval/replay-final-20261119/L12-restored.json` | Bundle L12-restored: evidence snapshot/graf/log dan dokumentasi terpilih beserta referensi hash/pointer. |
| `data/host1/evidence-retrieval/replay-final-20261119/L35-before.json` | Bundle L35-before: evidence snapshot/graf/log dan dokumentasi terpilih beserta referensi hash/pointer. |
| `data/host1/evidence-retrieval/replay-final-20261119/L35-down.json` | Bundle L35-down: evidence snapshot/graf/log dan dokumentasi terpilih beserta referensi hash/pointer. |
| `data/host1/evidence-retrieval/replay-final-20261119/L35-restored.json` | Bundle L35-restored: evidence snapshot/graf/log dan dokumentasi terpilih beserta referensi hash/pointer. |
| `data/host1/fixtures-manifest.json` | Daftar 148 fixture dan SHA-256 untuk memastikan input pengujian tidak berubah. |
| `data/host1/integration-faults/20261119T100613Z/L12/before/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/integration-faults/20261119T100613Z/L12/down/0002/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/integration-faults/20261119T100613Z/L12/restored/0003/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/integration-faults/20261119T100613Z/L35/before/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/integration-faults/20261119T100613Z/L35/down/0002/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/integration-faults/20261119T100613Z/L35/restored/0003/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/integration-faults/20261119T100613Z/graphs/L12/before/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/integration-faults/20261119T100613Z/graphs/L12/down/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/integration-faults/20261119T100613Z/graphs/L12/restored/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/integration-faults/20261119T100613Z/graphs/L35/before/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/integration-faults/20261119T100613Z/graphs/L35/down/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/integration-faults/20261119T100613Z/graphs/L35/restored/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/integration-faults/20261119T100613Z/inventory.json` | Identitas router, link dan peer yang diharapkan pada paket snapshot tersebut. |
| `data/host1/integration-faults/20261119T100613Z/logs/2026-11-19/r1.jsonl` | Event log FRR router r1; sumber citation riwayat yang benar-benar dibaca gate/replay. |
| `data/host1/integration-faults/20261119T100613Z/logs/2026-11-19/r2.jsonl` | Event log FRR router r2; sumber citation riwayat yang benar-benar dibaca gate/replay. |
| `data/host1/integration-faults/20261119T100613Z/logs/2026-11-19/r3.jsonl` | Event log FRR router r3; sumber citation riwayat yang benar-benar dibaca gate/replay. |
| `data/host1/integration-faults/20261119T100613Z/logs/2026-11-19/r4.jsonl` | Event log FRR router r4; sumber citation riwayat yang benar-benar dibaca gate/replay. |
| `data/host1/integration-faults/20261119T100613Z/logs/2026-11-19/r5.jsonl` | Event log FRR router r5; sumber citation riwayat yang benar-benar dibaca gate/replay. |
| `data/host1/integration-faults/20261119T100613Z/logs/2026-11-19/r6.jsonl` | Event log FRR router r6; sumber citation riwayat yang benar-benar dibaca gate/replay. |
| `data/host1/llm-temporal/20261120T124951Z/dev-v5/d2/observation-request.json` | Request grouped lama sebagai acuan regresi agar perubahan extractor tidak mengubah kontrol. |
| `data/host1/llm-temporal/20261120T124951Z/dev-v5/d2/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/mtu-replay/20261120T143211Z/L12-baseline.json` | Manifest input replay L12-baseline: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-boolean_mtu.json` | Manifest input replay L12-boolean_mtu: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-cross_link.json` | Manifest input replay L12-cross_link: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-fault.json` | Manifest input replay L12-fault: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-missing_endpoint.json` | Manifest input replay L12-missing_endpoint: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-partial.json` | Manifest input replay L12-partial: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-recovered.json` | Manifest input replay L12-recovered: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-reversed_time.json` | Manifest input replay L12-reversed_time: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L12-unknown_mtu.json` | Manifest input replay L12-unknown_mtu: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L35-baseline.json` | Manifest input replay L35-baseline: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L35-fault.json` | Manifest input replay L35-fault: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L35-partial.json` | Manifest input replay L35-partial: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L35-recovered.json` | Manifest input replay L35-recovered: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/L35-unknown_mtu.json` | Manifest input replay L35-unknown_mtu: menetapkan urutan snapshot/coverage untuk keadaan atau kontrol negatif ini. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/0/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/0/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/0/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/1/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/1/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/1/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/2/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/2/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/2/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/boolean_mtu/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/boolean_mtu/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/boolean_mtu/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/missing_endpoint/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/missing_endpoint/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/missing_endpoint/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/unknown_mtu/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/unknown_mtu/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L12/unknown_mtu/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/0/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/0/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/0/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/1/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/1/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/1/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/2/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/2/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/2/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/unknown_mtu/bundle.json` | Paket evidence dan dokumentasi beserta path/hash untuk satu keadaan replay. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/unknown_mtu/graph.json` | Graf topology/state/log bercitation yang direvalidasi terhadap snapshot sumber. |
| `data/host1/mtu-replay/20261120T143211Z/fixtures/L35/unknown_mtu/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/mtu-replay/latest-run.txt` | Pointer lokal stabil ke run fixture MTU yang dipakai setup unit test. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L12-restored-down_only/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/audit.json` | Metadata run, mode/options dan path/hash bundle; dibaca ulang validator penjelasan. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/combined-model-prediction.json` | Gabungan observasi dan fase yang dicocokkan dengan keluaran model mentah. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/input-contract.json` | Request agen tersimpan untuk dibandingkan dengan Request yang dibangun ulang. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/ollama-response.json` | Respons model mentah untuk membuktikan asal fase dan kelengkapan generasi. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/output-contract.json` | Response resmi tersimpan yang diverifikasi kembali terhadap kontrak dan klaim. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/prompt.txt` | Prompt historis yang dipakai validator untuk menghitung ulang token budget. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/raw-observations.json` | Ekstraksi observasi mentah model yang dicocokkan dengan evidence. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/raw-phase.json` | Fase model mentah sebelum metadata hasil dirakit/diterima validator. |
| `data/host1/negative-partial/20261120T140815Z/evaluation/L35-restored-down_only/visible-evidence.json` | View evidence yang benar-benar disediakan kepada model, termasuk history/coverage. |
| `data/host1/retrieval-unseen/run-20261119/state-en.json` | Hasil retrieval session-state yang dipakai unit test perluasan leaf YANG. |
| `data/host1/retrieval-unseen/run-20261119/timer-en.json` | Hasil retrieval timer BGP yang dipakai unit test adapter dan dukungan klaim. |
| `data/host1/telemetry/20261119T050248Z-fbeea22b/0001/snapshot.json` | State interface/OSPF/BGP/rute yang menjadi sumber fakta dan target pemeriksaan hash. |
| `data/host1/telemetry/20261119T050248Z-fbeea22b/inventory.json` | Identitas router, link dan peer yang diharapkan pada paket snapshot tersebut. |

### docs/

| File | Fungsi |
|---|---|
| `docs/akses-dari-laptop.md` | Panduan SSH Windows ke NetworkLab, konfigurasi laptop dan diagnosis koneksi. |
| `docs/host2-replay.md` | Panduan client HTTP Host 2: 16 skenario berurutan, format JSONL, timing dan penanganan kegagalan. |
| `docs/fault-harness.md` | Cara menjalankan lab replika, katalog dan fault runner serta batas adaptasi ke Host 1. |
| `docs/host1/OPERATIONS.md` | Lokasi file, environment, menjalankan modul dan pemeriksaan mount setelah migrasi. |
| `docs/host1/LIVE-API-DRAFT.md` | Usulan kontrak live untuk dibahas kelompok: endpoint diagnosis, evidence, varian, linter, timing dan JSONL; belum layanan aktif. |
| `docs/host1/README.md` | Indeks dokumentasi Host 1 dan tautan ke panduan masing-masing modul. |
| `docs/host1/REPOSITORY.md` | Katalog fungsi folder dan seluruh file kandidat Git; termasuk penjelasan file lokal yang di-ignore. |
| `docs/host1/STATUS.md` | Kemampuan saat ini, pekerjaan tersisa, pembagian jalur dan urutan integrasi. |
| `docs/host1/TOPOLOGY-DESIGN.md` | Rancangan delapan link, IP, AS, OSPF, iBGP/eBGP, policy dan jalur cadangan Host 1. |
| `docs/host1/VALIDATION.md` | Ringkasan hasil pengujian beserta batas klaim live, replay, sintetis dan controller/model. |

### faults/

| File | Fungsi |
|---|---|
| `faults/catalog.yaml` | Katalog 30 fault replika: langkah inject/revert, gejala dan ground truth untuk runner/evaluator. |

### host1/live_api/

| File | Fungsi |
|---|---|
| `host1/live_api/__init__.py` | Package schema dan simulator kontrak live, terpisah dari API replay. |
| `host1/live_api/README.md` | Panduan mock lokal, autentikasi, pemilihan schema, skenario client dan batas simulasi. |
| `host1/live_api/requirements.txt` | Dependency minimum runtime Pydantic dan tes JSON Schema. |
| `host1/live_api/models.py` | Model request/job/evidence/lint/health/capabilities dan validator binding/proyeksi/hash. |
| `host1/live_api/schema.json` | Definisi JSON Schema Draft 2020-12 yang dihasilkan dari model wire baru. |
| `host1/live_api/examples.json` | Bundle contoh payload sintetis untuk integrasi client, tanpa data mesin lokal. |
| `host1/live_api/examples.py` | Generator deterministik schema dan contoh; sumber fixture mock. |
| `host1/live_api/mock.py` | Simulator HTTP loopback, job async, SQLite, idempotensi dan outcome sintetis tanpa model/router. |
| `host1/live_api/test_mock.py` | Tes schema, HTTP, concurrency, evidence dan restart pada output/port sementara. |
| `host1/live_api/test_diagnosis.py` | Tes label kelas/router live, binding assessment, diagnosis tanpa patch dan kompatibilitas replay/linter. |

### host1/agent_contract/

| File | Fungsi |
|---|---|
| `host1/agent_contract/README.md` | Panduan penggunaan, alur dan batas modul agent_contract. |
| `host1/agent_contract/__init__.py` | Penanda package Python agent_contract; menjaga struktur import modul. |
| `host1/agent_contract/input.schema.json` | Kontrak input dalam JSON Schema agar komponen selain Python memahami bentuk Request. |
| `host1/agent_contract/models.py` | Model Pydantic Request/Response dan validator pasangan input/output, citation serta flag eksekusi. |
| `host1/agent_contract/output.schema.json` | Kontrak output dalam JSON Schema untuk hipotesis/abstain, klaim dan usulan patch. |
| `host1/agent_contract/validate_examples.py` | Memeriksa dua contoh sintetis valid dan kontrol negatif kontrak tanpa model atau router. |

### host1/graph_indexer/

| File | Fungsi |
|---|---|
| `host1/graph_indexer/CORRELATION.md` | Panduan model relasi event, aturan waktu, CLI korelasi dan batas interpretasinya. |
| `host1/graph_indexer/README.md` | Panduan penggunaan, alur dan batas modul graph_indexer. |
| `host1/graph_indexer/__init__.py` | Penanda package Python graph_indexer; menjaga struktur import modul. |
| `host1/graph_indexer/capture_faults.py` | Merekam paket log/snapshot saat uji fault L12/L35; dipakai hanya pada eksperimen live yang diizinkan. |
| `host1/graph_indexer/capture_live.py` | Mengambil paket snapshot dan marker FRR untuk uji integrasi log/graf pada lab aktif. |
| `host1/graph_indexer/correlate.py` | Menambahkan event log ke graf menurut router/protokol dan window waktu; tidak menyimpulkan kausalitas. |
| `host1/graph_indexer/indexer.py` | Menyusun NetworkX MultiDiGraph dari snapshot/inventory, dengan provenance dan state unknown yang eksplisit. |
| `host1/graph_indexer/requirements.txt` | Dependensi NetworkX yang dipin untuk modul graf. |
| `host1/graph_indexer/validate_faults.py` | Memeriksa korelasi event L12/L35 terhadap paket telemetry fault yang disimpan. |
| `host1/graph_indexer/validate_live.py` | Memeriksa marker dan relasi graf pada paket hasil capture_live. |

### host1/knowledge/

| File | Fungsi |
|---|---|
| `host1/knowledge/EVIDENCE.md` | Panduan format bundle, CLI evidence dan batas penafsiran fakta/citation. |
| `host1/knowledge/QUALITY-GATE.md` | Aturan keputusan context_ready/abstain, freshness dan dukungan klaim. |
| `host1/knowledge/README.md` | Panduan penggunaan, alur dan batas modul knowledge. |
| `host1/knowledge/__init__.py` | Penanda package Python knowledge; menjaga struktur import modul. |
| `host1/knowledge/chunks.jsonl` | 739 chunk corpus beserta teks, metadata dan ID; dibaca ranking lexical untuk hybrid retrieval. |
| `host1/knowledge/evaluate.py` | Acceptance retrieval untuk pertanyaan terarah dan pemeriksaan provenance setiap hit. |
| `host1/knowledge/evaluate_evidence.py` | Mengevaluasi integrasi retrieval dengan enam graf baseline/fault/pemulihan tersimpan. |
| `host1/knowledge/evaluate_gate.py` | Memeriksa acceptance dan kontrol negatif gate terhadap paket evidence. |
| `host1/knowledge/evaluate_gate_v2.py` | Mengevaluasi dukungan pertanyaan/klaim pada kumpulan query yang sudah disimpan. |
| `host1/knowledge/evaluate_preollama.py` | Evaluasi query pra-Ollama dan pengikatan hasil ke versi kode/corpus yang dibekukan. |
| `host1/knowledge/evaluate_unseen.py` | Membekukan dan menjalankan kumpulan query baru, anchor yang diharapkan dan audit hasil gate. |
| `host1/knowledge/evidence.py` | Memverifikasi bundle graf/snapshot/log, hash dan pointer, menghubungkan retrieval, serta memetakan path lama. |
| `host1/knowledge/fetch_mtu_references.py` | Mengunduh referensi primer MTU terpisah dari corpus Chroma. |
| `host1/knowledge/fetch_sources.py` | Mengunduh enam sumber FRR/OpenConfig pada versi tetap dan membuat manifest hash. |
| `host1/knowledge/quality_gate.py` | Menolak konteks tanpa integritas, freshness atau kutipan pendukung yang memenuhi aturan. |
| `host1/knowledge/question_support.py` | Memetakan pertanyaan yang dikenali menjadi persyaratan klaim; scope lain abstain. |
| `host1/knowledge/replay_preollama.py` | Regresi ulang query historis setelah perubahan gate/ekspansi YANG; dapat memerlukan arsip lokal. |
| `host1/knowledge/requirements.lock.txt` | Versi dependensi Python retrieval yang dipin untuk environment Linux. |
| `host1/knowledge/retriever.py` | Build/query Chroma, embedding ONNX, BM25 dan penggabungan ranking dense/lexical. |
| `host1/knowledge/sources-manifest.json` | Versi, URL dan SHA-256 enam sumber utama yang dipakai validasi citation. |
| `host1/knowledge/sources/frr-bgp.rst` | Dokumentasi resmi FRR bgp pada versi tetap untuk corpus dan citation. |
| `host1/knowledge/sources/frr-ospfd.rst` | Dokumentasi resmi FRR ospfd pada versi tetap untuk corpus dan citation. |
| `host1/knowledge/sources/frr-zebra.rst` | Dokumentasi resmi FRR zebra pada versi tetap untuk corpus dan citation. |
| `host1/knowledge/sources/openconfig-openconfig-bgp-common.yang` | Sumber schema OpenConfig openconfig-bgp-common.yang; dipin untuk retrieval dan pemeriksaan kutipan. |
| `host1/knowledge/sources/openconfig-openconfig-bgp-neighbor.yang` | Sumber schema OpenConfig openconfig-bgp-neighbor.yang; dipin untuk retrieval dan pemeriksaan kutipan. |
| `host1/knowledge/sources/openconfig-openconfig-interfaces.yang` | Sumber schema OpenConfig openconfig-interfaces.yang; dipin untuk retrieval dan pemeriksaan kutipan. |
| `host1/knowledge/supplemental-mtu/README.md` | Cakupan/lisensi dan batas interpretasi referensi MTU tambahan. |
| `host1/knowledge/supplemental-mtu/frr-ospf-packet.c` | Implementasi packet OSPF FRR sebagai referensi primer perilaku paket/MTU. |
| `host1/knowledge/supplemental-mtu/frr-ospf-vty.c` | Implementasi CLI OSPF FRR sebagai referensi primer pengaturan terkait MTU. |
| `host1/knowledge/supplemental-mtu/linux-netdevices.rst` | Dokumentasi kernel Linux untuk arti MTU pada network device. |
| `host1/knowledge/supplemental-mtu/manifest.json` | URL, versi, jenis dokumen dan SHA-256 empat referensi primer tambahan. |
| `host1/knowledge/supplemental-mtu/rfc2328.txt` | Spesifikasi OSPFv2, termasuk mekanisme InterfaceDown/KillNbr yang dipakai penjelasan RCA. |
| `host1/knowledge/test_evidence.py` | Unit test integritas sumber, hash/pointer, path lama, penolakan data palsu dan normalisasi referensi. |
| `host1/knowledge/test_quality_gate.py` | Unit test gate yang gagal tertutup pada evidence/intent/parameter yang tidak memenuhi aturan. |
| `host1/knowledge/test_question_support.py` | Unit test scope pertanyaan, klaim gabungan dan pencegahan bypass gate melalui metadata. |
| `host1/knowledge/test_retriever.py` | Unit test ranking lexical dan validasi parameter retrieval. |
| `host1/knowledge/test_yang_context.py` | Unit test parsing brace YANG, ekspansi leaf, batas ukuran dan dukungan klaim default. |
| `host1/knowledge/yang_context.py` | Memperluas hit YANG ke leaf lengkap yang bertumpang tindih tanpa mengubah ranking asli. |

### host1/log_ingestion/

| File | Fungsi |
|---|---|
| `host1/log_ingestion/README.md` | Panduan penggunaan, alur dan batas modul log_ingestion. |
| `host1/log_ingestion/check_live.py` | Probe marker pascarecovery tanpa me-restart Vector, disertai salinan sumber/hash. |
| `host1/log_ingestion/image.txt` | Referensi image Vector yang dipin untuk skrip manage. |
| `host1/log_ingestion/manage.sh` | Menyiapkan folder serta memvalidasi/menjalankan Vector dengan mount dan pembatasan container. |
| `host1/log_ingestion/test_live.py` | Uji marker daemon FRR dan ingestion; menyediakan helper yang juga dipakai check_live. |
| `host1/log_ingestion/vector.yaml` | Konfigurasi Vector untuk membaca log FRR, memberi identitas router dan menulis event JSON Lines. |

### host1/ollama_host/

| File | Fungsi |
|---|---|
| `host1/ollama_host/README.md` | Panduan penggunaan, alur dan batas modul ollama_host. |
| `host1/ollama_host/inference-profile.json` | Profil model, digest dan parameter inferensi yang harus dipenuhi adapter. |
| `host1/ollama_host/requirements-setup.txt` | Dependensi setup terpisah untuk pembacaan arsip terkompresi; bukan dependensi inferensi. |
| `host1/ollama_host/serve.sh` | Menjalankan Ollama dari private/runtime dengan home/model privat dan bind loopback. |
| `host1/ollama_host/smoke_test.py` | Memeriksa metadata backend dan dua inferensi JSON sintetis cold/warm. |
| `host1/ollama_host/verify_archive.py` | Memverifikasi ukuran/digest arsip Ollama sebelum mengekstrak binary lokal. |
| `host1/ollama_host/verify_model.py` | Memverifikasi manifest dan blob model terhadap digest tersimpan serta identitas API. |

### host1/reasoning_agent/

| File | Fungsi |
|---|---|
| `host1/reasoning_agent/API.md` | Panduan endpoint, startup, request/error, concurrency dan batas API replay. |
| `host1/reasoning_agent/MTU.md` | Panduan fixture dan profil MTU, batas observasional dan CLI replay. |
| `host1/reasoning_agent/RCA.md` | Panduan scope RCA administratif DOWN, CLI dan batas klaim controller/model. |
| `host1/reasoning_agent/README.md` | Panduan penggunaan, alur dan batas modul reasoning_agent. |
| `host1/reasoning_agent/TEMPORAL.md` | Panduan gabungan fase temporal, binding endpoint, negatif/history parsial dan validasi penjelasan. |
| `host1/reasoning_agent/__init__.py` | Penanda package Python reasoning_agent; menjaga struktur import modul. |
| `host1/reasoning_agent/adapter.py` | Memilih evidence/kutipan, membatasi token, memanggil Ollama dan memvalidasi jawaban dokumentasi. |
| `host1/reasoning_agent/analyze_endpoint_results.py` | Audit hasil paired, ikatan sumber dan kesetaraan request antarfaktor. |
| `host1/reasoning_agent/api.py` | HTTP API loopback untuk replay terdaftar, hasil, evidence, locking dan error; tanpa executor. |
| `host1/reasoning_agent/audit_negative.py` | Audit pascapengujian atas provenance, kontrak dan respons kasus negatif/parsial. |
| `host1/reasoning_agent/evaluate.py` | Kontrol negatif adapter dan evaluasi hasil replay Ollama tersimpan. |
| `host1/reasoning_agent/evaluate_endpoints.py` | Membandingkan strategi grouped/bound pada matriks urutan dan identitas endpoint. |
| `host1/reasoning_agent/evaluate_explanations.py` | Daftar delapan run penjelasan dan evaluator laporan klaim/citation yang juga dipakai tes. |
| `host1/reasoning_agent/evaluate_negative.py` | Membuat/menjalankan negatif dan history parsial; helper persist dipakai evaluator lain. |
| `host1/reasoning_agent/evaluate_temporal.py` | Menilai prediksi mentah model terpisah dari penerimaan gate/kontrak. |
| `host1/reasoning_agent/explanation.py` | Merevalidasi run tersimpan dan menyusun laporan klaim deterministik dengan citation per klaim. |
| `host1/reasoning_agent/freeze_endpoint_cases.py` | Membekukan kasus/label/hash dan pemetaan ID endpoint; id_map juga dipakai unit test. |
| `host1/reasoning_agent/freeze_temporal_cases.py` | Membekukan fixture temporal sebelum evaluasi untuk memisahkan input dan label. |
| `host1/reasoning_agent/mtu.py` | Profil observasi MTU sintetis: controller memeriksa nilai/relasi, model memilih fase. |
| `host1/reasoning_agent/rca.py` | Replay RCA administratif DOWN dan kontrol sehat, dengan validasi sumber/fakta/kontrak. |
| `host1/reasoning_agent/rca_gate.py` | Gate hipotesis link yang sempit, pemeriksaan state/log dan pemilihan mekanisme dokumentasi. |
| `host1/reasoning_agent/replay-scenarios.json` | Registri 16 scenario_id beserta path/hash input, profil dan penanda sintetis. |
| `host1/reasoning_agent/replay_mtu.py` | Membuat dan menjalankan skenario replay/negatif MTU sintetis tanpa fault router. |
| `host1/reasoning_agent/replay_rca.py` | Menjalankan preflight/inferensi pada enam paket evidence L12/L35 yang telah disimpan. |
| `host1/reasoning_agent/report_rca.py` | Merevalidasi hasil RCA dan merender penjelasan kondisi, gejala dan asal sumber. |
| `host1/reasoning_agent/temporal.py` | Ekstraksi endpoint/history dan pemilihan fase baseline/fault/recovered/undetermined oleh model. |
| `host1/reasoning_agent/test_adapter.py` | Unit test pemilihan kutipan, token budget, kontrak, output model dan penolakan patch/injeksi. |
| `host1/reasoning_agent/test_api.py` | Tes HTTP localhost nyata dengan respons model simulasi, termasuk error dan pengambilan evidence. |
| `host1/reasoning_agent/test_endpoint_mapping.py` | Unit test binding identitas/nilai, perubahan urutan/ID dan regresi temporal. |
| `host1/reasoning_agent/test_explanation.py` | Unit test klaim atomik, sumber citation, waktu, kondisi/gejala dan larangan penyebab yang tak terbukti. |
| `host1/reasoning_agent/test_mtu.py` | Unit test batas nilai MTU, fase, provenance dan penolakan model; tanpa model nyata. |
| `host1/reasoning_agent/test_rca.py` | Unit test batas scope RCA, target administratif, peer/log spesifik dan validasi prediksi. |
| `host1/reasoning_agent/test_temporal.py` | Unit test observasi, fase/history, citation dan penolakan prediksi salah tanpa mengoreksinya. |

### host1/telemetry/

| File | Fungsi |
|---|---|
| `host1/telemetry/README.md` | Panduan penggunaan, alur dan batas modul telemetry. |
| `host1/telemetry/__init__.py` | Penanda package Python telemetry; menjaga struktur import modul. |
| `host1/telemetry/collector.py` | Mengambil snapshot interface, peer OSPF/BGP, rute FRR/kernel dan metadata sumber dari router. |
| `host1/telemetry/test_link_faults.py` | Harness live L12/L35 yang mengubah link, mengumpulkan snapshot dan memulihkan baseline; bukan unit test biasa. |

### host1/tests/

| File | Fungsi |
|---|---|
| `host1/tests/test_correlation.py` | Unit test waktu event, duplikasi, routing relasi protokol dan state parsial pada korelasi log. |
| `host1/tests/test_graph_indexer.py` | Unit test state graf, MTU, sumber parsial, node-link round-trip dan validasi schema/lab. |
| `host1/tests/test_telemetry.py` | Unit test normalisasi dan kegagalan sebagian sumber collector tanpa menyentuh router. |
| `host1/tests/validate_live_telemetry.py` | Pemeriksa baseline sehat dari output collector; bukan detektor fault umum. |

### host1/tools/

| File | Fungsi |
|---|---|
| `host1/tools/MTU-VARIATIONS.md` | Prosedur freeze, variasi dan audit MTU; bukan eksekusi perbaikan router. |
| `host1/tools/audit_mtu_variations.py` | Memeriksa binding angka/endpoint/citation serta integritas hasil variasi MTU. |
| `host1/tools/mtu_variations.py` | Membuat/menjalankan variasi nilai, urutan dan penempatan MTU dengan kode yang dibekukan. |
| `host1/tools/smoke_agent_api.py` | Klien smoke HTTP dengan pemeriksaan respons, timing, citation dan fetch evidence. |
| `host1/tools/test_mtu_variations.py` | Unit test resolver JSON pointer dan audit angka/citation pada harness variasi. |

### lab/host1/

| File | Fungsi |
|---|---|
| `lab/host1/frr/README.md` | Panduan source config, image, validasi parser, deploy dan verifikasi lab FRR Host 1. |
| `lab/host1/frr/check-subnets.py` | Mendeteksi kesalahan/overlap subnet berdasarkan inventory rancangan. |
| `lab/host1/frr/configs/r1/frr.conf` | Konfigurasi FRR router r1: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/host1/frr/configs/r2/frr.conf` | Konfigurasi FRR router r2: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/host1/frr/configs/r3/frr.conf` | Konfigurasi FRR router r3: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/host1/frr/configs/r4/frr.conf` | Konfigurasi FRR router r4: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/host1/frr/configs/r5/frr.conf` | Konfigurasi FRR router r5: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/host1/frr/configs/r6/frr.conf` | Konfigurasi FRR router r6: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/host1/frr/design-plan.json` | Inventory terstruktur router/link/interface/peer untuk collector dan pemeriksa Host 1. |
| `lab/host1/frr/image-lock.json` | Catatan image FRR yang dipin, digest dan versi lingkungan yang telah diverifikasi. |
| `lab/host1/frr/test-failover.py` | Uji live yang mengubah status link L12/L35 lalu memeriksa perpindahan jalur dan pemulihan. |
| `lab/host1/frr/topology.clab.yml` | Definisi deploy Containerlab: node FRR, link, image, startup config, MTU dan bind log. |
| `lab/host1/frr/validate-config.sh` | Validasi YAML dan sintaks konfigurasi FRR dalam container parser sementara. |
| `lab/host1/frr/validation/vtysh.conf` | Pengaturan vtysh untuk pemuatan/pemeriksaan konfigurasi FRR. |
| `lab/host1/frr/verify-runtime.py` | Memeriksa lab yang sudah berjalan, routing, sesi, service route dan ping. |

### lab/replica/

| File | Fungsi |
|---|---|
| `lab/replica/daemons` | Daftar daemon FRR yang diaktifkan pada lab replika. |
| `lab/replica/six-node/configs/r1/frr.conf` | Konfigurasi FRR router r1: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/six-node/configs/r2/frr.conf` | Konfigurasi FRR router r2: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/six-node/configs/r3/frr.conf` | Konfigurasi FRR router r3: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/six-node/configs/r4/frr.conf` | Konfigurasi FRR router r4: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/six-node/configs/r5/frr.conf` | Konfigurasi FRR router r5: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/six-node/configs/r6/frr.conf` | Konfigurasi FRR router r6: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/six-node/topik8.clab.yml` | Definisi Containerlab enam router replika untuk pengujian katalog fault. |
| `lab/replica/two-node/configs/r1/frr.conf` | Konfigurasi FRR router r1: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/two-node/configs/r2/frr.conf` | Konfigurasi FRR router r2: alamat, OSPF/BGP, network/policy sesuai lab induknya. |
| `lab/replica/two-node/lab2.clab.yml` | Definisi Containerlab dua router latihan. |
| `lab/replica/vtysh.conf` | Pengaturan vtysh untuk pemuatan/pemeriksaan konfigurasi FRR. |

### laptop/

| File | Fungsi |
|---|---|
| `laptop/config.example.ps1` | Template pengaturan koneksi; salin sebagai config.ps1 yang di-ignore dan isi secara lokal. |
| `laptop/lab.ps1` | Pembungkus PowerShell untuk diagnosis koneksi dan menjalankan runner/cek melalui SSH ke Host 1. |
| `laptop/replay.ps1` | Client HTTP PowerShell 5.1/7 yang menjalankan 16 replay berurutan, memverifikasi evidence dan menyimpan respons/timing ke JSONL. |
| `laptop/tests/test_replay_client.py` | Tes pengembang terhadap script PowerShell asli menggunakan HTTP simulasi; mencakup urutan, UTF-8, error, timeout dan perlindungan file hasil. |

### scripts/

| File | Fungsi |
|---|---|
| `scripts/check_lab.py` | Memeriksa interface, OSPF, BGP, rute dan ping menurut ekspektasi lab replika. |
| `scripts/fault_runner.py` | Membaca katalog, menyuntikkan fault, menunggu gejala, menyimpan hasil, menjalankan revert dan membuat jadwal. |
| `scripts/host1.py` | Launcher Python yang mengatur root kerja dan PYTHONPATH agar modul Host 1 bisa diimpor. |
