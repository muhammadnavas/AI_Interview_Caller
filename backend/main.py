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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pymongo import MongoClient
from bson import ObjectId

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

# Email Configuration
SMTP_SERVER = config("SMTP_SERVER", default="smtp.gmail.com")
SMTP_PORT = int(config("SMTP_PORT", default="587"))
SMTP_USERNAME = config("SMTP_USERNAME", default="")
SMTP_PASSWORD = config("SMTP_PASSWORD", default="")
SENDER_EMAIL = config("SENDER_EMAIL", default="")

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


def find_candidate_by_phone(phone_number: str) -> Optional[dict]:
    """Find a candidate by phone number in MongoDB"""
    if not phone_number:
        return None
        
    try:
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")

        db = client[db_name]
        coll = db[coll_name]

        # Try different phone number variations
        phone_variations = [
            phone_number,
            phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", ""),
            phone_number if phone_number.startswith("+") else f"+1{phone_number.replace('+', '')}",
            phone_number.replace("+1", "") if phone_number.startswith("+1") else phone_number
        ]

        for phone_var in phone_variations:
            doc = coll.find_one({"$or": [
                {"phone": phone_var},
                {"phone_number": phone_var}
            ]})
            
            if doc:
                candidate = {
                    "id": str(doc.get("_id")),
                    "name": doc.get("name") or doc.get("full_name") or doc.get("candidate_name"),
                    "phone": doc.get("phone") or doc.get("phone_number"),
                    "email": doc.get("email"),
                    "position": doc.get("position") or doc.get("role"),
                    "company": doc.get("company") or doc.get("employer"),
                    "call_tracking": doc.get("call_tracking", {})
                }
                logger.info(f"Found candidate by phone {phone_number}: {candidate.get('name')}")
                return candidate
                
        logger.warning(f"No candidate found for phone number: {phone_number}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding candidate by phone {phone_number}: {e}")
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
    """Initialize comprehensive SQLite database for complete call tracking"""
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    
    # Main candidates table (enhanced)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT,
            position TEXT,
            company TEXT,
            created_at TEXT,
            updated_at TEXT,
            total_attempts INTEGER DEFAULT 0,
            last_contact_date TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    # Call attempts tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS call_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT,
            call_sid TEXT,
            phone_number TEXT,
            initiated_at TEXT,
            twilio_status TEXT,
            call_duration INTEGER,
            call_direction TEXT,
            call_price REAL,
            error_code TEXT,
            error_message TEXT,
            outcome TEXT,
            notes TEXT,
            FOREIGN KEY (candidate_id) REFERENCES candidates (id)
        )
    ''')
    
    # Enhanced conversation sessions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            call_sid TEXT PRIMARY KEY,
            candidate_id TEXT,
            candidate_phone TEXT,
            candidate_name TEXT,
            position TEXT,
            company TEXT,
            start_time TEXT,
            end_time TEXT,
            status TEXT,
            conversation_stage TEXT,
            confirmed_slot TEXT,
            email_sent BOOLEAN DEFAULT 0,
            email_sent_at TEXT,
            total_turns INTEGER DEFAULT 0,
            success_score REAL,
            ai_confidence_avg REAL,
            call_quality TEXT,
            notes TEXT,
            FOREIGN KEY (candidate_id) REFERENCES candidates (id)
        )
    ''')
    
    # Detailed conversation turns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sid TEXT,
            turn_number INTEGER,
            timestamp TEXT,
            candidate_input TEXT,
            ai_response TEXT,
            intent_detected TEXT,
            confidence_score REAL,
            conversation_stage TEXT,
            action_taken TEXT,
            FOREIGN KEY (call_sid) REFERENCES conversation_sessions (call_sid)
        )
    ''')
    
    # Interview schedules tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT,
            call_sid TEXT,
            scheduled_slot TEXT,
            scheduled_at TEXT,
            interview_date TEXT,
            interview_time TEXT,
            status TEXT DEFAULT 'scheduled',
            confirmation_email_sent BOOLEAN DEFAULT 0,
            reminder_sent BOOLEAN DEFAULT 0,
            interview_completed BOOLEAN DEFAULT 0,
            feedback_collected BOOLEAN DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (candidate_id) REFERENCES candidates (id),
            FOREIGN KEY (call_sid) REFERENCES conversation_sessions (call_sid)
        )
    ''')
    
    # Analytics and metrics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS call_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            total_calls INTEGER,
            successful_calls INTEGER,
            failed_calls INTEGER,
            interviews_scheduled INTEGER,
            emails_sent INTEGER,
            avg_call_duration REAL,
            success_rate REAL,
            updated_at TEXT
        )
    ''')
    
    # System logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            log_level TEXT,
            component TEXT,
            action TEXT,
            details TEXT,
            call_sid TEXT,
            candidate_id TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Comprehensive database schema initialized successfully")

def save_call_attempt(candidate_id: str, call_sid: str, phone_number: str, twilio_status: str = None, 
                     call_duration: int = None, error_code: str = None, error_message: str = None, 
                     outcome: str = None, notes: str = None):
    """Save call attempt to database for tracking"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO call_attempts 
            (candidate_id, call_sid, phone_number, initiated_at, twilio_status, call_duration, 
             call_direction, error_code, error_message, outcome, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            candidate_id,
            call_sid,
            phone_number,
            datetime.now().isoformat(),
            twilio_status,
            call_duration,
            'outbound',
            error_code,
            error_message,
            outcome,
            notes
        ))
        
        # Update candidate's total attempts
        cursor.execute('''
            UPDATE candidates 
            SET total_attempts = total_attempts + 1, last_contact_date = ? 
            WHERE id = ?
        ''', (datetime.now().isoformat(), candidate_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved call attempt for candidate {candidate_id}: {call_sid}")
        
    except Exception as e:
        logger.error(f"Error saving call attempt: {e}")

def save_conversation_session(session: ConversationSession):
    """Save enhanced conversation session to database"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Calculate metrics
        total_turns = len(session.turns)
        avg_confidence = sum(turn.confidence_score or 0 for turn in session.turns) / total_turns if total_turns > 0 else 0
        
        candidate = session.candidate or CANDIDATE
        candidate_id = candidate.get('id') if isinstance(candidate, dict) else None
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversation_sessions 
            (call_sid, candidate_id, candidate_phone, candidate_name, position, company,
             start_time, end_time, status, confirmed_slot, total_turns, ai_confidence_avg, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session.call_sid,
            candidate_id,
            session.candidate_phone,
            candidate.get('name') if isinstance(candidate, dict) else 'Unknown',
            candidate.get('position') if isinstance(candidate, dict) else 'Unknown Position',
            candidate.get('company') if isinstance(candidate, dict) else 'Unknown Company',
            session.start_time,
            session.end_time,
            session.status,
            session.confirmed_slot,
            total_turns,
            avg_confidence,
            f"Conversation completed with {total_turns} turns"
        ))
        
        # Save individual turns
        for turn in session.turns:
            cursor.execute('''
                INSERT OR REPLACE INTO conversation_turns 
                (call_sid, turn_number, timestamp, candidate_input, ai_response, 
                 intent_detected, confidence_score, conversation_stage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.call_sid,
                turn.turn_number,
                turn.timestamp,
                turn.candidate_input,
                turn.ai_response,
                turn.intent_detected,
                turn.confidence_score,
                'active'  # This could be enhanced based on conversation state
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved enhanced conversation session: {session.call_sid} with {total_turns} turns")
        
    except Exception as e:
        logger.error(f"Error saving conversation session: {e}")

def save_interview_schedule(candidate_id: str, call_sid: str, confirmed_slot: str, email_sent: bool = False):
    """Save interview schedule to database"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Parse the confirmed slot to extract date and time
        import re
        date_match = re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)', confirmed_slot)
        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM))', confirmed_slot, re.IGNORECASE)
        
        interview_day = date_match.group(1) if date_match else 'TBD'
        interview_time = time_match.group(1) if time_match else 'TBD'
        
        cursor.execute('''
            INSERT INTO interview_schedules 
            (candidate_id, call_sid, scheduled_slot, scheduled_at, interview_date, interview_time, 
             status, confirmation_email_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            candidate_id,
            call_sid,
            confirmed_slot,
            datetime.now().isoformat(),
            interview_day,
            interview_time,
            'scheduled',
            email_sent
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved interview schedule for candidate {candidate_id}: {confirmed_slot}")
        
        # Update candidate status to indicate successful scheduling
        update_candidate_status(candidate_id, "interview_scheduled", 
                              f"Interview scheduled for {confirmed_slot}. Email sent: {email_sent}")
        
    except Exception as e:
        logger.error(f"Error saving interview schedule: {e}")

def log_system_event(level: str, component: str, action: str, details: str, call_sid: str = None, candidate_id: str = None):
    """Log system events for comprehensive tracking"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO system_logs 
            (timestamp, log_level, component, action, details, call_sid, candidate_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            level,
            component,
            action,
            details,
            call_sid,
            candidate_id
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error logging system event: {e}")

def check_call_limit(candidate_id: str, max_attempts: int = 3) -> tuple[bool, int, bool]:
    """
    Check if candidate has reached the maximum call limit
    Returns: (can_call, current_attempts, has_scheduled_interview)
    """
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Count total call attempts for this candidate
        cursor.execute('''
            SELECT COUNT(*) FROM call_attempts 
            WHERE candidate_id = ?
        ''', (candidate_id,))
        
        current_attempts = cursor.fetchone()[0]
        
        # Check if candidate has already scheduled an interview
        cursor.execute('''
            SELECT COUNT(*) FROM interview_schedules 
            WHERE candidate_id = ? AND status = 'scheduled'
        ''', (candidate_id,))
        
        has_scheduled = cursor.fetchone()[0] > 0
        
        conn.close()
        
        # If they've scheduled an interview, they can receive calls (for confirmations, etc.)
        if has_scheduled:
            return True, current_attempts, True
        
        # If they haven't scheduled and reached the limit, no more calls
        can_call = current_attempts < max_attempts
        
        logger.info(f"Call limit check for {candidate_id}: {current_attempts}/{max_attempts} attempts, scheduled: {has_scheduled}, can_call: {can_call}")
        
        return can_call, current_attempts, has_scheduled
        
    except Exception as e:
        logger.error(f"Error checking call limit for candidate {candidate_id}: {e}")
        # On error, allow the call but log it
        return True, 0, False

def update_candidate_status(candidate_id: str, status: str, notes: str = None):
    """Update candidate status in the database"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Check if candidate exists in our local candidates table
        cursor.execute('SELECT id FROM candidates WHERE id = ?', (candidate_id,))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute('''
                UPDATE candidates 
                SET status = ?, updated_at = ?, total_attempts = (
                    SELECT COUNT(*) FROM call_attempts WHERE candidate_id = ?
                )
                WHERE id = ?
            ''', (status, datetime.now().isoformat(), candidate_id, candidate_id))
        else:
            # Insert candidate if not exists (from MongoDB data)
            cursor.execute('''
                INSERT OR IGNORE INTO candidates 
                (id, name, phone, email, position, company, created_at, updated_at, status, total_attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                candidate_id,
                'Unknown',  # These will be updated when we have full candidate data
                'Unknown',
                'Unknown',
                'Unknown',
                'Unknown',
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                status,
                0
            ))
        
        conn.commit()
        conn.close()
        
        if notes:
            log_system_event("INFO", "CANDIDATE_SYSTEM", "STATUS_UPDATE", 
                           f"Status updated to {status}: {notes}", 
                           candidate_id=candidate_id)
        
    except Exception as e:
        logger.error(f"Error updating candidate status: {e}")

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
    """Enhanced intent analysis for natural conversation flow"""
    text_lower = text.lower().strip()
    
    # Strong confirmation patterns
    confirmation_patterns = [
        (r'\b(yes|yeah|yep|yup|absolutely|definitely|sure|of course|sounds good|perfect|great|excellent)\b', 0.95),
        (r'\b(ok|okay|alright|fine|good|works for me|that works|i can do that)\b', 0.85),
        (r'\b(confirm|confirmed|book|schedule|set it up|let\'s do it)\b', 0.9),
        (r'\b(available|free|open)\b', 0.75),
    ]
    
    # Strong rejection patterns  
    rejection_patterns = [
        (r'\b(no|nope|not really|can\'t|cannot|unable|unavailable)\b', 0.9),
        (r'\b(busy|booked|occupied|not available|not free)\b', 0.85),
        (r'\b(different time|another time|reschedule|change|doesn\'t work|won\'t work)\b', 0.8),
        (r'\b(sorry|unfortunately|afraid)\b.*\b(can\'t|cannot|not|no)\b', 0.8),
    ]
    
    # Time-specific patterns (when they mention specific times)
    time_patterns = [
        (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*\b(at|@)?\s*(\d{1,2})\s*(am|pm)\b', 0.95),
        (r'\b(\d{1,2})\s*(am|pm)\b.*\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 0.95),
        (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 0.8),
        (r'\b(\d{1,2})\s*(am|pm|o\'clock)\b', 0.75),
        (r'\b(morning|afternoon|evening|noon|midnight)\b', 0.6),
    ]
    
    # Availability checking patterns
    availability_patterns = [
        (r'\b(let me check|check my calendar|look at my schedule|see what|when am i)\b', 0.7),
        (r'\b(what times|what slots|what options|available times|available slots)\b', 0.8),
    ]
    
    # Polite conversation patterns
    politeness_patterns = [
        (r'\b(thank you|thanks|appreciate|grateful)\b', 0.6),
        (r'\b(hello|hi|hey|good morning|good afternoon)\b', 0.6),
        (r'\b(sorry|excuse me|pardon)\b', 0.5),
    ]
    
    # Check patterns in order of confidence
    
    # Check for specific time mentions first (highest priority)
    for pattern, confidence in time_patterns:
        if re.search(pattern, text_lower):
            return "time_mention", confidence
    
    # Check for strong confirmations
    for pattern, confidence in confirmation_patterns:
        if re.search(pattern, text_lower):
            return "confirmation", confidence
    
    # Check for rejections
    for pattern, confidence in rejection_patterns:
        if re.search(pattern, text_lower):
            return "rejection", confidence
            
    # Check for availability checking
    for pattern, confidence in availability_patterns:
        if re.search(pattern, text_lower):
            return "checking_availability", confidence
    
    # Check for politeness (neutral but positive)
    for pattern, confidence in politeness_patterns:
        if re.search(pattern, text_lower):
            return "polite_response", confidence
    
    # Check text length and complexity for better classification
    if len(text_lower) < 3:
        return "unclear", 0.1
    elif len(text_lower.split()) == 1:
        # Single word responses
        single_word = text_lower.strip()
        if single_word in ["yes", "yep", "yeah", "ok", "okay", "sure", "fine", "good"]:
            return "confirmation", 0.8
        elif single_word in ["no", "nope", "nah"]:
            return "rejection", 0.8
        else:
            return "unclear", 0.4
    
    # Default: unclear intent but with some confidence if it's a reasonable response
    if len(text_lower.split()) >= 2:
        return "unclear", 0.5
    else:
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

def update_candidate_call_tracking(candidate_id: str, call_data: dict) -> bool:
    """Update candidate document in MongoDB with call tracking data"""
    try:
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning("pymongo not installed; cannot update call tracking")
            return False

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            logger.warning("MONGODB_URI not configured; cannot update call tracking")
            return False

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")
        db = client[db_name]
        coll = db[coll_name]

        # Try to find candidate by various ID formats
        try:
            from bson import ObjectId
            query = {"_id": ObjectId(candidate_id)}
            doc = coll.find_one(query)
        except Exception:
            doc = coll.find_one({"$or": [
                {"id": candidate_id},
                {"email": candidate_id},
                {"phone": candidate_id},
                {"phone_number": candidate_id}
            ]})

        if not doc:
            logger.warning(f"Candidate not found for ID: {candidate_id}")
            return False

        # Initialize call tracking structure if it doesn't exist
        if "call_tracking" not in doc:
            doc["call_tracking"] = {
                "total_attempts": 0,
                "max_attempts": 3,
                "status": "active",  # active, max_attempts, interview_scheduled, completed
                "last_contact_date": None,
                "call_history": [],
                "interview_details": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

        # Update call tracking data
        doc["call_tracking"]["total_attempts"] += 1
        doc["call_tracking"]["last_contact_date"] = call_data.get("initiated_at", datetime.now().isoformat())
        doc["call_tracking"]["updated_at"] = datetime.now().isoformat()
        
        # Add call to history
        doc["call_tracking"]["call_history"].append({
            "call_sid": call_data.get("call_sid"),
            "initiated_at": call_data.get("initiated_at"),
            "status": call_data.get("twilio_status"),
            "outcome": call_data.get("outcome"),
            "duration": call_data.get("call_duration"),
            "notes": call_data.get("notes")
        })

        # Update status based on attempts
        if doc["call_tracking"]["total_attempts"] >= doc["call_tracking"]["max_attempts"]:
            if not doc["call_tracking"].get("interview_details"):
                doc["call_tracking"]["status"] = "max_attempts"

        # Update the document
        try:
            from bson import ObjectId
            result = coll.update_one({"_id": ObjectId(candidate_id)}, {"$set": doc})
        except Exception:
            result = coll.update_one({"$or": [
                {"id": candidate_id},
                {"email": candidate_id},
                {"phone": candidate_id}
            ]}, {"$set": doc})

        logger.info(f"Updated call tracking for candidate {candidate_id}: {doc['call_tracking']['total_attempts']} attempts")
        return result.modified_count > 0

    except Exception as e:
        logger.error(f"Error updating call tracking for candidate {candidate_id}: {e}")
        return False

def update_candidate_interview_scheduled(candidate_id: str, interview_details: dict) -> bool:
    """Update candidate document when interview is successfully scheduled"""
    try:
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning("pymongo not installed; cannot update interview details")
            return False

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return False

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")
        db = client[db_name]
        coll = db[coll_name]

        # Find candidate
        try:
            from bson import ObjectId
            query = {"_id": ObjectId(candidate_id)}
        except Exception:
            query = {"$or": [
                {"id": candidate_id},
                {"email": candidate_id},
                {"phone": candidate_id}
            ]}

        # Update interview details and status
        update_data = {
            "$set": {
                "call_tracking.status": "interview_scheduled",
                "call_tracking.interview_details": {
                    "scheduled_slot": interview_details.get("scheduled_slot"),
                    "scheduled_at": interview_details.get("scheduled_at", datetime.now().isoformat()),
                    "call_sid": interview_details.get("call_sid"),
                    "email_sent": interview_details.get("email_sent", False),
                    "confirmation_sent_at": datetime.now().isoformat() if interview_details.get("email_sent") else None
                },
                "call_tracking.updated_at": datetime.now().isoformat()
            }
        }

        result = coll.update_one(query, update_data)
        
        if result.modified_count > 0:
            logger.info(f"✅ Successfully updated interview details for candidate {candidate_id}: {interview_details.get('scheduled_slot')}")
            # Verify the update by fetching the document
            doc = coll.find_one(query)
            if doc:
                logger.info(f"✅ Verification: Candidate status is now {doc.get('call_tracking', {}).get('status')}")
            return True
        else:
            logger.error(f"❌ Failed to update candidate {candidate_id}. Query: {query}")
            # Check if document exists
            doc = coll.find_one(query)
            if doc:
                logger.error(f"❌ Document exists but update failed. Current call_tracking: {doc.get('call_tracking')}")
            else:
                logger.error(f"❌ No document found with candidate_id: {candidate_id}")
            return False

    except Exception as e:
        logger.error(f"Error updating interview details for candidate {candidate_id}: {e}")
        return False

def get_candidate_call_status(candidate_id: str) -> dict:
    """Get call tracking status for a candidate from MongoDB"""
    try:
        try:
            from pymongo import MongoClient
        except ImportError:
            return {"can_call": True, "reason": "MongoDB not available", "attempts": 0}

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return {"can_call": True, "reason": "MongoDB not configured", "attempts": 0}

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")
        db = client[db_name]
        coll = db[coll_name]

        # Find candidate
        try:
            from bson import ObjectId
            doc = coll.find_one({"_id": ObjectId(candidate_id)})
        except Exception:
            doc = coll.find_one({"$or": [
                {"id": candidate_id},
                {"email": candidate_id},
                {"phone": candidate_id}
            ]})

        if not doc:
            return {"can_call": True, "reason": "New candidate", "attempts": 0}

        call_tracking = doc.get("call_tracking", {})
        total_attempts = call_tracking.get("total_attempts", 0)
        max_attempts = call_tracking.get("max_attempts", 3)
        status = call_tracking.get("status", "active")

        # Check if they can receive calls
        if status == "interview_scheduled":
            return {
                "can_call": False,
                "reason": "Interview already scheduled",
                "attempts": total_attempts,
                "status": status,
                "interview_details": call_tracking.get("interview_details")
            }

        if total_attempts >= max_attempts:
            return {
                "can_call": False,
                "reason": f"Maximum attempts reached ({total_attempts}/{max_attempts})",
                "attempts": total_attempts,
                "status": "max_attempts"
            }

        return {
            "can_call": True,
            "reason": f"Can receive calls ({total_attempts}/{max_attempts})",
            "attempts": total_attempts,
            "status": status
        }

    except Exception as e:
        logger.error(f"Error checking call status for candidate {candidate_id}: {e}")
        return {"can_call": True, "reason": "Error checking status", "attempts": 0}

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

async def send_interview_confirmation_email(candidate: dict, confirmed_slot: str, call_sid: str):
    """Send professional interview confirmation email"""
    logger.info(f"📧 Attempting to send interview confirmation email for call {call_sid}")
    logger.info(f"📧 Candidate: {candidate.get('name', 'Unknown')} ({candidate.get('email', 'No email')})")
    logger.info(f"📧 Confirmed slot: {confirmed_slot}")
    
    if not all([SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL]):
        logger.warning("❌ SMTP credentials not configured. Cannot send confirmation email.")
        return False
    
    try:
        # Extract candidate information
        candidate_name = candidate.get('name', 'Candidate')
        candidate_email = candidate.get('email')
        position = candidate.get('position', 'Software Developer')
        company = candidate.get('company', 'Our Company')
        
        if not candidate_email:
            logger.warning(f"No email address found for candidate: {candidate_name}")
            return False
        
        # Create email content
        subject = f"Interview Confirmation - {position} Position at {company}"
        
        # HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                    <h2 style="color: #2c3e50; margin-top: 0;">Interview Confirmation</h2>
                    <p>Dear {candidate_name},</p>
                    <p>Thank you for speaking with us today! We're excited to confirm your interview for the <strong>{position}</strong> position at <strong>{company}</strong>.</p>
                </div>
                
                <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #1976d2; margin-top: 0;">Interview Details:</h3>
                    <p><strong>Position:</strong> {position}</p>
                    <p><strong>Date & Time:</strong> {confirmed_slot}</p>
                    <p><strong>Format:</strong> Video Interview (Link will be sent separately)</p>
                    <p><strong>Duration:</strong> Approximately 45-60 minutes</p>
                </div>
                
                <div style="margin: 20px 0;">
                    <h3 style="color: #2c3e50;">What to Expect:</h3>
                    <ul style="padding-left: 20px;">
                        <li>Technical discussion about your experience and skills</li>
                        <li>Questions about your approach to problem-solving</li>
                        <li>Overview of our company culture and the role</li>
                        <li>Opportunity for you to ask questions about the position</li>
                    </ul>
                </div>
                
                <div style="margin: 20px 0;">
                    <h3 style="color: #2c3e50;">Preparation Tips:</h3>
                    <ul style="padding-left: 20px;">
                        <li>Review the job description and your application</li>
                        <li>Prepare examples of your relevant experience</li>
                        <li>Test your video/audio setup beforehand</li>
                        <li>Have questions ready about the role and company</li>
                    </ul>
                </div>
                
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Important:</strong> If you need to reschedule or have any questions, please reply to this email or call us at your earliest convenience.</p>
                </div>
                
                <div style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #e9ecef;">
                    <p>We look forward to speaking with you!</p>
                    <p>Best regards,<br>
                    <strong>Sarah Johnson</strong><br>
                    Talent Acquisition Team<br>
                    {company}<br>
                    <a href="mailto:{SENDER_EMAIL}" style="color: #1976d2;">{SENDER_EMAIL}</a></p>
                </div>
                
                <div style="margin-top: 20px; font-size: 12px; color: #6c757d; text-align: center;">
                    <p>This email was sent following your phone conversation on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}.<br>
                    Reference ID: {call_sid}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
        Interview Confirmation - {position} Position at {company}
        
        Dear {candidate_name},
        
        Thank you for speaking with us today! We're excited to confirm your interview for the {position} position at {company}.
        
        Interview Details:
        - Position: {position}
        - Date & Time: {confirmed_slot}
        - Format: Video Interview (Link will be sent separately)
        - Duration: Approximately 45-60 minutes
        
        What to Expect:
        • Technical discussion about your experience and skills
        • Questions about your approach to problem-solving
        • Overview of our company culture and the role
        • Opportunity for you to ask questions about the position
        
        Preparation Tips:
        • Review the job description and your application
        • Prepare examples of your relevant experience
        • Test your video/audio setup beforehand
        • Have questions ready about the role and company
        
        Important: If you need to reschedule or have any questions, please reply to this email or call us at your earliest convenience.
        
        We look forward to speaking with you!
        
        Best regards,
        Sarah Johnson
        Talent Acquisition Team
        {company}
        {SENDER_EMAIL}
        
        This email was sent following your phone conversation on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}.
        Reference ID: {call_sid}
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = candidate_email
        
        # Add both plain text and HTML versions
        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"✅ Interview confirmation email sent successfully to {candidate_email} for slot: {confirmed_slot}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")
        return False

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
        
        # Generate professional TwiML with natural conversation flow
        twiml = f"""<Response>
            <Say voice="alice">{html.escape(greeting)}</Say>
            <Pause length="1"/>
            <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="15" speechTimeout="auto">
                <Say voice="alice">I'm calling to schedule your interview. We're excited about your application and would love to meet with you. Are you available to discuss some potential interview times right now?</Say>
            </Gather>
            <Say voice="alice">Thank you for your time. We'll reach out via email with more details. Have a great day!</Say>
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
            
            # Generate contextual retry TwiML based on conversation stage
            retry_twiml = f"""<Response>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="15" speechTimeout="auto">
                    <Say voice="alice">I'm sorry, I didn't hear that clearly. Could you please speak a bit louder? I was asking if you're available to discuss some interview times right now.</Say>
                </Gather>
                <Say voice="alice">No worries! We'll send you an email with available times. Thank you!</Say>
                <Hangup/>
            </Response>"""
            return Response(content=retry_twiml, media_type="text/xml")
        
        # Get or create session
        session = conversation_sessions.get(call_sid)
        if not session:
            logger.warning(f"Session not found for CallSid: {call_sid}, creating new session")
            # Try to load from database first
            session = load_session_from_db(call_sid)
            if session:
                conversation_sessions[call_sid] = session
            else:
                # Find candidate by phone number to include in session
                caller_phone = form_data.get("From", "")
                candidate = find_candidate_by_phone(caller_phone)
                session = get_or_create_session(call_sid, caller_phone, candidate)
        
        # Analyze user intent and conversation context
        intent, intent_confidence = analyze_intent(speech_result)
        turn_number = len(session.turns) + 1
        
        logger.info(f"Turn #{turn_number} - Intent: {intent} (confidence: {intent_confidence:.2f}) - Input: '{speech_result}'")
        
        # Define conversation stages for better flow
        conversation_stage = "initial" if turn_number == 2 else "scheduling" if turn_number < 5 else "closing"
        
        # Handle different conversation stages
        if conversation_stage == "initial":
            # First response - check if they're available to talk
            if intent == "confirmation" or any(word in speech_result.lower() for word in ["yes", "yeah", "sure", "available", "okay", "ok"]):
                ai_response = "Wonderful! We have several interview slots available. Let me share them with you: Monday at 10 AM, Tuesday at 2 PM, Wednesday at 11 AM, or Thursday at 3 PM. Which of these times works best for your schedule?"
                next_action = "gather_schedule"
            elif intent == "rejection" or any(word in speech_result.lower() for word in ["no", "not", "busy", "can't", "cannot"]):
                ai_response = "I completely understand. Would you prefer if we sent you an email with our available times so you can respond when convenient?"
                next_action = "gather_email_preference"
            else:
                ai_response = "No problem at all. I'm calling to schedule your interview. Do you have just a minute to go over some available times?"
                next_action = "gather_availability"
                
        elif conversation_stage == "scheduling":
            # Main scheduling conversation
            if intent == "confirmation" and intent_confidence > 0.6:
                # Look for specific time mentioned
                mentioned_slot = find_mentioned_time_slot(speech_result, TIME_SLOTS)
                if mentioned_slot:
                    confirmed_slot = mentioned_slot
                    session.confirmed_slot = confirmed_slot
                    session.status = "completed"
                    session.end_time = datetime.now().isoformat()
                    
                    # Get candidate info for comprehensive tracking
                    candidate = session.candidate or CANDIDATE
                    if isinstance(candidate, dict) and candidate.get('id'):
                        candidate_id = candidate.get('id')
                    elif session.candidate_phone:
                        # If no candidate ID, try to find candidate by phone
                        found_candidate = find_candidate_by_phone(session.candidate_phone)
                        if found_candidate:
                            candidate_id = found_candidate.get('id')
                            session.candidate = found_candidate  # Update session with found candidate
                            candidate = found_candidate  # Update candidate for email
                        else:
                            candidate_id = f"phone_{session.candidate_phone}"
                    else:
                        candidate_id = candidate.get('email', 'unknown')
                    
                    logger.info(f"Processing interview confirmation for candidate ID: {candidate_id}")
                    
                    # Send confirmation email
                    email_sent = await send_interview_confirmation_email(candidate, confirmed_slot, call_sid)
                    
                    # Save interview schedule to MongoDB
                    interview_details = {
                        "scheduled_slot": confirmed_slot,
                        "call_sid": call_sid,
                        "email_sent": email_sent,
                        "scheduled_at": datetime.now().isoformat()
                    }
                    update_candidate_interview_scheduled(candidate_id, interview_details)
                    
                    # Log successful scheduling
                    log_system_event("INFO", "INTERVIEW_SYSTEM", "INTERVIEW_SCHEDULED", 
                                    f"Interview scheduled for {confirmed_slot}. Email sent: {email_sent}", 
                                    call_sid=call_sid, candidate_id=candidate_id)
                    
                    if email_sent:
                        ai_response = f"Perfect! I have you scheduled for {confirmed_slot}. You'll receive a detailed confirmation email shortly with all the interview information. We're looking forward to meeting with you!"
                    else:
                        ai_response = f"Perfect! I have you scheduled for {confirmed_slot}. We'll follow up with the interview details. We're looking forward to meeting with you!"
                    
                    next_action = "end_call"
                else:
                    ai_response = f"Great! Just to confirm, which time works best for you? We have Monday at 10 AM, Tuesday at 2 PM, Wednesday at 11 AM, or Thursday at 3 PM."
                    next_action = "gather_specific_time"
            elif intent == "rejection":
                ai_response = "I understand those times don't work. We're flexible with scheduling. Would you prefer morning or afternoon slots? We can also look at other days."
                next_action = "gather_preferences"
            elif any(day.lower() in speech_result.lower() for day in ["monday", "tuesday", "wednesday", "thursday"]):
                # They mentioned a day, try to match it
                mentioned_slot = find_mentioned_time_slot(speech_result, TIME_SLOTS)
                if mentioned_slot:
                    session.confirmed_slot = mentioned_slot
                    session.status = "completed"
                    session.end_time = datetime.now().isoformat()
                    
                    # Get candidate info for comprehensive tracking
                    candidate = session.candidate or CANDIDATE
                    if isinstance(candidate, dict) and candidate.get('id'):
                        candidate_id = candidate.get('id')
                    elif session.candidate_phone:
                        # If no candidate ID, try to find candidate by phone
                        found_candidate = find_candidate_by_phone(session.candidate_phone)
                        if found_candidate:
                            candidate_id = found_candidate.get('id')
                            session.candidate = found_candidate  # Update session with found candidate
                            candidate = found_candidate  # Update candidate for email
                        else:
                            candidate_id = f"phone_{session.candidate_phone}"
                    else:
                        candidate_id = candidate.get('email', 'unknown')
                    
                    logger.info(f"Processing interview confirmation for candidate ID: {candidate_id}")
                    
                    # Send confirmation email
                    email_sent = await send_interview_confirmation_email(candidate, mentioned_slot, call_sid)
                    
                    # Save interview schedule to MongoDB
                    interview_details = {
                        "scheduled_slot": mentioned_slot,
                        "call_sid": call_sid,
                        "email_sent": email_sent,
                        "scheduled_at": datetime.now().isoformat()
                    }
                    update_candidate_interview_scheduled(candidate_id, interview_details)
                    
                    # Log successful scheduling
                    log_system_event("INFO", "INTERVIEW_SYSTEM", "INTERVIEW_SCHEDULED", 
                                    f"Interview scheduled for {mentioned_slot}. Email sent: {email_sent}", 
                                    call_sid=call_sid, candidate_id=candidate_id)
                    
                    if email_sent:
                        ai_response = f"Excellent! I have you down for {mentioned_slot}. You'll receive a detailed confirmation email with all the interview information. Thank you so much!"
                    else:
                        ai_response = f"Excellent! I have you down for {mentioned_slot}. We'll follow up with all the interview details. Thank you so much!"
                    
                    next_action = "end_call"
                else:
                    ai_response = "I heard you mention a day preference. Let me repeat our exact times: Monday at 10 AM, Tuesday at 2 PM, Wednesday at 11 AM, or Thursday at 3 PM. Which specific time works?"
                    next_action = "gather_specific_time"
            else:
                ai_response = generate_ai_response(session, speech_result, intent, intent_confidence)
                next_action = "continue_gathering"
                
        else:  # closing stage
            ai_response = "Thank you for your time today. We'll send you an email with our available interview times and you can respond at your convenience. Have a great day!"
            session.status = "failed"
            session.end_time = datetime.now().isoformat()
            next_action = "end_call"
        
        # Prevent infinite loops - max 6 turns total
        if turn_number > 6:
            ai_response = "Thank you so much for your time. We'll follow up by email with scheduling details. Have a wonderful day!"
            session.status = "failed" if not session.confirmed_slot else "completed"
            session.end_time = datetime.now().isoformat()
            next_action = "end_call"
        
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
        
        logger.info(f"AI response: '{ai_response}' | Next action: {next_action}")
        
        # Generate TwiML based on conversation flow
        if next_action == "end_call" or session.status in ["completed", "failed"]:
            # End the call professionally
            final_twiml = f"""<Response>
                <Say voice='alice'>{html.escape(ai_response)}</Say>
                <Hangup/>
            </Response>"""
            return Response(content=final_twiml, media_type="text/xml")
            
        elif next_action == "gather_schedule":
            # Gathering time slot preferences
            schedule_twiml = f"""<Response>
                <Say voice="alice">{html.escape(ai_response)}</Say>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="15" speechTimeout="auto">
                    <Say voice="alice">Just say the day and time that works best for you.</Say>
                </Gather>
                <Say voice="alice">No problem! We'll email you the available times. Thank you!</Say>
                <Hangup/>
            </Response>"""
            return Response(content=schedule_twiml, media_type="text/xml")
            
        elif next_action == "gather_specific_time":
            # Getting specific time confirmation
            specific_twiml = f"""<Response>
                <Say voice="alice">{html.escape(ai_response)}</Say>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="15" speechTimeout="auto">
                    <Say voice="alice">Please tell me which specific time works for you.</Say>
                </Gather>
                <Say voice="alice">We'll follow up by email. Thank you!</Say>
                <Hangup/>
            </Response>"""
            return Response(content=specific_twiml, media_type="text/xml")
            
        else:
            # Default continuation for other cases
            continue_twiml = f"""<Response>
                <Say voice="alice">{html.escape(ai_response)}</Say>
                <Gather input="speech" action="{WEBHOOK_BASE_URL}/twilio-process" method="POST" timeout="15" speechTimeout="auto">
                    <Say voice="alice">Please let me know your thoughts.</Say>
                </Gather>
                <Say voice="alice">Thank you! We'll reach out by email with the details.</Say>
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
    
    # Check call limits from MongoDB
    final_candidate_id = candidate_id or candidate_info.get('email') or f"phone_{candidate_info.get('phone')}"
    call_status = get_candidate_call_status(final_candidate_id)
    
    if not call_status["can_call"]:
        return {
            "status": "error",
            "message": f"Cannot make call: {call_status['reason']}",
            "candidate": candidate_info.get("name"),
            "attempts": call_status["attempts"],
            "call_limit_reached": True,
            "details": call_status
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
        
        # Log call initiation
        log_system_event("INFO", "CALL_SYSTEM", "CALL_INITIATED", 
                        f"Initiating call to {candidate_info.get('phone')} for {candidate_info.get('name')} (Attempt {call_status['attempts'] + 1}/3)", 
                        candidate_id=final_candidate_id)
        
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
        
        # Update MongoDB with call attempt
        call_data = {
            "call_sid": call.sid,
            "initiated_at": datetime.now().isoformat(),
            "twilio_status": call.status,
            "outcome": "initiated",
            "notes": f"Call initiated to {candidate_info.get('name')} for {candidate_info.get('position')} position"
        }
        update_candidate_call_tracking(final_candidate_id, call_data)

        # Check call status after a moment
        import time
        time.sleep(2)
        updated_call = client.calls(call.sid).fetch()
        logger.info(f"Updated call status: {updated_call.status}")
        
        # Update MongoDB with latest call status
        updated_call_data = {
            "call_sid": call.sid,
            "initiated_at": datetime.now().isoformat(),
            "twilio_status": updated_call.status,
            "call_duration": getattr(updated_call, 'duration', None),
            "outcome": "in_progress" if updated_call.status in ['ringing', 'in-progress'] else updated_call.status,
            "notes": f"Call status updated: {updated_call.status}"
        }
        # Don't increment attempts again, just update the last call record
        # update_candidate_call_tracking(final_candidate_id, updated_call_data)
        
        if updated_call.status == 'failed':
            error_code = getattr(updated_call, 'error_code', 'Unknown')
            error_message = getattr(updated_call, 'error_message', 'Unknown error')
            
            logger.error(f"Call failed. Error code: {error_code}")
            logger.error(f"Error message: {error_message}")
            
            # Log failure
            log_system_event("ERROR", "CALL_SYSTEM", "CALL_FAILED", 
                            f"Call failed: {error_message} (Code: {error_code})", 
                            call_sid=call.sid, candidate_id=candidate_id)
            
            return {
                "status": "error",
                "message": f"Call failed: {error_message}",
                "error_code": error_code,
                "call_sid": call.sid
            }
        
        # Create or update in-memory session and persist
        session = get_or_create_session(call.sid, candidate_info.get("phone"), candidate=candidate_info)
        session.candidate = candidate_info
        save_conversation_session(session)
        
        # Log successful call setup
        log_system_event("INFO", "CALL_SYSTEM", "CALL_ESTABLISHED", 
                        f"Call established successfully with status: {updated_call.status}", 
                        call_sid=call.sid, candidate_id=candidate_id)

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
    """Get all candidates from MongoDB with call tracking data"""
    try:
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning("pymongo not installed; returning empty list")
            return {"candidates": [], "total": 0, "status": "error", "message": "MongoDB not available"}

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return {"candidates": [], "total": 0, "status": "error", "message": "MongoDB not configured"}

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")
        db = client[db_name]
        coll = db[coll_name]

        # Get all candidates with call tracking data
        candidates_cursor = coll.find({})
        candidates = []
        
        total_candidates = 0
        active_candidates = 0
        max_attempts_reached = 0
        interviews_scheduled = 0
        
        for doc in candidates_cursor:
            total_candidates += 1
            
            # Extract basic info
            candidate = {
                "id": str(doc.get("_id", doc.get("id", "unknown"))),
                "name": doc.get("name") or doc.get("full_name") or doc.get("candidate_name"),
                "phone": doc.get("phone") or doc.get("phone_number"),
                "email": doc.get("email"),
                "position": doc.get("position") or doc.get("role"),
                "company": doc.get("company") or doc.get("employer")
            }
            
            # Add call tracking data
            call_tracking = doc.get("call_tracking", {})
            candidate["call_tracking"] = {
                "total_attempts": call_tracking.get("total_attempts", 0),
                "max_attempts": call_tracking.get("max_attempts", 3),
                "status": call_tracking.get("status", "active"),
                "last_contact_date": call_tracking.get("last_contact_date"),
                "can_call": call_tracking.get("total_attempts", 0) < call_tracking.get("max_attempts", 3) and call_tracking.get("status", "active") not in ["interview_scheduled", "max_attempts"],
                "interview_details": call_tracking.get("interview_details"),
                "recent_calls": call_tracking.get("call_history", [])[-3:] if call_tracking.get("call_history") else []
            }
            
            # Update counters
            status = call_tracking.get("status", "active")
            if status == "active" and call_tracking.get("total_attempts", 0) < call_tracking.get("max_attempts", 3):
                active_candidates += 1
            elif status == "max_attempts":
                max_attempts_reached += 1
            elif status == "interview_scheduled":
                interviews_scheduled += 1
                
            candidates.append(candidate)
        
        return {
            "candidates": candidates,
            "total": total_candidates,
            "summary": {
                "active_candidates": active_candidates,
                "max_attempts_reached": max_attempts_reached,
                "interviews_scheduled": interviews_scheduled,
                "can_still_call": active_candidates
            },
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Error fetching candidates with call tracking: {e}")
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
            error_message = getattr(updated_call, 'error_message', 'Unknown error')
            error_code = getattr(updated_call, 'error_code', 'Unknown')
            
            logger.error(f"Call failed. Error: {error_message}")
            return {
                "status": "error",
                "message": f"Call failed: {error_message}",
                "error_code": error_code,
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

@app.post("/test-email")
async def test_email(request: Request):
    """Test email functionality"""
    try:
        body = await request.json()
        candidate_id = body.get("candidate_id") if isinstance(body, dict) else None
        test_slot = body.get("time_slot", "Monday at 10 AM")
        
        # Get candidate info
        candidate_info = None
        if candidate_id:
            candidate_info = fetch_candidate_by_id(candidate_id)
        
        if not candidate_info:
            candidate_info = CANDIDATE
        
        # Send test email
        test_call_sid = f"TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        email_sent = await send_interview_confirmation_email(candidate_info, test_slot, test_call_sid)
        
        return {
            "status": "success" if email_sent else "error",
            "message": "Test email sent successfully" if email_sent else "Failed to send test email",
            "candidate": candidate_info.get("name"),
            "email": candidate_info.get("email"),
            "time_slot": test_slot,
            "call_sid": test_call_sid
        }
        
    except Exception as e:
        logger.error(f"Error in test email: {e}")
        return {
            "status": "error",
            "message": f"Test email failed: {str(e)}"
        }

@app.get("/comprehensive-analytics")
async def get_comprehensive_analytics():
    """Get detailed analytics with all tracked data"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Call attempts analytics
        cursor.execute('SELECT COUNT(*) FROM call_attempts')
        total_call_attempts = cursor.fetchone()[0]
        
        cursor.execute('SELECT outcome, COUNT(*) FROM call_attempts GROUP BY outcome')
        outcome_stats = dict(cursor.fetchall())
        
        cursor.execute('SELECT twilio_status, COUNT(*) FROM call_attempts GROUP BY twilio_status')
        status_stats = dict(cursor.fetchall())
        
        # Interview scheduling analytics
        cursor.execute('SELECT COUNT(*) FROM interview_schedules WHERE status = "scheduled"')
        interviews_scheduled = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM interview_schedules WHERE confirmation_email_sent = 1')
        emails_sent = cursor.fetchone()[0]
        
        cursor.execute('SELECT scheduled_slot, COUNT(*) FROM interview_schedules GROUP BY scheduled_slot ORDER BY COUNT(*) DESC LIMIT 5')
        popular_slots = cursor.fetchall()
        
        # Conversation analytics
        cursor.execute('SELECT AVG(total_turns) FROM conversation_sessions WHERE total_turns > 0')
        avg_conversation_turns = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT AVG(ai_confidence_avg) FROM conversation_sessions WHERE ai_confidence_avg > 0')
        avg_ai_confidence = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT status, COUNT(*) FROM conversation_sessions GROUP BY status')
        conversation_status_stats = dict(cursor.fetchall())
        
        # Recent activity (last 7 days)
        cursor.execute('''
            SELECT DATE(initiated_at) as call_date, COUNT(*) as calls_count 
            FROM call_attempts 
            WHERE initiated_at >= datetime('now', '-7 days') 
            GROUP BY DATE(initiated_at) 
            ORDER BY call_date DESC
        ''')
        recent_activity = cursor.fetchall()
        
        # System logs summary
        cursor.execute('SELECT log_level, COUNT(*) FROM system_logs GROUP BY log_level')
        log_stats = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            "call_analytics": {
                "total_attempts": total_call_attempts,
                "outcome_breakdown": outcome_stats,
                "status_breakdown": status_stats,
                "success_rate": round((outcome_stats.get('interview_scheduled', 0) / total_call_attempts * 100) if total_call_attempts > 0 else 0, 2)
            },
            "interview_analytics": {
                "total_scheduled": interviews_scheduled,
                "emails_sent": emails_sent,
                "email_success_rate": round((emails_sent / interviews_scheduled * 100) if interviews_scheduled > 0 else 0, 2),
                "popular_time_slots": [{"slot": slot[0], "count": slot[1]} for slot in popular_slots]
            },
            "conversation_analytics": {
                "avg_turns_per_conversation": round(avg_conversation_turns, 2),
                "avg_ai_confidence": round(avg_ai_confidence, 3),
                "conversation_outcomes": conversation_status_stats
            },
            "recent_activity": [{"date": activity[0], "calls": activity[1]} for activity in recent_activity],
            "system_health": {
                "log_level_distribution": log_stats,
                "total_logs": sum(log_stats.values())
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating comprehensive analytics: {e}")
        return {"error": str(e)}

@app.get("/call-attempts/{candidate_id}")
async def get_candidate_call_history(candidate_id: str):
    """Get detailed call history for a specific candidate"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ca.*, cs.confirmed_slot, cs.status as conversation_status
            FROM call_attempts ca
            LEFT JOIN conversation_sessions cs ON ca.call_sid = cs.call_sid
            WHERE ca.candidate_id = ?
            ORDER BY ca.initiated_at DESC
        ''', (candidate_id,))
        
        attempts = cursor.fetchall()
        
        # Get column names
        columns = [desc[0] for desc in cursor.description]
        
        # Convert to list of dictionaries
        call_history = []
        for attempt in attempts:
            attempt_dict = dict(zip(columns, attempt))
            call_history.append(attempt_dict)
        
        # Get interview schedules for this candidate
        cursor.execute('''
            SELECT * FROM interview_schedules 
            WHERE candidate_id = ?
            ORDER BY scheduled_at DESC
        ''', (candidate_id,))
        
        interviews = cursor.fetchall()
        interview_columns = [desc[0] for desc in cursor.description]
        interview_history = [dict(zip(interview_columns, interview)) for interview in interviews]
        
        conn.close()
        
        return {
            "candidate_id": candidate_id,
            "total_attempts": len(call_history),
            "call_history": call_history,
            "interview_history": interview_history,
            "last_contact": call_history[0]['initiated_at'] if call_history else None
        }
        
    except Exception as e:
        logger.error(f"Error getting call history for candidate {candidate_id}: {e}")
        return {"error": str(e)}

@app.get("/system-logs")
async def get_system_logs(limit: int = 50, level: str = None):
    """Get system logs with optional filtering"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        if level:
            cursor.execute('''
                SELECT * FROM system_logs 
                WHERE log_level = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (level.upper(), limit))
        else:
            cursor.execute('''
                SELECT * FROM system_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
        
        logs = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        log_entries = [dict(zip(columns, log)) for log in logs]
        
        conn.close()
        
        return {
            "logs": log_entries,
            "total_returned": len(log_entries),
            "filter_level": level
        }
        
    except Exception as e:
        logger.error(f"Error getting system logs: {e}")
        return {"error": str(e)}

@app.get("/candidate-limits")
async def get_candidate_call_limits():
    """Get all candidates with their call attempt counts and interview status"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        
        # Get MongoDB candidates
        candidates_list = []
        try:
            mongo_candidates = {"status": "success", "candidates": get_all_candidates_from_mongo()}
            if mongo_candidates.get("status") == "success":
                candidates_list = mongo_candidates.get("candidates", [])
        except:
            pass
        
        candidate_info = {}
        
        # Process each candidate from MongoDB
        for candidate in candidates_list:
            candidate_id = candidate.get('id')
            if candidate_id:
                can_call, attempts, has_scheduled = check_call_limit(candidate_id)
                
                # Get last contact date
                cursor.execute('''
                    SELECT MAX(initiated_at) FROM call_attempts 
                    WHERE candidate_id = ?
                ''', (candidate_id,))
                last_contact = cursor.fetchone()[0]
                
                # Get scheduled interviews count
                cursor.execute('''
                    SELECT COUNT(*) FROM interview_schedules 
                    WHERE candidate_id = ? AND status = 'scheduled'
                ''', (candidate_id,))
                scheduled_count = cursor.fetchone()[0]
                
                candidate_info[candidate_id] = {
                    "name": candidate.get('name'),
                    "email": candidate.get('email'),
                    "phone": candidate.get('phone'),
                    "position": candidate.get('position'),
                    "company": candidate.get('company'),
                    "call_attempts": attempts,
                    "can_receive_calls": can_call,
                    "has_scheduled_interview": has_scheduled,
                    "scheduled_interviews_count": scheduled_count,
                    "last_contact_date": last_contact,
                    "status": "interview_scheduled" if has_scheduled else ("max_attempts" if attempts >= 3 else "active")
                }
        
        # Also check for any candidates in our local database that might not be in MongoDB
        cursor.execute('''
            SELECT DISTINCT candidate_id FROM call_attempts 
            WHERE candidate_id NOT IN (''' + ','.join(['?' for _ in candidate_info.keys()]) + ''')
        ''' if candidate_info else '''
            SELECT DISTINCT candidate_id FROM call_attempts
        ''', list(candidate_info.keys()) if candidate_info else [])
        
        local_only_candidates = cursor.fetchall()
        
        for (candidate_id,) in local_only_candidates:
            can_call, attempts, has_scheduled = check_call_limit(candidate_id)
            
            cursor.execute('''
                SELECT MAX(initiated_at) FROM call_attempts 
                WHERE candidate_id = ?
            ''', (candidate_id,))
            last_contact = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM interview_schedules 
                WHERE candidate_id = ? AND status = 'scheduled'
            ''', (candidate_id,))
            scheduled_count = cursor.fetchone()[0]
            
            candidate_info[candidate_id] = {
                "name": "Unknown (Local DB Only)",
                "email": candidate_id if '@' in candidate_id else "Unknown",
                "phone": candidate_id if candidate_id.startswith('phone_') else "Unknown",
                "position": "Unknown",
                "company": "Unknown",
                "call_attempts": attempts,
                "can_receive_calls": can_call,
                "has_scheduled_interview": has_scheduled,
                "scheduled_interviews_count": scheduled_count,
                "last_contact_date": last_contact,
                "status": "interview_scheduled" if has_scheduled else ("max_attempts" if attempts >= 3 else "active")
            }
        
        conn.close()
        
        # Sort by call attempts (highest first) and then by last contact
        sorted_candidates = sorted(
            candidate_info.items(), 
            key=lambda x: (x[1]["call_attempts"], x[1]["last_contact_date"] or ""), 
            reverse=True
        )
        
        return {
            "candidates": [{"candidate_id": cid, **info} for cid, info in sorted_candidates],
            "summary": {
                "total_candidates": len(candidate_info),
                "max_attempts_reached": len([c for c in candidate_info.values() if c["call_attempts"] >= 3 and not c["has_scheduled_interview"]]),
                "interviews_scheduled": len([c for c in candidate_info.values() if c["has_scheduled_interview"]]),
                "can_still_call": len([c for c in candidate_info.values() if c["can_receive_calls"]])
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting candidate call limits: {e}")
        return {"error": str(e)}

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
            "error_code": getattr(call, 'error_code', None),
            "error_message": getattr(call, 'error_message', None),
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