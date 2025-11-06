#!/usr/bin/env python3
"""
Reset candidate call attempts for testing
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def reset_candidate_call_attempts():
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
        
        candidate_id = "690b857c80befccb653eb73a"
        
        print(f"🔄 Resetting call attempts for candidate: {candidate_id}")
        
        # Remove call_tracking to reset attempts
        result = collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {"$unset": {"call_tracking": ""}}
        )
        
        if result.modified_count > 0:
            print("✅ Successfully reset call attempts!")
            print("📞 Candidate can now receive calls again")
        else:
            print("⚠️ No changes made - candidate might not exist or already reset")
            
        client.close()
        
        # Verify the reset
        from main import get_candidate_call_status
        call_status = get_candidate_call_status(candidate_id)
        print(f"📊 New call status: {call_status}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    reset_candidate_call_attempts()