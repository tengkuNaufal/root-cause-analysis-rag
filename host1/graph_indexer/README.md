# Graph indexer telemetry

Indexer offline membaca `snapshot.json` collector schema v1 dan inventory yang disimpan bersama run. Tidak menjalankan Docker, fault injection, atau remediation. Dependensi dipin NetworkX 3.4.2 (Python >=3.10); implementasi diuji menggunakan virtual environment Windows `.venv-graph`.

## Menjalankan

Dari root proyek, PowerShell:

```powershell
python scripts/host1.py -m venv private/.venv-graph
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m pip install -r host1/graph_indexer/requirements.txt
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m graph_indexer.indexer data/host1/telemetry/20261119T050248Z-fbeea22b/0001/snapshot.json --inventory data/host1/telemetry/20261119T050248Z-fbeea22b/inventory.json --output data/host1/graph-indexer/contoh-baru
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m unittest discover -s host1/tests -p test_graph_indexer.py -v
.\private\.venv-graph\Scripts\python.exe scripts/host1.py -m tests.test_graph_indexer --replay data/host1/graph-indexer/replay-baru
```

Direktori output harus baru agar bukti tidak tertimpa. Modul juga menggunakan API Python portabel; eksekusi WSL untuk indexer belum diuji pada milestone ini.

## Model graf

`build_graph(snapshot, inventory, snapshot_path)` menghasilkan `nx.MultiDiGraph`: relasi berarah dan beberapa jenis edge dapat menghubungkan pasangan router yang sama. Contoh R1→R2 memiliki adjacency OSPF sekaligus sesi iBGP. Koneksi fisik dibuat dua arah, sedangkan ringkasan menghitung link unik sekali.

| Node / edge | Isi |
|---|---|
| router | Identitas inventory, status sumber, pengamatan protokol dan kernel route |
| interface | Router pemilik, MTU, alamat, admin/carrier, counter dan evidence |
| route / prefix | Setiap kandidat FRR route, status installed/selected, prefix tujuan |
| owns / physical | Kepemilikan interface dan koneksi sesuai inventory |
| ospf / bgp | Status dari sisi pengamat, peer address, evidence; hubungan yang diharapkan tetap ada ketika hilang |
| has_route / destination / egress | Hubungan route dengan router, prefix, dan interface next hop |

Inventory hanya memasok identitas dan relasi yang diharapkan, tidak mengisi status runtime. `physical.state` berasal dari admin/carrier kedua endpoint: ada false → down; semuanya true → up; selain itu unknown. MTU mismatch dilaporkan terpisah. `absent` berarti sumber protokol sukses tetapi peer yang diharapkan tidak tercantum; `unknown` berarti sumber gagal/hilang. `healthy=false` berarti belum terkonfirmasi sehat; selalu baca `state` untuk membedakan unknown dan fault. Sesi sehat unik dihitung hanya jika kedua arah FULL/Established. Peer tak terpetakan tetap disimpan dalam `protocol_observations`, belum menjadi edge tersendiri.

Semua kandidat route dipertahankan. Ringkasan egress mengambil route installed dengan next hop `fib=true`, bukan sekadar next hop rekursif BGP. Ini belum merupakan perhitungan path end-to-end; shortest path fisik tidak sama dengan forwarding OSPF/BGP.

`graph.json` adalah node-link JSON yang bisa dimuat kembali melalui `nx.node_link_graph(data, edges='edges')`. `summary.json` berisi jumlah node/edge, status link unik, sesi sehat dua arah, dan egress route. Evidence menyimpan path snapshot, JSON pointer sumber, raw_file relatif direktori snapshot, dan waktu observasi. Metadata graf menyimpan SHA-256 snapshot/inventory dan versi NetworkX. File sumber tidak disalin/diubah; simpan bersama artefak graf. Path snapshot pada hasil run ini absolut Windows.

Graf dibangun ulang setiap snapshot, sehingga status lama tidak terbawa ketika sumber gagal. ID route menggunakan indeks kandidat dalam snapshot dan tidak dijamin stabil lintas snapshot; untuk membandingkan rute gunakan router/prefix/protocol/next hop. Snapshot bukan observasi atomik dan bukan waktu kejadian router. Indexer ini bekerja batch; tidak menyediakan daemon indexing, freshness monitor, database graf atau remediation otomatis. Integrasi log berada pada modul korelasi.

Referensi API resmi: [MultiDiGraph](https://networkx.org/documentation/stable/reference/classes/multidigraph.html) dan [node-link JSON](https://networkx.org/documentation/stable/reference/readwrite/generated/networkx.readwrite.json_graph.node_link_data.html).

Update integrasi: event Vector kini dapat ditambahkan sebagai node log dengan relasi ke router, snapshot, serta observasi protokol. Lihat CORRELATION.md dan ../../docs/host1/VALIDATION.md. Indexer dasar tetap dapat dijalankan tanpa log.
