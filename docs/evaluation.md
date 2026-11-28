# Evaluasi hasil dan pemilihan attempt

Evaluator bekerja offline pada JSONL. Satu cell eksperimen adalah `(fault_id, variant, trial)`;
`plan_order` mengikat cell tersebut pada jadwal yang sama. Jangan mencampur sesi benchmark,
smoke/demo, hasil sintetis, dan pilot dalam satu input evaluasi resmi.

Secara default cell duplikat ditolak. Ini mencegah `--retry` pada runner membuat denominator
bertambah tanpa keputusan eksplisit. Setelah kelompok menyepakati kebijakan, pilih:

```bash
python -m rca.evaluator data/host2/pilot/results.jsonl --out results/eval/pilot --attempt-policy first
```

`first` memilih nomor attempt terendah; `last` memilih tertinggi. Keduanya mengabaikan urutan
baris berkas dan tidak otomatis memilih hasil yang berhasil. Duplikasi tanpa nomor attempt,
nomor attempt sama, atau binding jadwal bertentangan tetap ditolak. Jangan menggunakan `last`
untuk menghapus kegagalan tanpa melaporkan kebijakan dan alasan retry.

`selection.json` mencatat kebijakan, jumlah input/terpilih/dikecualikan, identitas attempt yang
dikecualikan, hash input dan hash katalog. JSONL asli tetap disimpan. Hash katalog diperiksa
pada semua baris, termasuk attempt yang tidak dipilih; input lama tanpa hash masih didukung.
`--catalog` memilih katalog eksplisit, termasuk saat mengulang evaluasi arsip lama.

Kelulusan tes offline tidak membuktikan baseline, koneksi dua host, atau latensi live sehat.

Diagnosis yang didukung dapat memiliki proposal kosong karena penolakan API. Evaluator
memisahkan akurasi diagnosis, approval perintah, penolakan lint/guard, dan pemulihan. Semantik
catatan wire, JSONL runner dan metriknya dijelaskan di
[diagnosis dan penolakan proposal](host1/PROPOSAL-OUTCOME.md).

## Audit sitasi

Semua sitasi di assessment, claims, dan proposed_patch diperiksa, termasuk yang tidak disalin
ke daftar assessment. Pada respons live dengan `provenance.model_evidence_ids`, sitasi harus
ada pada input model **dan** manifest. Daftar input model kosong berarti tidak ada evidence
yang dapat dikutip; daftar tersebut tidak diganti dengan seluruh manifest.

Data live lama tanpa field tersebut tetap diterima dengan scope `manifest_legacy`, dicatat
pada runs_scored.csv dan diberi peringatan pada laporan. Varian regex memakai manifest lokalnya;
bentuk legacy memakai daftar evidence tersedia. `halluc_evidence_ids` mencatat sitasi bermasalah.
Metrik halusinasi adalah proxy ID dan topologi perintah, bukan pemeriksaan seluruh fakta teks.
Kontrak API dan proses layanan tidak berubah oleh audit offline ini.

## Penilaian penjelasan

[Sampler rubrik](rubrik-explainability.md) memakai `checked_catalog` dan `select_attempts` yang
sama, termasuk pemeriksaan hash attempt yang dikecualikan. Bundle evidence diverifikasi dari
arsip lokal dan diberi nama anonim; kunci privat menghubungkan sampel dengan run asli dan hash
input. Default scope tiga agen dapat diperluas ke regex secara eksplisit.

Tidak ada perubahan runner, katalog, prompt, kontrak wire API atau konfigurasi lab dalam perbaikan
ini. Untuk evaluasi resmi tetap bekukan kode/model/options, policy linter, katalog, topologi dan
jadwal; pisahkan data pilot dari benchmark. Pemilihan first/last adalah keputusan analisis yang
harus dilaporkan, bukan bukti kegagalan attempt lain boleh dihapus.
