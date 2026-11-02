# Universal Secure Locker

Universal Secure Locker adalah rancangan aplikasi brankas digital desktop yang menyimpan catatan dan file secara lokal dalam bentuk terenkripsi. Proyek ini ditujukan sebagai prototipe Tugas Akhir Kriptografi, dengan antarmuka web lokal dan engine keamanan berbasis Python.

> **Status:** Dokumen perancangan/prototipe. Fitur autentikasi, enkripsi, dan pemulihan perlu diuji serta ditinjau sebelum digunakan untuk menyimpan data penting.

## Stack yang Dipilih

Stack berikut dipilih agar aplikasi tidak memerlukan server terpisah, framework frontend besar, atau basis data eksternal.

| Bagian | Teknologi | Alasan |
|---|---|---|
| Desktop dan penghubung UI | **PyWebView** | Membuka UI HTML dalam jendela desktop dan menghubungkan JavaScript ke fungsi Python tanpa API server lokal. |
| Antarmuka | **HTML5, CSS3, JavaScript vanilla** | Ringan, mudah dipelajari, dan tidak membutuhkan proses build frontend. |
| Engine aplikasi | **Python 3.11 atau lebih baru** | Ekosistem pustaka kriptografi dan pengolahan file yang matang. |
| Enkripsi | **`cryptography` (AES-256-GCM)** | Enkripsi terautentikasi untuk menjaga kerahasiaan sekaligus mendeteksi perubahan ciphertext. |
| Hash password | **`argon2-cffi` (Argon2id)** | Hash password yang dirancang untuk memperlambat serangan tebak password offline. |
| Database | **SQLite melalui modul bawaan `sqlite3`** | Penyimpanan lokal tanpa server dan tanpa dependensi database tambahan. |
| Pengolahan gambar | **Pillow** | Membaca dan mengubah gambar untuk eksperimen steganografi LSB. |
| Autentikasi wajah (opsional) | **OpenCV** | Akses webcam dan eksperimen pengenalan wajah tanpa dependensi model `dlib` yang berat. |

PyWebView menghubungkan tampilan dan Python secara langsung. Karena itu, rancangan awal tidak memerlukan FastAPI/Flask, React/Vue, Tailwind/Bootstrap, atau Electron. Pilihan tersebut dapat ditinjau kembali jika proyek nantinya membutuhkan API terpisah atau antarmuka yang lebih kompleks.

## Fitur yang Direncanakan

- **Autentikasi berlapis:** pemeriksaan dongle USB, verifikasi wajah, dan password utama.
- **Catatan rahasia:** enkripsi dan dekripsi teks saat disimpan dan dibuka.
- **File locker:** menyimpan file sebagai ciphertext dan mengembalikannya setelah autentikasi.
- **Database lokal:** menyimpan metadata vault di SQLite.
- **Steganografi gambar:** eksperimen menyisipkan dan mengambil pesan dari gambar.
- **Audit log berantai:** mencatat hash transaksi untuk membantu mendeteksi perubahan pada riwayat.

## Kebutuhan Sistem

- Windows 10/11 64-bit (target pengembangan awal).
- Python 3.11 atau lebih baru, dengan `pip`.
- Microsoft Edge WebView2 Runtime untuk jendela PyWebView.
- Webcam dan dongle USB untuk menguji alur autentikasi terkait.
- Ruang penyimpanan lokal untuk database dan file terenkripsi.

Fitur inti dapat dikembangkan tanpa webcam atau dongle fisik; keduanya diperlukan untuk menguji alur autentikasi lengkap. Fitur wajah dapat membutuhkan dependensi tambahan sesuai implementasi dan platform.

## Instalasi dan Menjalankan

Pastikan WebView2 Runtime sudah tersedia, lalu jalankan perintah berikut dari folder proyek di PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pywebview cryptography argon2-cffi Pillow
python main.py
```

Jika PowerShell menolak aktivasi environment virtual, jalankan perintah aktivasi yang sesuai dengan kebijakan lokal atau gunakan Python dari environment virtual secara langsung. Tambahkan OpenCV jika modul autentikasi wajah sedang dikembangkan:

```powershell
python -m pip install opencv-contrib-python
```

Perintah `python main.py` baru dapat digunakan setelah launcher dan modul aplikasi tersedia. Saat ini repositori berisi dokumen perancangan; langkah di atas merupakan setup yang dituju untuk implementasi.

## Struktur Proyek yang Disarankan

```text
universal-secure-locker/
├── backend/
│   ├── database.py
│   ├── security/
│   │   ├── crypto_engine.py
│   │   ├── dongle_auth.py
│   │   └── biometric_auth.py
│   └── modules/
│       ├── locker_manager.py
│       ├── steganography.py
│       └── blockchain_ledger.py
├── frontend/
│   ├── index.html
│   ├── dashboard.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── webcam.js
│       └── api.js
├── storage/
│   └── encrypted_files/
├── main.py
└── README.md
```

`storage/` berisi data runtime lokal dan sebaiknya tidak dimasukkan ke version control. Modul `api.js` pada struktur ini hanya menangani komunikasi frontend ke API Python yang diekspos PyWebView, bukan server HTTP.

## Catatan Keamanan dan Batasan

- Gunakan **AES-GCM** untuk data teks maupun file; jangan membuat algoritma enkripsi sendiri. AES-GCM juga memeriksa integritas ciphertext saat dekripsi.
- Password tidak dienkripsi atau disimpan sebagai SHA-256 biasa. Simpan hash Argon2id dengan salt unik. Jika enkripsi memakai kunci turunan password, gunakan skema derivasi kunci yang sesuai dan parameter yang dapat diperbarui.
- Dongle sebaiknya membawa token rahasia acak yang diverifikasi secara aman. Serial number atau nama drive saja mudah ditiru dan bukan bukti kepemilikan yang kuat.
- Verifikasi wajah dari webcam dapat salah mengenali atau menolak pengguna, dan foto/video dapat menipu sistem sederhana. Perlakukan sebagai lapisan tambahan, bukan pengganti password atau kunci kriptografi.
- Steganografi hanya menyamarkan keberadaan pesan; **tidak mengenkripsi** pesan. Enkripsi pesan terlebih dahulu sebelum menyisipkannya.
- Blockchain lokal berbasis hash membantu mendeteksi perubahan pada rantai yang masih utuh, tetapi tidak menjamin immutability jika penyerang dapat mengubah atau mengganti seluruh file ledger.
- Enkripsi database harus mencakup data sensitif dan metadata yang relevan. SQLite standar tidak mengenkripsi file database secara otomatis.
- Jangan menyimpan password, kunci, token dongle, data wajah, file pengguna, atau isi vault di repository. Sediakan prosedur backup dan pemulihan kunci sebelum digunakan untuk data nyata.

## Dokumen Perancangan

Rincian latar belakang, kriteria tugas akhir, serta alur penggunaan terdapat di [dokumen perancangan proyek](./dokumen_perancangan_project_akhir_kriptografi.md).
