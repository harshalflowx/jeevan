import asyncio
from .base_service_connector import BaseServiceConnector, ServiceCredentials, AuthenticationError, ServiceSpecificError

class MockSearchService(BaseServiceConnector):
    """
    A mock implementation of a Search Service Connector.
    It simulates API calls to a web search engine.
    """
    def __init__(self, service_name: str = "MockSearchService", credentials: ServiceCredentials = None, api_delay_seconds: float = 0.05):
        self.api_delay_seconds = api_delay_seconds
        self.mock_api_key = "mock_search_api_key_valid" # Expected API key for this mock
        super().__init__(service_name, credentials)

        # Mock database of search results
        self.search_index = {
            "python programming": [
                {"title": "Official Python Website", "url": "https://www.python.org", "snippet": "The official website for Python programming language."},
                {"title": "Python for Beginners", "url": "https://example.com/python-beginners", "snippet": "A tutorial for those new to Python."},
            ],
            "large language models": [
                {"title": "LLM Overview - Wikipedia", "url": "https://en.wikipedia.org/wiki/Large_language_model", "snippet": "A large language model (LLM) is a language model consisting of a neural network with many parameters..."},
                {"title": "Understanding LLMs", "url": "https://example.com/llm-explained", "snippet": "An article explaining how LLMs work."},
            ]
        }

    def _validate_credentials(self):
        """
        Mock validation: For this service, let's say credentials are required.
        """
        if not self.credentials or not self.credentials.get_credential("api_key"):
            # In a real service, this might raise an error immediately or disable the service.
            # For this mock, we'll print a warning, and `execute` will check.
            print(f"Warning: {self.service_name} initialized without a valid API key in credentials. Operations will likely fail authentication.")
        elif self.credentials.get_credential("api_key") != self.mock_api_key:
             print(f"Warning: {self.service_name} initialized with an API key that doesn't match the expected mock key.")


    async def execute(self, command: str, params: dict = None, **kwargs) -> dict:
        """
        Simulates executing a command against a mock Search Engine.

        Supported commands:
        - "search_web": Simulates a web search.
            Params: {"query": "Search query text", "num_results": 3}

        Returns:
            dict: A dictionary containing the simulated search results.
                  Includes "success": True/False and "data": {"results": [...]} or "error": ...
        """
        await asyncio.sleep(self.api_delay_seconds) # Simulate network latency

        # Authentication check
        if not self.credentials or self.credentials.api_key != self.mock_api_key:
            raise AuthenticationError(f"{self.service_name}: Invalid or missing API key.")

        params = params or {}

        if command == "search_web":
            query = params.get("query")
            num_results = params.get("num_results", 5)

            if not query:
                return {"success": False, "error": "Query is required for search_web."}

            query_lower = query.lower()
            results = []

            # Simple mock search logic:
            for key_phrase, items in self.search_index.items():
                if key_phrase in query_lower:
                    results.extend(items)

            # If no exact match, provide some generic results or indicate no results
            if not results and query_lower == "empty search":
                results = [] # specific case for testing empty results
            elif not results:
                 results.append({
                    "title": f"No specific results for '{query}'",
                    "url": f"https://example.com/search?q={query.replace(' ', '+')}",
                    "snippet": f"This is a generic mock search result for '{query}'. Try 'python programming' or 'large language models'."
                })


            return {"success": True, "data": {"query": query, "results": results[:num_results], "total_found": len(results)}}

        else:
            raise ServiceSpecificError(f"{self.service_name}: Unknown command '{command}'.")

if __name__ == '__main__':
    async def main():
        print("--- MockSearchService Example ---")

        # Valid credentials are required for this mock service
        valid_creds = ServiceCredentials(api_key="mock_search_api_key_valid")
        invalid_creds = ServiceCredentials(api_key="wrong_key")
        no_creds_service = MockSearchService(api_delay_seconds=0.01) # Will print warning

        search_service_valid = MockSearchService(credentials=valid_creds, api_delay_seconds=0.01)
        search_service_invalid_auth = MockSearchService(credentials=invalid_creds, api_delay_seconds=0.01)


        print("\n1. Testing with VALID credentials...")
        search_query_python = "python programming"
        results_python = await search_service_valid.execute("search_web", {"query": search_query_python, "num_results": 1})
        print(f"Search results for '{search_query_python}': {results_python}")

        search_query_llm = "large language models benefits" # partial match
        results_llm = await search_service_valid.execute("search_web", {"query": search_query_llm}) # default num_results
        print(f"Search results for '{search_query_llm}': {results_llm}")

        search_query_unknown = "new ai technology" # no specific mock data
        results_unknown = await search_service_valid.execute("search_web", {"query": search_query_unknown})
        print(f"Search results for '{search_query_unknown}': {results_unknown}")

        search_query_empty_test = "empty search" # specific test for empty results
        results_empty_test = await search_service_valid.execute("search_web", {"query": search_query_empty_test})
        print(f"Search results for '{search_query_empty_test}': {results_empty_test}")


        print("\n2. Testing with INVALID credentials (expected AuthenticationError)...")
        try:
            await search_service_invalid_auth.execute("search_web", {"query": "anything"})
        except AuthenticationError as e:
            print(f"Caught expected error: {e}")
        except Exception as e:
            print(f"Caught unexpected error: {e}")

        print("\n3. Testing with NO credentials (expected AuthenticationError from execute)...")
        try:
            # Initialization of no_creds_service would have printed a warning.
            # The execute method should enforce the auth check.
            await no_creds_service.execute("search_web", {"query": "anything"})
        except AuthenticationError as e:
            print(f"Caught expected error: {e}")
        except Exception as e:
            print(f"Caught unexpected error: {e}")


        print("\n4. Testing unknown command (expected ServiceSpecificError)...")
        try:
            await search_service_valid.execute("translate_text", {"text": "hello"})
        except ServiceSpecificError as e:
            print(f"Caught expected error: {e}")

        print("\n--- End of Example ---")

    asyncio.run(main())
