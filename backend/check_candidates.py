#!/usr/bin/env python3
"""
Quick check of candidates in database
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import get_all_candidates_from_mongo, get_candidate_call_status

def check_candidates():
    candidates = get_all_candidates_from_mongo()
    print(f"Found {len(candidates)} candidates:")
    
    for i, c in enumerate(candidates):
        candidate_id = c.get("candidate_id")
        print(f"\n{i+1}. Candidate Details:")
        print(f"   ID: {candidate_id}")
        print(f"   Name: {c.get('name')}")
        print(f"   Phone: {c.get('phone')}")
        print(f"   Email: {c.get('email')}")
        print(f"   Position: {c.get('position')}")
        print(f"   Company: {c.get('company')}")
        
        # Check call status
        if candidate_id:
            call_status = get_candidate_call_status(candidate_id)
            print(f"   Call Status: {call_status}")

if __name__ == "__main__":
    check_candidates()