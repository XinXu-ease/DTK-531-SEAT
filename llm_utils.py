import sqlite3
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# LLM 
TOKEN = os.getenv("LITELLM_TOKEN")
BASE_URL = "https://litellm.oit.duke.edu/v1"
MODEL = "GPT 4.1 Mini"
if not TOKEN:
    raise RuntimeError("Missing LITELLM_TOKEN. Put it in .env and ensure .env is not committed.")

def build_llm_payload(conn: sqlite3.Connection, user_id: str):
    today = datetime.now().date().isoformat()
    row = conn.execute(
        """
        SELECT
          COALESCE(SUM(sit_duration_sec), 0.0),
          COALESCE(SUM(blc_count), 0),
          COALESCE(SUM(blc_duration_sec), 0.0)
        FROM daily_segments
        WHERE user_id=? AND date=?
        """,
        (user_id, today),
    ).fetchone()

    if not row:
        return None

    sit_time, blc_count, blc_time = row
    if float(sit_time) <= 0 and int(blc_count) <= 0 and float(blc_time) <= 0:
        return None

    return {
        "sit_time_minutes": round(sit_time / 60, 1),
        "blc_count": int(blc_count),
        "blc_time_minutes": round(blc_time / 60, 1),
    }

def generate_llm_advice(payload: dict):
    token = os.getenv("LITELLM_TOKEN")
    if not token:
        raise RuntimeError("Missing LITELLM_TOKEN")

    client = OpenAI(api_key=token, base_url=BASE_URL)

    prompt = f"""
User posture data summary:
- Total sitting time: {payload['sit_time_minutes']} minutes
- Unbalanced events: {payload['blc_count']}
- Unbalanced time: {payload['blc_time_minutes']} minutes

Please provide:
1) A concise behavioral summary
2) A practical ergonomic suggestion
"""

    resp = client.responses.create(model=MODEL, input=prompt)
    return resp.output_text
