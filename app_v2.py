import streamlit as st
import datetime
import uuid
import time
import threading
import os

# Optional Databricks imports with fallback
try:
    from databricks.sdk import WorkspaceClient
    from databricks import sql
    DATABRICKS_AVAILABLE = True
except ImportError:
    DATABRICKS_AVAILABLE = False
    print("Databricks SDK not available. Feedback will be stored locally instead of in database.")

# Alternative database options
try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

# You'll need to implement this function or replace with your model serving logic
def query_endpoint(endpoint_name, messages, max_tokens=128):
    """Query Databricks model serving endpoint - simple version"""
    try:
        import requests
        
        url = st.secrets['ENDPOINT_URL']
        
        headers = {
            "Authorization": f"Bearer {st.secrets['DATABRICKS_PAT']}",
            "Content-Type": "application/json"
        }
        
        request_data = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=request_data)
        response.raise_for_status()
        
        result = response.json()
        
        # Handle common response formats
        if "choices" in result and len(result["choices"]) > 0:
            return {"content": result["choices"][0]["message"]["content"]}
        elif "predictions" in result and len(result["predictions"]) > 0:
            return {"content": result["predictions"][0]}
        elif "content" in result:
            return {"content": result["content"]}
        else:
            return {"content": str(result)}
            
    except Exception as e:
        raise Exception(f"Model endpoint error: {str(e)}")

class StreamlitChatbot:
    def __init__(self, endpoint_name):
        self.endpoint_name = endpoint_name
        self._initialize_session_state()
        self._add_custom_css()
    
    def _initialize_session_state(self):
        """Initialize all session state variables"""
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'feedback_selection' not in st.session_state:
            st.session_state.feedback_selection = {}
        if 'feedback_comments' not in st.session_state:
            st.session_state.feedback_comments = {}
        if 'feedback_submitted' not in st.session_state:
            st.session_state.feedback_submitted = set()
        if 'input_key_counter' not in st.session_state:
            st.session_state.input_key_counter = 0
        if 'conversation_log_id' not in st.session_state:
            st.session_state.conversation_log_id = None
        if 'response_count' not in st.session_state:
            st.session_state.response_count = 0
    
    def _add_custom_css(self):
        """Add custom CSS styling"""
        st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
        
        /* Prevent ALL page scrolling */
        html, body {
            height: 100vh;
            overflow: hidden !important;
            margin: 0;
            padding: 0;
        }
        
        .main {
            height: 100vh !important;
            overflow: hidden !important;
        }
        
        .main .block-container {
            padding: 0 !important;
            max-width: 100% !important;
            height: 100vh !important;
            overflow: hidden !important;
        }
        
        /* FIXED HEADER - absolutely positioned at top */
        .fixed-header-section {
            position: fixed;
            top: 60px;
            left: 50%;
            transform: translateX(-50%);
            width: 90%;
            max-width: 1200px;
            background-color: white;
            z-index: 1000;
            padding: 1rem 0;
        }
        
        .chat-title {
            font-family: 'DM Sans', sans-serif;
            font-size: 28px;
            font-weight: 700;
            color: #1B3139;
            text-align: center;
            margin: 0 0 15px 0;
        }
        
        .info-note {
            background-color: #EEEDE9;
            border-left: 4px solid #1B3139;
            padding: 12px 16px;
            border-radius: 6px;
            font-size: 16px;
            color: #1B3139;
            margin: 0;
        }
        
        /* Spacer to push content below fixed header */
        .header-spacer {
            height: 200px;
        }
        
        /* Remove container scrolling - let page scroll naturally */
        [data-testid="stContainer"] {
            height: auto !important;
            max-height: none !important;
            overflow-y: visible !important;
            margin: 0 auto !important;
            width: 90% !important;
            max-width: 1200px !important;
            border: none !important;
        }
        
        /* Custom scrollbar */
        [data-testid="stContainer"]::-webkit-scrollbar {
            width: 8px;
        }
        
        [data-testid="stContainer"]::-webkit-scrollbar-track {
            background: #EEEDE9;
            border-radius: 4px;
        }
        
        [data-testid="stContainer"]::-webkit-scrollbar-thumb {
            background: #1B3139;
            border-radius: 4px;
        }
        
        [data-testid="stContainer"]::-webkit-scrollbar-thumb:hover {
            background: #2D4550;
        }
        
        .chat-message {
            font-family: 'DM Sans', sans-serif;
            padding: 15px 20px;
            border-radius: 20px;
            margin: 15px 0;
            font-size: 18px;
            line-height: 1.5;
            max-width: 80%;
            font-weight: 500;
        }
        
        .user-message {
            background-color: #FF3621;
            color: white;
            margin-left: auto;
            margin-right: 0;
        }
        
        .assistant-message {
            background-color: #1B3139;
            color: white;
            margin-left: 0;
            margin-right: auto;
        }
        
        .feedback-container {
            margin-top: 15px;
            padding: 15px;
            background-color: transparent;
            border-radius: 10px;
            font-size: 16px;
        }
        
        .feedback-thankyou {
            color: #00A972;
            font-weight: bold;
            margin-top: 8px;
            font-size: 16px;
        }
        
        .stButton > button {
            font-family: 'DM Sans', sans-serif;
            border-radius: 20px;
            font-size: 16px;
            white-space: nowrap !important;
            padding: 0.35rem 0.75rem !important;
        }
        
        /* FIXED INPUT BAR - absolutely positioned at bottom */
        .fixed-input-section {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: #F9F7F4;
            padding: 15px 20px;
            border-top: 2px solid #EEEDE9;
            z-index: 1000;
            box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
        }
        
        .stChatInput input {
            font-size: 18px !important;
            font-family: 'DM Sans', sans-serif;
        }
        
        .stTextArea textarea {
            font-size: 16px !important;
            font-family: 'DM Sans', sans-serif;
        }

        #new-chat-btn:hover {
            background-color: #f0f0f0 !important;
            transition: background-color 0.2s ease;
        }
        
        #new-chat-btn {
            transition: background-color 0.2s ease;
        }
        </style>
        """, unsafe_allow_html=True)
    
    def _call_model_endpoint(self, messages, max_tokens=128):
        """Call the model endpoint with error handling"""
        try:
            print('Calling model endpoint...')
            return query_endpoint(self.endpoint_name, messages, max_tokens)["content"]
        except Exception as e:
            print(f'Error calling model endpoint: {str(e)}')
            raise
    
    def _save_feedback_to_database(self, feedback_data):
        """Save feedback to database - simple version"""
        def insert_feedback():
            try:
                print("🛠️ Storing feedback...")
                from databricks import sql
                
                conn = sql.connect(
                    server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
                    http_path=st.secrets["DATABRICKS_HTTP_PATH"],
                    access_token=st.secrets["DATABRICKS_PAT"]
                )
                
                cursor = conn.cursor()
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                
                cursor.execute(f"""
                    INSERT INTO {st.secrets['FEEDBACK_TABLE']}
                    (id, timestamp, message, feedback, comment)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    feedback_data['id'],
                    feedback_data['timestamp'],
                    feedback_data['message'],
                    feedback_data['feedback'],
                    feedback_data['comment']
                ))
                
                conn.commit()
                cursor.close()
                conn.close()
                print("✅ Feedback committed to database")
                
            except Exception as e:
                import traceback
                print(f"⚠️ Could not store feedback: {e}")
                traceback.print_exc()
        
        threading.Thread(target=insert_feedback).start()

    def _save_conversation_log(self):
        """Upsert the entire chat history to the same feedback table"""
        def upsert_conversation(chat_history, conversation_id, response_count):
            try:
                from databricks import sql

                user_email = st.experimental_user.email if st.experimental_user else "unknown"
                
                conn = sql.connect(
                    server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
                    http_path=st.secrets["DATABRICKS_HTTP_PATH"],
                    access_token=st.secrets["DATABRICKS_PAT"]
                )
                cursor = conn.cursor()
    
                cursor.execute(f"""
                    MERGE INTO {st.secrets['FEEDBACK_TABLE']} AS target
                    USING (SELECT ? AS id) AS source
                    ON target.id = source.id
                    WHEN MATCHED THEN UPDATE SET 
                        timestamp = ?, 
                        message = ?, 
                        comment = ?
                    WHEN NOT MATCHED THEN INSERT (id, timestamp, message, feedback, comment)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    conversation_id,
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    str(chat_history),
                    f"Reponse(s): {response_count}",
                    conversation_id,
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    str(chat_history),
                    "Conversation_Log",
                    f"{user_email}: Reponse(s): {response_count}"
                ))
    
                conn.commit()
                cursor.close()
                conn.close()
    
            except Exception as e:
                import traceback
                print(f"⚠️ Could not upsert conversation: {e}")
                traceback.print_exc()

        if st.session_state.conversation_log_id is None:
            st.session_state.conversation_log_id = str(uuid.uuid4())

        st.session_state.response_count += 1
        threading.Thread(target=upsert_conversation, args=(st.session_state.chat_history, st.session_state.conversation_log_id, st.session_state.response_count)).start()
    
    def _render_message(self, message, index):
        """Render a single message with appropriate styling"""
        if message['role'] == 'user':
            st.markdown(f"""
            <div class="chat-message user-message">
                {message['content']}
            </div>
            """, unsafe_allow_html=True)
        else:
            formatted_content = message['content'].replace('\n', '<br>')
            st.markdown(f"""
            <div class="chat-message assistant-message">
                {formatted_content}
            </div>
            """, unsafe_allow_html=True)
            
            if index == len(st.session_state.chat_history) - 1:
                self._render_feedback_ui(index)
    
    def _render_feedback_ui(self, message_index):
        """Render feedback buttons and form"""
        if message_index in st.session_state.feedback_submitted:
            st.markdown('<div class="feedback-thankyou">Thank you for the feedback!</div>', 
                       unsafe_allow_html=True)
            return
        
        st.markdown('<div class="feedback-container">', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1, 6])
        
        with col1:
            if st.button("👍", key=f"thumbs_up_{message_index}", help="Good response"):
                st.session_state.feedback_selection[str(message_index)] = 'thumbs-up'
                st.rerun()
        
        with col2:
            if st.button("👎", key=f"thumbs_down_{message_index}", help="Poor response"):
                st.session_state.feedback_selection[str(message_index)] = 'thumbs-down'
                st.rerun()
        
        selected_feedback = st.session_state.feedback_selection.get(str(message_index))
        if selected_feedback:
            feedback_text = "👍 Positive" if selected_feedback == 'thumbs-up' else "👎 Negative"
            st.write(f"Selected: {feedback_text}")
            
            comment = st.text_area(
                "Optional comment:",
                key=f"comment_{message_index}",
                height=60,
                placeholder="Share your thoughts about this response..."
            )
            
            if st.button("Submit Feedback", key=f"submit_{message_index}", type="primary"):
                self._handle_feedback_submission(message_index, comment)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def _handle_feedback_submission(self, message_index, comment):
        """Handle feedback submission"""
        try:
            feedback_value = st.session_state.feedback_selection.get(str(message_index), 'none')

            user_email = st.experimental_user.email if st.experimental_user else "unknown"
            
            feedback_data = {
                'id': str(uuid.uuid4()),
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'message': str(st.session_state.chat_history),
                'feedback': feedback_value,
                'comment': f"{user_email}: {comment}" or f"{user_email}"
            }
            
            self._save_feedback_to_database(feedback_data)
            st.session_state.feedback_submitted.add(message_index)
            st.success("Thank you for your feedback!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Failed to submit feedback: {str(e)}")
            print(f"Feedback submission error: {e}")
    
    def _clear_chat(self):
        """Clear the chat history"""
        st.session_state.chat_history = []
        st.session_state.feedback_selection = {}
        st.session_state.feedback_comments = {}
        st.session_state.feedback_submitted = set()
        st.session_state.conversation_log_id = None
        st.session_state.input_key_counter += 1
        st.session_state.response_count = 0
        st.rerun()
    
    def render(self):
        """Main render method"""
    
        # If the hidden Streamlit trigger was clicked in the last run, clear now (same logic you had)
        if st.session_state.get('trigger_clear', False):
            st.session_state.trigger_clear = False
            self._clear_chat()
    
        # ---- FIXED HEADER with pure HTML button (unchanged look/placement) ----
        st.markdown(f'''
        <div class="fixed-header-section">
            <h2 class="chat-title">{st.secrets['PAGE_TITLE']}</h2>
            <div style="display: flex; gap: 10px; align-items: center; justify-content: center;">
                <div class="info-note" style="width: 600px;">
                    💬 Ask the rep below for handyman job information and estimates.
                </div>
                <button id="new-chat-btn"
                    style="padding: 0.35rem 0.75rem; background-color: white;
                           border: 1px solid #ddd; border-radius: 20px;
                           font-size: 16px; font-family: 'DM Sans', sans-serif;
                           cursor: pointer; white-space: nowrap;">
                    New Chat
                </button>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    
        # Reduced spacer to bring chat content closer to header
        st.markdown('<div style="height: 100px;"></div>', unsafe_allow_html=True)
    
        # ---- HIDDEN Streamlit button ----
        clear_trigger = st.button("trigger_clear_action", key="_hidden_clear_btn")
        
        # Hide the button using JavaScript component
        st.components.v1.html("""
        <script>
        (function hideButton() {
            const buttons = window.parent.document.querySelectorAll('button');
            buttons.forEach(btn => {
                if (btn.textContent.includes('trigger_clear')) {
                    btn.style.position = 'absolute';
                    btn.style.left = '-99999px';
                    btn.style.top = '-99999px';
                    btn.style.visibility = 'hidden';
                    btn.style.pointerEvents = 'auto';
                }
            });
        })();
        </script>
        """, height=0)
    
        # If the hidden Streamlit button fired, set the flag and rerun (same behavior you had)
        if clear_trigger:
            st.session_state.trigger_clear = True
            st.rerun()
    
        # ---- Chat content (unchanged) ----
        with st.container():
            if len(st.session_state.chat_history) == 0:
                st.markdown('''
                    <div style="text-align: center; color: #888; font-style: italic; padding: 40px 0;">
                        Start a conversation by typing your message below...
                    </div>
                ''', unsafe_allow_html=True)
            else:
                for i, message in enumerate(st.session_state.chat_history):
                    self._render_message(message, i)
    
        # ---- Fixed input bar (unchanged) ----
        st.markdown('<div class="fixed-input-section">', unsafe_allow_html=True)
        user_input = st.chat_input(
            placeholder="Type your message here... (Press Enter to send)",
            key=f"chat_input_{st.session_state.input_key_counter}"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
        # ---- JS: Attach event listener after page loads ----
        st.components.v1.html("""
        <script>
          const attachListener = () => {
            const newChatBtn = window.parent.document.getElementById('new-chat-btn');
            
            if (newChatBtn) {
              newChatBtn.addEventListener('click', function() {
                const allButtons = window.parent.document.querySelectorAll('button');
                let hiddenBtn = null;
                
                for (let btn of allButtons) {
                  if (btn.textContent.includes('trigger_clear')) {
                    hiddenBtn = btn;
                    break;
                  }
                }
                
                if (hiddenBtn) {
                  hiddenBtn.click();
                }
              });
            } else {
              setTimeout(attachListener, 100);
            }
          };
          
          setTimeout(attachListener, 1000);
        </script>
        """, height=0)
    
        # ---- Handle user input (unchanged) ----
        if user_input and user_input.strip():
            st.session_state.chat_history.append({'role': 'user', 'content': user_input.strip()})
            st.session_state.input_key_counter += 1
    
            with st.spinner("Thinking..."):
                try:
                    assistant_response = self._call_model_endpoint(st.session_state.chat_history)
                    st.session_state.chat_history.append({'role': 'assistant', 'content': assistant_response})
                    self._save_conversation_log()
                except Exception as e:
                    st.session_state.chat_history.append({'role': 'assistant', 'content': f'Error: {str(e)}'})
                    self._save_conversation_log()
    
            st.rerun()

def main():
    st.set_page_config(
        page_title="Ace Handyman Services Chat",
        page_icon="🔧",
        layout="centered",
        initial_sidebar_state="collapsed"
    )
    
    endpoint_name = st.secrets.get("DATABRICKS_ENDPOINT_NAME", "your_endpoint_name")
    chatbot = StreamlitChatbot(endpoint_name)
    chatbot.render()

def show_setup_instructions():
    with st.sidebar:
        st.header("Setup Instructions")
        st.subheader("1. Install Dependencies")
        st.code("""pip install streamlit databricks-sdk databricks-sql-connector""")
        st.subheader("2. Environment Variables")
        st.code("""
DATABRICKS_SERVER_HOSTNAME=your_hostname
DATABRICKS_HTTP_PATH=your_http_path  
DATABRICKS_ACCESS_TOKEN=your_token
        """)

if __name__ == "__main__":
    show_setup_instructions()
    main()
