# AI Interview Caller - Backend

A clean implementation of an AI-powered interview caller using **Twilio Voice API** and **Google Gemini AI**.

## Features

- 🎯 **Real Phone Calls** - Uses Twilio Voice API to make actual phone calls
- 🤖 **AI Conversation** - Gemini AI generates natural, context-aware responses
- 🎙️ **Speech Processing** - Automatic speech-to-text conversion via Twilio
- 📋 **Interview Flow** - Structured conversation for scheduling interviews
- 🔧 **Webhook Support** - Handles Twilio callbacks for call management

## Quick Setup

1. **Install Dependencies**
   ```bash
   pip install fastapi twilio google-generativeai python-decouple uvicorn
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Twilio and Gemini credentials
   ```

3. **Setup Public Webhook** (for development)
   ```bash
   # Install ngrok
   ngrok http 8000
   # Copy the HTTPS URL to WEBHOOK_BASE_URL in .env
   ```

4. **Run Server**
   ```bash
   python main.py
   # Or: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Required Services

### Twilio (Voice API)
- Sign up: https://www.twilio.com/try-twilio
- Get $15 free trial credit
- Purchase a phone number
- Copy Account SID, Auth Token, and Phone Number to .env

### Google Gemini AI
- Get API key: https://makersuite.google.com/app/apikey
- Copy to .env as GEMINI_API_KEY

## API Endpoints

- `POST /make-actual-call` - Initiate Twilio phone call
- `POST /twilio-voice` - Twilio webhook for call handling
- `POST /twilio-process` - Process speech and generate AI responses
- `GET /webhook-setup-guide` - Setup instructions for webhooks
- `GET /` - Status and configuration check

## Environment Variables

```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
GEMINI_API_KEY=your_gemini_key
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io
```

## How It Works

1. **Call Initiation**: Frontend calls `/make-actual-call`
2. **Twilio Dials**: Twilio makes real phone call to candidate
3. **Webhook Triggered**: Twilio sends call events to `/twilio-voice`
4. **Speech Processing**: Candidate speech converted to text
5. **AI Response**: Gemini generates contextual response
6. **TwiML Return**: AI response converted to speech via Twilio

## Architecture

```
Frontend (React) → FastAPI Backend → Twilio Voice API
                        ↓
                  Gemini AI Processing
                        ↓
                  TwiML Response → Speech
```

This is a streamlined version focused purely on Twilio voice calling and Gemini AI integration.