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
    guru_mapel,
    preferensi_map,
    guru_kelas_map,
    daftar_kelas,
    locked_slots=None,
    global_lock=False,
    jumlah_populasi=50,
    generasi_maks=200
):
    print("== MULAI PROSES GENETIC ALGORITHM ==")
    print(f"Jumlah populasi: {jumlah_populasi}, Generasi Maks: {generasi_maks}")
    print(f"Global Lock Aktif: {global_lock}")

    mapel = list(guru_mapel.keys())
    jam_per_minggu = 2

    locked_lookup = set()
    locked_map = {}
    if locked_slots:
        print(f"Jumlah slot terkunci: {len(locked_slots)}")
        for entry in locked_slots:
            kls = entry["kelas"]
            m = entry["mapel"]
            g = entry["guru"]
            for slot in entry["slots"]:
                h = slot["hari"]
                s = slot["waktu"]
                key = (kls, h, s)
                locked_lookup.add(key)
                locked_map[key] = (m, g)

    if global_lock and locked_slots:
        print("Global lock aktif. Mengembalikan slot terkunci...")
        return [
            (slot["kelas"], s["hari"], s["waktu"], slot["mapel"], slot["guru"])
            for slot in locked_slots
            for s in slot["slots"]
        ]

    def generate_chromosome():
        jadwal = []
        for kls in daftar_kelas:
            for m in mapel:
                count = 0
                locked_for_this = [
                    key for key in locked_lookup
                    if key[0] == kls and locked_map[key][0] == m
                ]
                for key in locked_for_this:
                    h, s = key[1], key[2]
                    g = locked_map[key][1]
                    jadwal.append((kls, h, s, m, g))
                    count += 1
                for _ in range(jam_per_minggu - count):
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

            is_locked = (kls, h, s) in locked_lookup and locked_map[(kls, h, s)][1] == g

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
            if guru_kelas_hari[key_guru_kls_hari] > 1 and not is_locked:
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
                kls, h_old, s_old, m, g_old = chromosome[i]
                key_slot = (kls, h_old, s_old)
                if key_slot in locked_lookup and locked_map[key_slot][1] == g_old:
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
    for gen in range(generasi_maks):
        selected = selection(populasi)
        new_population = []
        for _ in range(jumlah_populasi // 2):
            child1, child2 = crossover(selected[0], selected[1])
            new_population.append(mutate(child1))
            new_population.append(mutate(child2))
        populasi = new_population

        if gen % 10 == 0 or gen == generasi_maks - 1:
            skor = round(fitness(selected[0]), 4)
            print(f"Generasi {gen + 1}/{generasi_maks} - Fitness terbaik: {skor}")

    best = max(populasi, key=lambda x: fitness(x))
    print("== SELESAI GA. Fitness Terbaik:", round(fitness(best), 4))
    return best


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
