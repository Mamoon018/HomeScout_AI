from typing import ClassVar


class RequirementExtractionError(Exception):
    """Base failure surface of the requirement interpretation responsibility."""

    # Named so a caller can report which stage exited without inspecting a traceback.
    stage: ClassVar[str] = "unknown"


class InputTooShortError(RequirementExtractionError):
    """Raised when the input is empty, whitespace-only, or under the word bound."""

    stage: ClassVar[str] = "intake_and_assemble_payload"


class UnsupportedLanguageError(RequirementExtractionError):
    """Raised when the input is not written in English."""

    stage: ClassVar[str] = "intake_and_assemble_payload"


class ExtractionProviderError(RequirementExtractionError):
    """Raised when no provider in the bound order returned a body."""

    stage: ClassVar[str] = "execute_and_validate"


class ExtractionValidationError(RequirementExtractionError):
    """Raised when a returned body failed validation against the wire contract."""

    stage: ClassVar[str] = "execute_and_validate"
