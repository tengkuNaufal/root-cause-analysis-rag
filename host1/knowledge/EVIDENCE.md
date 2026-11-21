# Integrasi knowledge dan evidence Host 1

`python scripts/host1.py -m knowledge.evidence` membuat paket JSON untuk satu link dan satu snapshot dari graf NetworkX tersimpan. Modul membaca format node-link JSON hasil graph_indexer; tidak menginstal NetworkX ulang di venv retriever, membangun ulang graf, atau mengubah koleksi Chroma. Semua proses berjalan lokal di WSL NetworkLab, tanpa mengubah router.

## Alur dan kontrak data

1. Baca graph.json dan inventory. Verifikasi SHA-256 snapshot, inventory, dan seluruh file log frozen terhadap metadata graf. Path Windows/WSL dipetakan ke root proyek, path di luar proyek ditolak.
2. Pilih link dari inventory dan dua endpoint-nya. Cocokkan observasi interface dan sesi protokol graf dengan snapshot; periksa state physical dari flag admin/lower interface. Paket menyertakan sumber telemetry endpoint serta r1 (termasuk routing/kernel routes), status sumber, waktu dan JSON pointer. Route data disertakan sebagai konteks, bukan diagnosis perubahan rute otomatis.
3. Cocokkan setiap event graf dengan baris JSONL asli dan hash file, serta jendela event-time graf. Event masa depan ditolak. Pilih log endpoint dengan daemon protokol yang sesuai; jumlah event lain yang dikeluarkan dicatat. Ini belum pemetaan peer/interface per log: event lain pada router/protokol yang sama masih mungkin terpilih.
4. Bentuk query deterministik dari protokol, state physical, dan state peer. Tambahkan query OpenConfig interface/MTU, query session-state untuk BGP, serta maksimal dua pesan log terbaru. Pesan hanya data pencarian, tidak dijalankan sebagai instruksi. Tidak memakai nama fase baseline/down/restored atau label ground truth untuk menyusun query. Pertanyaan tambahan opsional melalui --question.
5. Jalankan retriever hybrid Chroma/BM25 yang ada. Setiap hasil diperiksa terhadap hash file dokumentasi, rentang baris, teks asli dan platform. Simpan 5 hit per query, query yang dipakai, skor, citation_url dan trigger_evidence. Log query menyertakan ID node graf dan citation log yang memicunya.

Struktur keluaran:
- `evidence.inputs`: graph/snapshot/inventory/log path relatif proyek + SHA-256.
- `evidence.physical`, `interfaces`, `sessions`: observasi graf terpilih dengan pointer sumber.
- `evidence.telemetry`: source payload, status dan pointer snapshot.
- `evidence.logs`: node log, pesan, timestamp, baris/hash JSONL dan edge konteks graf.
- `documentation`: query, hit/citation, trigger evidence, relation=documentation_context, causal_claim=false.
- `diagnosis=null`, `executable_patch=null`: tidak ada inferensi sebab atau eksekusi CLI.

Beberapa field graf/telemetry yang disalin tetap menyimpan path asli Windows/WSL; gunakan evidence.inputs dan helper local_path untuk resolusi lintas OS. Hash input disimpan untuk audit, bukan tanda tangan kriptografis dari pihak tepercaya. Hash bukan bukti bahwa isi observasi benar secara operasional.

## Menjalankan

Dari root proyek pada terminal interaktif NetworkLab:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m knowledge.evidence \
  --graph data/host1/integration-faults/20261119T100613Z/graphs/L35/down/graph.json \
  --inventory data/host1/integration-faults/20261119T100613Z/inventory.json \
  --link L35 \
  --output data/host1/evidence-retrieval/my-L35-query.json
```

Pilih nama keluaran baru: CLI menolak overwrite. Ini memakai corpus/database/model yang sudah dibangun; tidak perlu build ulang atau internet setelah setup awal.

Replay enam graf dan negative tests:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m knowledge.evaluate_evidence data/host1/evidence-retrieval/new-replay
private/.venv-retriever-wsl/bin/python scripts/host1.py -m unittest knowledge.test_evidence knowledge.test_retriever -v
```

## Batas penggunaan

Snapshot tidak atomik dan log sebelum snapshot dapat tetap ada setelah state pulih. Pesan Down bukan bukti fault masih aktif. Query template terutama memakai bahasa Inggris; kualitas multilingual belum dibuktikan. OpenConfig adalah schema, bukan CLI FRR, dan evidence builder tidak menjalankan perbaikan jaringan.

Paket memisahkan fakta runtime dari referensi dokumentasi dengan citation, tanpa memberi label penyebab. Evaluasi replay memeriksa integritas, state dan pemilihan event. Hasilnya bukan akurasi root cause atau benchmark relevansi retrieval.

## Quality gate

Paket baru memiliki quality_gate. Gate versi 2.1 memeriksa persyaratan klaim pertanyaan yang dikenali, provenance dan dukungan kutipan. Scope yang tidak dikenali tetap abstain. Ini aturan dukungan terbatas, bukan threshold similarity terkalibrasi atau semantic entailment umum. context_ready tidak mengizinkan diagnosis atau eksekusi CLI.

Gunakan [panduan gate](QUALITY-GATE.md) untuk opsi CLI, [hasil validasi](../../docs/host1/VALIDATION.md#retrieval-dan-quality-gate) untuk hasil dan batas klaim, serta [status Host 1](../../docs/host1/STATUS.md) untuk integrasi reasoning/API yang tersedia.
