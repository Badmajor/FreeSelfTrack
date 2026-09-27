class DomainError(Exception):
    status_code = 400


class NotFoundError(DomainError):
    status_code = 404


class AccessDeniedError(DomainError):
    # Resource-scoped endpoints deliberately hide inaccessible objects.
    status_code = 404


class InvalidWorkflowError(DomainError):
    status_code = 422
