"""Domain errors, mapped to HTTP responses in main.py.

Messages are written to be useful to an AI agent: they say what went wrong
and what the valid options are, so the agent can recover or ask the user.
"""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class Invalid(DomainError):
    status_code = 422
