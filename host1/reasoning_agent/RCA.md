# RCA operasional link — tanpa eksekusi

Modul `rca.py` memakai profil eksplisit `link-rca-1.0` untuk hipotesis operasional dari interface, protokol, graf, log dan dokumentasi. Modul ini tidak mengubah gate pertanyaan dokumentasi lama dan tidak membuka pertanyaan RCA umum secara otomatis.

Profil memeriksa integritas sumber melalui assess_context yang sudah ada, termasuk kelengkapan, hash, pointer, citation dan usia snapshot untuk mode live. Syarat heuristik topik dokumen diganti dengan dukungan mekanisme dari sumber primer yang diverifikasi: RFC2328 Section9.3 untuk InterfaceDown/KillNbr, serta FRR bgp.rst untuk fast-external-failover. Semua kegagalan integritas lain tetap menyebabkan abstain. RFC berasal dari arsip supplemental yang sudah ada; tidak ada indexing ulang Chroma. Ini dukungan mekanisme deterministik dari sumber yang dipin, bukan klaim bahwa retrieval Chroma otomatis selalu menemukan sumber kausal yang tepat.

Dua konteks yang saat ini diterima:

- Kedua interface UP/carrier UP dengan dua adjacency OSPF FULL atau sesi BGP Established: boleh menganalisis tidak adanya fault saat observasi ini. Log DOWN dalam window adalah riwayat, bukan penentu keadaan sekarang.
- Tepat satu interface administratif DOWN, kedua carrier DOWN, graf link DOWN, kedua peer tidak sehat, MTU sama dan diketahui, serta log transisi DOWN cocok pada kedua endpoint/interface/peer: boleh mengusulkan hipotesis hilangnya adjacency/sesi akibat interface administratif DOWN. Target harus sesuai observasi, bukan semata sisi yang mengeluarkan log.

Carrier DOWN dengan kedua admin UP, state parsial/kontradiktif, MTU mismatch, sumber hilang, data basi atau log peer yang tidak cocok berada di luar profil dan menghasilkan abstain. Profil ini tidak menentukan pelaku, perintah injection, kabel rusak, BGP timer mismatch atau diagnosis MTU.

Seleksi evidence menyimpan dokumentasi D1, dua interface T1/T2, graf physical/session G1, serta transisi log DOWN/UP yang benar-benar cocok. Prompt hanya berisi proyeksi ringkas yang diturunkan dari sumber; hash, pointer, event lengkap dan teks asli tetap ada dalam input-contract.json. Nama fase dan ground truth tidak dikirim ke model. Seluruh log diverifikasi, namun hanya transisi peer/interface fokus yang dipilih; event router lain tidak dipakai sebagai sebab.

RcaDraft memuat assessment, hypothesis, target, evidence_ids, missing_evidence. JSON schema membatasi bentuk dan target ke endpoint yang diamati, tanpa memberitahu model endpoint mana yang salah. Sesudah inferensi, validator menolak target yang tidak administratif DOWN, diagnosis aktif saat state sudah sehat, atau finding tanpa dukungan lintas sumber. Ini validasi aturan terhadap finding terstruktur; bukan general semantic entailment atas seluruh kalimat model. Ground truth L12/L35 hanya ada pada evaluator. Karena cakupan aturan sempit, hasil enam kasus bukan benchmark independen atau bukti RCA umum.

Controller akhir memisahkan asal analisis secara eksplisit. Konteks terverifikasi UP dilaporkan sebagai observasi deterministik dengan analysis_origin=verified_observation_rule, model_called=false, dan citation T1/T2/G1. Ini bukan jawaban LLM atau klaim bahwa seluruh jaringan sehat. Konteks fault yang koheren diteruskan ke Ollama dengan analysis_origin=ollama_hypothesis. Keputusan rute ini berasal dari state observasi, bukan fase/ground truth. Percobaan sebelumnya yang meminta model mengklasifikasikan semua kasus tetap disimpan; model sempat salah membaca state sehat/log historis dan hasil tersebut ditolak.

Ukuran field/array draf dibatasi; finding yang diterima memakai missing_evidence kosong untuk cakupan operasional yang telah lengkap. Unknown di luar cakupan, termasuk pelaku/perintah asal, ditulis controller pada limitations.json; model tidak diminta mengarang daftar alternatif state yang tidak teramati. Insufficient_evidence tetap boleh menyebut maksimal dua fakta yang kurang.

Hipotesis dipetakan ke kontrak resmi Response; confidence null, patch kosong dan execution_allowed=false. Gate diperiksa lagi setelah inferensi atau jalur observasi deterministik. diagnosis_allowed=false berarti tidak ada diagnosis final yang disahkan; gate hanya mengizinkan hipotesis operasional terbatas. Teks model tidak diperbaiki otomatis dan kegagalan tidak diubah menjadi jawaban positif. Tidak tersedia executor atau akses command router.

Dari root proyek dalam WSL NetworkLab:

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.rca \
  --bundle data/host1/evidence-retrieval/replay-final-20261119/L12-down.json \
  --mode replay --output data/host1/rca-agent/contoh-baru
```

Gunakan direktori baru. Mode replay tidak membuktikan jaringan masih berada pada keadaan historis itu. Mode live menerapkan freshness dan dapat menolak hasil sesudah cold load yang terlalu lama.

```bash
private/.venv-retriever-wsl/bin/python scripts/host1.py -m unittest reasoning_agent.test_rca -v
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.replay_rca data/host1/rca-agent/run-baru --stage preflight
private/.venv-retriever-wsl/bin/python scripts/host1.py -m reasoning_agent.replay_rca data/host1/rca-agent/run-baru --stage actual
```

Gunakan --case untuk uji bertahap satu kasus. Jika semua kasus telah dijalankan secara individual, --stage summarize hanya membaca audit yang sudah ada, tanpa mengulang inferensi. Exit0 dari CLI rca berarti laporan berhasil dibuat; baca audit/status dan output-contract.json. Evaluator replay mengembalikan nonzero jika finding/target tidak sesuai ekspektasi kasus.

Sesudah keenam replay selesai, laporan rantai evidence terpisah dapat dibuat sekali dengan `python scripts/host1.py -m reasoning_agent.report_rca DIREKTORI_REPLAY`. Modul ini memverifikasi kembali sumber, Request dan hasil/kontrak tersimpan sebelum menulis direktori review baru; tidak memanggil model. Ia mempertahankan teks asli model dan memberi label penjelasan controller, bukan mengganti penjelasan model yang singkat.

Hasil milestone: [docs/host1/VALIDATION.md](../../docs/host1/VALIDATION.md). Gunakan `data/host1/rca-agent/20261120T114204Z/hybrid-v1/actual-summary.json` serta `hybrid-v1/review/summary.json` untuk hasil akhir. Folder final/ pada run tersebut adalah percobaan LLM-only yang gagal dan tetap disimpan. Keberhasilan enam kasus hybrid bukan akurasi enam kasus LLM.
