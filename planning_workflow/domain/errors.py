"""Workflow-specific exceptions."""


class WorkflowError(RuntimeError):
    """Raised when a mechanical workflow invariant is violated."""


class ConfigurationError(WorkflowError):
    """Raised when required local configuration is missing or unusable."""


class ModelOutputError(WorkflowError):
    """Raised when a model response cannot be accepted into project state."""
