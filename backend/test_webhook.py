#!/usr/bin/env python3
"""
Test webhook endpoint directly to see if it's working
"""
import requests
import json

def test_webhook():
    # Replace with your actual webhook URL
    webhook_url = input("Enter your webhook URL (e.g., https://your-app.onrender.com/twilio-voice): ")
    
    # Simulate Twilio webhook data
    test_data = {
        "CallSid": "CAtest123456789",
        "From": "+1234567890", 
        "To": "+1987654321",
        "CallStatus": "ringing",
        "Direction": "inbound"
    }
    
    print(f"Testing webhook: {webhook_url}")
    print(f"Test data: {test_data}")
    
    try:
        response = requests.post(webhook_url, data=test_data, timeout=10)
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Content: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ Webhook is working!")
        else:
            print(f"\n❌ Webhook failed with status {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error calling webhook: {e}")

if __name__ == "__main__":
    test_webhook()