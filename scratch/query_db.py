import sqlite3
import os
from pathlib import Path

db_path = Path(os.environ.get("APPDATA", "")) / "OmniVoice" / "omnivoice.db"
print(f"Checking database at: {db_path}")

if db_path.exists():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        print("Tables in database:", tables)
        
        # Look for a voice/speaker profile table
        for table in tables:
            if "voice" in table.lower() or "profile" in table.lower() or "speaker" in table.lower() or "character" in table.lower():
                print(f"\n--- Columns in table '{table}': ---")
                cursor.execute(f"PRAGMA table_info({table});")
                for col in cursor.fetchall():
                    print(f"  {col[1]} ({col[2]})")
                
                print(f"\n--- First 5 rows in '{table}': ---")
                cursor.execute(f"SELECT * FROM {table} LIMIT 5;")
                rows = cursor.fetchall()
                for r in rows:
                    print(" ", r)
        
        conn.close()
    except Exception as e:
        print(f"Error querying database: {e}")
else:
    print("Database file does not exist.")
