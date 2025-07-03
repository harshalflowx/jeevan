import re
import speech_recognition as sr
import pyttsx3
import logging

logger = logging.getLogger(__name__)

# This API key should be configured more centrally in a real application.
# For now, we use the one consistent with main_orchestrator.py's test setup.
# It's assumed that the environment variable AI_ADMIN_HASHED_KEY corresponds to this plain text key.
DEFAULT_API_KEY = "test_api_key_123"

class CommandInterface:
    def __init__(self, orchestrator=None, default_api_key: str = DEFAULT_API_KEY):
        """
        Initializes the CommandInterface.

        Args:
            orchestrator: An instance of the MainOrchestrator to send commands to.
                          (Currently not used in this version as parsing happens here)
            default_api_key (str): The default API key to use for parsed commands.
        """
        self.orchestrator = orchestrator # Not directly used yet for sending, but good for context
        self.default_api_key = default_api_key
        self.recognizer = sr.Recognizer()
        self.microphone = None
        try:
            # Attempt to use the default microphone. This might fail if no microphone is found
            # or if PyAudio is not properly installed/configured.
            self.microphone = sr.Microphone()
        except AttributeError as e:
            logger.error(f"Failed to initialize sr.Microphone(). PyAudio might be missing or misconfigured: {e}")
            print("AI Warning: Microphone not found or PyAudio not configured. Voice input will not work.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during microphone initialization: {e}")
            print(f"AI Warning: Error initializing microphone: {e}. Voice input will not work.")

        try:
            self.tts_engine = pyttsx3.init()
        except Exception as e: # Catch potential runtime errors from pyttsx3 init
            logger.error(f"Failed to initialize pyttsx3 TTS engine: {e}")
            print(f"AI Warning: TTS engine failed to initialize: {e}. Voice output will not work.")
            self.tts_engine = None

        print("CommandInterface initialized (Text/Voice Chat Mode).")

    def speak(self, text: str):
        """Vocalizes the given text using TTS."""
        if self.tts_engine:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS engine error: {e}")
                print(f"[TTS Error: {e}]") # Fallback to print if speaking fails
        else:
            # If TTS engine isn't available, just print
            # This is already handled by the main_orchestrator's print statements
            pass

    def listen_for_voice_command(self, timeout_seconds: int = 5, phrase_time_limit_seconds: int = 10) -> str | None:
        """
        Listens for a voice command from the microphone and returns the recognized text.
        Returns None if recognition fails or timeout occurs.
        """
        if not self.microphone:
            self.speak("Microphone is not available. Please use text input.")
            print("AI (Audio): Microphone is not available.") # Also print for clarity
            return None

        with self.microphone as source:
            self.speak("Listening for your command...")
            print("AI (Audio): Listening...")
            try:
                # Adjust recognizer for ambient noise first, if desired
                # self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=timeout_seconds, phrase_time_limit=phrase_time_limit_seconds)
            except sr.WaitTimeoutError:
                logger.warning("No speech detected within timeout.")
                # self.speak("I didn't hear anything.") # Can be noisy
                return None
            except Exception as e:
                logger.error(f"Error during audio listening: {e}")
                self.speak("Sorry, I had trouble with the microphone.")
                return None

        try:
            self.speak("Recognizing...")
            print("AI (Audio): Recognizing...")
            # Using Google Web Speech API by default for SpeechRecognition
            # This requires an active internet connection.
            recognized_text = self.recognizer.recognize_google(audio)
            print(f"You (Voice): {recognized_text}")
            return recognized_text
        except sr.UnknownValueError:
            logger.warning("Google Web Speech API could not understand audio.")
            self.speak("Sorry, I could not understand what you said.")
            return None
        except sr.RequestError as e:
            logger.error(f"Could not request results from Google Web Speech API; {e}")
            self.speak("Sorry, I'm having trouble connecting to the speech service.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during voice recognition: {e}")
            self.speak("Sorry, an unexpected error occurred during voice recognition.")
            return None

    def parse_user_input(self, user_input: str) -> dict | None:
        """
        Parses free-form user input into a structured command.
        Uses simple keyword matching and regular expressions.
        This is a basic implementation and can be significantly improved.
        """
        user_input_lower = user_input.lower().strip()

        # Quit command
        if user_input_lower == "quit" or user_input_lower == "exit":
            return {"command_name": "quit_session", "parameters": {}, "api_key": self.default_api_key}

        # Execute code: "execute code print('hello')" or "run code print('hello')"
        match_exec = re.match(r"^(execute|run) code\s+(.+)", user_input, re.IGNORECASE)
        if match_exec:
            code_snippet = match_exec.group(2).strip()
            return {
                "command_name": "execute_code",
                "parameters": {"code_snippet": code_snippet},
                "api_key": self.default_api_key
            }

        # Gemini LLM generate text: "ask gemini what is ai?" or "gemini prompt what is ai?"
        match_gemini_llm = re.match(r"^(ask gemini|gemini prompt|gemini generate)\s+(.+)", user_input, re.IGNORECASE)
        if match_gemini_llm:
            prompt = match_gemini_llm.group(2).strip()
            return {
                "command_name": "gemini_generate_text",
                "parameters": {"prompt": prompt},
                "api_key": self.default_api_key
            }

        # Mock LLM generate text (fallback or specific testing): "mock llm prompt what is ai?"
        match_mock_llm = re.match(r"^(mock llm prompt|ask mock llm|mock llm generate)\s+(.+)", user_input, re.IGNORECASE)
        if match_mock_llm:
            prompt = match_mock_llm.group(2).strip()
            return {
                "command_name": "mock_llm_generate_text",
                "parameters": {"prompt": prompt},
                "api_key": self.default_api_key
            }

        # Search web: "search web for python programming" or "search python programming"
        match_search = re.match(r"^(search web for|search)\s+(.+)", user_input, re.IGNORECASE)
        if match_search:
            query = match_search.group(2).strip()
            return {
                "command_name": "search_web_mock", # Assumes orchestrator handles this
                "parameters": {"query": query},
                "api_key": self.default_api_key
            }

        # Propose self-update: "propose update: create a function that adds two numbers"
        match_propose_update = re.match(r"^(propose update|request feature|suggest improvement):\s*(.+)", user_input, re.IGNORECASE)
        if match_propose_update:
            task_description = match_propose_update.group(2).strip()
            return {
                "command_name": "propose_self_update",
                "parameters": {"task_description": task_description},
                "api_key": self.default_api_key # This command should be authenticated
            }

        # Help command (basic)
        if user_input_lower == "help":
            return {"command_name": "show_help", "parameters": {}, "api_key": self.default_api_key}


        # If no specific command is matched, treat as a generic Gemini LLM prompt (fallback)
        # This makes the chat feel more like talking to an LLM by default.
        if user_input: # Avoid empty input becoming an LLM prompt
            print(f"[CommandInterface] No specific command matched. Treating as Gemini LLM prompt: '{user_input}'")
            return {
                "command_name": "gemini_generate_text", # Default to Gemini
                "parameters": {"prompt": user_input}, # Send the whole input as prompt
                "api_key": self.default_api_key
            }

        return None # Unrecognized or empty command

    def get_command_from_console(self) -> dict | None:
        """
        Gets input from the console and parses it.
        """
        try:
            user_text = input("You: ")
            return self.parse_user_input(user_text)
        except EOFError: # Handle Ctrl+D or end of input stream
            print("Exiting...")
            return {"command_name": "quit_session", "parameters": {}, "api_key": self.default_api_key}
        except KeyboardInterrupt: # Handle Ctrl+C
            print("\nInterrupted. Type 'quit' to exit.")
            return None # Or return a specific interrupt command if needed


    def display_help(self):
        """Displays help messages for the chat interface."""
        # This method is called by the orchestrator if it receives "show_help"
        print("\n--- AI Command Help ---")
        print("Available command patterns:")
        print("  execute code <your python code>   - Executes the provided Python code.")
        print("  run code <your python code>       - Alias for execute code.")
        print("  ask gemini <your prompt>          - Sends prompt to Gemini LLM.")
        print("  gemini prompt <your prompt>       - Alias for ask gemini.")
        print("  ask mock llm <your prompt>        - Sends prompt to the Mock LLM.")
        print("  mock llm prompt <your prompt>     - Alias for ask mock llm.")
        print("  propose update: <description>     - AI attempts to generate code for the described update.")
        print("  search web for <your query>       - Searches the (mock) web for your query.")
        print("  search <your query>               - Alias for search web for.")
        print("  help                              - Shows this help message.")
        print("  quit / exit                       - Exits the AI chat.")
        print("\nIf your input doesn't match a specific command, it will be sent to Gemini LLM as a prompt by default.")
        print("-------------------------")


if __name__ == '__main__':
    # Example of how this CommandInterface might be used for parsing

    print("--- Command Interface (Text Chat Mode) Example ---")

    ci = CommandInterface()

    test_inputs = [
        "execute code print('Hello from test')",
        "run code for i in range(2): print(i)",
        "llm prompt Tell me about AI.",
        "ask llm What's the weather?",
        "search web for latest AI news",
        "search python tutorials",
        "What is the meaning of life?", # Fallback to LLM
        "help",
        "quit"
    ]

    print("\n--- Testing command parsing ---")
    for text_input in test_inputs:
        print(f"\nInput: \"{text_input}\"")
        parsed_command = ci.parse_user_input(text_input)
        if parsed_command:
            print(f"  Parsed: Command='{parsed_command['command_name']}', Params='{parsed_command['parameters']}'")
            if parsed_command["command_name"] == "show_help":
                ci.display_help()
        else:
            print("  Could not parse command or empty input.")

    print("\n--- Simulating console input loop (type 'quit' to exit) ---")
    # This loop is for testing the get_command_from_console directly.
    # In the real application, main_orchestrator.py would have the main loop.
    while True:
        command_struct = ci.get_command_from_console()
        if command_struct:
            print(f"  [CI Test] Received: {command_struct}")
            if command_struct['command_name'] == 'quit_session':
                print("  [CI Test] Quit command received. Exiting test loop.")
                break
            if command_struct['command_name'] == 'show_help':
                 ci.display_help()
            # Here, a connected orchestrator would process command_struct
        else:
            # Handle cases where get_command_from_console might return None (e.g. Ctrl+C not leading to quit)
            print("  [CI Test] No command parsed from input (e.g., after Ctrl+C).")

    print("\n--- End of Command Interface Example ---")
