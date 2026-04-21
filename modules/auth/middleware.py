"""
Authentication middleware for FastAPI.
"""

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import jwt
from datetime import datetime, timedelta

from modules.auth.models import UserManager, User
from modules.utils.logger import get_logger

logger = get_logger(__name__)

# JWT Configuration
JWT_SECRET_KEY = "your-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security = HTTPBearer(auto_error=False)
user_manager = UserManager()


class AuthMiddleware:
    def __init__(self):
        self.user_manager = UserManager()

    def create_jwt_token(self, user: User) -> str:
        """Create JWT token for user."""
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def verify_jwt_token(self, token: str) -> Optional[dict]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid JWT token")
            return None

    def get_current_user_from_token(self, token: str) -> Optional[User]:
        """Get user from JWT token."""
        payload = self.verify_jwt_token(token)
        if not payload:
            return None
        
        # Get fresh user data from database
        import sqlite3
        with sqlite3.connect("traffic_analyzer.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, email, role, created_at, last_login, is_active
                FROM users WHERE user_id = ? AND is_active = 1
            """, (payload["user_id"],))
            
            result = cursor.fetchone()
            if result:
                user_id, username, email, role, created_at, last_login, is_active = result
                return User(user_id, username, email, role, created_at, last_login, is_active)
        
        return None


auth_middleware = AuthMiddleware()


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[User]:
    """Dependency to get current authenticated user."""
    if not credentials:
        return None
    
    return auth_middleware.get_current_user_from_token(credentials.credentials)


def require_auth(current_user: Optional[User] = Depends(get_current_user)) -> User:
    """Dependency that requires authentication."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_role(required_role: str):
    """Dependency factory that requires specific role."""
    def role_checker(current_user: User = Depends(require_auth)) -> User:
        if current_user.role.value != required_role and current_user.role.value != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required"
            )
        return current_user
    return role_checker


def require_permission(permission: str):
    """Dependency factory that requires specific permission."""
    def permission_checker(current_user: User = Depends(require_auth)) -> User:
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )
        return current_user
    return permission_checker


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str:
    """Get user agent from request."""
    return request.headers.get("User-Agent", "unknown")