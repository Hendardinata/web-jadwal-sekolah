from flask import Flask, render_template, request, redirect, send_file, jsonify, flash, session, url_for
from pymongo import MongoClient
from ga import run_ga, evaluate_fitness
from fpdf import FPDF
import pandas as pd
from functools import wraps
from flask import abort
import datetime
import io
from bson import ObjectId
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
deleted_slots_collection = db['deleted_slots']

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
            session['role'] = user['role']
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

    #----------------------
    # STATISTIK DASHBOARD
    #----------------------

    morning_slots = {
        "07.30–08.00",
        "08.00–08.30",
        "08.30–09.00",
        "09.00–09.30",
        "09.30–10.00"
    }

    mapel_bobot_map = {
        doc['mapel']: doc.get('bobot', 'sedang')
        for doc in guru_mapel_collection.find()
    }

    jadwal = list(jadwal_final_collection.find())

    pagi = 0
    siang = 0
    mapel_count = {}
    berat_pagi = 0
    berat_total = 0

    for j in jadwal:
        m = j['mapel']
        s = j['waktu']
        bobot = mapel_bobot_map.get(m, 'sedang')

        # pagi / siang
        if s in morning_slots:
            pagi += 1
        else:
            siang += 1

        # distribusi mapel
        mapel_count[m] = mapel_count.get(m, 0) + 1

        # mapel berat
        if bobot == 'berat':
            berat_total += 1
            if s in morning_slots:
                berat_pagi += 1

    return render_template(
        "dashboard.html",
        pagi=pagi,
        siang=siang,
        mapel_count=mapel_count,
        berat_pagi=berat_pagi,
        berat_total=berat_total,
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

    # ==============================
    # HANDLE INPUT DATA (POST)
    # ==============================
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

    # ==============================
    # AMBIL DATA DASAR
    # ==============================
    guru_mapel_data = {doc['mapel']: doc.get('guru', []) for doc in guru_mapel_collection.find()}
    preferensi_map = {doc['guru']: doc.get('preferensi', []) for doc in guru_collection.find()}
    guru_kelas_map = {doc['guru']: doc.get('kelas_ajar', []) for doc in guru_collection.find()}
    daftar_kelas = [k['nama'] for k in kelas_collection.find({}, {"_id": 0})]
    locked_slots = list(locked_slots_collection.find({}, {"_id": 0}))

    status = status_collection.find_one({"key": "lock_status"})
    is_locked = status['locked'] if status else False

    # ==============================
    # FIX UTAMA: TIDAK ADA AUTO GA
    # ==============================
    jadwal_db = list(jadwal_final_collection.find({}, {"_id": 0}))

    jadwal = [
        (item['kelas'], item['hari'], item['waktu'], item['mapel'], item['guru'])
        for item in jadwal_db
    ]

    # ==============================
    # HITUNG FITNESS (OPSIONAL)
    # ==============================
    fitness_info = evaluate_fitness(jadwal, preferensi_map) if jadwal else {
        "score": 0,
        "conflict": 0
    }

    # ==============================
    # FORMAT DATA UNTUK TAMPILAN
    # ==============================
    data = {}
    for doc in jadwal_final_collection.find():
        kls = doc['kelas']
        hari = doc['hari']
        waktu = doc['waktu']
        
        new_text = f"{doc['mapel']} ({doc['guru']})"
        
        # Prevent silently overwriting data if GA generates conflicting slots
        if kls in data and hari in data[kls] and waktu in data[kls][hari]:
            data[kls][hari][waktu]["text"] += f" | {new_text}"
        else:
            data.setdefault(kls, {}).setdefault(hari, {})[waktu] = {
                "text": new_text,
                "id": str(doc['_id'])
            }

    semua_kelas = list(kelas_collection.find({}, {'_id': 0, 'nama': 1}))
    semua_mapel = list(guru_mapel_collection.find({}, {'_id': 0, 'mapel': 1}))
    semua_guru = list(guru_collection.find({}, {'_id': 0, 'guru': 1}))

    # ==============================
    # FITUR SEARCH
    # ==============================
    search = request.args.get('search', '').strip().lower()

    if search:
        filtered_data = {}

        for kelas, hari_data in data.items():
            if search in kelas.lower():
                filtered_data[kelas] = hari_data
                continue

            for hari, waktu_data in hari_data.items():
                for waktu, cell in waktu_data.items():
                    if search in cell["text"].lower():
                        filtered_data.setdefault(kelas, {}).setdefault(hari, {})[waktu] = cell

        data = filtered_data

    # ==============================
    # RENDER
    # ==============================
    return render_template(
        "index.html",
        jadwal=data,
        fitness_info=fitness_info,
        is_locked=is_locked,
        semua_kelas=semua_kelas,
        semua_mapel=semua_mapel,
        semua_guru=semua_guru,
        locked_slots=locked_slots,
        search=search or '',
        title="Jadwal"
    )

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
        jumlah_jam = int(request.form.get('jumlah_jam', 2))
        is_berurutan = 'berurutan' in request.form and jumlah_jam > 1

        pref_raw = request.form.getlist('preferensi')
        preferensi = [[h, s] for h_s in pref_raw for h, s in [h_s.split('|')]]

        # Update guru dan mapel
        guru_mapel_collection.update_one(
            {"mapel": mapel},
            {"$addToSet": {"guru": guru}},
            upsert=True
        )

        # Tambahkan kelas_ajar baru ke daftar lama tanpa duplikat
        existing_guru = guru_collection.find_one({"guru": guru}) or {}
        existing_kelas_ajar = set(existing_guru.get("kelas_ajar", []))
        updated_kelas_ajar = list(existing_kelas_ajar.union(set(kelas_ajar)))

        # Simpan data guru
        guru_collection.update_one(
            {"guru": guru},
            {"$set": {
                "kelas_ajar": updated_kelas_ajar,
                "preferensi": preferensi if not is_berurutan else [],
                "berurutan": is_berurutan
            }},
            upsert=True
        )

        # Simpan locked slots
        for kls in kelas_ajar:
            slot_data = {
                "jumlah_jam": jumlah_jam,
                "berurutan": is_berurutan,
                "updated_at": datetime.datetime.utcnow(),
                "slots": [] if is_berurutan else [{"hari": h, "waktu": s} for h, s in preferensi]
            }

            locked_slots_collection.update_one(
                {
                    "kelas": kls,
                    "mapel": mapel,
                    "guru": guru
                },
                {"$set": slot_data},
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
    jadwal_db = list(jadwal_final_collection.find({}, {"_id": 0}))

    jadwal = [
        (item['kelas'], item['hari'], item['waktu'], item['mapel'], item['guru'])
        for item in jadwal_db
    ]

    # === Hitung nilai fitness ===
    fitness_info = evaluate_fitness(jadwal, preferensi_map)

    # === Format data jadwal ke bentuk dictionary agar mudah ditampilkan di tabel ===
    data = {}
    for kls, h, s, m, g in jadwal:
        new_text = f"{m} ({g})"
        if kls in data and h in data[kls] and s in data[kls][h]:
            data[kls][h][s] += f" | {new_text}"
        else:
            data.setdefault(kls, {}).setdefault(h, {})[s] = new_text

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

@app.route('/management-edit/<id>', methods=['GET', 'POST'])
def edit_jadwal(id):
    # =========================================================
    #                   AMBIL DATA JADWAL
    # =========================================================
    jadwal_doc = jadwal_final_collection.find_one({"_id": ObjectId(id)})
    if not jadwal_doc:
        flash("Jadwal tidak ditemukan", "danger")
        return redirect(url_for('jadwal'))

    guru_lama = jadwal_doc["guru"]
    mapel_lama = jadwal_doc["mapel"]
    kelas_lama = jadwal_doc["kelas"]

    guru_doc = guru_collection.find_one({"guru": guru_lama}) or {}

    locked_doc = locked_slots_collection.find_one({
        "guru": guru_lama,
        "mapel": mapel_lama,
        "kelas": kelas_lama
    }) or {}

    # =========================================================
    #                       GET Data
    # =========================================================
    slots_lama = locked_doc.get("slots", [])

    jadwal = {
        "guru": guru_lama,
        "mapel": mapel_lama,
        "kelas_ajar": guru_doc.get("kelas_ajar", []),

        "preferensi": [
            f"{slot['hari']}|{slot['waktu']}"
            for slot in slots_lama
        ],

        "berurutan": locked_doc.get("berurutan", False),

        "jumlah_jam": locked_doc.get("jumlah_jam", 1)
    }

    semua_kelas = list(kelas_collection.find({}, {"_id": 0, "nama": 1}))
    semua_mapel = list(guru_mapel_collection.find({}, {"_id": 0, "mapel": 1}))
    semua_guru = list(guru_collection.find({}, {"_id": 0, "guru": 1}))

    # =========================================================
    #                        POST Data
    # =========================================================
    if request.method == 'POST':
        guru_baru = request.form['guru']
        mapel_baru = request.form['mapel']
        kelas_ajar_baru = request.form.getlist('kelas_ajar')

        jumlah_jam_baru = int(request.form.get('jumlah_jam', 1))
        berurutan_baru = 'berurutan' in request.form

        preferensi_raw = request.form.getlist('preferensi')

        # =====================================================
        #                   LOGIKA PREFERENSI
        # =====================================================
        slots_baru = []

        if preferensi_raw:
            slots_baru = [
                {"hari": h, "waktu": s}
                for h, s in (p.split("|") for p in preferensi_raw)
            ]

        # =====================================================
        #                   UPDATE guru mapel
        # =====================================================
        guru_mapel_collection.update_one(
            {"mapel": mapel_lama},
            {"$pull": {"guru": guru_lama}}
        )

        guru_mapel_collection.update_one(
            {"mapel": mapel_baru},
            {"$addToSet": {"guru": guru_baru}},
            upsert=True
        )

        # =====================================================
        #                    UPDATE guru
        # =====================================================
        guru_collection.update_one(
            {"guru": guru_baru},
            {"$set": {
                "kelas_ajar": list(set(kelas_ajar_baru)),
                "preferensi": slots_baru,
                "berurutan": berurutan_baru
            }},
            upsert=True
        )

        # =====================================================
        #                   UPDATE locked slots
        # =====================================================
        for kls in kelas_ajar_baru:
            locked_slots_collection.update_one(
                {
                    "guru": guru_baru,
                    "mapel": mapel_baru,
                    "kelas": kls
                },
                {"$set": {
                    "jumlah_jam": jumlah_jam_baru,  
                    "slots": slots_baru,            
                    "berurutan": berurutan_baru,
                    "updated_at": datetime.datetime.utcnow()
                }},
                upsert=True
            )

        # =====================================================
        #                   SYNC jadwal final
        # =====================================================
        jadwal_final_collection.delete_many({
            "guru": guru_lama,
            "mapel": mapel_lama,
            "kelas": {"$in": kelas_ajar_baru}
        })

        if slots_baru:
            for kls in kelas_ajar_baru:
                for slot in slots_baru:
                    jadwal_final_collection.insert_one({
                        "guru": guru_baru,
                        "mapel": mapel_baru,
                        "kelas": kls,
                        "hari": slot["hari"],
                        "waktu": slot["waktu"],
                        "updated_at": datetime.datetime.utcnow()
                    })

        flash("Jadwal berhasil diperbarui", "success")
        return redirect(url_for('jadwal'))

    return render_template(
        "management_edit.html",
        jadwal=jadwal,
        semua_kelas=semua_kelas,
        semua_mapel=semua_mapel,
        semua_guru=semua_guru
    )

#------------------------------------------------------
#                      FITUR PENGAMPU
#------------------------------------------------------

@app.route('/pengampu', methods=['GET'])
def daftar_pengampu():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    mapel_filter = request.args.get('mapel', '').strip()

    query = {}
    if mapel_filter:
        query["mapel"] = {"$regex": mapel_filter, "$options": "i"}

    cursor = guru_mapel_collection.find(query, {"_id": 0})

    data = []
    for d in cursor:
        data.append({
            "mapel": d.get("mapel"),
            "guru": d.get("guru", [])
        })

    return render_template(
        'pengampu.html',
        data=data,
        mapel_filter=mapel_filter,
        title="Data Guru Pengampu"
    )

@app.route('/hapus_pengampu', methods=['POST'])
@role_required('admin')
def hapus_pengampu():
    if 'username' not in session:
        flash('Silakan login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))
        
    mapel = request.form.get('mapel')
    guru = request.form.get('guru')
    
    if mapel and guru:
        guru_mapel_collection.update_one(
            {"mapel": mapel},
            {"$pull": {"guru": guru}}
        )
        flash(f'Guru {guru} berhasil dihapus dari pengampu {mapel}.', 'success')
    return redirect(url_for('daftar_pengampu'))


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
        bobot = request.form.get('bobot', 'sedang')  # default sedang

        if nama_mapel:
            existing = guru_mapel_collection.find_one({"mapel": nama_mapel})
            if not existing:
                guru_mapel_collection.insert_one({
                    "mapel": nama_mapel,
                    "guru": [],
                    "bobot": bobot
                })
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
    data_lama = guru_mapel_collection.find_one({"mapel": mapel_lama}) or {}

    if request.method == 'POST':
        mapel_baru = request.form['mapel'].strip()
        bobot_baru = request.form.get('bobot', 'sedang')

        if mapel_baru:
            existing = guru_mapel_collection.find_one({"mapel": mapel_baru})

            if not existing or mapel_baru == mapel_lama:
                guru_mapel_collection.update_one(
                    {"mapel": mapel_lama},
                    {"$set": {
                        "mapel": mapel_baru,
                        "bobot": bobot_baru
                    }}
                )
                flash("Mapel berhasil diperbarui.", "success")
            else:
                flash("Nama mapel sudah ada!", "danger")

        return redirect('/mapel')

    return render_template(
        "mapel_edit.html",
        mapel_lama=mapel_lama,
        bobot_lama=data_lama.get("bobot", "sedang"),
        title="Edit Mata Pelajaran"
    )

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

@app.route('/jadwal/hapus/<id>', methods=['POST'])
def hapus_jadwal(id):
    try:
        obj_id = ObjectId(id)
    except:
        return jsonify({"error": "ID tidak valid"}), 400

    data = jadwal_final_collection.find_one({"_id": obj_id})

    if not data:
        return jsonify({"error": "data tidak ditemukan"}), 404

    kelas = data["kelas"]
    mapel = data["mapel"]
    guru = data["guru"]

    # -------------------------
    # HAPUS DI FINAL
    #----------------------
    jadwal_final_collection.delete_many({
        "kelas": kelas,
        "mapel": mapel,
        "guru": guru
    })

    #----------------------
    # HAPUS DI LOCKED
    #----------------------
    locked_slots_collection.delete_many({
        "kelas": kelas,
        "mapel": mapel,
        "guru": guru
    })

    #----------------------
    # PUTUS RELASI KELAS JIKA GURU TIDAK MENGAJAR MAPEL APAPUN LAGI DI KELAS INI
    #----------------------
    remaining_in_kelas = jadwal_final_collection.find_one({
        "guru": guru,
        "kelas": kelas
    })
    
    if not remaining_in_kelas:
        guru_collection.update_one(
            {"guru": guru},
            {"$pull": {"kelas_ajar": kelas}}
        )

    #----------------------
    # HAPUS DI PENGAMPU JIKA GURU SUDAH TIDAK MENGAJAR MAPEL INI
    #----------------------
    remaining_jadwal = jadwal_final_collection.find_one({
        "guru": guru,
        "mapel": mapel
    })
    
    if not remaining_jadwal:
        guru_mapel_collection.update_one(
            {"mapel": mapel},
            {"$pull": {"guru": guru}}
        )

    return jsonify({"success": True})

@app.route('/generate_jadwal', methods=['POST'])
@role_required('admin')
def generate_jadwal():

    #----------------------
    # CEK LOCK GLOBAL
    #----------------------
    status = status_collection.find_one({"key": "lock_status"})
    is_locked = status['locked'] if status else False

    if is_locked:
        flash("Jadwal sedang terkunci!", "danger")
        return redirect(url_for('jadwal'))

    #----------------------
    # AMBIL DATA MASTER
    #----------------------
    guru_mapel_data = {
        doc['mapel']: doc.get('guru', [])
        for doc in guru_mapel_collection.find()
    }

    preferensi_map = {
        doc['guru']: doc.get('preferensi', [])
        for doc in guru_collection.find()
    }

    guru_kelas_map = {
        doc['guru']: doc.get('kelas_ajar', [])
        for doc in guru_collection.find()
    }

    daftar_kelas = [
        k['nama'] for k in kelas_collection.find({}, {"_id": 0})
    ]

    locked_slots = list(
        locked_slots_collection.find({}, {"_id": 0})
    )

    mapel_bobot_map = {
        doc['mapel']: doc.get('bobot', 'sedang')
        for doc in guru_mapel_collection.find()
    }

    #----------------------
    # AMBIL BLACKLIST (PENTING)
    #----------------------
    deleted_slots = list(
        deleted_slots_collection.find({}, {"_id": 0})
    )

    def is_deleted(kls, h, s, m, g):
        return any(
            d["kelas"] == kls and
            d["hari"] == h and
            d["waktu"] == s and
            d["mapel"] == m and
            d["guru"] == g
            for d in deleted_slots
        )

    #----------------------
    # RUN GA
    #----------------------
    jadwal = run_ga(
        guru_mapel=guru_mapel_data,
        preferensi_map=preferensi_map,
        guru_kelas_map=guru_kelas_map,
        daftar_kelas=daftar_kelas,
        locked_slots=locked_slots,
        global_lock=False,
        mapel_bobot_map=mapel_bobot_map
    )

    if not jadwal:
        flash("Generate gagal: jadwal kosong", "danger")
        return redirect(url_for('jadwal'))

    #----------------------
    # FILTER HASIL GA
    #----------------------
    filtered_jadwal = [
        (k, h, s, m, g)
        for k, h, s, m, g in jadwal
        if not is_deleted(k, h, s, m, g)
    ]

    #----------------------
    # RESET + SIMPAN BARU
    #----------------------
    jadwal_final_collection.delete_many({})

    insert_data = [
        {
            "kelas": k,
            "hari": h,
            "waktu": s,
            "mapel": m,
            "guru": g
        }
        for k, h, s, m, g in filtered_jadwal
    ]

    if insert_data:
        jadwal_final_collection.insert_many(insert_data)

    flash("Generate jadwal berhasil!", "success")
    return redirect(url_for('jadwal'))

if __name__ == '__main__':
    app.run(debug=True)
