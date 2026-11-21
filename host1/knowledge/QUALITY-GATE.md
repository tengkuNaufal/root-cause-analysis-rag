# Quality gate dan abstention Host 1

Modul `host1/knowledge/quality_gate.py` bekerja tanpa Ollama, dependency baru atau perubahan index Chroma. Paket baru dari `knowledge.evidence` otomatis mendapat field `quality_gate`; paket lama dapat dinilai melalui CLI terpisah tanpa ditimpa.

## Arti keputusan

- `context_ready`: bukti dan setidaknya satu kutipan memenuhi pemeriksaan integritas serta aturan topik untuk intent yang diminta. Boleh ditinjau sebagai konteks.
- `abstain`: bukti kurang memadai, tidak cocok, tidak valid, basi untuk mode live, atau intent belum didukung. Alasan ada pada `reasons`; `accepted_citations` dikosongkan.
- `diagnosis_allowed=false` dan `execution_allowed=false` selalu berlaku, termasuk ketika context_ready. Gate bukan reasoning agent atau command linter.

Hasil menyertakan versi gate, intent, mode, usia snapshot, pemeriksaan setiap hit, citation yang lolos, alasan dan langkah berikutnya. `hit_checks.accepted` menandai kecocokan topik per hit; hanya `accepted_citations` tingkat paket yang boleh dipakai sebagai pilihan akhir. Satu citation rusak menyebabkan seluruh paket abstain meskipun hit lain cocok. Kutipan berulang antarkueri tetap dapat muncul; bukan sumber independen tambahan.

## Pemeriksaan evidence

Hash graf/snapshot/inventory/log diperiksa ulang, lalu konteks dibangun ulang melalui fungsi context yang ada dan dibandingkan dengan payload paket. Penghilangan/perubahan telemetry atau log dalam paket akan ditolak. Sumber interface, protokol terkait, dan routes untuk kedua endpoint harus tersedia dengan status ok, snapshot harus complete, state tidak boleh unknown. Physical down tanpa log berkorelasi juga menghasilkan abstention. Tidak adanya log pada baseline sehat tidak otomatis dianggap kekurangan.

Setiap citation dibandingkan dengan manifest sumber: platform, versi, content kind, URL dan hash. Teks, rentang baris, ID chunk, citation URL dan content hash harus sesuai sumber lokal. Skor cosine/BM25/RRF tidak dapat mengesampingkan pemeriksaan ini.

## Profil relevansi eksplisit versi 1.0

| Intent | Aturan topik |
|---|---|
| network_context | Dokumentasi CLI FRR, nama protokol fokus dalam isi kutipan, dan minimal dua kata topik: OSPF memakai neighbor/adjacen/interface; BGP memakai peer/neighbor/session |
| interface_mtu_definition | Schema OpenConfig yang memuat deklarasi leaf mtu |
| bgp_session_state | Fokus link BGP dan schema OpenConfig yang memuat deklarasi leaf session-state |
| Lainnya | Abstain: intent tidak didukung/celah corpus |

Prefix identitas chunk tidak dihitung sebagai isi kutipan. Kata kunci ini adalah syarat topikal konservatif yang dapat diaudit, bukan pengukuran makna atau probabilitas kebenaran. Dokumentasi peer yang umum masih dapat lolos untuk network_context; ini tidak cukup untuk menjawab penyebab link down atau memilih fast-external-failover. Definisi MTU tidak sama dengan solusi MTU mismatch. Intent ospf_mtu_remediation sengaja tidak didukung sampai referensi dan validasinya memadai.

Builder otomatis memakai network_context bila tidak ada pertanyaan bebas. Jika memakai --question, builder abstain dengan intent unsupported_free_question: tidak menebak maksud pertanyaan atau mengklaim bahwa kutipan umum menjawabnya. CLI standalone menyediakan intent eksplisit untuk konteks yang cakupannya terbatas.

## Replay dan live

Mode default replay cocok untuk data historis: usia dihitung tetapi tidak membatalkan snapshot karena sudah lama. Mode ini tidak boleh digunakan sebagai izin tindakan live. Mode live menolak snapshot dengan usia negatif (masa depan) atau lebih dari 120 detik. Parameter fungsi max_age_seconds dapat diatur dalam rentang (0,3600]; ambang 120 detik adalah kebijakan awal, bukan hasil kalibrasi eksperimen. Snapshot tetap observasi tidak atomik.

Contoh dari root proyek (Windows python atau NetworkLab python3):

```bash
python3 scripts/host1.py -m knowledge.quality_gate \
  --bundle data/host1/evidence-retrieval/replay-final-20261119/L35-down.json \
  --intent network_context --mode replay \
  --output data/host1/quality-gate/my-replay.json
```

Ganti --mode live untuk memeriksa kesegaran terhadap waktu sekarang. Pilih output baru; CLI menolak overwrite. Exit 0 berarti laporan berhasil dibuat, bukan berarti konteks disetujui: pemanggil wajib membaca decision. Error membaca JSON/file input tetap merupakan kegagalan CLI, bukan persetujuan.

Pengujian:

```bash
python3 scripts/host1.py -m knowledge.evaluate_gate data/host1/quality-gate/new-evaluation
python3 scripts/host1.py -m unittest knowledge.test_quality_gate knowledge.test_evidence -v
```

## Batas dan tahap berikutnya

Gate tidak membuktikan sebab-akibat, tidak menjamin seluruh log sebelum power loss tersedia, dan bukan validasi semantik setiap klaim. Masih perlu evaluasi relevansi held-out dengan label manusia, penanganan pertanyaan yang lebih luas, pemeriksaan dukungan klaim, dan referensi OSPF MTU. Tidak ada setup Ollama, fault injection, atau perubahan router pada milestone ini. Laporan: ../docs/VALIDATION.md.

Evaluasi query baru selesai: baca docs/host1/VALIDATION.md (dari host1/knowledge/, gunakan ../docs/). Gate v1 masih dapat menerima dokumen BGP untuk pertanyaan tidak didukung jika intent eksplisit network_context; context_ready bukan izin menjawab pertanyaan. Hasil12kasus:anchor6/8,kesepakatan gate8/12. Jangan setup Ollama dulu; prioritaskan pengikatan query–intent/dukungan klaim.

Update v2: gate kini memeriksa persyaratan klaim dari pertanyaan terbatas, dengan alasan dan citation; lihat docs/host1/VALIDATION.md (dari host1/knowledge/, ../docs/). CLI mendukung --question; builder meneruskannya otomatis. Pernyataan lama bahwa semua pertanyaan bebas selalu ditolak berlaku untuk v1. Scope yang tidak dikenali tetap abstain. Regresi12kasus dan23tes lulus; bukan evaluasi held-out. Ollama belum disiapkan.

Update2.1 sebelum Ollama: compound request and describe ditolak; pertanyaan defaultMTUdiscovery dan artiACTIVE memiliki klaim tersendiri. Retriever melengkapi konteks leafYANG overlap dengan citation baru (lihat ../docs/VALIDATION.md). Aturan tetap terbatas, bukan general entailment.
