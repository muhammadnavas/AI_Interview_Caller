# Candidate ID System Testing Commands

## 1. First, start the backend server:
```bash
cd backend
python main.py
```

## 2. List all candidates to see their candidate_id values:
```bash
curl -X GET http://localhost:8000/list-candidates
```

## 3. Call a candidate using the proper JSON format:
```bash
# Replace "CANDIDATE_ID_HERE" with an actual candidate_id from step 2
curl -X POST http://localhost:8000/call-candidate \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "CANDIDATE_ID_HERE"}'
```

## Example of correct JSON format:
```json
{
  "candidate_id": "CAND_ABC12345"
}
```

## 4. Alternative test using the Python script:
```bash
cd backend
python test_candidate_id.py
```

## Notes:
- The candidate_id field should now be in format "CAND_XXXXXXXX" 
- If you see ObjectId values instead, the migration didn't complete properly
- Make sure the backend server is running before testing
- Check that MongoDB is running and accessible