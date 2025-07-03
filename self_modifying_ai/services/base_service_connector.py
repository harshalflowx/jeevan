from abc import ABC, abstractmethod

class ServiceCredentials:
    """
    A simple container for service credentials.
    Specific services might require different credential types (API keys, tokens, etc.).
    """
    def __init__(self, api_key: str = None, **kwargs):
        self.api_key = api_key
        self.other_credentials = kwargs

    def get_credential(self, name: str):
        if name == "api_key":
            return self.api_key
        return self.other_credentials.get(name)

class BaseServiceConnector(ABC):
    """
    Abstract base class for all service connectors.
    Service connectors are responsible for interacting with external APIs or services.
    """
    def __init__(self, service_name: str, credentials: ServiceCredentials = None):
        """
        Initializes the service connector.

        Args:
            service_name (str): A human-readable name for the service.
            credentials (ServiceCredentials, optional): Credentials required to authenticate with the service.
                                                       Defaults to None if the service requires no auth.
        """
        self.service_name = service_name
        self.credentials = credentials
        self._validate_credentials()

    @abstractmethod
    def _validate_credentials(self):
        """
        Validates if the necessary credentials for this service are provided.
        Should raise an error or log a warning if essential credentials are missing.
        This method is called during __init__.
        """
        pass

    @abstractmethod
    async def execute(self, command: str, params: dict = None, **kwargs) -> dict:
        """
        Executes a command or query against the external service.
        This method should be implemented by concrete service connectors.

        Args:
            command (str): The specific command or operation to perform (e.g., "translate_text", "search_web").
            params (dict, optional): Parameters for the command.
            **kwargs: Additional keyword arguments specific to the service implementation.

        Returns:
            dict: A dictionary containing the result from the service.
                  The structure of this dictionary will depend on the service.
                  It should include a "success": True/False field.

        Raises:
            NotImplementedError: If the concrete class does not implement this method.
            ConnectionError: If there's an issue connecting to the service.
            AuthenticationError: If authentication with the service fails.
            ServiceSpecificError: For other errors returned by the service.
        """
        pass

    def get_service_name(self) -> str:
        return self.service_name

# Example of potential error types (can be defined in a shared exceptions module later)
class AuthenticationError(Exception):
    pass

class ServiceSpecificError(Exception):
    pass

if __name__ == '__main__':
    print("BaseServiceConnector and ServiceCredentials definitions.")
    print("This file is intended to be imported, not run directly for functionality.")

    # Example of how a concrete class might use ServiceCredentials
    class MySampleCreds(ServiceCredentials):
        def __init__(self, api_key: str, user_id: str):
            super().__init__(api_key=api_key, user_id=user_id)
            self.user_id = user_id

    print("\nExample ServiceCredentials usage:")
    creds1 = ServiceCredentials(api_key="key123")
    print(f"Creds1 API Key: {creds1.get_credential('api_key')}")

    creds2 = MySampleCreds(api_key="key456", user_id="userABC")
    print(f"Creds2 API Key: {creds2.get_credential('api_key')}")
    print(f"Creds2 User ID: {creds2.get_credential('user_id')}")
    print(f"Creds2 via direct attribute: {creds2.user_id}")
