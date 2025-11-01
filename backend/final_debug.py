#!/usr/bin/env python3
"""
Final webhook debugging - Test Twilio configuration step by step
"""

def final_debug():
    print("🔍 FINAL TWILIO WEBHOOK DEBUG")
    print("=" * 50)
    
    print("\n1. ✅ YOUR APP IS WORKING:")
    print("   URL: https://ai-interview-caller-wz24.onrender.com/")
    print("   Status: CONFIRMED WORKING ✅")
    
    print("\n2. 🎯 WEBHOOK URL SHOULD BE:")
    print("   https://ai-interview-caller-wz24.onrender.com/twilio-voice")
    print("   Method: POST")
    print("   ^ Copy this EXACT URL ☝️")
    
    print("\n3. 🔧 CHECK TWILIO CONSOLE NOW:")
    print("   a) Go to: https://console.twilio.com/")
    print("   b) Click: Phone Numbers → Manage → Active Numbers")
    print("   c) Click on: +17853673103")
    print("   d) Scroll to 'Voice Configuration' section")
    print("   e) Check webhook URL is EXACTLY:")
    print("      https://ai-interview-caller-wz24.onrender.com/twilio-voice")
    print("   f) Method must be: POST")
    
    print("\n4. ❌ COMMON MISTAKES TO CHECK:")
    print("   • Using http:// instead of https://")
    print("   • Extra slash: /twilio-voice/ instead of /twilio-voice")  
    print("   • Wrong domain name or typo")
    print("   • Method set to GET instead of POST")
    print("   • Old ngrok URL still configured")
    
    print("\n5. 🧪 TEST COMMANDS:")
    print("   Test 1 (should work):")
    print("   curl https://ai-interview-caller-wz24.onrender.com/")
    print("")
    print("   Test 2 (should return XML):")
    print("   curl -X POST https://ai-interview-caller-wz24.onrender.com/twilio-voice")
    
    print("\n6. 📋 EXACT STEPS TO FIX:")
    print("   1. Copy: https://ai-interview-caller-wz24.onrender.com/twilio-voice")
    print("   2. Go to Twilio Console → Phone Numbers")
    print("   3. Click your number: +17853673103")
    print("   4. Paste URL in 'Voice webhook URL' field")
    print("   5. Select 'POST' method")
    print("   6. Click 'Save Configuration'")
    print("   7. Make test call immediately")
    
    print("\n🚨 IF STILL FAILING:")
    print("   Screenshot your Twilio phone number configuration")
    print("   and share it - there's likely a typo or wrong setting")
    
if __name__ == "__main__":
    final_debug()