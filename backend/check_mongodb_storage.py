"""
MongoDB Data Checker - Show exactly where call tracking data is stored
"""
import json
from datetime import datetime

def check_mongodb_storage():
    """Check MongoDB to see where call tracking data is actually stored"""
    try:
        # Import locally 
        from pymongo import MongoClient
        from bson import ObjectId
        
        # Your MongoDB connection details from .env
        MONGODB_URI = "mongodb+srv://navasns0409:rx4Fvt8un1dCovaz@cluster0.lz452k4.mongodb.net/"
        MONGODB_DB = "ai_interview_schedule"
        MONGODB_COLLECTION = "candidates"
        
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGODB_DB]
        collection = db[MONGODB_COLLECTION]
        
        print("=" * 60)
        print("🔍 CHECKING MONGODB STORAGE LOCATION")
        print("=" * 60)
        print(f"📍 Database: {MONGODB_URI}")
        print(f"📍 Database Name: {MONGODB_DB}")
        print(f"📍 Collection: {MONGODB_COLLECTION}")
        print()
        
        # Get all candidates with their call tracking data
        candidates = list(collection.find({}))
        
        print(f"📊 Found {len(candidates)} candidate(s) in MongoDB")
        print("=" * 60)
        
        for i, candidate in enumerate(candidates, 1):
            print(f"\n🧑‍💼 CANDIDATE #{i}")
            print("-" * 40)
            print(f"📱 ID: {candidate.get('_id', 'N/A')}")
            print(f"👤 Name: {candidate.get('name', 'N/A')}")
            print(f"📧 Email: {candidate.get('email', 'N/A')}")
            print(f"📞 Phone: {candidate.get('phone', 'N/A')}")
            
            # Check if call_tracking exists
            if 'call_tracking' in candidate:
                call_tracking = candidate['call_tracking']
                print(f"\n📊 CALL TRACKING DATA FOUND:")
                print(f"   📈 Total Attempts: {call_tracking.get('total_attempts', 0)}")
                print(f"   🚫 Max Attempts: {call_tracking.get('max_attempts', 3)}")
                print(f"   🎯 Status: {call_tracking.get('status', 'N/A')}")
                print(f"   📅 Last Contact: {call_tracking.get('last_contact_date', 'Never')}")
                
                # Show call history
                call_history = call_tracking.get('call_history', [])
                print(f"   📞 Call History ({len(call_history)} calls):")
                
                for j, call in enumerate(call_history, 1):
                    print(f"      📞 Call #{j}:")
                    print(f"         🆔 SID: {call.get('call_sid', 'N/A')}")
                    print(f"         📅 Time: {call.get('initiated_at', 'N/A')}")
                    print(f"         📊 Status: {call.get('status', 'N/A')}")
                    print(f"         🎯 Outcome: {call.get('outcome', 'N/A')}")
                    print(f"         📝 Notes: {call.get('notes', 'N/A')}")
                
                # Show interview details if any
                interview_details = call_tracking.get('interview_details')
                if interview_details:
                    print(f"   📅 INTERVIEW SCHEDULED:")
                    print(f"      🕒 Slot: {interview_details.get('scheduled_slot', 'N/A')}")
                    print(f"      📧 Email Sent: {interview_details.get('email_sent', False)}")
                    print(f"      📅 Scheduled At: {interview_details.get('scheduled_at', 'N/A')}")
                else:
                    print(f"   📅 Interview Details: None scheduled yet")
                    
            else:
                print(f"\n❌ NO CALL TRACKING DATA FOUND")
                print(f"   This candidate hasn't been called yet through the new system")
            
            print("-" * 40)
        
        print("\n" + "=" * 60)
        print("📍 STORAGE SUMMARY:")
        print("=" * 60)
        print("✅ Data is stored in MongoDB Atlas")
        print("✅ Database: ai_interview_schedule") 
        print("✅ Collection: candidates")
        print("✅ Structure: Each candidate document contains:")
        print("   - Basic info (name, phone, email, position, company)")
        print("   - call_tracking object with:")
        print("     - total_attempts (counter)")
        print("     - max_attempts (limit)")
        print("     - status (active/max_attempts/interview_scheduled)")
        print("     - last_contact_date (timestamp)")
        print("     - call_history (array of all calls)")
        print("     - interview_details (when scheduled)")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error checking MongoDB: {e}")

if __name__ == "__main__":
    check_mongodb_storage()