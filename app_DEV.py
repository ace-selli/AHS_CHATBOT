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
        # Add input key counter to force widget refresh
        if 'input_key_counter' not in st.session_state:
            st.session_state.input_key_counter = 0
        if 'conversation_log_id' not in st.session_state:
            st.session_state.conversation_log_id = None
        if 'response_count' not in st.session_state:
            st.session_state.response_count = 0
    
    def _add_custom_css(self):
        """Visual-only CSS: lock page scroll, create a center chat 'box' that scrolls, keep top areas always visible."""
        st.markdown("""
        <style>
        :root{
          /* If the input bar looks taller/shorter on your machine, adjust --input-h by ±10–20px */
          --input-h: 110px;        /* bottom input area space (chat_input + padding) */
          --bg: #F9F7F4;
          --border: rgba(49,51,63,.15);
        }

        /* --- Never allow page/window to scroll --- */
        html, body,
        [data-testid="stAppViewContainer"],
        .main {
          height: 100vh !important;
          overflow: hidden !important;     /* page-level scrolling is disabled */
          background: var(--bg);
        }

        /* --- Make the main content a vertical flex layout, minus the fixed input height --- */
        .main .block-container {
          max-width: 100%;
          height: calc(100vh - var(--input-h)) !important;  /* reserve space for fixed input bar */
          display: flex;
          flex-direction: column;   /* top sections + chat box that fills remaining space */
          overflow: hidden;         /* only the chat box will scroll */
          background: var(--bg);
          padding-top: 12px !important;
          padding-bottom: 12px !important;
        }

        /* --- Title (always visible; not in a scrollable area) --- */
        .chat-title {
          font-size: 28px;
          font-weight: 700;
          color: #1B3139;
          text-align: center;
          margin: 0 0 8px 0;
        }

        /* --- Info note + button row (also always visible; not scrollable) --- */
        .info-note {
          background-color: #EEEDE9;
          border-left: 4px solid #1B3139;
          padding: 12px 16px;
          border-radius: 6px;
          font-size: 16px;
          color: #1B3139;
          margin: 6px 0 8px 0;
        }

        /* --- The center chat "BOX" that scrolls (and nothing else scrolls) --- */
        .chat-scrollbox {
          /* This element takes the remaining height of .block-container */
          flex: 1;
          min-height: 0;            /* required so overflow works inside flex child */
          overflow-y: auto;         /* only place where scrolling is allowed */
          background: #FFFFFF;
          border: 1px solid rgba(49,51,63,.10);
          border-radius: 12px;
          padding: 8px 14px;
        }

        /* --- Chat bubbles (your existing visuals) --- */
        .chat-message {
          padding: 15px 20px;
          border-radius: 20px;
          margin: 15px 0;
          font-size: 20px;
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

        .feedback-container { margin-top: 15px; padding: 15px; background: transparent; border-radius: 10px; border: none; font-size: 16px; }
        .feedback-thankyou { color: #00A972; font-weight: bold; margin-top: 8px; font-size: 16px; }

        .stButton > button {
          border-radius: 20px;
          font-size: 16px;
          white-space: nowrap !important;
          overflow: visible !important;
        }
        .typing-indicator {
          background-color: #2D4550;
          color: #EEEDE9;
          padding: 15px 20px;
          border-radius: 20px;
          margin: 15px 0;
          font-style: italic;
          font-size: 18px;
        }

        /* --- Bottom input stays fixed (unchanged functionality) --- */
        .input-fixed {
          position: fixed; left: 0; right: 0; bottom: 0;
          background: var(--bg);
          padding: 15px 20px;
          border-top: 2px solid #EEEDE9;
          z-index: 1100;
          box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
        }

        /* Input font sizes (unchanged) */
        .stChatInput input { font-size: 18px !important; }
        .stTextArea textarea { font-size: 16px !important; }

        /* --- IMPORTANT: neutralize any previous hard heights on generic Streamlit containers --- */
        [data-testid="stContainer"] {
          height: auto !important;
          max-height: none !important;
          margin-bottom: 0 !important;
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
                print(f"🔍 Feedback data: {feedback_data}")
                print("🚀 Connecting to Databricks...")
                
                # Import databricks.sql here to ensure it's available
                from databricks import sql
                
                conn = sql.connect(
                    server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
                    http_path=st.secrets["DATABRICKS_HTTP_PATH"],
                    access_token=st.secrets["DATABRICKS_PAT"]
                )
                
                cursor = conn.cursor()
                
                # Debug: Check if we can connect and see the table
                print("🔍 Testing connection...")
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                print(f"✅ Connection test result: {result}")
                
                # Insert the feedback
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
                
                # Commit the transaction
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
        
        # Run in background thread
        threading.Thread(target=insert_feedback).start()

    def _save_conversation_log(self):
        """Upsert the entire chat history to the same feedback table (idempotent per session)"""
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

        # Use session state to track this session's unique log id
        if st.session_state.conversation_log_id is None:
            new_id = str(uuid.uuid4())
            st.session_state.conversation_log_id = new_id

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
        else:  # assistant message
            # Convert newlines to HTML line breaks for proper formatting
            formatted_content = message['content'].replace('\n', '<br>')
            st.markdown(f"""
            <div class="chat-message assistant-message">
                {formatted_content}
            </div>
            """, unsafe_allow_html=True)
            
            # Add feedback UI for the last assistant message
            if index == len(st.session_state.chat_history) - 1:
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
            
            # Comment box - only show after selection
            comment_key = f"comment_{message_index}"
            comment = st.text_area(
                "Optional comment:",
                key=comment_key,
                height=60,
                placeholder="Share your thoughts about this response..."
            )
            
            # Submit button - only show after selection
            submit_key = f"submit_{message_index}"
            if st.button("Submit Feedback", key=submit_key, type="primary"):
                self._handle_feedback_submission(message_index, comment)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def _handle_feedback_submission(self, message_index, comment):
        """Handle feedback submission"""
        try:
            # Get feedback selection
            feedback_value = st.session_state.feedback_selection.get(str(message_index), 'none')
            
            # Prepare feedback data with timezone-aware datetime
            feedback_data = {
                'id': str(uuid.uuid4()),
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'message': str(st.session_state.chat_history),
                'feedback': feedback_value,
                'comment': comment or ''
            }
            
            print(f"🔍 Submitting feedback: {feedback_data}")
            
            # Save to database
            self._save_feedback_to_database(feedback_data)
            
            # Mark as submitted
            st.session_state.feedback_submitted.add(message_index)
            
            # Show success message
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
        # Reset conversation_log_id to new UUID for new conversation
        st.session_state.conversation_log_id = None
        # Increment counter to force input widget to refresh
        st.session_state.input_key_counter += 1
        st.session_state.response_count = 0
        st.rerun()
    

    def render(self):
        """Render with a center-only scroll 'chat box' and no page scrolling (visual-only change)."""

        # Title (always visible; not inside a scrollable area)
        st.markdown('<h2 class="chat-title">DEV Ace Handyman Services Estimation Rep</h2>', unsafe_allow_html=True)

        # Info note + New Chat button row (always visible)
        info_col, clear_col = st.columns([7, 2])
        with info_col:
            st.markdown('<div class="info-note">💬 Ask the rep below for handyman job information and estimates.</div>',
                        unsafe_allow_html=True)
        with clear_col:
            st.markdown('<div style="margin-top: 8px;">', unsafe_allow_html=True)
            clear_button = st.button("New Chat", use_container_width=True, key="new_chat_btn")
            st.markdown('</div>', unsafe_allow_html=True)

        # ---- Center chat BOX: the ONLY scrollable region ----
        st.markdown('<div class="chat-scrollbox">', unsafe_allow_html=True)
        if len(st.session_state.chat_history) == 0:
            st.markdown('''
                <div style="text-align: center; color: #888; font-style: italic; padding: 40px 0;">
                    Start a conversation by typing your message below...
                </div>
            ''', unsafe_allow_html=True)
        else:
            for i, message in enumerate(st.session_state.chat_history):
                self._render_message(message, i)
        st.markdown('</div>', unsafe_allow_html=True)
        # -----------------------------------------------------

        # Fixed input at bottom (unchanged functionality)
        st.markdown('<div class="input-fixed">', unsafe_allow_html=True)
        user_input = st.chat_input(
            placeholder="Type your message here... (Press Enter to send)",
            key=f"chat_input_{st.session_state.input_key_counter}"
        )
        st.markdown('</div>', unsafe_allow_html=True)

        # Handle button clicks (unchanged)
        if clear_button:
            self._clear_chat()

        # Handle user input (unchanged)
        if user_input and user_input.strip():
            # Add user message
            st.session_state.chat_history.append({
                'role': 'user',
                'content': user_input.strip()
            })

            # Increment counter to clear input field
            st.session_state.input_key_counter += 1

            # Get assistant response
            with st.spinner("Thinking..."):
                try:
                    assistant_response = self._call_model_endpoint(st.session_state.chat_history)
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': assistant_response
                    })
                    # Save or update conversation log
                    self._save_conversation_log()
                except Exception as e:
                    error_message = f'Error: {str(e)}'
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': error_message
                    })
                    # Save or update conversation log
                    self._save_conversation_log()

            # Rerun to refresh the interface
            st.rerun()



def main():
    """Main function to run the Streamlit app"""
    st.set_page_config(
        page_title="Ace Handyman Services Chat",
        page_icon="🔧",
        layout="centered",
        initial_sidebar_state="collapsed"
    )
    
    # Initialize chatbot
    endpoint_name = st.secrets.get("DATABRICKS_ENDPOINT_NAME", "your_endpoint_name")
    chatbot = StreamlitChatbot(endpoint_name)
    
    # Render the chatbot
    chatbot.render()

# Requirements and setup instructions
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
