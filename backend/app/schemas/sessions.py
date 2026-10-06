from pydantic import BaseModel, EmailStr, Field


class PasswordConfirmation(BaseModel):
    current_password: str = Field(min_length=1)


class PasswordChange(PasswordConfirmation):
    new_password: str = Field(min_length=12, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class ResetRequestedResponse(BaseModel):
    message: str = "If this account is active, a password reset link will be emailed."
