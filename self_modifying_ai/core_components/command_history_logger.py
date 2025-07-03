import sqlite3
import datetime
import uuid

DB_NAME = "command_history.db"

class CommandHistoryLogger:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self._initialize_db()

    def _initialize_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_log (
                command_id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL,
                command_name TEXT,
                parameters TEXT,
                status TEXT NOT NULL,
                status_updated_at TEXT NOT NULL,
                user_id TEXT,
                error_message TEXT,
                result_summary TEXT,
                duration_ms INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def log_command_received(self, command_name: str, parameters: dict = None, user_id: str = None) -> str:
        command_id = str(uuid.uuid4())
        now_iso = datetime.datetime.utcnow().isoformat()

        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO command_log (command_id, received_at, command_name, parameters, status, status_updated_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (command_id, now_iso, command_name, str(parameters) if parameters else None, "received", now_iso, user_id))
        conn.commit()
        conn.close()
        return command_id

    def update_command_status(self, command_id: str, status: str, error_message: str = None, result_summary: str = None, duration_ms: int = None):
        now_iso = datetime.datetime.utcnow().isoformat()

        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        updates = {
            "status": status,
            "status_updated_at": now_iso
        }
        if error_message is not None:
            updates["error_message"] = error_message
        if result_summary is not None:
            updates["result_summary"] = result_summary
        if duration_ms is not None:
            updates["duration_ms"] = duration_ms

        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [command_id]

        cursor.execute(f"""
            UPDATE command_log
            SET {set_clause}
            WHERE command_id = ?
        """, values)

        conn.commit()
        conn.close()

    def get_command_log(self, command_id: str) -> dict:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM command_log WHERE command_id = ?", (command_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_logs(self, limit: int = 100) -> list[dict]:
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM command_log ORDER BY received_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

if __name__ == '__main__':
    # Example Usage
    logger = CommandHistoryLogger(db_name="test_command_history.db") # Use a test DB for example

    print("Initializing DB...")
    logger._initialize_db() # Ensure table is created

    print("Logging a new command...")
    cmd_id = logger.log_command_received("test_command", {"param1": "value1"}, user_id="test_user")
    print(f"Command logged with ID: {cmd_id}")

    print("Fetching command log...")
    log_entry = logger.get_command_log(cmd_id)
    print(f"Log entry: {log_entry}")

    print("Updating command status to processing...")
    logger.update_command_status(cmd_id, "processing")
    log_entry = logger.get_command_log(cmd_id)
    print(f"Updated log entry: {log_entry}")

    import time
    time.sleep(0.1) # Simulate work

    print("Updating command status to success...")
    start_time = datetime.datetime.strptime(log_entry["received_at"], "%Y-%m-%dT%H:%M:%S.%f")
    end_time = datetime.datetime.utcnow()
    duration = int((end_time - start_time).total_seconds() * 1000)
    logger.update_command_status(cmd_id, "success", result_summary="Command executed successfully.", duration_ms=duration)
    log_entry = logger.get_command_log(cmd_id)
    print(f"Final log entry: {log_entry}")

    print("\nAll logs:")
    all_logs = logger.get_all_logs()
    for log in all_logs:
        print(log)

    # Clean up test database
    import os
    os.remove("test_command_history.db")
    print("\nTest DB removed.")
