#!/usr/bin/env python3
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path(__file__).parent / "pi" / "chair.db"

print(f"Checking database at: {db_path}")
print(f"Database exists: {db_path.exists()}")

if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\nTables in database: {tables}")
    
    # Check sensor_data content
    if 'sensor_data' in tables:
        cursor.execute("SELECT COUNT(*) FROM sensor_data")
        count = cursor.fetchone()[0]
        print(f"Total records in sensor_data: {count}")
        
        if count > 0:
            cursor.execute("SELECT DISTINCT user_id FROM sensor_data")
            user_ids = [row[0] for row in cursor.fetchall()]
            print(f"Unique user_ids in database: {user_ids}")
            
            # Show sample records
            today = datetime.now().date().isoformat()
            cursor.execute(f"""
                SELECT user_id, seattype, timestamp FROM sensor_data
                WHERE DATE(datetime(timestamp, 'unixepoch')) = '{today}'
                ORDER BY timestamp DESC LIMIT 5
            """)
            print(f"\nSample records for today ({today}):")
            for row in cursor.fetchall():
                print(f"  user_id={row[0]}, seattype={row[1]}, time={datetime.fromtimestamp(row[2])}")
    
    conn.close()
else:
    print("Database does not exist yet")
