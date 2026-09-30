from sqlmodel import SQLModel
from pydantic import EmailStr

class SigninRequest(SQLModel):
    username: str
    password: str

class SignupRequest(SQLModel):
    username: str
    email: EmailStr
    password: str