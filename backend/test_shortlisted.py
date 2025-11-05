#!/usr/bin/env python3
"""
Test script to verify the shortlistedcandidates collection integration
"""
import requests
import json

# Test endpoint to list candidates from shortlistedcandidates collection
try:
    print("🧪 Testing shortlistedcandidates collection integration...")
    
    response = requests.get('http://localhost:8000/list-candidates')
    if response.status_code == 200:
        data = response.json()
        print('✅ Successfully fetched candidates from shortlistedcandidates collection:')
        print(json.dumps(data, indent=2))
        
        if data.get('candidates') and len(data['candidates']) > 0:
            # Try to call the first candidate
            candidate_id = data['candidates'][0]['id']
            print(f"\n🧪 Testing call to candidate ID: {candidate_id}")
            
            call_response = requests.post('http://localhost:8000/make-actual-call', 
                                        json={"candidate_id": candidate_id}, 
                                        headers={"Content-Type": "application/json"})
            
            if call_response.status_code == 200:
                call_data = call_response.json()
                print('✅ Call test response:')
                print(json.dumps(call_data, indent=2))
            else:
                print(f'❌ Call test failed: {call_response.status_code}')
                print(call_response.text)
        else:
            print('⚠️ No candidates found to test calling')
            
    else:
        print(f'❌ Error: {response.status_code}')
        print(response.text)
        
except Exception as e:
    print(f'❌ Test failed with error: {e}')