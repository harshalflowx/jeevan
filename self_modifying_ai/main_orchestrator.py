import datetime
import os
import logging
import time # For simulating work
import tempfile # For self-update code generation
import re # For extracting code from LLM response
import ast # For basic syntax validation of generated code
import sys # For sys.executable
import subprocess # For running pytest
import asyncio # For asyncio.to_thread if used

# Setup basic logging for the orchestrator
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Import core components
from core_components.command_history_logger import CommandHistoryLogger
from core_components.feedback_manager import FeedbackManager
from core_components.auth_manager import AuthManager
from core_components.code_executor import CodeExecutor, CodeExecutionResult
from core_components.ai_updater import AIUpdater

# Import service connectors
from services.base_service_connector import ServiceCredentials
from services.mock_llm_service import MockLanguageModelService
from services.mock_search_service import MockSearchService
from services.gemini_service_connector import GeminiServiceConnector # New import

from command_interface import CommandInterface

# --- Configuration ---
# These would typically come from a config file or environment variables
DB_PATH = "command_history.db" # Shared with CommandHistoryLogger
# AI_ADMIN_API_KEY_FOR_TESTING is now primarily managed by CommandInterface's DEFAULT_API_KEY
# but ensure the hash for "test_api_key_123" is set in AI_ADMIN_HASHED_KEY env var.
# To make AuthManager work, you'd generate a hash for AI_ADMIN_API_KEY_FOR_TESTING
# and set it as AI_ADMIN_HASHED_KEY environment variable.
# For this basic orchestrator, we'll simulate AuthManager usage.
# Run this to get a hash for the above key:
# python -c "import hashlib; print(hashlib.sha256('test_api_key_123'.encode()).hexdigest())"
# Then: export AI_ADMIN_HASHED_KEY="the_generated_hash"

# AI Updater configuration (relative to this script's location or an absolute path)
# For simplicity, let's assume the orchestrator is in the root of the 'self_modifying_ai' project
# and 'base_code_dir' is where the AI's own code (like core_components) resides.
ORCHESTRATOR_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_CODE_DIR = ORCHESTRATOR_DIR # AI's source code is here
STAGING_DIR = os.path.join(ORCHESTRATOR_DIR, "staging")
BACKUP_DIR = os.path.join(ORCHESTRATOR_DIR, "backup")


class MainOrchestrator:
    def __init__(self):
        logger.info("Initializing Main AI Loop / Orchestrator...")

        # Initialize components
        self.history_logger = CommandHistoryLogger(db_name=DB_PATH)
        self.feedback_mgr = FeedbackManager(command_history_logger=self.history_logger)
        self.auth_mgr = AuthManager() # Relies on AI_ADMIN_HASHED_KEY env var
        self.code_executor = CodeExecutor(default_timeout_seconds=10.0)
        self.ai_updater = AIUpdater(base_code_dir=BASE_CODE_DIR, staging_dir=STAGING_DIR, backup_dir=BACKUP_DIR)

        # Initialize service connectors (using mock versions for now)
        # Initialize actual LLM Service (Gemini)
        # It will try to use GEMINI_API_KEY from environment.
        self.gemini_llm_service = GeminiServiceConnector()
        logger.info(f"Gemini Service Connector initialized. API Key loaded: {bool(self.gemini_llm_service.api_key)}")

        # Keep Mock LLM Service for fallback or specific mock commands if needed
        mock_llm_creds = ServiceCredentials(api_key="mock_llm_api_key_valid")
        self.mock_llm_service = MockLanguageModelService(credentials=mock_llm_creds)

        # Mock Search Service (requires API key as per its mock implementation)
        search_creds = ServiceCredentials(api_key="mock_search_api_key_valid") # Use the key expected by MockSearchService
        self.search_service = MockSearchService(credentials=search_creds)

        self.command_interface = CommandInterface()

        self.user_id_for_testing = "test_user_001" # Could be enhanced to get from auth later
        logger.info("Orchestrator initialized successfully.")

    async def _execute_staged_tests(self, staged_test_file_abs_path: str, staging_root_abs_path: str) -> tuple[bool, str]:
        """
        Executes pytest on the staged test file.
        Args:
            staged_test_file_abs_path: Absolute path to the test file in the staging area.
            staging_root_abs_path: Absolute path to the root of the staging area (for PYTHONPATH).
        Returns:
            A tuple (tests_passed: bool, test_output: str).
        """
        logger.info(f"Executing tests for: {staged_test_file_abs_path}")
        self.command_interface.speak("Running automated tests on the generated code.")
        print(f"AI: Running automated tests from {staged_test_file_abs_path}...")

        # Prepare environment for subprocess, ensuring pytest can find the staged main code
        env = os.environ.copy()
        # Prepend staging_root_abs_path to PYTHONPATH. This allows tests to import modules
        # from the root of the staging area (e.g., from staging/utils/generated_utils.py)
        # The AIUpdater stages files like `utils/generated_utils.py` directly under staging_root_abs_path.
        # So, if test is `from utils.generated_utils import ...`, staging_root_abs_path is the correct root.
        existing_pythonpath = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = f"{staging_root_abs_path}{os.pathsep}{existing_pythonpath}"

        logger.info(f"Using PYTHONPATH for pytest: {env['PYTHONPATH']}")

        cmd = [sys.executable, "-m", "pytest", staged_test_file_abs_path]

        try:
            # Using asyncio.to_thread to run the blocking subprocess.run in a non-blocking way
            process = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60 # Add a timeout for test execution
            )
            test_output = f"Pytest STDOUT:\n{process.stdout}\n"
            if process.stderr:
                test_output += f"Pytest STDERR:\n{process.stderr}\n"

            logger.info(f"Pytest finished. Return code: {process.returncode}")
            logger.info(f"Pytest output:\n{test_output}")

            if process.returncode == 0:
                return True, test_output # All tests passed
            elif process.returncode == 1: # Pytest specific: tests failed
                return False, test_output
            else: # Other errors (e.g., pytest internal error, usage error)
                return False, f"Pytest execution error (code {process.returncode}).\n{test_output}"
        except subprocess.TimeoutExpired:
            logger.error(f"Pytest execution timed out for {staged_test_file_abs_path}")
            return False, "Pytest execution timed out."
        except Exception as e:
            logger.error(f"Error running pytest for {staged_test_file_abs_path}: {e}", exc_info=True)
            return False, f"An unexpected error occurred while running pytest: {str(e)}"


    async def process_command(self, command_struct: dict | None):
        """
        Processes a single structured command.
        This is a simplified dispatcher for the basic orchestrator.
        """
        if not command_struct: # Handles None from Ctrl+C in CommandInterface
            logger.info("No command received from interface.")
            return

        command_name = command_struct.get("command_name")
        parameters = command_struct.get("parameters", {})
        api_key = command_struct.get("api_key") # For authentication

        command_id = None
        start_time = time.monotonic()

        try:
            # Handle special internal commands from CommandInterface first
            if command_name == "quit_session":
                logger.info("Quit session command received. Orchestrator will stop.")
                response_text = "Goodbye!"
                self.command_interface.speak(response_text)
                print(f"AI: {response_text}")
                return {"status": "quit"}

            if command_name == "show_help":
                # Log this as an action, as it's a user request
                command_id = self.history_logger.log_command_received(command_name, parameters, self.user_id_for_testing)
                self.command_interface.display_help() # CI displays help
                duration_ms = int((time.monotonic() - start_time) * 1000)
                self.feedback_mgr.report_success(command_id, "Help displayed.", duration_ms=duration_ms)
                return


            # 1. Log command reception (even before auth for audit)
            command_id = self.history_logger.log_command_received(
                command_name=command_name,
                parameters=parameters,
                user_id=self.user_id_for_testing # Replace with actual user ID when available
            )
            # User already sees their input, so immediate feedback might be redundant here.
            # self.feedback_mgr.report_status(command_id, f"Command '{command_name}' received. Processing...", status_level="INFO")

            # 2. Authenticate (critical step)
            if not self.auth_mgr.is_authenticated(api_key):
                err_msg = "Authentication failed. Invalid API key."
                logger.error(f"Command ID {command_id}: {err_msg}")
                duration_ms = int((time.monotonic() - start_time) * 1000)
                ai_response_text = f"AI Error: {err_msg}"
                print(ai_response_text)
                self.command_interface.speak(err_msg) # Speak only the error
                self.history_logger.update_command_status(command_id, "failure", error_message=err_msg, duration_ms=duration_ms)
                return

            self.history_logger.update_command_status(command_id, "processing_authenticated")

            # 3. Command Dispatching
            if command_name == "execute_code":
                code_to_execute = parameters.get("code_snippet")
                if not code_to_execute:
                    raise ValueError("Missing 'code_snippet' for 'execute_code'.")

                feedback_text = "Executing your code..."
                print(f"AI: {feedback_text}")
                self.command_interface.speak(feedback_text)
                exec_result: CodeExecutionResult = self.code_executor.execute_python_snippet(code_to_execute)

                duration_ms = int((time.monotonic() - start_time) * 1000)
                if exec_result.success:
                    stdout_short = exec_result.stdout.strip()[:200] # Limit spoken length
                    speak_text = f"Code executed. Output: {stdout_short}"
                    print_text = f"AI: Code executed. Output:\n{exec_result.stdout}"
                    if exec_result.stderr.strip():
                        stderr_short = exec_result.stderr.strip()[:200]
                        speak_text += f"\nWarnings or Errors: {stderr_short}"
                        print_text += f"\nAI: Errors/Warnings during execution:\n{exec_result.stderr}"
                    print(print_text)
                    self.command_interface.speak(speak_text)
                    self.feedback_mgr.report_success(command_id, "Code snippet executed.",
                                                     result_summary=f"Stdout: {exec_result.stdout[:100]}...",
                                                     duration_ms=duration_ms, data={"stdout": exec_result.stdout, "stderr": exec_result.stderr, "return_code": exec_result.return_code})
                else:
                    error_detail = exec_result.error or f"Script error: {exec_result.stderr.strip()}"
                    feedback_text = f"Code execution failed. {error_detail}"
                    print(f"AI Error: {feedback_text}")
                    self.command_interface.speak(feedback_text)
                    self.feedback_mgr.report_failure(command_id, "Code snippet execution failed.",
                                                     error_message=error_detail,
                                                     duration_ms=duration_ms, data={"stdout": exec_result.stdout, "stderr": exec_result.stderr, "return_code": exec_result.return_code})

            elif command_name == "gemini_generate_text" or command_name == "mock_llm_generate_text":
                prompt = parameters.get("prompt")
                if not prompt:
                    raise ValueError(f"Missing 'prompt' for '{command_name}'.")

                service_to_use = self.gemini_llm_service if command_name == "gemini_generate_text" else self.mock_llm_service
                service_name_for_user = "Gemini LLM" if command_name == "gemini_generate_text" else "Mock LLM"

                feedback_text = f"Thinking with {service_name_for_user}..."
                print(f"AI: {feedback_text} (Prompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''})")
                self.command_interface.speak(feedback_text)

                try:
                    llm_result = await service_to_use.execute("generate_text", {"prompt": prompt})
                    duration_ms = int((time.monotonic() - start_time) * 1000)

                    if llm_result.get("success"):
                        generated_text = llm_result.get("data", {}).get("generated_text", "No text generated.")
                        print(f"AI ({service_name_for_user}): {generated_text}")
                        self.command_interface.speak(generated_text)
                        self.feedback_mgr.report_success(command_id, f"{service_name_for_user} generated text.",
                                                         result_summary=generated_text[:100]+"...",
                                                         duration_ms=duration_ms, data=llm_result.get("data"))
                    else:
                        error_msg = llm_result.get("error", f"Unknown {service_name_for_user} error")
                        details = llm_result.get("details", "")
                        full_error_msg = f"{error_msg}{(': ' + str(details)) if details else ''}"
                        feedback_text = f"{service_name_for_user} task failed. {full_error_msg}"
                        print(f"AI Error: {feedback_text}")
                        self.command_interface.speak(f"Error with {service_name_for_user}. {error_msg}")
                        self.feedback_mgr.report_failure(command_id, f"{service_name_for_user} failed.",
                                                         error_message=full_error_msg,
                                                         duration_ms=duration_ms, data=llm_result)
                except ConnectionError as e:
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    error_msg = f"Failed to connect to {service_name_for_user}: {e}"
                    print(f"AI Error: {error_msg}")
                    self.command_interface.speak(error_msg)
                    self.feedback_mgr.report_failure(command_id, f"{service_name_for_user} connection failed.", error_message=error_msg, duration_ms=duration_ms)
                except AuthenticationError as e:
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    error_msg = f"Authentication failed with {service_name_for_user}: {e}"
                    print(f"AI Error: {error_msg}")
                    self.command_interface.speak(error_msg)
                    self.feedback_mgr.report_failure(command_id, f"{service_name_for_user} authentication failed.", error_message=error_msg, duration_ms=duration_ms)

            elif command_name == "search_web_mock":
                query = parameters.get("query")
                if not query:
                    raise ValueError("Missing 'query' for 'search_web_mock'.")

                feedback_text = f"Searching mock web for: {query[:50]}{'...' if len(query) > 50 else ''}"
                print(f"AI: {feedback_text}")
                self.command_interface.speak(f"Searching mock web for {query}")
                search_result = await self.search_service.execute("search_web", {"query": query})
                duration_ms = int((time.monotonic() - start_time) * 1000)

                if search_result.get("success"):
                    results = search_result.get("data",{}).get("results",[])
                    response_text_print = ""
                    response_text_speak = ""
                    if results:
                        response_text_print = f"Found {len(results)} mock results:\n"
                        for i, res in enumerate(results[:3]):
                            response_text_print += f"  {i+1}. {res.get('title')} - {res.get('snippet')} ({res.get('url')})\n"
                        if len(results) > 3:
                            response_text_print += f"  ...and {len(results)-3} more."
                        response_text_speak = f"Found {len(results)} mock results. Top result: {results[0].get('title')}."
                    else:
                        response_text_print = "No mock results found for your query."
                        response_text_speak = response_text_print

                    print(f"AI: {response_text_print.strip()}")
                    self.command_interface.speak(response_text_speak)
                    self.feedback_mgr.report_success(command_id, "Mock search successful.", result_summary=f"Found {len(results)} results.", duration_ms=duration_ms, data=search_result.get("data"))
                else:
                    error_msg = search_result.get("error", "Unknown search error")
                    feedback_text = f"Mock search failed. {error_msg}"
                    print(f"AI Error: {feedback_text}")
                    self.command_interface.speak(feedback_text)
                    self.feedback_mgr.report_failure(command_id, "Mock web search failed.", error_message=error_msg, duration_ms=duration_ms, data=search_result)

            elif command_name == "propose_self_update":
                task_description = parameters.get("task_description")
                if not task_description:
                    raise ValueError("Missing 'task_description' for 'propose_self_update'.")

                feedback_text = f"Attempting to generate code for update task: '{task_description[:50]}...'"
                print(f"AI: {feedback_text}")
                self.command_interface.speak(feedback_text)

                # Define the target path for the new utility module
                # Ensure BASE_CODE_DIR is correctly pointing to the 'self_modifying_ai' root
                relative_target_path = os.path.join("utils", "generated_utils.py")
                # Construct a more detailed prompt for the LLM
                # Asking for main code and test code separately.
                # Using markers for easier parsing.
                main_code_marker = "===BEGIN_MAIN_CODE==="
                end_main_code_marker = "===END_MAIN_CODE==="
                test_code_marker = "===BEGIN_TEST_CODE==="
                end_test_code_marker = "===END_TEST_CODE==="

                llm_prompt = (
                    f"You are a helpful AI assistant that writes Python code and corresponding pytest unit tests.\n"
                    f"I need a Python utility module and its tests.\n"
                    f"The main utility code will be saved as '{relative_target_path}'.\n"
                    f"The task for the main utility code is: {task_description}.\n\n"
                    f"Generate the complete Python code for this utility module. Place this code between the markers "
                    f"'{main_code_marker}' and '{end_main_code_marker}'.\n"
                    f"Do not include any explanations or comments outside the Python code itself for this part.\n"
                    f"If the task is to create a function, ensure the file contains only that function and any necessary imports.\n\n"
                    f"After generating the main utility code, generate `pytest` unit tests for it. "
                    f"The tests should cover typical use cases and edge cases for the described functionality. "
                    f"Assume the utility module can be imported directly (e.g., `from utils.generated_utils import your_function`).\n"
                    f"Place these pytest unit tests between the markers '{test_code_marker}' and '{end_test_code_marker}'.\n"
                    f"Do not include any explanations or comments outside the Python code itself for the test part.\n\n"
                    f"Example of expected output structure:\n"
                    f"{main_code_marker}\n"
                    f"def greet_user(name):\n"
                    f"    return f'Hello, {{name}}! Welcome to the AI system.'\n"
                    f"{end_main_code_marker}\n\n"
                    f"{test_code_marker}\n"
                    f"import pytest\n"
                    f"from utils.generated_utils import greet_user # Adjust import based on actual save path if needed by tests\n\n"
                    f"def test_greet_user_typical():\n"
                    f"    assert greet_user('Alice') == 'Hello, Alice! Welcome to the AI system.'\n\n"
                    f"def test_greet_user_empty_name():\n"
                    f"    assert greet_user('') == 'Hello, ! Welcome to the AI system.'\n"
                    f"{end_test_code_marker}\n\n"
                    f"Ensure the markers are exactly as specified and on their own lines."
                )

                llm_response = await self.gemini_llm_service.execute("generate_text", {"prompt": llm_prompt})
                duration_ms = int((time.monotonic() - start_time) * 1000)

                if llm_response.get("success"):
                    generated_code = llm_response.get("data", {}).get("generated_text")
                    if not generated_code:
                        error_msg = "LLM generated an empty response."
                        print(f"AI Error: {error_msg}")
                        self.command_interface.speak(error_msg)
                        self.feedback_mgr.report_failure(command_id, "Self-update code generation failed.", error_message=error_msg, duration_ms=duration_ms)
                        return

                    # --- Phase 3: Extract Main Code and Test Code using Markers ---
                    raw_llm_output = generated_code # Keep original for logging if needed

                    def extract_code_between_markers(text, start_marker, end_marker):
                        try:
                            start_index = text.index(start_marker) + len(start_marker)
                            end_index = text.index(end_marker, start_index)
                            return text[start_index:end_index].strip()
                        except ValueError: # Handles if markers are not found
                            return None

                    code_to_stage = extract_code_between_markers(raw_llm_output, main_code_marker, end_main_code_marker)
                    test_code_to_stage = extract_code_between_markers(raw_llm_output, test_code_marker, end_test_code_marker)

                    if not code_to_stage:
                        error_msg = f"Could not extract main code using markers '{main_code_marker}' and '{end_main_code_marker}'. LLM output might not conform to the expected format."
                        logger.error(f"Command ID {command_id}: {error_msg}. Raw LLM output:\n{raw_llm_output}")
                        print(f"AI Error: {error_msg}")
                        self.command_interface.speak("Failed to extract main code from LLM response.")
                        self.feedback_mgr.report_failure(command_id, "Self-update code extraction failed.", error_message=error_msg, duration_ms=duration_ms)
                        return

                    if not test_code_to_stage:
                        # This could be a warning or an error depending on strictness. For now, make it an error.
                        error_msg = f"Could not extract test code using markers '{test_code_marker}' and '{end_test_code_marker}'. LLM output might not conform."
                        logger.error(f"Command ID {command_id}: {error_msg}. Raw LLM output:\n{raw_llm_output}")
                        print(f"AI Error: {error_msg}")
                        self.command_interface.speak("Failed to extract test code from LLM response. Main code was extracted but tests are missing.")
                        # Decide if we proceed without tests or fail. For robust self-update, tests are crucial.
                        self.feedback_mgr.report_failure(command_id, "Self-update test code extraction failed.", error_message=error_msg, duration_ms=duration_ms)
                        return # Stop if tests are missing

                    print(f"AI: LLM generated main code:\n---\n{code_to_stage}\n---")
                    print(f"AI: LLM generated test code:\n---\n{test_code_to_stage}\n---")
                    self.command_interface.speak("Main code and test code have been generated by the LLM. Performing syntax validation on main code...")

                    # --- Phase 2: Basic Validation (on main code) ---
                    try:
                        ast.parse(code_to_stage)
                        validation_msg = "Main code syntax validation passed."
                        print(f"AI: {validation_msg}")
                        self.command_interface.speak(validation_msg)
                    except SyntaxError as e_syntax:
                        error_msg = f"Generated main code failed syntax validation: {e_syntax}"
                        logger.error(f"Command ID {command_id}: {error_msg}", exc_info=True)
                        print(f"AI Error: {error_msg}")
                        self.command_interface.speak("Generated main code has syntax errors. Cannot proceed.")
                        self.feedback_mgr.report_failure(command_id, "Self-update main code validation failed.", error_message=str(e_syntax), duration_ms=duration_ms)
                        return

                    # --- Phase 3: Basic Validation (on test code) ---
                    try:
                        ast.parse(test_code_to_stage)
                        validation_msg_tests = "Test code syntax validation passed."
                        print(f"AI: {validation_msg_tests}")
                        self.command_interface.speak(validation_msg_tests)
                    except SyntaxError as e_syntax_tests:
                        error_msg = f"Generated test code failed syntax validation: {e_syntax_tests}"
                        logger.error(f"Command ID {command_id}: {error_msg}", exc_info=True)
                        print(f"AI Error: {error_msg}")
                        self.command_interface.speak("Generated test code has syntax errors. Cannot proceed with testing.")
                        self.feedback_mgr.report_failure(command_id, "Self-update test code validation failed.", error_message=str(e_syntax_tests), duration_ms=duration_ms)
                        return

                    # --- Staging Main Code and Test Code ---
                    staged_main_code_path = None
                    staged_test_code_path = None
                    relative_test_target_path = os.path.join("tests", "staged_tests", f"test_{os.path.basename(relative_target_path)}")

                    try:
                        # Stage main code
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', prefix='llm_main_') as tmp_main_code_file:
                            tmp_main_code_file.write(code_to_stage)
                            temp_main_code_file_path = tmp_main_code_file.name
                        staged_main_code_path = self.ai_updater.stage_code_from_source(temp_main_code_file_path, relative_target_path)
                        os.remove(temp_main_code_file_path)
                        print(f"AI: Main code staged to '{staged_main_code_path}'.")

                        # Stage test code
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', prefix='llm_test_') as tmp_test_code_file:
                            tmp_test_code_file.write(test_code_to_stage)
                            temp_test_code_file_path = tmp_test_code_file.name
                        staged_test_code_path = self.ai_updater.stage_code_from_source(temp_test_code_file_path, relative_test_target_path)
                        os.remove(temp_test_code_file_path)
                        print(f"AI: Test code staged to '{staged_test_code_path}'.")

                        staged_all_msg = f"Main code and test code generated, validated, and staged."
                        self.command_interface.speak(staged_all_msg)
                        # Log intermediate success of staging, actual success is after application (or testing pass)
                        self.history_logger.update_command_status(command_id, "processing_staged_for_test", result_summary="Code and tests staged for automated testing.")

                        # --- Phase 3: Automated Test Execution (Next Step in Plan) ---
                        # For now, we'll skip actual test execution and go to user confirmation
                        # This part will be filled in the "Implement Test Execution Sub-Process" step.
                        print("AI: Automated test execution would happen here. (Skipping for now)")
                        self.command_interface.speak("Automated test execution step is next. For now, skipping to confirmation.")

                        # --- Phase 2: User Confirmation & Controlled Application (existing logic) ---
                        # This confirmation will eventually be after successful automated tests.
                        confirmation_prompt = (
                            f"Main code staged to '{staged_main_code_path}' and test code to '{staged_test_code_path}'.\n"
                            f"Automated tests are currently skipped. If you proceed, this will apply the main code changes to the live file: "
                            f"'{os.path.join(self.ai_updater.base_code_dir, relative_target_path)}'.\n"
                            f"Do you want to apply this update now (without automated testing results)?"
                        )
                        if self.feedback_mgr.request_confirmation(confirmation_prompt):
                            self.command_interface.speak("Applying update as per your confirmation.")
                            print("AI: Applying update...")
                            try:
                                # Backup before applying
                                backup_info = self.ai_updater.backup_module_or_file(relative_target_path)
                                if backup_info:
                                    bk_msg = f"Backed up existing '{relative_target_path}' to '{backup_info}'."
                                    print(f"AI: {bk_msg}")
                                    self.command_interface.speak(bk_msg)
                                else:
                                    bk_msg = f"No existing file at '{relative_target_path}' to back up. Proceeding with new file creation."
                                    print(f"AI: {bk_msg}")
                                    self.command_interface.speak(bk_msg)

                                # Apply the update
                                applied_path = self.ai_updater.apply_staged_update(relative_target_path)
                                success_apply_msg = f"Update successfully applied to '{applied_path}'."
                                print(f"AI: {success_apply_msg}")
                                self.command_interface.speak(success_apply_msg)
                                self.feedback_mgr.report_success(command_id, "Self-update applied.", result_summary=success_apply_msg, duration_ms=duration_ms)
                            except Exception as e_apply:
                                error_apply_msg = f"Failed to apply update: {e_apply}"
                                logger.error(f"Command ID {command_id}: {error_apply_msg}", exc_info=True)
                                print(f"AI Error: {error_apply_msg}")
                                self.command_interface.speak("Failed to apply the update.")
                                self.feedback_mgr.report_failure(command_id, "Self-update application failed.", error_message=str(e_apply), duration_ms=duration_ms)
                        else:
                            cancel_msg = "Update application cancelled by user. Staged code remains for review."
                            print(f"AI: {cancel_msg}")
                            self.command_interface.speak(cancel_msg)
                            self.feedback_mgr.report_failure(command_id, "Self-update cancelled by user.", result_summary=cancel_msg, duration_ms=duration_ms, error_message="User cancellation") # error_message might be better

                    except Exception as e_stage:
                        error_msg = f"Failed to stage generated code after validation: {e_stage}"
                        logger.error(f"Command ID {command_id}: {error_msg}", exc_info=True)
                        print(f"AI Error: {error_msg}")
                        self.command_interface.speak("Failed to stage the generated code.")
                        self.feedback_mgr.report_failure(command_id, "Self-update code staging failed.", error_message=str(e_stage), duration_ms=duration_ms)

                else:
                    error_msg = llm_response.get("error", "LLM task failed for unknown reason.")
                    details = llm_response.get("details", "")
                    full_error_msg = f"{error_msg}{(': ' + str(details)) if details else ''}"
                    print(f"AI Error: Failed to generate code using LLM. {full_error_msg}")
                    self.command_interface.speak(f"Failed to generate code using LLM. {error_msg}")
                    self.feedback_mgr.report_failure(command_id, "Self-update code generation failed (LLM error).", error_message=full_error_msg, duration_ms=duration_ms)

            else:
                err_unhandled_cmd = f"I don't know how to handle the command '{command_name}'."
                print(f"AI: {err_unhandled_cmd}")
                self.command_interface.speak(err_unhandled_cmd)
                raise NotImplementedError(f"Command '{command_name}' is not implemented in orchestrator.")

        except Exception as e:
            err_msg_for_user = f"An internal error occurred: {str(e)}"
            print(f"AI Error: {err_msg_for_user}")
            self.command_interface.speak("I encountered an internal error.")
            logger.error(f"Command ID {command_id if command_id else 'N/A'}: Unhandled exception: {e}", exc_info=True)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            if command_id:
                self.history_logger.update_command_status(command_id, "failure", error_message=str(e), duration_ms=duration_ms)
            # No need for feedback_mgr.report_failure here as we've printed directly.

        finally:
            # Reduced noise by removing this log, as user gets direct feedback.
            # if command_id:
            #     log_entry = self.history_logger.get_command_log(command_id)
            #     logger.info(f"Command ID {command_id}: Processing complete. Final status: {log_entry.get('status') if log_entry else 'Unknown'}")
            pass


async def chat_loop(orchestrator: MainOrchestrator):
    """
    Main loop for the chat interface.
    """
    print("\n--- AI Chat Interface Active ---")
    print("Type 'help' for commands, 'voice' to enable voice input for next command, or 'quit' to exit.")

    use_voice_next = False
    while True:
        command_struct = None
        if use_voice_next:
            print("AI: Switched to voice input mode for this command.")
            self.command_interface.speak("Please say your command.")
            voice_input_text = orchestrator.command_interface.listen_for_voice_command()
            if voice_input_text:
                command_struct = orchestrator.command_interface.parse_user_input(voice_input_text)
            else:
                # Failed to get voice input or understand it, remain in voice mode or switch back?
                # For PoC, let's switch back to text and let user type 'voice' again.
                self.command_interface.speak("Voice input failed or was not understood. Please use text.")
                print("AI: Voice input failed/not understood. Type 'voice' again or use text.")
            use_voice_next = False # Reset after attempting voice input

        if not command_struct: # If not using voice, or voice failed
            user_text_input = orchestrator.command_interface.get_command_from_console() # This now just gets text
            if user_text_input and user_text_input.strip().lower() in ["voice", "listen"]:
                use_voice_next = True
                print("AI: Voice input enabled for the next command. Say your command after the prompt.")
                self.command_interface.speak("Voice input enabled for next command.")
                print("-" * 20)
                continue # Restart loop to immediately use voice
            command_struct = user_text_input # Already parsed by get_command_from_console if it's a command

        if command_struct and command_struct.get("command_name") == "quit_session":
            await orchestrator.process_command(command_struct) # Handles speaking "Goodbye"
            break

        # Process the command (either from text or parsed voice)
        processed_result = await orchestrator.process_command(command_struct)

        # If process_command returned a special status (like "quit" from earlier), handle it
        if isinstance(processed_result, dict) and processed_result.get("status") == "quit":
            break

        print("-" * 20) # Separator between interactions


if __name__ == "__main__":
    if not os.environ.get("AI_ADMIN_HASHED_KEY"):
        logger.warning("CRITICAL: AI_ADMIN_HASHED_KEY environment variable is not set for AuthManager.")
        logger.warning("Please set it to the hash of 'test_api_key_123' for default authentication to work.")
        # Example hash for 'test_api_key_123' is '150756332533defaace04390d6066ab01e9ef740dd0b885f90978910c8af8da9'

    orchestrator = MainOrchestrator()

    import asyncio
    try:
        asyncio.run(chat_loop(orchestrator))
    except KeyboardInterrupt:
        print("\nAI session terminated by user (Ctrl+C).")
    finally:
        print("\n--- Recent Command Logs (from DB) ---")
        recent_logs = orchestrator.history_logger.get_all_logs(limit=10)
        if recent_logs:
            for log_entry in recent_logs: # Renamed 'log' to 'log_entry' to avoid conflict
                result_summary = log_entry.get('result_summary')
                result_display = (result_summary[:50] + '...') if result_summary and len(result_summary) > 50 else result_summary if result_summary else "N/A"
                print(f"ID: {log_entry['command_id']}, Name: {log_entry['command_name']}, Status: {log_entry['status']}, Result: {result_display}")
        else:
            print("No logs found in the database.")
