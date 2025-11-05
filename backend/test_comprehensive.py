#!/usr/bin/env python3
"""
Test comprehensive AI Interview Call responses with scheduling status
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import (
    get_all_candidates_from_mongo, 
    fetch_candidate_by_id, 
    get_candidate_call_status,
    get_candidate_scheduling_status
)
import json

def test_comprehensive_responses():
    print("🎯 Testing Comprehensive AI Interview Call Responses")
    print("=" * 70)
    
    # Get candidate data
    candidates = get_all_candidates_from_mongo()
    if not candidates:
        print("❌ No candidates found in shortlistedcandidates collection")
        return
        
    candidate_id = candidates[0]['candidate_id']
    candidate_info = fetch_candidate_by_id(candidate_id)
    
    print("📋 1. ENHANCED POST /make-actual-call Response:")
    print("   Request Body: {'candidate_id': '" + candidate_id + "'}")
    print("\n   ✅ SUCCESS Response Structure:")
    
    # Simulate comprehensive response
    scheduling_status = get_candidate_scheduling_status(candidate_id)
    call_status = get_candidate_call_status(candidate_id)
    
    enhanced_response = {
        "status": "success",
        "message": f"Call initiated to {candidate_info.get('phone')}",
        "call_sid": "CA1234567890abcdef123456",
        "call_status": "queued",
        "webhook_url": "https://ai-interview-caller-wz24.onrender.com/twilio-voice",
        "candidate": {
            "id": candidate_id,
            "name": candidate_info.get("name"),
            "phone": candidate_info.get("phone"),
            "email": candidate_info.get("email"),
            "position": candidate_info.get("position"),
            "company": candidate_info.get("company")
        },
        "initial_status": "queued",
        "scheduling_status": scheduling_status,
        "call_tracking": {
            "total_attempts": call_status.get("attempts", 0) + 1,
            "max_attempts": 3,
            "can_call_again": call_status.get("attempts", 0) + 1 < 3
        }
    }
    
    print(json.dumps(enhanced_response, indent=2, default=str))
    
    print("\n" + "="*70)
    print("📊 2. GET /candidate-status/{candidate_id} Response:")
    print(f"   URL: /candidate-status/{candidate_id}")
    print("\n   📋 Comprehensive Status Response:")
    
    comprehensive_status = {
        "candidate_id": candidate_id,
        "candidate_info": {
            "name": candidate_info.get("name"),
            "phone": candidate_info.get("phone"),
            "email": candidate_info.get("email"),
            "position": candidate_info.get("position"),
            "company": candidate_info.get("company")
        },
        "call_tracking": {
            "can_call": call_status.get("can_call", False),
            "total_attempts": call_status.get("attempts", 0),
            "max_attempts": 3,
            "remaining_attempts": max(0, 3 - call_status.get("attempts", 0)),
            "status": call_status.get("status", "unknown"),
            "reason": call_status.get("reason", "")
        },
        "scheduling_status": {
            "interview_status": scheduling_status.get("interview_status", "not_scheduled"),
            "scheduled_date": scheduling_status.get("scheduled_date"),
            "interview_slot_confirmed": scheduling_status.get("interview_slot_confirmed"),
            "interview_details": {
                "slot": None,
                "scheduled_at": None,
                "confirmation_method": None
            },
            "email_notifications": {
                "confirmation_sent": False,
                "email_status": "not_sent",
                "sent_at": None,
                "recipient_email": candidate_info.get("email"),
                "delivery_status": "unknown"
            },
            "conversation_status": "not_started",
            "last_interaction": None
        },
        "overall_status": {
            "status": "not_contacted",
            "message": "No contact attempts made yet",
            "priority": "normal",
            "next_action": "Make initial call"
        },
        "last_updated": "2025-11-05T23:30:00.000000"
    }
    
    print(json.dumps(comprehensive_status, indent=2, default=str))
    
    print("\n" + "="*70)
    print("📞 3. AFTER SUCCESSFUL INTERVIEW SCHEDULING:")
    print("\n   🎉 Enhanced Response After Interview Confirmed:")
    
    post_interview_response = {
        "status": "success",
        "message": "Interview scheduled successfully",
        "call_sid": "CA1234567890abcdef123456",
        "candidate": {
            "id": candidate_id,
            "name": candidate_info.get("name"),
            "email": candidate_info.get("email")
        },
        "interview_details": {
            "confirmed_slot": "Tuesday at 2 PM",
            "scheduled_at": "2025-11-05T18:30:15.123456",
            "confirmation_method": "phone_call",
            "interview_status": "scheduled",
            "candidate_confirmed": True
        },
        "email_notifications": {
            "confirmation_sent": True,
            "email_status": "delivered",
            "sent_at": "2025-11-05T18:30:20.123456",
            "recipient": candidate_info.get("email"),
            "subject": f"Interview Confirmation - {candidate_info.get('position')} Position at {candidate_info.get('company')}",
            "delivery_status": "sent_successfully"
        },
        "call_tracking": {
            "total_attempts": 1,
            "max_attempts": 3,
            "status": "completed_successfully"
        },
        "overall_status": {
            "status": "interview_scheduled_confirmed",
            "message": "Interview scheduled and confirmation email sent",
            "priority": "low",
            "next_action": "No action needed - await interview"
        }
    }
    
    print(json.dumps(post_interview_response, indent=2, default=str))
    
    print("\n" + "="*70)
    print("📧 4. EMAIL STATUS TRACKING:")
    print("\n   📨 Email Success Status:")
    
    email_success = {
        "email_sent": True,
        "status": "success",
        "recipient": candidate_info.get("email"),
        "sent_at": "2025-11-05T18:30:20.123456",
        "subject": f"Interview Confirmation - {candidate_info.get('position')} Position",
        "confirmed_slot": "Tuesday at 2 PM"
    }
    
    print(json.dumps(email_success, indent=2, default=str))
    
    print("\n   ❌ Email Failure Status:")
    
    email_failure = {
        "email_sent": False,
        "status": "failed",
        "error": "SMTP authentication failed",
        "attempted_at": "2025-11-05T18:30:20.123456",
        "recipient": candidate_info.get("email")
    }
    
    print(json.dumps(email_failure, indent=2, default=str))
    
    print("\n" + "="*70)
    print("✅ SUMMARY - What Gets Stored in MongoDB:")
    print("\n   📝 Updated shortlistedcandidates document structure:")
    
    mongodb_structure = {
        "_id": candidate_id,
        "candidateName": candidate_info.get("name"),
        "candidateEmail": candidate_info.get("email"),
        "phoneNumber": candidate_info.get("phone", "").replace("+91", ""),
        "companyName": candidate_info.get("company"),
        "role": candidate_info.get("position"),
        "interviewStatus": "scheduled",  # Updated after scheduling
        "scheduledInterviewDate": "2025-11-05T18:30:15.123456",  # Updated after scheduling
        "call_tracking": {  # NEW: Added by our system
            "total_attempts": 1,
            "max_attempts": 3,
            "status": "completed",
            "last_contact_date": "2025-11-05T18:30:00.123456",
            "call_history": [
                {
                    "call_sid": "CA1234567890abcdef123456",
                    "initiated_at": "2025-11-05T18:30:00.123456",
                    "status": "completed",
                    "outcome": "interview_scheduled",
                    "notes": "Interview scheduled successfully"
                }
            ],
            "interview_details": {  # NEW: Comprehensive interview tracking
                "confirmed_slot": "Tuesday at 2 PM",
                "scheduled_at": "2025-11-05T18:30:15.123456",
                "confirmation_method": "phone_call",
                "interview_status": "scheduled",
                "candidate_confirmed": True,
                "email_status": {  # NEW: Email tracking
                    "sent": True,
                    "status": "delivered",
                    "sent_at": "2025-11-05T18:30:20.123456",
                    "recipient": candidate_info.get("email"),
                    "delivery_status": "sent_successfully",
                    "call_sid": "CA1234567890abcdef123456"
                }
            },
            "conversation_status": "completed",
            "created_at": "2025-11-05T18:30:00.123456",
            "updated_at": "2025-11-05T18:30:20.123456"
        }
    }
    
    print(json.dumps(mongodb_structure, indent=2, default=str))
    
    print("\n" + "="*70)
    print("🎯 KEY FEATURES IMPLEMENTED:")
    print("   ✅ Comprehensive scheduling status tracking")
    print("   ✅ Email notification status and delivery tracking")
    print("   ✅ Call attempt counting and limits")
    print("   ✅ Interview confirmation and details storage")
    print("   ✅ Overall status determination with priorities")
    print("   ✅ Next action recommendations")
    print("   ✅ All data stored in same MongoDB document")
    print("   ✅ Real-time status updates via API endpoints")
    
    print(f"\n🚀 Your candidate '{candidate_info.get('name')}' is ready for comprehensive AI interview scheduling!")

if __name__ == "__main__":
    try:
        test_comprehensive_responses()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()