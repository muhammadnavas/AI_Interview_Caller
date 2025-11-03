# MongoDB Migration Stubs
# This file contains stub implementations to replace SQLite-dependent functions
# These are temporary until full MongoDB implementations are created

def stub_candidate_limits():
    """Stub for candidate limits endpoint"""
    return {
        "message": "SQLite replaced with MongoDB - this endpoint needs MongoDB implementation",
        "candidates": [],
        "total": 0
    }

def stub_conversations():
    """Stub for conversations endpoint"""
    return {
        "message": "SQLite replaced with MongoDB - this endpoint needs MongoDB implementation", 
        "conversations": [],
        "total": 0
    }

def stub_analytics():
    """Stub for analytics endpoint"""
    return {
        "message": "SQLite replaced with MongoDB - use /comprehensive-analytics instead",
        "total_calls": 0,
        "successful_interviews": 0
    }

# Add other stub functions as needed