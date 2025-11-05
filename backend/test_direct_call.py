#!/usr/bin/env python3
"""
Direct test of make-actual-call function
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import asyncio
import json

async def test_make_actual_call():
    try:
        from main import make_actual_call
        
        class MockRequest:
            def __init__(self, json_data):
                self._json_data = json_data
                
            async def json(self):
                return self._json_data
        
        # Create mock request with candidate ID from MongoDB
        candidate_id = "690b857c80befccb653eb73a"
        mock_request = MockRequest({"candidate_id": candidate_id})
        
        print(f"🧪 Testing make_actual_call with candidate_id: {candidate_id}")
        print("=" * 50)
        
        # Call the function
        result = await make_actual_call(mock_request)
        
        print("📋 Result:")
        print(json.dumps(result, indent=2, default=str))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_make_actual_call())