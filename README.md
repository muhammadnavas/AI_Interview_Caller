# AI Interview Caller

A complete full-stack application for automated interview scheduling using AI-powered voice conversations. The system makes real phone calls to candidates, conducts intelligent conversations to schedule interviews, and provides comprehensive analytics.

## 🌟 Features

### Core Functionality
- **Real Phone Calls**: Makes actual phone calls using Twilio Voice API
- **AI Conversations**: GPT-4 powered natural language conversations
- **Smart Scheduling**: Handles multiple time slots and candidate preferences  
- **Intent Detection**: Understands confirmation, rejection, and time preferences
- **Conversation Persistence**: SQLite database stores all conversation history

### User Interface
- **Real-time Dashboard**: Monitor active calls and conversation status
- **Conversation History**: View detailed turn-by-turn conversation logs
- **Analytics**: Success rates, popular time slots, and performance metrics
- **Call Management**: Initiate calls and track outcomes

### Technical Features
- **Robust Error Handling**: Graceful fallbacks and detailed error reporting
- **Comprehensive Logging**: File and console logging for debugging
- **Session Management**: Persistent conversation state across interactions
- **Webhook Security**: Validates Twilio requests and handles failures

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   External      │
│   (Next.js)     │    │   (FastAPI)     │    │   Services      │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • Call UI       │◄──►│ • API Endpoints │◄──►│ • Twilio Voice  │
│ • Conversations │    │ • Conversation  │    │ • OpenAI GPT-4  │
│ • Analytics     │    │   Management    │    │ • ngrok         │
│ • Real-time     │    │ • Database      │    │                 │
│   Updates       │    │ • Logging       │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### 1. Prerequisites
- **Node.js** 18+ (for frontend)
- **Python** 3.10+ (for backend)
- **Twilio Account** (free trial available)
- **OpenAI API Key**
- **ngrok** (for local development webhooks)

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt  # or uv sync
cp .env.example .env
# Edit .env with your credentials
python main.py
```

### 3. Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local if needed
npm run dev
```

### 4. Webhook Setup (for development)
```bash
# In a separate terminal
ngrok http 8000
# Copy the https URL to your .env file as WEBHOOK_BASE_URL
```

### 5. Access the Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 📱 Usage

1. **Configure Candidate**: Set candidate details in backend `.env` file
2. **Start Services**: Run backend, frontend, and ngrok
3. **Make Call**: Click "Make Call" in the frontend interface
4. **Monitor**: Watch real-time conversation progress
5. **Review**: Check analytics and conversation history

## 🔧 Configuration

### Environment Variables

**Backend** (`.env`):
```env
# Twilio
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# OpenAI
OPENAI_API_KEY=your_openai_key

# Candidate
CANDIDATE_NAME=John Doe
CANDIDATE_PHONE=+1234567890
CANDIDATE_EMAIL=john@example.com
CANDIDATE_POSITION=Software Engineer
CANDIDATE_COMPANY=TechCorp

# Webhook (auto-detected with ngrok)
WEBHOOK_BASE_URL=https://your-url.ngrok.io
```

**Frontend** (`.env.local`):
```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### Time Slots Configuration
Edit `TIME_SLOTS` in `backend/main.py`:
```python
TIME_SLOTS = [
    "Monday at 10 AM",
    "Tuesday at 2 PM", 
    "Wednesday at 11 AM",
    "Thursday at 3 PM",
]
```

## 📊 API Documentation

### Core Endpoints
- `POST /make-actual-call` - Initiate interview call
- `GET /conversations` - List all conversations  
- `GET /conversations/{call_sid}` - Get conversation details
- `GET /analytics` - View call analytics
- `GET /` - System status

### Webhook Endpoints (called by Twilio)
- `POST /twilio-voice` - Call initiation webhook
- `POST /twilio-process` - Speech processing webhook

## 🗃️ Database Schema

**conversation_sessions**:
```sql
CREATE TABLE conversation_sessions (
    call_sid TEXT PRIMARY KEY,
    candidate_phone TEXT,
    start_time TEXT,
    end_time TEXT,
    status TEXT,  -- active, completed, failed
    confirmed_slot TEXT,
    turns_json TEXT
);
```

**conversation_turns**:
```sql
CREATE TABLE conversation_turns (
    id INTEGER PRIMARY KEY,
    call_sid TEXT,
    turn_number INTEGER,
    candidate_input TEXT,
    ai_response TEXT,
    timestamp TEXT,
    intent_detected TEXT,
    confidence_score REAL
);
```

## 🎯 Conversation Flow

1. **Greeting**: "Hello [Name]! I'm calling from [Company] regarding your [Position] interview..."
2. **Slot Offering**: Present available time slots
3. **Intent Analysis**: Detect confirmation, rejection, or time preferences
4. **Negotiation**: Handle objections and offer alternatives
5. **Confirmation**: Confirm selected slot and end call
6. **Fallback**: Handle unclear responses with guidance

## 📈 Analytics & Monitoring

### Metrics Tracked
- **Success Rate**: Percentage of successful interview confirmations
- **Average Turns**: Conversation efficiency metrics
- **Popular Slots**: Most preferred interview times
- **Call Outcomes**: Completed vs failed calls
- **Response Analysis**: Intent detection accuracy

### Logs Available
- **Application Logs**: `backend/conversation.log`
- **Console Output**: Real-time status updates
- **Database Records**: Persistent conversation history

## 🐛 Troubleshooting

### Common Issues

**"Webhook URL must be public"**
```bash
# Start ngrok and update .env
ngrok http 8000
# Copy https URL to WEBHOOK_BASE_URL
```

**"Invalid Twilio credentials"**
- Check Twilio Console for correct SID/Token
- Verify phone number format (+1234567890)

**"OpenAI API errors"**
- Check API key validity
- Verify sufficient credits
- Monitor rate limits

**Database permission errors**
- Ensure write permissions in backend directory
- Check SQLite installation

### Debug Mode
```bash
# Backend with debug logging
LOG_LEVEL=DEBUG python main.py

# Frontend with detailed errors
npm run dev
```

## 🚀 Deployment

### Production Checklist
- [ ] Use environment variables (not .env files)
- [ ] Set up proper webhook URLs (not ngrok)
- [ ] Configure SSL certificates
- [ ] Set up database backups
- [ ] Implement webhook signature validation
- [ ] Configure proper logging service
- [ ] Set up monitoring and alerts

### Deployment Options
- **Heroku**: Easy deployment with add-ons
- **AWS**: Full control with EC2/Lambda
- **Vercel**: Frontend + serverless functions
- **Railway**: Simple full-stack deployment

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Twilio** for voice communication infrastructure
- **OpenAI** for intelligent conversation capabilities
- **FastAPI** for robust backend framework
- **Next.js** for modern frontend development

## 📞 Support

For questions and support:
- Create an issue in this repository
- Check the troubleshooting guide above
- Review API documentation at `/docs`

---

**Made with ❤️ for automated interview scheduling**