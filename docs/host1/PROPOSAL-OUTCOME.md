# Diagnosis dan penolakan proposal

Diagnosis dan perintah dinilai terpisah. Job completed dengan status hypothesis dapat
memiliki proposed_patch dan assessment.commands kosong ketika usulan perintah ditolak.
Router, kelas, confidence, claims, evidence dan penjelasan diagnosis tetap dipertahankan.

Tidak ada field wire atau perubahan versi live.v1-draft2. Field missing_evidence yang sudah
ada dapat membawa catatan controller berawalan `proposal_rejected:v1:` diikuti JSON:
version, status=rejected, stage=lint/guard, code, commands_sha256, candidate_count, policy_version.
Catatan ini adalah hasil validasi proposal, bukan pernyataan bahwa evidence diagnosis kurang.
Hash memakai JSON canonical atas proyeksi commands kandidat; kandidat mentah tidak diekspor.
candidate_count menghitung objek command/blok, bukan jumlah baris CLI di dalam args.
Runner dan evaluator memakai decoder stdlib yang sama pada scripts/proposal_outcome.py.

Hanya penolakan policy yang dikenal yang dikonversi menjadi diagnosis tanpa proposal.
Diagnosis tanpa dukungan, binding/citation tidak valid, capture/freshness/hash gagal, schema
tidak valid dan exception internal tetap menyebabkan job gagal. Controller tidak membuat
perintah pengganti. proposal-validation.json lokal menyimpan kandidat dan alasan untuk audit.
Job tetap execution_allowed=false. Semua perubahan diuji offline sebelum aktivasi terkoordinasi.

Runner memverifikasi envelope dan evidence terlebih dahulu. Catatan penolakan valid disimpan
ke JSONL `proposal` dengan status rejected, stage, code, candidate_count dan hash kandidat.
`lint.status=not_requested` karena tidak ada perintah diekspor untuk linter client; ini tidak
menghapus hasil penolakan server yang tetap tercatat pada proposal. `execution.attempted=false`,
applied=false dan fallback_revert.reason=api_proposal_rejected. Hash kandidat bukan izin eksekusi
dan tidak dipakai sebagai hash commands client. Status run tetap completed, bukan job_failed.
Catatan malformed, duplikat atau penolakan yang masih mengekspor perintah ditolak sebagai
invalid_response. Penolakan proposal tidak mengurangi pemeriksaan evidence atau aturan terminal.

Evaluator tetap menilai rca_accuracy dari router/kelas diagnosis, terlepas dari proposal.
Proposal ditolak bukan abstain dan bukan agent_error. Metrik proposal_rejection_rate,
proposal_lint_rejection_rate dan proposal_guard_rejection_rate memakai semua run sebagai
denominator. command_approval_rate adalah proporsi run dengan perintah diekspor dan lolos
linter client; ini bukan bukti keberhasilan perbaikan. command_correctness yang sudah ada
tetap berarti lulus lint dan pulih oleh perintah agen. fix_success_rate tetap memakai run
yang benar-benar applied; fallback tidak dihitung sebagai pemulihan agen.

runs_scored.csv mencatat stage/code penolakan dan candidate_commands_count. Kandidat ditahan
tidak dapat diperiksa ulang untuk halusinasi perintah dari JSONL saja; flag
rejected_candidate_hallucination_unassessed menyatakan keterbatasan itu. Laporan tidak menganggap
hash sebagai isi kandidat. Metadata proposal runner harus cocok dengan catatan API; penolakan
yang diklaim applied/attempted ditolak sebagai data tidak konsisten.

Paket rubrik menampilkan diagnosis, penjelasan, evidence dan penolakan proposal secara terpisah,
tanpa membuka kandidat mentah atau varian. Diagnosis tidak otomatis mendapat seluruh skor nol
hanya karena proposal ditolak; dimensi perbaikan dinilai dari informasi yang tersedia, dengan
commands kosong dan alasan penolakan terlihat. Input lama tetap didukung, tetapi job failed pada
pilot lama tidak direkonstruksi menjadi diagnosis benar. Gunakan folder baru untuk pilot ulang.

Validasi offline: 650 tes dan 65 subtest lulus pada `tests/`, `host1/live_api/` dan
`host1/reasoning_agent/`. Cakupan mencakup JSONL runner-ke-evaluator, proyeksi Job strict,
penolakan schema/metadata tidak konsisten, evidence hash/reference, dan regresi replay.
Capture, model, router dan server memakai fixture/transport sintetis; HTTP uji pada port
acak terpisah dari API produksi. Ini bukan hasil pilot live atau klaim kenaikan akurasi model.
Aktivasi versi API baru dilakukan terpisah setelah review dan koordinasi dengan pengelola runner.
