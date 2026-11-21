# Salin jadi config.ps1 di folder ini lalu isi sesuai host utama. config.ps1 gak ikut di-commit.
$HostIp    = '<HOST_IP>'                          # isi IPv4 Windows host utama
$WinUser   = '<WINDOWS_USER>'                     # isi user Windows untuk login SSH
$Distro    = 'NetworkLab'                          # nama distro WSL (wsl -l -v)
$LinuxUser = '<LINUX_USER>'                       # isi user Linux di distro tersebut
$RepoPath  = '/path/to/root-cause-analysis-rag'    # isi path repo di WSL host utama
