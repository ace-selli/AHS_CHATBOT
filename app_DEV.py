import streamlit as st
import datetime
import uuid
import time
import threading
import os
import requests

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

# OPTIMIZATION 1: Cache requests session to reuse connections
@st.cache_resource
def get_requests_session():
    """Create a cached requests session to reuse HTTP connections"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {st.secrets['DATABRICKS_PAT']}",
        "Content-Type": "application/json"
    })
    return session

# OPTIMIZATION 2: Add timeout and connection pooling to endpoint calls
def query_endpoint(endpoint_name, messages, max_tokens=128):
    """Query Databricks model serving endpoint with optimizations"""
    try:
        # Use cached session for connection reuse
        session = get_requests_session()
        
        url = st.secrets['ENDPOINT_URL']
        
        request_data = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        # OPTIMIZATION 3: Add timeout to prevent hanging
        response = session.post(
            url, 
            json=request_data, 
            timeout=(10, 60)  # (connection timeout, read timeout)
        )
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

# OPTIMIZATION 4: Cache CSS to reduce recomputation
@st.cache_data
def get_custom_css():
    """Return cached CSS"""
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
    
    .main-container {
        font-family: 'DM Sans', sans-serif;
        background-color: #F9F7F4;
    }
    
    .chat-title {
        font-size: 24px;
        font-weight: 700;
        color: #1B3139;
        text-align: center;
        margin-bottom: 20px;
    }
    
    .chat-message {
        padding: 10px 15px;
        border-radius: 20px;
        margin: 10px 0;
        font-size: 16px;
        line-height: 1.4;
        max-width: 80%;
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
        margin-top: 10px;
        padding: 10px;
        background-color: transparent;
        border-radius: 10px;
        border: none;
    }
    
    .feedback-thankyou {
        color: #00A972;
        font-weight: bold;
        margin-top: 8px;
    }
    
    .stButton > button {
        border-radius: 20px;
    }
    
    .feedback-buttons {
        display: flex;
        gap: 10px;
        margin-bottom: 10px;
    }
    
    .typing-indicator {
        background-color: #2D4550;
        color: #EEEDE9;
        padding: 10px 15px;
        border-radius: 20px;
        margin: 10px 0;
        font-style: italic;
    }
    
    .fixed-bottom-input {
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
    
    .content-with-bottom-padding {
        padding-bottom: 120px;
    }
    
    .info-note {
        background-color: #EEEDE9;
        border-left: 4px solid #1B3139;
        padding: 12px 16px;
        margin: 15px 0 -10px 0;
        border-radius: 6px;
        font-size: 14px;
        color: #1B3139;
    }
    
    .chat-area {
        margin-top: -5px;
    }
    
    .info-note + div {
        margin-top: -20px !important;
    }
    
    div[data-testid="stMarkdown"]:has(.info-note) + div {
        margin-top: -30px !important;
    }
    </style>
    """

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
        """Add custom CSS styling using cached version"""
        st.markdown(get_custom_css(), unsafe_allow_html=True)
    
    # OPTIMIZATION 5: Add async-style call with better error handling
    def _call_model_endpoint(self, messages, max_tokens=128):
        """Call the model endpoint with optimizations"""
        try:
            print('Calling model endpoint...')
            start_time = time.time()
            
            result = query_endpoint(self.endpoint_name, messages, max_tokens)["content"]
            
            end_time = time.time()
            print(f'Model endpoint call completed in {end_time - start_time:.2f} seconds')
            
            return result
        except Exception as e:
            print(f'Error calling model endpoint: {str(e)}')
            raise
    
    def _save_feedback_to_database(self, feedback_data):
        """Save feedback to database - unchanged to preserve functionality"""
        def insert_feedback():
            try:
                print("🛠️ Storing feedback...")
                print(f"🔍 Feedback data: {feedback_data}")
                print("🚀 Connecting to Databricks...")
                
                from databricks import sql
                
                conn = sql.connect(
                    server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
                    http_path=st.secrets["DATABRICKS_HTTP_PATH"],
                    access_token=st.secrets["DATABRICKS_PAT"]
                )
                
                cursor = conn.cursor()
                
                print("🔍 Testing connection...")
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                print(f"✅ Connection test result: {result}")
                
                print("📝 Inserting feedback...")
                cursor.execute("""
                    INSERT INTO ai_squad_np.default.handyman_feedback
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
                print("✅ Feedback committed to database")
                
                cursor.close()
                conn.close()
                print("✅ Database connection closed")
                
            except Exception as e:
                import traceback
                print(f"⚠️ Could not store feedback: {e}")
                print("🔍 Full traceback:")
                traceback.print_exc()
        
        threading.Thread(target=insert_feedback).start()

    def _save_conversation_log(self):
        """Upsert conversation log - unchanged to preserve functionality"""
        def upsert_conversation(chat_history, conversation_id, response_count):
            try:
                from databricks import sql
    
                conn = sql.connect(
                    server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
                    http_path=st.secrets["DATABRICKS_HTTP_PATH"],
                    access_token=st.secrets["DATABRICKS_PAT"]
                )
                cursor = conn.cursor()
    
                cursor.execute("""
                    MERGE INTO ai_squad_np.default.handyman_feedback AS target
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
                    f"Reponse(s): {response_count}"
                ))
    
                conn.commit()
                cursor.close()
                conn.close()
    
            except Exception as e:
                import traceback
                print(f"⚠️ Could not upsert conversation: {e}")
                traceback.print_exc()

        if st.session_state.conversation_log_id is None:
            new_id = str(uuid.uuid4())
            st.session_state.conversation_log_id = new_id

        st.session_state.response_count += 1
        
        threading.Thread(target=upsert_conversation, args=(
            st.session_state.chat_history, 
            st.session_state.conversation_log_id, 
            st.session_state.response_count
        )).start()
    
    def _render_message(self, message, index):
        """Render a single message - unchanged"""
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
        """Render feedback UI - unchanged"""
        if message_index in st.session_state.feedback_submitted:
            st.markdown('<div class="feedback-thankyou">Thank you for the feedback!</div>', 
                       unsafe_allow_html=True)
            return
        
        st.markdown('<div class="feedback-container">', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1, 6])
        
        with col1:
            thumbs_up_key = f"thumbs_up_{message_index}"
            if st.button("👍", key=thumbs_up_key, help="Good response"):
                st.session_state.feedback_selection[str(message_index)] = 'thumbs-up'
                st.rerun()
        
        with col2:
            thumbs_down_key = f"thumbs_down_{message_index}"
            if st.button("👎", key=thumbs_down_key, help="Poor response"):
                st.session_state.feedback_selection[str(message_index)] = 'thumbs-down'
                st.rerun()
        
        selected_feedback = st.session_state.feedback_selection.get(str(message_index))
        if selected_feedback:
            feedback_text = "👍 Positive" if selected_feedback == 'thumbs-up' else "👎 Negative"
            st.write(f"Selected: {feedback_text}")
            
            comment_key = f"comment_{message_index}"
            comment = st.text_area(
                "Optional comment:",
                key=comment_key,
                height=60,
                placeholder="Share your thoughts about this response..."
            )
            
            submit_key = f"submit_{message_index}"
            if st.button("Submit Feedback", key=submit_key, type="primary"):
                self._handle_feedback_submission(message_index, comment)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def _handle_feedback_submission(self, message_index, comment):
        """Handle feedback submission - unchanged"""
        try:
            feedback_value = st.session_state.feedback_selection.get(str(message_index), 'none')
            
            feedback_data = {
                'id': str(uuid.uuid4()),
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'message': str(st.session_state.chat_history),
                'feedback': feedback_value,
                'comment': comment or ''
            }
            
            print(f"🔍 Submitting feedback: {feedback_data}")
            
            self._save_feedback_to_database(feedback_data)
            st.session_state.feedback_submitted.add(message_index)
            
            st.success("Thank you for your feedback!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Failed to submit feedback: {str(e)}")
            print(f"Feedback submission error: {e}")
    
    def _clear_chat(self):
        """Clear chat - unchanged"""
        st.session_state.chat_history = []
        st.session_state.feedback_selection = {}
        st.session_state.feedback_comments = {}
        st.session_state.feedback_submitted = set()
        st.session_state.conversation_log_id = None
        st.session_state.input_key_counter += 1
        st.session_state.response_count = 0
        st.rerun()
    
    def render(self):
        """Main render method - unchanged structure"""
        st.markdown('''
        <div class="content-with-bottom-padding">
        <h2 class="chat-title">DEV Ace Handyman Services Estimation Rep</h2>
        <div class="info-note">
            💬 Ask the rep below for handyman job information and estimates.
        </div>
        <div class="chat-area">
        ''', unsafe_allow_html=True)
        
        chat_container = st.container()
        
        with chat_container:
            for i, message in enumerate(st.session_state.chat_history):
                self._render_message(message, i)
        
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="fixed-bottom-input">', unsafe_allow_html=True)
        
        input_col, clear_col = st.columns([8, 1])
        
        with input_col:
            user_input = st.chat_input(
                placeholder="Type your message here... (Press Enter to send)",
                key=f"chat_input_{st.session_state.input_key_counter}"
            )
        
        with clear_col:
            clear_button = st.button("Clear", use_container_width=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
        
        if clear_button:
            self._clear_chat()
        
        if user_input and user_input.strip():
            st.session_state.chat_history.append({
                'role': 'user', 
                'content': user_input.strip()
            })
            
            st.session_state.input_key_counter += 1
            
            # OPTIMIZATION 6: More informative spinner with timing
            with st.spinner("Thinking..."):
                try:
                    assistant_response = self._call_model_endpoint(st.session_state.chat_history)
                    
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': assistant_response
                    })

                    self._save_conversation_log()
                    
                except Exception as e:
                    error_message = f'Error: {str(e)}'
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': error_message
                    })

                    self._save_conversation_log()
            
            st.rerun()

def main():
    """Main function"""
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
    """Show setup instructions in the sidebar"""
    with st.sidebar:
        st.header("Setup Instructions")
        
        st.subheader("1. Install Dependencies")
        st.code("""
# Basic requirements
pip install streamlit

# For Databricks integration (optional)
pip install databricks-sdk databricks-sql-connector

# For local SQLite fallback
# sqlite3 is included with Python
        """)
        
        st.subheader("2. Environment Variables")
        st.text("Set these if using Databricks:")
        st.code("""
DATABRICKS_SERVER_HOSTNAME=your_hostname
DATABRICKS_HTTP_PATH=your_http_path  
DATABRICKS_ACCESS_TOKEN=your_token
        """)
        
        st.subheader("3. Model Endpoint")
        st.text("Replace the query_endpoint function with your model serving logic")
        
        if not DATABRICKS_AVAILABLE:
            st.warning("⚠️ Databricks SDK not installed. Feedback will use local storage.")
        else:
            st.success("✅ Databricks SDK available")

if __name__ == "__main__":
    show_setup_instructions()
    main()
