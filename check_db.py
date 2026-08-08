from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
db = client['jadwal_db']
print('Total guru:', db.guru.count_documents({}))
print('Total kelas:', db.kelas.count_documents({}))
print('Total mapel:', db.mapel.count_documents({}))
print('Total locked_slots (where jumlah_jam is saved):', db.locked_slots.count_documents({}))
for doc in db.locked_slots.find():
    print(doc['mapel'], doc['guru'], doc['kelas'], doc.get('jumlah_jam', 'no jumlah_jam'))
