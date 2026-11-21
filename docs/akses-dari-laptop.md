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

Kalau jaringan memang tidak memungkinkan (misalnya hanya ada WiFi kampus), alternatifnya VPN mesh seperti Tailscale di kedua Windows. Ini belum diputuskan kelompok.
