import json
import time
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Seat Posture Simulator", page_icon=":chair:", layout="centered")

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

st.title("Seating Behavior Reminder")
st.caption("Reading seattype / blc_bad from latest_result.json")

with st.sidebar:
    st.header("Live Status")
    st.write(f"source file: `{RESULT_FILE}`")
    st.write(f"seattype: `{st.session_state.seattype}`")
    st.write(f"blc_bad: `{st.session_state.blc_bad}`")

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

col1, col2 = st.columns(2)
col1.metric("time_sit (backend sec)", f"{st.session_state.time_sit:.1f}")
col2.metric("time_sit (UI min)", f"{time_sit_ui_min:.0f}")

col3, col4 = st.columns(2)
col3.metric("time_blc (sec)", f"{st.session_state.time_blc:.1f}")
col4.metric("timethres_blc (sec)", TIMETHRES_BLC_SEC)

st.info(
    "0-15min smile, 15-45min neutral, >45min tired.\n\n"
    "backend 5s = UI 15min."
)

# Refresh once per second.
time.sleep(1)
st.rerun()
