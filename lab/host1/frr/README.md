# FRR baseline — lab rca

Konfigurasi sumber enam router sesuai `../../../docs/host1/TOPOLOGY-DESIGN.md`. **Lab telah di-deploy dan baseline OSPF/BGP/routing/ping lulus pada 19 November 2026. Lab ditinggalkan berjalan; periksa state aktual sebelum deploy ulang.** Laporan: `../../../docs/host1/VALIDATION.md`.

## Image dan file

- Image resmi: `quay.io/frrouting/frr:containerlab-10.7.1`, dipin dengan digest di YAML dan `image-lock.json`.
- Binary yang diperiksa melaporkan `10.7.1_git`; platform `linux/amd64`.
- `topology.clab.yml`: enam node `kind: frr`, delapan link MTU 1500, IP management dan pilihan daemon.
- `configs/r1/frr.conf` sampai `configs/r6/frr.conf`: alamat data/loopback/service, OSPF, BGP, prefix-list dan route-map.
- `design-plan.json`: inventaris desain, bukan file deploy.
- `validate-config.sh`: validasi YAML dan sintaks FRR tanpa deploy lab.
- `validation/vtysh.conf`: pendamping parser offline. Ini bukan file startup tambahan untuk lab; kind frr menghasilkan file runtime sendiri.

## Mekanisme konfigurasi

Containerlab membuat salinan `startup-config` di direktori runtime `clab-rca/<node>/config/frr.conf`, beserta `daemons` dan `vtysh.conf`. File runtime dapat berubah selama eksperimen; file sumber `configs/` dipertahankan sebagai baseline.

`enforce-startup-config: true` memastikan deploy baru memakai baseline sumber, bukan konfigurasi fault yang pernah disimpan. `restart-policy: "no"` mencegah Docker otomatis menghidupkan router tanpa link Containerlab setelah distro berhenti. Tetap pertahankan sesi WSL terbuka; jika distro berhenti, periksa dan lakukan redeploy terkontrol.

R1–R4 meminta daemon `bgpd` dan `ospfd`; R5/R6 hanya `bgpd`. Kind frr juga menjalankan daemon dasar zebra, staticd, mgmtd, dan watchfrr sesuai implementasi native; tidak perlu menyimpan enam salinan file `daemons` manual.

IPv4 forwarding diaktifkan lewat sysctl container. Reverse-path filtering dinonaktifkan pada `all`, `default`, dan setiap data interface untuk eksperimen asimetri. MTU diatur pada link YAML dan diperkuat melalui exec `ip link`. Alamat IP dipasang oleh konfigurasi FRR/zebra. iBGP memakai alamat loopback identitas eksplisit sebagai update-source, bukan nama `lo` yang memiliki dua alamat.

Image containerlab-native menghapus default route management saat startup. Jaringan connected management tetap ada; tidak termasuk OSPF atau prefix yang di-export BGP. Runtime behavior ini masih perlu diperiksa saat deploy.

## Validasi yang sudah dilakukan

- Image berhasil di-pull di NetworkLab dan digest dicatat.
- `clab validate` versi 0.82.0: enam node, delapan link, valid.
- Enam file `frr.conf` lolos `vtysh -C` pada image terpilih dalam container sementara `--network none`.
- Bind mount read-only file dari drive D berhasil untuk parser.
- Update runtime: deploy dari drive D berhasil; 5 OSPF FULL, 9 BGP Established, dan 30/30 arah ping service lulus (120/120 paket). Failover link L12 dan L35 serta pemulihan baseline juga lulus; lihat `../../../docs/host1/VALIDATION.md`. Write memory dan reset/redeploy penuh belum diuji.

Bukti sukses: `../../../data/host1/frr-config/20261119T113155-validation/`. Log awal di `../../../data/host1/frr-config/2026-11-19/` juga menyimpan percobaan parser yang gagal karena belum menyediakan file default; jangan menafsirkannya sebagai hasil akhir. Exit code vtysh saja tidak cukup, sehingga validator juga memeriksa pesan kesalahan.

## Menjalankan pemeriksaan ulang

Di terminal Ubuntu **NetworkLab** yang tetap terbuka:

```bash
cd '/path/to/root-cause-analysis-rag'
sudo bash lab/host1/frr/validate-config.sh
```

Image harus tersedia secara lokal; bila belum, pull referensi lengkap yang ada di YAML. Validator menghasilkan direktori bukti baru di `data/host1/frr-config/`. Container parser dihapus otomatis dengan `--rm`.

## Deploy dan verifikasi runtime

Deploy pertama sudah berhasil menggunakan perintah berikut. Sebelum deploy berikutnya, periksa subnet Docker/WSL/Windows/VPN, keberadaan lab rca, dan sesi WSL persisten. Jangan mengulang deploy pada lab yang masih aktif tanpa alasan:

```bash
cd '/path/to/root-cause-analysis-rag/lab/host1/frr'
sudo clab deploy -t topology.clab.yml
```

Target baseline OSPF/BGP/route/ping dan dua uji failover link sudah tercapai. Bukti di `../../../data/host1/frr-runtime/2026-11-19/` dan `../../../data/host1/frr-failover/20261119T115340/`. Dari root proyek jalankan `sudo python3 lab/host1/frr/verify-runtime.py data/host1/frr-runtime/<run-baru>/baseline` untuk pemeriksaan ulang tanpa mengubah konfigurasi. Script `test-failover.py` mengubah status L12/L35 dan hanya dijalankan jika gangguan lab diotorisasi. Contoh observasi:

```bash
sudo docker exec clab-rca-r1 vtysh -c 'show ip ospf neighbor json'
sudo docker exec clab-rca-r1 vtysh -c 'show bgp ipv4 unicast summary json'
sudo docker exec clab-rca-r1 vtysh -c 'show ip route json'
sudo docker exec clab-rca-r1 ping -I 10.100.1.1 -c 4 10.100.5.1
```

Untuk reset baseline setelah perubahan fault, simpan bukti lalu gunakan redeploy/reconfigure pada lab `rca` setelah diotorisasi. Jangan menyamakan restart proses/container dengan reset konfigurasi dan link. Cleanup lab menggunakan `sudo clab destroy -t topology.clab.yml`, bukan prune global.

## Alasan pemilihan image

Varian containerlab resmi 10.7.1 tersedia di registry dan menyediakan integrasi native, sementara kode Containerlab **v0.82.0** mendukung `kind: frr`, `startup-config`, dan pemilihan daemon. Tag versi tetap dipadukan dengan digest agar perubahan tag tidak mengubah lingkungan eksperimen. Pilihan ini telah lulus parser serta baseline runtime pada NetworkLab; bukan klaim versi terbaru atau keberhasilan seluruh skenario fault.

Referensi:

- https://containerlab.dev/manual/kinds/frr/
- https://raw.githubusercontent.com/srl-labs/containerlab/v0.82.0/nodes/frr/frr.go
- https://raw.githubusercontent.com/srl-labs/containerlab/v0.82.0/schemas/clab.schema.json
