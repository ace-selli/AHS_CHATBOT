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
    st.warning("Databricks SDK not available. Feedback will be stored locally instead of in database.")

# Alternative database options
try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

# You'll need to implement this function or replace with your model serving logic
def query_endpoint(endpoint_name, messages, max_tokens=128):
    """
    Replace this with your actual model serving implementation
    
    Expected format for messages:
    [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"}
    ]
    """
    
    # OPTION 1: If you're using Databricks Model Serving
    # Uncomment and modify this section:
    """
    try:
        import requests
        import json
        
        # Get credentials from Streamlit secrets
        hostname = st.secrets.get("DATABRICKS_SERVER_HOSTNAME", os.getenv("DATABRICKS_SERVER_HOSTNAME"))
        token = st.secrets.get("DATABRICKS_PAT", os.getenv("DATABRICKS_PAT"))
        
        if not hostname or not token:
            raise Exception("Databricks credentials not found in secrets or environment variables")
        
        # Databricks model serving endpoint URL
        url = st.secrets.get("ENDPOINT_URL", os.getenv("ENDPOINT_URL")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Format the request for your model
        request_data = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=request_data)
        response.raise_for_status()
        
        result = response.json()
        
        # Adjust this based on your model's response format
        if "choices" in result:
            return {"content": result["choices"][0]["message"]["content"]}
        elif "predictions" in result:
            return {"content": result["predictions"][0]["content"]}
        else:
            return {"content": str(result)}
            
    except Exception as e:
        raise Exception(f"Databricks model endpoint error: {str(e)}")
    """
    
    # OPTION 2: If you're using OpenAI API
    # Uncomment and modify this section:
    """
    try:
        import openai
        
        # Get API key from Streamlit secrets
        api_key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))
        
        if not api_key:
            raise Exception("OpenAI API key not found in secrets or environment variables")
        
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # or your preferred model
            messages=messages,
            max_tokens=max_tokens
        )
        
        return {"content": response.choices[0].message.content}
    except Exception as e:
        raise Exception(f"OpenAI API error: {str(e)}")
    """
    
    # PLACEHOLDER - Remove this when you implement your actual logic
    print(f"⚠️  PLACEHOLDER: Called endpoint '{endpoint_name}' with {len(messages)} messages")
    print(f"Last message: {messages[-1]['content']}")
    
    # Return a more helpful placeholder
    return {
        "content": """🔧 **This is a placeholder response.** 

To get your chatbot working with Databricks:

1. **Uncomment Option 1** in the `query_endpoint` function above
2. **Make sure your Streamlit secrets include:**
   - `DATABRICKS_SERVER_HOSTNAME`
   - `DATABRICKS_ACCESS_TOKEN`
3. **Update the `endpoint_name`** in the main() function to your actual model endpoint name
4. **Test with a simple message**

Your Streamlit secrets should look like:
```toml
DATABRICKS_SERVER_HOSTNAME = "your-hostname.databricks.com"
DATABRICKS_ACCESS_TOKEN = "dapi..."
DATABRICKS_HTTP_PATH = "/sql/1.0/warehouses/..."  # for feedback database
```

Your last message was: "{}"
""".format(messages[-1]['content'] if messages else "No messages")
    }

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
            background-color: #EEEDE9;
            border-radius: 10px;
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
        """Save feedback to database with multiple fallback options"""
        def insert_feedback():
            if DATABRICKS_AVAILABLE:
                self._save_to_databricks(feedback_data)
            elif SQLITE_AVAILABLE:
                self._save_to_sqlite(feedback_data)
            else:
                self._save_to_local_file(feedback_data)
        
        # Run database insert in background thread
        threading.Thread(target=insert_feedback).start()
    
    def _save_to_databricks(self, feedback_data):
        """Save feedback to Databricks database"""
        try:
            # Get credentials from Streamlit secrets
            SERVER_HOSTNAME = st.secrets.get("DATABRICKS_SERVER_HOSTNAME", os.getenv("DATABRICKS_SERVER_HOSTNAME", "adb***"))
            HTTP_PATH = st.secrets.get("DATABRICKS_HTTP_PATH", os.getenv("DATABRICKS_HTTP_PATH", "sql***"))
            ACCESS_TOKEN = st.secrets.get("DATABRICKS_PAT", os.getenv("DATABRICKS_PAT", "dapi***"))
            
            with sql.connect(
                server_hostname=SERVER_HOSTNAME,
                http_path=HTTP_PATH,
                access_token=ACCESS_TOKEN,
                auth_type="databricks-token"
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO ai_squad_np.default.handyman_feedback (
                            id, timestamp, message, feedback, comment
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        feedback_data['id'],
                        feedback_data['timestamp'],
                        feedback_data['message'],
                        feedback_data['feedback'],
                        feedback_data['comment']
                    ))
                    print("✅ Feedback saved to Databricks successfully")
        except Exception as e:
            print(f"❌ Databricks insert failed: {str(e)}")
            # Fallback to local storage
            if SQLITE_AVAILABLE:
                self._save_to_sqlite(feedback_data)
            else:
                self._save_to_local_file(feedback_data)
    
    def _save_to_sqlite(self, feedback_data):
        """Save feedback to local SQLite database"""
        try:
            # Create database if it doesn't exist
            conn = sqlite3.connect('feedback.db')
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS handyman_feedback (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    message TEXT,
                    feedback TEXT,
                    comment TEXT
                )
            ''')
            
            # Insert feedback
            cursor.execute('''
                INSERT INTO handyman_feedback (id, timestamp, message, feedback, comment)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                feedback_data['id'],
                feedback_data['timestamp'],
                feedback_data['message'],
                feedback_data['feedback'],
                feedback_data['comment']
            ))
            
            conn.commit()
            conn.close()
            print("✅ Feedback saved to SQLite successfully")
        except Exception as e:
            print(f"❌ SQLite insert failed: {str(e)}")
            # Final fallback to file
            self._save_to_local_file(feedback_data)
    
    def _save_to_local_file(self, feedback_data):
        """Save feedback to local JSON file as final fallback"""
        try:
            import json
            filename = 'feedback_log.jsonl'
            
            with open(filename, 'a') as f:
                f.write(json.dumps(feedback_data) + '\n')
            
            print("✅ Feedback saved to local file successfully")
        except Exception as e:
            print(f"❌ Local file save failed: {str(e)}")
            # Store in session state as absolute last resort
            if 'feedback_log' not in st.session_state:
                st.session_state.feedback_log = []
            st.session_state.feedback_log.append(feedback_data)
            print("✅ Feedback stored in session state")
    
    def _render_message(self, message, index):
        """Render a single message with appropriate styling"""
        if message['role'] == 'user':
            st.markdown(f"""
            <div class="chat-message user-message">
                {message['content']}
            </div>
            """, unsafe_allow_html=True)
        else:  # assistant message
            st.markdown(f"""
            <div class="chat-message assistant-message">
                {message['content']}
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
        
        # Show selected feedback
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
            # Get feedback selection
            feedback_value = st.session_state.feedback_selection.get(str(message_index), 'none')
            
            # Prepare feedback data
            feedback_data = {
                'id': str(uuid.uuid4()),
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'message': str(st.session_state.chat_history),
                'feedback': feedback_value,
                'comment': comment or ''
            }
            
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
        st.rerun()
    
    def render(self):
        """Main render method for the chatbot interface"""
        # Title and description
        st.markdown('<h2 class="chat-title">Ace Handyman Services Customer Rep</h2>', 
                   unsafe_allow_html=True)
        st.info("Note: Ask the below rep for handyman job information.")
        
        # Chat history container
        chat_container = st.container()
        
        with chat_container:
            # Display chat history
            for i, message in enumerate(st.session_state.chat_history):
                self._render_message(message, i)
        
        # Input section
        st.markdown("---")
        
        # Create columns for input and buttons
        input_col, send_col, clear_col = st.columns([6, 1, 1])
        
        with input_col:
            user_input = st.text_area(
                "Type your message here...",
                key="user_input",
                height=80,
                placeholder="Type your message here..."
            )
        
        with send_col:
            send_button = st.button("Send", type="primary", use_container_width=True)
        
        with clear_col:
            clear_button = st.button("Clear", use_container_width=True)
        
        # Handle button clicks
        if clear_button:
            self._clear_chat()
        
        if send_button and user_input.strip():
            # Add user message
            st.session_state.chat_history.append({
                'role': 'user', 
                'content': user_input.strip()
            })
            
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
                    
                except Exception as e:
                    # Add error message
                    error_message = f'Error: {str(e)}'
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': error_message
                    })
            
            # Clear input and rerun
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
    endpoint_name = "your_endpoint_name"  # Replace with your actual endpoint name
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
