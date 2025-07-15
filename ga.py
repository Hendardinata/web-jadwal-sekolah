import random

# Slot waktu dan hari
waktu_slot = [
    "07.30–08.00", "08.00–08.30", "08.30–09.00", "09.00–09.30",
    "09.30–10.00", "10.00–10.20", "10.20–10.50", "10.50–11.20",
    "11.20–11.50", "11.50–12.20", "12.20–13.00"
]
hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]
non_akademik = {
    "10.00–10.20", "10.20–10.50", "11.35–12.00", "12.00–12.25", "12.20–13.00"
}

def run_ga(
    guru_mapel,            # dict: mapel -> list guru
    preferensi_map,        # dict: guru -> list [hari, slot]
    guru_kelas_map,        # dict: guru -> list kelas
    daftar_kelas,          # list: nama-nama kelas dari collection `kelas`
    locked_slots=None,     # list dict {kelas, hari, waktu, mapel, guru}
    global_lock=False,
    jumlah_populasi=50,
    generasi_maks=200
):
    
    print("== MULAI PROSES GENETIC ALGORITHM ==")  # LOG
    print(f"Jumlah populasi: {jumlah_populasi}, Generasi Maks: {generasi_maks}")  # LOG
    print(f"Global Lock Aktif: {global_lock}")  # LOG
    
    mapel = list(guru_mapel.keys())
    jam_per_minggu = 2

    # Siapkan lookup untuk slot terkunci
    locked_lookup = set()
    locked_map = {}
    if locked_slots:
        print(f"Jumlah slot terkunci: {len(locked_slots)}")
        for slot in locked_slots:
            key = (slot["kelas"], slot["hari"], slot["waktu"])
            locked_lookup.add(key)
            locked_map[key] = (slot["mapel"], slot["guru"])

    # Jika global lock aktif, langsung gunakan locked slots
    if global_lock and locked_slots:
        print("Global lock aktif. Mengembalikan slot terkunci...")
        jadwal_locked = []
        for slot in locked_slots:
            jadwal_locked.append((
                slot["kelas"], slot["hari"], slot["waktu"],
                slot["mapel"], slot["guru"]
            ))
        return jadwal_locked

    def generate_chromosome():
        jadwal = []
        for kls in daftar_kelas:
            for m in mapel:
                for _ in range(jam_per_minggu):
                    # Cek apakah slot locked untuk mapel ini pada kelas ini
                    locked_for_this = [key for key in locked_lookup if key[0] == kls]
                    found_locked = None
                    for key in locked_for_this:
                        mapel_locked, _ = locked_map[key]
                        if mapel_locked == m:
                            found_locked = key
                            break
                    if found_locked:
                        h, s = found_locked[1], found_locked[2]
                        g = locked_map[found_locked][1]
                        jadwal.append((kls, h, s, m, g))
                    else:
                        kandidat_guru = [
                            g for g in guru_mapel[m]
                            if g in guru_kelas_map and kls in guru_kelas_map[g]
                        ]
                        if not kandidat_guru:
                            continue
                        g = random.choice(kandidat_guru)
                        while True:
                            h = random.choice(hari)
                            s = random.choice(waktu_slot)
                            if s not in non_akademik and (kls, h, s) not in locked_lookup:
                                break
                        jadwal.append((kls, h, s, m, g))
        return jadwal

    def fitness(chromosome):
        konflik = 0
        slot_kelas = set()
        slot_guru = set()
        mapel_kelas_slot = set()
        guru_kelas_hari = {}
        jam_guru_per_hari = {}

        for kls, h, s, m, g in chromosome:
            key_kls = (kls, h, s)
            key_guru = (g, h, s)
            key_mapel_kls_slot = (kls, h, s, m)
            key_guru_kls_hari = (g, kls, h)

            if key_kls in slot_kelas:
                konflik += 1
            if key_guru in slot_guru:
                konflik += 1
            if key_mapel_kls_slot in mapel_kelas_slot:
                konflik += 1
            if s in non_akademik:
                konflik += 5

            guru_kelas_hari.setdefault(key_guru_kls_hari, 0)
            guru_kelas_hari[key_guru_kls_hari] += 1
            if guru_kelas_hari[key_guru_kls_hari] > 1:
                konflik += 3

            jam_guru_per_hari.setdefault((g, h), 0)
            jam_guru_per_hari[(g, h)] += 1
            if jam_guru_per_hari[(g, h)] > 4:
                konflik += 1

            if preferensi_map.get(g) and [h, s] not in preferensi_map[g]:
                konflik += 2

            slot_kelas.add(key_kls)
            slot_guru.add(key_guru)
            mapel_kelas_slot.add(key_mapel_kls_slot)

        return 1 / (1 + konflik)

    def selection(populasi):
        populasi.sort(key=lambda x: fitness(x), reverse=True)
        return populasi[:2]

    def crossover(p1, p2):
        idx = len(p1) // 2
        return p1[:idx] + p2[idx:], p2[:idx] + p1[idx:]

    def mutate(chromosome, mutation_rate=0.1):
        for i in range(len(chromosome)):
            if random.random() < mutation_rate:
                kls, _, _, m, old_guru = chromosome[i]
                key_slot = (kls, chromosome[i][1], chromosome[i][2])
                if locked_lookup and key_slot in locked_lookup:
                    continue
                kandidat_guru = [
                    g for g in guru_mapel[m]
                    if g in guru_kelas_map and kls in guru_kelas_map[g]
                ]
                if not kandidat_guru:
                    continue
                g = random.choice(kandidat_guru)
                while True:
                    h = random.choice(hari)
                    s = random.choice(waktu_slot)
                    if s not in non_akademik and (kls, h, s) not in locked_lookup:
                        break
                chromosome[i] = (kls, h, s, m, g)
        return chromosome
    print("Membuat populasi awal...") 
    
    populasi = [generate_chromosome() for _ in range(jumlah_populasi)]
    for _ in range(generasi_maks):
        selected = selection(populasi)
        new_population = []
        for _ in range(jumlah_populasi // 2):
            child1, child2 = crossover(selected[0], selected[1])
            new_population.append(mutate(child1))
            new_population.append(mutate(child2))
        populasi = new_population

    return max(populasi, key=lambda x: fitness(x))


def evaluate_fitness(jadwal, preferensi_map):
    konflik = 0
    slot_kelas = set()
    slot_guru = set()
    mapel_kelas_slot = set()
    guru_kelas_hari = {}
    jam_guru_per_hari = {}

    for kls, h, s, m, g in jadwal:
        key_kls = (kls, h, s)
        key_guru = (g, h, s)
        key_mapel_kls_slot = (kls, h, s, m)
        key_guru_kls_hari = (g, kls, h)

        if key_kls in slot_kelas:
            konflik += 1
        if key_guru in slot_guru:
            konflik += 1
        if key_mapel_kls_slot in mapel_kelas_slot:
            konflik += 1
        if s in non_akademik:
            konflik += 5

        guru_kelas_hari.setdefault(key_guru_kls_hari, 0)
        guru_kelas_hari[key_guru_kls_hari] += 1
        if guru_kelas_hari[key_guru_kls_hari] > 1:
            konflik += 3

        jam_guru_per_hari.setdefault((g, h), 0)
        jam_guru_per_hari[(g, h)] += 1
        if jam_guru_per_hari[(g, h)] > 4:
            konflik += 1

        if preferensi_map.get(g) and [h, s] not in preferensi_map[g]:
            konflik += 2

        slot_kelas.add(key_kls)
        slot_guru.add(key_guru)
        mapel_kelas_slot.add(key_mapel_kls_slot)

    return {
        "score": round(1 / (1 + konflik), 4),
        "conflict": konflik
    }
