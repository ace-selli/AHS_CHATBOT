import streamlit as st
import requests
import threading
from datetime import datetime
import databricks.sql

# Custom CSS to match Dash app style
def add_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'DM Sans', sans-serif;
            background-color: #F9F7F4;
        }
        .chat-container {
            max-width: 800px;
            margin: 0 auto;
            background-color: #FFFFFF;
            border-radius: 10px;
            padding: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .chat-title {
            font-size: 24px;
            font-weight: 700;
            color: #1B3139;
            text-align: center;
        }
        .chat-history {
            flex-grow: 1;
            overflow-y: auto;
            margin-bottom: 1rem;
            padding-right: 1rem;
            max-height: 60vh;
        }
        .user-message {
            background-color: #FF3621;
            color: white;
            padding: 12px;
            border-radius: 20px;
            margin-bottom: 10px;
            max-width: 70%;
            align-self: flex-end;
        }
        .assistant-message {
            background-color: #1B3139;
            color: white;
            padding: 12px;
            border-radius: 20px;
            margin-bottom: 10px;
            max-width: 70%;
            align-self: flex-start;
        }
        .typing-indicator {
            background-color: #2D4550;
            color: #EEEDE9;
            border-radius: 20px;
            padding: 10px;
            display: inline-flex;
            gap: 5px;
            align-items: center;
            max-width: 120px;
        }
        .typing-dot {
            width: 8px;
            height: 8px;
            background-color: #EEEDE9;
            border-radius: 50%;
            animation: blink 1.2s infinite;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes blink {
            0% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
            100% { transform: translateY(0); }
        }

        .chat-input {
            border-radius: 20px;
        }
        .input-row {
            display: flex;
            gap: 10px;
        }
        .send-btn {
            background-color: #00A972;
            border: none;
            color: white;
            border-radius: 20px;
        }
        .clear-btn {
            background-color: #98102A;
            border: none;
            color: white;
            border-radius: 20px;
        }
    </style>
    """, unsafe_allow_html=True)

# Page setup
st.set_page_config(page_title="Field Staff Chatbot", layout="wide")
add_custom_css()

st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
st.markdown("<h2 class='chat-title'>*** Services Customer Rep</h2>", unsafe_allow_html=True)
st.markdown("Note: Ask the below rep for handyman job information.")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_feedback" not in st.session_state:
    st.session_state.pending_feedback = None

# Feedback handling function
def store_feedback(question, answer, score, comment, category):
    try:
        conn = databricks.sql.connect(
            server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
            http_path=st.secrets["DATABRICKS_HTTP_PATH"],
            access_token=st.secrets["DATABRICKS_PAT"]
        )
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ***.default.feedback
            (question, answer, score, comment, timestamp, category, user)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            question, answer, score, comment,
            datetime.now().isoformat(), category, ""
        ))
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Could not store feedback: {e}")

# Chat history
with st.container():
    for idx, msg in enumerate(st.session_state.messages):
        role_class = "user-message" if msg["role"] == "user" else "assistant-message"
        st.markdown(f"<div class='{role_class}'>{msg['content']}</div>", unsafe_allow_html=True)

        if msg["role"] == "assistant":
            question_idx = idx - 1
            question = (
                st.session_state.messages[question_idx]["content"]
                if question_idx >= 0 else ""
            )
            feedback_key = f"feedback_{idx}"
            if st.session_state.get(feedback_key) != "submitted":
                with st.container():
                    st.write("Was this answer helpful?")
                    col1, col2 = st.columns(2)
                    if col1.button("👍 Yes", key=f"yes_{idx}"):
                        comment = st.text_area("Comments (optional)", key=f"comment_yes_{idx}")
                        threading.Thread(target=store_feedback, args=(question, msg["content"], "thumbs_up", comment, "")).start()
                        st.session_state[feedback_key] = "submitted"
                        st.success("🎉 Thanks for your feedback!")
                    if col2.button("👎 No", key=f"no_{idx}"):
                        category = st.selectbox("What was the issue?", ["inaccurate", "outdated", "too long", "too short", "other"], key=f"cat_{idx}")
                        comment = st.text_area("How can we improve?", key=f"comment_no_{idx}")
                        if st.button("Submit Feedback 👎", key=f"submit_no_{idx}"):
                            threading.Thread(target=store_feedback, args=(question, msg["content"], "thumbs_down", comment, category)).start()
                            st.session_state[feedback_key] = "submitted"
                            st.success("🎉 Thanks for your feedback!")

# Input field and buttons
user_input = st.text_area("Your message", placeholder="Type your message here...", height=80, key="input_box")

col1, col2 = st.columns([1, 1])
if col1.button("Send", use_container_width=True):
    if user_input.strip():
        st.session_state.messages.append({"role": "user", "content": user_input.strip()})
        st.session_state["input_box"] = ""

        with st.spinner("Typing..."):
            headers = {
                "Authorization": f"Bearer {st.secrets['DATABRICKS_PAT']}",
                "Content-Type": "application/json"
            }
            payload = {"messages": st.session_state.messages}
            try:
                response = requests.post(
                    url=st.secrets["ENDPOINT_URL"],
                    headers=headers,
                    json=payload,
                    timeout=20
                )
                result = response.json()
                reply = result.get("choices", [{}])[0].get("message", {}).get("content", "⚠️ No response.")
            except Exception as e:
                reply = f"❌ Error: {e}"

            st.session_state.messages.append({"role": "assistant", "content": reply})

if col2.button("Clear Chat", use_container_width=True):
    st.session_state.messages = []

st.markdown("</div>", unsafe_allow_html=True)
