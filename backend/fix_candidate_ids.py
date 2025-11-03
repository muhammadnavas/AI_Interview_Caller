from pymongo import MongoClient
import uuid

client = MongoClient('mongodb://localhost:27017/')
db = client['interview_scheduler']
candidates = list(db.candidates.find())

print('Current candidates in MongoDB:')
updated = 0
for c in candidates:
    cid = c.get('candidate_id')
    if not cid:
        new_id = f'CAND_{str(uuid.uuid4())[:8].upper()}'
        result = db.candidates.update_one({'_id': c['_id']}, {'$set': {'candidate_id': new_id}})
        print(f'  ✅ Added {new_id} to {c.get("name", "Unknown")}')
        updated += 1
    else:
        print(f'  ✓ {cid} -> {c.get("name", "Unknown")}')

print(f'Updated {updated} candidates')
client.close()