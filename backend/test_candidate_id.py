#!/usr/bin/env python3
"""
Test script for the candidate_id system
"""
import requests
import json

# Test endpoints
BASE_URL = "http://localhost:8000"

def test_list_candidates():
    """Test listing candidates to see their candidate_id values"""
    print("🔍 Testing candidate listing...")
    try:
        response = requests.get(f"{BASE_URL}/list-candidates")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {data.get('total', 0)} candidates:")
            for candidate in data.get('candidates', []):
                print(f"   - ID: {candidate.get('id')}")
                print(f"     Name: {candidate.get('name')}")
                print(f"     Phone: {candidate.get('phone')}")
                print(f"     Email: {candidate.get('email')}")
                print()
            return data.get('candidates', [])
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return []

def test_call_candidate(candidate_id):
    """Test calling a candidate with proper JSON format"""
    print(f"📞 Testing call to candidate: {candidate_id}")
    try:
        payload = {"candidate_id": candidate_id}
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(f"{BASE_URL}/call-candidate", 
                                json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Call initiated successfully!")
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            if 'call_sid' in data:
                print(f"   Call SID: {data.get('call_sid')}")
        else:
            print(f"❌ Call failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Call error: {e}")

if __name__ == "__main__":
    print("🚀 Testing Candidate ID System\n")
    
    # First, list candidates to see their IDs
    candidates = test_list_candidates()
    
    if candidates:
        # Test calling the first candidate
        first_candidate_id = candidates[0].get('id')
        if first_candidate_id:
            print()
            test_call_candidate(first_candidate_id)
        else:
            print("❌ No candidate ID found in first candidate")
    else:
        print("❌ No candidates found to test with")