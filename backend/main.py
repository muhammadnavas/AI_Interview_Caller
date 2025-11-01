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
import html
import xml.etree.ElementTree as ET

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
    # First check environment variable (for production deployment)
    webhook_url = config("WEBHOOK_BASE_URL", default=None)
    if webhook_url:
        print(f"Using configured WEBHOOK_BASE_URL: {webhook_url}")
        return webhook_url.rstrip('/')
    
    # Then try to detect ngrok for local development
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
                        return public_url.rstrip('/')
    except:
        pass
    
    # Fallback to localhost (will cause issues in production)
    fallback_url = "http://localhost:8000"
    print(f"WARNING: Using fallback URL: {fallback_url} - This won't work in production!")
    return fallback_url

WEBHOOK_BASE_URL = get_webhook_url().rstrip('/')

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


def get_all_candidates_from_mongo() -> list:
    """Get all candidates from MongoDB for selection."""
    try:
        from pymongo import MongoClient
        
        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return []

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")

        db = client[db_name]
        coll = db[coll_name]

        docs = list(coll.find())
        candidates = []
        
        for doc in docs:
            candidate = {
                "id": str(doc.get("_id")),
                "name": doc.get("name") or doc.get("full_name") or doc.get("candidate_name"),
                "phone": doc.get("phone") or doc.get("phone_number"),
                "email": doc.get("email"),
                "position": doc.get("position") or doc.get("role"),
                "company": doc.get("company") or doc.get("employer"),
            }
            # Only add candidates with valid phone numbers
            if candidate["phone"] and candidate["phone"].startswith("+"):
                candidates.append(candidate)
        
        return candidates
        
    except Exception as e:
        logger.warning(f"Could not load candidates from MongoDB: {e}")
        return []


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

def load_session_from_db(call_sid: str) -> Optional[ConversationSession]:
    """Load conversation session from database"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM conversation_sessions WHERE call_sid = ?', (call_sid,))
        session_data = cursor.fetchone()
        
        if not session_data:
            conn.close()
            return None
        
        # Reconstruct session from DB
        turns = []
        if session_data[6]:  # turns_json
            turns_data = json.loads(session_data[6])
            for turn_dict in turns_data:
                turns.append(ConversationTurn(**turn_dict))
        
        session = ConversationSession(
            call_sid=session_data[0],
            candidate_phone=session_data[1],
            start_time=session_data[2],
            end_time=session_data[3],
            status=session_data[4],
            confirmed_slot=session_data[5],
            turns=turns
        )
        
        # Try to load candidate from DB if available
        # For now, we'll set candidate to None and let it be loaded later if needed
        session.candidate = None
        
        conn.close()
        return session
    except Exception as e:
        logger.error(f"Error loading session from DB: {e}")
        return None

def get_or_create_session(call_sid: str, candidate_phone: str, candidate: Optional[dict] = None) -> ConversationSession:
    """Get existing session or create new one, loading from DB if needed"""
    if call_sid in conversation_sessions:
        return conversation_sessions[call_sid]
    
    # Try to load from DB first
    session = load_session_from_db(call_sid)
    if session:
        conversation_sessions[call_sid] = session
        # Update candidate if provided and not set
        if candidate and not session.candidate:
            session.candidate = candidate
            save_conversation_session(session)
        return session
    
    # Create new session
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
            # fallback to searching by id, email, or phone
            doc = coll.find_one({"id": candidate_id}) or coll.find_one({"email": candidate_id}) or coll.find_one({"phone": candidate_id}) or coll.find_one({"phone_number": candidate_id})

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
    """Get professional AI greeting message."""
    c = candidate or CANDIDATE
    name = c.get('name', 'there') if isinstance(c, dict) else 'there'
    position = c.get('position', 'the position') if isinstance(c, dict) else 'the position'
    company = c.get('company', 'our company') if isinstance(c, dict) else 'our company'
    
    # First name only for more natural conversation
    first_name = name.split()[0] if name and name != 'there' else name
    
    greeting = f"Hello {first_name}! This is Sarah from {company}'s talent acquisition team. I'm calling regarding your application for the {position} position. I hope I'm catching you at a good time for a quick interview scheduling call."
    return greeting

def generate_ai_response(session: ConversationSession, user_input: str, intent: str, confidence: float) -> str:
    """Generate appropriate AI response based on conversation context and intent"""
    turn_count = len(session.turns)
    candidate = session.candidate or CANDIDATE
    
    try:
        if openai_client:
            # Prepare conversation context
            context_messages = []
            context_messages.append({
                "role": "system", 
                "content": f"""You are Sarah, a professional talent acquisition specialist from {candidate.get('company', 'the company')} scheduling an interview with {candidate.get('name', 'the candidate')} for a {candidate.get('position', 'Software Engineer')} position.

Available interview time slots: {', '.join(TIME_SLOTS)}

Conversation context:
- Turn count: {turn_count + 1}
- Detected intent: {intent} (confidence: {confidence:.2f})
- Current status: {session.status}

Professional Guidelines:
1. Maintain a warm, professional tone
2. Keep responses concise (20-30 words max)
3. Use "we" and "our team" language
4. Guide naturally toward time slot selection
5. Show enthusiasm about their candidacy
6. Be flexible and accommodating
7. Always end positively

Response patterns:
- Confirmation: Express excitement, confirm details, mention next steps
- Rejection: Show understanding, offer alternatives professionally  
- Unclear: Gently clarify without being repetitive
- Time mention: Acknowledge their preference and work with it"""
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
            # Professional fallback responses when OpenAI is not available
            candidate_name = candidate.get('name', '').split()[0] if candidate.get('name') else ''
            
            if intent == "confirmation":
                return f"Excellent, {candidate_name}! I'll send you a calendar invite for {TIME_SLOTS[0]}. Our team is excited to meet you!"
            elif intent == "rejection":
                return f"No problem at all, {candidate_name}. We have these alternatives: {', '.join(TIME_SLOTS[1:])}. Would any of these work better for you?"
            elif turn_count >= 2:
                return f"Let me share our available interview slots: {', '.join(TIME_SLOTS)}. Which time works best for your schedule?"
            else:
                return f"Wonderful! Would {TIME_SLOTS[0]} work for your interview? We're very excited about your application."
                
    except Exception as e:
        logger.error(f"AI response generation failed: {e}")
        candidate_name = candidate.get('name', '').split()[0] if candidate.get('name') else ''
        return f"Thank you, {candidate_name}. Would {TIME_SLOTS[0]} work for your interview? Please let me know if that suits your schedule."

@app.get("/test-webhook") 
async def test_webhook():
    """Test endpoint to verify app is working"""
    return {"status": "OK", "message": "Webhook endpoint is accessible", "webhook_url": f"{WEBHOOK_BASE_URL}/twilio-voice"}

@app.get("/twilio-voice")
async def twilio_voice_get():
    """GET endpoint for webhook verification"""
    return {"message": "Twilio webhook endpoint is ready", "method": "POST required for actual calls"}

@app.post("/twilio-voice")
async def twilio_voice(request: Request):
    """AI Interview Scheduler - Main webhook for incoming calls"""
    try:
        # Parse Twilio webhook data
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "unknown")
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")
        call_status = form_data.get("CallStatus", "")
        
        logger.info(f"Incoming call - CallSid: {call_sid}, From: {from_number}, To: {to_number}, Status: {call_status}")
        
        # Create or get session for this call
        session = get_or_create_session(call_sid, from_number)
        
        # Get appropriate greeting based on candidate data
        greeting = get_ai_greeting(session.candidate)
        
        # Log initial turn
        initial_turn = ConversationTurn(
            turn_number=1,
            candidate_input=f"[CALL INITIATED] From: {from_number}",
            ai_response=greeting,
            timestamp=datetime.now().isoformat(),
            intent_detected="call_start",
            confidence_score=1.0
        )
        session.turns.append(initial_turn)
        save_conversation_session(session)
        
        # Generate TwiML with conversation flow
        twiml = f"""<Response>
            <Say voice="alice">{html.escape(greeting)}</Say>
            <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10" speechTimeout="auto">
                <Say voice="alice">Please let me know if any of these times work for you: Monday at 10 AM, Tuesday at 2 PM, Wednesday at 11 AM, or Thursday at 3 PM.</Say>
            </Gather>
            <Say voice="alice">Thank you. We'll follow up by email with the details.</Say>
            <Hangup/>
        </Response>"""
        
        logger.info(f"Generated initial TwiML for call {call_sid}")
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.error(f"Error in twilio_voice webhook: {e}")
        # Return basic TwiML even on error
        error_twiml = """<Response>
            <Say voice="alice">Hello! This is AI Interview Scheduler. We're experiencing technical difficulties. We'll follow up by email. Goodbye!</Say>
            <Hangup/>
        </Response>"""
        return Response(content=error_twiml, media_type="text/xml")

@app.post("/twilio-process")
async def process_speech(request: Request):
    """Process candidate speech response with full conversation tracking"""
    try:
        # Parse Twilio webhook data
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "unknown")
        speech_result = form_data.get("SpeechResult", "").strip()
        confidence = float(form_data.get("Confidence", "0.0"))
        
        logger.info(f"Speech received - CallSid: {call_sid}, Speech: '{speech_result}', Confidence: {confidence}")
        
        # Handle empty or low confidence speech
        if not speech_result or len(speech_result) < 3 or confidence < 0.3:
            logger.warning(f"Empty or low confidence speech: '{speech_result}' (confidence: {confidence})")
            
            # Generate retry TwiML
            retry_twiml = f"""<Response>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10" speechTimeout="auto">
                    <Say voice="alice">I'm sorry, I didn't catch that clearly. Could you please repeat which time works for you? Monday at 10 AM, Tuesday at 2 PM, Wednesday at 11 AM, or Thursday at 3 PM?</Say>
                </Gather>
                <Say voice="alice">Thank you. We'll follow up by email with the details.</Say>
                <Hangup/>
            </Response>"""
            return Response(content=retry_twiml, media_type="text/xml")
        
        # Get or create session
        session = conversation_sessions.get(call_sid)
        if not session:
            logger.warning(f"Session not found for CallSid: {call_sid}, creating new session")
            session = get_or_create_session(call_sid, form_data.get("From", ""))
        
        # Analyze user intent
        intent, intent_confidence = analyze_intent(speech_result)
        turn_number = len(session.turns) + 1
        
        logger.info(f"Turn #{turn_number} - Intent: {intent} (confidence: {intent_confidence:.2f})")
        
        # Prevent infinite loops - max 6 turns
        if turn_number > 6:
            ai_response = "Thank you for your time. Due to call length limits, we'll follow up by email with scheduling options. Goodbye."
            session.status = "failed"
            session.end_time = datetime.now().isoformat()
            
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
            
            return Response(
                content=f"<Response><Say voice='alice'>{html.escape(ai_response)}</Say><Hangup/></Response>",
                media_type="text/xml"
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
            
            confirmation_twiml = f"<Response><Say voice='alice'>{html.escape(ai_response)}</Say><Hangup/></Response>"
            return Response(content=confirmation_twiml, media_type="text/xml")
        
        # Handle rejection or request for different time
        elif intent == "rejection":
            if turn_number >= 3:
                ai_response = "I understand. We'll follow up by email with alternative options. Thank you for your time."
                session.status = "failed"
                session.end_time = datetime.now().isoformat()
            else:
                ai_response = f"I understand. We have these other slots available: {', '.join(TIME_SLOTS[1:])}. Would any of these work for you?"
        
        # Too many unclear interactions - provide guidance
        elif turn_number >= 4:
            ai_response = f"Let me be clear about our available times: {', '.join(TIME_SLOTS)}. Please say 'yes' or 'confirm' followed by your preferred time."
            
            if turn_number >= 5:
                ai_response = "Thank you for your time. We'll follow up by email with scheduling options. Goodbye."
                session.status = "failed"
                session.end_time = datetime.now().isoformat()
        
        # Generate contextual AI response for other cases
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
        
        # Generate appropriate TwiML response
        if session.status in ["completed", "failed"]:
            # Call should end
            final_twiml = f"<Response><Say voice='alice'>{html.escape(ai_response)}</Say><Hangup/></Response>"
            return Response(content=final_twiml, media_type="text/xml")
        else:
            # Continue conversation
            continue_twiml = f"""<Response>
                <Say voice="alice">{html.escape(ai_response)}</Say>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="10" speechTimeout="auto">
                    <Say voice="alice">Please let me know which time works best for you.</Say>
                </Gather>
                <Say voice="alice">Thank you. We'll send you an email with the details.</Say>
                <Hangup/>
            </Response>"""
            return Response(content=continue_twiml, media_type="text/xml")
        
    except Exception as e:
        logger.error(f"Error in process_speech endpoint: {e}")
        error_twiml = """<Response>
            <Say voice='alice'>Sorry, there was a system error. We'll follow up by email. Goodbye.</Say>
            <Hangup/>
        </Response>"""
        return Response(content=error_twiml, media_type="text/xml")

# This section was corrupted and has been removed

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

@app.get("/candidates")
async def get_candidates():
    """Get all candidates from MongoDB"""
    try:
        candidates = get_all_candidates_from_mongo()
        
        return {
            "candidates": candidates,
            "total": len(candidates),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error fetching candidates: {e}")
        return {
            "error": str(e),
            "candidates": [],
            "total": 0,
            "status": "error"
        }

@app.post("/call-candidate")
async def call_specific_candidate(request: Request):
    """Make a professional call to a specific candidate by ID"""
    try:
        # Get candidate ID from request body
        body = await request.json()
        candidate_id = body.get("candidate_id")
        
        if not candidate_id:
            return {
                "status": "error",
                "message": "candidate_id is required"
            }
        
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
        
        # Load candidate from MongoDB
        candidate_info = fetch_candidate_by_id(candidate_id)
        if not candidate_info:
            return {
                "status": "error",
                "message": f"Candidate not found with ID: {candidate_id}"
            }
        
        if not candidate_info.get("phone") or not candidate_info.get("phone").startswith("+"):
            return {
                "status": "error",
                "message": f"Invalid phone number for candidate: {candidate_info.get('phone')}"
            }
        
        webhook_url = f"{WEBHOOK_BASE_URL}/twilio-voice"
        
        # Check if webhook URL is publicly accessible
        if "localhost" in WEBHOOK_BASE_URL or "127.0.0.1" in WEBHOOK_BASE_URL:
            return {
                "status": "error", 
                "message": "Webhook URL must be public. Start ngrok with: ngrok http 8000",
                "suggestion": "Run 'ngrok http 8000' in a separate terminal to create a public tunnel"
            }
        
        logger.info(f"Initiating professional interview call to {candidate_info['name']} ({candidate_info['phone']})")
        logger.info(f"Position: {candidate_info.get('position')} at {candidate_info.get('company')}")
        logger.info(f"Using webhook: {webhook_url}")
        
        # Initialize Twilio client
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Test credentials
        try:
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
            timeout=30,
            record=False,
        )

        logger.info(f"Professional call initiated - Call ID: {call.sid}")
        
        # Check initial call status
        import time
        time.sleep(2)
        updated_call = client.calls(call.sid).fetch()
        
        if updated_call.status == 'failed':
            logger.error(f"Call failed. Error: {updated_call.error_message}")
            return {
                "status": "error",
                "message": f"Call failed: {updated_call.error_message}",
                "error_code": updated_call.error_code,
                "call_sid": call.sid
            }
        
        # Pre-create session with candidate info
        session = get_or_create_session(call.sid, candidate_info.get("phone"), candidate=candidate_info)

        return {
            "status": "success",
            "message": f"Professional interview call initiated to {candidate_info.get('name')}",
            "call_sid": call.sid,
            "call_status": updated_call.status,
            "candidate": {
                "name": candidate_info.get("name"),
                "phone": candidate_info.get("phone"),
                "email": candidate_info.get("email"),
                "position": candidate_info.get("position"),
                "company": candidate_info.get("company")
            },
            "webhook_url": webhook_url,
            "initial_status": call.status
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Professional call failed: {error_msg}")
        
        if "not a valid phone number" in error_msg.lower():
            return {
                "status": "error",
                "message": f"Invalid phone number format. Use format: +1234567890"
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
        "status": "WORKING",
        "webhook_url": WEBHOOK_BASE_URL,
        "twilio_webhook_test": f"{WEBHOOK_BASE_URL}/twilio-voice",
        "config": {
            "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER),
            "openai_configured": bool(OPENAI_API_KEY),
            "database_enabled": True,
        },
    }

@app.get("/recent-conversations")
async def get_recent_conversations(limit: int = 10):
    """Get recent conversations with detailed turn information"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversation_sessions 
            ORDER BY start_time DESC 
            LIMIT ?
        ''', (limit,))
        sessions = cursor.fetchall()
        
        result = []
        for session in sessions:
            turns = json.loads(session[6]) if session[6] else []
            
            # Calculate conversation metrics
            total_turns = len(turns)
            duration = None
            if session[2] and session[3]:  # start_time and end_time
                try:
                    start = datetime.fromisoformat(session[2])
                    end = datetime.fromisoformat(session[3])
                    duration = str(end - start)
                except:
                    pass
            
            # Get last AI response and candidate input
            last_turn = turns[-1] if turns else None
            
            session_summary = {
                "call_sid": session[0],
                "candidate_phone": session[1],
                "start_time": session[2],
                "end_time": session[3],
                "status": session[4],
                "confirmed_slot": session[5],
                "total_turns": total_turns,
                "duration": duration,
                "last_candidate_input": last_turn.get("candidate_input") if last_turn else None,
                "last_ai_response": last_turn.get("ai_response") if last_turn else None,
                "final_intent": last_turn.get("intent_detected") if last_turn else None,
                "conversation_turns": turns
            }
            result.append(session_summary)
        
        conn.close()
        return {
            "recent_conversations": result,
            "total_found": len(result)
        }
        
    except Exception as e:
        logger.error(f"Error fetching recent conversations: {e}")
        return {"error": str(e), "recent_conversations": []}

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

@app.get("/live-conversation/{call_sid}")
async def get_live_conversation_status(call_sid: str):
    """Get live conversation status for active calls"""
    try:
        # Check in-memory sessions first (for active calls)
        if call_sid in conversation_sessions:
            session = conversation_sessions[call_sid]
            
            # Get Twilio call status if credentials available
            twilio_status = None
            if all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN]):
                try:
                    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                    call = client.calls(call_sid).fetch()
                    twilio_status = {
                        "status": call.status,
                        "duration": call.duration,
                        "direction": call.direction
                    }
                except:
                    pass
            
            return {
                "call_sid": call_sid,
                "conversation_status": session.status,
                "current_turn": len(session.turns),
                "candidate_phone": session.candidate_phone,
                "start_time": session.start_time,
                "end_time": session.end_time,
                "confirmed_slot": session.confirmed_slot,
                "twilio_status": twilio_status,
                "recent_turns": [asdict(turn) for turn in session.turns[-3:]],  # Last 3 turns
                "candidate_info": session.candidate
            }
        
        # If not in memory, check database
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM conversation_sessions WHERE call_sid = ?', (call_sid,))
        session_data = cursor.fetchone()
        conn.close()
        
        if not session_data:
            return {"error": "Conversation not found", "call_sid": call_sid}
        
        turns = json.loads(session_data[6]) if session_data[6] else []
        
        return {
            "call_sid": call_sid,
            "conversation_status": session_data[4],  # status
            "current_turn": len(turns),
            "candidate_phone": session_data[1],
            "start_time": session_data[2],
            "end_time": session_data[3],
            "confirmed_slot": session_data[5],
            "twilio_status": None,  # Not available for completed calls
            "recent_turns": turns[-3:] if turns else [],  # Last 3 turns
            "candidate_info": None
        }
        
    except Exception as e:
        logger.error(f"Error getting live conversation status for {call_sid}: {e}")
        return {"error": str(e), "call_sid": call_sid}

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