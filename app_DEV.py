import streamlit as st
import datetime
import uuid
import time
import threading
import os
import re
import requests
import json

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

def stream_databricks_chat(messages):
    """
    Yields text chunks from a Databricks chat endpoint that supports SSE ('data:' lines).
    Compatible with OpenAI-style /v1/chat/completions stream responses.
    """
    url = st.secrets["ENDPOINT_URL"]
    headers = {
        "Authorization": f"Bearer {st.secrets['DATABRICKS_PAT']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Connection": "keep-alive",
    }
    payload = {"messages": messages, "stream": True}

    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=300) as r:
            r.raise_for_status()
            for raw_line in r.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                data = raw_line[len("data: "):].strip() if raw_line.startswith("data: ") else raw_line.strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = obj["choices"][0].get("delta") or obj["choices"][0].get("message") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece
                except Exception:
                    piece = obj.get("response") or obj.get("text") or ""
                    if piece:
                        yield piece
    except requests.exceptions.RequestException as e:
        yield f"\n\n Connection error while streaming: {e}"

def query_endpoint(endpoint_name, messages, max_tokens=128):
    """Non-streaming fallback for model endpoint - simple version"""
    try:
        url = st.secrets['ENDPOINT_URL']
        
        headers = {
            "Authorization": f"Bearer {st.secrets['DATABRICKS_PAT']}",
            "Content-Type": "application/json"
        }
        
        request_data = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": False
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
        # Add streaming state
        if 'is_streaming' not in st.session_state:
            st.session_state.is_streaming = False
    
    def _add_custom_css(self):
        """Add custom CSS styling with typing indicator"""
        # Add typing indicator CSS from first implementation
        TYPING_CSS = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
        
        .typing-dots { display:inline-flex; align-items:center; gap:.35rem; opacity:0.9; }
        .typing-dots .dot {
          width:.38rem; height:.38rem; border-radius:50%;
          background: currentColor; opacity:.25; animation: bounce 1s infinite ease-in-out;
        }
        .typing-dots .dot:nth-child(2){ animation-delay:.2s }
        .typing-dots .dot:nth-child(3){ animation-delay:.4s }
        @keyframes bounce { 0%,80%,100%{transform:translateY(0); opacity:.25} 40%{transform:translateY(-.25rem); opacity:1} }
        
        .main-container {
            font-family: 'DM Sans', sans-serif;
            background-color: #FFFFFF;
        }
        
        .chat-title {
            font-size: 24px;
            font-weight: 700;
            color: #E73137;
            text-align: center;
            margin-bottom: 20px;
        }
        
        .chat-message {
            padding: 15px 20px;
            border-radius: 20px;
            margin: 10px 0;
            font-size: 16px;
            line-height: 1.6;
            max-width: 80%;
            word-wrap: break-word;
            overflow-wrap: break-word;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .user-message {
            background-color: #E73137;
            color: white;
            margin-left: auto;
            margin-right: 0;
        }
        
        .assistant-message {
            background-color: #F8F9FA;
            color: #2C3E50;
            margin-left: 0;
            margin-right: auto;
            border: 1px solid #E5E5E5;
        }
        
        /* Improved text formatting within messages */
        .assistant-message p {
            margin: 0 0 12px 0;
            line-height: 1.6;
            color: #2C3E50;
        }
        
        .assistant-message p:last-child {
            margin-bottom: 0;
        }
        
        .assistant-message ul, .assistant-message ol {
            margin: 8px 0 12px 0;
            padding-left: 20px;
        }
        
        .assistant-message li {
            margin-bottom: 6px;
            line-height: 1.5;
            color: #2C3E50;
        }
        
        .assistant-message strong {
            font-weight: 600;
            color: #E73137;
        }
        
        .assistant-message em {
            font-style: italic;
            color: #5A6B7D;
        }
        
        .assistant-message code {
            background-color: #E8E9EA;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            color: #2C3E50;
            border: 1px solid #D1D5DB;
        }
        
        .assistant-message pre {
            background-color: #F1F3F4;
            padding: 12px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 12px 0;
            border-left: 3px solid #E73137;
            border: 1px solid #D1D5DB;
        }
        
        .assistant-message pre code {
            background-color: transparent;
            padding: 0;
            font-size: 13px;
            line-height: 1.4;
            white-space: pre;
            border: none;
        }
        
        .assistant-message blockquote {
            border-left: 3px solid #E73137;
            padding-left: 15px;
            margin: 12px 0;
            font-style: italic;
            color: #5A6B7D;
        }
        
        /* Enhanced handyman response styling with better contrast */
        .assistant-message .summary-header {
            background: linear-gradient(135deg, #FFF5F5 0%, #FED7D7 100%);
            padding: 12px 16px;
            border-radius: 10px;
            margin-bottom: 15px;
            border-left: 4px solid #E73137;
            border: 1px solid #F7A8AA;
        }
        
        .assistant-message .estimate-row {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            font-size: 16px;
        }
        
        .assistant-message .estimate-emoji {
            margin-right: 10px;
            font-size: 18px;
        }
        
        .assistant-message .estimate-label {
            font-weight: 600;
            color: #E73137;
            margin-right: 8px;
        }
        
        .assistant-message .confidence-badge {
            background: #E73137;
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
        }
        
        .assistant-message .confidence-badge.low {
            background: #F56565;
            color: white;
        }
        
        .assistant-message .confidence-badge.high {
            background: #C53030;
            color: white;
        }
        
        .assistant-message .section-header {
            display: flex;
            align-items: center;
            font-weight: 600;
            color: #E73137;
            margin: 18px 0 10px 0;
            font-size: 16px;
        }
        
        .assistant-message .section-emoji {
            margin-right: 8px;
            font-size: 18px;
        }
        
        .assistant-message .enhanced-list {
            list-style: none;
            padding: 0;
            margin: 8px 0 16px 0;
        }
        
        .assistant-message .enhanced-list li {
            background: #FFFFFF;
            margin-bottom: 8px;
            padding: 10px 12px;
            border-radius: 8px;
            border-left: 3px solid #E73137;
            line-height: 1.5;
            display: flex;
            align-items: flex-start;
            border: 1px solid #E5E5E5;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .assistant-message .list-emoji {
            margin-right: 10px;
            font-size: 16px;
            margin-top: 1px;
            flex-shrink: 0;
        }
        
        .assistant-message .question-list li {
            border-left-color: #E73137;
            background: #FFF5F5;
        }
        
        .assistant-message .task-list li {
            border-left-color: #E73137;
            background: #FFFFFF;
        }
        
        .feedback-container {
            margin-top: 10px;
            padding: 10px;
            background-color: transparent;
            border-radius: 10px;
            border: none;
        }
        
        .feedback-thankyou {
            color: #E73137;
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
            background-color: #F8F9FA;
            color: #2C3E50;
            padding: 10px 15px;
            border-radius: 20px;
            margin: 10px 0;
            font-style: italic;
            border: 1px solid #E5E5E5;
        }
        
        /* Fixed bottom input bar */
        .fixed-bottom-input {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: #FFFFFF;
            padding: 15px 20px;
            border-top: 2px solid #E73137;
            z-index: 1000;
            box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
        }
        
        /* Add bottom padding to content so it doesn't get hidden */
        .content-with-bottom-padding {
            padding-bottom: 120px;
        }
        
        .info-note {
            background-color: rgba(231, 49, 55, 0.1);
            border-left: 4px solid #E73137;
            padding: 12px 16px;
            margin: 15px 0 -10px 0;
            border-radius: 6px;
            font-size: 14px;
            color: #2C3E50;
        }
        
        .chat-area {
            margin-top: -5px;
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
        """
        st.markdown(TYPING_CSS, unsafe_allow_html=True)
    
    def _call_model_endpoint_streaming(self, messages):
        """Call the model endpoint with streaming support"""
        try:
            print('Calling model endpoint with streaming...')
            return stream_databricks_chat(messages)
        except Exception as e:
            print(f'Error calling streaming endpoint: {str(e)}')
            # Fallback to non-streaming
            try:
                response = query_endpoint(self.endpoint_name, messages)["content"]
                # Simulate streaming by yielding the whole response
                yield response
            except Exception as fallback_error:
                yield f"Error: {str(fallback_error)}"
    
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
    
    def _format_message_content(self, content):
        """Format handyman response with consistent structure and simple emojis"""
        if not content:
            return content
        
        # Check if this looks like a handyman response
        if self._is_handyman_response(content):
            return self._format_handyman_response(content)
        else:
            # Fall back to general formatting for other types of responses
            return self._format_general_content(content)
    
    def _is_handyman_response(self, content):
        """Check if content follows the standard handyman response format"""
        # Make the check more flexible
        has_time = re.search(r'estimated\s+time:', content, re.IGNORECASE) is not None
        has_confidence = re.search(r'confidence:', content, re.IGNORECASE) is not None
        has_summary = re.search(r'schedule\s+summary:', content, re.IGNORECASE) is not None
        
        return has_time and has_confidence and has_summary
    
    def _format_handyman_response(self, content):
        """Format handyman response with enhanced visual structure"""
        import re
        
        # Extract components using more flexible regex patterns
        time_match = re.search(r'Estimated time:\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
        confidence_match = re.search(r'Confidence:\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
        
        # More flexible pattern for schedule summary
        summary_match = re.search(r'Schedule Summary:\s*\n((?:\s*-\s*.+(?:\n|$))*)', content, re.IGNORECASE | re.MULTILINE)
        
        # More flexible pattern for questions
        questions_match = re.search(r'To improve this estimate[^:]*:\s*\n((?:\s*-\s*.+(?:\n|$))*)', content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        html_parts = []
        
        # Header section with time and confidence
        if time_match or confidence_match:
            html_parts.append('<div class="summary-header">')
            
            if time_match:
                html_parts.append('<div class="estimate-row">')
                html_parts.append('<span class="estimate-emoji">⏱️</span>')
                html_parts.append('<span class="estimate-label">Estimated time:</span>')
                html_parts.append(f'<span>{self._escape_html(time_match.group(1).strip())}</span>')
                html_parts.append('</div>')
            
            if confidence_match:
                confidence = confidence_match.group(1).strip().lower()
                badge_class = "confidence-badge"
                if 'low' in confidence:
                    badge_class += " low"
                elif 'high' in confidence:
                    badge_class += " high"
                
                html_parts.append('<div class="estimate-row">')
                html_parts.append('<span class="estimate-emoji">🎯</span>')
                html_parts.append('<span class="estimate-label">Confidence:</span>')
                html_parts.append(f'<span class="{badge_class}">{self._escape_html(confidence_match.group(1).strip())}</span>')
                html_parts.append('</div>')
            
            html_parts.append('</div>')
        
        # Schedule Summary - always as single bullet point
        if summary_match:
            html_parts.append('<div class="section-header">')
            html_parts.append('<span class="section-emoji">📋</span>')
            html_parts.append('<span>Schedule Summary</span>')
            html_parts.append('</div>')
            html_parts.append('<ul class="enhanced-list task-list">')
            
            # Combine all summary items into one
            summary_text = summary_match.group(1).strip()
            # Remove bullet points and newlines, join with commas
            summary_items = []
            for line in summary_text.split('\n'):
                line = line.strip()
                if line and line.startswith('- '):
                    summary_items.append(line[2:].strip())  # Remove '- ' prefix
            
            if summary_items:
                combined_summary = ', '.join(summary_items)
                html_parts.append('<li>')
                html_parts.append('<span class="list-emoji">🔧</span>')
                html_parts.append(f'<span>{self._escape_html(combined_summary)}</span>')
                html_parts.append('</li>')
            
            html_parts.append('</ul>')
        
        # Questions section
        if questions_match:
            html_parts.append('<div class="section-header">')
            html_parts.append('<span class="section-emoji">❓</span>')
            html_parts.append('<span>To improve this estimate, please answer the following</span>')
            html_parts.append('</div>')
            html_parts.append('<ul class="enhanced-list question-list">')
            
            questions_text = questions_match.group(1).strip()
            for line in questions_text.split('\n'):
                line = line.strip()
                if line and line.startswith('- '):
                    question = line[2:].strip()  # Remove '- ' prefix
                    if question:
                        html_parts.append('<li>')
                        html_parts.append('<span class="list-emoji">💭</span>')
                        html_parts.append(f'<span>{self._escape_html(question)}</span>')
                        html_parts.append('</li>')
            
            html_parts.append('</ul>')
        
        return ''.join(html_parts)
    
    def _format_general_content(self, content):
        """Format general content (non-handyman responses)"""
        # Split content into paragraphs first
        paragraphs = content.split('\n\n')
        formatted_paragraphs = []
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
                
            # Handle different content types within each paragraph
            formatted_paragraph = self._format_paragraph(paragraph.strip())
            formatted_paragraphs.append(formatted_paragraph)
        
        return '<br><br>'.join(formatted_paragraphs)
    
    def _format_paragraph(self, paragraph):
        """Format individual paragraph with proper markup"""
        # Handle code blocks (triple backticks)
        if '```' in paragraph:
            parts = paragraph.split('```')
            formatted_parts = []
            
            for i, part in enumerate(parts):
                if i % 2 == 0:  # Regular text
                    if part.strip():
                        formatted_parts.append(self._format_inline_text(part.strip()))
                else:  # Code block
                    if part.strip():
                        # Extract language if specified
                        lines = part.strip().split('\n')
                        if len(lines) > 1 and not lines[0].strip().startswith(' '):
                            # First line might be language
                            code_content = '\n'.join(lines[1:]) if len(lines) > 1 else lines[0]
                        else:
                            code_content = part.strip()
                        formatted_parts.append(f'<pre><code>{self._escape_html(code_content)}</code></pre>')
            
            return ''.join(formatted_parts)
        
        # Handle bullet points and numbered lists
        lines = paragraph.split('\n')
        if len(lines) > 1:
            # Check if this looks like a list
            list_pattern = re.compile(r'^[\s]*[•\-\*]\s+|^\d+\.\s+')
            if any(list_pattern.match(line) for line in lines if line.strip()):
                formatted_lines = []
                in_list = False
                list_type = None
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    bullet_match = re.match(r'^[•\-\*]\s+(.+)', line)
                    number_match = re.match(r'^\d+\.\s+(.+)', line)
                    
                    if bullet_match:
                        if not in_list or list_type != 'ul':
                            if in_list:
                                formatted_lines.append(f'</{list_type}>')
                            formatted_lines.append('<ul>')
                            in_list = True
                            list_type = 'ul'
                        formatted_lines.append(f'<li>{self._format_inline_text(bullet_match.group(1))}</li>')
                    elif number_match:
                        if not in_list or list_type != 'ol':
                            if in_list:
                                formatted_lines.append(f'</{list_type}>')
                            formatted_lines.append('<ol>')
                            in_list = True
                            list_type = 'ol'
                        formatted_lines.append(f'<li>{self._format_inline_text(number_match.group(1))}</li>')
                    else:
                        if in_list:
                            formatted_lines.append(f'</{list_type}>')
                            in_list = False
                            list_type = None
                        formatted_lines.append(f'<p>{self._format_inline_text(line)}</p>')
                
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                
                return ''.join(formatted_lines)
        
        # Regular paragraph - split by single newlines for line breaks
        lines = paragraph.split('\n')
        formatted_lines = [self._format_inline_text(line.strip()) for line in lines if line.strip()]
        return '<p>' + '<br>'.join(formatted_lines) + '</p>'
    
    def _format_inline_text(self, text):
        """Format inline text elements like bold, italic, code spans"""
        if not text:
            return text
            
        # Handle inline code (single backticks)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # Handle bold (**text** or __text__)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        
        # Handle italic (*text* or _text_) - but not if already in strong tags
        text = re.sub(r'(?<!</?strong>)\*([^*]+)\*(?!</?strong>)', r'<em>\1</em>', text)
        text = re.sub(r'(?<!</?strong>)_([^_]+)_(?!</?strong>)', r'<em>\1</em>', text)
        
        return text
    
    def _escape_html(self, text):
        """Escape HTML special characters"""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#x27;'))
    
    def _render_message(self, message, index):
        """Render a single message with appropriate styling and improved formatting"""
        if message['role'] == '
