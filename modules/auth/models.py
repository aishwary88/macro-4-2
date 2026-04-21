"""
User authentication models and database schema.
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from enum import Enum

from modules.utils.logger import get_logger

logger = get_logger(__name__)


class UserRole(Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User:
    def __init__(self, user_id: int, username: str, email: str, role: str, 
                 created_at: str, last_login: Optional[str] = None, is_active: bool = True):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.role = UserRole(role)
        self.created_at = created_at
        self.last_login = last_login
        self.is_active = is_active

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "is_active": self.is_active
        }

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission based on role."""
        permissions = {
            UserRole.ADMIN: [
                "view_dashboard", "manage_users", "manage_cameras", 
                "view_reports", "export_data", "system_settings",
                "delete_data", "manage_integrations"
            ],
            UserRole.OPERATOR: [
                "view_dashboard", "manage_cameras", "view_reports", 
                "export_data", "upload_videos"
            ],
            UserRole.VIEWER: [
                "view_dashboard", "view_reports"
            ]
        }
        return permission in permissions.get(self.role, [])


class Session:
    def __init__(self, session_id: str, user_id: int, created_at: str, 
                 expires_at: str, is_active: bool = True):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = created_at
        self.expires_at = expires_at
        self.is_active = is_active

    def is_expired(self) -> bool:
        """Check if session is expired."""
        return datetime.now() > datetime.fromisoformat(self.expires_at)


class UserManager:
    def __init__(self, db_path: str = "traffic_analyzer.db"):
        self.db_path = db_path
        self.init_tables()
        self.create_default_admin()

    def init_tables(self):
        """Initialize user management tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    failed_login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP
                )
            """)
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # Activity logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            conn.commit()
            logger.info("User management tables initialized")

    def create_default_admin(self):
        """Create default admin user if no users exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            if user_count == 0:
                # Create default admin
                self.create_user(
                    username="admin",
                    email="admin@trafficanalyzer.com",
                    password="admin123",
                    role=UserRole.ADMIN
                )
                logger.info("Default admin user created: admin/admin123")

    def hash_password(self, password: str, salt: str = None) -> tuple:
        """Hash password with salt."""
        if salt is None:
            salt = secrets.token_hex(32)
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        
        return password_hash, salt

    def create_user(self, username: str, email: str, password: str, 
                   role: UserRole) -> Optional[int]:
        """Create a new user."""
        try:
            password_hash, salt = self.hash_password(password)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, salt, role)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, email, password_hash, salt, role.value))
                
                user_id = cursor.lastrowid
                conn.commit()
                
                self.log_activity(user_id, "USER_CREATED", f"User {username} created")
                logger.info(f"User created: {username} ({role.value})")
                return user_id
                
        except sqlite3.IntegrityError as e:
            logger.error(f"Failed to create user {username}: {e}")
            return None

    def authenticate_user(self, username: str, password: str, 
                         ip_address: str = None) -> Optional[User]:
        """Authenticate user credentials."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, email, password_hash, salt, role, 
                       created_at, last_login, is_active, failed_login_attempts, locked_until
                FROM users WHERE username = ? OR email = ?
            """, (username, username))
            
            user_data = cursor.fetchone()
            if not user_data:
                self.log_activity(None, "LOGIN_FAILED", f"Invalid username: {username}", ip_address)
                return None
            
            user_id, username, email, stored_hash, salt, role, created_at, last_login, is_active, failed_attempts, locked_until = user_data
            
            # Check if account is locked
            if locked_until and datetime.now() < datetime.fromisoformat(locked_until):
                self.log_activity(user_id, "LOGIN_BLOCKED", "Account locked", ip_address)
                return None
            
            # Check if account is active
            if not is_active:
                self.log_activity(user_id, "LOGIN_FAILED", "Account disabled", ip_address)
                return None
            
            # Verify password
            password_hash, _ = self.hash_password(password, salt)
            if password_hash != stored_hash:
                # Increment failed attempts
                failed_attempts += 1
                lock_until = None
                if failed_attempts >= 5:
                    lock_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                
                cursor.execute("""
                    UPDATE users SET failed_login_attempts = ?, locked_until = ?
                    WHERE user_id = ?
                """, (failed_attempts, lock_until, user_id))
                conn.commit()
                
                self.log_activity(user_id, "LOGIN_FAILED", "Invalid password", ip_address)
                return None
            
            # Reset failed attempts and update last login
            cursor.execute("""
                UPDATE users SET failed_login_attempts = 0, locked_until = NULL, 
                                last_login = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            
            user = User(user_id, username, email, role, created_at, last_login, is_active)
            self.log_activity(user_id, "LOGIN_SUCCESS", "User logged in", ip_address)
            return user

    def create_session(self, user_id: int, ip_address: str = None, 
                      user_agent: str = None) -> str:
        """Create a new user session."""
        session_id = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_sessions (session_id, user_id, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, user_id, expires_at, ip_address, user_agent))
            conn.commit()
        
        return session_id

    def get_user_by_session(self, session_id: str) -> Optional[User]:
        """Get user by session ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.username, u.email, u.role, u.created_at, 
                       u.last_login, u.is_active, s.expires_at
                FROM users u
                JOIN user_sessions s ON u.user_id = s.user_id
                WHERE s.session_id = ? AND s.is_active = 1
            """, (session_id,))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            user_id, username, email, role, created_at, last_login, is_active, expires_at = result
            
            # Check if session is expired
            if datetime.now() > datetime.fromisoformat(expires_at):
                self.invalidate_session(session_id)
                return None
            
            return User(user_id, username, email, role, created_at, last_login, is_active)

    def invalidate_session(self, session_id: str):
        """Invalidate a user session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_sessions SET is_active = 0 WHERE session_id = ?
            """, (session_id,))
            conn.commit()

    def get_all_users(self) -> List[User]:
        """Get all users."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, email, role, created_at, last_login, is_active
                FROM users ORDER BY created_at DESC
            """)
            
            users = []
            for row in cursor.fetchall():
                user_id, username, email, role, created_at, last_login, is_active = row
                users.append(User(user_id, username, email, role, created_at, last_login, is_active))
            
            return users

    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information."""
        allowed_fields = ['username', 'email', 'role', 'is_active']
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                values.append(value.value if isinstance(value, UserRole) else value)
        
        if not updates:
            return False
        
        values.append(user_id)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE users SET {', '.join(updates)} WHERE user_id = ?
                """, values)
                conn.commit()
                
                self.log_activity(user_id, "USER_UPDATED", f"User updated: {kwargs}")
                return cursor.rowcount > 0
                
        except sqlite3.IntegrityError:
            return False

    def delete_user(self, user_id: int) -> bool:
        """Delete a user (soft delete by deactivating)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_active = 0 WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            
            # Invalidate all sessions
            cursor.execute("""
                UPDATE user_sessions SET is_active = 0 WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            
            self.log_activity(user_id, "USER_DELETED", "User deactivated")
            return cursor.rowcount > 0

    def log_activity(self, user_id: Optional[int], action: str, 
                    details: str = None, ip_address: str = None):
        """Log user activity."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO activity_logs (user_id, action, details, ip_address)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, details, ip_address))
            conn.commit()

    def get_activity_logs(self, user_id: Optional[int] = None, 
                         limit: int = 100) -> List[Dict]:
        """Get activity logs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute("""
                    SELECT al.*, u.username 
                    FROM activity_logs al
                    LEFT JOIN users u ON al.user_id = u.user_id
                    WHERE al.user_id = ?
                    ORDER BY al.timestamp DESC LIMIT ?
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT al.*, u.username 
                    FROM activity_logs al
                    LEFT JOIN users u ON al.user_id = u.user_id
                    ORDER BY al.timestamp DESC LIMIT ?
                """, (limit,))
            
            logs = []
            for row in cursor.fetchall():
                log_id, user_id, action, details, ip_address, timestamp, username = row
                logs.append({
                    "log_id": log_id,
                    "user_id": user_id,
                    "username": username,
                    "action": action,
                    "details": details,
                    "ip_address": ip_address,
                    "timestamp": timestamp
                })
            
            return logs