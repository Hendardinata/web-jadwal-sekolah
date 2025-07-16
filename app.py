from flask import Flask, render_template, request, redirect, send_file, jsonify, flash, session, url_for
from pymongo import MongoClient
from ga import run_ga, evaluate_fitness
from fpdf import FPDF
import pandas as pd
from functools import wraps
from flask import abort
import datetime
import io
import os

app = Flask(__name__)

# Mengatur direktori template dan static
app.template_folder = 'templates'

# Mengatur app.static_folder 
app = Flask(__name__, template_folder='templates/pages', static_folder='templates/assets')

app.secret_key = 'sma_6_mataram'

# Koneksi ke MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['jadwal_db']
guru_mapel_collection = db['mapel']
guru_collection = db['guru']
kelas_collection = db["kelas"]
locked_slots_collection = db['locked_slots']
status_collection = db['status']
jadwal_final_collection = db['final_jadwal']

#------------------------------------------------------
#                    MIDDLERWARE
#------------------------------------------------------

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            role = session.get('role')
            if role not in allowed_roles:
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

#------------------------------------------------------
#                FITUR LOGIN & lOGOUT
#------------------------------------------------------

users = {
    "admin": {"password": "admin123", "role": "admin"},
    "guru": {"password": "guru", "role": "guru"},
    "siswa": {"password": "siswa", "role": "siswa"}
}

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = users.get(username)
        if user and user['password'] == password:
            session['username'] = username
            session['role'] = user['role']  # Simpan role di session
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'danger')
            return redirect(url_for('login'))

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

#------------------------------------------------------
#                           DASHBOARD
#------------------------------------------------------

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    semua_kelas = list(db.kelas.find())
    semua_mapel = list(db.mapel.find())
    semua_guru = list(db.guru.find())
    semua_jadwal = list(db.jadwal.find())

    return render_template(
        "dashboard.html",
        semua_kelas=semua_kelas,
        semua_mapel=semua_mapel,
        semua_guru=semua_guru,
        jumlah_kelas=len(semua_kelas),
        jumlah_mapel=len(semua_mapel),
        jumlah_guru=len(semua_guru),
        total_jadwal=len(semua_jadwal),
        title="Dashboard",
        username=session['username']
    )

#------------------------------------------------------
#                       JADWAL
#------------------------------------------------------

@app.route('/jadwal', methods=['GET', 'POST'])
def jadwal():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        mapel = request.form['mapel']
        guru = request.form['guru']
        kelas_ajar = request.form.getlist('kelas_ajar')
        pref_raw = request.form.getlist('preferensi')
        preferensi = [[h, s] for h_s in pref_raw for h, s in [h_s.split('|')]]

        guru_mapel_collection.update_one(
            {"mapel": mapel},
            {"$addToSet": {"guru": guru}},
            upsert=True
        )

        guru_collection.update_one(
            {"guru": guru},
            {"$set": {
                "kelas_ajar": kelas_ajar,
                "preferensi": preferensi
            }},
            upsert=True
        )
        return redirect('/')

    guru_mapel_data = {doc['mapel']: doc.get('guru', []) for doc in guru_mapel_collection.find()}
    preferensi_map = {doc['guru']: doc.get('preferensi', []) for doc in guru_collection.find()}
    guru_kelas_map = {doc['guru']: doc.get('kelas_ajar', []) for doc in guru_collection.find()}
    daftar_kelas = [k['nama'] for k in kelas_collection.find({}, {"_id": 0})]
    locked_slots = list(locked_slots_collection.find({}, {"_id": 0}))
    status = status_collection.find_one({"key": "lock_status"})
    is_locked = status['locked'] if status else False

    if is_locked:
        jadwal_db = list(jadwal_final_collection.find({}, {"_id": 0}))
        jadwal = [(item['kelas'], item['hari'], item['waktu'], item['mapel'], item['guru']) for item in jadwal_db]
    else:
        jadwal = run_ga(
            guru_mapel=guru_mapel_data,
            preferensi_map=preferensi_map,
            guru_kelas_map=guru_kelas_map,
            daftar_kelas=daftar_kelas,
            locked_slots=locked_slots,
            global_lock=False
        )
        if jadwal:
            jadwal_final_collection.delete_many({})
            jadwal_final_collection.insert_many([
                {"kelas": k, "hari": h, "waktu": s, "mapel": m, "guru": g}
                for k, h, s, m, g in jadwal
            ])

    fitness_info = evaluate_fitness(jadwal, preferensi_map)

    data = {}
    for kls, h, s, m, g in jadwal:
        data.setdefault(kls, {}).setdefault(h, {})[s] = f"{m} ({g})"

    semua_kelas = list(kelas_collection.find({}, {'_id': 0, 'nama': 1}))
    semua_mapel = list(guru_mapel_collection.find({}, {'_id': 0, 'mapel': 1}))
    semua_guru = list(guru_collection.find({}, {'_id': 0, 'guru': 1}))

    return render_template("index.html",
                           jadwal=data,
                           fitness_info=fitness_info,
                           is_locked=is_locked,
                           semua_kelas=semua_kelas,
                           semua_mapel=semua_mapel,
                           semua_guru=semua_guru,
                           locked_slots=locked_slots,
                           title="Jadwal")

#------------------------------------------------------
#                MANAGEMENT JADWAL
#------------------------------------------------------

@app.route('/management', methods=['GET', 'POST'])
def management_jadwal():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        mapel = request.form['mapel']
        guru = request.form['guru']
        kelas_ajar = request.form.getlist('kelas_ajar')
        pref_raw = request.form.getlist('preferensi')
        preferensi = [[h, s] for h_s in pref_raw for h, s in [h_s.split('|')]]

        # Update guru dan mapel
        guru_mapel_collection.update_one(
            {"mapel": mapel},
            {"$addToSet": {"guru": guru}},
            upsert=True
        )

        guru_collection.update_one(
            {"guru": guru},
            {"$set": {
                "kelas_ajar": kelas_ajar,
                "preferensi": preferensi
            }},
            upsert=True
        )

        # Simpan preferensi sebagai locked slot (untuk semua kelas yang diajar)
        if preferensi:
            for kls in kelas_ajar:
                locked_slots_collection.update_one(
                    {
                        "kelas": kls,
                        "mapel": mapel,
                        "guru": guru
                    },
                    {
                        "$set": {
                            "slots": [{"hari": h, "waktu": s} for h, s in preferensi],
                            "updated_at": datetime.datetime.utcnow()
                        }
                    },
                    upsert=True
                )

        return redirect('/jadwal')

    # === Ambil semua data yang dibutuhkan ===
    guru_mapel_data = {doc['mapel']: doc.get('guru', []) for doc in guru_mapel_collection.find()}
    preferensi_map = {doc['guru']: doc.get('preferensi', []) for doc in guru_collection.find()}
    guru_kelas_map = {doc['guru']: doc.get('kelas_ajar', []) for doc in guru_collection.find()}
    daftar_kelas = [k['nama'] for k in kelas_collection.find({}, {"_id": 0})]
    locked_slots = list(locked_slots_collection.find({}, {"_id": 0}))
    status = status_collection.find_one({"key": "lock_status"})
    is_locked = status['locked'] if status else False

    # === Jalankan GA atau ambil jadwal final ===
    if is_locked:
        jadwal_db = list(jadwal_final_collection.find({}, {"_id": 0}))
        jadwal = [(item['kelas'], item['hari'], item['waktu'], item['mapel'], item['guru']) for item in jadwal_db]
    else:
        jadwal = run_ga(
            guru_mapel=guru_mapel_data,
            preferensi_map=preferensi_map,
            guru_kelas_map=guru_kelas_map,
            daftar_kelas=daftar_kelas,
            locked_slots=locked_slots,
            global_lock=False
        )
        if jadwal:
            jadwal_final_collection.delete_many({})
            jadwal_final_collection.insert_many([
                {"kelas": k, "hari": h, "waktu": s, "mapel": m, "guru": g}
                for k, h, s, m, g in jadwal
            ])

    # === Hitung nilai fitness ===
    fitness_info = evaluate_fitness(jadwal, preferensi_map)

    # Format data jadwal ke bentuk dictionary agar mudah ditampilkan di tabel
    data = {}
    for kls, h, s, m, g in jadwal:
        data.setdefault(kls, {}).setdefault(h, {})[s] = f"{m} ({g})"

    semua_kelas = list(kelas_collection.find({}, {'_id': 0, 'nama': 1}))
    semua_mapel = list(guru_mapel_collection.find({}, {'_id': 0, 'mapel': 1}))
    semua_guru = list(guru_collection.find({}, {'_id': 0, 'guru': 1}))

    return render_template("management.html",
                           jadwal=data,
                           fitness_info=fitness_info,
                           is_locked=is_locked,
                           semua_kelas=semua_kelas,
                           semua_mapel=semua_mapel,
                           semua_guru=semua_guru,
                           locked_slots=locked_slots,
                           title="Manajemen Jadwal")


#------------------------------------------------------
#                      FITUR PENGAMPU
#------------------------------------------------------

@app.route('/pengampu', methods=['GET'])
def daftar_pengampu():
    mapel_filter = request.args.get('mapel')

    if mapel_filter:
        data = list(guru_mapel_collection.find({"mapel": {"$regex": mapel_filter, "$options": "i"}}))
    else:
        data = list(guru_mapel_collection.find())

    return render_template('pengampu.html', data=data, mapel_filter=mapel_filter or '')

#------------------------------------------------------
# CREATE DAN READ FITUR KELAS, MATA PELAJARAN DAN GURU
#------------------------------------------------------

@app.route('/kelas', methods=['GET', 'POST'])
def tambah_kelas():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        nama_kelas = request.form['kelas'].strip()
        if nama_kelas:
            existing = kelas_collection.find_one({"nama": nama_kelas})
            if not existing:
                kelas_collection.insert_one({"nama": nama_kelas})
        return redirect('/kelas')

    daftar_kelas = list(kelas_collection.find({}, {"_id": 0}))
    return render_template("kelas.html", daftar_kelas=daftar_kelas,title="Manajemen Kelas")

@app.route('/guru', methods=['GET', 'POST'])
def tambah_guru():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        nama_guru = request.form['guru'].strip()
        if nama_guru:
            exists = guru_collection.find_one({"guru": nama_guru})
            if not exists:
                guru_collection.insert_one({
                    "guru": nama_guru
                })
        return redirect('/guru')

    daftar_guru = list(guru_collection.find({}, {'_id': 0, 'guru': 1}))
    return render_template("guru.html", daftar_guru=daftar_guru,title="Manajemen Guru")

@app.route('/mapel', methods=['GET', 'POST'])
def tambah_mapel():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        nama_mapel = request.form['mapel'].strip()
        if nama_mapel:
            existing = guru_mapel_collection.find_one({"mapel": nama_mapel})
            if not existing:
                guru_mapel_collection.insert_one({"mapel": nama_mapel, "guru": []})
        return redirect('/mapel')

    daftar_mapel = list(guru_mapel_collection.find({}, {"_id": 0}))
    return render_template("mapel.html", daftar_mapel=daftar_mapel,title="Manajemen Mata Pelajaran")

#------------------------------------------------------
#     EDIT FITUR KELAS, MATA PELAJARAN DAN GURU
#------------------------------------------------------

@app.route('/kelas_edit/<nama_lama>', methods=['GET', 'POST'])
def edit_kelas(nama_lama):
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        nama_baru = request.form['kelas'].strip()
        if nama_baru:
            kelas_collection.update_one({"nama": nama_lama}, {"$set": {"nama": nama_baru}})
            flash(f'Kelas {nama_lama} diubah menjadi {nama_baru}.', 'success')
        return redirect('/kelas')

    return render_template('kelas_edit.html', nama_lama=nama_lama, title="Edit Kelas")

@app.route('/mapel_edit/<mapel_lama>', methods=['GET', 'POST'])
def edit_mapel(mapel_lama):
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    mapel_lama = mapel_lama.strip()

    if request.method == 'POST':
        mapel_baru = request.form['mapel'].strip()
        if mapel_baru and mapel_baru != mapel_lama:
            # Pastikan tidak ada duplikat
            existing = guru_mapel_collection.find_one({"mapel": mapel_baru})
            if not existing:
                guru_mapel_collection.update_one(
                    {"mapel": mapel_lama},
                    {"$set": {"mapel": mapel_baru}}
                )
                flash("Nama mapel berhasil diperbarui.", "success")
            else:
                flash("Nama mapel baru sudah ada!", "danger")
        return redirect('/mapel')

    return render_template("mapel_edit.html", mapel_lama=mapel_lama, title="Edit Mata Pelajaran")

@app.route('/guru_edit/<nama_lama>', methods=['GET', 'POST'])
def edit_guru(nama_lama):
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    nama_lama = nama_lama.strip()

    if request.method == 'POST':
        nama_baru = request.form['guru'].strip()
        if nama_baru and nama_baru != nama_lama:
            existing = guru_mapel_collection.find_one({"guru": nama_baru})
            if not existing:
                guru_collection.update_one(
                    {"guru": nama_lama},
                    {"$set": {"guru": nama_baru}}
                )
                flash("Nama guru berhasil diperbarui.", "success")
            else:
                flash("Nama guru baru sudah ada!", "danger")
        return redirect('/guru')

    return render_template("guru_edit.html", nama_lama=nama_lama, title="Edit Guru")

#------------------------------------------------------
#     HAPUS FITUR KELAS, MATA PELAJARAN DAN GURU
#------------------------------------------------------

@app.route('/kelas/hapus', methods=['POST'])
def hapus_kelas():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    nama_kelas = request.form['kelas'].strip()
    if nama_kelas:
        kelas_collection.delete_one({"nama": nama_kelas})
        flash(f'Kelas {nama_kelas} berhasil dihapus.', 'success')
    return redirect('/kelas')

@app.route('/mapel/hapus', methods=['POST'])
def hapus_mapel():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    nama_mapel = request.form['mapel']
    if nama_mapel:
        guru_mapel_collection.delete_one({"mapel": nama_mapel})
        flash(f"Mapel '{nama_mapel}' berhasil dihapus.", "success")
    return redirect('/mapel')

@app.route('/guru/hapus', methods=['POST'])
def hapus_guru():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    nama_guru = request.form['guru']
    if nama_guru:
        guru_collection.delete_one({"guru": nama_guru})
        flash(f"Guru '{nama_guru}' berhasil dihapus.", "success")
    return redirect('/guru')

#------------------------------------------------------
#               SISTEM LOCK & UNLOCK JADWAL
#------------------------------------------------------

@app.route('/toggle_lock', methods=['POST'])
def toggle_lock():
    data = request.json
    slot = {
        "kelas": data['kelas'],
        "hari": data['hari'],
        "waktu": data['waktu']
    }
    existing = locked_slots_collection.find_one(slot)
    if existing:
        locked_slots_collection.delete_one(slot)
        return jsonify({"status": "unlocked"})
    else:
        locked_slots_collection.insert_one({**slot, "mapel": data['mapel'], "guru": data['guru']})
        return jsonify({"status": "locked"})

@app.route('/toggle_global_lock', methods=['POST'])
def toggle_global_lock():
    status = status_collection.find_one({"key": "lock_status"}) or {"locked": False}
    new_status = not status['locked']
    status_collection.update_one(
        {"key": "lock_status"},
        {"$set": {"locked": new_status}},
        upsert=True
    )
    return jsonify({"locked": new_status})

def get_locked_slots():
    return list(locked_slots_collection.find({}, {"_id": 0}))

#------------------------------------------------------
#          DOWNLOAD JADWAL VERSI CSV DAN PDF
#------------------------------------------------------

@app.route('/export')
def export_excel():
    guru_mapel_data = {doc['mapel']: doc.get('guru', []) for doc in guru_mapel_collection.find()}
    preferensi_map = {doc['guru']: doc.get('preferensi', []) for doc in guru_collection.find()}
    guru_kelas_map = {doc['guru']: doc.get('kelas_ajar', []) for doc in guru_collection.find()}
    daftar_kelas = [k['nama'] for k in kelas_collection.find({}, {"_id": 0})]
    locked_slots = list(locked_slots_collection.find({}, {"_id": 0}))
    status = status_collection.find_one({"key": "lock_status"})
    is_locked = status['locked'] if status else False

    if is_locked:
        jadwal_db = list(jadwal_final_collection.find({}, {"_id": 0}))
        jadwal = [(item['kelas'], item['hari'], item['waktu'], item['mapel'], item['guru']) for item in jadwal_db]
    else:
        jadwal = run_ga(
            guru_mapel=guru_mapel_data,
            preferensi_map=preferensi_map,
            guru_kelas_map=guru_kelas_map,
            daftar_kelas=daftar_kelas,
            locked_slots=locked_slots,
            global_lock=False
        )

    rows = [{"Kelas": k, "Hari": h, "Waktu": s, "Mapel": m, "Guru": g} for k, h, s, m, g in jadwal]
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Jadwal')
    output.seek(0)
    return send_file(output, download_name="jadwal.xlsx", as_attachment=True)

@app.route('/pdf')
def export_pdf():
    guru_mapel_data = {doc['mapel']: doc.get('guru', []) for doc in guru_mapel_collection.find()}
    preferensi_map = {doc['guru']: doc.get('preferensi', []) for doc in guru_collection.find()}
    guru_kelas_map = {doc['guru']: doc.get('kelas_ajar', []) for doc in guru_collection.find()}
    daftar_kelas = [k['nama'] for k in kelas_collection.find({}, {"_id": 0})]
    locked_slots = list(locked_slots_collection.find({}, {"_id": 0}))
    status = status_collection.find_one({"key": "lock_status"})
    is_locked = status['locked'] if status else False

    if is_locked:
        jadwal_db = list(jadwal_final_collection.find({}, {"_id": 0}))
        jadwal = [(item['kelas'], item['hari'], item['waktu'], item['mapel'], item['guru']) for item in jadwal_db]
    else:
        jadwal = run_ga(
            guru_mapel=guru_mapel_data,
            preferensi_map=preferensi_map,
            guru_kelas_map=guru_kelas_map,
            daftar_kelas=daftar_kelas,
            locked_slots=locked_slots,
            global_lock=False
        )

    data_per_kelas = {}
    for kls, h, s, m, g in jadwal:
        data_per_kelas.setdefault(kls, []).append((h, s, m, g))

    guru_list = sorted(set(g for _, _, _, _, g in jadwal))
    mapel_list = sorted(set(m for _, _, _, m, _ in jadwal))

    def clean(text):
        return ''.join(c if ord(c) < 256 else '-' for c in text)

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "JADWAL SEKOLAH - SMA NEGERI 6 MATARAM", ln=True, align="C")

    # Ukuran halaman (A4 landscape): 297mm x 210mm
    # Jadwal di kiri, guru/mapel di kanan

    # Titik awal dan lebar untuk jadwal
    jadwal_x = 10
    jadwal_y = 30
    jadwal_w = 160  # jadwal lebih sempit agar ada ruang untuk tabel di kanan

    # Titik awal tabel di kanan
    right_x = jadwal_x + jadwal_w + 10  # spasi 10mm antar kolom
    right_w = 100
    guru_y = jadwal_y
    mapel_y = guru_y + (len(guru_list) + 2) * 6 + 10  # tinggi guru + margin 10mm

    pdf.set_xy(jadwal_x, jadwal_y)
    pdf.set_font("Arial", 'B', 11)
    pdf.set_font("Arial", size=9)

    for kelas, items in data_per_kelas.items():
        pdf.set_x(jadwal_x)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, f"Kelas: {clean(kelas)}", ln=True)
        pdf.set_font("Arial", size=8)
        pdf.set_x(jadwal_x)
        pdf.cell(30, 6, "Hari", border=1)
        pdf.cell(30, 6, "Waktu", border=1)
        pdf.cell(50, 6, "Mapel", border=1)
        pdf.cell(50, 6, "Guru", border=1)
        pdf.ln()

        for h, s, m, g in sorted(items):
            pdf.set_x(jadwal_x)
            pdf.cell(30, 6, clean(h), border=1)
            pdf.cell(30, 6, clean(s), border=1)
            pdf.cell(50, 6, clean(m), border=1)
            pdf.cell(50, 6, clean(g), border=1)
            pdf.ln()

    # Tabel Guru (kanan atas)
    pdf.set_xy(right_x, guru_y)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(right_w, 8, "Daftar Guru", border=1, ln=True, align='C')
    pdf.set_font("Arial", size=9)
    for g in guru_list:
        pdf.set_x(right_x)
        pdf.cell(right_w, 6, clean(g), border=1, ln=True)

    # Tabel Mapel (kanan bawah)
    pdf.set_xy(right_x, mapel_y)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(right_w, 8, "Daftar Mata Pelajaran", border=1, ln=True, align='C')
    pdf.set_font("Arial", size=9)
    for m in mapel_list:
        pdf.set_x(right_x)
        pdf.cell(right_w, 6, clean(m), border=1, ln=True)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return send_file(output, download_name="jadwal_rinci.pdf", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
