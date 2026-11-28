# Rubrik Explainability

Dipakai untuk menilai field `explanation` (bersama `evidence_ids` dan `commands`) pada jawaban agen.
Setiap dimensi diberi skor **0, 1, atau 2**, sehingga skor total 0–10.

## Sampel dan pembagian

- Menilai 450 penjelasan terlalu lama, jadi yang dinilai adalah **satu trial per fault per varian**
  yang dipilih acak (30 fault × 3 varian = **90 penjelasan**).
- Varian **disembunyikan** dari penilai (item diberi ID acak `X001`…) supaya penilaian tidak bias.
- 9 item pertama dinilai **ketiga anggota** untuk mengukur kesepakatan; sisanya (81) dibagi rata,
  sehingga tiap anggota menilai 9 + 27 = 36 item.
- Penilai boleh melihat ground truth (`gt_router`, `gt_class`) karena dimensi konsistensi dan
  perbaikan membutuhkannya, tetapi **jangan membuka `kunci_sampel.csv`** sebelum semua selesai.

```
python -m rca.explain sample results/runs/full.jsonl --raters ashkar fayyaz naufal --evidence-root private/arsip-live
# isi kolom skor di results/explain/penilaian_<nama>.csv
python -m rca.explain aggregate results/explain
```

### Input, retry dan evidence offline

Sampler dan evaluator numerik memakai validasi katalog serta pemilihan attempt yang sama;
lihat [panduan evaluasi](evaluation.md). Duplikasi cell ditolak secara default. Setelah kebijakan
kelompok disepakati, `--attempt-policy first` atau `last` harus sama pada kedua jalur. Gunakan
`--catalog` untuk katalog arsip tertentu; hash setiap baris diperiksa sebelum sampling.

Scope default adalah tiga varian agen (90 item bila semua 30 fault tersedia), sesuai rubrik di atas.
Untuk menyertakan pembanding regex secara eksplisit, gunakan
`--variants zero_shot text_rag graph_rag rule_based` (120 item bila lengkap). Untuk 120 item dengan
overlap 9, tiap penilai menerima 9 + 37 = 46 item. Sampler tidak mengklaim katalog lengkap bila input
baru berisi sebagian pilot: jumlah aktual dicatat dalam `selection.json`.

Untuk evidence live, simpan arsip job lengkap sebelum retensi server habis. Struktur yang dibaca
adalah `private/arsip-live/<job_id>/evidence-index.json` beserta JSON sumber yang dirujuk indeks,
misalnya `facts.json`, `documentation.json` atau `graph.json`. Ini adalah struktur output layanan
live yang sudah ada; sampler hanya membacanya, tanpa HTTP, Docker, Ollama, atau perubahan router.

```bash
python -m rca.explain sample data/host2/pilot/results.jsonl \
  --out results/explain --evidence-root private/arsip-live \
  --raters ashkar fayyaz naufal
```

Semua evidence yang dikutip diperiksa terhadap manifest, hash file sumber, JSON pointer dan isi
fragmen pada indeks. Arsip hilang atau tidak cocok menghentikan pembuatan paket, bukan menghasilkan
lembar grounding tanpa bukti. Regex memakai excerpt lokal yang tersimpan dalam respons, terikat ke
hash JSONL input; excerpt itu tidak diklaim memiliki hash sumber router asli. Run gagal/abstain tanpa
sitasi tetap dapat disampel dengan bundle kosong, agar kegagalan tidak dikeluarkan dari penilaian.

Bagikan kepada penilai CSV miliknya dan folder `evidence/`. Kolom `evidence_bundle` menunjuk JSON
ber-ID `X001`, berisi hanya ID evidence, jenis dan konten fragmen, tanpa identitas run, varian,
lokasi sumber, atau provenance tambahan. Perbedaan isi evidence antarvarian masih dapat memberi
petunjuk; anonimisasi label tidak menjamin penilai sama sekali tidak dapat menebak varian.

Simpan `kunci_sampel.csv` dan `selection.json` secara privat sampai penilaian selesai. Kunci memuat
request/job ID, plan_order, trial, attempt, hash baris/input/katalog/bundle dan hash sumber evidence.
`run_id` memakai request_id bila runner tidak menulis run_id; input legacy tanpa keduanya memakai
hash baris sebagai identitas. Folder output harus kosong sehingga penilaian yang sudah diisi tidak
tertindih. Paket ini adalah data lokal, bukan fixture yang ditambahkan ke Git; output default
`results/explain/` di-ignore.

Prompt agen saat ini membatasi penjelasan menjadi 12 kata. Tetap nilai memakai rubrik yang
disepakati; catat keterbatasan kelengkapan rantai kausal/justifikasi dan jangan melonggarkan rubrik
setelah melihat hasil. Perubahan prompt atau rubrik perlu disepakati sebelum benchmark resmi.

## Dimensi

| # | Dimensi (kolom CSV) | 0 | 1 | 2 |
|---|---|---|---|---|
| 1 | **Grounding evidence** (`grounding`) | Tidak menyebut evidence apa pun, atau menyebut fakta yang tidak ada di evidence (halusinasi). | Menyebut evidence secara umum ("log menunjukkan error") tanpa rincian atau ID. | Mengutip evidence spesifik (baris log, status neighbor, nilai MTU/timer, jumlah prefix) dan sesuai dengan `evidence_ids`. |
| 2 | **Rantai kausal** (`kausal`) | Langsung menyebut penyebab tanpa alasan, atau alasannya tidak logis. | Ada hubungan gejala → penyebab, tetapi ada langkah yang hilang. | Runtut: gejala yang teramati → mekanisme protokol (mis. DBD ditolak karena MTU) → akar masalah di router/interface tertentu. |
| 3 | **Konsistensi** (`konsistensi`) | Penjelasan bertentangan dengan `router`/`root_cause` atau dengan perintah yang diusulkan. | Sebagian konsisten (mis. kelas benar, tetapi router/interface yang dibahas berbeda dengan perintah). | Penjelasan, `router`, `root_cause`, dan `commands` saling cocok. |
| 4 | **Justifikasi perbaikan** (`perbaikan`) | Tidak menjelaskan mengapa perintah memperbaiki masalah. | Menyebut perintahnya tetapi tidak menjelaskan efeknya atau cara memverifikasinya. | Menjelaskan mengapa perintah memulihkan jaringan dan apa yang dicek sesudahnya (mis. neighbor Full, prefix diterima). |
| 5 | **Kejelasan** (`kejelasan`) | Sulit dipahami, terlalu panjang, atau penuh isi yang tidak relevan. | Dapat dipahami tetapi bertele-tele atau ada bagian yang tidak relevan. | Ringkas, jelas bagi operator jaringan, tanpa isi yang tidak relevan. |

## Aturan penilaian

1. Nilai penjelasan **sebagaimana adanya**. Diagnosis yang salah tetap bisa mendapat skor kejelasan tinggi,
   tetapi dimensi grounding dan kausal biasanya rendah karena tidak didukung evidence.
2. Kalau `explanation` kosong atau agen gagal menghasilkan JSON, beri 0 untuk semua dimensi.
3. Jika ragu antara dua skor, pilih yang lebih rendah dan tulis alasannya di kolom `catatan`.
4. Isi skor hanya dengan angka `0`, `1`, atau `2`; baris yang tidak lengkap dilewati saat agregasi.

## Contoh singkat (fault MTU di r1 eth1)

- **Skor 10:** "Neighbor r2 di eth1 tertahan di ExStart (ev-07) dan log r1 menyebut MTU 1500 dari
  neighbor lebih besar dari MTU eth1 1400 (ev-03). DBD ditolak sehingga adjacency tidak pernah Full.
  Mengembalikan MTU eth1 ke 1500 menyamakan kedua sisi; verifikasi dengan `show ip ospf neighbor` (Full)
  dan ping 1472 byte."
- **Skor 4:** "Ada masalah OSPF di r1, kemungkinan konfigurasi interface salah. Ubah MTU." (grounding 0,
  kausal 1, konsistensi 2, perbaikan 1, kejelasan 0–1)
