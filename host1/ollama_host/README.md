# Ollama lokal — Host 1

Runtime native Linux berada di `private/runtime/ollama/dist`, model di `private/runtime/ollama/models`, dan home proses di `private/runtime/ollama/home`. Seluruh runtime diabaikan Git: home proses dapat memuat private key Ollama dan tidak boleh disalin ke bukti/dokumentasi. Tidak memakai Docker Desktop atau distro Ubuntu lama.

Dari root proyek di WSL NetworkLab, jalankan layanan pada terminal yang dipertahankan:

```bash
bash host1/ollama_host/serve.sh
```

Periksa dulu `curl -fsS http://127.0.0.1:11434/api/version` agar tidak memulai layanan kedua. Binding localhost, konteks default 2048, satu request/model aktif, keep-alive lima menit. Model dilepas dari RAM/VRAM sesudah idle; file model tetap tersimpan. Tidak ada auto-start Windows/systemd yang dipasang.

Terminal NetworkLab lain dari root proyek:

```bash
private/runtime/ollama/dist/bin/ollama list
private/runtime/ollama/dist/bin/ollama ps
python3 host1/ollama_host/smoke_test.py data/host1/ollama-setup/SMOKE-BARU
```

Gunakan direktori keluaran baru. Smoke test memeriksa metadata model `llama3.1:8b` Q4_K_M dan dua inferensi JSON sintetis cold/warm. Istilah cold berarti request pertama dalam run; untuk benar-benar mengukur load awal pastikan model belum resident (lihat `/api/ps`). Output mencatat wall time, load duration dan token/s. Ini bukan pengujian reasoning jaringan, kualitas RCA atau target perbaikan MTU <10 detik. Tidak ada perintah hasil model yang dieksekusi.

Profil awal terukur ada di `inference-profile.json`: `num_gpu=20`, `num_ctx=2048`, temperature0, seed42, output64token untuk smoke. Smoke memakai opsi profil ini secara default; `--num-gpu` dapat mengganti untuk perbandingan terbatas. Klien API lain harus meneruskan `options` tersebut secara eksplisit; serve.sh sendiri tidak memaksa jumlah layerGPU. Cold/warm pertama dengan offload otomatis lulus tetapi lambat (243,05/15,37detik); perbandingan20layer lulus dengan67,99/0,65detik. Ini sampel tunggal tiap kondisi, bukan benchmark terkontrol. Pilih/batasi evidence dan anggaran output baru sebelum reasoning; jangan memakai batas64token untuk jawaban agent lengkap.

Instalasi sesi awal menggunakan rilis resmi terpilih pada metadata `data/host1/ollama-setup/<run>/release.json`. `verify_archive.py` mencocokkan ukuran dan SHA-256 upstream sebelum ekstraksi; direktori dist harus belum ada. Decompressor zstandard berada pada target terpisah `private/runtime/ollama/python-deps`, tidak mengubah dependency retriever. Jangan mengunduh/rebuild ulang untuk pemakaian biasa.

Layanan dapat dihentikan dengan Ctrl+C pada terminal foreground pemiliknya. Bila layanan dimulai background dalam sesi setup, identitas PID dan log ada di direktori bukti run. Periksa command/PID aktual sebelum menghentikan proses; PID lama dapat dipakai ulang. Menutup atau menghentikan WSL juga menghentikan lab; pertahankan sesi NetworkLab selama eksperimen.

Dokumentasi primer: [Linux](https://docs.ollama.com/linux), [FAQ konfigurasi](https://docs.ollama.com/faq), [API generate](https://docs.ollama.com/api/generate), [model llama3.1:8b](https://ollama.com/library/llama3.1:8b).
