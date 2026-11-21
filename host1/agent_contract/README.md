# Kontrak reasoning agent

Modul ini menyediakan model Pydantic dan JSON Schema. Adapter Ollama terpisah tersedia di host1/reasoning_agent/; linter dan executor belum tersedia. Dependency Pydantic2.14.3 sudah ada pada .venv-retriever-wsl. Schema input/output diekspor dari models.py; sumber kebenaran kontrak adalah models.py dan validate_pair.

## Input

Request memuat schema_version, request_id, lab=rca, question, mode replay/live, snapshot_completed_at, ringkasan gate, evidence, dan execution_allowed=false. Setiap evidence mempunyai ID unik, kind telemetry/log/graph/documentation, source_path, SHA-256, locator dan content. Locator adalah JSON pointer untuk snapshot/graf, nomor baris untuk log, atau URL/baris untuk dokumen.

Controller masa depan wajib memverifikasi hash/pointer/freshness melalui evidence builder/gate sebelum menyusun input. Pydantic memeriksa bentuk, bukan keaslian file maupun kelayakan semantik evidence. Gate/input berasal dari controller, bukan boleh diganti oleh model. Jangan memasukkan seluruh JSON evidence besar ke prompt tanpa pemilihan relevansi dan batas token; jangan membuang citation untuk menghemat konteks.

## Output

Response memuat status hypothesis/abstain, root_cause_hypothesis, confidence opsional0..1, claims dengan evidence_ids, missing_evidence, proposed_patch dan execution_allowed=false. Confidence adalah estimasi model yang belum terkalibrasi. Hypothesis adalah usulan belum tervalidasi, bukan diagnosis terbukti.

Setiap proposed command memiliki router r1..r6, interface opsional, interpreter linux_argv/vtysh_commands, arguments berbentuk list, evidence_ids, rationale dan validation_status=unvalidated. Linux argv adalah satu argv; vtysh_commands adalah rangkaian string per-command vtysh. Kontrak tidak menjalankan atau menggabungkan isi list ke shell. Schema bukan allowlist command: validasi sintaks, izin target, dampak, rollback dan post-verification masih tugas linter/executor terpisah.

Abstain mengharuskan hipotesis/confidence null dan patch kosong. validate_pair menolak mismatch request_id, referensi tidak dikenal, atau hipotesis saat gate abstain/answer_supported=false. Extra fields ditolak. Eksekusi tidak dapat diaktifkan melalui respons. Setelah linter dibangun, hasil validasinya harus menjadi artefak terpisah; jangan mempercayai klaim validasi yang dibuat model.

## Alur yang direncanakan

Evidence builder → quality gate → input contract → reasoning agent → output contract → command linter → verifikasi/otorisasi eksekusi lab → post-verification. Integrasi tahap awal pada host1/reasoning_agent/ memanggil Ollama untuk pertanyaan dokumentasi yang didukung gate, dengan evidence terpilih dan budget konteks. Tahap ini menolak patch, mempertahankan diagnosis_allowed=false/execution_allowed=false, dan tidak memiliki executor. Pertanyaan root cause yang belum didukung tetap abstain sebelum inferensi. Lihat ../reasoning_agent/README.md.

Tes tanpa model:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m agent_contract.validate_examples data/host1/pre-ollama/new-contract-test
```

Hasil saat ini: dua contoh sintetis valid dan enam kontrol negatif lulus (execution flag, request mismatch, abstain dengan hipotesis, referensi tak dikenal, bypass gate, extra field). Contoh sengaja memakai referensi sintetis dan bukan diagnosis jaringan nyata. Bukti ada pada data/host1/pre-ollama/contract/.
