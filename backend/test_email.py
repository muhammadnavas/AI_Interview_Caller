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

import asyncio
import sys
import os
sys.path.append('.')

# Import the main module
from main import send_interview_confirmation_email

async def test_resend_email():
    """Test email sending with Resend API (HTTP-only, no SMTP)"""
    print("🧪 Testing Resend email functionality (HTTP-only)...")
    
    candidate_info = {
        'name': 'Test Candidate',
        'email': 'navasns0409@gmail.com',  # Your test email
        'position': 'Software Engineer', 
        'company': 'LinkUp'
    }
    
    try:
        result = await send_interview_confirmation_email(
            candidate_info, 
            'Monday at 10 AM', 
            'TEST-CALL-RESEND-123'
        )
        
        print(f"✅ Email test result: {result}")
        
        # Check if email was actually sent via HTTP API
        if result.get('email_sent') == True:
            print(f"🎉 SUCCESS: Email sent via {result.get('service', 'Unknown')}")
        elif result.get('status') == 'logged_for_manual':
            print("⚠️  Email logged for manual processing")
        else:
            print(f"❌ Email failed: {result.get('error', 'Unknown error')}")
            
        return result
    except Exception as e:
        print(f"❌ Email test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_resend_email())
    print(f"\n🎯 Final test result: {result}")

if __name__ == "__main__":
    print("=" * 50)
    print("EMAIL API TEST")
    print("=" * 50)
    asyncio.run(test_email_sending())
    print("=" * 50)