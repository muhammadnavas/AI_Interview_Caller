#!/usr/bin/env python3
"""
Script to seed a candidate into MongoDB for testing.
"""

import os
from pymongo import MongoClient
from decouple import config

def seed_candidate():
    """Seed a test candidate into MongoDB"""
    try:
        mongodb_uri = config("MONGODB_URI", default=None)
        if not mongodb_uri:
            print("MONGODB_URI not configured")
            return

        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db_name = config("MONGODB_DB", default="ai_interview_schedule")
        coll_name = config("MONGODB_COLLECTION", default="candidates")

        db = client[db_name]
        coll = db[coll_name]

        candidate = {
            "name": "Muhammad Navas",
            "phone": "+917975091087",
            "email": "muhammadnavas012@gmail.com",
            "position": "Software Engineer",
            "company": "TechCorp",
        }

        # Upsert by email
        result = coll.replace_one({"email": candidate["email"]}, candidate, upsert=True)
        
        if result.upserted_id:
            print(f"Inserted new candidate with ID: {result.upserted_id}")
        else:
            print(f"Updated existing candidate")

        print(f"Candidate: {candidate}")

    except Exception as e:
        print(f"Error seeding candidate: {e}")

if __name__ == "__main__":
    seed_candidate()