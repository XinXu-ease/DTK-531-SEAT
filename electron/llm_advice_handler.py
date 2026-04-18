#!/usr/bin/env python3
"""
Handler script for getting LLM advice.
Called from Electron via IPC, outputs JSON result.

Current data structure:
- sensor_data table: created by mqtt_infer.py, contains raw recording data
- daily_segments table: expected by llm_utils.py, but not yet implemented

This script queries available data and calls generate_llm_advice.
"""
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import llm_utils
sys.path.insert(0, str(Path(__file__).parent))

def get_advice_from_available_data(db_path, user_id):
    """
    Query available data from sensor_data table and generate advice.
    Falls back to mock data if no database exists or no data available.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Try to query sensor_data table (real recorded data)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sensor_data'")
        if cursor.fetchone():
            # Query today's data
            today = datetime.now().date().isoformat()
            cursor.execute("""
                SELECT 
                  COUNT(*) as record_count,
                  SUM(CASE WHEN blc_bad = 1 THEN 1 ELSE 0 END) as blc_count,
                  CAST(COUNT(*) * 0.1 AS REAL) as sit_duration_sec,
                  CAST(SUM(CASE WHEN blc_bad = 1 THEN 1 ELSE 0 END) * 0.1 AS REAL) as blc_duration_sec
                FROM sensor_data
                WHERE user_id = ? AND DATE(datetime(timestamp, 'unixepoch')) = ?
            """, (user_id, today))
            
            row = cursor.fetchone()
            if row and row[0] > 0:  # if record_count > 0
                conn.close()
                record_count, blc_count, sit_time, blc_time = row
                return {
                    "sit_time_minutes": round(sit_time / 60, 1) if sit_time else 0,
                    "blc_count": int(blc_count) if blc_count else 0,
                    "blc_time_minutes": round(blc_time / 60, 1) if blc_time else 0,
                    "source": "sensor_data"
                }
        
        conn.close()
        
    except Exception as e:
        print(f"Database query error: {e}", file=sys.stderr)
    
    # Fallback: No data available
    return None

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing user_id argument"}))
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    try:
        # Connect to SQLite database
        db_path = Path(__file__).parent.parent / "pi" / "chair.db"
        
        # Try to get advice from available data
        payload = get_advice_from_available_data(db_path, user_id)
        
        if not payload:
            print(json.dumps({
                "success": False,
                "error": f"No sensor data recorded for user '{user_id}' today. Please enable recording in Dashboard."
            }))
            sys.exit(0)
        
        # Now try to generate LLM advice
        # Import here to handle missing dependencies gracefully
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from llm_utils import generate_llm_advice
            advice = generate_llm_advice(payload)
        except Exception as llm_error:
            # Fallback to simple advice if LLM fails
            print(f"LLM call error: {llm_error}", file=sys.stderr)
            advice = f"Based on today's data: {int(payload['sit_time_minutes'])} min sitting, {int(payload['blc_count'])} balance events."
        
        # Output as JSON
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
