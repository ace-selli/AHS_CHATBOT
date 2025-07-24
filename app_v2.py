import streamlit as st
import datetime
import uuid
import time
import threading
from databricks.sdk import WorkspaceClient
from databricks import sql
import os

# You'll need to implement this function or replace with your model serving logic
def query_endpoint(endpoint_name, messages, max_tokens=128):
    """
    Replace this with your actual model serving implementation
    """
    # Placeholder implementation - replace with your actual model serving code
    try:
        # Your model serving logic here
        # For now, returning a placeholder response
        return {"content": "This is a placeholder response. Please implement your model serving logic."}
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
        """Save feedback to database in a separate thread"""
        def insert_feedback():
            try:
                # Replace with your actual database credentials
                SERVER_HOSTNAME = "adb***"  # Replace with your server hostname
                HTTP_PATH = "sql***"        # Replace with your HTTP path
                ACCESS_TOKEN = "dapi***"    # Replace with your access token
                
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
                        print("✅ Feedback saved successfully")
            except Exception as e:
                print(f"❌ Feedback insert failed: {str(e)}")
        
        # Run database insert in background thread
        threading.Thread(target=insert_feedback).start()
    
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
            # Get current user info
            w = WorkspaceClient()
            current_user_info = w.current_user.me()
            user_email = current_user_info.user_name
            
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

if __name__ == "__main__":
    main()
