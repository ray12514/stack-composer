from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


class StackComposerError(Exception):
    """Base class for user-facing stack-composer errors."""


class NotImplementedCommand(StackComposerError):
    """Raised by command stubs that are intentionally not implemented yet."""


class ValidationFailed(StackComposerError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__(f"validation failed with {len(issues)} issue(s)")
