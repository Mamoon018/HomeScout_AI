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


class CategoryResolutionError(Exception):
    """Base failure surface of Mechanism 2 Component 2A (category scope resolution)."""

    # Named so a caller can report which operation exited without reading a traceback.
    # Operation 1 and Operation 2 share these classes, so the raiser may override the
    # default with the concrete stage via the constructor.
    stage: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class CategoryMappingProviderError(CategoryResolutionError):
    """Raised when no provider in the bound order returned a mapping/resolution body."""

    stage: ClassVar[str] = "execute_taxonomy_mapping"


class CategoryMappingValidationError(CategoryResolutionError):
    """Raised when a returned body failed the mapping/resolution wire contract."""

    stage: ClassVar[str] = "execute_taxonomy_mapping"
