# Universal Secure Locker

Universal Secure Locker adalah prototipe aplikasi desktop brankas digital lokal untuk proyek Tugas Akhir Kriptografi.

## Fokus Tahap Awal

Login memiliki dua tahap:

1. **Kunci perangkat:** USB Flashdisk dan verifikasi wajah melalui webcam.
2. **Akun:** login atau pendaftaran dengan username dan password yang di-hash memakai Argon2id.

Setelah login, akun dapat membuat folder, mengunggah, melihat, mengunduh, dan memperbarui file. Setiap unduhan meminta password akun lagi. Data file berada di disk lokal pada folder akun, sedangkan SQLite menyimpan akun, metadata, dan izin. File database dienkripsi dengan AES-GCM ketika terkunci; sesudah USB dan wajah terverifikasi, aplikasi membukanya sebagai cache sementara. Catatan rahasia dan payload log transaksi juga dienkripsi sebelum disimpan ke tabelnya. Pemilik item atau admin membagikan izin **buat, lihat, dan ubah** secara terpisah untuk setiap folder atau file. Tidak ada akses otomatis ke item milik akun lain, termasuk bagi admin; admin dapat mengatur izin, tetapi tetap perlu izin item untuk membaca kontennya. Penghapusan item belum tersedia.

Closure tampil sebagai pemandu dengan bubble dialog yang menyambut pengguna dan memperbarui petunjuk sesuai tahap pendaftaran, verifikasi, atau akses dashboard.

## Login Akun dan Pembagian Akses

- Setelah USB dan wajah cocok, pilih **Buat akun** atau **Masuk**. Password minimal 10 karakter dan disimpan sebagai hash Argon2id di `storage/accounts.db`; password asli tidak disimpan.
- Akun pertama otomatis menjadi admin. Pendaftaran mandiri untuk akun berikutnya tetap tersedia, tetapi akun baru hanya dapat melihat file miliknya sendiri sampai pemilik atau admin memberinya izin.
- USB dan model wajah tetap menjadi lapisan perangkat bersama untuk instalasi lokal ini. Username/password tahap kedua menentukan akun dan izin data yang digunakan.
- Admin dapat mengatur izin pada item yang dikelola, tetapi status admin sendiri **tidak** memberikan akses baca ke seluruh isi vault. Pemilik file/folder juga dapat membagikan item miliknya.
- Hak akses ditetapkan pada tiap item dan tidak diwariskan. Untuk membuka file di dalam folder bersama, penerima perlu hak **lihat** pada seluruh folder induk dan hak **lihat** pada file tersebut. Untuk membuat item di folder bersama, penerima perlu hak **lihat** dan **buat** di folder itu.
- Hak **ubah** otomatis menyertakan hak **lihat**. Izin dapat dicabut dengan menghilangkan semua centang lalu menyimpan.
- Tombol **Lihat** membuka preview file. Untuk setiap unduhan, tekan **Unduh** di bagian atas preview lalu verifikasi dengan password akun; setelah itu dialog simpan native akan meminta lokasi file. Membatalkan dialog tidak menyimpan file. Password yang salah tidak mengirimkan file.
- Setiap akun memiliki folder lokal `storage/users/account-{id}-{username}/`. SQLite menyimpan metadata, hash password, dan izin; isi file berada pada filesystem lokal. Unggahan dibatasi 10 MiB.
- Password tetap di-hash Argon2id. `storage/accounts.db` dienkripsi AES-256-GCM dengan kunci yang dilindungi Windows DPAPI saat database terkunci; sesudah USB dan wajah lolos verifikasi, database dibuka ke file kerja sementara di direktori temporary OS, lalu file kerja dihapus saat database dikunci kembali. Cache ini bukan RAM-only: penghentian paksa dapat meninggalkan file sementara. API `save_secret_note`/`get_secret_notes` menyimpan isi catatan terenkripsi dalam SQLite. API `record_transaction` menambahkan payload terenkripsi ke rantai hash mini, dan `verify_transaction_chain` memeriksa integritas urutan tersebut.
- Dokumen umum (termasuk PDF, teks, dan video) dienkripsi saat disimpan dengan AES-256-GCM. Saat sesi akun terkunci, file di folder lokal berisi ciphertext; file asli hanya didekripsi dalam memori ketika pengguna membuka atau mengunduhnya lewat aplikasi. Gambar dengan ekstensi umum seperti PNG/JPG/GIF/WEBP sengaja tetap utuh/tidak dienkripsi.
- Folder dan file yang tampil di vault tetap memakai nama yang dipilih, sementara direktori fisiknya memakai ID resource untuk mencegah benturan nama/path. Kunci AES acak dilindungi Windows DPAPI untuk profil pengguna Windows ini, dan dibuka setelah login akun. Enkripsi ini melindungi file dari pembacaan langsung biasa melalui File Explorer, bukan dari malware/proses yang berjalan sebagai pengguna Windows yang sama atau akses administrator.
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
| Steganografi gambar | **Pillow** | Menyisipkan ciphertext heksadesimal ke bit LSB pada gambar PNG tanpa kompresi destruktif. |
| Enkripsi file dokumen | **AES-256-GCM (`cryptography`)** | Mengenkripsi dokumen pada filesystem; kunci acak dilindungi DPAPI Windows. Gambar dikecualikan. |
| Akun, izin, dan metadata | **SQLite melalui `sqlite3` bawaan Python** | Menyimpan akun, hash, metadata resource, dan izin per item di `storage/accounts.db`. |
| Audit log | **Mini-blockchain SHA-256 + SQLite** | Menyimpan blok aktivitas berantai di database lokal dan memvalidasi integritas rantai. |
| Konten file | **Filesystem lokal** | Menyimpan file di `storage/users/account-{id}-{username}/`; folder ini diabaikan Git. |
| Faktor perangkat | **JSON dan model OpenCV lokal** | Menyimpan hash token USB dan model wajah pada folder `storage/`. |

PyWebView dipilih daripada Electron atau API FastAPI/Flask agar tahap awal tetap ringan dan tidak membutuhkan server web terpisah.

### Super Enkripsi Teks

1. Masukkan Caesar shift (0–25) dan satu kunci alfanumerik ASCII sepanjang 12–128 karakter. Kunci yang sama digunakan untuk Vigenere dan XOR; simpan parameter ini agar dapat mendekripsi.
2. Buat key pair RSA 3072-bit atau tempel public/private key PEM yang cocok. Public key mengenkripsi, sedangkan private key hanya digunakan untuk dekripsi.
3. Enkripsi memproses teks UTF-8 maksimal 16 KiB dengan urutan Caesar → Vigenere → XOR → RSA-OAEP dengan SHA-256. Caesar/Vigenere hanya menggeser huruf Latin A–Z/a–z; XOR diterapkan pada byte UTF-8. RSA-OAEP menangani blok data, lalu hasilnya dikodekan sebagai teks heksadesimal (`0–9`, `a–f`).
4. Tempel ciphertext dan masukkan kembali shift, kunci bersama, serta private key yang cocok untuk mendekripsi. Untuk menyimpan, tekan **Simpan ciphertext sebagai .txt**; hanya ciphertext yang disimpan.
5. Key pair yang dibuat tidak disimpan aplikasi. Simpan private key di tempat aman dan jangan membagikannya. Jika hilang, ciphertext tidak dapat didekripsi.

Jangan memilih bilangan prima RSA 20–30 digit: ukuran tersebut terlalu kecil untuk keamanan RSA modern. Pembuatan key pair 3072-bit oleh pustaka kriptografi lebih tepat daripada memasukkan bilangan prima sendiri. Lapisan Caesar/Vigenere/XOR adalah algoritma klasik untuk demonstrasi dan tidak menambah keamanan RSA yang berarti; fitur ini tidak memberikan autentikasi/integritas ciphertext dan tidak menggantikan enkripsi file dengan skema terautentikasi seperti AES-GCM. Jangan gunakan sebagai satu-satunya perlindungan data penting.

### Steganografi Gambar

- Modul `backend/security/steganography.py` menyediakan `hide_message(image_path, secret_text, output_dir)` dan `reveal_message(image_path)`.
- Hanya PNG yang didukung. Fungsi sisip menolak teks biasa dan menerima payload dalam format heksadesimal seperti ciphertext dari super enkripsi. Fungsi ini memvalidasi format ciphertext, tetapi tidak dapat membuktikan bahwa string heksadesimal benar-benar dienkripsi; enkripsi harus dilakukan lebih dulu melalui fitur super enkripsi.
- Contoh pemakaian setelah memperoleh ciphertext di aplikasi:

  ```python
  from backend.security.steganography import hide_message, reveal_message

  result_path = hide_message("foto.png", ciphertext, "hasil")
  extracted_ciphertext = reveal_message(result_path)
  ```

- Kapasitas diperiksa sebelum menyisipkan. Tiap kanal warna RGB menyimpan satu bit dan nilai kanal berubah paling banyak satu; alpha dipertahankan. Maksimum ukuran gambar adalah 40 megapiksel dan payload dibatasi 64 KiB.
- Hasil disimpan langsung di folder tujuan dengan nama asli, misalnya `foto.png`. Jika nama sudah dipakai, digunakan `foto (1).png`, `foto (2).png`, dan seterusnya. Folder tujuan harus sudah ada.
- Halaman **Steganografi** tersedia dari tombol di dashboard. Halaman ini menyediakan formulir untuk menyisipkan ciphertext ke PNG (folder tujuan dipilih melalui dialog native) dan mengekstrak ciphertext kembali. Hanya akun yang sedang login yang dapat menggunakan API tersebut.
- Simpan hasil sebagai PNG. Mengubahnya ke JPG atau mengirimkannya melalui layanan yang mengubah ukuran/kompresi gambar dapat merusak pesan tersembunyi. LSB bukan perlindungan terhadap analisis steganografi; fitur ini bukan metode untuk menghindari pemantauan atau pemeriksaan keamanan.

### Audit Mini-Blockchain

- `backend/blockchain.py` menyediakan `MiniBlockchain(database_path)`, `add_audit_log(action_data)`, `get_chain()`, dan `is_chain_valid()`. Genesis Block dibuat otomatis saat tabel audit pertama kali diinisialisasi.
- Setiap blok menyimpan index, timestamp UTC, action data, previous hash, dan SHA-256 hash atas seluruh field tersebut. Blok tersimpan di tabel `blockchain_blocks` pada SQLite aplikasi. `blockchain_state` menyimpan head ledger agar penghapusan blok terakhir juga terdeteksi.
- Aplikasi mencatat aktivitas penting seperti verifikasi USB/wajah, login/logout, buka/simpan/perbarui file, unduh, izin, steganografi, catatan, dan enkripsi/dekripsi pesan. Isi pesan rahasia, password, ciphertext, dan kunci tidak ditambahkan ke audit log.
- Rantai lokal bersifat *tamper-evident*, bukan blockchain terdistribusi atau bukti anti-pemalsuan terhadap admin/proses yang dapat mengubah database dan seluruh head ledger sekaligus. Database aplikasi sendiri dienkripsi saat terkunci.

### Build Windows dengan PyInstaller

Build dilakukan pada Windows dan memasukkan seluruh folder `frontend/` ke executable. Resource statis dicari melalui `get_resource_path()` di `main.py`; data yang dapat ditulis seperti `storage/` tetap berada di folder yang sama dengan `.exe`, bukan di folder ekstraksi sementara PyInstaller.

1. Aktifkan virtual environment proyek.
2. Pasang dependensi aplikasi dan build:

   ```powershell
   python -m pip install -r requirements-build.txt
   ```

3. Buat executable `onefile` tanpa jendela terminal dengan satu perintah:

   ```powershell
   python -m PyInstaller --noconfirm --clean --onefile --windowed --name UniversalSecureLocker --add-data "frontend;frontend" --collect-all webview --collect-all cv2 --collect-all PIL --collect-all argon2 --collect-all cryptography main.py
   ```

   Konfigurasi yang sama tersedia di `UniversalSecureLocker.spec`; jalankan `build_windows.bat` atau `python -m PyInstaller --noconfirm --clean UniversalSecureLocker.spec`. Hasilnya ada di `dist/UniversalSecureLocker.exe`.

4. Salin `.exe` ke folder yang bisa ditulis oleh akun Windows yang menjalankannya. Aplikasi membuat `storage/` di sebelah `.exe` untuk database dan file akun. Jangan jalankan dari folder terlindungi seperti `Program Files` tanpa mengatur izin tulis.
5. Backup folder `storage/` secara aman dan sediakan Windows WebView2 Runtime pada komputer tujuan.

Opsi `--onefile` mengekstrak resource frontend ke direktori sementara saat mulai. Mode ini bukan perlindungan kode atau rahasia dari reverse engineering. Untuk startup lebih cepat dan pemeriksaan file lebih mudah, ganti `--onefile` dengan `--onedir`; konfigurasi spec juga dapat disesuaikan untuk distribusi folder.

### Enkripsi File Dokumen

- Modul `backend/security/file_crypto.py` menyediakan `FileEncryption.encrypt_file(path, key)` dan `FileEncryption.decrypt_file(path, key)` untuk pemakaian file langsung, serta fungsi bytes yang digunakan oleh storage aplikasi. Helper file langsung juga melewati gambar yang dikenali.
- Dokumen disimpan dengan format biner ber-header USL dan AES-256-GCM (nonce acak 12 byte + tag autentikasi). Isi ciphertext tidak bisa dibuka sebagai dokumen normal dari File Explorer. Aplikasi mendekripsinya di memori hanya saat permintaan baca; hasil unduhan dari aplikasi adalah file asli.
- File gambar umum (PNG, JPG/JPEG, GIF, BMP, TIFF, WEBP, HEIC/HEIF, atau MIME `image/*`) sengaja disimpan tanpa perubahan. File video dan jenis file lain dienkripsi.
- Kunci AES acak disimpan dalam keadaan terproteksi DPAPI pada `storage/file-encryption-key.dpapi`. Kunci dibuka setelah login akun, dan referensinya dilepas saat logout. Backup file ini bersama database dan folder `storage/users/`; kunci DPAPI terikat pada profil Windows/machine tempat kunci dibuat sehingga pemulihan ke profil atau komputer lain tidak otomatis tersedia.
- Saat aplikasi dimulai, dokumen lama yang masih plaintext dienkripsi otomatis; file gambar tetap dibiarkan seperti semula. Kunci segera dikunci kembali dan hanya dibuka setelah login. Jangan menghapus atau mengganti file kunci DPAPI, karena file terenkripsi tidak dapat dipulihkan tanpanya.
- File asli didekripsi hanya untuk preview atau unduhan melalui aplikasi. Hasil unduhan yang disimpan ke lokasi pilihan pengguna adalah salinan plaintext biasa; penyimpanan vault di `storage/users/` tetap ciphertext.
- Batas keamanan: DPAPI melindungi kunci terhadap akses file biasa dari pengguna Windows lain, tetapi bukan proses jahat yang berjalan sebagai pengguna Windows yang sama atau administrator. Metadata SQLite dan gambar yang dikecualikan tetap tidak dienkripsi. Fitur ini tidak membuat file terbaca di luar aplikasi hanya karena pengguna berhasil login; pembacaan di aplikasi mendekripsi saat diminta.

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

## Cara Menggunakan Fitur Aplikasi

### Brankas File dan Izin

1. Setelah login, gunakan **＋ Folder** untuk membuat folder. Masuk ke folder dengan memilihnya; gunakan **Kembali** untuk kembali ke folder utama.
2. Gunakan **＋ Unggah file** di dashboard untuk memilih file dari komputer. Ukuran unggahan maksimal 10 MiB. Dokumen umum dienkripsi di penyimpanan lokal; gambar yang didukung tetap tidak dienkripsi.
3. Pilih **Lihat** pada file untuk membuka pratinjau di dalam aplikasi. Untuk menyimpan salinan ke komputer, tekan **Unduh** di bagian atas pratinjau, masukkan password akun yang sedang login, lalu pilih lokasi pada dialog simpan. Unduhan adalah salinan plaintext; file di vault tetap terenkripsi.
4. Pemilik atau admin dapat menggunakan **Atur akses** pada item untuk memberikan izin **Lihat**, **Ubah**, atau—pada folder—**Buat** kepada akun lain. Izin tidak diwariskan: untuk melihat file dalam folder bersama, penerima perlu izin lihat pada folder induk dan file itu sendiri.
5. Untuk mengganti file, gunakan aksi **Ubah** pada item yang dapat diedit. Gunakan **Kunci aplikasi** untuk logout dan mengunci database serta kunci enkripsi.

### Enkripsi dan Dekripsi Pesan

1. Di dashboard, pada panel **Enkripsi berlapis**, tekan **Buat key pair RSA 3072-bit** atau masukkan key pair RSA PEM yang sudah dimiliki. Salin dan simpan private key dengan aman; aplikasi tidak menyimpannya.
2. Isi Caesar shift 0–25, kunci alfanumerik yang sama (12–128 karakter) untuk Vigenere dan XOR, public key RSA, lalu pesan plaintext. Tekan **Enkripsi berlapis**.
3. Tekan **Simpan ciphertext sebagai .txt** untuk menyimpan ciphertext ke folder akun sebagai `pesan_terenkripsi_{angka}.txt`; file akan muncul di daftar brankas. Hanya ciphertext yang disimpan.
4. Untuk dekripsi, tempel ciphertext, masukkan Caesar shift dan kunci yang sama, serta private key RSA yang cocok, lalu tekan **Dekripsi berlapis**.

### Steganografi PNG

1. Dari dashboard, buka halaman **Steganografi**.
2. Untuk menyisipkan pesan, pilih PNG, tempel ciphertext heksadesimal yang dihasilkan fitur enkripsi pesan, lalu tekan **Sisipkan & simpan PNG**. Pilih folder tujuan pada dialog folder native. Hasil memakai nama PNG sumber; jika sudah ada, aplikasi menambahkan `(1)`, `(2)`, dan seterusnya. Gambar hasil disimpan di folder tujuan yang dipilih, bukan otomatis ke vault.
3. Untuk membaca pesan, pilih PNG yang berisi pesan dan tekan **Ekstrak ciphertext**. Salin hasilnya, kembali ke dashboard, lalu gunakan panel dekripsi dengan parameter dan private key RSA yang sesuai.
4. Jangan mengubah hasil menjadi JPEG atau mengirimkannya melalui layanan yang mengompres/mengubah gambar karena data LSB dapat rusak.

### Menjalankan Versi Executable

Setelah build selesai, jalankan `dist\UniversalSecureLocker.exe` atau salin executable ke folder yang dapat ditulis lalu jalankan dari sana. Aplikasi membuat folder `storage/` di sebelah executable untuk data akun, database, dan file. Jangan menghapus `storage/file-encryption-key.dpapi`; file terenkripsi tidak dapat dipulihkan tanpanya. Untuk backup atau pemindahan, baca catatan enkripsi dan keterikatan kunci DPAPI pada bagian keamanan.

## Struktur Proyek

```text
universal-secure-locker/
├── backend/
│   ├── blockchain.py          # Rantai audit SHA-256 di SQLite
│   ├── database.py            # Akun, metadata resource, izin, catatan, dan ledger
│   ├── modules/
│   │   ├── blockchain_ledger.py
│   │   ├── locker_manager.py
│   │   └── steganography.py
│   ├── security/
│   │   ├── biometric_auth.py   # Pendaftaran dan verifikasi wajah
│   │   ├── crypto_engine.py    # Enkripsi/dekripsi pesan dan key RSA
│   │   ├── database_crypto.py  # Database terenkripsi saat terkunci
│   │   ├── dongle_auth.py      # Pendaftaran dan verifikasi USB
│   │   ├── file_crypto.py      # Enkripsi file AES-GCM
│   │   ├── file_key_store.py   # Penyimpanan kunci file dengan DPAPI
│   │   └── steganography.py    # Sisip/ekstrak ciphertext pada PNG
├── frontend/
│   ├── index.html              # Verifikasi perangkat dan login/daftar
│   ├── dashboard.html          # Brankas, enkripsi/dekripsi pesan
│   ├── steganography.html      # Sisip dan ekstrak ciphertext PNG
│   ├── assets/
│   │   └── img/
│   │       └── Closure_2.png
│   ├── css/
│   │   └── style.css           # Tampilan semua halaman
│   └── js/
│       ├── api.js              # Bridge pemanggilan API Python
│       ├── app.js              # Interaksi UI dan alur aplikasi
│       └── webcam.js           # Akses pratinjau webcam
├── storage/                    # Data lokal runtime; diabaikan Git
│   ├── accounts.db             # Database terenkripsi saat aplikasi terkunci
│   ├── auth_config.json        # Konfigurasi/hash token USB
│   ├── face_model.yml          # Model pengenalan wajah
│   ├── file-encryption-key.dpapi
│   └── users/
│       └── account-{id}-{username}/
│                               # File akun dan ciphertext dokumen
├── main.py                     # Aplikasi desktop, API, dan resource path
├── UniversalSecureLocker.spec  # Konfigurasi PyInstaller
├── build_windows.bat           # Perintah build Windows
├── requirements.txt            # Dependensi aplikasi
├── requirements-build.txt      # Dependensi aplikasi + PyInstaller
├── tests/
│   ├── test_account_api.py
│   ├── test_account_database.py
│   ├── test_blockchain.py
│   ├── test_crypto_engine.py
│   ├── test_database_crypto.py
│   ├── test_file_crypto.py
│   └── test_steganography.py
├── .gitignore
├── dokumen_perancangan_project_akhir_kriptografi.md
└── README.md
```

Folder `.venv/`, `build/`, `dist/`, cache Python, serta `storage/` adalah folder lokal/runtime dan diabaikan Git. File di bawah `storage/` dibuat saat aplikasi digunakan; beberapa file baru muncul setelah pendaftaran wajah/USB atau pembuatan akun.

Rincian latar belakang dan rancangan keseluruhan terdapat di [dokumen perancangan proyek](./dokumen_perancangan_project_akhir_kriptografi.md).

## Catatan Keamanan dan Batasan

- Ini adalah **demonstrasi autentikasi**, bukan sistem keamanan siap produksi. Jangan gunakan untuk melindungi data penting.
- File token USB adalah rahasia statis. Orang yang dapat menyalinnya dapat menduplikasi kunci; serial perangkat dan pendeteksian drive juga bukan bukti USB yang tahan manipulasi.
- Pendaftaran USB tidak menjalankan proses format. Aplikasi hanya membuat file token baru di folder utama USB yang dipilih. File yang sudah ada tidak ditimpa; jika file token dengan nama yang sama sudah ada, pendaftaran dibatalkan.
- LBPH merupakan pengenal wajah sederhana, bukan sistem biometrik modern yang tahan spoofing. Prototipe ini tidak memiliki deteksi keaktifan (*liveness detection*), sehingga foto/video dapat berisiko mengecoh verifikasi. Nilai ambang pengenalan perlu diuji pada kondisi kamera yang beragam.
- Model wajah dan konfigurasi disimpan lokal tanpa enkripsi pada tahap ini. Amankan komputer dan jangan membagikan folder `storage/`.
- Hash password tidak dapat mengembalikan password asli. Dokumen umum dienkripsi AES-GCM saat tersimpan; database terenkripsi saat terkunci, sementara catatan dan payload transaksi mini-ledger dienkripsi pada kolom. Database kerja sementara tersedia saat aplikasi telah lolos USB dan wajah, sehingga malware atau proses yang berjalan sebagai pengguna Windows yang sama tetap dapat mengakses data selama sesi. Gambar yang dikecualikan dari enkripsi file tetap tidak dienkripsi. Amankan komputer dan backup folder `storage/` dengan hati-hati.
- Izin akun berlaku saat mengakses aplikasi. Pengguna dengan akses OS langsung ke folder `storage/` dapat mengubah atau menghapus file; database memakai AES-GCM saat terkunci dan catatan transaksi memakai rantai hash, tetapi rantai hash lokal bukan blockchain terdistribusi dan bukan perlindungan terhadap admin/malware yang dapat mengubah database saat aplikasi terbuka.
- Kamera hanya digunakan melalui aplikasi lokal; frame tidak dikirim ke layanan internet.
- Dashboard menyimpan konten file pada `storage/users/` dan metadata/izin/audit pada database SQLite. Saat aplikasi diperbarui, BLOB file lama yang masih berada di database akan dipindahkan otomatis ke folder akun; startup mengenkripsi dokumen lama. Backup database, `storage/users/`, dan `storage/file-encryption-key.dpapi` bersama-sama.
- Super enkripsi teks sudah tersedia dengan urutan Caesar → Vigenere → XOR → RSA-OAEP. Implementasi ini untuk pembelajaran, bukan pengganti enkripsi file/database atau enkripsi terautentikasi.
- Gunakan pustaka kriptografi teruji untuk fitur produksi. AES-GCM untuk enkripsi terautentikasi dan Argon2id untuk hash password; jangan mengimplementasikan algoritma kriptografi sendiri.

## Perubahan Tampilan Terbaru

- **Halaman awal:** gambar Closure ditampilkan sebagai pemandu di samping bubble dialog, bukan sebagai logo. Instruksi dialog berubah mengikuti proses pendaftaran dan verifikasi.
- **Panduan Closure:** gambar dan bubble di halaman awal maupun login tahap kedua selalu tampil melayang dan tetap terlihat saat halaman digulir. Gambar Closure ditampilkan utuh; bubble dirapatkan hingga penandanya menyentuh gambar. Pada layar kecil, panduan diringkas dan diposisikan di sudut bawah.
- **Pratinjau webcam:** setelah webcam diaktifkan, pratinjau melayang tepat di bawah bubble Closure dan tetap terlihat saat halaman pendaftaran digulir.
- **Kembali ke biometrik:** dari login tahap kedua, tombol **Kembali ke verifikasi biometrik** mengakhiri tahap autentikasi perangkat saat ini dan membawa pengguna ke halaman verifikasi USB/wajah. Kedua faktor harus diverifikasi ulang sebelum login akun.
- **Dashboard:** Closure menyambut pengguna melalui bubble dialog dan menjelaskan cakupan akses akun; dashboard mendukung folder/file dengan izin per item. File lokal terletak di `storage/users/`, bukan sebagai BLOB SQLite.
- **Penyimpanan lokal akun:** pembuatan akun membuat folder `storage/users/account-{id}-{username}/`; konten file berada pada filesystem lokal dan SQLite hanya menyimpan metadata/izin. BLOB lama dimigrasikan saat database dibuka.
- **Enkripsi dokumen:** file non-gambar dienkripsi dengan AES-256-GCM saat disimpan dan hanya didekripsi di memori saat dibuka/diunduh lewat aplikasi; kuncinya dilindungi Windows DPAPI. Gambar tetap tidak dienkripsi.
- **Super enkripsi teks:** implementasi Caesar → Vigenere → XOR → RSA-OAEP SHA-256, keluaran hex alfanumerik, pengelolaan key pair RSA 3072-bit, dan opsi menyimpan ciphertext sebagai `pesan_terenkripsi_{angka}.txt`.
- **Pesan terminal dan bubble:** status serta pesan panduan/error tetap dikirim ke terminal sebagai log `INFO` dan juga ditampilkan pada bubble Closure; perubahan UI tidak menghilangkan log terminal.
- **Login tahap kedua:** setelah verifikasi USB dan wajah, pengguna masuk atau mendaftar menggunakan username/password dengan hash Argon2id. Akun pertama menjadi admin; akun selanjutnya dapat mendaftar mandiri.
- **Multiakun dan izin:** dashboard menampilkan folder/file yang dapat diakses akun aktif, dengan izin buat/lihat/ubah yang dikelola terpisah per item. File saat ini dibatasi 10 MiB; dokumen dienkripsi lokal, gambar dikecualikan.
