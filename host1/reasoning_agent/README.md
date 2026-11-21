# Integrasi reasoning Ollama — tahap tanpa eksekusi

Pengembangan RCA operasional link tersedia melalui profil terpisah: [RCA.md](RCA.md). Gate dokumentasi di bawah tetap berlaku untuk CLI adapter; gunakan CLI rca untuk hipotesis link-state yang cakupannya eksplisit.

Klasifikasi baseline/fault/recovery oleh LLM tanpa routing sehat controller tersedia pada [TEMPORAL.md](TEMPORAL.md). Jalur ini memisahkan ekstraksi fakta oleh model dan keputusan fase, dengan validasi sebelum/sesudah inferensi.

Adapter memakai evidence builder dan quality gate yang sudah ada; tidak mengubah corpus, ranking, gate atau kontrak agent. Seluruh output tetap usulan belum terverifikasi secara semantik. Tidak tersedia executor, shell tool atau akses perintah router dari adapter.

Alur:

1. Verifikasi ulang bundle, hash sumber, telemetry/graf/log, citation dan dukungan pertanyaan melalui gate. Abaikan keputusan gate tersimpan sebagai otoritas; hitung ulang. Mode live juga menegakkan usia snapshot, termasuk setelah inferensi.
2. Pilih kutipan yang memenuhi setiap persyaratan klaim. Simpan paragraf utuh beserta heading FRR terdekat agar istilah tidak kehilangan konteks, URL/rentang baris dan offset karakter. Tambahkan proyeksi dua interface endpoint, relasi fisik graf dan satu log terbaru bila tersedia. Tidak memakai label ground truth/fase eksperimen sebagai input.
3. Prune kandidat dokumentasi ke hit terpilih, lalu jalankan gate lagi. ID E1, E2, ... dalam prompt memetakan citation lengkap pada input-contract.json. Hash/path/locator tidak dibuang dari artefak audit; hanya tidak diulang di prompt.
4. Render framing Llama 3 secara eksplisit dan gunakan API generate raw=true. Batas atas byte UTF-8 seluruh prompt dipakai secara konservatif untuk model byte-BPE yang digest-nya dipin: prompt_upper_bound + 512 output + 64 cadangan harus <=2048. Ini bukan hitungan tokenizer eksak atau perkiraan chars/4. Bila tidak muat, abstain; jangan memotong citation atau teks diam-diam. Skema output dikirim sebagai grammar format, tidak ditempel sebagai teks prompt.
5. Panggil hanya model lokal dan digest terverifikasi, memakai profil num_gpu=20. Wire schema meminta AnswerDraft yang ketat: answer, evidence_ids dan missing_evidence. ID yang diizinkan hanya citation dokumentasi; model tidak menentukan metadata kontrak, patch atau execution flag. Output memperoleh cadangan 512 token, berbeda dari smoke setup 64 token.
6. Validasi AnswerDraft, lalu petakan teks jawaban secara verbatim ke kontrak Response: request_id milik controller, confidence null, patch kosong, execution false. Tolak respons terpotong, hitungan token tak sesuai anggaran, JSON/draf/kontrak invalid, reference ID tidak dikenal, atau citation non-dokumentasi untuk jawaban definisi. Jalankan gate lagi setelah inferensi. Kegagalan menghasilkan abstain controller; respons mentah ditahan sebagai bukti. Mapping ini bukan perbaikan teks model: isi jawaban dan IDs tidak diubah, dan tidak ada retry otomatis.

Gate sekarang hanya mendukung pertanyaan dokumentasi tertentu. Pertanyaan root cause/fix MTU tetap abstain sebelum model dipanggil. Status hypothesis dalam kontrak dipakai untuk jawaban dokumentasi tentatif pada tahap ini; diagnosis_allowed=false dan execution_allowed=false tetap berlaku. Mengutip sumber yang valid tidak membuktikan kebenaran semantik setiap kalimat. Tidak ada skor akurasi RCA yang dihasilkan oleh pengujian integrasi ini.

Dari root proyek di WSL NetworkLab dengan Ollama aktif:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.adapter \
  --bundle data/host1/reasoning-agent/20261120T111138Z/bundle-timers.json \
  --question 'Which BGP timer value is keepalive and which is hold time?' \
  --mode replay \
  --output data/host1/reasoning-agent/contoh-baru
```

Direktori output harus baru. Replay memakai data historis dan tidak mengklaim kondisi jaringan sekarang. Ganti mode live hanya dengan bundle baru yang lengkap dan segar. CLI exit0 berarti laporan berhasil dibuat; baca audit.status, audit.reason dan output-contract.json untuk mengetahui hasil sebenarnya.

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m unittest reasoning_agent.test_adapter -v
```

Artefak positif: gate-before/selected-gate/gate-after.json, input-contract.json, budget.json, prompt.txt, ollama-request/response.json, mapped-contract.json, output-contract.json, audit.json. Pada penolakan awal, hanya artefak yang sempat dibuat dan abstain controller tersedia. Controller tidak memerlukan layanan router aktif untuk replay.

Keterangan perangkat dari pengguna pada 20 November 2026: Genshin dibuka bersamaan dengan pengujian setup sebelumnya dan memakai VRAM. Latensi pada laporan setup tetap merupakan pengukuran dengan beban berbagi, bukan benchmark Ollama yang diisolasi. Pengukuran sebelum/sesudah yang terkontrol belum dilakukan; profil 20 layer dipertahankan agar tahap ini tidak mencampur perubahan runtime dan integrasi.

Profil MTU terpisah: baca [MTU.md](MTU.md) dan [hasil replay sintetis](../../docs/host1/VALIDATION.md). CLI reasoning_agent.mtu menerima urutan evidence terverifikasi; tahap ini hanya kesetaraan nilai MTU, belum diagnosis dampak routing atau eksekusi.

API replay lokal Host 1 tersedia melalui reasoning_agent.api. Baca [API.md](API.md) dan [hasil pengujian](../../docs/host1/VALIDATION.md). Input scenario_id terdaftar; hasil/evidence/citation/timing tersedia lewat HTTP loopback, tanpa eksekusi.
