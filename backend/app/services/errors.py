class DomainError(Exception):
    status_code = 400


class NotFoundError(DomainError):
    status_code = 404


class InvalidWorkflowError(DomainError):
    status_code = 422


class DuplicateEmailError(DomainError):
    status_code = 409


class InvalidCredentialsError(DomainError):
    status_code = 401
