from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.rest import Client as TwilioClient
from openai import OpenAI
import uvicorn
import re
import json
# sqlite3 removed - using MongoDB only
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging
import html
import xml.etree.ElementTree as ET
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from pymongo import MongoClient
    from bson import ObjectId
    MONGODB_AVAILABLE = True
except ImportError:
    logger.warning("PyMongo not available. MongoDB features will be disabled.")
    MONGODB_AVAILABLE = False
    MongoClient = None
    ObjectId = None

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
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
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")

        db = client[db_name]
        coll = db[coll_name]

        docs = list(coll.find())
        candidates = []
        
        for doc in docs:
            # Map shortlistedcandidates collection fields to our expected format
            phone = doc.get("phoneNumber", "")
            # Ensure phone number has country code prefix
            if phone and not phone.startswith("+"):
                phone = f"+91{phone}"  # Assuming Indian numbers based on screenshot
                
            candidate = {
                "candidate_id": str(doc.get("_id")),  # Use MongoDB ObjectId as candidate_id
                "name": doc.get("candidateName", "Unknown"),
                "phone": phone,
                "email": doc.get("candidateEmail", ""),
                "position": doc.get("role", ""),
                "company": doc.get("companyName", ""),
                "call_tracking": doc.get("call_tracking", {})
            }
            # Only add candidates with valid phone numbers
            if candidate["phone"] and len(candidate["phone"]) > 5:
                candidates.append(candidate)
        
        return candidates
        
    except Exception as e:
        logger.warning(f"Could not load candidates from MongoDB: {e}")
        return []


def find_candidate_by_phone(phone_number: str) -> Optional[dict]:
    """Find a candidate by phone number in MongoDB"""
    if not phone_number:
        logger.warning("Cannot find candidate: No phone number provided")
        return None
        
    if not MONGODB_AVAILABLE:
        logger.warning("MongoDB not available, using fallback candidate data")
        # Return a basic candidate structure for fallback
        return {
            "id": "unknown",
            "name": "Candidate", 
            "phone": phone_number,
            "email": "candidate@example.com",
            "position": "Software Developer",
            "company": "Company",
            "call_tracking": {}
        }
        
    try:
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")

        db = client[db_name]
        coll = db[coll_name]

        # Try different phone number variations
        phone_variations = [
            phone_number,
            phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", ""),
            # Handle Indian numbers: +917975091087 -> 7975091087
            phone_number.replace("+91", "") if phone_number.startswith("+91") else phone_number,
            # Handle US numbers: +1234567890 -> 234567890  
            phone_number.replace("+1", "") if phone_number.startswith("+1") else phone_number,
            # Add +91 prefix if not present and looks like Indian number
            f"+91{phone_number}" if not phone_number.startswith("+") and len(phone_number) == 10 else phone_number,
            # Add +1 prefix if not present
            f"+1{phone_number}" if not phone_number.startswith("+") and len(phone_number) >= 10 else phone_number
        ]

        for phone_var in phone_variations:
            doc = coll.find_one({"$or": [
                {"phoneNumber": phone_var},
                {"phone": phone_var}
            ]})
            
            if doc:
                candidate = {
                    "id": str(doc.get("_id")),
                    "name": doc.get("candidateName") or doc.get("name"),
                    "phone": doc.get("phoneNumber") or doc.get("phone"),
                    "email": doc.get("candidateEmail") or doc.get("email"),
                    "position": doc.get("role") or doc.get("position"),
                    "company": doc.get("companyName") or doc.get("company"),
                    "call_tracking": doc.get("call_tracking", {}),
                    "raw": doc  # Store the raw document for reference
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

# MongoDB-only initialization
def init_database():
    """Initialize MongoDB collections for complete call tracking"""
    if not MONGODB_AVAILABLE:
        logger.warning("MongoDB not available. Database initialization skipped.")
        return
        
    try:
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        db = client[db_name]
        
        # Ensure indexes exist for better performance
        candidates_coll = db["candidates"]
        candidates_coll.create_index("phone")
        candidates_coll.create_index("email")
        candidates_coll.create_index("candidate_id", unique=True)  # New unique candidate_id field
        
        # Update existing candidates to have candidate_id field
        candidates_without_id = candidates_coll.find({"candidate_id": {"$exists": False}})
        for candidate in candidates_without_id:
            import uuid
            # Generate unique candidate ID
            candidate_id = f"CAND_{str(uuid.uuid4())[:8].upper()}"
            candidates_coll.update_one(
                {"_id": candidate["_id"]},
                {"$set": {"candidate_id": candidate_id}}
            )
            logger.info(f"Added candidate_id {candidate_id} to existing candidate {candidate.get('name', 'Unknown')}")
        
        # Create other collections with candidate_id references
        conversations_coll = db["conversations"]
        conversations_coll.create_index("candidate_id")
        conversations_coll.create_index("call_sid")
        
        # Create system_logs collection
        logs_coll = db["system_logs"]
        logs_coll.create_index("timestamp")
        
        logger.info("MongoDB collections and indexes initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB: {e}")
    
    # MongoDB only - no SQLite tables needed

def create_candidate_with_id(name: str, phone: str, email: str = None, position: str = None, company: str = None) -> str:
    """Create a new candidate with a unique candidate_id and return the candidate_id"""
    try:
        from pymongo import MongoClient
        import uuid
        
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Generate unique candidate ID
        candidate_id = f"CAND_{str(uuid.uuid4())[:8].upper()}"
        
        # Check if candidate already exists by phone or email
        existing = db.candidates.find_one({"$or": [{"phone": phone}, {"email": email}]}) if email else db.candidates.find_one({"phone": phone})
        
        if existing:
            # If candidate exists but doesn't have candidate_id, add it
            if not existing.get("candidate_id"):
                db.candidates.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"candidate_id": candidate_id}}
                )
                logger.info(f"Added candidate_id {candidate_id} to existing candidate")
                return candidate_id
            else:
                logger.info(f"Candidate already exists with ID {existing['candidate_id']}")
                return existing["candidate_id"]
        
        # Create new candidate with candidate_id
        candidate_doc = {
            "candidate_id": candidate_id,
            "name": name,
            "phone": phone,
            "email": email or "",
            "position": position or "",
            "company": company or "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": "active",
            "call_history": [],
            "interview_status": "not_scheduled"
        }
        
        result = db.candidates.insert_one(candidate_doc)
        client.close()
        
        logger.info(f"Created new candidate with ID {candidate_id}: {name}")
        return candidate_id
        
    except Exception as e:
        logger.error(f"Error creating candidate: {e}")
        return None


def save_call_attempt(candidate_id: str, call_sid: str, phone_number: str, twilio_status: str = None, 
                     call_duration: int = None, error_code: str = None, error_message: str = None, 
                     outcome: str = None, notes: str = None, mongodb_candidate_id: str = None):
    """Save call attempt to MongoDB only"""
    logger.info(f"📝 Saving call attempt to MongoDB for candidate {candidate_id}: {call_sid}")
    # MongoDB tracking is handled by update_candidate_call_tracking function
    # This function is kept for compatibility but uses MongoDB backend
    call_data = {
        "call_sid": call_sid,
        "phone_number": phone_number,
        "initiated_at": datetime.now().isoformat(),
        "twilio_status": twilio_status,
        "call_duration": call_duration,
        "call_direction": "outbound",
        "error_code": error_code,
        "error_message": error_message,
        "outcome": outcome,
        "notes": notes
    }
    return update_candidate_call_tracking(candidate_id, call_data)

def save_conversation_session(session: ConversationSession):
    """Save conversation session to MongoDB only"""
    logger.info(f"💾 Saving conversation session to MongoDB: {session.call_sid}")
    
    if not MONGODB_AVAILABLE:
        logger.warning("MongoDB not available, skipping conversation session save")
        return
        
    try:
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        db = client[db_name]
        
        # Save to conversations collection
        conversations_coll = db["conversations"] 
        
        # Calculate metrics
        total_turns = len(session.turns)
        avg_confidence = sum(turn.confidence_score or 0 for turn in session.turns) / total_turns if total_turns > 0 else 0
        
        candidate = session.candidate or CANDIDATE
        candidate_id = candidate.get('id') if isinstance(candidate, dict) else None
        
        conversation_doc = {
            "call_sid": session.call_sid,
            "candidate_id": candidate_id,
            "candidate_phone": session.candidate_phone,
            "candidate_name": candidate.get('name') if isinstance(candidate, dict) else 'Unknown',
            "position": candidate.get('position') if isinstance(candidate, dict) else 'Unknown Position',
            "company": candidate.get('company') if isinstance(candidate, dict) else 'Unknown Company',
            "start_time": session.start_time,
            "end_time": session.end_time,
            "status": session.status,
            "confirmed_slot": session.confirmed_slot,
            "total_turns": total_turns,
            "ai_confidence_avg": avg_confidence,
            "turns": [
                {
                    "turn_number": turn.turn_number,
                    "timestamp": turn.timestamp,
                    "candidate_input": turn.candidate_input,
                    "ai_response": turn.ai_response,
                    "intent_detected": turn.intent_detected,
                    "confidence_score": turn.confidence_score
                }
                for turn in session.turns
            ],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        conversations_coll.replace_one(
            {"call_sid": session.call_sid},
            conversation_doc,
            upsert=True
        )
        
        logger.info(f"Saved conversation session: {session.call_sid} with {total_turns} turns")
        
    except Exception as e:
        logger.error(f"Error saving conversation session to MongoDB: {e}")

def save_interview_schedule(candidate_id: str, call_sid: str, confirmed_slot: str, email_sent: bool = False, mongodb_candidate_id: str = None):
    """Save interview schedule to MongoDB only - this is handled by update_candidate_interview_scheduled"""
    logger.info(f"📅 Interview schedule handled by MongoDB update function for candidate {candidate_id}: {confirmed_slot}")
    
    # Interview details for MongoDB
    interview_details = {
        "scheduled_slot": confirmed_slot,
        "call_sid": call_sid,
        "email_sent": email_sent,
        "scheduled_at": datetime.now().isoformat()
    }
    
    return update_candidate_interview_scheduled(candidate_id, interview_details)

def log_system_event(level: str, component: str, action: str, details: str, call_sid: str = None, candidate_id: str = None):
    """Log system events for comprehensive tracking to MongoDB"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "log_level": level,
            "component": component,
            "action": action,
            "details": details,
            "call_sid": call_sid,
            "candidate_id": candidate_id
        }
        
        db.system_logs.insert_one(log_entry)
        client.close()
        
    except Exception as e:
        logger.error(f"Error logging system event to MongoDB: {e}")

def check_call_limit(candidate_id: str, max_attempts: int = 3) -> tuple[bool, int, bool]:
    """
    Check if candidate has reached the maximum call limit using MongoDB
    Returns: (can_call, current_attempts, has_scheduled_interview)
    """
    try:
        from pymongo import MongoClient
        
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Find candidate in MongoDB using candidate_id field
        candidate = db.candidates.find_one({"candidate_id": candidate_id})
        
        if not candidate:
            client.close()
            return True, 0, False
            
        # Get current call attempts from candidate record
        call_history = candidate.get('call_history', [])
        current_attempts = len(call_history)
        
        # Check if candidate has already scheduled an interview
        has_scheduled = candidate.get('interview_status') == 'scheduled'
        
        client.close()
        
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
    """Update candidate status in MongoDB only"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Update candidate status in MongoDB using candidate_id field
        result = db.candidates.update_one(
            {"candidate_id": candidate_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now().isoformat()
                }
            },
            upsert=False
        )
        
        client.close()
        
        if notes:
            log_system_event("INFO", "CANDIDATE_SYSTEM", "STATUS_UPDATE", 
                           f"Status updated to {status}: {notes}", 
                           candidate_id=candidate_id)
        
        logger.info(f"Updated candidate {candidate_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Error updating candidate status in MongoDB: {e}")

def load_session_from_db(call_sid: str) -> Optional[ConversationSession]:
    """Load conversation session from MongoDB"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        session_data = db.conversations.find_one({"call_sid": call_sid})
        
        if not session_data:
            client.close()
            return None
        
        # Reconstruct session from MongoDB
        turns = []
        if session_data.get('turns'):
            for turn_dict in session_data['turns']:
                turns.append(ConversationTurn(**turn_dict))
        
        session = ConversationSession(
            call_sid=session_data['call_sid'],
            candidate_phone=session_data['candidate_phone'],
            start_time=session_data['start_time'],
            end_time=session_data.get('end_time'),
            status=session_data['status'],
            confirmed_slot=session_data.get('confirmed_slot'),
            turns=turns
        )
        
        # Set candidate to None - will be loaded from MongoDB when needed
        session.candidate = None
        
        client.close()
        return session
    except Exception as e:
        logger.error(f"Error loading session from MongoDB: {e}")
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
    """Fetch candidate document from MongoDB shortlistedcandidates collection by ObjectId.

    Returns normalized dict or None.
    """
    try:
        try:
            from pymongo import MongoClient
            from bson import ObjectId
        except ImportError:
            logger.warning("pymongo not installed; cannot fetch candidate by id")
            return None

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            logger.debug("MONGODB_URI not configured; cannot fetch candidate by id")
            return None

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        db = client[db_name]
        coll = db[coll_name]

        # Try to find by ObjectId (primary method for shortlistedcandidates collection)
        try:
            query = {"_id": ObjectId(candidate_id)}
            doc = coll.find_one(query)
        except Exception as e:
            logger.warning(f"Invalid ObjectId format: {candidate_id}, error: {e}")
            return None

        if not doc:
            logger.warning(f"No candidate found with ID: {candidate_id}")
            return None

        # Map the shortlistedcandidates collection fields to our expected format
        phone = doc.get("phoneNumber", "")
        # Ensure phone number has country code prefix
        if phone and not phone.startswith("+"):
            phone = f"+91{phone}"  # Add India country code
            
        return {
            "name": doc.get("candidateName", "Unknown"),
            "phone": phone,
            "email": doc.get("candidateEmail", ""),
            "position": doc.get("role", ""),
            "company": doc.get("companyName", ""),
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
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        db = client[db_name]
        coll = db[coll_name]

        # Try to find candidate by ObjectId (primary method for shortlistedcandidates)
        try:
            from bson import ObjectId
            query = {"_id": ObjectId(candidate_id)}
            doc = coll.find_one(query)
        except Exception as e:
            logger.warning(f"Invalid candidate_id format: {candidate_id}, error: {e}")
            return False

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
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
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

        logger.info(f"📝 Executing MongoDB update with query: {query}")
        logger.info(f"📝 Update data: {update_data}")
        
        result = coll.update_one(query, update_data)
        
        logger.info(f"📊 MongoDB update result - matched: {result.matched_count}, modified: {result.modified_count}")
        
        if result.modified_count > 0:
            logger.info(f"✅ Successfully updated interview details for candidate {candidate_id}: {interview_details.get('scheduled_slot')}")
            
            # Verify the update by fetching the document
            doc = coll.find_one(query)
            if doc:
                interview_status = doc.get('call_tracking', {}).get('status', 'unknown')
                scheduled_slot = doc.get('call_tracking', {}).get('interview_details', {}).get('scheduled_slot', 'none')
                logger.info(f"✅ Verification - Status: {interview_status}, Slot: {scheduled_slot}")
            return True
        else:
            if result.matched_count == 0:
                logger.error(f"❌ No document found with candidate_id: {candidate_id}")
                logger.error(f"❌ Query used: {query}")
                
                # Try to find any document that might match
                test_docs = list(coll.find().limit(3))
                if test_docs:
                    sample_doc = test_docs[0]
                    logger.error(f"📄 Sample document structure: _id={sample_doc.get('_id')}, candidateName={sample_doc.get('candidateName')}")
                else:
                    logger.error(f"📄 Collection appears to be empty")
            else:
                logger.error(f"❌ Document found but update failed. Matched: {result.matched_count}")
                doc = coll.find_one(query)
                if doc:
                    logger.error(f"❌ Current call_tracking: {doc.get('call_tracking')}")
            return False

    except Exception as e:
        logger.error(f"Error updating interview details for candidate {candidate_id}: {e}")
        return False

def get_candidate_scheduling_status(candidate_id: str) -> dict:
    """Get comprehensive scheduling status for a candidate from MongoDB"""
    try:
        try:
            from pymongo import MongoClient
            from bson import ObjectId
        except ImportError:
            return {"scheduling_status": "unknown", "reason": "MongoDB not available"}

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return {"scheduling_status": "unknown", "reason": "MongoDB not configured"}

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        db = client[db_name]
        coll = db[coll_name]

        # Find candidate by ObjectId
        try:
            doc = coll.find_one({"_id": ObjectId(candidate_id)})
        except Exception as e:
            return {"scheduling_status": "error", "reason": f"Invalid candidate ID: {e}"}

        if not doc:
            return {"scheduling_status": "not_found", "reason": "Candidate not found"}

        # Ensure doc is a dictionary before proceeding
        if not isinstance(doc, dict):
            return {"scheduling_status": "error", "reason": "Invalid candidate document format"}

        # Extract scheduling information with safe access
        interview_status = doc.get("interviewStatus", "not_scheduled") if doc else "not_scheduled"
        scheduled_date = doc.get("scheduledInterviewDate", None) if doc else None
        
        # Check if there's call tracking data with interview details
        call_tracking = doc.get("call_tracking", {}) if doc else {}
        call_tracking = call_tracking if isinstance(call_tracking, dict) else {}
        
        interview_details = call_tracking.get("interview_details", {}) if call_tracking else {}
        interview_details = interview_details if isinstance(interview_details, dict) else {}
        
        email_status = interview_details.get("email_status", {}) if interview_details else {}
        email_status = email_status if isinstance(email_status, dict) else {}
        
        scheduling_status = {
            "interview_status": interview_status,
            "scheduled_date": scheduled_date,
            "interview_slot_confirmed": interview_details.get("confirmed_slot", None),
            "interview_details": {
                "slot": interview_details.get("confirmed_slot", None),
                "scheduled_at": interview_details.get("scheduled_at", None),
                "confirmation_method": interview_details.get("confirmation_method", None)
            },
            "email_notifications": {
                "confirmation_sent": email_status.get("sent", False) if email_status else False,
                "email_status": email_status.get("status", "not_sent") if email_status else "not_sent",
                "sent_at": email_status.get("sent_at", None) if email_status else None,
                "recipient_email": email_status.get("recipient", None) if email_status else None,
                "delivery_status": email_status.get("delivery_status", "unknown") if email_status else "unknown"
            },
            "conversation_status": call_tracking.get("conversation_status", "not_started"),
            "last_interaction": call_tracking.get("last_contact_date", None)
        }

        client.close()
        return scheduling_status

    except Exception as e:
        logger.error(f"Error getting scheduling status for candidate {candidate_id}: {e}")
        return {"scheduling_status": "error", "reason": str(e)}

def update_candidate_email_status(candidate_id: str, email_status: dict) -> bool:
    """Update candidate document with email notification status"""
    try:
        try:
            from pymongo import MongoClient
            from bson import ObjectId
        except ImportError:
            logger.warning("pymongo not installed; cannot update email status")
            return False

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return False

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        db = client[db_name]
        coll = db[coll_name]

        # Update candidate with email status - ensure parent structure exists
        try:
            # Try to use ObjectId first
            try:
                query = {"_id": ObjectId(candidate_id)}
            except Exception as oid_error:
                # If ObjectId fails, try alternative queries
                logger.warning(f"Invalid ObjectId {candidate_id}, trying alternative lookup: {oid_error}")
                query = {"$or": [
                    {"id": candidate_id},
                    {"candidateEmail": candidate_id},
                    {"phoneNumber": candidate_id.replace("+91", "")},
                    {"phoneNumber": candidate_id}
                ]}
            
            # First, initialize the interview_details structure if it's null or doesn't exist
            init_result = coll.update_one(
                {
                    **query,
                    "$or": [
                        {"call_tracking.interview_details": {"$exists": False}},
                        {"call_tracking.interview_details": None}
                    ]
                },
                {
                    "$set": {
                        "call_tracking.interview_details": {},
                        "call_tracking.created_at": datetime.now().isoformat()
                    }
                }
            )
            
            # Then update the email status
            result = coll.update_one(
                query,
                {
                    "$set": {
                        "call_tracking.interview_details.email_status": email_status,
                        "call_tracking.updated_at": datetime.now().isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Successfully updated email status for candidate {candidate_id}")
            else:
                logger.warning(f"No candidate document updated for ID: {candidate_id}")
                
            client.close()
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating email status: {e}, full error: {e}")
            client.close()
            return False

    except Exception as e:
        logger.error(f"Error updating candidate email status: {e}")
        return False

def update_interview_status(candidate_id: str, status: str, confirmed_slot: str = None, call_sid: str = None) -> bool:
    """Update the main interviewStatus field in MongoDB document"""
    try:
        try:
            from pymongo import MongoClient
            from bson import ObjectId
        except ImportError:
            logger.warning("pymongo not installed; cannot update interview status")
            return False

        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            return False

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        db = client[db_name]
        coll = db[coll_name]

        # Build update data
        update_data = {
            "interviewStatus": status,
            "updatedAt": datetime.now().isoformat()
        }
        
        # Add optional fields if provided
        if confirmed_slot:
            update_data["scheduledInterviewDate"] = confirmed_slot
        if call_sid:
            update_data["lastCallSid"] = call_sid
            
        # Update using ObjectId
        try:
            query = {"_id": ObjectId(candidate_id)}
            logger.info(f"🔄 Updating interview status for ObjectId {candidate_id}: {status}")
        except Exception as oid_error:
            logger.error(f"Invalid ObjectId {candidate_id}: {oid_error}")
            return False

        result = coll.update_one(
            query,
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"✅ Successfully updated interview status for {candidate_id}: {status}")
            if confirmed_slot:
                logger.info(f"✅ Scheduled interview slot: {confirmed_slot}")
            client.close()
            return True
        else:
            logger.error(f"❌ No candidate document found for ID: {candidate_id}")
            client.close()
            return False
            
    except Exception as e:
        logger.error(f"Error updating interview status for {candidate_id}: {e}")
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
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
        db = client[db_name]
        coll = db[coll_name]

        # Find candidate by ObjectId
        try:
            from bson import ObjectId
            doc = coll.find_one({"_id": ObjectId(candidate_id)})
        except Exception as e:
            logger.warning(f"Invalid candidate_id format: {candidate_id}, error: {e}")
            return {"can_call": False, "reason": "Invalid candidate ID format", "attempts": 0}

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
    logger.info(f"Sending interview confirmation email for call {call_sid}")
    logger.info(f"Candidate: {candidate.get('name', 'Unknown')} ({candidate.get('email', 'No email')})")
    logger.info(f"Confirmed slot: {confirmed_slot}")
    
    if not all([SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL]):
        logger.warning("SMTP credentials not configured. Cannot send confirmation email.")
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
        
        # Send email using HTTP-based APIs only (SMTP blocked on Render)
        email_sent = False
        email_service_used = None
        
        # Try Resend API first (most reliable on Render)
        resend_api_key = config("RESEND_API_KEY", default=None)
        if resend_api_key and not email_sent:
            try:
                logger.info(f"🚀 Attempting Resend API to {candidate_email}")
                
                resend_url = "https://api.resend.com/emails"
                # Use your verified domain from the Node.js code
                from_email = config("RESEND_FROM_EMAIL", default="JobPortal@notezy.online")
                
                resend_payload = {
                    "from": f"Sarah Johnson - LinkUp Talent Team <{from_email}>",
                    "to": [candidate_email],
                    "subject": subject,
                    "html": html_body,
                    "text": text_body,
                    "headers": {
                        "X-Entity-Ref-ID": call_sid,
                        "Reply-To": SENDER_EMAIL
                    },
                    "tags": [
                        {"name": "category", "value": "interview-confirmation"},
                        {"name": "candidate_name", "value": candidate_name.replace(" ", "_")},
                        {"name": "call_sid", "value": call_sid}
                    ]
                }
                
                resend_headers = {
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json"
                }
                
                response = requests.post(
                    resend_url, 
                    json=resend_payload, 
                    headers=resend_headers, 
                    timeout=15
                )
                
                if response.status_code in (200, 201):
                    response_data = response.json()
                    email_id = response_data.get('id', 'unknown')
                    logger.info(f"✅ Resend API SUCCESS: Email sent to {candidate_email} (ID: {email_id})")
                    email_sent = True
                    email_service_used = "Resend"
                else:
                    logger.error(f"❌ Resend API error: {response.status_code} - {response.text}")
                    
            except Exception as resend_error:
                logger.error(f"💥 Resend API failed: {resend_error}")
        
        # Fallback to SendGrid if Resend failed
        if not email_sent:
            sendgrid_api_key = config("SENDGRID_API_KEY", default=None)
            if sendgrid_api_key:
                try:
                    logger.info(f"🔄 Trying SendGrid API fallback to {candidate_email}")
                    
                    sendgrid_url = "https://api.sendgrid.com/v3/mail/send"
                    sendgrid_payload = {
                        "personalizations": [
                            {
                                "to": [{"email": candidate_email, "name": candidate_name}],
                                "subject": subject
                            }
                        ],
                        "from": {"email": SENDER_EMAIL, "name": "Sarah Johnson - LinkUp Talent Team"},
                        "reply_to": {"email": SENDER_EMAIL},
                        "content": [
                            {"type": "text/plain", "value": text_body},
                            {"type": "text/html", "value": html_body}
                        ],
                        "tracking_settings": {
                            "click_tracking": {"enable": True},
                            "open_tracking": {"enable": True}
                        },
                        "categories": ["interview-confirmation", "ai-scheduler"]
                    }
                    
                    sendgrid_headers = {
                        "Authorization": f"Bearer {sendgrid_api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    response = requests.post(
                        sendgrid_url, 
                        json=sendgrid_payload, 
                        headers=sendgrid_headers, 
                        timeout=15
                    )
                    
                    if response.status_code in (200, 202):
                        logger.info(f"✅ SendGrid API SUCCESS: Email sent to {candidate_email}")
                        email_sent = True
                        email_service_used = "SendGrid"
                    else:
                        logger.error(f"❌ SendGrid API error: {response.status_code} - {response.text}")
                        
                except Exception as sendgrid_error:
                    logger.error(f"💥 SendGrid API failed: {sendgrid_error}")
            else:
                logger.warning("📧 SENDGRID_API_KEY not configured, skipping SendGrid")
        
        # Final fallback - log email for manual sending (SMTP not available on Render)
        if not email_sent:
            logger.warning("⚠️  All HTTP email providers failed - logging email for manual processing")
            logger.warning(f"📧 EMAIL LOG for {candidate_email}:")
            logger.warning(f"   Subject: {subject}")
            logger.warning(f"   Scheduled Slot: {confirmed_slot}")
            logger.warning(f"   Call SID: {call_sid}")
            logger.warning(f"   Content Preview: {text_body[:200]}...")
            logger.warning(f"   Full HTML Length: {len(html_body)} chars")
            
            # Mark as logged for manual follow-up
            email_sent = "logged"
            email_service_used = "Manual Log"
        
        # Process email results and update database
        if email_sent == True:
            logger.info(f"✅ Email successfully sent to {candidate_email} via {email_service_used}")
            email_status = {
                "sent": True,
                "status": "delivered",
                "sent_at": datetime.now().isoformat(),
                "recipient": candidate_email,
                "subject": subject,
                "confirmed_slot": confirmed_slot,
                "delivery_status": f"sent_via_{email_service_used.lower()}",
                "call_sid": call_sid,
                "service": email_service_used
            }
        elif email_sent == "logged":
            logger.warning(f"⚠️ Email logged for manual processing: {candidate_email}")
            email_status = {
                "sent": False,
                "status": "logged_for_manual_processing",
                "sent_at": datetime.now().isoformat(),
                "recipient": candidate_email,
                "subject": subject,
                "confirmed_slot": confirmed_slot,
                "delivery_status": "manual_follow_up_required",
                "call_sid": call_sid,
                "service": "Manual Log",
                "note": "All API providers failed - email logged for manual sending"
            }
        else:
            logger.error(f"❌ All email delivery methods failed for {candidate_email}")
            email_status = {
                "sent": False,
                "status": "failed_all_providers",
                "sent_at": datetime.now().isoformat(),
                "recipient": candidate_email,
                "subject": subject,
                "confirmed_slot": confirmed_slot,
                "delivery_status": "complete_failure",
                "call_sid": call_sid,
                "error": "All HTTP email providers and logging failed"
            }
        
        # Update candidate document with email status (success or failure)
        candidate_raw = candidate.get('raw') if candidate else None
        candidate_id_for_update = candidate_raw.get('_id') if candidate_raw else candidate.get('id') if candidate else None
        if candidate_id_for_update:
            try:
                update_candidate_email_status(candidate_id_for_update, email_status)
                logger.info(f"📝 Updated candidate {candidate_id_for_update} email status: {email_status['status']}")
            except Exception as update_error:
                logger.error(f"Failed to update email status in database: {update_error}")
        
        # Return appropriate response based on email delivery status
        if email_sent == True:
            return {
                "email_sent": True,
                "status": "success",
                "recipient": candidate_email,
                "sent_at": datetime.now().isoformat(),
                "subject": subject,
                "confirmed_slot": confirmed_slot,
                "service": email_service_used
            }
        elif email_sent == "logged":
            return {
                "email_sent": False,  # False because not actually delivered
                "status": "logged_for_manual",
                "recipient": candidate_email,
                "sent_at": datetime.now().isoformat(),
                "subject": subject,
                "confirmed_slot": confirmed_slot,
                "note": "Email logged for manual follow-up"
            }
        else:
            return {
                "email_sent": False,
                "status": "failed",
                "recipient": candidate_email,
                "sent_at": datetime.now().isoformat(),
                "subject": subject,
                "confirmed_slot": confirmed_slot,
                "error": "All email providers failed"
            }
        
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")
        
        # Update candidate document with failure status
        email_status = {
            "sent": False,
            "status": "failed",
            "attempted_at": datetime.now().isoformat(),
            "recipient": candidate_email,
            "error": str(e),
            "delivery_status": "failed",
            "call_sid": call_sid
        }
        
        # Update candidate in MongoDB with email failure status
        candidate_raw = candidate.get('raw') if candidate else None
        candidate_id_for_update = candidate_raw.get('_id') if candidate_raw else candidate.get('id') if candidate else None
        if candidate_id_for_update:
            update_candidate_email_status(candidate_id_for_update, email_status)
        
        return {
            "email_sent": False,
            "status": "failed",
            "error": str(e),
            "attempted_at": datetime.now().isoformat(),
            "recipient": candidate_email
        }

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

@app.post("/test-json")
async def test_json_parsing(request: Request):
    """Test JSON parsing for debugging"""
    try:
        body = await request.json()
        return {
            "status": "success", 
            "message": "JSON parsed successfully",
            "received_data": body,
            "candidate_id": body.get("candidate_id", "NOT_PROVIDED")
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"JSON parsing failed: {str(e)}",
            "help": "Send JSON like: {\"candidate_id\": \"your_id_here\"}"
        }

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
        
        logger.info(f"Call webhook - CallSid: {call_sid}, From: {from_number}, To: {to_number}, Status: {call_status}")
        
        # Determine if this is an outbound call (from our Twilio number) or inbound call
        candidate_phone = None
        if from_number == TWILIO_PHONE_NUMBER:
            # Outbound call - we called the candidate, so candidate phone is 'To'
            candidate_phone = to_number
            logger.info(f"Outbound call detected - candidate phone: {candidate_phone}")
        else:
            # Inbound call - candidate called us, so candidate phone is 'From'  
            candidate_phone = from_number
            logger.info(f"Inbound call detected - candidate phone: {candidate_phone}")
        
        # Find candidate by phone number
        candidate = None
        try:
            candidate = find_candidate_by_phone(candidate_phone)
            if candidate:
                logger.info(f"Found candidate: {candidate.get('name')} ({candidate.get('phone')})")
            else:
                logger.warning(f"Could not find candidate for phone number: {candidate_phone}")
        except Exception as e:
            logger.error(f"Error finding candidate by phone {candidate_phone}: {e}")
        
        # Create or get session for this call with candidate info
        try:
            session = get_or_create_session(call_sid, candidate_phone, candidate)
        except Exception as e:
            logger.error(f"Error creating session for call {call_sid}: {e}")
            # Use a basic session if creation fails
            session = ConversationSession(
                call_sid=call_sid,
                candidate_phone=from_number,
                start_time=datetime.now().isoformat(),
                turns=[],
                candidate=candidate
            )
        
        # Get appropriate greeting based on candidate data
        try:
            greeting = get_ai_greeting(session.candidate)
        except Exception as e:
            logger.error(f"Error generating greeting: {e}")
            greeting = "Hello! This is Sarah from the talent acquisition team. I'm calling to schedule your interview."
        
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
            try:
                # Try to load from database first
                session = load_session_from_db(call_sid)
                if session:
                    conversation_sessions[call_sid] = session
                else:
                    # Find candidate by phone number to include in session
                    caller_phone = form_data.get("From", "")
                    candidate = None
                    try:
                        candidate = find_candidate_by_phone(caller_phone)
                    except Exception as e:
                        logger.error(f"Error finding candidate by phone: {e}")
                    session = get_or_create_session(call_sid, caller_phone, candidate)
            except Exception as e:
                logger.error(f"Error creating/loading session: {e}")
                # Create minimal session if all else fails
                session = ConversationSession(
                    call_sid=call_sid,
                    candidate_phone=form_data.get("From", ""),
                    start_time=datetime.now().isoformat(),
                    turns=[],
                    candidate=None
                )
        
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
            logger.info(f"Processing scheduling stage - Intent: {intent}, Confidence: {intent_confidence}")
            if intent == "confirmation" and intent_confidence > 0.6:
                # Look for specific time mentioned
                mentioned_slot = find_mentioned_time_slot(speech_result, TIME_SLOTS)
                if mentioned_slot:
                    try:
                        confirmed_slot = mentioned_slot
                        session.confirmed_slot = confirmed_slot
                        session.status = "completed"
                        session.end_time = datetime.now().isoformat()
                        
                        # Get candidate info for comprehensive tracking
                        candidate = session.candidate or CANDIDATE
                        candidate_id = None
                        
                        try:
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
                                candidate_id = candidate.get('email', 'unknown') if candidate else 'unknown'
                        except Exception as candidate_error:
                            logger.error(f"Error processing candidate info: {candidate_error}")
                            candidate_id = 'unknown'
                        
                        logger.info(f"Processing interview confirmation for candidate ID: {candidate_id}")
                        
                        # Send confirmation email (don't let this block the confirmation)
                        email_sent = False
                        try:
                            if candidate and candidate.get('email'):
                                email_result = await send_interview_confirmation_email(candidate, confirmed_slot, call_sid)
                                # Handle both dictionary and boolean returns
                                email_sent = email_result.get("email_sent", False) if isinstance(email_result, dict) else bool(email_result)
                            else:
                                logger.warning("No candidate email available for confirmation")
                        except Exception as email_error:
                            logger.error(f"Failed to send confirmation email: {email_error}")
                            email_sent = False
                        
                        # Save interview schedule to MongoDB (don't let this block the confirmation)
                        try:
                            interview_details = {
                                "confirmed_slot": confirmed_slot,
                                "call_sid": call_sid,
                                "email_status": email_sent if isinstance(email_sent, dict) else {
                                    "sent": bool(email_sent),
                                    "status": "sent" if email_sent else "failed",
                                    "sent_at": datetime.now().isoformat() if email_sent else None
                                },
                                "scheduled_at": datetime.now().isoformat(),
                                "confirmation_method": "phone_call",
                                "interview_status": "scheduled",
                                "scheduling_completed": True,
                                "candidate_confirmed": True
                            }
                            if candidate_id and candidate_id != 'unknown':
                                update_candidate_interview_scheduled(candidate_id, interview_details)
                                logger.info(f"Updated MongoDB with interview details for candidate {candidate_id}")
                                
                                # Update the main interview status field
                                update_interview_status(candidate_id, "interview_scheduled", confirmed_slot, call_sid)
                                logger.info(f"✅ Updated interview status to 'interview_scheduled' for candidate {candidate_id}")
                            else:
                                logger.warning("Could not update MongoDB - no valid candidate ID")
                        except Exception as db_error:
                            logger.error(f"Failed to update MongoDB: {db_error}")
                            # Continue anyway - the confirmation can still work
                    except Exception as mongo_error:
                        logger.error(f"Failed to update MongoDB: {mongo_error}")
                    
                    # Also save to SQLite database
                    try:
                        save_interview_schedule(
                            candidate_id=candidate_id,
                            mongodb_candidate_id=candidate_id,  # MongoDB ID stored separately
                            call_sid=call_sid,
                            confirmed_slot=confirmed_slot,
                            email_sent=email_sent
                        )
                        logger.info(f"📝 Saved interview schedule to SQLite for candidate {candidate_id}")
                    except Exception as sqlite_error:
                        logger.error(f"Failed to save interview schedule to SQLite: {sqlite_error}")
                    
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
                logger.info(f"🗓️ Day mentioned in speech: '{speech_result}' - Looking for time slot match")
                mentioned_slot = find_mentioned_time_slot(speech_result, TIME_SLOTS)
                logger.info(f"🎯 Found time slot match: {mentioned_slot}")
                if mentioned_slot:
                    session.confirmed_slot = mentioned_slot
                    session.status = "completed"
                    session.end_time = datetime.now().isoformat()
                    
                    # Get candidate info for comprehensive tracking
                    candidate = session.candidate or CANDIDATE
                    candidate_id = None
                    
                    # Try to get MongoDB ObjectId for database operations
                    if session.candidate and isinstance(session.candidate, dict):
                        # Use the raw document _id if available
                        raw_doc = session.candidate.get('raw')
                        if raw_doc and raw_doc.get('_id'):
                            candidate_id = str(raw_doc.get('_id'))
                            logger.info(f"✅ Using existing candidate ObjectId: {candidate_id}")
                        elif session.candidate.get('id'):
                            candidate_id = session.candidate.get('id')
                            logger.info(f"✅ Using candidate ID from session: {candidate_id}")
                    
                    # If no candidate ID yet, try to find by phone
                    if not candidate_id and session.candidate_phone:
                        logger.info(f"🔍 Looking up candidate by phone: {session.candidate_phone}")
                        found_candidate = find_candidate_by_phone(session.candidate_phone)
                        if found_candidate:
                            candidate_id = found_candidate.get('id')  # This is the MongoDB ObjectId as string
                            session.candidate = found_candidate  # Update session with found candidate
                            candidate = found_candidate  # Update candidate for email
                            logger.info(f"✅ Found candidate by phone - ID: {candidate_id}, Name: {found_candidate.get('name')}")
                        else:
                            logger.warning(f"❌ No candidate found for phone: {session.candidate_phone}")
                            candidate_id = f"phone_{session.candidate_phone}"
                    
                    # Final fallback
                    if not candidate_id:
                        candidate_id = candidate.get('email', 'unknown') if candidate else 'unknown'
                        logger.warning(f"⚠️ Using fallback candidate ID: {candidate_id}")
                    
                    logger.info(f"Processing interview confirmation for candidate ID: {candidate_id}")
                    
                    # Send confirmation email
                    try:
                        email_result = await send_interview_confirmation_email(candidate, mentioned_slot, call_sid)
                        # Handle both dictionary and boolean returns
                        email_sent = email_result.get("email_sent", False) if isinstance(email_result, dict) else bool(email_result)
                    except Exception as email_error:
                        logger.error(f"Failed to send confirmation email: {email_error}")
                        email_sent = False
                    
                    # Save interview schedule to MongoDB
                    logger.info(f"💾 Saving interview schedule to MongoDB...")
                    logger.info(f"   Candidate ID: {candidate_id}")
                    logger.info(f"   Scheduled Slot: {mentioned_slot}")
                    logger.info(f"   Call SID: {call_sid}")
                    
                    try:
                        interview_details = {
                            "scheduled_slot": mentioned_slot,
                            "call_sid": call_sid,
                            "email_sent": email_sent,
                            "scheduled_at": datetime.now().isoformat()
                        }
                        
                        update_result = update_candidate_interview_scheduled(candidate_id, interview_details)
                        if update_result:
                            logger.info(f"✅ Successfully saved interview schedule to MongoDB")
                            
                            # Update the main interview status field
                            update_interview_status(candidate_id, "interview_scheduled", mentioned_slot, call_sid)
                            logger.info(f"✅ Updated interview status to 'interview_scheduled' for candidate {candidate_id}")
                        else:
                            logger.error(f"❌ Failed to save interview schedule - update_result: {update_result}")
                            
                    except Exception as mongo_error:
                        logger.error(f"💥 MongoDB update failed with exception: {mongo_error}")
                        import traceback
                        logger.error(f"Full traceback: {traceback.format_exc()}")
                    
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
            
            # Update interview status to reflect call ended without scheduling
            if session.candidate and isinstance(session.candidate, dict):
                candidate_id = session.candidate.get('id')
                if candidate_id:
                    update_interview_status(candidate_id, "call_completed_no_scheduling", None, call_sid)
                    logger.info(f"📞 Updated status: call completed without scheduling for {candidate_id}")
        
        # Prevent infinite loops - max 6 turns total
        if turn_number > 6:
            ai_response = "Thank you so much for your time. We'll follow up by email with scheduling details. Have a wonderful day!"
            session.status = "failed" if not session.confirmed_slot else "completed"
            session.end_time = datetime.now().isoformat()
            next_action = "end_call"
            
            # Update interview status based on whether scheduling was completed
            if session.candidate and isinstance(session.candidate, dict):
                candidate_id = session.candidate.get('id')
                if candidate_id:
                    if session.confirmed_slot:
                        # This should have been handled already, but just in case
                        update_interview_status(candidate_id, "interview_scheduled", session.confirmed_slot, call_sid)
                        logger.info(f"✅ Max turns reached - interview was scheduled for {candidate_id}")
                    else:
                        update_interview_status(candidate_id, "call_timeout", None, call_sid)
                        logger.info(f"⏰ Max turns reached - call timed out without scheduling for {candidate_id}")
        
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
    """Make actual Twilio call with comprehensive validation and proper MongoDB integration"""
    # Read candidate_id from JSON body - this is required
    try:
        body = await request.json()
        candidate_id = body.get("candidate_id") if isinstance(body, dict) else None
        logger.info(f"Processing call request for candidate_id: {candidate_id}")
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        return {
            "status": "error",
            "message": "Invalid JSON in request body. Please provide candidate_id."
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
    
    # Candidate ID is required for proper tracking
    if not candidate_id:
        return {
            "status": "error",
            "message": "candidate_id is required. Please provide a valid candidate ID from MongoDB."
        }

    # Resolve candidate details from MongoDB
    candidate_info = fetch_candidate_by_id(candidate_id)
    
    if not candidate_info:
        return {
            "status": "error",
            "message": f"Candidate not found with ID: {candidate_id}. Please check the candidate exists in MongoDB."
        }

    if not candidate_info.get("phone") or candidate_info.get("phone") == "+1234567890":
        return {
            "status": "error",
            "message": f"Invalid phone number for candidate {candidate_id}: {candidate_info.get('phone')}. Please update the candidate's phone number."
        }
        
    logger.info(f"Found candidate: {candidate_info.get('name')} ({candidate_info.get('phone')})")
    
    # Check call limits from MongoDB using the actual MongoDB document ID
    call_status = get_candidate_call_status(candidate_id)
    
    if not call_status["can_call"]:
        logger.warning(f"Call blocked for {candidate_info.get('name')}: {call_status['reason']}")
        return {
            "status": "error",
            "message": f"Cannot make call: {call_status['reason']}",
            "candidate": candidate_info.get("name"),
            "attempts": call_status["attempts"],
            "call_limit_reached": True,
            "details": call_status
        }
        
    logger.info(f"Call allowed for {candidate_info.get('name')} - Attempt {call_status['attempts'] + 1}/3")
    
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
        logger.info(f"Initiating call to {candidate_info.get('phone')}")
        logger.info(f"Using webhook: {webhook_url}")
        logger.info(f"Using candidate: {candidate_info.get('email') or candidate_info.get('name')}")
        
        # Initialize Twilio client
        try:
            client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            # Validate credentials by fetching account info
            account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
            logger.info(f"Twilio account validated: {account.friendly_name}")
        except Exception as cred_error:
            logger.error(f"Twilio credential validation failed: {cred_error}")
            return {
                "status": "error",
                "message": f"Invalid Twilio credentials: {str(cred_error)}"
            }
        
        # Log call initiation
        logger.info(f"Initiating call to {candidate_info.get('phone')} for {candidate_info.get('name')} (Attempt {call_status['attempts'] + 1}/3)")
        log_system_event("INFO", "CALL_SYSTEM", "CALL_INITIATED", 
                        f"Initiating call to {candidate_info.get('phone')} for {candidate_info.get('name')} (Attempt {call_status['attempts'] + 1}/3)", 
                        candidate_id=candidate_id)
        
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
        logger.info(f"Updating MongoDB call tracking for candidate {candidate_id}")
        update_candidate_call_tracking(candidate_id, call_data)
        
        # Also save to SQLite database with MongoDB candidate ID
        save_call_attempt(
            candidate_id=candidate_id,  # Use MongoDB ID as primary identifier
            mongodb_candidate_id=candidate_id,  # Store MongoDB ID separately
            call_sid=call.sid,
            phone_number=candidate_info.get('phone'),
            twilio_status=call.status,
            outcome="initiated",
            notes=f"Call initiated to {candidate_info.get('name')} for {candidate_info.get('position')} position"
        )

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
        # Update call record without incrementing attempts
        
        if updated_call.status == 'failed':
            error_code = getattr(updated_call, 'error_code', 'Unknown')
            error_message = getattr(updated_call, 'error_message', 'Unknown error')
            
            logger.error(f"Call failed. Error code: {error_code}")
            logger.error(f"Error message: {error_message}")
            
            # Update MongoDB with failure
            failure_data = {
                "call_sid": call.sid,
                "initiated_at": datetime.now().isoformat(),
                "twilio_status": "failed",
                "outcome": "failed",
                "error_code": error_code,
                "error_message": error_message,
                "notes": f"Call failed: {error_message}"
            }
            update_candidate_call_tracking(candidate_id, failure_data)
            
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

        # Get current scheduling status from the candidate document
        try:
            scheduling_status = get_candidate_scheduling_status(candidate_id)
        except Exception as e:
            logger.error(f"Failed to get scheduling status: {e}")
            scheduling_status = {"scheduling_status": "error", "reason": str(e)}
        
        return {
            "status": "success",
            "message": f"Call initiated to {candidate_info.get('phone')}",
            "call_sid": call.sid,
            "call_status": updated_call.status,
            "webhook_url": webhook_url,
            "candidate": {
                "id": candidate_id,
                "name": candidate_info.get("name"),
                "phone": candidate_info.get("phone"),
                "email": candidate_info.get("email"),
                "position": candidate_info.get("position"),
                "company": candidate_info.get("company")
            },
            "initial_status": call.status,
            "scheduling_status": scheduling_status,
            "call_tracking": {
                "total_attempts": call_status["attempts"] + 1,
                "max_attempts": 3,
                "can_call_again": call_status["attempts"] + 1 < 3
            }
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Call failed: {error_msg}")
        
        # Provide specific error guidance
        if "not a valid phone number" in error_msg.lower():
            return {
                "status": "error",
                "message": f"Invalid phone number format: {candidate_info.get('phone')}. Use format: +1234567890"
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
        db_name = config("MONGODB_DB", default="test")
        coll_name = config("MONGODB_COLLECTION", default="shortlistedcandidates")
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
            
            # Map shortlistedcandidates fields to our expected format
            phone = doc.get("phoneNumber", "")
            # Ensure phone number has country code prefix
            if phone and not phone.startswith("+"):
                phone = f"+91{phone}"  # Assuming Indian numbers
            
            # Extract basic info
            candidate = {
                "id": str(doc.get("_id")),
                "name": doc.get("candidateName", "Unknown"),
                "phone": phone,
                "email": doc.get("candidateEmail", ""),
                "position": doc.get("role", ""),
                "company": doc.get("companyName", "")
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
        # Get candidate ID from request body with better error handling
        try:
            body = await request.json()
        except Exception as json_error:
            return {
                "status": "error",
                "message": f"Invalid JSON in request body: {str(json_error)}. Please send valid JSON with candidate_id field."
            }
        
        candidate_id = body.get("candidate_id")
        
        if not candidate_id:
            return {
                "status": "error",
                "message": "candidate_id is required in JSON body. Example: {\"candidate_id\": \"CAND_12345678\"}"
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
        
        # Validate credentials
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

@app.get("/candidates")
async def get_candidates():
    """Get all available candidates for selection"""
    try:
        candidates = get_all_candidates_from_mongo()
        if not candidates:
            return {"status": "error", "message": "No candidates found", "candidates": []}
        
        # Format candidates for frontend
        formatted_candidates = []
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            call_status = get_candidate_call_status(candidate_id) if candidate_id else {"can_call": False}
            
            candidate_info = {
                "id": candidate_id,
                "name": candidate.get("name", "Unknown"),
                "phone": candidate.get("phone", "Unknown"),
                "email": candidate.get("email", "Unknown"),
                "position": candidate.get("position", "Unknown"),
                "company": candidate.get("company", "Unknown"),
                "call_status": call_status
            }
            formatted_candidates.append(candidate_info)
        
        return {
            "status": "success",
            "candidates": formatted_candidates,
            "total": len(formatted_candidates)
        }
    
    except Exception as e:
        logger.error(f"Failed to get candidates: {e}")
        return {"status": "error", "message": str(e), "candidates": []}

@app.post("/call-candidate/{candidate_id}")
async def call_specific_candidate(candidate_id: str):
    """Make a call to a specific candidate by ID"""
    try:
        # Validate candidate exists
        candidate = fetch_candidate_by_id(candidate_id)
        if not candidate:
            return {"status": "error", "message": f"Candidate with ID {candidate_id} not found"}
        
        # Check if candidate can receive calls
        call_status = get_candidate_call_status(candidate_id)
        if not call_status["can_call"]:
            return {
                "status": "error", 
                "message": f"Cannot call candidate: {call_status['reason']}"
            }
        
        logger.info(f"🎯 Making call to selected candidate: {candidate.get('name', 'Unknown')} (ID: {candidate_id})")
        
        # Create a proper mock request for make_actual_call function
        class MockRequest:
            def __init__(self, json_data):
                self._json_data = json_data
                
            async def json(self):
                return self._json_data
        
        try:
            mock_request = MockRequest({"candidate_id": candidate_id})
            result = await make_actual_call(mock_request)
        except Exception as e:
            result = {"status": "error", "message": f"Function call failed: {str(e)}"}
        
        return {
            "status": result.get("status", "success"),
            "message": f"Call initiated for {candidate.get('name', 'Unknown')}",
            "candidate_id": candidate_id,
            "candidate_name": candidate.get('name', 'Unknown'),
            "candidate_phone": candidate.get('phone', 'Unknown'),
            "call_result": result
        }
    
    except Exception as e:
        logger.error(f"Call to candidate {candidate_id} failed: {e}")
        return {"status": "error", "message": f"Call failed: {str(e)}"}

@app.post("/test-call")
async def test_call_with_first_candidate():
    """Test call endpoint - makes a call using the first available candidate"""
    try:
        # Get first available candidate
        candidates = get_all_candidates_from_mongo()
        if not candidates:
            return {
                "status": "error",
                "message": "No candidates found in database. Please add candidates to MongoDB first."
            }
        
        # Find a candidate that hasn't reached call limits
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")  # Fixed: use candidate_id instead of id
            if candidate_id:
                call_status = get_candidate_call_status(candidate_id)
                if call_status["can_call"]:
                    logger.info(f"Initiating test call to candidate: {candidate.get('name')} (ID: {candidate_id})")
                    
                    # Create a proper mock request for make_actual_call function
                    class MockRequest:
                        def __init__(self, json_data):
                            self._json_data = json_data
                            
                        async def json(self):
                            return self._json_data
                    
                    try:
                        mock_request = MockRequest({"candidate_id": candidate_id})
                        result = await make_actual_call(mock_request)
                    except Exception as e:
                        result = {"status": "error", "message": f"Function call failed: {str(e)}"}
                    
                    return {
                        "status": "success",
                        "message": f"Test call initiated to {candidate.get('name')}",
                        "candidate": {
                            "id": candidate_id,
                            "name": candidate.get('name'),
                            "phone": candidate.get('phone')
                        },
                        "call_result": result
                    }
        
        return {
            "status": "error",
            "message": "All candidates have reached their call limits. No calls can be made."
        }
        
    except Exception as e:
        logger.error(f"Error in test call: {e}")
        return {
            "status": "error",
            "message": f"Test call failed: {str(e)}"
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
        email_result = await send_interview_confirmation_email(candidate_info, test_slot, test_call_sid)
        
        # Handle both dictionary and boolean returns
        email_sent = email_result.get("email_sent", False) if isinstance(email_result, dict) else bool(email_result)
        
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

@app.get("/list-candidates")
async def list_all_candidates():
    """Get all candidates with their IDs for making calls"""
    try:
        candidates = get_all_candidates_from_mongo()
        
        if not candidates:
            return {
                "status": "warning",
                "message": "No candidates found in MongoDB",
                "candidates": [],
                "total": 0
            }
        
        # Format candidates for easy selection
        formatted_candidates = []
        for candidate in candidates:
            formatted_candidates.append({
                "id": candidate.get("candidate_id", "unknown"),  # Use candidate_id field from get_all_candidates_from_mongo
                "name": candidate.get("name", "Unknown"),
                "phone": candidate.get("phone", "No phone"),
                "email": candidate.get("email", "No email"),
                "position": candidate.get("position", "No position"),
                "company": candidate.get("company", "No company"),
                "call_tracking": candidate.get("call_tracking", {})
            })
        
        return {
            "status": "success",
            "candidates": formatted_candidates,
            "total": len(formatted_candidates)
        }
        
    except Exception as e:
        logger.error(f"Error listing candidates: {e}")
        return {
            "status": "error",
            "message": f"Failed to list candidates: {str(e)}"
        }

@app.get("/comprehensive-analytics")
async def get_comprehensive_analytics():
    """Get detailed analytics with MongoDB data"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient('mongodb://localhost:27017/')
        db = client['interview_scheduler']
        
        # Call attempts analytics from candidates collection
        candidates = list(db.candidates.find())
        total_call_attempts = sum(len(candidate.get('call_history', [])) for candidate in candidates)
        
        # Count outcomes from call history
        outcome_stats = {}
        status_stats = {}
        
        for candidate in candidates:
            for call in candidate.get('call_history', []):
                outcome = call.get('outcome', 'unknown')
                outcome_stats[outcome] = outcome_stats.get(outcome, 0) + 1
                
                status = call.get('twilio_status', 'unknown')
                status_stats[status] = status_stats.get(status, 0) + 1
        
        # Interview scheduling analytics
        interviews_scheduled = len([c for c in candidates if c.get('interview_status') == 'scheduled'])
        emails_sent = len([c for c in candidates if c.get('interview_details', {}).get('email_sent')])
        
        # Popular slots from interview details
        slots = [c.get('interview_details', {}).get('scheduled_slot') for c in candidates if c.get('interview_details', {}).get('scheduled_slot')]
        popular_slots = {}
        for slot in slots:
            popular_slots[slot] = popular_slots.get(slot, 0) + 1
        popular_slots_list = sorted(popular_slots.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Conversation analytics from conversations collection
        conversations = list(db.conversations.find())
        avg_conversation_turns = sum(len(conv.get('turns', [])) for conv in conversations) / len(conversations) if conversations else 0
        
        # Conversation status stats
        conversation_status_stats = {}
        for conv in conversations:
            status = conv.get('status', 'unknown')
            conversation_status_stats[status] = conversation_status_stats.get(status, 0) + 1
        
        # System logs summary
        log_stats = {}
        try:
            logs = db.system_logs.aggregate([
                {"$group": {"_id": "$log_level", "count": {"$sum": 1}}}
            ])
            log_stats = {log["_id"]: log["count"] for log in logs}
        except:
            log_stats = {"info": 0}
        
        client.close()
        
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
                "popular_time_slots": [{"slot": slot[0], "count": slot[1]} for slot in popular_slots_list]
            },
            "conversation_analytics": {
                "avg_turns_per_conversation": round(avg_conversation_turns, 2),
                "avg_ai_confidence": 0.85,  # Default value since we don't track this in MongoDB yet
                "conversation_outcomes": conversation_status_stats
            },
            "recent_activity": [],  # Can be implemented later with date filtering
            "system_health": {
                "log_level_distribution": log_stats,
                "total_logs": sum(log_stats.values())
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating comprehensive analytics from MongoDB: {e}")
        return {"error": str(e)}

@app.get("/call-attempts/{candidate_id}")
async def get_candidate_call_history(candidate_id: str):
    """Get detailed call history for a specific candidate from MongoDB"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient('mongodb://localhost:27017/')
        db = client['interview_scheduler']
        
        # Find candidate in MongoDB
        candidate = db.candidates.find_one({"$or": [{"phone": candidate_id}, {"_id": candidate_id}]})
        
        if not candidate:
            client.close()
            return {"error": "Candidate not found"}
        
        # Get call history from candidate record
        call_history = candidate.get('call_history', [])
        
        # Get conversation history for this candidate
        conversations = list(db.conversations.find({"candidate_phone": candidate.get('phone')}))
        
        # Merge call and conversation data
        for call in call_history:
            # Find matching conversation
            matching_conv = next((conv for conv in conversations if conv.get('call_sid') == call.get('call_sid')), None)
            if matching_conv:
                call['confirmed_slot'] = matching_conv.get('confirmed_slot')
                call['conversation_status'] = matching_conv.get('status')
        
        # Get interview details
        interview_history = []
        if candidate.get('interview_details'):
            interview_history = [candidate['interview_details']]
        
        client.close()
        
        return {
            "candidate_id": candidate_id,
            "total_attempts": len(call_history),
            "call_history": call_history,
            "interview_history": interview_history,
            "last_contact": call_history[0]['initiated_at'] if call_history else None
        }
        
    except Exception as e:
        logger.error(f"Error getting call history for candidate {candidate_id} from MongoDB: {e}")
        return {"error": str(e)}

@app.get("/system-logs")
async def get_system_logs(limit: int = 50, level: str = None):
    """Get system logs from MongoDB"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient('mongodb://localhost:27017/')
        db = client['interview_scheduler']
        
        query = {}
        if level:
            query["log_level"] = level.upper()
        
        logs = list(db.system_logs.find(query).sort("timestamp", -1).limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        for log in logs:
            if "_id" in log:
                log["_id"] = str(log["_id"])
        
        client.close()
        
        return {
            "logs": logs,
            "total_returned": len(logs),
            "filter_level": level
        }
        
    except Exception as e:
        logger.error(f"Error getting system logs: {e}")
        return {"error": str(e)}

@app.get("/candidate-limits")
async def get_candidate_call_limits():
    """Get all candidates with their call attempt counts and interview status from MongoDB"""
    try:
        from pymongo import MongoClient
        
        client = MongoClient('mongodb://localhost:27017/')
        db = client['interview_scheduler']
        
        candidates = list(db.candidates.find())
        candidate_info = {}
        
        for candidate in candidates:
            candidate_id = str(candidate.get('_id', candidate.get('phone', 'unknown')))
            call_history = candidate.get('call_history', [])
            attempts = len(call_history)
            has_scheduled = candidate.get('interview_status') == 'scheduled'
            can_call = attempts < 3 or has_scheduled
            
            # Get last contact date from call history
            last_contact = None
            if call_history:
                last_contact = max(call.get('initiated_at', '') for call in call_history)
            
            scheduled_count = 1 if has_scheduled else 0
            
            candidate_info[candidate_id] = {
                "name": candidate.get('name', 'Unknown'),
                "email": candidate.get('email', 'Unknown'),
                "phone": candidate.get('phone', 'Unknown'),
                "position": candidate.get('position', 'Unknown'),
                "company": candidate.get('company', 'Unknown'),
                "call_attempts": attempts,
                "can_receive_calls": can_call,
                "has_scheduled_interview": has_scheduled,
                "scheduled_interviews_count": scheduled_count,
                "last_contact_date": last_contact,
                "status": "interview_scheduled" if has_scheduled else ("max_attempts" if attempts >= 3 else "active")
            }
        
        client.close()
        
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
        "version": "2.0.1",  # Updated version
        "status": "WORKING",
        "timestamp": datetime.now().isoformat(),
        "webhook_url": WEBHOOK_BASE_URL,
        "twilio_webhook_test": f"{WEBHOOK_BASE_URL}/twilio-voice",
        "config": {
            "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER),
            "openai_configured": bool(OPENAI_API_KEY),
            "database_enabled": MONGODB_AVAILABLE,
            "mongodb_collection": config("MONGODB_COLLECTION", default="shortlistedcandidates")
        },
        "fixes_applied": [
            "Phone number matching for +91 prefix",
            "Improved webhook error handling", 
            "Fixed candidate lookup in shortlistedcandidates collection",
            "Enhanced session management",
            "Robust fallback mechanisms"
        ]
    }

@app.get("/recent-conversations")
async def get_recent_conversations(limit: int = 10):
    """Get recent conversations with detailed turn information from MongoDB"""
    try:
        if not MONGODB_AVAILABLE:
            return {"error": "MongoDB not available", "recent_conversations": []}
            
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Get recent conversations from MongoDB
        sessions = list(db.conversations.find().sort("start_time", -1).limit(limit))
        client.close()
        
        result = []
        for session in sessions:
            # Convert ObjectId to string
            if "_id" in session:
                session["_id"] = str(session["_id"])
                
            turns = session.get("turns", [])
            
            # Calculate conversation metrics
            total_turns = len(turns)
            duration = None
            start_time = session.get("start_time")
            end_time = session.get("end_time")
            if start_time and end_time:
                try:
                    start = datetime.fromisoformat(start_time)
                    end = datetime.fromisoformat(end_time)
                    duration = str(end - start)
                except:
                    pass
            
            # Get last AI response and candidate input
            last_turn = turns[-1] if turns else None
            
            session_summary = {
                "call_sid": session.get("call_sid"),
                "candidate_phone": session.get("candidate_phone"),
                "start_time": start_time,
                "end_time": end_time,
                "status": session.get("status"),
                "confirmed_slot": session.get("confirmed_slot"),
                "total_turns": total_turns,
                "duration": duration,
                "last_candidate_input": last_turn.get("candidate_input") if last_turn else None,
                "last_ai_response": last_turn.get("ai_response") if last_turn else None,
                "final_intent": last_turn.get("intent_detected") if last_turn else None,
                "conversation_turns": turns
            }
            result.append(session_summary)
        return {
            "recent_conversations": result,
            "total_found": len(result)
        }
        
    except Exception as e:
        logger.error(f"Error fetching recent conversations: {e}")
        return {"error": str(e), "recent_conversations": []}

@app.get("/conversations")
async def get_conversations():
    """Get all conversation sessions from MongoDB"""
    try:
        if not MONGODB_AVAILABLE:
            return {"error": "MongoDB not available", "conversations": []}
            
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Get conversations from MongoDB
        conversations = list(db.conversations.find().sort("start_time", -1))
        
        result = []
        for session in conversations:
            # Convert ObjectId to string for JSON serialization
            if "_id" in session:
                session["_id"] = str(session["_id"])
                
            session_dict = {
                "call_sid": session.get("call_sid"),
                "candidate_phone": session.get("candidate_phone"),
                "start_time": session.get("start_time"),
                "end_time": session.get("end_time"),
                "status": session.get("status"),
                "confirmed_slot": session.get("confirmed_slot"),
                "turns": session.get("turns", [])
            }
            result.append(session_dict)
        
        client.close()
        return {"conversations": result}
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return {"error": str(e), "conversations": []}

@app.get("/conversations/{call_sid}")
async def get_conversation(call_sid: str):
    """Get specific conversation details"""
    try:
        if not MONGODB_AVAILABLE:
            return {"error": "MongoDB not available"}
            
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        session = db.conversations.find_one({"call_sid": call_sid})
        client.close()
        
        if not session:
            return {"error": "Conversation not found"}
        
        # Convert ObjectId to string
        if "_id" in session:
            session["_id"] = str(session["_id"])
        
        result = {
            "call_sid": session.get("call_sid"),
            "candidate_phone": session.get("candidate_phone"),
            "start_time": session.get("start_time"),
            "end_time": session.get("end_time"),
            "status": session.get("status"),
            "confirmed_slot": session.get("confirmed_slot"),
            "turns": session.get("turns", [])
        }
        
        return result
    except Exception as e:
        logger.error(f"Error fetching conversation {call_sid}: {e}")
        return {"error": str(e)}

@app.get("/analytics")
async def get_analytics():
    """Get conversation analytics from MongoDB"""
    try:
        if not MONGODB_AVAILABLE:
            return {"error": "MongoDB not available"}
            
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Basic stats using MongoDB aggregation
        pipeline_total = [{"$count": "total"}]
        total_result = list(db.conversations.aggregate(pipeline_total))
        total_calls = total_result[0]["total"] if total_result else 0
        
        successful_calls = db.conversations.count_documents({"status": "completed"})
        failed_calls = db.conversations.count_documents({"status": "failed"})
        active_calls = db.conversations.count_documents({"status": "active"})
        
        # Average turns per call
        pipeline_avg = [
            {"$match": {"turns": {"$exists": True}}},
            {"$project": {"turn_count": {"$size": "$turns"}}},
            {"$group": {"_id": None, "avg_turns": {"$avg": "$turn_count"}}}
        ]
        avg_result = list(db.conversations.aggregate(pipeline_avg))
        avg_turns = avg_result[0]["avg_turns"] if avg_result else 0
        
        # Most confirmed slots
        pipeline_slots = [
            {"$match": {"confirmed_slot": {"$ne": None}}},
            {"$group": {"_id": "$confirmed_slot", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        slot_results = list(db.conversations.aggregate(pipeline_slots))
        slot_preferences = [{"slot": slot["_id"], "count": slot["count"]} for slot in slot_results]
        
        client.close()
        
        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "active_calls": active_calls,
            "success_rate": round((successful_calls / total_calls * 100) if total_calls > 0 else 0, 2),
            "average_turns_per_call": round(avg_turns, 2),
            "slot_preferences": slot_preferences
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
        
        # If not in memory, check MongoDB database
        if MONGODB_AVAILABLE:
            try:
                client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
                db = client['interview_scheduler']
                session_data = db.conversations.find_one({"call_sid": call_sid})
                client.close()
                
                if session_data:
                    turns = session_data.get("turns", [])
                    
                    return {
                        "call_sid": call_sid,
                        "conversation_status": session_data.get("status"),
                        "current_turn": len(turns),
                        "candidate_phone": session_data.get("candidate_phone"),
                        "start_time": session_data.get("start_time"),
                        "end_time": session_data.get("end_time"),
                        "confirmed_slot": session_data.get("confirmed_slot"),
                        "twilio_status": None,  # Not available for completed calls
                        "recent_turns": turns[-3:] if turns else [],  # Last 3 turns
                        "candidate_info": None
                    }
            except Exception as db_error:
                logger.error(f"MongoDB error in live conversation: {db_error}")
        
        return {"error": "Conversation not found", "call_sid": call_sid}
        
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

@app.get("/candidate-status/{candidate_id}")
async def get_comprehensive_candidate_status(candidate_id: str):
    """Get comprehensive status including call, interview, and email information"""
    try:
        # Get candidate basic info
        candidate_info = fetch_candidate_by_id(candidate_id)
        if not candidate_info:
            return {
                "status": "error",
                "message": f"Candidate not found with ID: {candidate_id}"
            }

        # Get scheduling status
        scheduling_status = get_candidate_scheduling_status(candidate_id)
        
        # Get call status
        call_status = get_candidate_call_status(candidate_id)
        
        # Combine all information
        comprehensive_status = {
            "candidate_id": candidate_id,
            "candidate_info": {
                "name": candidate_info.get("name"),
                "phone": candidate_info.get("phone"),
                "email": candidate_info.get("email"),
                "position": candidate_info.get("position"),
                "company": candidate_info.get("company")
            },
            "call_tracking": {
                "can_call": call_status.get("can_call", False),
                "total_attempts": call_status.get("attempts", 0),
                "max_attempts": 3,
                "remaining_attempts": max(0, 3 - call_status.get("attempts", 0)),
                "status": call_status.get("status", "unknown"),
                "reason": call_status.get("reason", "")
            },
            "scheduling_status": scheduling_status,
            "overall_status": determine_overall_status(scheduling_status, call_status),
            "last_updated": datetime.now().isoformat()
        }
        
        return comprehensive_status
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get candidate status: {str(e)}"
        }

def determine_overall_status(scheduling_status: dict, call_status: dict) -> dict:
    """Determine overall candidate status based on scheduling and call data"""
    interview_status = scheduling_status.get("interview_status", "not_scheduled")
    email_status = scheduling_status.get("email_notifications", {})
    
    if interview_status == "scheduled" and email_status.get("confirmation_sent"):
        overall = "interview_scheduled_confirmed"
        message = "Interview scheduled and confirmation email sent"
    elif interview_status == "scheduled":
        overall = "interview_scheduled_pending"
        message = "Interview scheduled but email confirmation pending"
    elif call_status.get("attempts", 0) >= 3:
        overall = "max_attempts_reached"
        message = "Maximum call attempts reached, manual follow-up needed"
    elif call_status.get("attempts", 0) > 0:
        overall = "in_progress"
        message = f"Contact attempts made ({call_status.get('attempts', 0)}/3)"
    else:
        overall = "not_contacted"
        message = "No contact attempts made yet"
    
    return {
        "status": overall,
        "message": message,
        "priority": get_priority_level(overall),
        "next_action": get_next_action(overall)
    }

def get_priority_level(status: str) -> str:
    """Get priority level based on status"""
    if status == "max_attempts_reached":
        return "high"
    elif status in ["interview_scheduled_pending", "in_progress"]:
        return "medium"
    elif status == "interview_scheduled_confirmed":
        return "low"
    else:
        return "normal"

def get_next_action(status: str) -> str:
    """Get recommended next action based on status"""
    actions = {
        "not_contacted": "Make initial call",
        "in_progress": "Continue follow-up calls",
        "max_attempts_reached": "Manual review and alternative contact",
        "interview_scheduled_pending": "Verify email delivery or resend",
        "interview_scheduled_confirmed": "No action needed - await interview"
    }
    return actions.get(status, "Review status")

@app.delete("/conversations/{call_sid}")
async def delete_conversation(call_sid: str):
    """Delete a conversation session from MongoDB"""
    try:
        if not MONGODB_AVAILABLE:
            return {"error": "MongoDB not available"}
            
        client = MongoClient(config("MONGODB_URI", default="mongodb://localhost:27017"))
        db = client['interview_scheduler']
        
        # Delete from MongoDB
        result = db.conversations.delete_one({"call_sid": call_sid})
        client.close()
        
        if result.deleted_count > 0:
            # Also remove from memory
            if call_sid in conversation_sessions:
                del conversation_sessions[call_sid]
            return {"message": "Conversation deleted successfully"}
        else:
            return {"error": "Conversation not found"}
    except Exception as e:
        logger.error(f"Error deleting conversation {call_sid}: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    print("AI Interview Caller - Ready to receive calls")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)