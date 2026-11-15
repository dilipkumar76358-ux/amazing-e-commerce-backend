from pydantic import BaseModel
from typing import Optional, List


class UserProfileResponse(BaseModel):
    id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    account_status: str = "active"
    roles: List[str] = ["customer"]
    avatar_url: Optional[str] = None


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None


class UserRolesResponse(BaseModel):
    user_id: str
    roles: List[str]
