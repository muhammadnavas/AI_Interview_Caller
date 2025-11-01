#!/usr/bin/env python3
"""
Complete Twilio Configuration Checker and Fixer
"""

def check_twilio_config():
    print("🔧 TWILIO CONFIGURATION CHECKER")
    print("=" * 50)
    
    print("\n✅ STEP 1: VERIFY YOUR APP STATUS")
    print("Your app URL: https://ai-interview-caller-wz24.onrender.com/")
    print("Test it: curl https://ai-interview-caller-wz24.onrender.com/")
    print("Should show: AI Interview Caller status")
    
    print("\n🎯 STEP 2: CORRECT WEBHOOK URL")
    print("Copy this EXACT URL for Twilio Console:")
    print("┌─────────────────────────────────────────────────────────┐")
    print("│ https://ai-interview-caller-wz24.onrender.com/twilio-voice │")
    print("└─────────────────────────────────────────────────────────┘")
    
    print("\n📋 STEP 3: TWILIO CONSOLE CONFIGURATION")
    print("1. Go to: https://console.twilio.com/")
    print("2. Navigate: Phone Numbers → Manage → Active Numbers")  
    print("3. Click on: +17853673103")
    print("4. Find 'Voice Configuration' section")
    print("5. Set these EXACT values:")
    print("   ┌── Webhook URL ────────────────────────────────────────┐")
    print("   │ https://ai-interview-caller-wz24.onrender.com/twilio-voice │")
    print("   └───────────────────────────────────────────────────────┘")
    print("   ┌── HTTP Method ─┐")
    print("   │ POST           │")
    print("   └────────────────┘")
    print("6. Click 'Save Configuration'")
    
    print("\n🧪 STEP 4: TEST COMMANDS")
    print("Run these to verify:")
    print("curl https://ai-interview-caller-wz24.onrender.com/twilio-voice")
    print("# Should return: webhook is ready")
    print()
    print("curl -X POST https://ai-interview-caller-wz24.onrender.com/twilio-voice")
    print("# Should return: XML response")
    
    print("\n🚨 STEP 5: COMMON MISTAKES TO AVOID")
    print("❌ Using http:// instead of https://")
    print("❌ Adding extra slashes: /twilio-voice/ ❌")
    print("❌ Setting method to GET instead of POST")
    print("❌ Using old ngrok URLs")
    print("❌ Typos in the domain name")
    
    print("\n🎉 STEP 6: MAKE TEST CALL")
    print("After saving configuration:")
    print("1. Wait 30 seconds for Twilio to update")
    print("2. Call +17853673103")
    print("3. Should hear: 'Hello! This is AI Interview Scheduler...'")
    print("4. If you hear this message, webhook is working! 🎊")
    
    print("\n💡 STEP 7: IF STILL NOT WORKING")
    print("Check these in order:")
    print("1. Webhook URL is EXACTLY as shown above")
    print("2. Method is POST (not GET)")
    print("3. No extra characters or spaces in URL")
    print("4. Try testing from a different phone")
    print("5. Check Twilio Console 'Monitor' → 'Logs' for error details")

if __name__ == "__main__":
    check_twilio_config()