"""
Simple authentication helpers for faster startup.
"""

from typing import Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

def get_current_user_simple(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Simple auth check - returns None if no auth, for now."""
    # For now, return None to allow access without authentication
    # This can be enhanced later when needed
    return None

def require_auth_simple(current_user = Depends(get_current_user_simple)):
    """Simple auth requirement - disabled for now."""
    # For now, allow all requests
    return {"user_id": 1, "username": "admin", "role": "admin"}

def require_permission_simple(permission: str):
    """Simple permission check - allows all for now."""
    def permission_checker(current_user = Depends(require_auth_simple)):
        return current_user
    return permission_checker

def require_role_simple(role: str):
    """Simple role check - allows all for now."""
    def role_checker(current_user = Depends(require_auth_simple)):
        return current_user
    return role_checker