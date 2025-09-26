from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.rest import Client as TwilioClient
from openai import OpenAI
import uvicorn
import re

# Configuration
try:
    from decouple import config
except ImportError:
    def config(key, default=None):
        return default

# Twilio
TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="")
TWILIO_PHONE_NUMBER = config("TWILIO_PHONE_NUMBER", default="")

# OpenAI
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Webhook URL - Auto-detect ngrok or use config
def get_webhook_url():
    try:
        import requests
        response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        if response.status_code == 200:
            tunnels = response.json()["tunnels"]
            for tunnel in tunnels:
                if tunnel["config"]["addr"] == "http://localhost:8000":
                    public_url = tunnel["public_url"]
                    if public_url.startswith("https://"):
                        print(f"Auto-detected ngrok URL: {public_url}")
                        return public_url
    except:
        pass
    
    configured_url = config("WEBHOOK_BASE_URL", default="http://localhost:8000")
    print(f"Using configured URL: {configured_url}")
    return configured_url

WEBHOOK_BASE_URL = get_webhook_url()

# FastAPI app
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Candidate data - Load from environment variables for security
CANDIDATE = {
    "name": config("CANDIDATE_NAME", default="John Doe"),
    "phone": config("CANDIDATE_PHONE", default="+1234567890"),
    "email": config("CANDIDATE_EMAIL", default="candidate@example.com"),
    "position": config("CANDIDATE_POSITION", default="Software Engineer"),
    "company": config("CANDIDATE_COMPANY", default="TechCorp"),
}

TIME_SLOTS = [
    "Monday at 10 AM",
    "Tuesday at 2 PM",
    "Wednesday at 11 AM",
    "Thursday at 3 PM",
]

# Conversation state
conversation_state = {
    "call_active": False,
    "confirmed_slot": None,
    "interaction_count": 0,
}

def reset_conversation_state():
    global conversation_state
    conversation_state = {
        "call_active": False,
        "confirmed_slot": None,
        "interaction_count": 0,
    }

def is_confirmation_response(text):
    """Check if user is confirming the interview"""
    confirmation_patterns = [
        r'\b(yes|yeah|confirm|confirmed|ok|okay|sure|perfect|sounds good|that works|fine)\b',
        r'\b(schedule|book|set)\b.*\b(it|that|interview)\b',
    ]
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in confirmation_patterns)

def get_ai_greeting():
    """Get AI greeting message"""
    return f"Hello {CANDIDATE['name']}! I'm calling from {CANDIDATE['company']} regarding your {CANDIDATE['position']} interview. Are you available to discuss timing?"

@app.post("/twilio-voice")
async def twilio_voice(request: Request):
    """Entry point for Twilio call"""
    print(f"New call started for {CANDIDATE['name']}")
    
    reset_conversation_state()
    conversation_state["call_active"] = True
    
    greeting = get_ai_greeting()
    
    response = f"""
    <Response>
        <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10">
            <Say voice="alice" language="en-IN">{greeting}</Say>
        </Gather>
        <Say voice="alice" language="en-IN">I'm sorry, I didn't hear anything. Goodbye.</Say>
    </Response>
    """
    
    return Response(content=response.strip(), media_type="application/xml")

@app.post("/twilio-process")
async def process_speech(SpeechResult: str = Form(...)):
    """Process candidate response"""
    conversation_state["interaction_count"] += 1
    
    print(f"Turn #{conversation_state['interaction_count']}: Candidate said: '{SpeechResult}'")
    
    # Check if candidate is confirming
    if is_confirmation_response(SpeechResult):
        # Find mentioned time slot or use first available
        mentioned_slot = None
        for slot in TIME_SLOTS:
            if any(word in SpeechResult.lower() for word in slot.lower().split()):
                mentioned_slot = slot
                break
        
        confirmed_slot = mentioned_slot or TIME_SLOTS[0]
        conversation_state["confirmed_slot"] = confirmed_slot
        
        print(f"CONFIRMATION DETECTED! Confirmed slot: {confirmed_slot}")
        
        # Final confirmation and end call
        ai_response = f"Perfect! Your interview is confirmed for {confirmed_slot}. Thank you!"
        
        print(f"AI final response: '{ai_response}'")
        print(f"Call completed - Total interactions: {conversation_state['interaction_count']}")
        
        # End the call
        response_xml = f"""
        <Response>
            <Say voice="alice" language="en-IN">{ai_response}</Say>
            <Hangup/>
        </Response>
        """
        return Response(content=response_xml.strip(), media_type="application/xml")
    
    # If too many interactions, provide guidance
    if conversation_state["interaction_count"] >= 3:
        ai_response = f"I have these slots available: {', '.join(TIME_SLOTS)}. Please say 'confirm' and the time you prefer."
        print(f"AI guidance response: '{ai_response}'")
        
        response_xml = f"""
        <Response>
            <Say voice="alice" language="en-IN">{ai_response}</Say>
            <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10">
                <Say voice="alice" language="en-IN">Please confirm your preferred time slot.</Say>
            </Gather>
            <Say voice="alice" language="en-IN">Thank you. We'll follow up by email.</Say>
        </Response>
        """
        return Response(content=response_xml.strip(), media_type="application/xml")
    
    # Generate AI response
    try:
        if openai_client:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You are a professional recruiter scheduling an interview for {CANDIDATE['name']} for a {CANDIDATE['position']} position at {CANDIDATE['company']}. Be direct and professional. Available slots: {', '.join(TIME_SLOTS)}. Ask them to confirm a specific slot."},
                    {"role": "user", "content": f"Candidate response: '{SpeechResult}'. Respond in under 20 words. Focus on getting them to confirm a specific time slot."}
                ],
                max_tokens=50,
            )
            ai_response = response.choices[0].message.content.strip()
        else:
            ai_response = f"Thank you. Are you available for an interview on {TIME_SLOTS[0]}? Please say 'confirm' if yes."
    except Exception as e:
        print(f"AI generation failed: {e}")
        ai_response = f"Thank you. Are you available for an interview on {TIME_SLOTS[0]}? Please say 'confirm' if yes."

    print(f"AI response: '{ai_response}'")

    response_xml = f"""
    <Response>
        <Say voice="alice" language="en-IN">{ai_response}</Say>
        <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10">
            <Say voice="alice" language="en-IN">Please let me know which time works for you.</Say>
        </Gather>
        <Say voice="alice" language="en-IN">Thank you. We'll send you an email confirmation.</Say>
    </Response>
    """
    return Response(content=response_xml.strip(), media_type="application/xml")

@app.post("/make-actual-call")
async def make_actual_call():
    """Make actual Twilio call"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return {"status": "error", "message": "Twilio credentials missing"}
    
    webhook_url = f"{WEBHOOK_BASE_URL}/twilio-voice"
    
    # Check if webhook URL is publicly accessible
    if "localhost" in WEBHOOK_BASE_URL or "127.0.0.1" in WEBHOOK_BASE_URL:
        return {
            "status": "error", 
            "message": "Webhook URL must be public. Start ngrok with: ngrok http 8000"
        }
    
    try:
        print(f"Initiating call to {CANDIDATE['phone']}")
        print(f"Using webhook: {webhook_url}")
        
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            url=webhook_url,
            to=CANDIDATE["phone"],
            from_=TWILIO_PHONE_NUMBER,
        )
        
        print(f"Call initiated - Call ID: {call.sid}")
        
        return {
            "status": "success",
            "message": f"Call initiated to {CANDIDATE['phone']}",
            "call_sid": call.sid,
            "call_status": call.status,
        }
    except Exception as e:
        print(f"Call failed: {e}")
        return {"status": "error", "message": f"Call failed: {str(e)}"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Interview Caller",
        "candidate": CANDIDATE,
        "config": {
            "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER),
            "openai_configured": bool(OPENAI_API_KEY),
            "webhook_url": WEBHOOK_BASE_URL,
        },
    }

if __name__ == "__main__":
    print("AI Interview Caller - Ready to receive calls")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)