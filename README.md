# AI Interview Scheduler

An intelligent automated interview scheduling system that uses AI-powered phone calls to schedule interviews with candidates. The system integrates with Twilio for voice calls, MongoDB for data storage, and email services for confirmations.

## 🚀 Features

- **AI-Powered Voice Calls**: Automated phone calls using Twilio and OpenAI
- **Intelligent Conversation Flow**: Natural language processing for scheduling
- **MongoDB Integration**: Complete candidate and call tracking
- **Email Confirmations**: Automated interview confirmation emails via Resend/SendGrid
- **Real-time Analytics**: Comprehensive call and scheduling analytics
- **Retry Logic**: Smart retry mechanism for failed calls
- **Dashboard UI**: Frontend interface for managing candidates and interviews

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   External      │
│   (Next.js)     │    │   (FastAPI)     │    │   Services      │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • Dashboard     │◄──►│ • API Endpoints │◄──►│ • Twilio Voice  │
│ • Candidate Mgmt│    │ • AI Logic      │    │ • OpenAI GPT    │
│ • Analytics     │    │ • Webhooks      │    │ • MongoDB Atlas │
│ • Call Logs     │    │ • Email Service │    │ • Resend/SendGrid│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

- Python 3.8+
- Node.js 16+ (for frontend)
- MongoDB Atlas account
- Twilio account with phone number
- Resend or SendGrid account for emails
- OpenAI API key

## 🛠️ Installation

### Backend Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/muhammadnavas/AI_Interview_Caller.git
   cd AI_Interview_Caller/backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Setup**
   Create a `.env` file in the backend directory:
   ```env
   # Email Configuration
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   SENDER_EMAIL=your_email@gmail.com

   # Email Providers (HTTP APIs - Primary)
   EMAIL_USER=your_email@gmail.com
   EMAIL_PASS=your_app_password
   RESEND_API_KEY=re_your_resend_api_key
   SENDGRID_API_KEY=SG.your_sendgrid_api_key

   # AI Configuration
   GEMINI_API_KEY=your_gemini_api_key
   OPENAI_API_KEY=sk-your_openai_api_key

   # Twilio Configuration
   TWILIO_ACCOUNT_SID=ACyour_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=+1234567890

   # Webhook URL (for deployment)
   WEBHOOK_BASE_URL=https://your-app.onrender.com

   # MongoDB Configuration
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
   MONGODB_DB=test
   MONGODB_COLLECTION=shortlistedcandidates
   ```

5. **Run the application**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend Setup

1. **Navigate to frontend directory**
   ```bash
   cd ../frontend
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Run the development server**
   ```bash
   npm run dev
   ```

## 🌐 Deployment

### Deploy on Render

1. **Connect your GitHub repository** to Render
2. **Configure environment variables** in Render dashboard
3. **Set build command**: `pip install -r requirements.txt`
4. **Set start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Update Twilio webhook URL** to your Render app URL

### Deploy Frontend on Vercel

1. **Connect repository** to Vercel
2. **Set framework preset** to Next.js
3. **Configure environment variables**
4. **Deploy**

## 📚 API Documentation

### Core Endpoints

#### Twilio Integration
- `POST /twilio-voice` - Main webhook for incoming/outgoing calls
- `POST /twilio-process` - Process speech during calls

#### Call Management
- `POST /make-actual-call` - Initiate outbound calls
- `POST /call-candidate/{candidate_id}` - Call specific candidate
- `GET /call-status/{call_sid}` - Get call status

#### Candidate Management
- `GET /candidates` - List all candidates
- `GET /candidate-status/{candidate_id}` - Get candidate status
- `GET /list-candidates` - Detailed candidate list

#### Analytics & Monitoring
- `GET /analytics` - System analytics
- `GET /conversations` - Call conversation history
- `GET /system-logs` - Application logs
- `GET /recent-conversations` - Recent call logs

#### Testing
- `POST /test-email` - Test email functionality
- `POST /test-call` - Test call functionality
- `GET /test-webhook` - Webhook health check

### Conversation Flow

```mermaid
graph TD
    A[Outbound Call] --> B[AI Greeting]
    B --> C[Candidate Response]
    C --> D{Intent Detection}
    D -->|Positive| E[Present Time Slots]
    D -->|Negative| F[Handle Objection]
    D -->|Unclear| G[Clarify Response]
    E --> H[Wait for Time Selection]
    H --> I{Time Slot Mentioned?}
    I -->|Yes| J[Confirm Selection]
    I -->|No| K[Repeat Options]
    J --> L[Send Email Confirmation]
    L --> M[Update Database]
    M --> N[End Call]
    F --> O[Offer Alternatives]
    O --> P[Schedule Later]
    G --> Q[Ask Again]
    K --> E
    Q --> C
```

## 🗄️ Database Schema

### MongoDB Collections

#### shortlistedcandidates
```json
{
  "_id": ObjectId,
  "candidateName": "string",
  "candidateEmail": "string", 
  "phoneNumber": "string",
  "role": "string",
  "companyName": "string",
  "interviewStatus": "active|calling|scheduled|completed|failed",
  "call_tracking": {
    "total_attempts": Number,
    "status": "string",
    "interview_details": {
      "scheduled_slot": "string",
      "scheduled_at": "ISODate",
      "call_sid": "string",
      "email_sent": Boolean,
      "email_status": {
        "sent": Boolean,
        "status": "string",
        "sent_at": "ISODate",
        "service": "string"
      }
    },
    "call_history": []
  }
}
```

#### conversations
```json
{
  "call_sid": "string",
  "candidate_id": "string",
  "status": "active|completed|failed",
  "confirmed_slot": "string",
  "turns": [
    {
      "turn_number": Number,
      "candidate_input": "string", 
      "ai_response": "string",
      "intent_detected": "string",
      "confidence_score": Number
    }
  ]
}
```

## ⚙️ Configuration

### Time Slots
Configure available interview slots in `main.py`:
```python
TIME_SLOTS = [
    "Monday at 10 AM",
    "Tuesday at 2 PM", 
    "Wednesday at 11 AM",
    "Thursday at 3 PM"
]
```

### AI Prompts
Customize AI behavior in the `generate_ai_response()` function.

### Email Templates
Modify email templates in `send_interview_confirmation_email()` function.

## 🔧 Troubleshooting

### Common Issues

1. **SMTP Blocked on Render**
   - Solution: Use HTTP email APIs (Resend/SendGrid) instead of SMTP
   - The app automatically falls back to HTTP APIs

2. **Twilio Webhook Not Receiving Calls**
   - Check webhook URL configuration in Twilio console
   - Ensure URL is accessible and returns 200 status

3. **MongoDB Connection Issues**
   - Verify MongoDB URI and network access
   - Check if IP is whitelisted in MongoDB Atlas

4. **OpenAI API Errors**
   - Verify API key and billing status
   - Check rate limits and usage

### Logs and Debugging

- Application logs available at `/system-logs` endpoint
- Call conversations stored in MongoDB
- Email delivery status tracked in candidate documents

## 🔒 Security

- Environment variables for sensitive data
- MongoDB connection with authentication
- HTTPS for all external API calls
- Input validation and sanitization
- Rate limiting on endpoints

## 📈 Monitoring

- Real-time call status tracking
- Email delivery confirmation
- Candidate interaction analytics
- System health monitoring
- Error logging and alerting

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For issues and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the API documentation

## 🔮 Future Enhancements

- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Integration with calendar systems
- [ ] SMS notifications
- [ ] Video interview scheduling
- [ ] Candidate feedback collection
- [ ] Advanced AI conversation training

---

Built with ❤️ for efficient interview scheduling automation.