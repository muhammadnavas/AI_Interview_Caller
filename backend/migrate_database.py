"""
Database Migration Script
Migrate existing database to new comprehensive schema
"""
import sqlite3
import json
from datetime import datetime

def migrate_database():
    """Migrate existing database to new comprehensive schema"""
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    
    print("Starting database migration...")
    
    try:
        # Check if new tables exist, create them if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                name TEXT,
                phone TEXT,
                email TEXT,
                position TEXT,
                company TEXT,
                created_at TEXT,
                updated_at TEXT,
                total_attempts INTEGER DEFAULT 0,
                last_contact_date TEXT,
                status TEXT DEFAULT 'active'
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT,
                call_sid TEXT,
                phone_number TEXT,
                initiated_at TEXT,
                twilio_status TEXT,
                call_duration INTEGER,
                call_direction TEXT,
                call_price REAL,
                error_code TEXT,
                error_message TEXT,
                outcome TEXT,
                notes TEXT,
                FOREIGN KEY (candidate_id) REFERENCES candidates (id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interview_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT,
                call_sid TEXT,
                scheduled_slot TEXT,
                scheduled_at TEXT,
                interview_date TEXT,
                interview_time TEXT,
                status TEXT DEFAULT 'scheduled',
                confirmation_email_sent BOOLEAN DEFAULT 0,
                reminder_sent BOOLEAN DEFAULT 0,
                interview_completed BOOLEAN DEFAULT 0,
                feedback_collected BOOLEAN DEFAULT 0,
                notes TEXT,
                FOREIGN KEY (candidate_id) REFERENCES candidates (id),
                FOREIGN KEY (call_sid) REFERENCES conversation_sessions (call_sid)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                log_level TEXT,
                component TEXT,
                action TEXT,
                details TEXT,
                call_sid TEXT,
                candidate_id TEXT
            )
        """)
        
        # Check if conversation_sessions needs new columns
        cursor.execute("PRAGMA table_info(conversation_sessions)")
        existing_columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = {
            'candidate_id': 'TEXT',
            'candidate_name': 'TEXT',
            'position': 'TEXT', 
            'company': 'TEXT',
            'conversation_stage': 'TEXT',
            'email_sent': 'BOOLEAN DEFAULT 0',
            'email_sent_at': 'TEXT',
            'total_turns': 'INTEGER DEFAULT 0',
            'success_score': 'REAL',
            'ai_confidence_avg': 'REAL',
            'call_quality': 'TEXT',
            'notes': 'TEXT'
        }
        
        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE conversation_sessions ADD COLUMN {col_name} {col_type}")
                    print(f"Added column: {col_name}")
                except Exception as e:
                    print(f"Column {col_name} already exists or error: {e}")
        
        # Check conversation_turns table
        cursor.execute("PRAGMA table_info(conversation_turns)")
        turn_columns = [column[1] for column in cursor.fetchall()]
        
        turn_new_columns = {
            'conversation_stage': 'TEXT',
            'action_taken': 'TEXT'
        }
        
        for col_name, col_type in turn_new_columns.items():
            if col_name not in turn_columns:
                try:
                    cursor.execute(f"ALTER TABLE conversation_turns ADD COLUMN {col_name} {col_type}")
                    print(f"Added turn column: {col_name}")
                except Exception as e:
                    print(f"Turn column {col_name} already exists or error: {e}")
        
        # Migrate existing data
        cursor.execute("SELECT call_sid, turns_json FROM conversation_sessions WHERE turns_json IS NOT NULL")
        sessions = cursor.fetchall()
        
        for call_sid, turns_json in sessions:
            try:
                turns = json.loads(turns_json) if turns_json else []
                total_turns = len(turns)
                
                if total_turns > 0:
                    avg_confidence = sum(turn.get('confidence_score', 0) for turn in turns) / total_turns
                    cursor.execute("""
                        UPDATE conversation_sessions 
                        SET total_turns = ?, ai_confidence_avg = ?, notes = ?
                        WHERE call_sid = ?
                    """, (total_turns, avg_confidence, f"Migrated session with {total_turns} turns", call_sid))
                    
                print(f"Migrated session {call_sid} with {total_turns} turns")
            except Exception as e:
                print(f"Error migrating session {call_sid}: {e}")
        
        # Add sample system log
        cursor.execute("""
            INSERT INTO system_logs (timestamp, log_level, component, action, details)
            VALUES (?, 'INFO', 'DATABASE', 'MIGRATION_COMPLETED', 'Database successfully migrated to comprehensive schema')
        """, (datetime.now().isoformat(),))
        
        conn.commit()
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()