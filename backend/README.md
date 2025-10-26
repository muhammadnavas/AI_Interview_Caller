# AI Interview Caller Backend

A sophisticated FastAPI backend service for automated interview scheduling using Twilio voice calls, OpenAI for intelligent conversation management, and SQLite for conversation persistence.

## 🚀 Features

- **Intelligent Conversations**: AI-powered conversation flow with intent detection and context awareness
- **Persistent Storage**: SQLite database for conversation history and analytics
- **Real-time Monitoring**: Comprehensive logging and conversation tracking
- **Robust Error Handling**: Graceful fallbacks and detailed error reporting
- **Analytics Dashboard**: Call success rates, turn analytics, and slot preferences
- **Multiple Time Slots**: Flexible scheduling with candidate preference detection

## 📋 Prerequisites

- Python 3.10+
- Twilio Account with phone number
- OpenAI API key
- ngrok (for webhook access during development)

## �️ Installation

1. **Clone and navigate to backend directory**:
```bash
cd backend
```

2. **Install dependencies**:
```bash
pip install fastapi uvicorn twilio openai python-decouple sqlite3 requests
```
Or using uv:
```bash
uv sync
```

3. **Set up environment variables**:
   - Copy `.env.example` to `.env`
   - Fill in your credentials:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Candidate Information
CANDIDATE_NAME=John Doe
CANDIDATE_PHONE=+1234567890
CANDIDATE_EMAIL=candidate@example.com
CANDIDATE_POSITION=Software Engineer
CANDIDATE_COMPANY=TechCorp
```

4. **Set up ngrok for webhook access**:
```bash
# Install ngrok from https://ngrok.com/
ngrok http 8000
```

## 🚀 Running the Service

1. **Start the backend server**:
```bash
python main.py
```

2. **In a separate terminal, start ngrok**:
```bash
ngrok http 8000
```

3. **Access the API**:
   - API docs: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/`

## 📊 API Endpoints

### Core Functionality
- `POST /make-actual-call` - Initiate automated interview call
- `POST /twilio-voice` - Twilio webhook entry point (called by Twilio)
- `POST /twilio-process` - Process speech responses (called by Twilio)

### Monitoring & Analytics
- `GET /` - System status and configuration
- `GET /conversations` - List all conversation sessions
- `GET /conversations/{call_sid}` - Get specific conversation details
- `GET /analytics` - Conversation analytics and success metrics
- `DELETE /conversations/{call_sid}` - Delete conversation record

## 🗂️ Database Schema

The system automatically creates SQLite tables:

**conversation_sessions**:
- call_sid (Primary Key)
- candidate_phone
- start_time, end_time
- status (active/completed/failed)
- confirmed_slot
- turns_json (conversation history)

**conversation_turns**:
- Individual turn records with intent detection and confidence scores

## 🎯 Conversation Flow

1. **Greeting**: Professional introduction with company and position details
2. **Intent Detection**: AI analyzes responses for confirmation, rejection, or time preferences
3. **Slot Negotiation**: Offers available time slots and handles preferences
4. **Confirmation**: Confirms selected slot and ends call
5. **Fallback Handling**: Graceful handling of unclear responses or excessive turns

## 📈 Analytics Features

- **Success Rate Tracking**: Percentage of successful interview scheduling
- **Turn Analysis**: Average conversation length and efficiency metrics  
- **Slot Preferences**: Popular time slot selection patterns
- **Real-time Monitoring**: Active call tracking and status updates

## 🔧 Configuration Options

**Time Slots**: Modify `TIME_SLOTS` array in main.py:
```python
TIME_SLOTS = [
    "Monday at 10 AM",
    "Tuesday at 2 PM", 
    "Wednesday at 11 AM",
    "Thursday at 3 PM",
]
```

**Conversation Limits**: 
- Maximum 6 turns per call (configurable)
- 10-second speech timeout
- Automatic fallback after unclear responses

## 🐛 Troubleshooting

**Common Issues**:

1. **"Webhook URL must be public"**
   - Start ngrok: `ngrok http 8000`
   - Ensure WEBHOOK_BASE_URL points to ngrok URL

2. **"Invalid Twilio credentials"**
   - Verify TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
   - Check Twilio console for correct values

3. **"Invalid phone number format"**
   - Use format: +1234567890 (include country code)
   - Verify candidate phone number is valid

4. **Database errors**
   - Database is created automatically on first run
   - Check file permissions in current directory

## 📝 Logging

Logs are written to:
- Console (real-time monitoring)
- `conversation.log` file (persistent logging)

Log levels: INFO (default), DEBUG, WARNING, ERROR

## 🔒 Security Considerations

- Keep API keys secure in `.env` file
- Don't commit `.env` to version control
- Use HTTPS webhooks in production
- Validate Twilio webhook signatures (recommended for production)

## 🚀 Deployment

For production deployment:
1. Use environment variables instead of `.env` file
2. Set up proper webhook URL (not ngrok)
3. Configure logging to external service
4. Set up database backups
5. Implement webhook signature validation