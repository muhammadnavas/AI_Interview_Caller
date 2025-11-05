#!/usr/bin/env python3
"""
Simple test to verify the shortlistedcandidates collection integration
"""

# Add the backend directory to the path so we can import main.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the functions we want to test
try:
    from main import get_all_candidates_from_mongo, fetch_candidate_by_id
    
    print("🧪 Testing shortlistedcandidates collection integration...")
    print("=" * 50)
    
    # Test 1: Get all candidates
    print("📋 Test 1: Fetching all candidates from shortlistedcandidates collection...")
    candidates = get_all_candidates_from_mongo()
    
    if candidates:
        print(f"✅ Found {len(candidates)} candidates:")
        for i, candidate in enumerate(candidates[:3]):  # Show first 3
            print(f"  {i+1}. {candidate.get('name')} ({candidate.get('phone')}) - {candidate.get('email')}")
            print(f"     Position: {candidate.get('position')} at {candidate.get('company')}")
            print(f"     ID: {candidate.get('candidate_id')}")
        
        if len(candidates) > 3:
            print(f"  ... and {len(candidates) - 3} more candidates")
            
        # Test 2: Fetch specific candidate by ID
        if candidates:
            test_candidate_id = candidates[0]['candidate_id']
            print(f"\n👤 Test 2: Fetching specific candidate by ID: {test_candidate_id}")
            
            candidate_info = fetch_candidate_by_id(test_candidate_id)
            
            if candidate_info:
                print("✅ Successfully fetched candidate details:")
                print(f"   Name: {candidate_info.get('name')}")
                print(f"   Phone: {candidate_info.get('phone')}")
                print(f"   Email: {candidate_info.get('email')}")
                print(f"   Position: {candidate_info.get('position')}")
                print(f"   Company: {candidate_info.get('company')}")
            else:
                print("❌ Failed to fetch candidate by ID")
    else:
        print("❌ No candidates found. Check MongoDB connection and collection name.")
        
    print("\n" + "=" * 50)
    print("✅ Test completed!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Test failed with error: {e}")
    import traceback
    traceback.print_exc()