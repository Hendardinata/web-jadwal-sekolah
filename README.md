# Web Jadwal Sekolah (School Scheduling Web Application)

Aplikasi berbasis web untuk otomatisasi penyusunan jadwal mata pelajaran sekolah menggunakan **Algoritma Genetika (Genetic Algorithm)**. Aplikasi ini dibangun dengan **Flask (Python)** dan menggunakan **MongoDB** sebagai basis data.

Aplikasi ini bertujuan untuk memudahkan admin atau bagian kurikulum dalam menyusun jadwal pelajaran yang bebas dari bentrok (conflict-free), mendukung jam pelajaran berurutan, mengakomodasi preferensi waktu mengajar guru, serta menyediakan antarmuka manajemen jadwal secara manual jika diperlukan.

## 🌟 Fitur Utama

1. **Autentikasi & Multi-Role Akses:**
   - Mendukung login dengan 3 role berbeda: **Admin**, **Guru**, dan **Siswa** (dengan hak akses masing-masing).
2. **Dashboard Interaktif:**
   - Menampilkan statistik jadwal seperti jumlah kelas, mapel, guru, jadwal pagi vs siang, dan distribusi mata pelajaran.
3. **Manajemen Master Data:**
   - **CRUD Kelas:** Tambah, edit, dan hapus data kelas.
   - **CRUD Mata Pelajaran (Mapel):** Tambah mapel beserta bobot pelajaran (misal: berat/sedang).
   - **CRUD Guru:** Tambah, edit, hapus data guru.
   - **Manajemen Guru Pengampu:** Menetapkan guru untuk mengajar mata pelajaran tertentu di kelas tertentu.
4. **Penyusunan Jadwal Otomatis (Algoritma Genetika):**
   - Menghasilkan jadwal secara otomatis dengan meminimalisir bentrokan (waktu mengajar guru bersamaan, satu kelas dua mapel, dll).
   - Mendukung **Jam Berurutan** (Misal: 2 jam pelajaran berturut-turut untuk satu mapel).
   - Mempertimbangkan **Preferensi Guru** (Guru hanya bisa mengajar di hari/jam tertentu).
   - Mempertimbangkan waktu non-akademik (waktu istirahat).
5. **Manajemen Jadwal Manual & Lock System:**
   - Memungkinkan admin untuk memodifikasi jadwal yang sudah di-generate (edit guru/mapel pada slot tertentu).
   - Fitur **Lock Slot**: Mengunci jadwal tertentu agar tidak berubah saat algoritma genetika dijalankan kembali.
6. **Ekspor & Cetak:**
   - Aplikasi menggunakan library seperti `pandas`, `fpdf2`, `weasyprint`, dan `XlsxWriter` untuk keperluan ekspor jadwal ke format Excel atau PDF.

---

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask
- **Database:** MongoDB
- **Algoritma:** Algoritma Genetika (Genetic Algorithm) dalam Python (`ga.py`)
- **Frontend:** HTML5, CSS3, Jinja2 Templates
- **Libraries Tambahan:** `pymongo`, `pandas`, `XlsxWriter`, `WeasyPrint`, `fpdf2`

---

## ⚙️ Persyaratan (Prerequisites)

Sebelum menjalankan aplikasi, pastikan Anda telah menginstal:
1. [Python](https://www.python.org/downloads/) (Disarankan versi 3.8 ke atas)
2. [MongoDB](https://www.mongodb.com/try/download/community) (Berjalan secara lokal di port `27017`)
3. Git (opsional, untuk clone repository)

---

## 🚀 Cara Instalasi

1. **Clone Repository:**
   ```bash
   git clone https://github.com/Hendardinata/web-jadwal-sekolah.git
   cd web-jadwal-sekolah
   ```

2. **Buat dan Aktifkan Virtual Environment (Disarankan):**
   - Di Windows:
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - Di macOS/Linux:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install Dependensi:**
   Instal semua library yang dibutuhkan melalui `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

4. **Pastikan MongoDB Berjalan:**
   Pastikan service MongoDB sudah berjalan di perangkat Anda (`mongodb://localhost:27017/`). Aplikasi secara otomatis akan membuat database bernama `jadwal_db`.

---

## 💻 Cara Menjalankan & Penggunaan

1. **Jalankan Aplikasi:**
   Jalankan file utama `app.py`:
   ```bash
   python app.py
   ```
   Aplikasi akan berjalan di `http://127.0.0.1:5000/`.

2. **Login Default:**
   Buka browser dan akses alamat di atas. Gunakan kredensial berikut untuk login:
   - **Admin**
     - Username: `admin`
     - Password: `admin123`
   - **Guru**
     - Username: `guru`
     - Password: `guru`
   - **Siswa**
     - Username: `siswa`
     - Password: `siswa`

3. **Langkah Penggunaan untuk Admin (Curriculum):**
   - **Langkah 1:** Buka menu **Manajemen Kelas**, **Mata Pelajaran**, dan **Guru** untuk memasukkan data master.
   - **Langkah 2:** Tetapkan **Guru Pengampu** (Guru A mengajar Mapel B di Kelas C, D).
   - **Langkah 3:** Masukkan preferensi jadwal guru atau set jam berurutan pada menu Manajemen Jadwal (jika diperlukan).
   - **Langkah 4:** Jalankan proses *Generate* Jadwal (menggunakan Algoritma Genetika). Algoritma akan mencari jadwal dengan nilai kebugaran (fitness) terbaik untuk menghindari bentrok.
   - **Langkah 5:** Jika ada jadwal khusus yang harus tetap (tidak boleh digeser), gunakan fitur **Lock Slot**. Jika diperlukan, Anda dapat mengubah jadwal secara manual.

---

## 🧬 Penjelasan Algoritma Genetika

Aplikasi ini menggunakan Algoritma Genetika di file `ga.py` untuk mengoptimasi penjadwalan:
- **Kromosom (Chromosome):** Merepresentasikan satu full jadwal (Kombinasi Kelas, Hari, Waktu, Mapel, Guru).
- **Populasi:** Sekumpulan alternatif jadwal.
- **Fitness Function (Fungsi Kebugaran):** Menilai seberapa bagus jadwal. Skor berkurang (penalti) jika ada konflik seperti:
  - Guru mengajar di dua kelas bersamaan.
  - Kelas memiliki dua mata pelajaran bersamaan.
  - Mata pelajaran berat di jam rawan (penalti bobot).
  - Melanggar preferensi guru.
- **Crossover & Mutasi:** Menciptakan variasi jadwal baru dari jadwal yang sudah baik. Slot yang dikunci (locked) tidak akan dimutasi.

---

## 🤝 Kontribusi

Pull requests dipersilakan. Untuk perubahan besar, harap buka issue terlebih dahulu untuk mendiskusikan apa yang ingin Anda ubah.

## 📝 Lisensi

[MIT](https://choosealicense.com/licenses/mit/)
