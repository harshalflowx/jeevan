import datetime
from .command_history_logger import CommandHistoryLogger

# Placeholder for a more sophisticated UserFeedback logger/interface
# For now, we'll just print to console.
def user_feedback_logger(level: str, message: str, data: dict = None):
    timestamp = datetime.datetime.utcnow().isoformat()
    log_message = f"[{timestamp}] [{level.upper()}] {message}"
    if data:
        log_message += f" | Data: {data}"
    print(log_message)


class FeedbackManager:
    def __init__(self, command_history_logger: CommandHistoryLogger):
        self.command_history_logger = command_history_logger

    def report_status(self, command_id: str, message: str, status_level: str = "INFO", data: dict = None):
        """
        Reports a general status update to the user and logs it.
        'status_level' can be INFO, WARNING, ERROR, etc. for user feedback.
        The status in CommandHistoryLogger will be updated to 'processing' or a more specific one
        if this feedback indicates a milestone.
        """
        user_feedback_logger(status_level, message, data)
        # This is a general status update; major status changes (success/failure) are handled by specific methods.
        # If the command is still broadly "processing", we can update its timestamp or add to a running log.
        # For now, we assume major status updates come through report_success/report_failure.

    def report_progress(self, command_id: str, message: str, percentage: float = None, data: dict = None):
        """
        Reports progress of an ongoing command.
        """
        progress_message = message
        if percentage is not None:
            progress_message = f"{message} ({percentage:.2f}%)"
        user_feedback_logger("INFO", progress_message, data)
        # This might not always update the main status in command_history_logger,
        # but could be stored in a more detailed log if available.

    def report_success(self, command_id: str, message: str, result_summary: str = None, duration_ms: int = None, data: dict = None):
        """
        Reports successful completion of a command.
        Updates CommandHistoryLogger with "success".
        """
        user_feedback_logger("SUCCESS", message, data)
        self.command_history_logger.update_command_status(
            command_id,
            status="success",
            result_summary=result_summary or message,
            duration_ms=duration_ms
        )

    def report_failure(self, command_id: str, message: str, error_message: str = None, duration_ms: int = None, data: dict = None):
        """
        Reports failure of a command.
        Updates CommandHistoryLogger with "failure".
        """
        user_feedback_logger("ERROR", message, data)
        self.command_history_logger.update_command_status(
            command_id,
            status="failure",
            error_message=error_message or message,
            duration_ms=duration_ms
        )

    def request_confirmation(self, message: str, data: dict = None) -> bool:
        """
        Requests confirmation from the user.
        This is a placeholder. In a real system, this would interact with the Command Interface.
        """
        user_feedback_logger("CONFIRMATION_REQUEST", message, data)
        while True:
            response = input(f"{message} (yes/no): ").strip().lower()
            if response == "yes":
                user_feedback_logger("INFO", "User confirmed.")
                return True
            elif response == "no":
                user_feedback_logger("INFO", "User denied.")
                return False
            else:
                print("Invalid input. Please enter 'yes' or 'no'.")


if __name__ == '__main__':
    # Example Usage
    # Setup a dummy CommandHistoryLogger for the example
    # In a real app, this would be properly initialized and passed.
    class MockCommandHistoryLogger:
        def __init__(self):
            self.db = {}
            print("MockCommandHistoryLogger initialized.")

        def log_command_received(self, command_name: str, parameters: dict = None, user_id: str = None) -> str:
            command_id = f"cmd_{len(self.db) + 1}"
            self.db[command_id] = {
                "command_id": command_id, "received_at": datetime.datetime.utcnow().isoformat(),
                "command_name": command_name, "parameters": parameters, "status": "received",
                "status_updated_at": datetime.datetime.utcnow().isoformat(), "user_id": user_id,
                "error_message": None, "result_summary": None, "duration_ms": None
            }
            print(f"MockLogged command received: {command_id}, Name: {command_name}")
            return command_id

        def update_command_status(self, command_id: str, status: str, error_message: str = None, result_summary: str = None, duration_ms: int = None):
            if command_id in self.db:
                self.db[command_id]["status"] = status
                self.db[command_id]["status_updated_at"] = datetime.datetime.utcnow().isoformat()
                if error_message: self.db[command_id]["error_message"] = error_message
                if result_summary: self.db[command_id]["result_summary"] = result_summary
                if duration_ms: self.db[command_id]["duration_ms"] = duration_ms
                print(f"MockUpdated command status: {command_id} to {status}")
            else:
                print(f"MockError: Command ID {command_id} not found for update.")

        def get_command_log(self, command_id: str):
            return self.db.get(command_id)

    mock_logger = MockCommandHistoryLogger()
    feedback_mgr = FeedbackManager(mock_logger)

    print("\n--- Simulating Command Flow ---")

    # Simulate receiving a command
    cmd_name = "example_task"
    cmd_params = {"input": "test_data"}
    user = "test_user"

    # This part would typically be done by the orchestrator before calling feedback manager for updates
    print(f"\nOrchestrator: Logging reception of command '{cmd_name}'...")
    cmd_id = mock_logger.log_command_received(command_name=cmd_name, parameters=cmd_params, user_id=user)
    print(f"Orchestrator: Command '{cmd_name}' logged with ID: {cmd_id}")

    # Start processing
    feedback_mgr.report_status(cmd_id, f"Starting task: {cmd_name}", status_level="INFO")
    mock_logger.update_command_status(cmd_id, "processing") # Orchestrator might do this

    feedback_mgr.report_progress(cmd_id, "Step 1 of 2 complete", percentage=50.0)

    # Simulate asking for confirmation (if needed by a component)
    # confirmation_needed = True
    # if confirmation_needed:
    #     if feedback_mgr.request_confirmation("Proceed with critical step?"):
    #         feedback_mgr.report_status(cmd_id, "Critical step confirmed by user.", status_level="INFO")
    #     else:
    #         feedback_mgr.report_failure(cmd_id, "Critical step denied by user.", error_message="User cancellation")
    #         print("\n--- End of Simulation (User Denied) ---")
    #         print("Final log state:", mock_logger.get_command_log(cmd_id))
    #         exit()


    feedback_mgr.report_progress(cmd_id, "Step 2 of 2 complete", percentage=100.0)

    # Simulate success
    simulated_duration = 1234 # ms
    feedback_mgr.report_success(cmd_id, f"Task '{cmd_name}' completed successfully.",
                                result_summary="All steps finished without error.",
                                duration_ms=simulated_duration)

    print("\nFinal log state for successful command:", mock_logger.get_command_log(cmd_id))

    # Simulate another command that fails
    fail_cmd_name = "failing_task"
    print(f"\nOrchestrator: Logging reception of command '{fail_cmd_name}'...")
    fail_cmd_id = mock_logger.log_command_received(command_name=fail_cmd_name, user_id=user)
    print(f"Orchestrator: Command '{fail_cmd_name}' logged with ID: {fail_cmd_id}")

    feedback_mgr.report_status(fail_cmd_id, f"Starting task: {fail_cmd_name}", status_level="INFO")
    mock_logger.update_command_status(fail_cmd_id, "processing")

    simulated_fail_duration = 567 # ms
    feedback_mgr.report_failure(fail_cmd_id, f"Task '{fail_cmd_name}' failed.",
                                error_message="Simulated error during execution.",
                                duration_ms=simulated_fail_duration,
                                data={"error_code": "E123"})

    print("\nFinal log state for failed command:", mock_logger.get_command_log(fail_cmd_id))
    print("\n--- End of Simulation ---")
