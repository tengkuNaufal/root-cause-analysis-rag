# Referensi tambahan MTU terverifikasi

Sumber primer diunduh 19 November 2026; URL, versi, waktu dan SHA-256 ada pada manifest.json. Ini lampiran pengetahuan terpisah, **belum dimasukkan ke koleksi Chroma**: source C, standar protokol, dan dokumentasi Linux tidak boleh dilabeli ulang sebagai manual CLI FRR atau schema OpenConfig.

## FRR OSPFv2

Source FRR dipin ke commit f8c0b08dcb0c78f9e42b9b86ae70b049e4e617c1, sama dengan tag dokumentasi10.7.1 yang dipakai:

- [ospf_vty.c](https://github.com/FRRouting/frr/blob/f8c0b08dcb0c78f9e42b9b86ae70b049e4e617c1/ospfd/ospf_vty.c#L9853-L9905), salinan frr-ospf-vty.c: mendefinisikan ip ospf mtu-ignore pada context interface, mengatur flag pengabaian pemeriksaan mismatch; bentuk no juga tersedia.
- [ospf_packet.c](https://github.com/FRRouting/frr/blob/f8c0b08dcb0c78f9e42b9b86ae70b049e4e617c1/ospfd/ospf_packet.c#L1224-L1234), salinan frr-ospf-packet.c: pemeriksaan paket Database Description berhenti ketika MTU peer lebih besar dari interface lokal dan flag ignore tidak aktif.
- [RFC2328 bagian10.6](https://www.rfc-editor.org/rfc/rfc2328.html#section-10.6), salinan rfc2328.txt baris4925–4929: menjelaskan penolakan Database Description yang mengiklankan datagram lebih besar daripada kemampuan interface penerima tanpa fragmentasi.

Temuan ini menutup celah bukti keberadaan command di source FRR, bukan membuktikan solusi live untuk lab. Flag ignore melewati pemeriksaan protokol, tidak menyamakan MTU interface atau menjamin forwarding paket besar. Default baseline proyek tetap MTU1500 di kedua endpoint. Pemulihan nilai MTU sesuai inventory adalah kandidat untuk uji berikutnya, bukan patch yang dieksekusi di milestone ini. Manual ospfd.rst yang terindeks masih tidak mendokumentasikan command tersebut; gate remedy tetap abstain.

## MTU Linux dan schema OpenConfig

[Dokumentasi kernel v6.3](https://www.kernel.org/doc/html/v6.3/networking/netdevices.html#mtu), salinan linux-netdevices.rst baris185–205, menjelaskan MTU perangkat Linux sebagai ukuran tanpa overhead link layer. Contohnya membedakan MTU1500 dengan panjang buffer yang juga membawa header Ethernet. Angka VLAN di bagian ini adalah tag, jangan keliru menyebutnya FCS.

Schema OpenConfig yang sudah dipin menyebut contoh default1514 pada leaf interface/mtu (host1/knowledge/sources/openconfig-openconfig-interfaces.yang sekitar485). Itu konteks field berbeda. Jangan menerapkan definisi MTU Linux secara otomatis pada pertanyaan mengenai field OpenConfig, atau menyimpulkan rincian FCS yang tidak tertulis dalam kutipan. Gate untuk pertanyaan gabungan header/FCS tetap konservatif bila sumber spesifik belum menjawabnya.

Tidak ada fault MTU baru, perubahan interface, pengujian command konfigurasi, atau validasi remedy otomatis. File data/host1/pre-ollama/frr-command-list.txt hanya daftar command mode saat ini; tidak ditemukannya command konfigurasi di mode exec tidak membuktikan command tidak ada. Bukti keberadaannya di sini berasal dari source versi tetap, bukan hasil menjalankannya.
