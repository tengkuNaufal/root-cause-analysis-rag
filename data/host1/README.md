# Fixture Host 1 yang dibagikan

Folder ini juga menyimpan hasil eksperimen lokal. `.gitignore` hanya mengizinkan 148 file input yang benar-benar dibaca oleh 179 eksekusi unit test dan seluruh 16 skenario API replay. Terdapat 133 JSON, enam JSON Lines dan sembilan file teks, dengan ukuran total sekitar 12,34 MiB. Daftar dan SHA-256 ada di [fixtures-manifest.json](fixtures-manifest.json).

Data yang dibagikan meliputi snapshot/log/graf L12/L35, fixture MTU sintetis, query retrieval yang dipakai tes, serta kontrak, respons dan prompt tersimpan yang dibaca validator delapan penjelasan. Pemilihannya berdasarkan pencatatan akses file, bukan memasukkan seluruh folder atau seluruh path yang disebut dalam JSON.

Salinan publik adalah **turunan yang disanitasi untuk privasi**. Path absolut mesin diubah menjadi path relatif repositori. MAC serta IPv6 link-local yang terekam diganti secara konsisten dengan nilai sintetis agar identitas interface tidak dapat diturunkan dari EUI-64. State routing IPv4, alamat rancangan lab, MTU, waktu dan klasifikasi tetap dipertahankan. Hash file, referensi hash dan ID snapshot terkait dihitung ulang; hash pada manifest adalah hash salinan publik. Evidence asli serta hash historisnya disimpan di `private/privacy-originals/` dan tidak masuk Git. Kebijakan sanitasi juga dicatat di dalam manifest.

Log instalasi, checkpoint Vector, percobaan gagal/antara, dump mentah collector yang tidak dibaca, salinan request/budget/audit yang tidak diperlukan, laporan migrasi, keluaran tes sementara dan hasil run baru di-ignore. Salinan lokal tetap tersedia. Metadata historis seperti raw_file dapat menunjuk dump debug dalam arsip lokal; snapshot/graf/log yang benar-benar dibaca dan diverifikasi tetap dibagikan. Skrip evaluasi historis di luar cakupan tes dan katalog replay dapat memerlukan arsip lokal tambahan.

Model, virtual environment dan database Chroma berada di `private/`, sehingga clone baru tetap perlu menyiapkan dependensi dan storage lokal. Lihat [panduan operasional](../../docs/host1/OPERATIONS.md).
