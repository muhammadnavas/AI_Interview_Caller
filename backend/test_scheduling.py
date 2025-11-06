#!/usr/bin/env python3
"""
Test the get_candidate_scheduling_status function directly
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_scheduling_status():
    try:
        from main import get_candidate_scheduling_status
        
        candidate_id = "690b857c80befccb653eb73a"
        
        print(f"🧪 Testing scheduling status for candidate: {candidate_id}")
        
        result = get_candidate_scheduling_status(candidate_id)
        
        print("✅ Success! Result:")
        print(result)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_scheduling_status()