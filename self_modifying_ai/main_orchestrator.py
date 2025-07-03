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
import eel # For the Web GUI
from dotenv import load_dotenv # For loading .env file

# Load environment variables from .env file at the very beginning
load_dotenv()

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
from services.base_service_connector import ServiceCredentials, AuthenticationError # Added AuthenticationError here
from services.mock_llm_service import MockLanguageModelService
from services.mock_search_service import MockSearchService
from services.gemini_service_connector import GeminiServiceConnector

from command_interface import CommandInterface

ORCHESTRATOR_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_CODE_DIR = ORCHESTRATOR_DIR
STAGING_DIR = os.path.join(ORCHESTRATOR_DIR, "staging")
BACKUP_DIR = os.path.join(ORCHESTRATOR_DIR, "backup")
DB_PATH = "command_history.db"

class MainOrchestrator:
    def __init__(self):
        logger.info("Initializing Main AI Loop / Orchestrator...")
        if eel.update_activity_log_js: eel.update_activity_log_js("Orchestrator initializing...")()

        self.history_logger = CommandHistoryLogger(db_name=DB_PATH)
        self.feedback_mgr = FeedbackManager(command_history_logger=self.history_logger) # Still used for DB logging
        self.auth_mgr = AuthManager()
        self.code_executor = CodeExecutor(default_timeout_seconds=10.0)
        self.ai_updater = AIUpdater(base_code_dir=BASE_CODE_DIR, staging_dir=STAGING_DIR, backup_dir=BACKUP_DIR)

        self.gemini_llm_service = GeminiServiceConnector()
        if eel.update_activity_log_js: eel.update_activity_log_js(f"Gemini Service Connector initialized. API Key Loaded: {bool(self.gemini_llm_service.api_key)}")()

        mock_llm_creds = ServiceCredentials(api_key="mock_llm_api_key_valid")
        self.mock_llm_service = MockLanguageModelService(credentials=mock_llm_creds)

        search_creds = ServiceCredentials(api_key="mock_search_api_key_valid")
        self.search_service = MockSearchService(credentials=search_creds)

        self.command_interface = CommandInterface()
        self.user_id_for_testing = "test_user_001"
        logger.info("Orchestrator initialized successfully.")
        if eel.update_activity_log_js: eel.update_activity_log_js("Orchestrator initialized successfully.")()

    async def _execute_staged_tests(self, staged_test_file_abs_path: str, staging_root_abs_path: str) -> tuple[bool, str]:
        logger.info(f"Executing tests for: {staged_test_file_abs_path}")
        activity_msg = f"Running automated tests from {os.path.basename(staged_test_file_abs_path)}..."
        if eel.update_activity_log_js: eel.update_activity_log_js(activity_msg)()

        env = os.environ.copy()
        existing_pythonpath = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = f"{staging_root_abs_path}{os.pathsep}{existing_pythonpath}"
        logger.info(f"Using PYTHONPATH for pytest: {env['PYTHONPATH']}")
        cmd = [sys.executable, "-m", "pytest", staged_test_file_abs_path]

        try:
            process = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, env=env, timeout=60
            )
            test_output = f"Pytest STDOUT:\n{process.stdout}\n"
            if process.stderr: test_output += f"Pytest STDERR:\n{process.stderr}\n"
            logger.info(f"Pytest finished. Return code: {process.returncode}. Output:\n{test_output}")

            if process.returncode == 0: return True, test_output
            elif process.returncode == 1: return False, test_output # Tests failed
            else: return False, f"Pytest execution error (code {process.returncode}).\n{test_output}"
        except subprocess.TimeoutExpired:
            logger.error(f"Pytest execution timed out for {staged_test_file_abs_path}")
            return False, "Pytest execution timed out."
        except Exception as e:
            logger.error(f"Error running pytest for {staged_test_file_abs_path}: {e}", exc_info=True)
            return False, f"An unexpected error occurred while running pytest: {str(e)}"

    async def process_command(self, command_struct: dict | None):
        if not command_struct:
            logger.info("No command received from interface.")
            return
        command_name = command_struct.get("command_name")
        parameters = command_struct.get("parameters", {})
        api_key = command_struct.get("api_key")
        command_id = None
        start_time = time.monotonic()
        ai_chat_response = None # Primary message to send back to chat UI

        try:
            if command_name == "quit_session":
                logger.info("Quit session command received.")
                if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI", "Goodbye!")()
                return {"status": "quit"}

            if command_name == "show_help":
                command_id = self.history_logger.log_command_received(command_name, parameters, self.user_id_for_testing)
                # Help text is now directly obtained from CommandInterface and sent to GUI
                # CommandInterface.display_help() was console-based.
                help_text_lines = [
                    "--- AI Command Help ---",
                    "Available command patterns:",
                    "  execute code <your python code>   - Executes Python code.",
                    "  run code <your python code>       - Alias for execute code.",
                    "  ask gemini <prompt>               - Sends prompt to Gemini LLM.",
                    "  ask mock llm <prompt>             - Sends prompt to Mock LLM.",
                    "  propose update: <description>     - AI attempts to generate & test code for an update.",
                    "  search <query>                    - Searches mock web.",
                    "  help                              - Shows this help message.",
                    "  voice / listen                    - Enable voice input for next command.",
                    "  quit / exit                       - Exits the AI.",
                    "\nIf input doesn't match, it's sent to Gemini LLM by default."
                ]
                ai_chat_response = "\n".join(help_text_lines)
                if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI", ai_chat_response)()
                self.feedback_mgr.report_success(command_id, "Help displayed.", duration_ms=int((time.monotonic() - start_time) * 1000))
                return

            command_id = self.history_logger.log_command_received(command_name, parameters, self.user_id_for_testing)
            if eel.update_activity_log_js: eel.update_activity_log_js(f"Received command: {command_name}. Authenticating...")()

            if not self.auth_mgr.is_authenticated(api_key):
                err_msg = "Authentication failed. Invalid API key."
                logger.error(f"Command ID {command_id}: {err_msg}")
                if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Error", err_msg)()
                if eel.update_activity_log_js: eel.update_activity_log_js(f"Authentication failed for command {command_name}.")()
                self.history_logger.update_command_status(command_id, "failure", error_message=err_msg, duration_ms=int((time.monotonic() - start_time) * 1000))
                return

            self.history_logger.update_command_status(command_id, "processing_authenticated")
            if eel.update_activity_log_js: eel.update_activity_log_js("Authenticated. Processing command...")()

            if command_name == "execute_code":
                code_to_execute = parameters.get("code_snippet", "")
                if not code_to_execute: raise ValueError("Missing 'code_snippet'.")
                if eel.update_activity_log_js: eel.update_activity_log_js("Executing code snippet...")()
                exec_result = self.code_executor.execute_python_snippet(code_to_execute)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                if exec_result.success:
                    res_summary = f"Stdout: {exec_result.stdout[:100]}..."
                    ai_chat_response = f"Code executed.\nOutput:\n{exec_result.stdout.strip()[:500]}"
                    if exec_result.stderr.strip(): ai_chat_response += f"\nWarnings/Errors:\n{exec_result.stderr.strip()[:300]}"
                    self.feedback_mgr.report_success(command_id, "Code snippet executed.", result_summary=res_summary, duration_ms=duration_ms, data={"stdout": exec_result.stdout, "stderr": exec_result.stderr, "return_code": exec_result.return_code})
                else:
                    error_detail = exec_result.error or f"Script error: {exec_result.stderr.strip()}"
                    ai_chat_response = f"Code execution failed.\n{error_detail}"
                    self.feedback_mgr.report_failure(command_id, "Code snippet execution failed.", error_message=error_detail, duration_ms=duration_ms, data={"stdout": exec_result.stdout, "stderr": exec_result.stderr, "return_code": exec_result.return_code})

            elif command_name in ["gemini_generate_text", "mock_llm_generate_text"]:
                prompt = parameters.get("prompt", "")
                if not prompt: raise ValueError(f"Missing 'prompt'.")
                service = self.gemini_llm_service if command_name == "gemini_generate_text" else self.mock_llm_service
                s_name = "Gemini LLM" if command_name == "gemini_generate_text" else "Mock LLM"
                if eel.update_activity_log_js: eel.update_activity_log_js(f"Querying {s_name} with prompt: {prompt[:30]}...")()
                try:
                    res = await service.execute("generate_text", {"prompt": prompt})
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    if res.get("success"):
                        text = res.get("data", {}).get("generated_text", "No text.")
                        ai_chat_response = f"({s_name}): {text}"
                        self.feedback_mgr.report_success(command_id, f"{s_name} generated text.", result_summary=text[:100]+"...", duration_ms=duration_ms, data=res.get("data"))
                    else:
                        err = res.get("error", f"Unknown {s_name} error")
                        details = res.get("details", "")
                        full_err = f"{err}{(': ' + str(details)) if details else ''}"
                        ai_chat_response = f"Error with {s_name}: {full_err}"
                        self.feedback_mgr.report_failure(command_id, f"{s_name} failed.", error_message=full_err, duration_ms=duration_ms, data=res)
                except (ConnectionError, AuthenticationError) as e_conn_auth:
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    ai_chat_response = f"Error with {s_name}: {e_conn_auth}"
                    self.feedback_mgr.report_failure(command_id, f"{s_name} error.", error_message=str(e_conn_auth), duration_ms=duration_ms)

            elif command_name == "search_web_mock":
                query = parameters.get("query", "")
                if not query: raise ValueError("Missing 'query'.")
                if eel.update_activity_log_js: eel.update_activity_log_js(f"Searching mock web for: {query[:30]}...")()
                res = await self.search_service.execute("search_web", {"query": query})
                duration_ms = int((time.monotonic() - start_time) * 1000)
                if res.get("success"):
                    results = res.get("data",{}).get("results",[])
                    if results:
                        parts = [f"Found {len(results)} mock results:"]
                        for i, r_item in enumerate(results[:3]): parts.append(f"  {i+1}. {r_item.get('title')} - {r_item.get('snippet')[:50]}...")
                        if len(results) > 3: parts.append(f"  ...and {len(results)-3} more.")
                        ai_chat_response = "\n".join(parts)
                    else: ai_chat_response = "No mock results found."
                    self.feedback_mgr.report_success(command_id, "Mock search.", result_summary=f"Found {len(results)} results.", duration_ms=duration_ms, data=res.get("data"))
                else:
                    err = res.get("error", "Unknown search error")
                    ai_chat_response = f"Mock search failed: {err}"
                    self.feedback_mgr.report_failure(command_id, "Mock search failed.", error_message=err, duration_ms=duration_ms, data=res)

            elif command_name == "propose_self_update":
                task_desc = parameters.get("task_description", "")
                if not task_desc: raise ValueError("Missing 'task_description'.")
                if eel.update_activity_log_js: eel.update_activity_log_js(f"Self-update proposal: {task_desc[:40]}...")()

                relative_target_path = os.path.join("utils", "generated_utils.py")
                relative_test_target_path = os.path.join("tests", "staged_tests", f"test_{os.path.basename(relative_target_path)}")
                main_code_marker = "===BEGIN_MAIN_CODE==="; end_main_code_marker = "===END_MAIN_CODE==="
                test_code_marker = "===BEGIN_TEST_CODE==="; end_test_code_marker = "===END_TEST_CODE==="
                llm_prompt = (
                    f"You are an AI assistant writing Python code and pytest tests.\n"
                    f"Main code for '{relative_target_path}' task: {task_desc}.\n"
                    f"Generate main code between '{main_code_marker}' and '{end_main_code_marker}'.\n"
                    f"Generate pytest tests for it, assuming import from 'utils.generated_utils'. Place tests between '{test_code_marker}' and '{end_test_code_marker}'.\n"
                    f"Provide only raw Python code for both sections, no extra explanations or markdown."
                ) # Simplified prompt for brevity, original was more detailed.

                if eel.update_activity_log_js: eel.update_activity_log_js("Requesting code and tests from LLM...")()
                llm_response = await self.gemini_llm_service.execute("generate_text", {"prompt": llm_prompt})
                current_duration_ms = int((time.monotonic() - start_time) * 1000)

                if not llm_response.get("success"):
                    err = llm_response.get("error", "LLM task failed")
                    ai_chat_response = f"LLM code generation failed: {err}"
                    if eel.update_activity_log_js: eel.update_activity_log_js(ai_chat_response)()
                    self.feedback_mgr.report_failure(command_id, "Self-update code gen failed (LLM error).", error_message=err, duration_ms=current_duration_ms)
                else:
                    generated_bundle = llm_response.get("data", {}).get("generated_text", "")
                    if not generated_bundle:
                        ai_chat_response = "LLM generated empty response."
                        if eel.update_activity_log_js: eel.update_activity_log_js(ai_chat_response)()
                        self.feedback_mgr.report_failure(command_id, "Self-update code gen failed.", error_message=ai_chat_response, duration_ms=current_duration_ms)
                    else:
                        def extract_code(text, s, e):
                            try: return text[text.index(s)+len(s):text.index(e)].strip()
                            except ValueError: return None
                        main_code = extract_code(generated_bundle, main_code_marker, end_main_code_marker)
                        test_code = extract_code(generated_bundle, test_code_marker, end_test_code_marker)

                        if not main_code or not test_code:
                            err_extract = "Could not extract main/test code from LLM. Markers missing/format error."
                            ai_chat_response = err_extract
                            if eel.update_activity_log_js: eel.update_activity_log_js(err_extract + " Check LLM raw output in logs.")()
                            logger.error(f"CmdID {command_id}: {err_extract}. LLM Raw:\n{generated_bundle}")
                            self.feedback_mgr.report_failure(command_id, "Self-update code extraction failed.", error_message=err_extract, duration_ms=current_duration_ms)
                        else:
                            if eel.update_activity_log_js:
                                eel.update_activity_log_js("Code extracted. Validating syntax...")()
                                if eel.add_message_to_chat_js: # Show code in chat for review
                                     eel.add_message_to_chat_js("AI_Code", f"Generated Main Code:\n```python\n{main_code}\n```")()
                                     eel.add_message_to_chat_js("AI_Code", f"Generated Test Code:\n```python\n{test_code}\n```")()
                            try:
                                ast.parse(main_code); ast.parse(test_code)
                                if eel.update_activity_log_js: eel.update_activity_log_js("Syntax OK for main & test code. Staging...")()
                                try:
                                    with tempfile.NamedTemporaryFile(mode='w',delete=False,suffix='.py') as f_main: f_main.write(main_code); p_main=f_main.name
                                    staged_main = self.ai_updater.stage_code_from_source(p_main, relative_target_path)
                                    os.remove(p_main)
                                    with tempfile.NamedTemporaryFile(mode='w',delete=False,suffix='.py') as f_test: f_test.write(test_code); p_test=f_test.name
                                    staged_test = self.ai_updater.stage_code_from_source(p_test, relative_test_target_path)
                                    os.remove(p_test)
                                    if eel.update_activity_log_js: eel.update_activity_log_js(f"Files staged: {staged_main}, {staged_test}. Running tests...")()
                                    self.history_logger.update_command_status(command_id, "processing_staged_for_test", result_summary="Code & tests staged.")

                                    tests_passed, test_out = await self._execute_staged_tests(staged_test, self.ai_updater.staging_dir)
                                    if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Test_Output", f"Test Results:\n{test_out}")()

                                    if tests_passed:
                                        if eel.update_activity_log_js: eel.update_activity_log_js("Automated tests passed.")()
                                        self.history_logger.update_command_status(command_id, "processing_tests_passed", result_summary="Tests passed.")

                                        # TODO: Replace input() with a GUI modal for confirmation via Eel.
                                        # This requires JS to call back a Python function with the confirmation.
                                        if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Confirm", "Tests passed. Apply update? (Type 'yes' or 'no' in CONSOLE for now)")()
                                        if self.feedback_mgr.request_confirmation(f"Tests passed for staged code. Apply to live system?"): # Still uses console input
                                            if eel.update_activity_log_js: eel.update_activity_log_js("User confirmed. Applying update...")()
                                            try:
                                                bk_info = self.ai_updater.backup_module_or_file(relative_target_path)
                                                if eel.update_activity_log_js: eel.update_activity_log_js(f"Backup: {bk_info if bk_info else 'No existing file'}")()
                                                applied_p = self.ai_updater.apply_staged_update(relative_target_path)
                                                ai_chat_response = f"Update applied to {applied_p} after tests passed & confirmation."
                                                if eel.update_activity_log_js: eel.update_activity_log_js(ai_chat_response)()
                                                self.feedback_mgr.report_success(command_id, "Self-update applied.", result_summary=ai_chat_response, duration_ms=current_duration_ms)
                                            except Exception as e_apply:
                                                ai_chat_response = f"Failed to apply update: {e_apply}"
                                                if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Error", ai_chat_response)()
                                                self.feedback_mgr.report_failure(command_id, "Self-update apply failed.", error_message=str(e_apply), duration_ms=current_duration_ms)
                                        else: # User cancelled
                                            ai_chat_response = "Update application cancelled by user."
                                            if eel.update_activity_log_js: eel.update_activity_log_js(ai_chat_response)()
                                            self.feedback_mgr.report_failure(command_id, "Self-update cancelled.", result_summary=ai_chat_response, error_message="User cancellation", duration_ms=current_duration_ms)
                                    else: # Tests failed
                                        ai_chat_response = f"Automated tests failed. Update not applied. Review test output."
                                        if eel.update_activity_log_js: eel.update_activity_log_js(ai_chat_response + f"\n{test_out}")()
                                        self.feedback_mgr.report_failure(command_id, "Self-update tests failed.", result_summary="Tests failed.", error_message=test_out, duration_ms=current_duration_ms)
                                except Exception as e_stage: # Staging or test execution error
                                    ai_chat_response = f"Error during staging/testing: {e_stage}"
                                    if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Error", ai_chat_response)()
                                    self.feedback_mgr.report_failure(command_id, "Self-update staging/test error.", error_message=str(e_stage), duration_ms=current_duration_ms)
                            except SyntaxError as e_syntax: # Syntax error in main or test code
                                ai_chat_response = f"Syntax error in generated code: {e_syntax}"
                                if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Error", ai_chat_response)()
                                self.feedback_mgr.report_failure(command_id, "Self-update code validation failed.", error_message=str(e_syntax), duration_ms=current_duration_ms)
            else:
                err_unhandled_cmd = f"I don't know how to handle the command '{command_name}'."
                ai_chat_response = err_unhandled_cmd
                self.history_logger.update_command_status(command_id, "failure", error_message=err_unhandled_cmd, duration_ms=int((time.monotonic() - start_time) * 1000))

            if ai_chat_response and eel.add_message_to_chat_js:
                eel.add_message_to_chat_js("AI", ai_chat_response)()

        except Exception as e:
            err_msg_for_user = f"An internal error occurred: {str(e)}"
            if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Error", err_msg_for_user)()
            logger.error(f"Command ID {command_id if command_id else 'N/A'}: Unhandled exception: {e}", exc_info=True)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            if command_id:
                self.history_logger.update_command_status(command_id, "failure", error_message=str(e), duration_ms=duration_ms)

        finally:
            pass # Main loop handles UI updates now


# Commenting out the old console-based chat_loop as it's replaced by Eel GUI
# async def chat_loop(orchestrator: MainOrchestrator):
#     """
#     Main loop for the chat interface.
#     """
#     print("\n--- AI Chat Interface Active ---")
#     print("Type 'help' for commands, 'voice' to enable voice input for next command, or 'quit' to exit.")

#     use_voice_next = False
#     # ... (rest of the old chat_loop logic) ...
#     pass

# Global orchestrator instance for Eel to access
orchestrator_instance: MainOrchestrator | None = None

@eel.expose
async def handle_user_message_py(message_text: str):
    global orchestrator_instance
    if not orchestrator_instance:
        logger.error("Orchestrator not initialized.")
        if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI_Error", "Orchestrator not ready.")()
        return

    logger.info(f"GUI message received: {message_text}")
    if eel.add_message_to_chat_js: eel.add_message_to_chat_js("User", message_text)()

    command_struct = orchestrator_instance.command_interface.parse_user_input(message_text)

    if command_struct:
        processed_status = await orchestrator_instance.process_command(command_struct)
        if isinstance(processed_status, dict) and processed_status.get("status") == "quit":
            logger.info("Quit processed by orchestrator. Eel window should be closable by user.")
            # Consider eel.close_window() or similar if direct control is needed.
    else:
        logger.warning(f"No command structure parsed from: {message_text}")
        if eel.add_message_to_chat_js: eel.add_message_to_chat_js("AI", "I didn't understand that command.")()


if __name__ == "__main__":
    if not os.environ.get("AI_ADMIN_HASHED_KEY"):
        logger.warning("CRITICAL: AI_ADMIN_HASHED_KEY environment variable is not set for AuthManager.")

    orchestrator_instance = MainOrchestrator()
    web_gui_path = os.path.join(ORCHESTRATOR_DIR, 'web_gui')
    eel.init(web_gui_path)
    logger.info(f"Eel initialized, serving files from: {web_gui_path}")

    # `handle_user_message_py` is already exposed via decorator.
    # No need to expose `command_interface.speak` as TTS is handled by JS.

    logger.info("Starting Eel GUI. Close the GUI window or press Ctrl+C in console to quit.")
    try:
        eel.start('main.html', size=(1200, 900), mode='chrome-app', block=True)
    except (OSError, IOError) as e:
        logger.error(f"Could not start Eel browser window: {e}")
        logger.info("Ensure Chrome/Edge is installed or try mode=None for default browser.")
    except Exception as e:
        logger.error(f"An unexpected error occurred starting Eel: {e}", exc_info=True)
    finally:
        logger.info("AI system shutting down.")
        if orchestrator_instance:
            print("\n--- Recent Command Logs (from DB) ---")
            recent_logs = orchestrator_instance.history_logger.get_all_logs(limit=10)
            if recent_logs:
                for log_entry in recent_logs:
                    result_summary = log_entry.get('result_summary')
                    result_display = (result_summary[:50] + '...') if result_summary and len(result_summary) > 50 else result_summary if result_summary else "N/A"
                    print(f"ID: {log_entry['command_id']}, Name: {log_entry['command_name']}, Status: {log_entry['status']}, Result: {result_display}")
            else:
                print("No logs found in the database.")

[end of self_modifying_ai/main_orchestrator.py]
