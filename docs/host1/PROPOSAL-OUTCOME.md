# Diagnosis dan penolakan proposal

Diagnosis dan perintah dinilai terpisah. Job completed dengan status hypothesis dapat
memiliki proposed_patch dan assessment.commands kosong ketika usulan perintah ditolak.
Router, kelas, confidence, claims, evidence dan penjelasan diagnosis tetap dipertahankan.

Tidak ada field wire atau perubahan versi live.v1-draft2. Field missing_evidence yang sudah
ada dapat membawa catatan controller berawalan `proposal_rejected:v1:` diikuti JSON:
version, status=rejected, stage=lint/guard, code, commands_sha256, candidate_count, policy_version.
Catatan ini adalah hasil validasi proposal, bukan pernyataan bahwa evidence diagnosis kurang.
Hash memakai JSON canonical atas proyeksi commands kandidat; kandidat mentah tidak diekspor.
Runner dan evaluator memakai decoder stdlib yang sama pada scripts/proposal_outcome.py.

Hanya penolakan policy yang dikenal yang dikonversi menjadi diagnosis tanpa proposal.
Diagnosis tanpa dukungan, binding/citation tidak valid, capture/freshness/hash gagal, schema
tidak valid dan exception internal tetap menyebabkan job gagal. Controller tidak membuat
perintah pengganti. proposal-validation.json lokal menyimpan kandidat dan alasan untuk audit.
Job tetap execution_allowed=false. Semua perubahan diuji offline sebelum aktivasi terkoordinasi.
