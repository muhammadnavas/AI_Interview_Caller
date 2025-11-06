#!/usr/bin/env python3
"""
Check raw phone number in database
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_raw_phone():
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
        doc = collection.find_one({"_id": ObjectId(candidate_id)})
        
        if doc:
            print("Raw phone number in DB:", repr(doc.get("phoneNumber")))
            print("All phone-related fields:")
            for key, value in doc.items():
                if 'phone' in key.lower():
                    print(f"  {key}: {repr(value)}")
        else:
            print("Candidate not found")
            
        client.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_raw_phone()