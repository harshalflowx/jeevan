import subprocess
import tempfile
import os
import time
import sys

class CodeExecutionResult:
    def __init__(self, success: bool, stdout: str, stderr: str, return_code: int, duration: float, error: str = None):
        self.success = success  # True if execution completed without internal errors and return_code is 0
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.duration = duration  # Execution time in seconds
        self.error = error  # For errors in the executor itself (e.g., timeout, setup issues)

    def __repr__(self):
        return (f"CodeExecutionResult(success={self.success}, return_code={self.return_code}, "
                f"duration={self.duration:.4f}s, stdout='{self.stdout[:50]}...', "
                f"stderr='{self.stderr[:50]}...', error='{self.error}')")

class CodeExecutor:
    def __init__(self, default_timeout_seconds: float = 10.0):
        self.default_timeout_seconds = default_timeout_seconds

    def execute_python_snippet(self, code_snippet: str, input_data: str = None, timeout_seconds: float = None) -> CodeExecutionResult:
        """
        Executes an arbitrary Python code snippet in an isolated process.

        Args:
            code_snippet (str): The Python code to execute.
            input_data (str, optional): Data to be passed to the script's stdin.
            timeout_seconds (float, optional): Specific timeout for this execution.
                                               Defaults to self.default_timeout_seconds.

        Returns:
            CodeExecutionResult: An object containing stdout, stderr, return code, and success status.
        """
        current_timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        start_time = time.monotonic()

        # Create a temporary file to store the code snippet
        # Suffix is important for Windows, prefix for readability
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', prefix='code_exec_') as tmp_script:
            tmp_script_path = tmp_script.name
            tmp_script.write(code_snippet)

        python_executable = sys.executable # Use the same Python interpreter that's running this script

        try:
            process = subprocess.Popen(
                [python_executable, "-I", tmp_script_path], # -I for isolated mode
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Work with text streams (universal_newlines=True in older Python)
                encoding='utf-8'
            )

            stdout, stderr = process.communicate(input=input_data, timeout=current_timeout)
            return_code = process.returncode
            duration = time.monotonic() - start_time

            # Consider execution successful if the executor didn't error out AND the script's return code is 0
            execution_successful = (return_code == 0)
            return CodeExecutionResult(success=execution_successful, stdout=stdout, stderr=stderr, return_code=return_code, duration=duration)

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start_time
            process.kill() # Ensure the process is killed
            stdout, stderr = process.communicate() # Retrieve any output captured before kill
            return CodeExecutionResult(success=False, stdout=stdout, stderr=stderr, return_code=-1, # Using -1 for timeout
                                       duration=duration, error="Execution timed out.")
        except FileNotFoundError: # Should not happen if sys.executable is valid
            duration = time.monotonic() - start_time
            return CodeExecutionResult(success=False, stdout="", stderr="", return_code=-1,
                                       duration=duration, error=f"Python interpreter not found at {python_executable}.")
        except Exception as e:
            duration = time.monotonic() - start_time
            return CodeExecutionResult(success=False, stdout="", stderr=str(e), return_code=-1,
                                       duration=duration, error=f"An unexpected error occurred: {str(e)}")
        finally:
            # Clean up the temporary file
            if os.path.exists(tmp_script_path):
                os.remove(tmp_script_path)

if __name__ == '__main__':
    executor = CodeExecutor(default_timeout_seconds=5.0)

    print("--- CodeExecutor Example ---")

    # 1. Simple successful execution
    print("\n1. Simple success case:")
    code1 = "print('Hello from snippet!')\nimport sys\nsys.exit(0)"
    result1 = executor.execute_python_snippet(code1)
    print(result1)
    assert result1.success
    assert result1.return_code == 0
    assert "Hello from snippet!" in result1.stdout

    # 2. Execution with an error in the snippet
    print("\n2. Snippet with runtime error (non-zero exit code):")
    code2 = "print('About to divide by zero...')\nx = 1/0"
    result2 = executor.execute_python_snippet(code2)
    print(result2)
    assert not result2.success # success is False because return_code is not 0
    assert result2.return_code != 0
    assert "ZeroDivisionError" in result2.stderr

    # 3. Execution with stdin
    print("\n3. Snippet with stdin:")
    code3 = "name = input('Enter your name: ')\nprint(f'Hello, {name}!')"
    result3 = executor.execute_python_snippet(code3, input_data="Jules")
    print(result3)
    assert result3.success
    assert "Hello, Jules!" in result3.stdout

    # 4. Timeout execution
    print("\n4. Snippet that times out:")
    code4 = "import time\nprint('Starting long task...')\ntime.sleep(3)\nprint('Should not see this')"
    result4 = executor.execute_python_snippet(code4, timeout_seconds=1.0) # Short timeout
    print(result4)
    assert not result4.success
    assert result4.error == "Execution timed out."
    assert "Starting long task..." in result4.stdout # Output before timeout might be captured
    assert "Should not see this" not in result4.stdout

    # 5. Snippet with non-zero exit code (but no stderr)
    print("\n5. Snippet with explicit non-zero exit code:")
    code5 = "import sys\nprint('Exiting with code 5')\nsys.exit(5)"
    result5 = executor.execute_python_snippet(code5)
    print(result5)
    assert not result5.success # success is False because return_code is not 0
    assert result5.return_code == 5
    assert "Exiting with code 5" in result5.stdout

    # 6. Empty snippet
    print("\n6. Empty snippet:")
    code6 = ""
    result6 = executor.execute_python_snippet(code6)
    print(result6)
    assert result6.success # Empty script is valid Python, exits with 0
    assert result6.return_code == 0
    assert result6.stdout == ""
    assert result6.stderr == ""

    print("\n--- End of Example ---")
