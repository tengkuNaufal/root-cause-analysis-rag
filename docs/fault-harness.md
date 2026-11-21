# Katalog fault dan runner

Bagian ini dipakai untuk menyuntikkan gangguan ke lab, menunggu gejalanya muncul, lalu memulihkan lab ke kondisi awal. Semua skrip jalan di Ubuntu yang menjalankan containerlab. Dari laptop, skrip yang sama dipanggil lewat SSH (lihat [akses-dari-laptop.md](akses-dari-laptop.md)).

## Isi

| Path | Isi |
|---|---|
| `faults/catalog.yaml` | 30 fault (10 kelas x 3 lokasi): langkah inject, langkah revert, gejala yang diharapkan, ground truth |
| `scripts/check_lab.py` | cek interface, OSPF, BGP, dan ping antar-loopback, lalu simpan snapshot JSON |
| `scripts/fault_runner.py` | jalankan fault dari katalog dan buat jadwal benchmark |
| `lab/replica/` | lab replika enam router yang dipakai untuk menguji katalog sebelum ada akses ke Host 1 |
| `data/replica/` | hasil uji 30 fault di lab replika |
| `data/benchmark_plan.csv` | jadwal 450 run (30 fault x 3 varian x 5 trial), urutan acak dengan seed 42 |

Ground truth di katalog hanya dibaca runner dan evaluator. Jangan dikirim ke agen.

## Menjalankan lab replika

```bash
docker pull quay.io/frrouting/frr:10.4.1
cd lab/replica/six-node
sudo containerlab deploy -t topik8.clab.yml
cd ../../..
sleep 40
python3 scripts/check_lab.py --lab topik8
```

Kalau semuanya normal, hasilnya:

```text
Lab topik8: 6 router, ping loopback 30/30 berhasil
SEMUA CEK LOLOS
```

Lab latihan dua router ada di `lab/replica/two-node` dan dicek dengan `--lab lab2`. Semua link memakai MTU 1500, bukan bawaan containerlab (9500), supaya fault MTU punya patokan yang jelas.

Topologi replika:

| AS | Router | Border |
|---|---|---|
| 65001 | r1, r2 | r2 |
| 65002 | r3, r4 | r4 |
| 65003 | r5, r6 | r6 |

| Link | Endpoint A | Endpoint B | Protokol |
|---|---|---|---|
| r1-r2 | r1 eth1 10.0.12.1/30 | r2 eth1 10.0.12.2/30 | OSPF |
| r3-r4 | r3 eth1 10.0.34.1/30 | r4 eth1 10.0.34.2/30 | OSPF |
| r5-r6 | r5 eth1 10.0.56.1/30 | r6 eth1 10.0.56.2/30 | OSPF |
| r2-r4 | r2 eth2 10.0.24.1/30 | r4 eth2 10.0.24.2/30 | eBGP |
| r4-r6 | r4 eth3 10.0.46.1/30 | r6 eth2 10.0.46.2/30 | eBGP |
| r6-r2 | r6 eth3 10.0.26.1/30 | r2 eth3 10.0.26.2/30 | eBGP |

Loopback rN adalah `10.255.0.N/32`. Border mengiklankan loopback AS-nya lewat eBGP dan memasukkan loopback AS lain ke OSPF, jadi r1, r3, dan r5 juga bisa saling ping.

## Menjalankan fault

```bash
python3 scripts/fault_runner.py list
python3 scripts/fault_runner.py run F01 F16
python3 scripts/fault_runner.py run --all
python3 scripts/fault_runner.py plan --seed 42
```

Untuk tiap fault, runner mengecek kondisi awal, menyuntikkan fault, menunggu gejala, menyimpan evidence, menjalankan revert, lalu menunggu sampai semua cek lolos dan rute ke loopback sama lagi dengan kondisi awal. Gejala dihitung dari cek yang gagal ditambah rute yang berubah. Kalau lab tidak pulih, runner berhenti supaya fault berikutnya tidak tercampur. Hasilnya satu baris JSON per fault di `data/runs/`.

## Hasil uji di lab replika

Ke-30 fault menimbulkan gejala yang terdeteksi dan pulih ke kondisi awal (`data/replica/`). Beberapa catatan:

- Fault hello timer dan autentikasi OSPF baru terlihat setelah 42 sampai 53 detik, karena tetangga OSPF baru dianggap hilang setelah dead interval 40 detik.
- Neighbor shutdown dan filter inbound di link eBGP tidak bikin ping gagal, karena trafik pindah lewat AS ketiga. Filter inbound cuma terlihat dari satu rute yang pindah jalur.
- IP salah di link eBGP (F30) tidak langsung memutus sesi BGP, karena hold timer 180 detik belum habis. Gejalanya juga cuma perpindahan jalur.
- Waktu yang tercatat ikut menghitung lamanya pengecekan, jadi angkanya kasar.

## Menyesuaikan dengan Host 1

Katalog dan `EXPECTED` di `check_lab.py` masih mengikuti topologi replika. Sebelum dipakai di Host 1:

1. Ganti `LAB` di `fault_runner.py` dan kunci `EXPECTED` di `check_lab.py` dengan nama lab Host 1 (container-nya bernama `clab-<nama lab>-<router>`).
2. Isi `EXPECTED` dengan interface, router-id tetangga OSPF, dan peer eBGP tiap router di Host 1.
3. Sesuaikan router, interface, alamat, ASN, dan peer di `faults/catalog.yaml`.
4. Jalankan `fault_runner.py run --all` di Host 1. Fault yang tidak menimbulkan gejala atau tidak pulih diganti lalu diuji lagi.
