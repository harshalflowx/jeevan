// Ensure Eel is ready before trying to use it or expose functions
document.addEventListener("DOMContentLoaded", function() {
    initializeChat();
});

function initializeChat() {
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const voiceInputButton = document.getElementById('voiceInputButton');
    const chatLog = document.getElementById('chatLog');

    if (!messageInput || !sendButton || !chatLog || !voiceInputButton) {
        console.error("Chat or voice elements not found in HTML!");
        return;
    }

    sendButton.addEventListener('click', sendMessage);
    voiceInputButton.addEventListener('click', startVoiceInput);
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    console.log("Chat interface initialized. Eel should be available.");
}

async function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    let messageText = messageInput.value.trim();

    if (messageText === "") {
        return;
    }

    // Clear the input field
    messageInput.value = "";

    // Call Python function (exposed via Eel)
    // This function will also be responsible for adding the user's message to the chat log via add_message_to_chat_js
    try {
        console.log(`JS: Sending to Python: ${messageText}`);
        await eel.handle_user_message_py(messageText)(); // Note the extra () to call the exposed Python function
    } catch (error) {
        console.error("Error calling Python (handle_user_message_py):", error);
        add_message_to_chat_js("Error", "Could not send message to AI backend.");
    }
}

// This function is exposed to Python so Python can call it
eel.expose(add_message_to_chat_js);
function add_message_to_chat_js(sender, message) {
    const chatLog = document.getElementById('chatLog');
    if (!chatLog) {
        console.error("chatLog element not found for add_message_to_chat_js");
        return;
    }
    const messageElement = document.createElement('div');
    messageElement.classList.add('chat-message', sender.toLowerCase() + '-message');

    const senderElement = document.createElement('strong');
    senderElement.textContent = sender + ": ";

    const contentElement = document.createElement('span');
    // To display newlines correctly if the message contains them
    // Replace \n with <br> for HTML display
    contentElement.innerHTML = message.replace(/\n/g, '<br>');

    messageElement.appendChild(senderElement);
    messageElement.appendChild(contentElement);

    chatLog.appendChild(messageElement);
    // Scroll to the bottom of the chat log
    chatLog.scrollTop = chatLog.scrollHeight;
    console.log(`JS: Added to chat: ${sender} - ${message}`);

    // --- TTS Integration: Speak AI responses ---
    if (sender.toLowerCase().startsWith("ai")) { // Speak AI messages and AI_Error messages
        speak_ai_response(message);
    }
}

// --- Web Speech API for TTS ---
let synth;
if ('speechSynthesis' in window) {
    synth = window.speechSynthesis;
} else {
    console.warn("Web Speech API (speechSynthesis) not supported by this browser.");
    update_activity_log_js("Warning: Web Speech API (TTS) not supported. AI responses will not be spoken.");
}

function speak_ai_response(text_to_speak) {
    if (synth) {
        // Basic sanitization: browsers might struggle with overly long text or certain characters.
        // For a PoC, keep it simple. In production, more advanced text chunking/cleaning might be needed.
        // Remove potential markdown like ```python ... ``` for cleaner speech.
        let clean_text = text_to_speak.replace(/```[\s\S]*?```/g, "Code block displayed.");
        // Replace common markdown for lists or emphasis that sound odd when read.
        clean_text = clean_text.replace(/(\*|_){1,2}([^*_]+)\1{1,2}/g, '$2'); // Bold/Italics
        clean_text = clean_text.replace(/`([^`]+)`/g, '$1'); // Inline code
        clean_text = clean_text.replace(/^-\s*/gm, ''); // List items


        if (clean_text.trim() === "") return; // Don't speak empty or only-code-block messages

        const utterance = new SpeechSynthesisUtterance(clean_text);
        // Optional: Configure voice, rate, pitch
        // utterance.lang = 'en-US'; // Can be set if needed
        // const voices = synth.getVoices(); // To select a specific voice
        // utterance.voice = voices[0];
        // utterance.rate = 1; // 0.1 to 10
        // utterance.pitch = 1; // 0 to 2

        utterance.onerror = function(event) {
            console.error('SpeechSynthesisUtterance.onerror', event.error);
            update_activity_log_js(`TTS Error: ${event.error}`);
        };

        // Optional: Cancel any ongoing speech before speaking new message
        // if (synth.speaking) {
        //     synth.cancel();
        // }
        synth.speak(utterance);
        console.log("JS: Attempting to speak: " + clean_text.substring(0, 50) + "...");
    } else {
        console.log("JS: TTS not available, cannot speak: " + text_to_speak.substring(0, 50) + "...");
    }
}


// Placeholder for activity log updates (will be exposed similarly)
eel.expose(update_activity_log_js);
function update_activity_log_js(status_text) {
    const activityLog = document.getElementById('activityLog');
     if (!activityLog) {
        console.error("activityLog element not found");
        return;
    }
    const statusElement = document.createElement('p');
    statusElement.textContent = `[${new Date().toLocaleTimeString()}] ${status_text}`;
    activityLog.appendChild(statusElement);
    activityLog.scrollTop = activityLog.scrollHeight; // Scroll to bottom
    console.log(`JS: Activity Log Updated: ${status_text}`);
}

// Initial message to confirm JS is loaded and can call Python (optional)
// (async function() {
//     try {
//         if (eel && typeof eel.py_version === 'function') { // Check if a simple exposed Python func exists
//             let version = await eel.py_version()();
//             add_message_to_chat_js("System", `Connected to Python backend. Python version: ${version}`);
//         } else {
//             add_message_to_chat_js("System", "Eel loaded, but Python connection test function not found.");
//         }
//     } catch (e) {
//         add_message_to_chat_js("System", "Error connecting to Python backend via Eel on startup.");
//         console.error("Eel startup test error:", e);
//     }
// })();
console.log("script.js loaded. Eel functions exposed. DOMContentLoaded listener set.");
// Add an initial message to the activity log from JS itself
update_activity_log_js("JavaScript interface loaded.");


// --- Web Speech API for STT ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false; // Process single utterances
    recognition.lang = 'en-US';     // Language
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {
        console.log("Voice recognition started. Speak into the microphone.");
        update_activity_log_js("Voice recognition started. Listening...");
        document.getElementById('voiceInputButton').textContent = "🎙️ Listening...";
        document.getElementById('voiceInputButton').disabled = true;
    };

    recognition.onresult = function(event) {
        const transcript = event.results[0][0].transcript;
        console.log("Voice transcript: " + transcript);
        update_activity_log_js(`Voice recognized: "${transcript}"`);

        // Set the transcript to the message input and then send it
        // This reuses the existing sendMessage logic which calls Python
        const messageInput = document.getElementById('messageInput');
        messageInput.value = transcript; // Put recognized text into input field
        sendMessage(); // Send it like a typed message
    };

    recognition.onerror = function(event) {
        console.error("Voice recognition error", event.error);
        let errorMessage = "Voice recognition error: " + event.error;
        if (event.error === 'no-speech') {
            errorMessage = "No speech was detected. Please try again.";
        } else if (event.error === 'audio-capture') {
            errorMessage = "Microphone problem. Ensure it's enabled and permitted.";
        } else if (event.error === 'not-allowed') {
            errorMessage = "Voice input not allowed. Please grant microphone permission.";
        }
        add_message_to_chat_js("AI_Error", errorMessage);
        update_activity_log_js(`Voice recognition failed: ${event.error}`);
    };

    recognition.onend = function() {
        console.log("Voice recognition ended.");
        document.getElementById('voiceInputButton').textContent = "🎤";
        document.getElementById('voiceInputButton').disabled = false;
        update_activity_log_js("Voice recognition ended.");
    };

} else {
    console.warn("Web Speech API (SpeechRecognition) not supported by this browser.");
    update_activity_log_js("Warning: Web Speech API not supported by this browser. Voice input disabled.");
    // Optionally disable or hide the voice input button if API is not supported
    // document.getElementById('voiceInputButton').style.display = 'none';
}

function startVoiceInput() {
    if (recognition) {
        try {
            recognition.start();
        } catch (e) {
            // This can happen if recognition is already started, though onend should prevent it.
            console.error("Error starting voice recognition:", e);
            update_activity_log_js("Error trying to start voice recognition.");
            document.getElementById('voiceInputButton').textContent = "🎤";
            document.getElementById('voiceInputButton').disabled = false;
        }
    } else {
        add_message_to_chat_js("AI_Error", "Voice input is not supported or enabled in your browser.");
        console.warn("Attempted to start voice input, but recognition API is not available.");
    }
}
