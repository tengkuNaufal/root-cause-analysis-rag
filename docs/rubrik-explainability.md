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
python -m rca.explain sample results/runs/full.jsonl --raters ashkar fayyaz naufal
# isi kolom skor di results/explain/penilaian_<nama>.csv
python -m rca.explain aggregate results/explain
```

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
