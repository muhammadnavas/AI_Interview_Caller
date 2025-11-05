#!/usr/bin/env python3
"""
Test MongoDB connection and list candidates
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_mongodb_connection():
    try:
        from pymongo import MongoClient
        from decouple import config
        
        # Get MongoDB configuration
        mongodb_uri = config("MONGODB_URI", default=None)
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        
        print("🔗 Testing MongoDB Connection...")
        print(f"URI: {mongodb_uri}")
        print(f"Database: {db_name}")
        print(f"Collection: {coll_name}")
        print("=" * 50)
        
        if not mongodb_uri:
            print("❌ MONGODB_URI not found in .env file")
            return
            
        # Test connection
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        
        # Test server connection
        client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        
        # Access database and collection
        db = client[db_name]
        collection = db[coll_name]
        
        # Count documents
        doc_count = collection.count_documents({})
        print(f"📊 Found {doc_count} documents in {db_name}.{coll_name}")
        
        if doc_count > 0:
            # Get first document
            first_doc = collection.find_one()
            print(f"📄 Sample document structure:")
            for key, value in first_doc.items():
                if key == '_id':
                    print(f"   {key}: {str(value)}")
                else:
                    print(f"   {key}: {value}")
                    
            # Test our function
            print("\n🧪 Testing get_all_candidates_from_mongo()...")
            from main import get_all_candidates_from_mongo
            candidates = get_all_candidates_from_mongo()
            
            if candidates:
                print(f"✅ Function returned {len(candidates)} candidates:")
                for i, candidate in enumerate(candidates):
                    print(f"   {i+1}. {candidate.get('name')} (ID: {candidate.get('candidate_id')})")
                    print(f"      Phone: {candidate.get('phone')}")
                    print(f"      Email: {candidate.get('email')}")
            else:
                print("❌ Function returned no candidates")
        else:
            print("⚠️ No documents found in collection")
            
        client.close()
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_mongodb_connection()