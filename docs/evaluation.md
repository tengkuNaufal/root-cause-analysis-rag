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
