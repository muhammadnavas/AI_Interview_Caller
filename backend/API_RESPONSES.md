# 🎯 AI Interview Call Endpoint - Response Documentation

## 📞 What the AI Interview Call Endpoint Returns

Based on your `shortlistedcandidates` collection data, here are the exact responses you'll get:

---

## 📋 1. GET `/list-candidates`

**Response:**
```json
{
  "status": "success",
  "candidates": [
    {
      "candidate_id": "690b857c80befccb653eb73a",
      "name": "sam", 
      "phone": "+918660761403",
      "email": "samarthhegde816@gmail.com",
      "position": "AI Engineer",
      "company": "LinkUp",
      "call_tracking": {}
    }
  ],
  "total": 1
}
```

---

## 🎯 2. POST `/make-actual-call`

**Request:**
```json
{
  "candidate_id": "690b857c80befccb653eb73a"
}
```

### ✅ **Success Response** (When call is initiated successfully):
```json
{
  "status": "success",
  "message": "Call initiated to +918660761403",
  "call_sid": "CA1234567890abcdef123456",
  "call_status": "queued",
  "webhook_url": "https://ai-interview-caller-wz24.onrender.com/twilio-voice", 
  "candidate": "sam",
  "initial_status": "queued"
}
```

### ❌ **Error Responses** (Possible scenarios):

#### **1. Invalid Candidate ID:**
```json
{
  "status": "error",
  "message": "Candidate not found with ID: 690b857c80befccb653eb73a. Please check the candidate exists in MongoDB."
}
```

#### **2. Missing Twilio Credentials:**
```json
{
  "status": "error",
  "message": "Missing Twilio credentials: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN. Check your .env file."
}
```

#### **3. Call Limit Reached:**
```json
{
  "status": "error", 
  "message": "Cannot make call: Maximum attempts reached (3/3)",
  "candidate": "sam",
  "attempts": 3,
  "call_limit_reached": true,
  "details": {
    "can_call": false,
    "reason": "Maximum attempts reached (3/3)",
    "attempts": 3,
    "status": "max_attempts"
  }
}
```

#### **4. Invalid Phone Number:**
```json
{
  "status": "error",
  "message": "Invalid phone number for candidate 690b857c80befccb653eb73a: 8660761403. Please update the candidate's phone number."
}
```

#### **5. Twilio Call Failed:**
```json
{
  "status": "error",
  "message": "Call failed: The number you have dialed is not in service",
  "error_code": "21214", 
  "call_sid": "CA1234567890abcdef123456"
}
```

---

## 📊 3. Candidate Data Structure

**Raw MongoDB Document** (from `shortlistedcandidates`):
```json
{
  "_id": "690b857c80befccb653eb73a",
  "candidateId": "68f9070c8b0f083d6bf39ee7",
  "applicationId": "690b6e05340d3de0ef5053e7", 
  "jobId": "68fde2f8b77a9c91fe550235",
  "candidateName": "sam",
  "candidateEmail": "samarthhegde816@gmail.com",
  "phoneNumber": "8660761403",
  "companyName": "LinkUp", 
  "role": "AI Engineer",
  "recruiterId": "68fde294b77a9c91fe55022b",
  "interviewStatus": "scheduled",
  "techStack": ["React", "Python"],
  "experience": "0",
  "shortlistedAt": "2025-11-05 17:12:28.928000",
  "__v": 0,
  "scheduledInterviewDate": "2025-11-05 17:42:22.797000"
}
```

**Mapped to System Format:**
```json
{
  "name": "sam",
  "phone": "8660761403", 
  "email": "samarthhegde816@gmail.com",
  "position": "AI Engineer",
  "company": "LinkUp"
}
```

---

## 📞 4. Call Status Check Response

**GET `/call-status/{call_sid}`** or internal check:
```json
{
  "can_call": true,
  "reason": "Can receive calls (0/3)",
  "attempts": 0, 
  "status": "active"
}
```

---

## 🚀 5. After Successful Call

The system will:
1. **Create Twilio Call** to `+918660761403`
2. **Update MongoDB** with call tracking data
3. **Handle AI Conversation** via webhook
4. **Schedule Interview** if candidate agrees
5. **Send Email Confirmation** to `samarthhegde816@gmail.com`

The AI will greet the candidate: 
> *"Hello sam! This is an AI assistant calling from LinkUp regarding your AI Engineer position application. I'd like to schedule your interview. Do you have a moment to talk?"*

---

## ✅ Summary

**Your specific candidate "sam" will get:**
- ✅ Phone call to `+918660761403`
- ✅ Professional AI greeting mentioning LinkUp and AI Engineer role
- ✅ Interview scheduling conversation
- ✅ Email confirmation to `samarthhegde816@gmail.com`
- ✅ Call tracking in MongoDB `shortlistedcandidates` collection