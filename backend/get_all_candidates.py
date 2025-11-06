#!/usr/bin/env python3
"""
Get all candidates with their IDs for the frontend dropdown
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def get_all_candidates():
    try:
        from pymongo import MongoClient
        from bson import ObjectId
        from decouple import config
        
        # MongoDB connection
        mongodb_uri = config("MONGODB_URI", default=None)
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        collection = db[coll_name]
        
        print("📋 All available candidates:")
        print("=" * 50)
        
        candidates = list(collection.find({}))
        
        if not candidates:
            print("❌ No candidates found in the database")
            return []
        
        candidate_list = []
        for i, candidate in enumerate(candidates, 1):
            candidate_info = {
                'id': str(candidate['_id']),
                'name': candidate.get('candidateName', 'Unknown'),
                'phone': candidate.get('phoneNumber', 'Unknown'),
                'email': candidate.get('candidateEmail', 'Unknown'),
                'position': candidate.get('role', 'Unknown'),
                'company': candidate.get('companyName', 'Unknown')
            }
            candidate_list.append(candidate_info)
            
            print(f"{i}. {candidate_info['name']} (ID: {candidate_info['id']})")
            print(f"   Phone: {candidate_info['phone']}")
            print(f"   Email: {candidate_info['email']}")
            print(f"   Position: {candidate_info['position']} at {candidate_info['company']}")
            print()
        
        client.close()
        return candidate_list
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

if __name__ == "__main__":
    get_all_candidates()