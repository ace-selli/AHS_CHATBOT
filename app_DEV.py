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
        # Add conversation ID for conversation storage
        if 'conversation_id' not in st.session_state:
            st.session_state.conversation_id = str(uuid.uuid4())
    
    def _add_custom_css(self):
        """Add custom CSS styling to match the original design"""
        st.markdown("""
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
            background-color: transparent; /* Changed from #EEEDE9 to transparent */
            border-radius: 10px;
            border: none; /* Remove any potential border */
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
        
        /* Fixed bottom input bar */
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
        
        /* Add bottom padding to content so it doesn't get hidden */
        .content-with-bottom-padding {
            padding-bottom: 120px;
        }
        
        .info-note {
            background-color: #EEEDE9;
            border-left: 4px solid #1B3139;
            padding: 12px 16px;
            margin: 15px 0 -10px 0; /* Changed bottom margin to negative to pull content up */
            border-radius: 6px;
            font-size: 14px;
            color: #1B3139;
        }
        
        .chat-area {
            margin-top: -5px; /* Negative margin to pull chat area up closer to info note */
        }
        
        /* Aggressive targeting of the gap after info note */
        .info-note + div {
            margin-top: -20px !important;
        }
        
        /* Target Streamlit's vertical block that comes after info note */
        div[data-testid="stMarkdown"]:has(.info-note) + div {
            margin-top: -30px !important;
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
                # Skip if Databricks is not available
                if not DATABRICKS_AVAILABLE:
                    print("⚠️ Databricks not available, skipping feedback storage")
                    return
                    
                print("🛠️ Storing feedback...")
                print(f"🔍 Feedback data: {feedback_data}")
                print("🚀 Connecting to Databricks...")
                
                # Import databricks.sql here to ensure it's available
                from databricks import sql
                
                # Check if all required secrets are available
                required_secrets = ["DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_PAT"]
                for secret in required_secrets:
                    if secret not in st.secrets:
                        print(f"⚠️ Missing secret: {secret}, skipping feedback storage")
                        return
                
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
        
        # Run in background thread with daemon=True to prevent blocking
        thread = threading.Thread(target=insert_feedback, daemon=True)
        thread.start()
    
    def _save_conversation_to_database(self, conversation_data):
        """Save/update conversation to database using existing table structure"""
        def upsert_conversation():
            try:
                # Skip if Databricks is not available
                if not DATABRICKS_AVAILABLE:
                    print("⚠️ Databricks not available, skipping conversation storage")
                    return
                    
                print("🛠️ Storing conversation...")
                print(f"🔍 Conversation ID: {conversation_data['conversation_id']}")
                print("🚀 Connecting to Databricks...")
                
                # Import databricks.sql here to ensure it's available
                from databricks import sql
                
                # Check if all required secrets are available
                required_secrets = ["DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_PAT"]
                for secret in required_secrets:
                    if secret not in st.secrets:
                        print(f"⚠️ Missing secret: {secret}, skipping conversation storage")
                        return
                
                conn = sql.connect(
                    server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
                    http_path=st.secrets["DATABRICKS_HTTP_PATH"],
                    access_token=st.secrets["DATABRICKS_PAT"]
                )
                
                cursor = conn.cursor()
                
                # Delete any existing conversation logs for this conversation
                # We'll identify them by the comment field containing the conversation_id
                print("🗑️ Deleting existing conversation records...")
                cursor.execute("""
                    DELETE FROM ai_squad_np.default.handyman_feedback 
                    WHERE feedback = 'conversation_log' 
                    AND comment LIKE ?
                """, (f'%conversation_id:{conversation_data["conversation_id"]}%',))
                
                deleted_count = cursor.rowcount
                print(f"🗑️ Deleted {deleted_count} existing conversation records")
                
                # Insert the new conversation record using existing table structure
                print("📝 Inserting new conversation...")
                cursor.execute("""
                    INSERT INTO ai_squad_np.default.handyman_feedback
                    (id, timestamp, message, feedback, comment)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    conversation_data['id'],
                    conversation_data['timestamp'],
                    conversation_data['message'],
                    conversation_data['feedback'],
                    conversation_data['comment']
                ))
                
                # Commit the transaction
                conn.commit()
                print("✅ Conversation committed to database")
                
                cursor.close()
                conn.close()
                print("✅ Database connection closed")
                
            except Exception as e:
                import traceback
                print(f"⚠️ Could not store conversation: {e}")
                print("🔍 Full traceback:")
                traceback.print_exc()
        
        # Run in background thread with daemon=True to prevent blocking
        thread = threading.Thread(target=upsert_conversation, daemon=True)
        thread.start()
    
    def _store_conversation_after_response(self):
        """Store the entire conversation after receiving a bot response"""
        try:
            # Only store if we have Databricks available and secrets configured
            if not DATABRICKS_AVAILABLE:
                print("⚠️ Databricks not available, skipping conversation storage")
                return
                
            # Check if required secrets exist
            required_secrets = ["DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_PAT"]
            missing_secrets = [s for s in required_secrets if s not in st.secrets]
            if missing_secrets:
                print(f"⚠️ Missing secrets {missing_secrets}, skipping conversation storage")
                return
            
            # Prepare conversation data
            conversation_data = {
                'id': str(uuid.uuid4()),  # New ID for each update
                'conversation_id': st.session_state.conversation_id,  # Keep for internal tracking
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'message': str(st.session_state.chat_history),  # Store entire conversation
                'feedback': 'conversation_log',  # Special marker to distinguish from user feedback
                'comment': f'conversation_id:{st.session_state.conversation_id} | {len(st.session_state.chat_history)} messages'
            }
            
            print(f"🔍 Storing conversation: {st.session_state.conversation_id}")
            
            # Save to database (will overwrite existing conversation)
            self._save_conversation_to_database(conversation_data)
            
        except Exception as e:
            print(f"Conversation storage error: {e}")
            # Don't raise the exception - we don't want to break the chat flow
    
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
        """Clear the chat history and start a new conversation"""
        st.session_state.chat_history = []
        st.session_state.feedback_selection = {}
        st.session_state.feedback_comments = {}
        st.session_state.feedback_submitted = set()
        # Generate new conversation ID for new conversation
        st.session_state.conversation_id = str(uuid.uuid4())
        # Increment counter to force input widget to refresh
        st.session_state.input_key_counter += 1
        st.rerun()
    
    def render(self):
        """Main render method for the chatbot interface"""
        # Title, info note, and chat area in single container to eliminate all gaps
        st.markdown('''
        <div class="content-with-bottom-padding">
        <h2 class="chat-title">Ace Handyman Services Customer Rep</h2>
        <div class="info-note">
            💬 Ask the rep below for handyman job information and estimates.
        </div>
        <div class="chat-area">
        ''', unsafe_allow_html=True)
        
        chat_container = st.container()
        
        with chat_container:
            # Display chat history
            for i, message in enumerate(st.session_state.chat_history):
                self._render_message(message, i)
        
        
        st.markdown('</div>', unsafe_allow_html=True)  # Close chat-area
        st.markdown('</div>', unsafe_allow_html=True)  # Close content-with-bottom-padding
        
        # Fixed input section at bottom of screen
        st.markdown('<div class="fixed-bottom-input">', unsafe_allow_html=True)
        
        # Create columns for chat input and clear button
        input_col, clear_col = st.columns([8, 1])
        
        with input_col:
            # Use st.chat_input for built-in Enter key support
            user_input = st.chat_input(
                placeholder="Type your message here... (Press Enter to send)",
                key=f"chat_input_{st.session_state.input_key_counter}"
            )
        
        with clear_col:
            clear_button = st.button("Clear", use_container_width=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Handle button clicks
        if clear_button:
            self._clear_chat()
        
        if user_input and user_input.strip():
            # Add user message
            st.session_state.chat_history.append({
                'role': 'user', 
                'content': user_input.strip()
            })
            
            # Increment counter to clear input field
            st.session_state.input_key_counter += 1
            
            # Show typing indicator
            with st.spinner("Thinking..."):
                try:
                    # Get assistant response
                    assistant_response = self._call_model_endpoint(st.session_state.chat_history)
                    
                    # Add assistant message
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': assistant_response
                    })
                    
                    print(f"🤖 Assistant response received, chat history length: {len(st.session_state.chat_history)}")
                    
                    # Store conversation after receiving response
                    self._store_conversation_after_response()
                    
                except Exception as e:
                    # Add error message
                    error_message = f'Error: {str(e)}'
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': error_message
                    })
                    
                    # Store conversation even if there was an error
                    self._store_conversation_after_response()
            
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
        
        st.subheader("4. How Conversation Storage Works")
        st.text("Using your existing feedback table structure:")
        st.code("""
-- Conversations are stored with:
-- feedback = 'conversation_log'
-- comment contains conversation_id for overwrite logic
-- message contains the full conversation history

-- To view stored conversations:
SELECT * FROM ai_squad_np.default.handyman_feedback 
WHERE feedback = 'conversation_log' 
ORDER BY timestamp DESC;
        """)
        
        st.info("💡 No table changes needed! Conversations use the existing feedback table structure with special markers to distinguish them from user feedback.")
        
        if not DATABRICKS_AVAILABLE:
            st.warning("⚠️ Databricks SDK not installed. Feedback will use local storage.")
        else:
            st.success("✅ Databricks SDK available")

if __name__ == "__main__":
    show_setup_instructions()
    main()
