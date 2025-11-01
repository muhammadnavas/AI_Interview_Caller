#!/usr/bin/env python3
"""
Debug webhook connectivity issues
"""

def debug_webhook_setup():
    print("=== TWILIO WEBHOOK DEBUG GUIDE ===\n")
    
    print("1. CHECK YOUR RENDER APP STATUS:")
    print("   - Go to https://dashboard.render.com")
    print("   - Find your AI Interview Caller service")
    print("   - Check if it shows 'Live' status (green)")
    print("   - Copy the service URL (e.g., https://your-app.onrender.com)")
    print()
    
    print("2. TEST YOUR RENDER APP DIRECTLY:")
    print("   - Open browser and go to: https://your-app.onrender.com")
    print("   - You should see the API status page")
    print("   - If you get 404/500 error, your app isn't deployed properly")
    print()
    
    print("3. CHECK TWILIO CONSOLE CONFIGURATION:")
    print("   - Go to https://console.twilio.com/")
    print("   - Navigate to Phone Numbers > Manage > Active Numbers")
    print("   - Click on your Twilio phone number")
    print("   - In 'Voice' section, check webhook URL:")
    print("     Should be: https://your-app.onrender.com/twilio-voice")
    print("     Method should be: HTTP POST")
    print()
    
    print("4. TEST WEBHOOK ENDPOINT DIRECTLY:")
    print("   - Use curl or Postman to test:")
    print("   curl -X POST https://your-app.onrender.com/twilio-voice \\")
    print("        -d 'CallSid=test123' \\")
    print("        -d 'From=%2B1234567890' \\")
    print("        -d 'To=%2B0987654321'")
    print("   - Should return XML response")
    print()
    
    print("5. CHECK RENDER LOGS:")
    print("   - In Render dashboard, click on your service")
    print("   - Go to 'Logs' tab")
    print("   - Make a test call and watch for log entries")
    print("   - Look for 'TWILIO WEBHOOK CALLED' message")
    print()
    
    print("6. COMMON ISSUES:")
    print("   ❌ Wrong URL: Using localhost instead of Render URL")
    print("   ❌ HTTP instead of HTTPS in Twilio webhook")
    print("   ❌ App not deployed or crashed")
    print("   ❌ Environment variables missing on Render")
    print("   ❌ Typo in webhook URL")
    print()
    
    print("7. ENVIRONMENT VARIABLES ON RENDER:")
    print("   Make sure these are set in Render dashboard:")
    print("   - TWILIO_ACCOUNT_SID")
    print("   - TWILIO_AUTH_TOKEN") 
    print("   - TWILIO_PHONE_NUMBER")
    print("   - WEBHOOK_BASE_URL (should be your Render app URL)")
    print()

if __name__ == "__main__":
    debug_webhook_setup()