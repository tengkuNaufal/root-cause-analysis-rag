# Profil observasi MTU — tahap replay sintetis

Profil `reasoning_agent.mtu` berdiri terpisah dari profil administratif DOWN. Jalur lama tetap menolak MTU mismatch; tidak ada perluasan diam-diam izin diagnosis atau eksekusi.

Scope tahap ini: membandingkan nilai MTU yang tercatat pada dua interface link fokus dalam satu sampai tiga snapshot tersusun waktu. Admin/carrier harus UP, sumber lengkap, identitas link/endpoint konsisten dan timestamp meningkat. MTU harus integer positif dalam rentang uint16; boolean bukan integer MTU yang sah. Snapshot, graf dan citation dokumentasi direvalidasi dengan pemeriksaan sumber yang ada.

Fase dipilih LLM dari current_relation dan earlier_relations (EQUAL/UNEQUAL), serta coverage complete/partial. Relasi dihitung controller dari pasangan integer terverifikasi; angka asli dan citation tetap ada dalam audit/kontrak. Semua empat label selalu tersedia; expected label, nama file, node dan citation tidak masuk prompt. Controller membandingkan fase model dengan evidence setelah inferensi. Jawaban salah tetap abstain, tidak diganti dengan label yang benar. Nilai observasi, perbandingan angka dan penjelasan/citation berasal dari controller, bukan ekstraksi, aritmetika atau narasi bebas model. Percobaan angka saja dan array boolean disimpan terpisah; perbaikan ini tidak boleh disebut kemampuan LLM membandingkan MTU sendiri.

- baseline: semua sampel yang diberikan menunjukkan MTU sama dan cakupan urutan tersebut dinyatakan lengkap.
- fault: pasangan terbaru berbeda, termasuk ketika peer tetap sehat. Label ini berarti mismatch teramati dalam profil ini, bukan fault routing yang sudah dibuktikan.
- recovered: pasangan terbaru sama setelah sampel mismatch terlihat. Ini pemulihan kesetaraan nilai, bukan bukti perintah perbaikan berhasil.
- undetermined: pasangan terbaru sama, mismatch sebelumnya tidak terlihat dan history yang diberikan parsial.

Tidak ada MTU yang direkomendasikan atau endpoint yang dinyatakan salah konfigurasinya hanya karena angkanya lebih kecil. MTU sama-sama 1400 bukan mismatch, dan latest mismatch tetap terdeteksi walaupun history parsial.

Referensi OpenConfig leaf MTU diambil dari arsip primer lokal yang hash-nya cocok dengan manifest. Ini definisi umum, bukan bukti knob live, pemetaan sempurna byte layer Ethernet/Linux, atau syarat bahwa kedua perangkat mesti menggunakan nilai tertentu. Profile belum menyimpulkan kegagalan OSPF akibat MTU, masalah PMTUD/BGP atau sebab packet loss. Untuk klaim tersebut diperlukan evidence khusus tambahan, termasuk konfigurasi yang relevan dan gejala yang membedakan penyebab lain.

## Menjalankan replay

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.replay_mtu prepare \
  data/host1/mtu-replay/nama-run-baru
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.replay_mtu evaluate \
  data/host1/mtu-replay/nama-run-baru
```

Folder harus baru. Generator menyalin baseline UP L12/L35 ke folder fixture, mengubah MTU secara sintetis 1500/1500 → 1400/1500 → 1500/1500 dan memakai urutan timestamp sumber yang sesuai. Node log lama dihapus pada salinan agar log administratif DOWN tidak disalahgunakan sebagai bukti MTU. Snapshot/graf salinan di-hash dan bundle dibangun ulang; seluruh original tetap dipertahankan. Semua fixture memiliki provenance.json dengan synthetic=true dan collector_measurement=false.

Manifest kasus, label, hash fixture/sumber/kode dibekukan sebelum evaluasi. Pemeriksaan kode dilakukan per kasus; fixture/sumber diperiksa sebelum dan sesudah suite. Kasus parsial memakai sampel terakhir saja. Dua link memakai pola angka yang sama, sehingga bukan delapan input reasoning independen.

Agent satu urutan dapat dipanggil tanpa evaluator:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.mtu \
  --sequence data/host1/mtu-replay/nama-run-baru/L12-fault.json \
  --output data/host1/mtu-replay/analisis-baru
```

Mode default replay. `--mode live` hanya memberlakukan freshness pada sampel terbaru; sampel sebelumnya tetap historis. Ia tidak mengambil telemetry baru.

Output menyimpan Request, view terpilih, gate sumber, budget, request/response model asli, raw phase, kontrak dan audit. Setiap klaim angka mengutip telemetry endpoint dan snapshot tepat; state peer/physical mengutip graf. H1 adalah graf urutan input buatan controller yang mengikat manifest/history_complete, bukan jaminan collector atas seluruh riwayat jaringan. D1 adalah definisi MTU. Kontrak dan klaim dirender terbatas lalu diperiksa ulang; semua patch kosong, diagnosis_allowed/execution_allowed=false. Tidak ada executor.
