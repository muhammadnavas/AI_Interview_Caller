#!/bin/bash
# Debug script for candidate_id JSON testing

echo "🔧 Candidate ID System Debug Script"
echo "======================================"
echo ""

# Test 1: Check if server is running
echo "1️⃣ Testing server connectivity..."
curl -s http://localhost:8000/test-webhook > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ Server is running on port 8000"
else
    echo "❌ Server is NOT running. Start with: cd backend && python main.py"
    exit 1
fi
echo ""

# Test 2: Test JSON parsing with debug endpoint
echo "2️⃣ Testing JSON parsing..."
curl -X POST http://localhost:8000/test-json \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "TEST_12345678"}' \
  -w "\nHTTP Status: %{http_code}\n"
echo ""

# Test 3: Get actual candidates
echo "3️⃣ Getting list of candidates..."
curl -s -X GET http://localhost:8000/list-candidates | python -m json.tool
echo ""

# Test 4: Provide example curl command
echo "4️⃣ Example curl command for calling a candidate:"
echo "Replace ACTUAL_CANDIDATE_ID with a real ID from step 3:"
echo ""
echo "curl -X POST http://localhost:8000/call-candidate \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"candidate_id\": \"ACTUAL_CANDIDATE_ID\"}'"
echo ""

echo "🎯 Common Issues:"
echo "- Make sure to use double quotes in JSON: {\"candidate_id\": \"value\"}"
echo "- Include Content-Type header: -H \"Content-Type: application/json\""
echo "- Use actual candidate_id from step 3, not placeholder text"
echo "- Escape quotes properly in command line"