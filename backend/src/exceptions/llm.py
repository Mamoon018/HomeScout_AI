class LLMProviderError(Exception):
    """Base error for the structured-LLM provider adapters."""


class LLMResponseTruncatedError(LLMProviderError):
    """Raised when a provider stopped generating before the body was complete."""
