# Universal Secure Locker

Universal Secure Locker adalah prototipe aplikasi desktop brankas digital lokal untuk proyek Tugas Akhir Kriptografi.

## Fokus Tahap Awal

Login memiliki dua tahap:

1. **Kunci perangkat:** USB Flashdisk dan verifikasi wajah melalui webcam.
2. **Akun:** login atau pendaftaran dengan username dan password yang di-hash memakai Argon2id.

Setelah login, akun dapat membuat folder, mengunggah, melihat/mengunduh, dan memperbarui file. Data file berada di disk lokal pada folder akun, sedangkan SQLite hanya menyimpan metadata dan izin. Pemilik item atau admin membagikan izin **buat, lihat, dan ubah** secara terpisah untuk setiap folder atau file. Tidak ada akses otomatis ke item milik akun lain, termasuk bagi admin; admin dapat mengatur izin, tetapi tetap perlu izin item untuk membaca kontennya. Penghapusan item belum tersedia.

Closure tampil sebagai pemandu dengan bubble dialog yang menyambut pengguna dan memperbarui petunjuk sesuai tahap pendaftaran, verifikasi, atau akses dashboard.

## Login Akun dan Pembagian Akses

- Setelah USB dan wajah cocok, pilih **Buat akun** atau **Masuk**. Password minimal 10 karakter dan disimpan sebagai hash Argon2id di `storage/accounts.db`; password asli tidak disimpan.
- Akun pertama otomatis menjadi admin. Pendaftaran mandiri untuk akun berikutnya tetap tersedia, tetapi akun baru hanya dapat melihat file miliknya sendiri sampai pemilik atau admin memberinya izin.
- USB dan model wajah tetap menjadi lapisan perangkat bersama untuk instalasi lokal ini. Username/password tahap kedua menentukan akun dan izin data yang digunakan.
- Admin dapat mengatur izin pada item yang dikelola, tetapi status admin sendiri **tidak** memberikan akses baca ke seluruh isi vault. Pemilik file/folder juga dapat membagikan item miliknya.
- Hak akses ditetapkan pada tiap item dan tidak diwariskan. Untuk membuka file di dalam folder bersama, penerima perlu hak **lihat** pada seluruh folder induk dan hak **lihat** pada file tersebut. Untuk membuat item di folder bersama, penerima perlu hak **lihat** dan **buat** di folder itu.
- Hak **ubah** otomatis menyertakan hak **lihat**. Izin dapat dicabut dengan menghilangkan semua centang lalu menyimpan.
- Setiap akun memiliki folder lokal `storage/users/account-{id}-{username}/`. Isi file disimpan di dalam folder akun tersebut, termasuk dalam subfolder lokal untuk item folder; SQLite hanya menyimpan metadata, hash password, dan izin. Unggahan dibatasi 10 MiB.
- Folder dan file yang tampil di vault tetap memakai nama yang dipilih, sementara direktori fisiknya memakai ID resource untuk mencegah benturan nama/path. Data file dan database **belum dienkripsi**. Pembatasan akun ini hanya berlaku di dalam aplikasi; pengguna yang memiliki akses OS dapat membaca folder akun maupun database secara langsung.
- Dashboard menyediakan super enkripsi teks berurutan Caesar → Vigenere → XOR → RSA-OAEP. Ciphertext berupa heksadesimal agar hanya memakai karakter `0–9` dan `a–f`; penyimpanan ke `items/pesan_terenkripsi_{angka}.txt` tetap dilakukan setelah tombol simpan ditekan.
- RSA memakai key pair standar 3072-bit yang dapat dibuat dari aplikasi atau diimpor sebagai PEM. Public key dipakai untuk enkripsi, private key pasangannya untuk dekripsi. Kunci Vigenere/XOR yang sama (minimal 12 huruf/angka) dan Caesar shift (0–25) harus digunakan kembali untuk dekripsi.

## Panduan Closure dan Pesan Terminal

Closure menyambut pengguna dan memberikan instruksi dalam bubble dialog. Pesan tersebut mengikuti tahap yang sedang berlangsung: aktivasi webcam, pengambilan sampel wajah, pemilihan dan pendaftaran USB, hingga verifikasi akses. Informasi pada elemen status di halaman juga tetap ditampilkan.

Pesan panduan Closure **juga tetap dicatat di terminal** sebagai log berlevel `INFO`; fitur bubble tidak menggantikan pesan terminal. Jalankan aplikasi dari PowerShell agar log dapat dilihat:

```powershell
.\.venv\Scripts\python.exe main.py
```

Log menggunakan format waktu, level, dan nama logger, misalnya `INFO universal_secure_locker: Closure: Webcam aktif...`. Jika halaman dibuka langsung tanpa bridge PyWebView, Closure tetap memberikan panduan di layar dan pesan tersedia di konsol browser.

## Stack yang Dipilih

| Bagian | Teknologi | Penggunaan |
|---|---|---|
| Desktop | **PyWebView** | Membuka UI HTML sebagai aplikasi desktop dan menyediakan penghubung JavaScript ke Python. |
| Antarmuka | **HTML5, CSS3, JavaScript vanilla** | UI lokal tanpa framework frontend atau proses bundling. |
| Webcam dan pengenalan wajah | **OpenCV contrib + NumPy** | Deteksi wajah Haar dan pengenal LBPH sederhana untuk demonstrasi. |
| USB | **Windows API melalui `ctypes`** | Mencari drive removable dan memeriksa token pada flashdisk tanpa dependensi tambahan. |
| Password akun | **Argon2id (`argon2-cffi`)** | Menyimpan hash password akun dengan salt dan parameter Argon2id. |
| Super enkripsi pesan | **`cryptography`** | RSA-OAEP SHA-256 3072-bit; Caesar, Vigenere, dan XOR untuk demonstrasi berlapis. |
| Akun, izin, dan metadata | **SQLite melalui `sqlite3` bawaan Python** | Menyimpan akun, hash, metadata resource, dan izin per item di `storage/accounts.db`. |
| Konten file | **Filesystem lokal** | Menyimpan file di `storage/users/account-{id}-{username}/`; folder ini diabaikan Git. |
| Faktor perangkat | **JSON dan model OpenCV lokal** | Menyimpan hash token USB dan model wajah pada folder `storage/`. |

PyWebView dipilih daripada Electron atau API FastAPI/Flask agar tahap awal tetap ringan dan tidak membutuhkan server web terpisah. Enkripsi file/database, steganografi, dan audit ledger direncanakan untuk tahap berikutnya dan belum digunakan.

### Super Enkripsi Teks

1. Masukkan Caesar shift (0–25) dan satu kunci alfanumerik ASCII sepanjang 12–128 karakter. Kunci yang sama digunakan untuk Vigenere dan XOR; simpan parameter ini agar dapat mendekripsi.
2. Buat key pair RSA 3072-bit atau tempel public/private key PEM yang cocok. Public key mengenkripsi, sedangkan private key hanya digunakan untuk dekripsi.
3. Enkripsi memproses teks UTF-8 maksimal 16 KiB dengan urutan Caesar → Vigenere → XOR → RSA-OAEP dengan SHA-256. Caesar/Vigenere hanya menggeser huruf Latin A–Z/a–z; XOR diterapkan pada byte UTF-8. RSA-OAEP menangani blok data, lalu hasilnya dikodekan sebagai teks heksadesimal (`0–9`, `a–f`).
4. Tempel ciphertext dan masukkan kembali shift, kunci bersama, serta private key yang cocok untuk mendekripsi. Untuk menyimpan, tekan **Simpan ciphertext sebagai .txt**; hanya ciphertext yang disimpan.
5. Key pair yang dibuat tidak disimpan aplikasi. Simpan private key di tempat aman dan jangan membagikannya. Jika hilang, ciphertext tidak dapat didekripsi.

Jangan memilih bilangan prima RSA 20–30 digit: ukuran tersebut terlalu kecil untuk keamanan RSA modern. Pembuatan key pair 3072-bit oleh pustaka kriptografi lebih tepat daripada memasukkan bilangan prima sendiri. Lapisan Caesar/Vigenere/XOR adalah algoritma klasik untuk demonstrasi dan tidak menambah keamanan RSA yang berarti; fitur ini tidak memberikan autentikasi/integritas ciphertext dan tidak menggantikan enkripsi file dengan skema terautentikasi seperti AES-GCM. Jangan gunakan sebagai satu-satunya perlindungan data penting.

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
7. Setelah status wajah dan USB menunjukkan **Terdaftar**, tekan **Verifikasi dua kunci**. Jika keduanya cocok, formulir akun akan terbuka.
8. Buat akun pertama (otomatis admin), atau masuk dengan akun yang sudah ada. Username minimal 3 karakter; password minimal 10 karakter.
9. Di dashboard, buat folder dan unggah file. Pemilik dapat memilih **Atur akses** untuk memberi akun lain izin per item.
10. Akun penerima logout lalu login memakai username/password sendiri. Akun tersebut hanya melihat item yang dimiliki atau yang izinnya telah diberikan; untuk item dalam folder, izin lihat harus diberikan pada folder induk dan itemnya.
11. Tekan **Kunci aplikasi** pada dashboard untuk logout. Login berikutnya kembali memerlukan USB dan wajah.

Untuk menguji penolakan akses, lepaskan flashdisk terdaftar atau coba verifikasi menggunakan wajah yang berbeda. Pendaftaran biometrik tersimpan lokal di `storage/face_model.yml`; hash token tersimpan di `storage/auth_config.json`. Kedua file tersebut tidak ditambahkan ke Git.

## Struktur Proyek

```text
universal-secure-locker/
├── backend/
│   ├── database.py            # Akun Argon2id, resource, dan ACL per item
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
├── tests/
│   ├── test_account_api.py
│   └── test_account_database.py
└── README.md
```

Rincian latar belakang dan rancangan keseluruhan terdapat di [dokumen perancangan proyek](./dokumen_perancangan_project_akhir_kriptografi.md).

## Catatan Keamanan dan Batasan

- Ini adalah **demonstrasi autentikasi**, bukan sistem keamanan siap produksi. Jangan gunakan untuk melindungi data penting.
- File token USB adalah rahasia statis. Orang yang dapat menyalinnya dapat menduplikasi kunci; serial perangkat dan pendeteksian drive juga bukan bukti USB yang tahan manipulasi.
- Pendaftaran USB tidak menjalankan proses format. Aplikasi hanya membuat file token baru di folder utama USB yang dipilih. File yang sudah ada tidak ditimpa; jika file token dengan nama yang sama sudah ada, pendaftaran dibatalkan.
- LBPH merupakan pengenal wajah sederhana, bukan sistem biometrik modern yang tahan spoofing. Prototipe ini tidak memiliki deteksi keaktifan (*liveness detection*), sehingga foto/video dapat berisiko mengecoh verifikasi. Nilai ambang pengenalan perlu diuji pada kondisi kamera yang beragam.
- Model wajah dan konfigurasi disimpan lokal tanpa enkripsi pada tahap ini. Amankan komputer dan jangan membagikan folder `storage/`.
- Hash password tidak dapat mengembalikan password asli, tetapi metadata database dan konten file tetap lokal tanpa enkripsi. Amankan komputer dan backup folder `storage/` dengan hati-hati.
- Izin akun berlaku saat mengakses aplikasi. Pengguna yang memiliki akses OS langsung ke `storage/accounts.db` dapat membaca atau mengubah datanya; enkripsi at-rest dan perlindungan integritas database belum dibuat.
- Kamera hanya digunakan melalui aplikasi lokal; frame tidak dikirim ke layanan internet.
- Dashboard menyimpan konten file pada `storage/users/` dan metadata/izin pada database SQLite. Saat aplikasi diperbarui, BLOB file lama yang masih berada di database akan dipindahkan otomatis ke folder akun; backup database dan `storage/users/` bersama-sama. Steganografi dan audit ledger belum dibuat; database serta file belum dienkripsi.
- Super enkripsi teks sudah tersedia dengan urutan Caesar → Vigenere → XOR → RSA-OAEP. Implementasi ini untuk pembelajaran, bukan pengganti enkripsi file/database atau enkripsi terautentikasi.
- Gunakan pustaka kriptografi teruji untuk fitur produksi. AES-GCM untuk enkripsi terautentikasi dan Argon2id untuk hash password; jangan mengimplementasikan algoritma kriptografi sendiri.

## Perubahan Tampilan Terbaru

- **Halaman awal:** gambar Closure ditampilkan sebagai pemandu di samping bubble dialog, bukan sebagai logo. Instruksi dialog berubah mengikuti proses pendaftaran dan verifikasi.
- **Panduan Closure:** gambar dan bubble di halaman awal maupun login tahap kedua selalu tampil melayang dan tetap terlihat saat halaman digulir. Gambar Closure ditampilkan utuh; bubble dirapatkan hingga penandanya menyentuh gambar. Pada layar kecil, panduan diringkas dan diposisikan di sudut bawah.
- **Pratinjau webcam:** setelah webcam diaktifkan, pratinjau melayang tepat di bawah bubble Closure dan tetap terlihat saat halaman pendaftaran digulir.
- **Kembali ke biometrik:** dari login tahap kedua, tombol **Kembali ke verifikasi biometrik** mengakhiri tahap autentikasi perangkat saat ini dan membawa pengguna ke halaman verifikasi USB/wajah. Kedua faktor harus diverifikasi ulang sebelum login akun.
- **Dashboard:** Closure menyambut pengguna melalui bubble dialog dan menjelaskan cakupan akses akun; dashboard mendukung folder/file dengan izin per item. File lokal terletak di `storage/users/`, bukan sebagai BLOB SQLite.
- **Penyimpanan lokal akun:** pembuatan akun membuat folder `storage/users/account-{id}-{username}/`; konten file berada pada filesystem lokal dan SQLite hanya menyimpan metadata/izin. BLOB lama dimigrasikan saat database dibuka.
- **Super enkripsi teks:** implementasi Caesar → Vigenere → XOR → RSA-OAEP SHA-256, keluaran hex alfanumerik, pengelolaan key pair RSA 3072-bit, dan opsi menyimpan ciphertext sebagai `pesan_terenkripsi_{angka}.txt`.
- **Pesan terminal dan bubble:** status serta pesan panduan/error tetap dikirim ke terminal sebagai log `INFO` dan juga ditampilkan pada bubble Closure; perubahan UI tidak menghilangkan log terminal.
- **Login tahap kedua:** setelah verifikasi USB dan wajah, pengguna masuk atau mendaftar menggunakan username/password dengan hash Argon2id. Akun pertama menjadi admin; akun selanjutnya dapat mendaftar mandiri.
- **Multiakun dan izin:** dashboard menampilkan folder/file yang dapat diakses akun aktif, dengan izin buat/lihat/ubah yang dikelola terpisah per item. File saat ini dibatasi 10 MiB dan disimpan di filesystem lokal tanpa enkripsi.
