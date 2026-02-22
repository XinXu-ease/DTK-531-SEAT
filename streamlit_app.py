import json
import time
from pathlib import Path
import paho.mqtt.client as mqtt
import streamlit as st
import sqlite3
from llm_utils import build_llm_payload, generate_llm_advice

st.set_page_config(page_title="Seat Posture Simulator", page_icon=":chair:", layout="centered")

@st.cache_resource
def get_mqtt_client():
    c = mqtt.Client()
    c.connect("test.mosquitto.org", 1883, 60)
    c.loop_start()
    return c

def sync_active_user(client, user_id: str):
    user_id = (user_id or "").strip()
    if not user_id:
        return
    last = st.session_state.get("last_synced_user_id")
    now = time.time()
    last_sent_at = float(st.session_state.get("last_synced_user_at", 0.0))
    should_publish = (last != user_id) or (now - last_sent_at >= 5.0)
    if should_publish:
        client.publish(
            "chair/user",
            json.dumps({"user_id": user_id}),
            qos=1,
            retain=True,
        )
        st.session_state["last_synced_user_id"] = user_id
        st.session_state["last_synced_user_at"] = now

# get data
conn = sqlite3.connect("chair.db", check_same_thread=False)

TIMETHRES_SIT_SEC = 5   # backend 5s -> UI 15min
TIMETHRES_BLC_SEC = 5   # backend 5s warning threshold
UI_MIN_PER_SEC = 15 / TIMETHRES_SIT_SEC  # 3 min per backend second
RESULT_FILE = Path("latest_result.json")

if "seattype" not in st.session_state:
    st.session_state.seattype = False
if "blc_bad" not in st.session_state:
    st.session_state.blc_bad = False
if "time_sit" not in st.session_state:
    st.session_state.time_sit = 0.0
if "time_blc" not in st.session_state:
    st.session_state.time_blc = 0.0


def load_latest_result(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None

    return {
        "seattype": bool(int(data.get("seattype", 0))),
        "blc_bad": bool(int(data.get("blc_bad", 0))),
        "time_sit": float(data.get("time_sit", 0.0)),
        "time_blc": float(data.get("time_blc", 0.0)),
    }


latest = load_latest_result(RESULT_FILE)
if latest is not None:
    st.session_state.seattype = latest["seattype"]
    st.session_state.blc_bad = latest["blc_bad"]
    st.session_state.time_sit = latest["time_sit"]
    st.session_state.time_blc = latest["time_blc"]

with st.sidebar:
    st.header("Live Status")
    user_id = st.text_input("User ID", key="user_id")
    st.write(f"source file: `{RESULT_FILE}`")
    st.write(f"seattype: `{st.session_state.seattype}`")
    st.write(f"blc_bad: `{st.session_state.blc_bad}`")

client = get_mqtt_client()
sync_active_user(client, user_id)


tab1, tab2 = st.tabs(["Seating Behavior Reminder", "Calibration Mode"])

with tab1:
    st.title("Seating Behavior Reminder")
    st.caption("Reading seattype / blc_bad from latest_result.json")

    # ---- UI mapping ----
    time_sit_ui_min = st.session_state.time_sit * UI_MIN_PER_SEC

    if time_sit_ui_min < 15:
        emoji = "😄"
    elif time_sit_ui_min < 45:
        emoji = "😐"
    else:
        emoji = "😭"

    st.markdown(
        """
        <style>
        .emoji {
            font-size: 72px;
            text-align: center;
            margin: 16px 0;
        }
        .shake {
            display: inline-block;
            animation: shake 0.45s infinite;
        }
        @keyframes shake {
            0%   { transform: translate(0, 0) rotate(0deg); }
            25%  { transform: translate(-3px, 1px) rotate(-2deg); }
            50%  { transform: translate(3px, -1px) rotate(2deg); }
            75%  { transform: translate(-2px, 1px) rotate(-1deg); }
            100% { transform: translate(0, 0) rotate(0deg); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.time_blc > TIMETHRES_BLC_SEC and st.session_state.seattype:
        st.markdown(f"<div class='emoji'><span class='shake'>{emoji}</span></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='emoji'>{emoji}</div>", unsafe_allow_html=True)

    mcol1, mcol2 = st.columns(2)
    mcol1.metric("time_sit (backend sec)", f"{st.session_state.time_sit:.1f}")
    mcol2.metric("time_sit (UI min)", f"{time_sit_ui_min:.0f}")

    mcol3, mcol4 = st.columns(2)
    mcol3.metric("time_blc (sec)", f"{st.session_state.time_blc:.1f}")
    mcol4.metric("timethres_blc (sec)", TIMETHRES_BLC_SEC)

    st.info(
        "0-15min smile, 15-45min neutral, >45min cry.\n\n"
        "backend 5s = UI 15min."
    )

    st.divider()
    st.subheader("LLM Advice")

    try:
        payload = build_llm_payload(conn, user_id)
    except Exception as e:
        payload = None
        st.error(f"Failed to build payload: {e}")

    if payload:
        st.json(payload)

        if st.button("Generate LLM Advice", key="gen_llm_advice"):
            with st.spinner("Generating..."):
                try:
                    advice = generate_llm_advice(payload)
                    st.write(advice)
                except Exception as e:
                    st.error(f"LLM generation failed: {e}")
    else:
        st.warning("No data yet.")

with tab2:
    st.title("Calibration Mode")

    duration = st.number_input("Duration (seconds)", min_value=1, max_value=60, value=10)

    ccol1, ccol2 = st.columns(2)

    with ccol1:
        if st.button("Record 10s Label 0 (Balanced)"):
            cmd = {"user_id": user_id, "label": 0, "duration": duration}
            client.publish("chair/calib", json.dumps(cmd))
            st.success("Sent calibration start")

    with ccol2:
        if st.button("Record 10s Label 1 (Unbalanced)"):
            cmd = {"user_id": user_id, "label": 1, "duration": duration}
            client.publish("chair/calib", json.dumps(cmd))
            st.success("Sent calibration start")

# Refresh once per second.
time.sleep(1)
st.rerun()
