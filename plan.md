# AI System Architecture Overview

This document provides a conceptual overview of the major components within the self-modifying AI system and how they interact.

## 1. Core Components

The system is designed modularly. Key conceptual components include:

1.  **Command Interface (Conceptual - Not yet fully built):**
    *   **Responsibilities:** Receives instructions from the user (you). This is envisioned as primarily a Natural Language Processing (NLP) interface, capable of understanding complex requests. It would also support specific structured commands as fallbacks or for precise operations.
    *   **Interactions:**
        *   Receives input from the User.
        *   Passes commands to the Main AI Loop/Orchestrator.
        *   Likely uses an NLP Service (e.g., Gemini, Azure AI via a `ServiceConnector`) for parsing.

2.  **Main AI Loop / Orchestrator (Conceptual - Not yet fully built):**
    *   **Responsibilities:** The central "brain" that coordinates the AI's actions. It takes parsed commands, makes decisions, and delegates tasks to other components. It manages the overall state of operations and ensures adherence to policies.
    *   **Interactions:**
        *   Receives parsed commands from the Command Interface.
        *   Uses `AuthManager` to verify user authentication for sensitive commands.
        *   Invokes `AIUpdater` for self-modification tasks.
        *   Invokes `CodeExecutor` to run arbitrary code snippets.
        *   Utilizes various `ServiceConnector`s (LLM, Search, etc.) for external data/capabilities.
        *   Uses `FeedbackManager` to report progress, results, and errors to the user.
        *   Ensures all actions are logged via `CommandHistoryLogger`.
        *   Implements confirmation flows for critical actions as defined in `POWER_CONTROL_POLICY.md`.

3.  **Authentication Manager (`AuthManager` - `conceptual_auth_manager.py`):**
    *   **Responsibilities:** Manages user authentication. Currently supports API key-based authentication for the single primary user.
    *   **Interactions:**
        *   Called by the Main AI Loop to authenticate incoming commands.
        *   Reads a hashed admin API key (typically from an environment variable).

4.  **AI Updater (`AIUpdater` - `conceptual_updater.py`):**
    *   **Responsibilities:** Handles the AI's self-modification capabilities. This includes staging new code, running (simulated) tests, backing up existing modules, applying updates, and reloading modules.
    *   **Interactions:**
        *   Invoked by the Main AI Loop for update tasks.
        *   Interacts with the filesystem to manage code files (staging, backup, replacement).
        *   Uses `importlib` for dynamic module reloading.
        *   (Future) Will need to integrate with `FeedbackManager` for user confirmation on critical updates.

5.  **Code Executor (`CodeExecutor` - `conceptual_code_executor.py`):**
    *   **Responsibilities:** Executes arbitrary Python code snippets in a somewhat isolated environment. Manages input to the snippet, captures its output (stdout, stderr), handles timeouts, and reports execution results.
    *   **Interactions:**
        *   Invoked by the Main AI Loop when a task requires dynamic code execution.
        *   Uses `subprocess` and `python -I` for basic isolation.

6.  **Command History Logger (`CommandHistoryLogger` - `conceptual_command_history.py`):**
    *   **Responsibilities:** Logs all received commands, their processing status (received, processing, success, failure), and relevant metadata (timestamp, user, error messages, result summaries).
    *   **Interactions:**
        *   Used by the Main AI Loop and other components (like `FeedbackManager`) to record the lifecycle of commands.
        *   Stores data in an SQLite database (`command_history.db`).

7.  **Feedback Manager (`FeedbackManager` - `conceptual_feedback_manager.py`):**
    *   **Responsibilities:** Formats and delivers feedback messages to the user regarding the AI's operations, status, successes, and failures.
    *   **Interactions:**
        *   Used by the Main AI Loop and other components (`AIUpdater`, `CodeExecutor`, etc.) to report back to the user.
        *   Outputs structured feedback (simulated via a dedicated "UserFeedback" logger).
        *   Integrates with `CommandHistoryLogger` to ensure significant feedback points (like operation success/failure) are also recorded in the command's history.

8.  **Service Connectors (`BaseServiceConnector`, `conceptual_llm_service.py`, `conceptual_search_service.py`, etc.):**
    *   **Responsibilities:** Provide a standardized way to interact with external services and APIs (e.g., LLMs like Gemini, Search APIs, Azure AI services). They handle authentication with the external service, request formatting, and response parsing.
    *   **Interactions:**
        *   `BaseServiceConnector` (`conceptual_service_connector.py`): Defines the abstract interface.
        *   Specific implementations (e.g., `MockLanguageModelService`, `MockSearchService`) are invoked by the Main AI Loop or other components needing external capabilities.
        *   They would use `ServiceCredentials` to manage API keys for the respective services.

## 2. Data Storage (Conceptual)

*   **`command_history.db`:** An SQLite database used by `CommandHistoryLogger` to store the history of all commands.
*   **Configuration Data:**
    *   AI Admin API Key Hash: Stored via environment variable (`AI_ADMIN_HASHED_KEY`).
    *   External Service API Keys: Conceptually stored via environment variables or a secure secrets manager.
*   **AI's Codebase:** The Python files (`.py`) that constitute the AI itself. `AIUpdater` manages these.
*   **Temporary Files:**
    *   `AIUpdater` uses `staging/` and `backup/` directories.
    *   `CodeExecutor` uses temporary files for scripts.

## 3. High-Level Interaction Flow (Example: User Command for Self-Update)

1.  **User** issues a command (e.g., "Update module X from git_source_Y").
2.  **Command Interface** receives the command, potentially uses an NLP Service (via a **ServiceConnector**) to parse it into a structured request.
3.  **Main AI Loop** receives the structured request.
4.  **Main AI Loop** calls `AuthManager` to authenticate the user via the provided API key.
5.  If authenticated, **Main AI Loop** identifies it as a self-update task.
6.  **(If critical update per `POWER_CONTROL_POLICY.md`) Main AI Loop** uses `FeedbackManager` to request explicit confirmation from the user. User provides confirmation.
7.  **Main AI Loop** logs the command initiation (or "awaiting_confirmation" then "processing") with `CommandHistoryLogger`.
8.  **Main AI Loop** invokes `AIUpdater.apply_update(...)` with the details.
9.  **AIUpdater** performs its steps (staging, testing, backup, replace, reload), potentially using `FeedbackManager` for step-by-step progress.
10. **AIUpdater** returns success/failure to the **Main AI Loop**.
11. **Main AI Loop** uses `FeedbackManager` to report the final outcome to the user.
12. **Main AI Loop** ensures `CommandHistoryLogger` is updated with the final status, duration, and any errors/results via `FeedbackManager`'s integration or directly.

## 4. Diagram (Text-Based Conceptual)

```
+---------------------+      +---------------------+      +-----------------------+
|        User         |<---->|  Command Interface  |<---->|  Main AI Loop /       |
+---------------------+      |    (NLP, Parser)    |      |     Orchestrator      |
                             +---------------------+      +-----------+-----------+
                                                                      |
         +------------------------------------------------------------+-------------------------------------------------------------+
         |                             |                              |                           |                               |
         v                             v                              v                           v                               v
+-----------------+        +-----------------------+      +---------------------+      +-----------------+      +-------------------------+
|  AuthManager    |        |  AIUpdater            |      |   CodeExecutor      |      | FeedbackManager |      | Service Connectors      |
| (API Key Auth)  |        |  (Self-Modification)  |      | (Arbitrary Code)    |      | (User Output)   |      | (LLM, Search, Azure...) |
+-----------------+        +-----------------------+      +---------------------+      +-----------------+      +-------------------------+
                                       |                              |                           |
                                       |                              |                           |
                                       +------------------------------+---------------------------+
                                                                      |
                                                                      v
                                                        +--------------------------+
                                                        |  CommandHistoryLogger    |
                                                        |  (SQLite DB)             |
                                                        +--------------------------+
```

This architecture is designed to be modular and extensible, allowing new capabilities and services to be integrated over time while maintaining a degree of control and observability.
```
