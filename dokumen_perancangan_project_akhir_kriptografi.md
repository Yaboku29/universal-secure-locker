# Dokumen Perancangan Project Akhir Kriptografi
## **Universal Secure Locker (Brankas Digital Terenkripsi)**

---

## 1. Penjelasan Project & Latar Belakang

### 1.1 Penjelasan Project
**Universal Secure Locker** adalah aplikasi brankas digital desktop berbasis lokal yang dirancang untuk menyimpan dan mengamankan berbagai jenis aset digital—mulai dari catatan teks rahasia, dokumen (PDF/Word/Excel), hingga file gambar. 

Aplikasi ini tidak sekadar menyimpan file, melainkan mengintegrasikan skema keamanan *multi-layer* yang menggabungkan verifikasi fisik (*hardware dongle*), biometrik wajah, super enkripsi data, steganografi, hingga pencatatan transaksi aset berbasis *blockchain* sederhana.

### 1.2 Latar Belakang & Permasalahan
Di era digital saat ini, penyimpanan data lokal di komputer pribadi masih rentan terhadap akses tanpa izin (*unauthorized access*). Jika sebuah laptop dipinjam, dicuri, atau diakses oleh pihak luar, file yang tersimpan di direktori lokal umumnya dapat dibaca secara langsung (*plain text*).

Untuk mengatasi masalah ini, dibutuhkan sebuah sistem penyimpanan lokal yang:
1. **Tidak dapat dijalankan** tanpa otorisasi perangkat fisik (dongle USB) dan pemilik sah (biometrik wajah).
2. **Tidak dapat dibaca langsung dari sistem file** karena seluruh data dan metadatanya telah mengalami proses enkripsi matematika.
3. **Memiliki jejak audit yang terjamin integritasnya** sehingga data yang telah disimpan tidak dapat dimanipulasi secara ilegal tanpa terdeteksi.

---

## 2. Fitur Utama & Kebutuhan Spesifikasi (Kriteria Tugas Akhir)

Aplikasi ini dirancang untuk memenuhi seluruh kriteria Tugas Akhir Kriptografi sebagai berikut:

| No | Kriteria Tugas Akhir | Implementasi pada Universal Secure Locker |
|---|---|---|
| 1 | **Login Biometrik & Dongle** | Aplikasi hanya dapat dibuka jika USB Flashdisk khusus (dongle) terdeteksi di port USB **DAN** verifikasi wajah pengguna via webcam berhasil. Memiliki modul *recovery mode* pendaftaran dongle baru dengan verifikasi biometrik ketat. |
| 2 | **Login Kriptografi** | Kredensial akun utama diamankan di basis data menggunakan algoritma *hashing* terstandar (SHA-256 / Argon2). |
| 3 | **Super Enkripsi Teks** | Pesan teks diproses berurutan dengan Caesar, Vigenere, XOR, lalu RSA-OAEP SHA-256. Implementasi Caesar/Vigenere/XOR ini untuk demonstrasi akademik dan bukan pengganti skema enkripsi terautentikasi untuk data produksi. |
| 4 | **Enkripsi File** | File dokumen (PDF, DOCX, XLSX, dll.) dienkripsi menggunakan algoritma *file cipher* mandiri (seperti RSA atau Blowfish/AES-GCM) yang berbeda dari enkripsi teks. |
| 5 | **Enkripsi Database** | Seluruh data sensitif dan metadata file yang tersimpan di dalam basis data lokal (SQLite) tersimpan dalam bentuk *ciphertext*. |
| 6 | **Steganografi Gambar** | Modul khusus untuk menyembunyikan pesan teks rahasia atau kode *recovery* ke dalam file gambar (PNG/JPG) menggunakan teknik *Least Significant Bit* (LSB). |
| 7 | **Blockchain Sederhana** | Setiap aktivitas pembuatan, pengubahan, atau penghapusan aset di dalam brankas dicatat ke dalam *ledger* berantai (*blockchain* mini berbasis SHA-256) untuk menjamin immutability log. |

---

## 3. Perkiraan Tech Stack (HTML/CSS UI + Python Engine)

### Catatan RSA untuk Super Enkripsi Teks

RSA menggunakan pasangan public/private key yang dibuat oleh pustaka kriptografi (minimal 3072-bit pada aplikasi), bukan pilihan bilangan prima 20–30 digit. Bilangan prima dengan panjang tersebut menghasilkan modulus yang terlalu kecil dan tidak aman. Public key digunakan untuk enkripsi; hanya private key pasangannya yang dapat mendekripsi. Private key wajib dicadangkan pengguna secara aman karena aplikasi tidak menyimpannya.

Untuk mendapatkan tampilan UI/UX yang sangat fleksibel (berbasis HTML/CSS/JS) namun tetap mempertahankan keandalan pemrosesan kriptografi Python, *tech stack* yang direkomendasikan adalah:

### **Frontend (UI/UX - Fleksibel)**
* **HTML5 & CSS3:** Untuk penataan tata letak (*layout*) brankas digital yang modern, responsif, dan fleksibel.
* **Tailwind CSS / Bootstrap:** (Opsional) Framework CSS untuk mempercepat pembuatan komponen antarmuka.
* **JavaScript (Vanilla / React / Vue):** Memproses interaksi UI, menangkap *stream* kamera webcam, dan melakukan *fetching* data ke backend lokal.

### **Desktop Wrapper / Bridge**
* **PyWebView / Electron / Tauri:** Membawa antarmuka HTML/CSS ke dalam aplikasi desktop native tanpa memerlukan browser eksternal. *PyWebView* adalah opsi paling ringan karena langsung menjembatani kode JavaScript di HTML dengan fungsi Python.

### **Backend & Engine Kriptografi (Python)**
* **Python 3.x:** Bahasa utama penanganan logika bisnis dan enkripsi.
* **FastAPI / Flask (Lokal API):** Server web lokal ringan penyedia endpoint API antara Frontend HTML dan Backend Python.
* **`cryptography` & `pycryptodome`:** Modul untuk enkripsi AES, RSA, dan *hashing*.
* **`opencv-python` & `face_recognition`:** Modul untuk menangkap *stream* kamera dan ekstrasi fitur biometrik wajah.
* **`psutil` / `wmi`:** Modul untuk membaca status port USB dan mengidentifikasi Serial Number / Key-File pada Dongle Flashdisk.
* **`sqlite3`:** Basis data lokal ringan.
* **`Pillow` (PIL):** Pemrosesan gambar untuk steganografi LSB.

---

## 4. Struktur Arsitektur & Folder Proyek

```text
universal_secure_locker/
│
├── backend/                      # Engine Python & Logika Bisnis
│   ├── app.py                    # Main Server API lokal (FastAPI / Flask)
│   ├── database.py               # Pengelolaan koneksi & enkripsi database SQLite
│   │
│   ├── security/                 # Modul Keamanan Tambahan
│   │   ├── dongle_auth.py        # Validasi USB Flashdisk & Serial ID
│   │   ├── biometric_auth.py     # Pengenalan & pencocokan wajah (Webcam)
│   │   └── crypto_engine.py      # Implementasi Super Enkripsi, AES, & File Cipher
│   │
│   └── modules/                  # Modul Fitur Aplikasi
│       ├── locker_manager.py     # Manajemen enkripsi/dekripsi simpan file
│       ├── steganography.py      # Modul LSB sisip & ekstrak pesan di gambar
│       └── blockchain_ledger.py  # Rantai blok (block hashing) log transaksi
│
├── frontend/                     # UI/UX berbasis HTML/CSS/JS
│   ├── index.html                # Halaman Login (Dongle Check & Face Scan)
│   ├── dashboard.html            # Dasbor Utama Brankas File & Catatan
│   ├── css/
│   │   └── style.css             # Styling UI Brankas
│   └── js/
│       ├── app.js                # Interaksi UI dasar
│       ├── webcam.js             # Penanganan feed kamera biometrik
│       └── api.js                # Komunikasi ke Backend Python
│
├── storage/                      # Folder Penyimpanan Lokal (Terenkripsi)
│   ├── vault.db                  # File SQLite (isi terenkripsi)
│   ├── encrypted_files/          # Tempat menyimpan file terenkripsi (.bin)
│   └── blockchain.json           # File catatan ledger blockchain mini
│
├── main.py                       # Launcher utama (Menjalankan Backend + PyWebView UI)
└── requirements.txt              # Daftar pustaka Python yang dibutuhkan
```

---

## 5. Alur Pemakaian Aplikasi (User Flow)

1. **Aplikasi Dijalankan:**
   * Antarmuka HTML terbuka menunjukkan status *"Memeriksa Perangkat Keamanan..."*.
   * Backend Python mengecek keberadaan USB Dongle. Jika tidak ditemukan, layar menampilkan peringatan dan aplikasi terkunci.
2. **Autentikasi Ganda:**
   * Jika Dongle valid, halaman HTML mengaktifkan modul webcam.
   * Pengguna melakukan pemindaian wajah. Jika cocok, sistem meminta masukan *password* utama.
3. **Akses Dasbor Utama:**
   * Pengguna masuk ke halaman utama brankas (HTML/CSS).
   * Pengguna dapat memilih fitur: **Simpan Catatan Teks** (Super Enkripsi), **Unggah File Dokumen** (Enkripsi File), **Steganografi Gambar**, atau **Lihat Riwayat Blockchain**.
4. **Proses Penyimpanan & Logging:**
   * Ketika pengguna menyimpan file/catatan baru, Python akan mengenkripsi file tersebut dan menyimpannya di folder `encrypted_files/`.
   * Metadata pencatatan disimpan ke `vault.db` dalam keadaan terenkripsi.
   * Sebuah blok baru ditambahkan ke `blockchain.json` yang memuat hash transaksi terbaru.