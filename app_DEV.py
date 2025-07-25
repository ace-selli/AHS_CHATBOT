import streamlit as st
import streamlit.components.v1 as components
import datetime
import uuid
import time
import threading
import os
import requests
import io
import base64

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

def transcribe_audio_azure(audio_data):
    """Transcribe audio using Azure Speech-to-Text REST API"""
    try:
        # Get Azure credentials from Streamlit secrets
        subscription_key = st.secrets.get("AZURE_SPEECH_KEY")
        region = st.secrets.get("AZURE_SPEECH_REGION", "eastus")
        
        if not subscription_key:
            raise Exception("Azure Speech subscription key not found in secrets")
        
        # Azure Speech-to-Text endpoint
        endpoint = f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        
        headers = {
            'Ocp-Apim-Subscription-Key': subscription_key,
            'Content-Type': 'audio/wav; codecs=audio/pcm; samplerate=16000',
            'Accept': 'application/json'
        }
        
        params = {
            'language': 'en-US',
            'format': 'detailed'
        }
        
        # Send audio data to Azure
        response = requests.post(endpoint, headers=headers, params=params, data=audio_data)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract transcript from Azure response
        if result.get('RecognitionStatus') == 'Success':
            if result.get('NBest') and len(result['NBest']) > 0:
                return result['NBest'][0]['Display']
            elif result.get('DisplayText'):
                return result['DisplayText']
        else:
            raise Exception(f"Azure transcription failed: {result.get('RecognitionStatus', 'Unknown error')}")
            
        return ""
        
    except Exception as e:
        print(f"Azure STT error: {str(e)}")
        raise Exception(f"Speech transcription failed: {str(e)}")

def create_speech_to_text_component():
    """Create a custom STT component that records audio and sends to Azure"""
    stt_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {
                font-family: 'DM Sans', sans-serif;
                margin: 0;
                padding: 10px;
                background: transparent;
            }
            
            .stt-container {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .stt-button {
                background: #FF3621;
                color: white;
                border: none;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
                transition: all 0.3s ease;
                box-shadow: 0 2px 10px rgba(255, 54, 33, 0.3);
            }
            
            .stt-button:hover {
                background: #e6301d;
                transform: scale(1.05);
            }
            
            .stt-button.recording {
                background: #00A972;
                animation: pulse 1.5s infinite;
            }
            
            .stt-button.processing {
                background: #1B3139;
                animation: spin 1s linear infinite;
            }
            
            .stt-button:disabled {
                background: #ccc;
                cursor: not-allowed;
                transform: none;
            }
            
            @keyframes pulse {
                0% {
                    box-shadow: 0 0 0 0 rgba(0, 169, 114, 0.7);
                }
                70% {
                    box-shadow: 0 0 0 10px rgba(0, 169, 114, 0);
                }
                100% {
                    box-shadow: 0 0 0 0 rgba(0, 169, 114, 0);
                }
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .stt-status {
                font-size: 14px;
                color: #1B3139;
                font-weight: 500;
            }
            
            .stt-transcript {
                font-size: 12px;
                color: #666;
                margin-top: 5px;
                font-style: italic;
            }
            
            .error-message {
                color: #FF3621;
                font-size: 12px;
                margin-top: 5px;
            }
            
            .recording-timer {
                font-size: 12px;
                color: #00A972;
                font-weight: bold;
                margin-top: 3px;
            }
        </style>
    </head>
    <body>
        <div class="stt-container">
            <button id="sttButton" class="stt-button" title="Click to start voice recording">
                🎤
            </button>
            <div>
                <div id="sttStatus" class="stt-status">Click to record voice</div>
                <div id="recordingTimer" class="recording-timer" style="display: none;"></div>
                <div id="sttTranscript" class="stt-transcript"></div>
                <div id="errorMessage" class="error-message"></div>
            </div>
        </div>

        <script>
            let mediaRecorder = null;
            let audioChunks = [];
            let isRecording = false;
            let recordingStartTime = null;
            let timerInterval = null;
            
            const button = document.getElementById('sttButton');
            const status = document.getElementById('sttStatus');
            const transcript = document.getElementById('sttTranscript');
            const errorMsg = document.getElementById('errorMessage');
            const timer = document.getElementById('recordingTimer');
            
            function updateTimer() {
                if (recordingStartTime) {
                    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                    const minutes = Math.floor(elapsed / 60);
                    const seconds = elapsed % 60;
                    timer.textContent = `Recording: ${minutes}:${seconds.toString().padStart(2, '0')}`;
                }
            }
            
            function startRecording() {
                navigator.mediaDevices.getUserMedia({ audio: true })
                    .then(stream => {
                        audioChunks = [];
                        mediaRecorder = new MediaRecorder(stream, {
                            mimeType: 'audio/webm;codecs=opus'
                        });
                        
                        mediaRecorder.ondataavailable = event => {
                            if (event.data.size > 0) {
                                audioChunks.push(event.data);
                            }
                        };
                        
                        mediaRecorder.onstop = () => {
                            // Stop all tracks to release microphone
                            stream.getTracks().forEach(track => track.stop());
                            
                            // Process recorded audio
                            const audioBlob = new Blob(audioChunks, { type: 'audio/webm;codecs=opus' });
                            processAudioBlob(audioBlob);
                        };
                        
                        mediaRecorder.start();
                        isRecording = true;
                        recordingStartTime = Date.now();
                        
                        // Update UI
                        button.classList.add('recording');
                        button.innerHTML = '⏹️';
                        status.textContent = 'Recording... Click to stop';
                        timer.style.display = 'block';
                        errorMsg.textContent = '';
                        
                        // Start timer
                        timerInterval = setInterval(updateTimer, 1000);
                        updateTimer();
                        
                    })
                    .catch(error => {
                        console.error('Error accessing microphone:', error);
                        status.textContent = 'Ready to record';
                        errorMsg.textContent = 'Could not access microphone. Please check permissions.';
                        isRecording = false;
                    });
            }
            
            function stopRecording() {
                if (mediaRecorder && isRecording) {
                    mediaRecorder.stop();
                    isRecording = false;
                    
                    // Clear timer
                    if (timerInterval) {
                        clearInterval(timerInterval);
                        timerInterval = null;
                    }
                    
                    // Update UI
                    button.classList.remove('recording');
                    button.classList.add('processing');
                    button.innerHTML = '⏳';
                    button.disabled = true;
                    status.textContent = 'Processing audio...';
                    timer.style.display = 'none';
                }
            }
            
            async function processAudioBlob(audioBlob) {
                try {
                    // Convert webm to wav format for Azure
                    const audioBuffer = await audioBlob.arrayBuffer();
                    const base64Audio = btoa(String.fromCharCode(...new Uint8Array(audioBuffer)));
                    
                    // Send audio to Streamlit backend for Azure processing
                    window.parent.postMessage({
                        type: 'stt_audio',
                        audio_data: base64Audio,
                        audio_type: 'audio/webm'
                    }, '*');
                    
                } catch (error) {
                    console.error('Error processing audio:', error);
                    resetUI();
                    errorMsg.textContent = 'Error processing audio recording';
                }
            }
            
            function resetUI() {
                button.classList.remove('recording', 'processing');
                button.innerHTML = '🎤';
                button.disabled = false;
                status.textContent = 'Click to record voice';
                timer.style.display = 'none';
                recordingStartTime = null;
                
                if (timerInterval) {
                    clearInterval(timerInterval);
                    timerInterval = null;
                }
            }
            
            // Listen for messages from Streamlit
            window.addEventListener('message', function(event) {
                if (event.data.type === 'stt_result') {
                    transcript.textContent = 'Transcript: ' + event.data.transcript;
                    resetUI();
                    status.textContent = 'Transcription complete!';
                } else if (event.data.type === 'stt_error') {
                    resetUI();
                    errorMsg.textContent = event.data.error;
                }
            });
            
            button.addEventListener('click', function() {
                if (isRecording) {
                    stopRecording();
                } else {
                    startRecording();
                }
            });
            
            // Check microphone permissions on load
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                status.textContent = 'Click to record voice';
            } else {
                status.textContent = 'Microphone not supported';
                button.disabled = true;
                button.style.opacity = '0.5';
                errorMsg.textContent = 'Your browser does not support microphone recording.';
            }
        </script>
    </body>
    </html>
    """
    return stt_html

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
        # Add STT transcript storage
        if 'stt_transcript' not in st.session_state:
            st.session_state.stt_transcript = ''
        if 'manual_input' not in st.session_state:
            st.session_state.manual_input = ''
        # Add audio processing state
        if 'audio_processing' not in st.session_state:
            st.session_state.audio_processing = False
    
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
            padding-bottom: 180px; /* Increased to accommodate STT component */
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
        
        /* STT input container */
        .stt-input-container {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .stt-component {
            flex-shrink: 0;
        }
        
        .input-section {
            flex: 1;
        }
        
        /* Aggressive targeting of the gap after info note */
        .info-note + div {
            margin-top: -20px !important;
        }
        
        /* Target Streamlit's vertical block that comes after info note */
        div[data-testid="stMarkdown"]:has(.info-note) + div {
            margin-top: -30px !important;
        }
        
        .azure-stt-info {
            background-color: #E3F2FD;
            border-left: 4px solid #2196F3;
            padding: 8px 12px;
            margin: 10px 0;
            border-radius: 4px;
            font-size: 12px;
            color: #1565C0;
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
    
    def _process_audio_for_transcription(self, audio_data_b64, audio_type):
        """Process audio data and send to Azure for transcription"""
        try:
            # Decode base64 audio data
            audio_data = base64.b64decode(audio_data_b64)
            
            # For now, we'll pass the webm data directly to Azure
            # In production, you might want to convert webm to wav
            transcript = transcribe_audio_azure(audio_data)
            
            if transcript:
                st.session_state.stt_transcript = transcript
                st.success(f"🎤 Voice input captured: '{transcript}'")
                st.rerun()
            else:
                st.warning("No speech detected in the recording. Please try again.")
                
        except Exception as e:
            st.error(f"Speech transcription failed: {str(e)}")
            print(f"Audio transcription error: {e}")
    
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
        st.session_state.stt_transcript = ''
        st.session_state.manual_input = ''
        st.session_state.audio_processing = False
        # Increment counter to force input widget to refresh
        st.session_state.input_key_counter += 1
        st.rerun()
    
    def _process_message(self, message_text):
        """Process a message (from either text input or STT)"""
        if message_text and message_text.strip():
            # Add user message
            st.session_state.chat_history.append({
                'role': 'user', 
                'content': message_text.strip()
            })
            
            # Clear inputs
            st.session_state.stt_transcript = ''
            st.session_state.manual_input = ''
            
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
                    
                except Exception as e:
                    # Add error message
                    error_message = f'Error: {str(e)}'
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': error_message
                    })
            
            # Rerun to refresh the interface
            st.rerun()
    
    def render(self):
        """Main render method for the chatbot interface"""
        # Handle JavaScript messages from STT component first
        if hasattr(st, 'query_params'):
            # This is a simplified approach - in production you'd use session state
            pass
        
        # Title, info note, and chat area in single container to eliminate all gaps
        st.markdown('''
        <div class="content-with-bottom-padding">
        <h2 class="chat-title">Ace Handyman Services Customer Rep</h2>
        <div class="info-note">
            💬 Ask the rep below for handyman job information and estimates. You can type or use voice input powered by Azure Speech Services.
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
        
        # Azure STT info
        st.markdown('''
        <div class="azure-stt-info">
            🎙️ Voice input powered by Microsoft Azure Speech Services - Click microphone to record, click again to stop
        </div>
        ''', unsafe_allow_html=True)
        
        st.markdown('<div class="stt-input-container">', unsafe_allow_html=True)
        
        # STT Component
        col1, col2 = st.columns([1, 6])
        
        with col1:
            st.markdown('<div class="stt-component">', unsafe_allow_html=True)
            
            # Create a placeholder for the STT component
            stt_placeholder = st.empty()
            
            # Create STT component with message handling
            stt_component = components.html(
                create_speech_to_text_component(),
                height=90,
                key=f"stt_component_{st.session_state.input_key_counter}"
            )
            
            # Handle audio messages (this is a simplified approach)
            # In a real implementation, you'd use st.experimental_get_query_params() 
            # or implement a proper callback mechanism
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="input-section">', unsafe_allow_html=True)
            
            # Combine manual input and STT transcript
            current_input = st.session_state.manual_input
            if st.session_state.stt_transcript:
                current_input = st.session_state.stt_transcript
            
            # Text input with current value
            user_input = st.text_area(
                label="Type your message or use
