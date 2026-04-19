#!/usr/bin/env python3
"""
Handler script for getting LLM advice.
Called from Electron via IPC, outputs JSON result.

Queries chair.db from remote Pi via SSH.
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import llm_utils
sys.path.insert(0, str(Path(__file__).parent))

# Pi configuration
PI_HOST = "172.20.4.137"
PI_USER = "dti"
PI_DB_PATH = "/home/dti/Desktop/DTK-531-SEAT/pi/chair.db"

def query_pi_database(user_id):
    """
    Query chair.db on Pi via SSH and get today's data for user.
    Returns dict with metrics or None if no data.
    """
    try:
        today = datetime.now().date().isoformat()
        
        # SQLite query to run on Pi
        sql_query = f"""SELECT 
  COUNT(*) as record_count,
  SUM(CASE WHEN blc_bad = 1 THEN 1 ELSE 0 END) as blc_count,
  CAST(COUNT(*) * 0.1 AS REAL) as sit_duration_sec,
  CAST(SUM(CASE WHEN blc_bad = 1 THEN 1 ELSE 0 END) * 0.1 AS REAL) as blc_duration_sec
FROM sensor_data
WHERE user_id = '{user_id}' AND DATE(datetime(timestamp, 'unixepoch')) = '{today}'
"""
        
        # Run SQLite query remotely via SSH
        print(f"[DEBUG] Querying Pi database via SSH...", file=sys.stderr)
        
        result = subprocess.run(
            ["ssh", f"{PI_USER}@{PI_HOST}", "sqlite3", PI_DB_PATH],
            input=sql_query,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"[DEBUG] SSH query failed: {result.stderr}", file=sys.stderr)
            return None
        
        # Parse result
        output = result.stdout.strip()
        if not output:
            print(f"[DEBUG] No query results from Pi", file=sys.stderr)
            return None
        
        parts = output.split('|')
        if len(parts) < 4:
            print(f"[DEBUG] Unexpected query result format: {output}", file=sys.stderr)
            return None
        
        record_count = int(parts[0])
        blc_count = int(float(parts[1])) if parts[1] else 0
        sit_time = float(parts[2]) if parts[2] else 0
        blc_time = float(parts[3]) if parts[3] else 0
        
        if record_count == 0:
            print(f"[DEBUG] No records for user {user_id} today", file=sys.stderr)
            return None
        
        return {
            "sit_time_minutes": round(sit_time / 60, 1),
            "blc_count": blc_count,
            "blc_time_minutes": round(blc_time / 60, 1),
            "source": "database_ssh"
        }
        
    except subprocess.TimeoutExpired:
        print(f"[DEBUG] SSH query timeout", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[DEBUG] SSH query error: {e}", file=sys.stderr)
        return None

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing user_id argument"}))
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    try:
        # Query Pi database via SSH
        print(f"[DEBUG] Fetching today's data for user {user_id}...", file=sys.stderr)
        payload = query_pi_database(user_id)
        
        if not payload:
            print(json.dumps({
                "success": False,
                "error": f"No sensor data recorded for user '{user_id}' today. Please enable recording in Dashboard."
            }))
            sys.exit(0)
        
        # Now try to generate LLM advice
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from llm_utils import generate_llm_advice
            advice = generate_llm_advice(payload)
        except Exception as llm_error:
            print(f"LLM call error: {llm_error}", file=sys.stderr)
            advice = f"Based on today's data: {int(payload['sit_time_minutes'])} min sitting, {int(payload['blc_count'])} balance events."
        
        print(json.dumps({
            "success": True,
            "advice": advice,
            "payload": payload
        }))
        sys.exit(0)
        
    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": f"Failed to get advice: {str(e)}"
        }))
        sys.exit(1)

if __name__ == "__main__":
    main()
