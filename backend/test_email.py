#!/usr/bin/env python3
"""
Test script for email functionality with Resend API
"""
import asyncio
import sys
import os

# Add current directory to path to import main
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import send_interview_confirmation_email, config

async def test_email_sending():
    """Test the email sending functionality"""
    print("🧪 Testing Resend Email API Integration...")
    
    # Test candidate info
    candidate_info = {
        'name': 'Test Candidate',
        'email': 'navasns0409@gmail.com',  # Use your email for testing
        'position': 'AI Engineer', 
        'company': 'LinkUp',
        'raw': None  # No MongoDB document for test
    }
    
    try:
        print(f"📧 Sending test email to: {candidate_info['email']}")
        print(f"🔑 Resend API Key configured: {'Yes' if config('RESEND_API_KEY') else 'No'}")
        
        result = await send_interview_confirmation_email(
            candidate_info, 
            'Monday at 10 AM', 
            'TEST_CALL_123'
        )
        
        print(f"\n✅ Email Function Result:")
        print(f"   Status: {result.get('status', 'unknown')}")
        print(f"   Email Sent: {result.get('email_sent', False)}")
        print(f"   Recipient: {result.get('recipient', 'unknown')}")
        print(f"   Method: {result.get('method', 'unknown')}")
        
        if result.get('email_sent'):
            print("🎉 SUCCESS: Email should be delivered!")
        else:
            print(f"❌ FAILED: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 50)
    print("EMAIL API TEST")
    print("=" * 50)
    asyncio.run(test_email_sending())
    print("=" * 50)