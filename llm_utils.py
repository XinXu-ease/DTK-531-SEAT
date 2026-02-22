import json
import sqlite3
import os
from openai import OpenAI

# LLM 
TOKEN = os.getenv("LITELLM_TOKEN")
BASE_URL = "https://litellm.oit.duke.edu/v1"
MODEL = "GPT 4.1 Mini"
if not TOKEN:
    raise RuntimeError("Missing LITELLM_TOKEN. Put it in .env and ensure .env is not committed.")

def build_llm_payload(conn: sqlite3.Connection, user_id: str):
    row = conn.execute("""
      SELECT sit_time_sec, blc_count, blc_time_sec, pressure_json
      FROM daily_summary
      WHERE user_id=?
      ORDER BY updated_at DESC
      LIMIT 1
    """, (user_id,)).fetchone()

    if not row:
        return None

    sit_time, blc_count, blc_time, pressure_json = row
    pressure_data = json.loads(pressure_json)

    return {
        "sit_time_minutes": round(sit_time / 60, 1),
        "blc_count": int(blc_count),
        "blc_time_minutes": round(blc_time / 60, 1),
        "pressure_samples": pressure_data[:200],  # 控制长度
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
- Sample pressure data: {payload['pressure_samples']}

Please provide:
1) A concise behavioral summary
2) A practical ergonomic suggestion
"""

    resp = client.responses.create(model=MODEL, input=prompt)
    return resp.output_text
