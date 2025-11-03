#!/usr/bin/env python3
"""
Add candidate_id field to existing candidates in MongoDB
"""
from pymongo import MongoClient
import uuid
from datetime import datetime

def add_candidate_ids():
    """Add candidate_id field to all candidates that don't have one"""
    try:
        client = MongoClient('mongodb://localhost:27017/')
        db = client['interview_scheduler']
        
        # Find candidates without candidate_id
        candidates_without_id = list(db.candidates.find({"candidate_id": {"$exists": False}}))
        
        print(f"Found {len(candidates_without_id)} candidates without candidate_id")
        
        for candidate in candidates_without_id:
            # Generate unique candidate ID
            candidate_id = f"CAND_{str(uuid.uuid4())[:8].upper()}"
            
            # Update the candidate
            result = db.candidates.update_one(
                {"_id": candidate["_id"]},
                {
                    "$set": {
                        "candidate_id": candidate_id,
                        "updated_at": datetime.now().isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                print(f"✅ Added candidate_id '{candidate_id}' to {candidate.get('name', 'Unknown')}")
            else:
                print(f"❌ Failed to update {candidate.get('name', 'Unknown')}")
        
        # Verify the update
        all_candidates = list(db.candidates.find())
        print(f"\nVerification - All candidates now:")
        for candidate in all_candidates:
            print(f"  - ID: {candidate.get('candidate_id', 'MISSING')} | Name: {candidate.get('name')} | Phone: {candidate.get('phone')}")
        
        client.close()
        print(f"\n🎉 Migration complete! Updated {len(candidates_without_id)} candidates.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    add_candidate_ids()