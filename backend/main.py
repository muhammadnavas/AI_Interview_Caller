from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.rest import Client as TwilioClient
from openai import OpenAI
import uvicorn
import re
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('conversation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
app = FastAPI(title="AI Interview Caller", description="Automated interview scheduling with conversation tracking")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    try:
        init_database()
        logger.info("Database initialized successfully")
        
        # Validate critical configuration
        config_issues = []
        if not TWILIO_ACCOUNT_SID:
            config_issues.append("TWILIO_ACCOUNT_SID not configured")
        if not TWILIO_AUTH_TOKEN:
            config_issues.append("TWILIO_AUTH_TOKEN not configured")
        if not TWILIO_PHONE_NUMBER:
            config_issues.append("TWILIO_PHONE_NUMBER not configured")
        if not OPENAI_API_KEY:
            config_issues.append("OPENAI_API_KEY not configured")
        
        if config_issues:
            logger.warning(f"Configuration issues detected: {', '.join(config_issues)}")
            logger.warning("Some features may not work properly. Check your .env file.")
        else:
            logger.info("All configuration validated successfully")
        
        logger.info("AI Interview Caller service started successfully")
        logger.info(f"Webhook URL: {WEBHOOK_BASE_URL}")
        logger.info(f"Candidate: {CANDIDATE['name']} ({CANDIDATE['phone']})")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Candidate data - Load from environment variables for security
def load_candidate_from_mongo() -> dict | None:
    """Try to load a candidate document from MongoDB.

    Priority: if CANDIDATE_EMAIL is set in env, query by email; otherwise return the first document.
    Returns a dict with keys: name, phone, email, position, company or None on failure/not found.
    """
    try:
        # Import locally so the app can still start even if pymongo isn't installed yet
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning("pymongo not installed; skipping MongoDB candidate load")
            return None

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return None

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")

        db = client[db_name]
        coll = db[coll_name]

        email = config("CANDIDATE_EMAIL", default=None)
        query = {"email": email} if email else {}

        doc = coll.find_one(query) if query else coll.find_one()
        if not doc:
            return None

        return {
            "name": doc.get("name") or doc.get("full_name") or doc.get("candidate_name"),
            "phone": doc.get("phone") or doc.get("phone_number"),
            "email": doc.get("email"),
            "position": doc.get("position") or doc.get("role"),
            "company": doc.get("company") or doc.get("employer"),
        }
    except Exception as e:
        logger.warning(f"Could not load candidate from MongoDB: {e}")
        return None


# Prefer candidate from MongoDB when available, fall back to env vars
mongo_candidate = load_candidate_from_mongo()
if mongo_candidate:
    CANDIDATE = mongo_candidate
    logger.info(f"Loaded candidate from MongoDB: {CANDIDATE.get('email')}")
else:
    CANDIDATE = {
        "name": config("CANDIDATE_NAME", default="John Doe"),
        "phone": config("CANDIDATE_PHONE", default="+91 8660761403"),
        "email": config("CANDIDATE_EMAIL", default="navasns0409@gmail.com"),
        "position": config("CANDIDATE_POSITION", default="Software Engineer"),
        "company": config("CANDIDATE_COMPANY", default="TechCorp"),
    }

TIME_SLOTS = [
    "Monday at 10 AM",
    "Tuesday at 2 PM",
    "Wednesday at 11 AM",
    "Thursday at 3 PM",
]

# Data models for conversation tracking
@dataclass
class ConversationTurn:
    turn_number: int
    candidate_input: str
    ai_response: str
    timestamp: str
    intent_detected: Optional[str] = None
    confidence_score: Optional[float] = None

@dataclass
class ConversationSession:
    call_sid: str
    candidate_phone: str
    start_time: str
    end_time: Optional[str] = None
    status: str = "active"  # active, completed, failed
    confirmed_slot: Optional[str] = None
    turns: List[ConversationTurn] = None
    # optional candidate info attached to this session
    candidate: Optional[dict] = None
    
    def __post_init__(self):
        if self.turns is None:
            self.turns = []

# Global conversation sessions storage
conversation_sessions: Dict[str, ConversationSession] = {}

# Database initialization
def init_database():
    """Initialize SQLite database for conversation persistence"""
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            call_sid TEXT PRIMARY KEY,
            candidate_phone TEXT,
            start_time TEXT,
            end_time TEXT,
            status TEXT,
            confirmed_slot TEXT,
            turns_json TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sid TEXT,
            turn_number INTEGER,
            candidate_input TEXT,
            ai_response TEXT,
            timestamp TEXT,
            intent_detected TEXT,
            confidence_score REAL,
            FOREIGN KEY (call_sid) REFERENCES conversation_sessions (call_sid)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def save_conversation_session(session: ConversationSession):
    """Save conversation session to database"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversation_sessions 
            (call_sid, candidate_phone, start_time, end_time, status, confirmed_slot, turns_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            session.call_sid,
            session.candidate_phone,
            session.start_time,
            session.end_time,
            session.status,
            session.confirmed_slot,
            json.dumps([asdict(turn) for turn in session.turns])
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved conversation session: {session.call_sid}")
    except Exception as e:
        logger.error(f"Error saving conversation session: {e}")

def get_or_create_session(call_sid: str, candidate_phone: str, candidate: Optional[dict] = None) -> ConversationSession:
    """Get existing session or create new one"""
    if call_sid in conversation_sessions:
        return conversation_sessions[call_sid]
    
    session = ConversationSession(
        call_sid=call_sid,
        candidate_phone=candidate_phone,
        start_time=datetime.now().isoformat(),
        turns=[],
        candidate=candidate
    )
    conversation_sessions[call_sid] = session
    save_conversation_session(session)
    return session

def analyze_intent(text: str) -> tuple[str, float]:
    """Analyze user intent and return intent type with confidence score"""
    text_lower = text.lower().strip()
    
    # Confirmation patterns
    confirmation_patterns = [
        (r'\b(yes|yeah|yep|confirm|confirmed|ok|okay|sure|perfect|sounds good|that works|fine|absolutely|definitely)\b', 0.9),
        (r'\b(schedule|book|set)\b.*\b(it|that|interview)\b', 0.8),
        (r'\b(good|great|works for me)\b', 0.7),
    ]
    
    # Rejection patterns
    rejection_patterns = [
        (r'\b(no|nope|can\'t|cannot|not available|busy|unavailable|won\'t work)\b', 0.9),
        (r'\b(different time|another time|reschedule)\b', 0.8),
    ]
    
    # Time mention patterns
    time_patterns = [
        (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 0.8),
        (r'\b(\d{1,2})\s*(am|pm)\b', 0.7),
        (r'\b(morning|afternoon|evening)\b', 0.6),
    ]
    
    # Check for confirmation
    for pattern, confidence in confirmation_patterns:
        if re.search(pattern, text_lower):
            return "confirmation", confidence
    
    # Check for rejection
    for pattern, confidence in rejection_patterns:
        if re.search(pattern, text_lower):
            return "rejection", confidence
    
    # Check for time mention
    for pattern, confidence in time_patterns:
        if re.search(pattern, text_lower):
            return "time_mention", confidence
    
    # Default: unclear intent
    return "unclear", 0.3


def fetch_candidate_by_id(candidate_id: str) -> Optional[dict]:
    """Fetch candidate document from MongoDB by _id or by id string field.

    Returns normalized dict or None.
    """
    try:
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning("pymongo not installed; cannot fetch candidate by id")
            return None

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            logger.debug("MONGODB_URI not configured; cannot fetch candidate by id")
            return None

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")
        db = client[db_name]
        coll = db[coll_name]

        # try ObjectId first
        try:
            from bson import ObjectId
            query = {"_id": ObjectId(candidate_id)}
            doc = coll.find_one(query)
        except Exception:
            # fallback to searching by id or email field
            doc = coll.find_one({"id": candidate_id}) or coll.find_one({"email": candidate_id})

        if not doc:
            return None

        return {
            "name": doc.get("name") or doc.get("full_name") or doc.get("candidate_name"),
            "phone": doc.get("phone") or doc.get("phone_number"),
            "email": doc.get("email"),
            "position": doc.get("position") or doc.get("role"),
            "company": doc.get("company") or doc.get("employer"),
            "raw": doc,
        }
    except Exception as e:
        logger.warning(f"Error fetching candidate by id: {e}")
        return None

def find_mentioned_time_slot(text: str, available_slots: List[str]) -> Optional[str]:
    """Find if any time slot is mentioned in the text"""
    text_lower = text.lower()
    for slot in available_slots:
        slot_words = slot.lower().split()
        if any(word in text_lower for word in slot_words):
            return slot
    return None

def get_ai_greeting(candidate: Optional[dict] = None) -> str:
    """Get AI greeting message. Use provided candidate dict or fall back to global CANDIDATE."""
    c = candidate or CANDIDATE
    name = c.get('name') if isinstance(c, dict) else 'Candidate'
    company = c.get('company') if isinstance(c, dict) else 'Company'
    position = c.get('position') if isinstance(c, dict) else 'position'
    return f"Hello {name}! I'm calling from {company} regarding your {position} interview. Are you available to discuss timing?"

def generate_ai_response(session: ConversationSession, user_input: str, intent: str, confidence: float) -> str:
    """Generate appropriate AI response based on conversation context and intent"""
    turn_count = len(session.turns)
    
    try:
        if openai_client:
            # Prepare conversation context
            context_messages = []
            context_messages.append({
                "role": "system", 
                "content": f"""You are a professional recruiter scheduling an interview for {CANDIDATE['name']} for a {CANDIDATE['position']} position at {CANDIDATE['company']}. 

Available time slots: {', '.join(TIME_SLOTS)}

Conversation context:
- Turn count: {turn_count + 1}
- Detected intent: {intent} (confidence: {confidence:.2f})
- Current status: {session.status}

Guidelines:
1. Be professional but friendly
2. Keep responses under 25 words
3. Guide towards slot confirmation
4. If intent is unclear after 2 turns, list available slots clearly
5. If rejection detected, offer alternatives
6. Confirm and end call when confirmation detected"""
            })
            
            # Add conversation history for context
            for turn in session.turns[-3:]:  # Last 3 turns for context
                context_messages.append({"role": "assistant", "content": turn.ai_response})
                context_messages.append({"role": "user", "content": turn.candidate_input})
            
            # Add current user input
            context_messages.append({"role": "user", "content": user_input})
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=context_messages,
                max_tokens=60,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        else:
            # Fallback responses when OpenAI is not available
            if intent == "confirmation":
                return f"Perfect! Let me confirm your interview for {TIME_SLOTS[0]}. Is that correct?"
            elif intent == "rejection":
                return f"I understand. We have these other slots: {', '.join(TIME_SLOTS[1:])}. Any of these work?"
            elif turn_count >= 2:
                return f"Let me be clear. Available slots: {', '.join(TIME_SLOTS)}. Please say 'confirm' and your preferred time."
            else:
                return f"Great! Are you available for an interview on {TIME_SLOTS[0]}? Please say 'confirm' if yes."
                
    except Exception as e:
        logger.error(f"AI response generation failed: {e}")
        return f"Thank you. Are you available for an interview on {TIME_SLOTS[0]}? Please say 'confirm' if yes."

@app.post("/twilio-voice")
async def twilio_voice(request: Request):
    """Entry point for Twilio call with validation"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "unknown")
        from_number = form_data.get("From", CANDIDATE["phone"])
        call_status = form_data.get("CallStatus", "unknown")
        
        logger.info(f"New call started - CallSid: {call_sid}, From: {from_number}, Status: {call_status}")
        
        # Validate that this is a legitimate Twilio call
        if call_sid == "unknown":
            logger.warning("Received call without valid CallSid")
            return Response(
                content="<Response><Say>Invalid call request.</Say><Hangup/></Response>",
                media_type="application/xml"
            )
        
        # Create new conversation session (if not created by outgoing call)
        session = conversation_sessions.get(call_sid)
        if not session:
            session = get_or_create_session(call_sid, from_number)
        # Use session-specific candidate if available
        greeting = get_ai_greeting(session.candidate if session and session.candidate else None)
        
        logger.info(f"Starting conversation with greeting: {greeting}")
        
        response_xml = f"""
        <Response>
            <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10" speechTimeout="3" language="en-US">
                <Say voice="alice" language="en-US">{greeting}</Say>
            </Gather>
            <Say voice="alice" language="en-US">I'm sorry, I didn't hear anything. We'll follow up by email. Goodbye.</Say>
            <Hangup/>
        </Response>
        """
        
        return Response(content=response_xml.strip(), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error in twilio_voice endpoint: {e}")
        return Response(
            content="<Response><Say>Sorry, there was a system error. Goodbye.</Say><Hangup/></Response>",
            media_type="application/xml"
        )

@app.post("/twilio-process")
async def process_speech(request: Request):
    """Process candidate response with improved conversation management and validation"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "unknown")
        speech_result = form_data.get("SpeechResult", "").strip()
        confidence = form_data.get("Confidence", "0")
        
        logger.info(f"Processing speech - CallSid: {call_sid}, Input: '{speech_result}', Confidence: {confidence}")
        
        # Validate input
        if call_sid == "unknown":
            logger.error("Received speech processing request without valid CallSid")
            return Response(
                content="<Response><Say>System error. Goodbye.</Say><Hangup/></Response>",
                media_type="application/xml"
            )
        
        # Handle empty or unclear speech
        if not speech_result or len(speech_result.strip()) < 2:
            logger.warning(f"Empty or very short speech result: '{speech_result}'")
            response_xml = f"""
            <Response>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10" speechTimeout="3">
                    <Say voice="alice" language="en-US">I'm sorry, I didn't catch that. Could you please repeat your response?</Say>
                </Gather>
                <Say voice="alice" language="en-US">Thank you. We'll follow up by email.</Say>
                <Hangup/>
            </Response>
            """
            return Response(content=response_xml.strip(), media_type="application/xml")
        
        # Get or create session
        session = conversation_sessions.get(call_sid)
        if not session:
            logger.warning(f"Session not found for CallSid: {call_sid}, creating new session")
            session = get_or_create_session(call_sid, CANDIDATE["phone"])
        
        # Analyze user intent
        intent, intent_confidence = analyze_intent(speech_result)
        turn_number = len(session.turns) + 1
        
        logger.info(f"Turn #{turn_number} - Intent: {intent} (confidence: {intent_confidence:.2f})")
        
        # Prevent infinite loops - max 6 turns
        if turn_number > 6:
            ai_response = "Thank you for your time. Due to call length limits, we'll follow up by email with scheduling options. Goodbye."
            session.status = "failed"
            session.end_time = datetime.now().isoformat()
            
            turn = ConversationTurn(
                turn_number=turn_number,
                candidate_input=speech_result,
                ai_response=ai_response,
                timestamp=datetime.now().isoformat(),
                intent_detected=intent,
                confidence_score=intent_confidence
            )
            session.turns.append(turn)
            save_conversation_session(session)
            
            return Response(
                content=f"<Response><Say voice='alice' language='en-US'>{ai_response}</Say><Hangup/></Response>",
                media_type="application/xml"
            )
        
        # Handle confirmation intent
        if intent == "confirmation" and intent_confidence > 0.6:
            # Find mentioned time slot or use first available
            mentioned_slot = find_mentioned_time_slot(speech_result, TIME_SLOTS)
            confirmed_slot = mentioned_slot or TIME_SLOTS[0]
            
            session.confirmed_slot = confirmed_slot
            session.status = "completed"
            session.end_time = datetime.now().isoformat()
            
            ai_response = f"Perfect! Your interview is confirmed for {confirmed_slot}. We'll send you a calendar invite. Thank you!"
            
            # Record final turn
            turn = ConversationTurn(
                turn_number=turn_number,
                candidate_input=speech_result,
                ai_response=ai_response,
                timestamp=datetime.now().isoformat(),
                intent_detected=intent,
                confidence_score=intent_confidence
            )
            session.turns.append(turn)
            save_conversation_session(session)
            
            logger.info(f"CONFIRMATION DETECTED! Confirmed slot: {confirmed_slot} - Call completed in {turn_number} turns")
            
            response_xml = f"""
            <Response>
                <Say voice="alice" language="en-US">{ai_response}</Say>
                <Hangup/>
            </Response>
            """
            return Response(content=response_xml.strip(), media_type="application/xml")
    
        # Handle rejection or request for different time
        elif intent == "rejection":
            if turn_number >= 3:
                ai_response = "I understand. We'll follow up by email with alternative options. Thank you for your time."
                session.status = "failed"
                session.end_time = datetime.now().isoformat()
            else:
                ai_response = f"I understand. We have these other slots: {', '.join(TIME_SLOTS[1:])}. Any of these work for you?"
        
        # Too many unclear interactions - provide guidance
        elif turn_number >= 4:
            ai_response = f"Let me be clear about our available times: {', '.join(TIME_SLOTS)}. Please say 'confirm' followed by your preferred time."
            
            if turn_number >= 5:
                ai_response = "Thank you for your time. We'll follow up by email with scheduling options. Goodbye."
                session.status = "failed"
                session.end_time = datetime.now().isoformat()
                
                turn = ConversationTurn(
                    turn_number=turn_number,
                    candidate_input=speech_result,
                    ai_response=ai_response,
                    timestamp=datetime.now().isoformat(),
                    intent_detected=intent,
                    confidence_score=intent_confidence
                )
                session.turns.append(turn)
                save_conversation_session(session)
                
                response_xml = f"""
                <Response>
                    <Say voice="alice" language="en-US">{ai_response}</Say>
                    <Hangup/>
                </Response>
                """
                return Response(content=response_xml.strip(), media_type="application/xml")
        
        # Generate contextual AI response
        else:
            ai_response = generate_ai_response(session, speech_result, intent, intent_confidence)
    
        # Record conversation turn
        turn = ConversationTurn(
            turn_number=turn_number,
            candidate_input=speech_result,
            ai_response=ai_response,
            timestamp=datetime.now().isoformat(),
            intent_detected=intent,
            confidence_score=intent_confidence
        )
        session.turns.append(turn)
        save_conversation_session(session)
        
        logger.info(f"AI response: '{ai_response}'")
        
        # Determine if call should end
        if session.status in ["completed", "failed"]:
            response_xml = f"""
            <Response>
                <Say voice="alice" language="en-US">{ai_response}</Say>
                <Hangup/>
            </Response>
            """
        else:
            response_xml = f"""
            <Response>
                <Say voice="alice" language="en-US">{ai_response}</Say>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10" speechTimeout="3">
                    <Say voice="alice" language="en-US">Please let me know which time works for you.</Say>
                </Gather>
                <Say voice="alice" language="en-US">Thank you. We'll send you an email with the details.</Say>
            </Response>
            """
        
        return Response(content=response_xml.strip(), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in process_speech endpoint: {e}")
        return Response(
            content="<Response><Say voice='alice' language='en-US'>Sorry, there was a system error. We'll follow up by email. Goodbye.</Say><Hangup/></Response>",
            media_type="application/xml"
        )

@app.post("/make-actual-call")
async def make_actual_call(request: Request):
    """Make actual Twilio call with comprehensive validation"""
    # read optional candidate_id from JSON body
    try:
        body = await request.json()
    except Exception:
        body = {}
    candidate_id = body.get("candidate_id") if isinstance(body, dict) else None

    # Validate Twilio credentials
    missing_creds = []
    if not TWILIO_ACCOUNT_SID:
        missing_creds.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing_creds.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_PHONE_NUMBER:
        missing_creds.append("TWILIO_PHONE_NUMBER")
    
    if missing_creds:
        return {
            "status": "error", 
            "message": f"Missing Twilio credentials: {', '.join(missing_creds)}. Check your .env file."
        }
    
    # Resolve candidate details (prefer candidate_id -> mongo -> env CANDIDATE)
    candidate_info = None
    if candidate_id:
        candidate_info = fetch_candidate_by_id(candidate_id)

    if not candidate_info:
        # fall back to the global CANDIDATE loaded at startup
        candidate_info = CANDIDATE

    if not candidate_info or not candidate_info.get("phone") or candidate_info.get("phone") == "+1234567890":
        return {
            "status": "error",
            "message": "Please provide a valid candidate_id or configure candidate phone number in env"
        }
    
    webhook_url = f"{WEBHOOK_BASE_URL}/twilio-voice"
    
    # Check if webhook URL is publicly accessible
    if "localhost" in WEBHOOK_BASE_URL or "127.0.0.1" in WEBHOOK_BASE_URL:
        return {
            "status": "error", 
            "message": "Webhook URL must be public. Start ngrok with: ngrok http 8000",
            "suggestion": "Run 'ngrok http 8000' in a separate terminal to create a public tunnel"
        }
    
    # Validate phone number format
    if not candidate_info.get("phone", "").startswith("+"):
        return {
            "status": "error",
            "message": "Phone number must include country code (e.g., +1234567890)"
        }
    
    try:
        logger.info(f"Initiating call to {CANDIDATE['phone']}")
        logger.info(f"Using webhook: {webhook_url}")
        logger.info(f"Using candidate: {candidate_info.get('email') or candidate_info.get('name')}")
        
        # Test Twilio client initialization
        try:
            client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            # Test credentials by fetching account info (this will fail if credentials are invalid)
            account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
            logger.info(f"Twilio account validated: {account.friendly_name}")
        except Exception as cred_error:
            logger.error(f"Twilio credential validation failed: {cred_error}")
            return {
                "status": "error",
                "message": f"Invalid Twilio credentials: {str(cred_error)}"
            }
        
        # Create the call
        call = client.calls.create(
            url=webhook_url,
            to=candidate_info.get("phone"),
            from_=TWILIO_PHONE_NUMBER,
            timeout=30,  # Give more time for answer
            record=False,  # Don't record by default
        )

        logger.info(f"Call initiated successfully - Call ID: {call.sid}")
        logger.info(f"Initial call status: {call.status}")

        # Check call status after a moment
        import time
        time.sleep(2)
        updated_call = client.calls(call.sid).fetch()
        logger.info(f"Updated call status: {updated_call.status}")
        
        if updated_call.status == 'failed':
            logger.error(f"Call failed. Error code: {updated_call.error_code}")
            logger.error(f"Error message: {updated_call.error_message}")
            return {
                "status": "error",
                "message": f"Call failed: {updated_call.error_message}",
                "error_code": updated_call.error_code,
                "call_sid": call.sid
            }
        
        # create or update in-memory session and persist
        session = get_or_create_session(call.sid, candidate_info.get("phone"), candidate=candidate_info)
        session.candidate = candidate_info
        save_conversation_session(session)

        return {
            "status": "success",
            "message": f"Call initiated to {candidate_info.get('phone')}",
            "call_sid": call.sid,
            "call_status": updated_call.status,
            "webhook_url": webhook_url,
            "candidate": candidate_info.get("name"),
            "initial_status": call.status
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Call failed: {error_msg}")
        
        # Provide specific error guidance
        if "not a valid phone number" in error_msg.lower():
            return {
                "status": "error",
                "message": f"Invalid phone number format: {CANDIDATE['phone']}. Use format: +1234567890"
            }
        elif "twilio" in error_msg.lower() and "credentials" in error_msg.lower():
            return {
                "status": "error",
                "message": "Twilio authentication failed. Check your TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN"
            }
        elif "balance" in error_msg.lower():
            return {
                "status": "error",
                "message": "Insufficient Twilio account balance. Please add funds to your Twilio account."
            }
        else:
            return {
                "status": "error", 
                "message": f"Call failed: {error_msg}",
                "suggestion": "Check your Twilio console for more details"
            }

@app.get("/")
async def root():
    """Root endpoint with system status"""
    return {
        "message": "AI Interview Caller",
        "version": "2.0.0",
        "candidate": CANDIDATE,
        "available_slots": TIME_SLOTS,
        "active_conversations": len([s for s in conversation_sessions.values() if s.status == "active"]),
        "config": {
            "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER),
            "openai_configured": bool(OPENAI_API_KEY),
            "webhook_url": WEBHOOK_BASE_URL,
            "database_enabled": True,
        },
    }

@app.get("/conversations")
async def get_conversations():
    """Get all conversation sessions"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM conversation_sessions ORDER BY start_time DESC')
        sessions = cursor.fetchall()
        
        result = []
        for session in sessions:
            session_dict = {
                "call_sid": session[0],
                "candidate_phone": session[1],
                "start_time": session[2],
                "end_time": session[3],
                "status": session[4],
                "confirmed_slot": session[5],
                "turns": json.loads(session[6]) if session[6] else []
            }
            result.append(session_dict)
        
        conn.close()
        return {"conversations": result}
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return {"error": str(e), "conversations": []}

@app.get("/conversations/{call_sid}")
async def get_conversation(call_sid: str):
    """Get specific conversation details"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM conversation_sessions WHERE call_sid = ?', (call_sid,))
        session = cursor.fetchone()
        
        if not session:
            return {"error": "Conversation not found"}
        
        result = {
            "call_sid": session[0],
            "candidate_phone": session[1],
            "start_time": session[2],
            "end_time": session[3],
            "status": session[4],
            "confirmed_slot": session[5],
            "turns": json.loads(session[6]) if session[6] else []
        }
        
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error fetching conversation {call_sid}: {e}")
        return {"error": str(e)}

@app.get("/analytics")
async def get_analytics():
    """Get conversation analytics"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Basic stats
        cursor.execute('SELECT COUNT(*) FROM conversation_sessions')
        total_calls = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM conversation_sessions WHERE status = "completed"')
        successful_calls = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM conversation_sessions WHERE status = "failed"')
        failed_calls = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM conversation_sessions WHERE status = "active"')
        active_calls = cursor.fetchone()[0]
        
        # Average turns per call
        cursor.execute('SELECT AVG(json_array_length(turns_json)) FROM conversation_sessions WHERE turns_json IS NOT NULL')
        avg_turns = cursor.fetchone()[0] or 0
        
        # Most confirmed slots
        cursor.execute('SELECT confirmed_slot, COUNT(*) as count FROM conversation_sessions WHERE confirmed_slot IS NOT NULL GROUP BY confirmed_slot ORDER BY count DESC')
        slot_preferences = cursor.fetchall()
        
        conn.close()
        
        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "active_calls": active_calls,
            "success_rate": round((successful_calls / total_calls * 100) if total_calls > 0 else 0, 2),
            "average_turns_per_call": round(avg_turns, 2),
            "slot_preferences": [{"slot": slot[0], "count": slot[1]} for slot in slot_preferences]
        }
    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        return {"error": str(e)}

@app.get("/call-status/{call_sid}")
async def get_call_status(call_sid: str):
    """Get current status of a Twilio call"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN]):
        return {"error": "Twilio credentials not configured"}
    
    try:
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call = client.calls(call_sid).fetch()
        
        return {
            "call_sid": call.sid,
            "status": call.status,
            "direction": call.direction,
            "from": call.from_,
            "to": call.to,
            "duration": call.duration,
            "price": call.price,
            "error_code": call.error_code,
            "error_message": call.error_message,
            "start_time": str(call.start_time) if call.start_time else None,
            "end_time": str(call.end_time) if call.end_time else None
        }
    except Exception as e:
        logger.error(f"Error fetching call status for {call_sid}: {e}")
        return {"error": str(e)}

@app.delete("/conversations/{call_sid}")
async def delete_conversation(call_sid: str):
    """Delete a conversation session"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM conversation_sessions WHERE call_sid = ?', (call_sid,))
        cursor.execute('DELETE FROM conversation_turns WHERE call_sid = ?', (call_sid,))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            # Also remove from memory
            if call_sid in conversation_sessions:
                del conversation_sessions[call_sid]
            return {"message": "Conversation deleted successfully"}
        else:
            conn.close()
            return {"error": "Conversation not found"}
    except Exception as e:
        logger.error(f"Error deleting conversation {call_sid}: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    print("AI Interview Caller - Ready to receive calls")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)