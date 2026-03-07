"""
Authentication & authorization for Pomogaika admin panel
Uses Supabase Auth for login, custom admin_users table for roles
"""

from fastapi import Header, HTTPException, Depends
from typing import Optional
from supabase_client import get_supabase


class AdminUser:
    """Authenticated admin/editor user"""
    def __init__(self, auth_user_id: str, email: str, role: str, name: str):
        self.auth_user_id = auth_user_id
        self.email = email
        self.role = role
        self.name = name

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_editor(self) -> bool:
        return self.role == "editor"


async def get_current_user(authorization: str = Header(...)) -> AdminUser:
    """
    Verify JWT token and return AdminUser with role.
    Usage: user = Depends(get_current_user)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.replace("Bearer ", "")
    sb = get_supabase()

    try:
        # Verify token with Supabase Auth
        user_response = sb.auth.get_user(token)
        auth_user = user_response.user
        if not auth_user:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    # Get role from admin_users table
    result = sb.table("admin_users").select("*").eq(
        "auth_user_id", auth_user.id
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="User is not an admin or editor"
        )

    admin_data = result.data[0]
    return AdminUser(
        auth_user_id=auth_user.id,
        email=admin_data["email"],
        role=admin_data["role"],
        name=admin_data["name"]
    )


async def require_admin(user: AdminUser = Depends(get_current_user)) -> AdminUser:
    """Require admin role. Usage: user = Depends(require_admin)"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
