import asyncio
from .base_service_connector import BaseServiceConnector, ServiceCredentials, AuthenticationError, ServiceSpecificError

class MockLanguageModelService(BaseServiceConnector):
    """
    A mock implementation of a Language Model Service Connector.
    It simulates API calls to an LLM.
    """
    def __init__(self, service_name: str = "MockLLMService", credentials: ServiceCredentials = None, api_delay_seconds: float = 0.1):
        super().__init__(service_name, credentials)
        self.api_delay_seconds = api_delay_seconds
        # Example: Store some mock state or configuration
        self.model_capabilities = {
            "generate_text": ["gpt-mock-basic", "gpt-mock-creative"],
            "summarize": ["gpt-mock-basic"]
        }
        self.mock_api_key = "mock_llm_api_key_valid" # Expected API key for this mock

    def _validate_credentials(self):
        """
        Mock validation: Checks if an API key is provided if credentials object exists.
        """
        if self.credentials:
            if not self.credentials.get_credential("api_key"):
                print(f"Warning: {self.service_name} initialized with credentials object but no API key.")
            # In a real service, you might check if the key format is valid, etc.
        else:
            # For this mock, we'll allow operation without credentials for some basic commands
            # or assume a default behavior.
            print(f"Info: {self.service_name} initialized without credentials. Some operations might be restricted or use defaults.")


    async def execute(self, command: str, params: dict = None, **kwargs) -> dict:
        """
        Simulates executing a command against a mock LLM.

        Supported commands:
        - "generate_text": Simulates text generation.
            Params: {"prompt": "Some text", "model": "gpt-mock-basic"}
        - "summarize": Simulates text summarization.
            Params: {"text_to_summarize": "Long text...", "model": "gpt-mock-basic"}
        - "check_capability": Checks if a model supports a command.
             Params: {"command_to_check": "generate_text", "model": "gpt-mock-basic"}

        Returns:
            dict: A dictionary containing the simulated result.
                  Includes "success": True/False and "data": ... or "error": ...
        """
        await asyncio.sleep(self.api_delay_seconds) # Simulate network latency

        # Mock authentication check for specific commands if credentials are set
        if self.credentials and self.credentials.api_key != self.mock_api_key:
            if command in ["generate_text", "summarize"]: # Let's say these require auth
                raise AuthenticationError(f"{self.service_name}: Invalid API key.")

        params = params or {}

        if command == "generate_text":
            prompt = params.get("prompt")
            model = params.get("model", "gpt-mock-basic")
            if not prompt:
                return {"success": False, "error": "Prompt is required for generate_text."}
            if model not in self.model_capabilities.get("generate_text", []):
                 return {"success": False, "error": f"Model '{model}' does not support 'generate_text' or is invalid."}

            # Simulate different responses based on model or prompt
            if "creative" in model:
                generated_text = f"Creative mock response to: '{prompt}' using {model}."
            else:
                generated_text = f"Standard mock response to: '{prompt}' using {model}."
            return {"success": True, "data": {"generated_text": generated_text, "model_used": model}}

        elif command == "summarize":
            text_to_summarize = params.get("text_to_summarize")
            model = params.get("model", "gpt-mock-basic")
            if not text_to_summarize:
                return {"success": False, "error": "text_to_summarize is required for summarize."}
            if model not in self.model_capabilities.get("summarize", []):
                 return {"success": False, "error": f"Model '{model}' does not support 'summarize' or is invalid."}

            summary = f"Mock summary of '{text_to_summarize[:30]}...' using {model}."
            return {"success": True, "data": {"summary": summary, "model_used": model}}

        elif command == "check_capability":
            cmd_to_check = params.get("command_to_check")
            model_to_check = params.get("model")
            if not cmd_to_check or not model_to_check:
                return {"success": False, "error": "command_to_check and model are required."}

            supported = model_to_check in self.model_capabilities.get(cmd_to_check, [])
            return {"success": True, "data": {"command": cmd_to_check, "model": model_to_check, "is_supported": supported}}

        else:
            raise ServiceSpecificError(f"{self.service_name}: Unknown command '{command}'.")

if __name__ == '__main__':
    async def main():
        print("--- MockLanguageModelService Example ---")

        # Without credentials (some commands might work, some might be restricted if designed so)
        print("\n1. Initializing without credentials...")
        mock_llm_no_auth = MockLanguageModelService(api_delay_seconds=0.01)

        # This command doesn't require auth in our mock
        cap_result_no_auth = await mock_llm_no_auth.execute("check_capability", {"command_to_check": "generate_text", "model": "gpt-mock-basic"})
        print(f"Capability check (no auth): {cap_result_no_auth}")

        # This command would require auth if credentials were provided and were wrong.
        # Since no credentials, it might proceed with a default behavior or a specific non-authenticated path.
        # In this mock, 'generate_text' only fails if credentials *are* provided and *are wrong*.
        gen_result_no_auth = await mock_llm_no_auth.execute("generate_text", {"prompt": "Hello world (no auth)"})
        print(f"Generate text (no auth): {gen_result_no_auth}")


        # With valid credentials
        print("\n2. Initializing with VALID credentials...")
        valid_creds = ServiceCredentials(api_key="mock_llm_api_key_valid")
        mock_llm_valid_auth = MockLanguageModelService(credentials=valid_creds, api_delay_seconds=0.01)

        gen_result_valid = await mock_llm_valid_auth.execute("generate_text", {"prompt": "Hello with valid auth", "model": "gpt-mock-creative"})
        print(f"Generate text (valid auth): {gen_result_valid}")

        summarize_result_valid = await mock_llm_valid_auth.execute("summarize", {"text_to_summarize": "This is a long text about AI."})
        print(f"Summarize (valid auth): {summarize_result_valid}")

        # With invalid credentials
        print("\n3. Initializing with INVALID credentials...")
        invalid_creds = ServiceCredentials(api_key="invalid_key")
        mock_llm_invalid_auth = MockLanguageModelService(credentials=invalid_creds, api_delay_seconds=0.01)

        try:
            print("Attempting generate_text with invalid auth (expected AuthenticationError)...")
            await mock_llm_invalid_auth.execute("generate_text", {"prompt": "Hello with invalid auth"})
        except AuthenticationError as e:
            print(f"Caught expected error: {e}")
        except Exception as e:
            print(f"Caught unexpected error: {e}")

        # Test unsupported model
        print("\n4. Testing unsupported model...")
        try:
            unsupported_model_result = await mock_llm_valid_auth.execute("generate_text", {"prompt": "Test prompt", "model": "unknown-model"})
            print(f"Generate text (unsupported model): {unsupported_model_result}")
        except ServiceSpecificError as e:
             print(f"Caught expected error for unsupported model: {e}")


        # Test unknown command
        print("\n5. Testing unknown command...")
        try:
            await mock_llm_valid_auth.execute("unknown_command", {"data": "test"})
        except ServiceSpecificError as e:
            print(f"Caught expected error for unknown command: {e}")

        print("\n--- End of Example ---")

    asyncio.run(main())
