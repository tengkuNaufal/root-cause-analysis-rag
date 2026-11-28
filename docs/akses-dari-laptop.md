# Akses lab dari laptop (host kedua)

Untuk menjalankan 16 skenario replay melalui API HTTP dan menyimpan JSONL, gunakan [client replay Host 2](host2-replay.md). Panduan SSH di bawah digunakan untuk akses perintah lab dan runner live.

Tujuannya: laptop bisa menjalankan perintah di Ubuntu host utama lewat SSH (Secure Shell, koneksi terminal terenkripsi ke komputer lain). Nanti skrip injeksi fault dan monitoring dari laptop memakai jalur ini.

Cara yang dipakai di sini tidak mengubah jaringan WSL di host utama, jadi lab yang sudah jalan tidak ikut terganggu: laptop SSH ke **Windows** host utama, lalu Windows meneruskan perintah ke distro `NetworkLab` lewat `wsl`.

## 1. Pastikan dua komputer bisa saling melihat

Kedua komputer harus di jaringan yang sama. WiFi kampus biasanya memblokir koneksi antarperangkat (client isolation), jadi pakai router rumah/kos yang sama, hotspot HP yang sama, atau kabel LAN langsung.

Di host utama, PowerShell: `ipconfig` lalu catat IPv4 adaptor yang dipakai (misalnya `192.168.1.20`).
Di laptop, PowerShell: `ping 192.168.1.20`. Kalau timeout, tetap lanjut ke langkah 2 dulu karena firewall Windows sering memblokir ping saja.

## 2. Nyalakan OpenSSH Server di Windows host utama

PowerShell **Run as Administrator** di host utama:

```powershell
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
Get-NetFirewallRule -Name *OpenSSH-Server* | Select-Object Name, Enabled
```

Baris terakhir harus menunjukkan `Enabled: True`. Kalau aturan belum ada:

```powershell
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -Profile Private
```

Pastikan profil jaringan Windows yang dipakai adalah **Private**, bukan Public.

## 3. Uji dari laptop

PowerShell di laptop (OpenSSH Client sudah bawaan Windows 10/11):

```powershell
ssh <user-windows-host-utama>@192.168.1.20
```

Masukkan password akun Windows host utama. Setelah masuk:

```text
wsl -d NetworkLab -u USER_LINUX -- docker ps
```

Harus tampil daftar container `clab-rca-r1` sampai `clab-rca-r6` kalau lab sedang jalan.

Menjalankan cek lab langsung dari laptop dalam satu perintah:

Ganti `USER_LINUX`, nama user Windows, alamat contoh, dan `/path/to/root-cause-analysis-rag` dengan konfigurasi lokal masing-masing. Jangan menyimpan nilai koneksi pribadi di template yang dibagikan.

```powershell
ssh <user-windows-host-utama>@192.168.1.20 'wsl -d NetworkLab -u USER_LINUX --cd "/path/to/root-cause-analysis-rag" -- python3 scripts/check_lab.py'
```

Setelah ini berhasil, pakai skrip `laptop\lab.ps1` supaya tidak perlu mengetik ulang:

```powershell
Copy-Item laptop\config.example.ps1 laptop\config.ps1   # lalu isi IP dan user di config.ps1
.\laptop\lab.ps1 reach      # port 22 host utama terjangkau?
.\laptop\lab.ps1 check      # cek kesehatan lab
.\laptop\lab.ps1 faults F01   # jalankan satu fault dari katalog
```

Kalau PowerShell menolak menjalankan skrip (`running scripts is disabled`), jalankan sekali: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Supaya tidak ditanya password terus, daftarkan public key laptop (`id_ed25519.pub`) di host utama. Kalau akun Windows host utama administrator, jalankan di PowerShell **Run as Administrator** di host utama:

```powershell
Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value '<isi id_ed25519.pub dari laptop>'
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```

Perintah `icacls` wajib, karena OpenSSH mengabaikan file ini kalau izinnya terlalu longgar. Untuk akun biasa, isi key ditaruh di `$env:USERPROFILE\.ssh\authorized_keys`.

## Kalau tidak bisa tersambung

| Gejala | Kemungkinan penyebab |
|---|---|
| `Connection timed out` | beda jaringan, client isolation, atau firewall/profil Public |
| `Connection refused` | service `sshd` belum jalan di host utama |
| `Permission denied` | user/password salah; pakai nama user Windows, bukan nama user Linux |
| `There is no distribution with the supplied name` | nama distro beda; cek di host utama dengan `wsl -l -v` |
| `permission denied ... docker.sock` | user Linux belum masuk grup docker |

## Akses dari luar rumah lewat Tailscale

Host utama ada di rumah, sedangkan laptop dipakai di kampus atau kos. Tailscale membuat jaringan privat terenkripsi antar-perangkat lewat internet, jadi laptop bisa SSH ke host utama dari mana saja tanpa port forwarding di router rumah. API agen tetap terikat ke `127.0.0.1` di WSL dan tidak dibuka ke luar; semua perintah jalan di host utama lewat SSH.

Sekali setup:

1. Pasang Tailscale for Windows di host utama dan laptop (<https://tailscale.com/download>), login, lalu pastikan kedua perangkat ada di tailnet yang sama. Pemilik tailnet bisa mengundang anggota lain lewat admin console.
2. Di host utama, catat IP Tailscale-nya (`tailscale ip -4`, bentuknya `100.x.y.z`).
3. Di host utama, PowerShell **Run as Administrator**, izinkan SSH hanya dari alamat Tailscale:

   ```powershell
   New-NetFirewallRule -Name sshd-tailscale -DisplayName 'OpenSSH via Tailscale' -Direction Inbound -Protocol TCP -LocalPort 22 -RemoteAddress 100.64.0.0/10 -Action Allow -Profile Any
   ```

4. Di laptop, isi `$HostIp` di `laptop\config.ps1` dengan IP Tailscale host utama, lalu cek `.\laptop\lab.ps1 reach` dan `.\laptop\lab.ps1 check`.

Uji dari jaringan yang akan dipakai (WiFi kampus, hotspot HP) beberapa hari sebelum dibutuhkan. Kalau WiFi kampus memblokir koneksi langsung, Tailscale biasanya tetap tersambung lewat relay dengan latensi lebih tinggi, tapi tetap harus dibuktikan.

## Monitoring benchmark dari laptop

Benchmark berjalan di tmux sesi `bench` di host utama dan menulis ke `data/host2/bench`. Laptop cuma membaca, jadi koneksi laptop yang putus tidak menghentikan benchmark.

```powershell
.\laptop\lab.ps1 status        # progres per varian, baris bermasalah, baris yang ditahan, 5 run terakhir
.\laptop\lab.ps1 status 12     # detail baris jadwal 12 (diagnosis, perintah, lint, waktu)
.\laptop\lab.ps1 watch         # nonton layar tmux secara read-only, keluar dengan Ctrl+B lalu D
```

Angka di `status` cuma pengecekan cepat terhadap katalog. Angka resmi tetap dari evaluator.

## Demo satu run live

`demo` menjalankan satu fault lengkap di lab asli: inject, diagnosis agen, lint, penerapan perintah, verifikasi, lalu menampilkan detail run. Token API diminta interaktif dan tidak disimpan. Varian `rule_based` (pembanding regex) tidak butuh API dan token.

```powershell
.\laptop\lab.ps1 demo F01 graph_rag
.\laptop\lab.ps1 demo F16 text_rag
```

Hasil demo disimpan terpisah di `data/host2/demo/<waktu>-<fault>-<varian>/` sehingga tidak tercampur dengan hasil benchmark. `bench.py` mengunci lab, jadi demo ditolak kalau benchmark sedang berjalan, begitu juga sebaliknya. Di host utama perintah yang sama adalah `bash scripts/demo.sh F01 graph_rag`.

Fault yang cocok untuk demo karena gejalanya jelas: F01 (MTU), F04 (link down), F16 (BGP neighbor shutdown), F25 (missing network).

Smoke test MTU (F01-F03, target pulih di bawah 10 detik) juga bisa dijalankan dari laptop:

```powershell
.\laptop\lab.ps1 smoke graph_rag
.\laptop\lab.ps1 smoke rule_based    # pembanding regex, gak minta token
```

## Persiapan hari presentasi

Demo live bergantung pada host utama di rumah, jadi siapkan cadangan:

1. Rekam layar beberapa run live (`lab.ps1 demo ...` dan `lab.ps1 status`) sebelum hari presentasi, misalnya dengan Xbox Game Bar (`Win+Alt+R`) atau OBS. Rekaman ini dipakai kalau koneksi atau host utama bermasalah.
2. Di host utama: Sleep diatur `Never`, Windows Update di-pause selama minggu presentasi, lab, API agen, dan Ollama sudah jalan (API sebaiknya di tmux juga), lalu jalankan satu demo sebagai pemanasan supaya model sudah termuat di GPU.
3. Dari laptop di lokasi presentasi: `reach`, `check`, lalu satu `demo` uji coba sebelum maju.
4. Jangan jalankan benchmark di hari yang sama dengan demo, karena lab cuma bisa dipakai satu proses.
