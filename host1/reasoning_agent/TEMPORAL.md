# Klasifikasi fase oleh LLM — tanpa substitusi keputusan sehat

Pembaruan binding endpoint: ekstraktor default kini `bound`, dengan dua panggilan endpoint dan satu konteks sebelum panggilan fase. Identitas source diikat controller; nilai observasi tetap disalin model dan diverifikasi. Strategi dua panggilan lama tersedia lewat `--extractor grouped`. Baca [Binding endpoint](TEMPORAL.md#binding-endpoint); penjelasan tahap logis di bawah tetap berlaku, tetapi bukan lagi satu panggilan ekstraksi global pada mode default.

Jalur `reasoning_agent.temporal` selalu memanggil Ollama untuk input yang lolos gate, termasuk state sehat. Jalur hybrid pada rca.py tetap tersedia dan tidak diubah. Controller memvalidasi sumber, fakta dan jawaban; ia tidak memilih fase yang benar untuk mengganti prediksi model yang salah.

Tahap pertama meminta LLM mengekstrak node admin/carrier DOWN, dua string state peer, physical state, cakupan riwayat, dan urutan event menurut timestamp. Input berupa fakta JSON bertipe, dipisahkan antara current dan history. Ekstraksi model dibandingkan dengan sumber; kesalahan menyebabkan abstain, bukan dikoreksi. Stage kedua hanya menerima ekstraksi model yang lolos pemeriksaan.

Tahap kedua hanya memilih phase dengan skema datar dan contoh generik bernama X:if0. Contoh baseline dan recovery menampilkan kedua jenis state peer agar protokol tidak menjadi shortcut label. Semua label tetap tersedia pada setiap kasus. Model tidak menerima expected label/target evaluator atau nama fase dari path. Metadata current dan target kemudian dipetakan dari fase yang dipilih model serta node admin DOWN hasil ekstraksi model. Citation diikat controller ke sumber yang sudah diverifikasi dengan citation_origin yang eksplisit; bukan skor kemampuan model menghasilkan citation. Teks penjelasan memakai template controller dengan explanation_origin; ini bukan klaim bahwa model menghasilkan penjelasan bebas yang berkualitas. Model tidak diberi field untuk mengarang pelaku/konfigurasi yang tak diamati.

Definisi fase dibatasi oleh observasi yang tersedia:

- fault: kondisi fault saat snapshot, dengan target operasional administratif DOWN yang didukung.
- baseline: sehat saat snapshot dan tidak ada event DOWN/UP pada ringkasan riwayat lengkap yang disediakan. Ini bukan bukti bahwa jaringan tidak pernah mengalami fault di luar window.
- recovered: sehat saat snapshot, dengan event DOWN yang diikuti UP pada riwayat yang diberikan. Urutan timestamp digunakan, bukan urutan baris tampilan.
- undetermined: sehat saat snapshot tetapi riwayat sengaja tidak lengkap, sehingga baseline dan pemulihan tidak dapat dibedakan. Jangan menebak label dari nama file.

Evidence tetap bersumber dari bundle yang hash/citation/pointer-nya diperiksa gate link-rca-1.0. D1 dokumentasi tetap diverifikasi dan disimpan dalam kontrak; isi mekanisme fault tidak diulang dalam prompt klasifikasi fase karena tidak membuktikan keadaan saat ini. Keputusan fase memakai interface, graf/session dan riwayat terverifikasi. History lengkap berarti ringkasan transisi fokus dari bundle yang tersedia, bukan jaminan semua event jaringan nyata telah tertangkap.

Setiap panggilan memiliki konteks2048, cadangan keluaran256 dan overhead64, dengan batas atas byte UTF-8 sebelum inferensi. Respons terpotong, ekstraksi salah, fase yang bertentangan dengan evidence atau citation yang kurang/palsu ditolak. Gate dijalankan ulang setelah dua panggilan. Response resmi tetap confidence=null, proposed_patch=[], execution_allowed=false. Tidak ada executor, perubahan router atau fault baru.

Dari root proyek dalam WSL NetworkLab dengan Ollama aktif:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.temporal \
  --bundle data/host1/evidence-retrieval/replay-final-20261119/L12-restored.json \
  --mode replay --output data/host1/llm-temporal/contoh-baru
```

Pilih direktori baru. Artifact penting: input-contract.json, visible-evidence.json, observation-request/response.json, raw-observations.json, observation-budget.json, reasoning-input.json, ollama-request/response.json, raw-phase.json, combined-model-prediction.json, budget.json, gate-before/after.json, output-contract.json dan audit.json. Fase mentah dan metadata gabungan tidak ditimpa oleh keputusan validasi. raw_phase_correct pada ringkasan menilai fase mentah, raw_correct menilai gabungan dua keluaran model beserta metadata target, accepted menilai kontrak/citation/gate. model_calls menghitung kasus yang memanggil model; llm_requests menghitung panggilan tahap aktual.

Pengujian:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m unittest reasoning_agent.test_temporal -v
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.freeze_temporal_cases data/host1/llm-temporal/run-baru
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.evaluate_temporal data/host1/llm-temporal/run-baru \
  --stage development --label dev-v1
```

Enam kasus lama dipakai untuk pengembangan. Dua belas perturbasi presentasi/visibilitas dibekukan sebelum pengembangan dan dijalankan sekali setelah kode dibekukan melalui --stage variations. Fingerprint implementasi diperiksa selama evaluasi. Variasi ini adalah rancangan assistant atas trace lama, bukan fault jaringan independen atau label manusia. Bila hasil variasi dipakai untuk tuning, set itu telah menjadi data pengembangan; jangan mengklaimnya sebagai held-out baru.


## Binding endpoint

Ekstraktor default temporal sekarang `bound`. Identitas endpoint berasal dari satu baris source yang telah diverifikasi, bukan dipilih LLM dari daftar node. Setiap endpoint dikirim sendiri dengan node, admin_up, carrier_up dan peer_state. Citation ID disimpan pada binding controller dan tidak dikirim ke prompt ekstraksi.

Model hanya menyalin tiga nilai observasi. Boolean tidak memakai const/enum yang memaksa jawaban benar; salah salin tetap ditolak. Node/ref tidak boleh ditambahkan sebagai field respons model. Karena satu respons terikat ke satu source row, boolean yang benar tidak dapat dipasangkan melalui indeks daftar yang berbeda.

Setelah dua endpoint valid, panggilan terpisah menyalin physical/history dan mengurutkan event. ObservationDraft dirakit dari **nilai model** dan identitas source milik controller, lalu diperiksa ulang terhadap semua sumber. Daftar endpoint/state dinormalisasi urutannya hanya sesudah validasi. Langkah ini tidak mengubah boolean salah atau memilih fase. Panggilan terakhir tetap meminta LLM memilih fase; tidak ada fallback hasil sehat controller.

Asal metadata harus dibedakan: identitas node, citation dan template penjelasan milik controller; nilai observasi dan fase berasal dari model. Ini perbaikan binding program, bukan bukti LLM telah belajar memetakan identitas arbitrer. Model tetap dapat salah menyalin nilai; abstention dipertahankan.

Biaya normal menjadi empat panggilan per kasus: dua endpoint, satu konteks history/physical, satu fase. Ekstraktor grouped lama tetap tersedia dengan dua panggilan, untuk pembanding yang jujur. Request grouped pada kontrol native diuji identik dengan arsip sebelum perubahan.

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.temporal \
  --bundle data/host1/evidence-retrieval/replay-final-20261119/L35-down.json \
  --extractor bound --mode replay --output data/host1/endpoint-mapping/contoh-baru
```

Pilih output baru. `--extractor grouped` menjalankan strategi lama. Gate evidence, freshness live, budget per panggilan, validasi fakta/kontrak dan larangan eksekusi tetap berlaku.

Artifact baru: endpoint-1/2-binding.json, endpoint-1/2-request/response/raw/budget.json, history-context-request/response/raw/budget.json, endpoint-bindings.json, raw-observations.json (agregat nilai model + identitas controller), kemudian artifact fase dan kontrak biasa. Respons model asli selalu disimpan; tidak diganti bila salah.

Uji faktor dibekukan oleh freeze_endpoint_cases.py: dua sumber fault L12/L35 × urutan normal/terbalik × citation native/opaque baru. Dalam tiap link, pemetaan ID baru sama pada kedua urutan, sehingga hanya satu faktor berubah pada perbandingan cell. Dua cell normal/native adalah kontrol lama; enam cell lainnya layout baru. Empat regresi sehat memakai ID baru dan endpoint terbalik. Semua masih memakai dua trace fault lama, bukan fault independen.

Kode kandidat dibekukan sebelum pengujian paired. Strategi grouped dan bound dijalankan pada matriks dan urutan kasus yang sama. Nilai seed/temp/model/context tetap sama, namun satu run per cell bukan eksperimen statistik umum. ID tidak memengaruhi prompt bound secara desain; kesetaraan input per-node diuji terpisah dari keberhasilan LLM.


## Uji negatif dan history parsial

Evaluator ini menguji batas pipeline temporal `bound`, tanpa mengubah router atau menjalankan usulan CLI. Semua perubahan evidence dilakukan pada salinan di folder run; provenance mencatat bundle serta input asli. Data sintetis bukan hasil collector atau fault live.

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.evaluate_negative prepare \
  data/host1/negative-partial/nama-run-baru
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.evaluate_negative evaluate \
  data/host1/negative-partial/nama-run-baru
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.audit_negative \
  data/host1/negative-partial/nama-run-baru
```

Gunakan folder baru. `prepare` membekukan manifest kasus, label evaluator, hash bundle asli dan kode sebelum inferensi. Mengubah kode setelah prepare akan menghentikan evaluasi. Jangan menimpa percobaan lama atau menyebut variasi yang sudah terbuka sebagai test baru.

Ada sepuluh negatif per link L12/L35:

- Status pengumpulan source gagal dan snapshot parsial.
- Telemetry protokol sehat bertentangan dengan interface DOWN.
- Carrier DOWN ketika kedua endpoint admin UP, di luar profil RCA sempit saat ini.
- Log pendukung hilang serta nilai admin interface tidak diketahui.
- Citation dokumentasi rusak, hash snapshot salah, dan bundle graf berbeda dari sumbernya.
- Snapshot historis yang diminta melalui mode live, sehingga freshness harus menolak.

Enam kategori pertama membangun ulang bundle dari salinan graph/snapshot dengan hash serta pointer valid. Penolakan harus mencapai pemeriksaan completeness/state/log, bukan sekadar mismatch hash. Tiga kategori korupsi sengaja gagal pada pemeriksaan provenance. Stale-live memakai sumber asli, tanpa mengumpulkan snapshot atau memanggil router.

Enam layout history parsial menggabungkan pemotongan history dengan ID baru, urutan endpoint/event terbalik dan dokumentasi di akhir. Sumbernya baseline atau pemulihan tersimpan; current tetap sehat, tetapi fase baseline versus recovered tidak dapat dipastikan dari history yang diberikan. Expected phase tidak masuk prompt. Hasil yang diterima harus berupa `undetermined` mentah dari model dan lolos kontrak; sekadar error/abstain model tidak dihitung sebagai keberhasilan kategori ini.

Untuk negatif sumber, keberhasilan memerlukan abstain sebelum model dipanggil dan alasan gate yang sesuai. Ini membuktikan guard controller, bukan kemampuan model menolak konflik. Semua respons harus `execution_allowed=false` dan patch kosong.

`evaluation/summary.json` memisahkan kedua kategori. Post-audit memeriksa kontrak, binding, nilai endpoint mentah, observations agregat, fase mentah dan hash kode/data. Laporan milestone: [VALIDATION.md](../../docs/host1/VALIDATION.md).


## Validasi penjelasan

Evaluator memeriksa delapan run temporal tersimpan: baseline, fault dan pemulihan L12/L35, ditambah dua history parsial. Dua teks LLM lama juga dibaca ulang untuk review kualitatif. Tidak ada inferensi baru, command router atau perubahan pada jalur inferensi temporal.

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.evaluate_explanations \
  data/host1/explanation-quality/nama-folder-baru
private/.venv-retriever-wsl/bin/python scripts/host1.py -m unittest \
  reasoning_agent.test_explanation reasoning_agent.test_endpoint_mapping
```

Folder output harus baru. Lihat JSON untuk klaim terstruktur, MD untuk penjelasan yang bisa dibaca, `summary.json` untuk hasil, dan `legacy-prose-review.json` untuk teks asli serta keterbatasannya. Evaluator membekukan hash kode/input sebelum pemeriksaan dan memastikan tidak berubah selama evaluasi.

`explanation.load_run` menjalankan ulang gate sumber, membangun ulang Request dan visible view, memeriksa observations model, mencocokkan fase dengan respons mentah LLM, serta memvalidasi ulang kontrak tersimpan. Tidak mengubah jawaban lama atau menggantinya dengan jawaban yang dianggap lebih baik.

Laporan baru berasal dari controller dan menggunakan vocabulary klaim terbatas:

- Kondisi admin/carrier per interface → citation telemetry endpoint tersebut.
- State physical dan peer → citation graf yang sudah dicocokkan dengan snapshot sumber.
- Transisi historis beserta timestamp → citation log terkait, bukan bukti bahwa fault masih aktif.
- Fase → observasi saat ini dan history/coverage view; recovered juga memerlukan log DOWN/UP.
- Kondisi administratif DOWN terdekat → telemetry endpoint DOWN saja.
- Mekanisme umum → dokumentasi, tanpa menganggapnya bukti konfigurasi aktif atau pelaku.

`V1` adalah citation audit untuk `/history` pada visible-evidence.json. Ia menjelaskan kelengkapan atau pemotongan input yang diberikan, bukan sumber telemetry baru. Klaim baseline dibatasi pada view yang dinyatakan lengkap; tidak membuktikan tidak pernah ada fault. History parsial menghasilkan undetermined meskipun current dapat diketahui sehat.

Validasi memeriksa nilai, teks template, role, subject, timestamp dan citation tepat untuk setiap klaim; ID yang valid tetapi salah sumber tetap ditolak. Teks bebas yang belum didukung tidak dapat memperoleh persetujuan hanya dengan menempelkan citation valid. Root cause awal tetap `not_established`; kondisi DOWN, kehilangan carrier dan perubahan peer tidak membuktikan aktor, perintah pemicu atau kerusakan hardware.

Ini validasi laporan deterministik dengan klaim terbatas, bukan general semantic entailment, penilaian manusia independen atau peningkatan kemampuan LLM menulis penjelasan bebas. Laporan baru disimpan sebagai artefak review terpisah; respons agent lama dipertahankan. Diagnosis dan eksekusi tetap dilarang, patch kosong.
