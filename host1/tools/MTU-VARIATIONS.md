# Variasi nilai dan urutan endpoint pada agent MTU beku

Harness `mtu_variations.py` dan auditor `audit_mtu_variations.py` tidak mengubah agent production. Pembekuan awal mencatat seluruh Python existing pada reasoning_agent, knowledge dan agent_contract, profil inferensi serta manifest sumber. Total pada run pertama: 52 file. Hash diperiksa sebelum pembuatan fixture, sebelum setiap kasus dan setelah evaluasi.

Run pertama: `data/host1/mtu-variations/20261120T143910Z/`. `code-before.json` dibuat sebelum penulisan harness atau fixture baru. Harness memiliki hash tersendiri di preregistered.json dan tidak boleh diubah setelah prepare.

Untuk mengulang dengan **versi agent beku yang sama**, gunakan folder baru dan salin code-before.json dari run tersebut. Pemeriksaan akan menolak jika kode production sudah berubah. Jangan mengganti hash agar kandidat yang berbeda tampak sama.

```bash
mkdir -p data/host1/mtu-variations/nama-baru
cp data/host1/mtu-variations/20261120T143910Z/code-before.json \
  data/host1/mtu-variations/nama-baru/code-before.json
private/.venv-retriever-wsl/bin/python host1/tools/mtu_variations.py prepare \
  data/host1/mtu-variations/nama-baru
private/.venv-retriever-wsl/bin/python host1/tools/audit_mtu_variations.py \
  data/host1/mtu-variations/nama-baru
private/.venv-retriever-wsl/bin/python host1/tools/mtu_variations.py evaluate \
  data/host1/mtu-variations/nama-baru
private/.venv-retriever-wsl/bin/python host1/tools/audit_mtu_variations.py \
  data/host1/mtu-variations/nama-baru --post
```

Pola kasus pada harness ini kini telah terbuka. Mengulangnya bukan pengujian variasi baru atau held-out baru.

Desain: dua link × dua keluarga angka × dua urutan inventory × dua penempatan nilai = 16 kasus fault. Nilai hanya ditukar antar-node jika faktor swapped=true; membalik inventory saja tidak menukar nilainya. Salinan inventory/snapshot/graf disesuaikan konsisten, di-hash dan bundle direkonstruksi. Sumber asli tidak diubah.

L12 memakai 1492/9000 dan 1500/1501; L35 memakai 1280/9216 dan 8999/9000. Kontrol baseline/recovered/partial memakai keluarga wide dan kedua urutan. Nilai sama yang sehat dalam profil ini berarti kesetaraan saja, bukan MTU sesuai kebijakan atau rekomendasi nilai. Negatif menambahkan MTU nol, lebih besar uint16, string dan manipulasi nilai bundle yang tidak sesuai sumber.

Auditor preflight memeriksa urutan endpoint yang benar-benar terbentuk, assignment nilai berdasarkan node, serta peer/physical tetap sehat. Auditor hasil memeriksa pointer snapshot, isi reference, setiap klaim numerik dan citation endpointnya. Dua salinan klaim palsu menggunakan ID valid tetapi endpoint salah atau dokumentasi untuk nilai live: kontrak struktural bisa menerima ID tersebut, sedangkan audit numerik wajib menolaknya. Salinan ini tidak menimpa hasil asli dan bukan klaim bahwa production contract sendiri menolak semantic misattribution.

Agent mengurutkan endpoint dan menghitung EQUAL/UNEQUAL sebelum model. Karena itu variasi angka/urutan sengaja tidak terlihat oleh LLM. Kesamaan hash request aktual dicatat; metrik ini menguji ketahanan pemetaan pipeline, bukan aritmetika LLM, general semantic entailment atau sebab gangguan routing. Tidak ada fault live, patch atau executor.

Hasil lengkap pertama berada pada data/host1/mtu-variations/20261120T144600Z-audit-fixed/. Run awal menyimpan persiapan, preflight dan percobaan parsial sebelum perbaikan auditor pointer array. Fixture/label dan production tidak berubah; parent_registration mengikat kedua run. Lihat [laporan hasil](../../docs/host1/VALIDATION.md).
