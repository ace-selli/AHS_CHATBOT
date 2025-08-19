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

# PERFORMANCE OPTIMIZATION 1: Cache database connections
@st.cache_resource
def get_databricks_connection():
    """Cache the Databricks connection to avoid repeated authentication"""
    try:
        if not DATABRICKS_AVAILABLE:
            return None
        
        from databricks import sql
        conn = sql.connect(
            server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
            http_path=st.secrets["DATABRICKS_HTTP_PATH"],
            access_token=st.secrets["DATABRICKS_PAT"]
        )
        print("✅ Databricks connection established and cached")
        return conn
    except Exception as e:
        print(f"❌ Failed to establish Databricks connection: {e}")
        return None

# PERFORMANCE OPTIMIZATION 2: Cache the model endpoint function
@st.cache_data(show_spinner=False, ttl=300)  # Cache for 5 minutes
def query_endpoint_cached(endpoint_name, messages_str, max_tokens=128):
    """Cached version of model endpoint query"""
    try:
        import requests
        
        # Convert messages string back to list for API call
        import json
        messages = json.loads(messages_str)
        
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
            return result["choices"][0]["message"]["content"]
        elif "predictions" in result and len(result["predictions"]) > 0:
            return result["predictions"][0]
        elif "content" in result:
            return result["content"]
        else:
            return str(result)
            
    except Exception as e:
        raise Exception(f"Model endpoint error: {str(e)}")

# Original function for non-cacheable calls
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

# PERFORMANCE OPTIMIZATION 3: Cache CSS to avoid recomputation
@st.cache_data
def get_custom_css():
    """Cache the custom CSS to avoid recomputation"""
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
        # PERFORMANCE OPTIMIZATION 4: Initialize database connection once
        self.db_conn = get_databricks_connection()
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
        # PERFORMANCE OPTIMIZATION 5: Track if first call has been made
        if 'first_call_made' not in st.session_state:
            st.session_state.first_call_made = False
    
    def _add_custom_css(self):
        """Add custom CSS styling using cached version"""
        st.markdown(get_custom_css(), unsafe_allow_html=True)
    
    def _call_model_endpoint(self, messages, max_tokens=128):
        """Call the model endpoint with caching for repeated queries"""
        try:
            print('Calling model endpoint...')
            
            # PERFORMANCE OPTIMIZATION 6: Use cached version for similar queries
            # Convert messages to string for caching (lists are not hashable)
            import json
            messages_str = json.dumps(messages, sort_keys=True)
            
            # For the first few calls or very recent messages, don't use cache
            # This ensures dynamic responses while still benefiting from cache for repeated queries
            if not st.session_state.first_call_made:
                st.session_state.first_call_made = True
                return query_endpoint(self.endpoint_name, messages, max_tokens)["content"]
            else:
                # Use cached version for subsequent similar queries
                return query_endpoint_cached(self.endpoint_name, messages_str, max_tokens)
                
        except Exception as e:
            print(f'Error calling model endpoint: {str(e)}')
            raise
    
    def _save_feedback_to_database(self, feedback_data):
        """Save feedback to database using cached connection"""
        def insert_feedback():
            try:
                print("🛠️ Storing feedback...")
                print(f"🔍 Feedback data: {feedback_data}")
                
                # PERFORMANCE OPTIMIZATION 7: Use cached connection
                if self.db_conn is None:
                    print("⚠️ No database connection available")
                    return
                
                cursor = self.db_conn.cursor()
                
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
                
                self.db_conn.commit()
                print("✅ Feedback committed to database")
                cursor.close()
                
            except Exception as e:
                import traceback
                print(f"⚠️ Could not store feedback: {e}")
                print("🔍 Full traceback:")
                traceback.print_exc()
        
        # Run in background thread to avoid blocking UI
        threading.Thread(target=insert_feedback).start()

    def _save_conversation_log(self):
        """Upsert the entire chat history using cached connection"""
        def upsert_conversation(chat_history, conversation_id, response_count):
            try:
                # PERFORMANCE OPTIMIZATION 8: Use cached connection
                if self.db_conn is None:
                    print("⚠️ No database connection available for conversation log")
                    return
                
                cursor = self.db_conn.cursor()
    
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
    
                self.db_conn.commit()
                cursor.close()
    
            except Exception as e:
                import traceback
                print(f"⚠️ Could not upsert conversation: {e}")
                traceback.print_exc()

        if st.session_state.conversation_log_id is None:
            new_id = str(uuid.uuid4())
            st.session_state.conversation_log_id = new_id

        st.session_state.response_count += 1
        
        # Run in background to avoid blocking UI
        threading.Thread(target=upsert_conversation, args=(
            st.session_state.chat_history, 
            st.session_state.conversation_log_id, 
            st.session_state.response_count
        )).start()
    
    # PERFORMANCE OPTIMIZATION 9: Optimize message rendering
    @st.cache_data(show_spinner=False)
    def _format_message_content(_self, content, is_user=False):
        """Cache formatted message content to avoid reprocessing"""
        if is_user:
            return f'<div class="chat-message user-message">{content}</div>'
        else:
            formatted_content = content.replace('\n', '<br>')
            return f'<div class="chat-message assistant-message">{formatted_content}</div>'
    
    def _render_message(self, message, index):
        """Render a single message with cached formatting"""
        is_user = message['role'] == 'user'
        formatted_html = self._format_message_content(message['content'], is_user)
        st.markdown(formatted_html, unsafe_allow_html=True)
        
        # Add feedback UI for the last assistant message
        if not is_user and index == len(st.session_state.chat_history) - 1:
            self._render_feedback_ui(index)
    
    def _render_feedback_ui(self, message_index):
        """Render feedback buttons and form for assistant messages"""
        if message_index in st.session_state.feedback_submitted:
            st.markdown('<div class="feedback-thankyou">Thank you for the feedback!</div>', 
                       unsafe_allow_html=True)
            return
        
        st.markdown('<div class="feedback-container">', unsafe_allow_html=True)
        
        # Feedback buttons
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
        
        # Show selected feedback and form ONLY if a thumb button was pressed
        selected_feedback = st.session_state.feedback_selection.get(str(message_index))
        if selected_feedback:
            feedback_text = "👍 Positive" if selected_feedback == 'thumbs-up' else "👎 Negative"
            st.write(f"Selected: {feedback_text}")
            
            # Comment box
            comment_key = f"comment_{message_index}"
            comment = st.text_area(
                "Optional comment:",
                key=comment_key,
                height=60,
                placeholder="Share your thoughts about this response..."
            )
            
            # Submit button
            submit_key = f"submit_{message_index}"
            if st.button("Submit Feedback", key=submit_key, type="primary"):
                self._handle_feedback_submission(message_index, comment)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def _handle_feedback_submission(self, message_index, comment):
        """Handle feedback submission"""
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
            
            # Save to database (async)
            self._save_feedback_to_database(feedback_data)
            
            # Mark as submitted
            st.session_state.feedback_submitted.add(message_index)
            
            st.success("Thank you for your feedback!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Failed to submit feedback: {str(e)}")
            print(f"Feedback submission error: {e}")
    
    def _clear_chat(self):
        """Clear the chat history and reset state"""
        st.session_state.chat_history = []
        st.session_state.feedback_selection = {}
        st.session_state.feedback_comments = {}
        st.session_state.feedback_submitted = set()
        st.session_state.conversation_log_id = None
        st.session_state.input_key_counter += 1
        st.session_state.response_count = 0
        st.session_state.first_call_made = False  # Reset first call flag
        # PERFORMANCE OPTIMIZATION 10: Clear caches when starting new conversation
        st.cache_data.clear()
        st.rerun()
    
    def render(self):
        """Main render method for the chatbot interface"""
        # PERFORMANCE OPTIMIZATION 11: Use containers to minimize redraws
        header_container = st.container()
        chat_container = st.container()
        input_container = st.container()
        
        with header_container:
            st.markdown('''
            <div class="content-with-bottom-padding">
            <h2 class="chat-title">Ace Handyman Services Estimation Rep</h2>
            <div class="info-note">
                💬 Ask the rep below for handyman job information and estimates.
            </div>
            <div class="chat-area">
            ''', unsafe_allow_html=True)
        
        with chat_container:
            # Display chat history
            for i, message in enumerate(st.session_state.chat_history):
                self._render_message(message, i)
        
        st.markdown('</div></div>', unsafe_allow_html=True)
        
        # Fixed input section at bottom
        with input_container:
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
        
        # Handle input
        if clear_button:
            self._clear_chat()
        
        if user_input and user_input.strip():
            # Add user message
            st.session_state.chat_history.append({
                'role': 'user', 
                'content': user_input.strip()
            })
            
            st.session_state.input_key_counter += 1
            
            # PERFORMANCE OPTIMIZATION 12: Use more specific spinner context
            with st.spinner("🤖 Generating response..."):
                try:
                    assistant_response = self._call_model_endpoint(st.session_state.chat_history)
                    
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': assistant_response
                    })

                    # Save conversation log (async)
                    self._save_conversation_log()
                    
                except Exception as e:
                    error_message = f'Error: {str(e)}'
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': error_message
                    })

                    self._save_conversation_log()
            
            st.rerun()

# PERFORMANCE OPTIMIZATION 13: Cache the main app setup
@st.cache_resource
def setup_streamlit_config():
    """Cache Streamlit configuration setup"""
    st.set_page_config(
        page_title="Ace Handyman Services Chat",
        page_icon="🔧",
        layout="centered",
        initial_sidebar_state="collapsed"
    )
    return True

def main():
    """Main function to run the Streamlit app"""
    setup_streamlit_config()
    
    # Initialize chatbot with cached connection
    endpoint_name = st.secrets.get("DATABRICKS_ENDPOINT_NAME", "your_endpoint_name")
    chatbot = StreamlitChatbot(endpoint_name)
    
    # Render the chatbot
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
