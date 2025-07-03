import os
import asyncio
import logging
import aiohttp

from .base_service_connector import BaseServiceConnector, ServiceCredentials, AuthenticationError, ServiceSpecificError

logger = logging.getLogger(__name__)

# Hypothetical Gemini API endpoint for text generation
# Replace with actual endpoint if known. This is a placeholder.
GEMINI_API_ENDPOINT_V1_GENERATE_TEXT = "https_//generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent" # Intentionally broken URL for placeholder

class GeminiServiceConnector(BaseServiceConnector):
    """
    A service connector for interacting with Google's Gemini LLM API.
    """
    def __init__(self, service_name: str = "GeminiLLMService", api_key: str = None, api_endpoint: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.api_endpoint = api_endpoint or GEMINI_API_ENDPOINT_V1_GENERATE_TEXT

        # Pass a ServiceCredentials object to the parent, even if just with the API key
        creds = ServiceCredentials(api_key=self.api_key) if self.api_key else None
        super().__init__(service_name, credentials=creds)

        if not self.api_key:
            logger.warning(f"{self.service_name}: GEMINI_API_KEY is not set. Calls will likely fail authentication.")
        if self.api_endpoint == GEMINI_API_ENDPOINT_V1_GENERATE_TEXT and "https_" in self.api_endpoint: # Check if it's still the placeholder
             logger.warning(f"{self.service_name}: API endpoint is using a placeholder URL ({self.api_endpoint}). Please configure a real endpoint.")


    def _validate_credentials(self):
        """
        Validates if the API key is present.
        """
        if not self.credentials or not self.credentials.get_credential("api_key"):
            # This warning is already logged in __init__ if api_key is missing,
            # but BaseServiceConnector requires this method.
            # Actual API call failure will be the ultimate test.
            logger.info(f"{self.service_name}: API key not configured. Authentication with the actual Gemini API will fail.")
            # Not raising an error here, as the service might be conditionally used.

    async def execute(self, command: str, params: dict = None, **kwargs) -> dict:
        """
        Executes a command against the Gemini LLM API.

        Supported commands:
        - "generate_text": Generates text based on a prompt.
            Params: {"prompt": "User's prompt string"}

        Returns:
            dict: A dictionary containing the result.
                  {"success": True/False, "data": ..., "error": ...}
        """
        if not self.api_key:
            raise AuthenticationError(f"{self.service_name}: API key is missing. Cannot make API calls.")

        if self.api_endpoint == GEMINI_API_ENDPOINT_V1_GENERATE_TEXT and "https_" in self.api_endpoint:
             return {"success": False, "error": f"{self.service_name}: API endpoint is a placeholder. Configure a real endpoint."}


        params = params or {}
        headers = {
            "Content-Type": "application/json",
            # Gemini API key is typically sent in the URL as `key=YOUR_API_KEY`
            # or sometimes in headers, depending on the specific client/endpoint.
            # For REST, usually it's part of the query params for a GET or in body/header for POST.
            # Assuming it's a POST and key is in URL for this example.
        }

        url_with_key = f"{self.api_endpoint}?key={self.api_key}"

        if command == "generate_text":
            prompt_text = params.get("prompt")
            if not prompt_text:
                return {"success": False, "error": "Prompt is required for generate_text."}

            # Construct the payload for Gemini API (this is a common structure)
            # Refer to official Gemini API documentation for the correct payload structure.
            payload = {
                "contents": [{
                    "parts": [{"text": prompt_text}]
                }]
                # Add other parameters like generationConfig if needed:
                # "generationConfig": {
                #   "temperature": 0.7,
                #   "maxOutputTokens": 256,
                # }
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url_with_key, headers=headers, json=payload) as response:
                        response_status = response.status
                        response_json = await response.json()

                        if response_status == 200:
                            # Assuming the response structure contains generated text like:
                            # response_json['candidates'][0]['content']['parts'][0]['text']
                            # This needs to be adapted based on actual Gemini API response.
                            try:
                                generated_text = response_json['candidates'][0]['content']['parts'][0]['text']
                                return {"success": True, "data": {"generated_text": generated_text, "raw_response": response_json}}
                            except (KeyError, IndexError, TypeError) as e:
                                logger.error(f"{self.service_name} - Error parsing successful response: {e}. Response: {response_json}")
                                return {"success": False, "error": "Failed to parse successful response from Gemini API.", "details": str(e), "raw_response": response_json}

                        elif response_status == 401 or response_status == 403:
                            logger.error(f"{self.service_name} - Authentication error ({response_status}): {response_json}")
                            raise AuthenticationError(f"Gemini API authentication failed ({response_status}): {response_json.get('error', {}).get('message', 'Unauthorized')}")
                        else:
                            logger.error(f"{self.service_name} - API error ({response_status}): {response_json}")
                            return {"success": False, "error": f"Gemini API error ({response_status})", "details": response_json.get('error', {}).get('message', response_json)}

            except aiohttp.ClientConnectorError as e:
                logger.error(f"{self.service_name} - Connection error: {e}")
                raise ConnectionError(f"Failed to connect to Gemini API: {e}")
            except AuthenticationError: # Re-raise to be caught by orchestrator if needed
                raise
            except Exception as e:
                logger.error(f"{self.service_name} - Unexpected error during API call: {e}", exc_info=True)
                raise ServiceSpecificError(f"An unexpected error occurred with Gemini service: {e}")

        else:
            return {"success": False, "error": f"Unknown command '{command}' for {self.service_name}."}

if __name__ == '__main__':
    async def main():
        print("--- GeminiServiceConnector Example ---")
        # To test this, you MUST set the GEMINI_API_KEY environment variable
        # and potentially update GEMINI_API_ENDPOINT_V1_GENERATE_TEXT if the placeholder is not correct.

        api_key_is_set = bool(os.environ.get("GEMINI_API_KEY"))
        print(f"GEMINI_API_KEY environment variable is set: {api_key_is_set}")

        # Intentionally use a placeholder URL that will cause a connection error if not overridden
        # and if the default GEMINI_API_ENDPOINT_V1_GENERATE_TEXT is used as is.
        # To properly test, replace "https_" with "https://" in the default URL or provide a real one.
        # This example will likely fail unless the placeholder URL is fixed or a real one is provided.

        # Fix the placeholder URL for a slightly more realistic local test simulation (will still fail if key is bad or endpoint is truly fake)
        live_test_endpoint = GEMINI_API_ENDPOINT_V1_GENERATE_TEXT.replace("https_//", "https://")


        gemini_connector = GeminiServiceConnector(api_endpoint=live_test_endpoint) # Uses env var for API key

        if not api_key_is_set:
            print("GEMINI_API_KEY is not set. Skipping live API call tests.")
            print("To run tests, set GEMINI_API_KEY and ensure the endpoint is valid.")
            try:
                # This should raise AuthenticationError if API key is missing
                await gemini_connector.execute("generate_text", {"prompt": "This should fail due to missing API key."})
            except AuthenticationError as e:
                print(f"Caught expected AuthenticationError: {e}")
            return

        print(f"\nAttempting to call (mocked or real) Gemini API endpoint: {gemini_connector.api_endpoint}")
        print(f"Using API Key: ...{gemini_connector.api_key[-4:] if gemini_connector.api_key else 'None'}")


        # Test 1: Generate text
        print("\n1. Test: Generate Text")
        prompt1 = "What is the speed of light in a vacuum?"
        try:
            result1 = await gemini_connector.execute("generate_text", {"prompt": prompt1})
            print(f"Result for '{prompt1}':")
            if result1.get("success"):
                print(f"  Success: True")
                print(f"  Generated Text: {result1.get('data', {}).get('generated_text')[:200]}...")
            else:
                print(f"  Success: False")
                print(f"  Error: {result1.get('error')}")
                print(f"  Details: {result1.get('details')}")
        except Exception as e:
            print(f"  Caught Exception: {e}")

        # Test 2: Unknown command
        print("\n2. Test: Unknown command")
        try:
            result2 = await gemini_connector.execute("analyze_sentiment", {"text": "This is great!"})
            print(f"Result for 'analyze_sentiment': {result2}")
        except Exception as e:
            print(f"  Caught Exception: {e}")

        # Test 3: Missing prompt
        print("\n3. Test: Missing prompt for generate_text")
        try:
            result3 = await gemini_connector.execute("generate_text", {})
            print(f"Result for missing prompt: {result3}")
        except Exception as e:
            print(f"  Caught Exception: {e}")

    # Setup logging to see connector's internal logs for the example run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # asyncio.run(main()) # This will make real API calls if key and endpoint are valid.
    print("\nNOTE: The main() function for GeminiServiceConnector is commented out by default")
    print("to prevent accidental real API calls during automated runs.")
    print("Uncomment 'asyncio.run(main())' and ensure GEMINI_API_KEY is set to test live.")
