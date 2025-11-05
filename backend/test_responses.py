#!/usr/bin/env python3
"""
Test what the AI interview call endpoint returns with shortlistedcandidates data
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import get_all_candidates_from_mongo, fetch_candidate_by_id, get_candidate_call_status
import json

def test_endpoint_responses():
    print("🧪 Testing AI Interview Call Endpoint Response")
    print("=" * 60)
    
    # Test 1: Get candidates list response
    print("📋 1. GET /list-candidates Response:")
    candidates = get_all_candidates_from_mongo()
    
    if candidates:
        response_data = {
            "status": "success",
            "candidates": candidates,
            "total": len(candidates)
        }
        print(json.dumps(response_data, indent=2))
        
        candidate_id = candidates[0]['candidate_id']
        print(f"\n👤 2. Candidate Details for ID: {candidate_id}")
        
        # Test 2: Fetch individual candidate
        candidate_info = fetch_candidate_by_id(candidate_id)
        if candidate_info:
            print("   Fetched candidate info:")
            print(json.dumps(candidate_info, indent=2, default=str))
            
            # Test 3: Check call status
            print(f"\n📞 3. Call Status Check:")
            call_status = get_candidate_call_status(candidate_id)
            print(json.dumps(call_status, indent=2))
            
            # Test 4: Simulate make-actual-call response
            print(f"\n🎯 4. Simulated POST /make-actual-call Response:")
            print(f"   Request Body: {{'candidate_id': '{candidate_id}'}}")
            print("\n   Expected Response Structure:")
            
            if candidate_info.get('phone'):
                success_response = {
                    "status": "success",
                    "message": f"Call initiated to {candidate_info.get('phone')}",
                    "call_sid": "CA123456789abcdef",  # Would be actual Twilio Call SID
                    "call_status": "queued",  # Initial Twilio status
                    "webhook_url": "https://ai-interview-caller-wz24.onrender.com/twilio-voice",
                    "candidate": candidate_info.get('name'),
                    "initial_status": "queued"
                }
                print(json.dumps(success_response, indent=2))
            else:
                error_response = {
                    "status": "error",
                    "message": f"Invalid phone number for candidate {candidate_id}: {candidate_info.get('phone')}. Please update the candidate's phone number."
                }
                print(json.dumps(error_response, indent=2))
        else:
            print("   ❌ Could not fetch candidate info")
    else:
        print("   ❌ No candidates found")
        
    print("\n" + "=" * 60)

if __name__ == "__main__":
    try:
        test_endpoint_responses()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()