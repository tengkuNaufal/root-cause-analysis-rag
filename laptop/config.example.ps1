# Salin jadi config.ps1 di folder ini lalu isi sesuai host utama. config.ps1 gak ikut di-commit.
$HostIp    = '192.168.1.20'                        # IPv4 Windows host utama (cek pakai ipconfig)
$WinUser   = 'ashkar'                              # user Windows host utama buat login SSH
$Distro    = 'NetworkLab'                          # nama distro WSL (wsl -l -v)
$LinuxUser = 'scar'                                # user Linux di distro itu
$RepoPath  = '/home/scar/root-cause-analysis-rag'  # path repo di Ubuntu host utama
