# Universal Secure Locker

Universal Secure Locker adalah prototipe aplikasi desktop brankas digital lokal untuk proyek Tugas Akhir Kriptografi.

## Fokus Tahap Awal

Versi ini berfokus pada tampilan dasar dan uji alur autentikasi dua kunci:

1. **USB Flashdisk** — aplikasi menambahkan satu file token rahasia `USL-USB-KEY.txt` di flashdisk dan menyimpan hash token di komputer.
2. **Biometrik wajah** — pengguna mendaftarkan 12 sampel wajah dari webcam. OpenCV mendeteksi wajah dan membuat model pengenal LBPH lokal.

Kedua kunci wajib terdaftar dan lolos verifikasi sebelum dashboard demonstrasi terbuka. Dashboard saat ini hanya menunjukkan bahwa alur akses berhasil; fitur catatan, file locker, dan enkripsi belum dibuat.

## Stack yang Dipilih

| Bagian | Teknologi | Penggunaan |
|---|---|---|
| Desktop | **PyWebView** | Membuka UI HTML sebagai aplikasi desktop dan menyediakan penghubung JavaScript ke Python. |
| Antarmuka | **HTML5, CSS3, JavaScript vanilla** | UI lokal tanpa framework frontend atau proses bundling. |
| Webcam dan pengenalan wajah | **OpenCV contrib + NumPy** | Deteksi wajah Haar dan pengenal LBPH sederhana untuk demonstrasi. |
| USB | **Windows API melalui `ctypes`** | Mencari drive removable dan memeriksa token pada flashdisk tanpa dependensi tambahan. |
| Data autentikasi | **JSON dan model OpenCV lokal** | Menyimpan hash token USB dan model wajah pada folder `storage/`. |

PyWebView dipilih daripada Electron atau API FastAPI/Flask agar tahap awal tetap ringan dan tidak membutuhkan server web terpisah. SQLite, AES-GCM, Argon2id, steganografi, dan audit ledger direncanakan untuk tahap berikutnya dan belum digunakan oleh prototipe ini.

## Kebutuhan

- Windows 10/11 64-bit.
- Python 3.11 atau lebih baru dan `pip`.
- Microsoft Edge WebView2 Runtime.
- Webcam.
- USB Flashdisk yang diformat dengan filesystem yang dapat ditulis.

Deteksi USB saat ini khusus Windows dan hanya menampilkan drive yang dilaporkan sistem sebagai removable. Beberapa USB eksternal yang dilaporkan sebagai fixed drive mungkin tidak muncul.

## Instalasi dan Menjalankan

Jalankan perintah berikut di PowerShell dari folder proyek:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Jika Python 3.11 tidak terpasang, ganti `-3.11` dengan versi Python 3.11+ yang tersedia, misalnya `-3.14`.

Jika PowerShell menolak aktivasi environment virtual, gunakan Python dari environment virtual secara langsung:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Cara Menguji Dua Kunci

1. Jalankan aplikasi dan tekan **Aktifkan webcam**.
2. Arahkan wajah ke kamera. Tekan **Ambil sampel** 12 kali; ubah sedikit sudut wajah atau ekspresi di antara pengambilan.
3. Setelah 12 sampel, tombol **Daftarkan wajah sekarang** aktif. Tekan tombol tersebut untuk menyimpan model wajah.
4. Sambungkan USB Flashdisk. Tekan tombol perbarui daftar, lalu pilih drive USB yang benar.
5. Setelah memilih drive, tombol **Daftarkan USB sebagai kunci** tersedia. Tekan tombol tersebut dan setujui konfirmasi.
6. Pendaftaran USB **tidak memformat flashdisk dan tidak menghapus atau menimpa file yang sudah ada**. Aplikasi hanya membuat satu file token kecil bernama `USL-USB-KEY.txt` di folder utama USB; file token ini jangan dihapus atau diubah.
7. Setelah status wajah dan USB menunjukkan **Terdaftar**, tekan **Verifikasi dan buka**. Dashboard demonstrasi hanya terbuka jika kedua kunci cocok.
8. Tekan **Kunci aplikasi** pada dashboard untuk kembali ke layar akses.

Untuk menguji penolakan akses, lepaskan flashdisk terdaftar atau coba verifikasi menggunakan wajah yang berbeda. Pendaftaran biometrik tersimpan lokal di `storage/face_model.yml`; hash token tersimpan di `storage/auth_config.json`. Kedua file tersebut tidak ditambahkan ke Git.

## Struktur Proyek

```text
universal-secure-locker/
├── backend/
│   ├── security/
│   │   ├── biometric_auth.py
│   │   └── dongle_auth.py
│   └── modules/
├── frontend/
│   ├── index.html
│   ├── dashboard.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       └── api.js
├── storage/                  # Data autentikasi lokal, diabaikan Git
├── main.py
├── requirements.txt
└── README.md
```

Rincian latar belakang dan rancangan keseluruhan terdapat di [dokumen perancangan proyek](./dokumen_perancangan_project_akhir_kriptografi.md).

## Catatan Keamanan dan Batasan

- Ini adalah **demonstrasi autentikasi**, bukan sistem keamanan siap produksi. Jangan gunakan untuk melindungi data penting.
- File token USB adalah rahasia statis. Orang yang dapat menyalinnya dapat menduplikasi kunci; serial perangkat dan pendeteksian drive juga bukan bukti USB yang tahan manipulasi.
- Pendaftaran USB tidak menjalankan proses format. Aplikasi hanya membuat file token baru di folder utama USB yang dipilih. File yang sudah ada tidak ditimpa; jika file token dengan nama yang sama sudah ada, pendaftaran dibatalkan.
- LBPH merupakan pengenal wajah sederhana, bukan sistem biometrik modern yang tahan spoofing. Prototipe ini tidak memiliki deteksi keaktifan (*liveness detection*), sehingga foto/video dapat berisiko mengecoh verifikasi. Nilai ambang pengenalan perlu diuji pada kondisi kamera yang beragam.
- Model wajah dan konfigurasi disimpan lokal tanpa enkripsi pada tahap ini. Amankan komputer dan jangan membagikan folder `storage/`.
- Kamera hanya digunakan melalui aplikasi lokal; frame tidak dikirim ke layanan internet.
- Dashboard setelah autentikasi belum menyimpan catatan atau file, dan belum ada enkripsi database maupun file.
- Jangan mengimplementasikan algoritma kriptografi sendiri pada tahap lanjutan. Gunakan pustaka teruji, misalnya `cryptography` dengan AES-GCM untuk enkripsi terautentikasi dan Argon2id untuk hash password.
