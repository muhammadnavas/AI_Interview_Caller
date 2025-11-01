from decouple import config
from pymongo import MongoClient

try:
    mongodb_uri = config('MONGODB_URI')
    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client['ai_interview_schedule']
    coll = db['candidates']

    # Test connection
    client.admin.command('ping')
    print('✅ MongoDB connection successful!')

    # Get candidate count
    count = coll.count_documents({})
    print(f'📊 Total candidates: {count}')

    # Get first few candidates
    candidates = list(coll.find().limit(3))
    print('\n📋 Sample candidates:')
    for i, candidate in enumerate(candidates, 1):
        print(f'{i}. Name: {candidate.get("name", "N/A")}')
        print(f'   Phone: {candidate.get("phone", "N/A")}')
        print(f'   Email: {candidate.get("email", "N/A")}')
        print(f'   Position: {candidate.get("position", "N/A")}')
        print(f'   Company: {candidate.get("company", "N/A")}')
        print(f'   ID: {candidate.get("_id")}')
        print()

except Exception as e:
    print(f'❌ Error: {e}')