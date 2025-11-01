#!/usr/bin/env python3
"""
Test script to debug interview confirmation functionality
This script simulates a webhook call with interview confirmation
"""

import sys
import os
import asyncio
from datetime import datetime

# Add the backend directory to the path to import main.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_candidate_lookup():
    """Test if we can find candidates by phone number"""
    print("=== Testing Candidate Lookup ===")
    
    # Import after adding to path
    from main import find_candidate_by_phone, load_candidate_from_mongo
    
    # Test loading all candidates
    print("\n1. Loading all candidates from MongoDB:")
    candidates = load_candidate_from_mongo()
    print(f"Found {len(candidates)} candidates")
    for candidate in candidates:
        if isinstance(candidate, dict):
            print(f"  - {candidate.get('name', 'Unknown')} ({candidate.get('phone', 'No phone')}) ID: {candidate.get('id', 'No ID')}")
        else:
            print(f"  - Invalid candidate format: {candidate}")
    
    if candidates:
        # Test finding by phone
        test_phone = candidates[0].get('phone')
        print(f"\n2. Testing find_candidate_by_phone with: {test_phone}")
        found = find_candidate_by_phone(test_phone)
        if found:
            print(f"✅ Found candidate: {found.get('name')} (ID: {found.get('id')})")
        else:
            print("❌ Could not find candidate by phone")
            
        # Test with Twilio format (adding +1 prefix if not present)
        if test_phone and not test_phone.startswith("+1"):
            twilio_format = f"+1{test_phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')}"
            print(f"\n3. Testing Twilio format: {twilio_format}")
            found_twilio = find_candidate_by_phone(twilio_format)
            if found_twilio:
                print(f"✅ Found with Twilio format: {found_twilio.get('name')}")
            else:
                print("❌ Could not find with Twilio format")

async def test_interview_confirmation():
    """Test the complete interview confirmation flow"""
    print("\n=== Testing Interview Confirmation Flow ===")
    
    from main import (find_candidate_by_phone, update_candidate_interview_scheduled, 
                     send_interview_confirmation_email, ConversationSession)
    
    # Find a test candidate
    candidates = find_candidate_by_phone("+91 8660761403")  # Using default phone
    if not candidates:
        print("❌ No test candidate found. Creating mock candidate...")
        candidates = {
            'id': 'test_candidate_123',
            'name': 'Test Candidate',
            'email': 'test@example.com',
            'phone': '+91 8660761403',
            'position': 'Software Developer',
            'company': 'Test Company'
        }
    
    print(f"Using test candidate: {candidates.get('name')} (ID: {candidates.get('id')})")
    
    # Test MongoDB update
    print("\n1. Testing MongoDB interview update...")
    interview_details = {
        "scheduled_slot": "Monday at 10 AM",
        "call_sid": "test_call_123",
        "email_sent": False,
        "scheduled_at": datetime.now().isoformat()
    }
    
    try:
        success = update_candidate_interview_scheduled(candidates.get('id'), interview_details)
        if success:
            print("✅ MongoDB update successful")
        else:
            print("❌ MongoDB update failed")
    except Exception as e:
        print(f"❌ MongoDB update error: {e}")
    
    # Test email sending
    print("\n2. Testing email confirmation...")
    try:
        email_success = await send_interview_confirmation_email(
            candidates, 
            "Monday at 10 AM", 
            "test_call_123"
        )
        if email_success:
            print("✅ Email sent successfully")
        else:
            print("❌ Email sending failed")
    except Exception as e:
        print(f"❌ Email error: {e}")

def test_mongodb_connection():
    """Test MongoDB connectivity"""
    print("\n=== Testing MongoDB Connection ===")
    
    try:
        from main import config
        from pymongo import MongoClient
        
        mongodb_uri = config("MONGODB_URI", default="mongodb://localhost:27017")
        print(f"MongoDB URI: {mongodb_uri}")
        
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")
        
        db = client[db_name]
        coll = db[coll_name]
        
        # Test connection
        count = coll.count_documents({})
        print(f"✅ Connected to MongoDB. Found {count} documents in {db_name}.{coll_name}")
        
        # Show sample documents
        docs = list(coll.find().limit(2))
        for i, doc in enumerate(docs, 1):
            print(f"Sample doc {i}: {doc.get('name', 'Unknown')} - {doc.get('phone', 'No phone')}")
            
    except Exception as e:
        print(f"❌ MongoDB connection error: {e}")

if __name__ == "__main__":
    print("🔧 Interview Confirmation Test Suite")
    print("=" * 50)
    
    # Test MongoDB connection first
    test_mongodb_connection()
    
    # Test candidate lookup
    test_candidate_lookup()
    
    # Test interview confirmation flow
    asyncio.run(test_interview_confirmation())
    
    print("\n" + "=" * 50)
    print("✅ Test suite completed!")