"""
Notification system for external integrations.
Supports SMS, Email, WhatsApp, and Webhook notifications.
"""

import smtplib
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from datetime import datetime
import sqlite3

from modules.utils.logger import get_logger
from core.config import settings

logger = get_logger(__name__)


class NotificationConfig:
    def __init__(self):
        # Email Configuration
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_username = ""
        self.email_password = ""
        self.from_email = ""
        
        # SMS Configuration (using TextBelt API as example)
        self.sms_api_key = ""
        self.sms_api_url = "https://textbelt.com/text"
        
        # WhatsApp Configuration (using Twilio WhatsApp API)
        self.whatsapp_account_sid = ""
        self.whatsapp_auth_token = ""
        self.whatsapp_from_number = ""
        
        # Webhook Configuration
        self.webhook_urls = []
        
        # Load from database
        self.load_config()

    def load_config(self):
        """Load notification configuration from database."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT config_key, config_value FROM notification_config
                """)
                
                config_map = dict(cursor.fetchall())
                
                # Update configuration
                for key, value in config_map.items():
                    if hasattr(self, key):
                        if key == 'webhook_urls':
                            setattr(self, key, json.loads(value) if value else [])
                        else:
                            setattr(self, key, value)
                            
        except Exception as e:
            logger.warning(f"Could not load notification config: {e}")

    def save_config(self, config_updates: Dict):
        """Save notification configuration to database."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                
                # Create table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notification_config (
                        config_key TEXT PRIMARY KEY,
                        config_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Update configuration
                for key, value in config_updates.items():
                    if key == 'webhook_urls':
                        value = json.dumps(value)
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO notification_config (config_key, config_value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (key, value))
                    
                    # Update instance variable
                    setattr(self, key, config_updates[key])
                
                conn.commit()
                logger.info("Notification configuration updated")
                
        except Exception as e:
            logger.error(f"Failed to save notification config: {e}")


class NotificationManager:
    def __init__(self):
        self.config = NotificationConfig()
        self.init_tables()

    def init_tables(self):
        """Initialize notification tables."""
        with sqlite3.connect("traffic_analyzer.db") as conn:
            cursor = conn.cursor()
            
            # Notification rules table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_rules (
                    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    conditions_json TEXT DEFAULT '{}',
                    notification_types TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Notification history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_history (
                    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER,
                    event_type TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (rule_id) REFERENCES notification_rules (rule_id)
                )
            """)
            
            conn.commit()

    def add_notification_rule(self, name: str, event_type: str, conditions: Dict,
                            notification_types: List[str], recipients: Dict) -> int:
        """Add a new notification rule."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO notification_rules 
                    (name, event_type, conditions_json, notification_types, recipients_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name, event_type, json.dumps(conditions),
                    ','.join(notification_types), json.dumps(recipients)
                ))
                
                rule_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Notification rule added: {name} (ID: {rule_id})")
                return rule_id
                
        except Exception as e:
            logger.error(f"Failed to add notification rule: {e}")
            return 0

    def send_overspeed_alert(self, vehicle_data: Dict, camera_info: Dict):
        """Send overspeed violation alert."""
        event_data = {
            "event_type": "overspeed_violation",
            "vehicle_id": vehicle_data.get("vehicle_unique_id"),
            "speed": vehicle_data.get("max_speed", 0),
            "speed_limit": settings.SPEED_LIMIT_KMH,
            "plate_number": vehicle_data.get("plate_number", "Unknown"),
            "camera_name": camera_info.get("name", "Unknown"),
            "location": camera_info.get("location", "Unknown"),
            "timestamp": datetime.now().isoformat()
        }
        
        self._process_event("overspeed_violation", event_data)

    def send_system_alert(self, alert_type: str, message: str, severity: str = "info"):
        """Send system alert notification."""
        event_data = {
            "event_type": "system_alert",
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat()
        }
        
        self._process_event("system_alert", event_data)

    def _process_event(self, event_type: str, event_data: Dict):
        """Process event and send notifications based on rules."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT rule_id, name, conditions_json, notification_types, recipients_json
                    FROM notification_rules 
                    WHERE event_type = ? AND is_active = 1
                """, (event_type,))
                
                for row in cursor.fetchall():
                    rule_id, name, conditions_json, notification_types, recipients_json = row
                    
                    conditions = json.loads(conditions_json)
                    recipients = json.loads(recipients_json)
                    
                    # Check if conditions are met
                    if self._check_conditions(event_data, conditions):
                        # Send notifications
                        for notification_type in notification_types.split(','):
                            self._send_notification(
                                rule_id, notification_type.strip(), 
                                event_data, recipients
                            )
                            
        except Exception as e:
            logger.error(f"Failed to process event {event_type}: {e}")

    def _check_conditions(self, event_data: Dict, conditions: Dict) -> bool:
        """Check if event data meets notification conditions."""
        try:
            for key, condition in conditions.items():
                if key not in event_data:
                    continue
                
                value = event_data[key]
                operator = condition.get("operator", "eq")
                expected = condition.get("value")
                
                if operator == "gt" and value <= expected:
                    return False
                elif operator == "lt" and value >= expected:
                    return False
                elif operator == "eq" and value != expected:
                    return False
                elif operator == "contains" and expected not in str(value):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking conditions: {e}")
            return False

    def _send_notification(self, rule_id: int, notification_type: str, 
                          event_data: Dict, recipients: Dict):
        """Send notification using specified method."""
        try:
            message = self._format_message(event_data)
            
            if notification_type == "email":
                self._send_email(rule_id, message, recipients.get("emails", []))
            elif notification_type == "sms":
                self._send_sms(rule_id, message, recipients.get("phones", []))
            elif notification_type == "whatsapp":
                self._send_whatsapp(rule_id, message, recipients.get("whatsapp", []))
            elif notification_type == "webhook":
                self._send_webhook(rule_id, event_data, recipients.get("webhooks", []))
                
        except Exception as e:
            logger.error(f"Failed to send {notification_type} notification: {e}")

    def _format_message(self, event_data: Dict) -> str:
        """Format notification message based on event data."""
        if event_data["event_type"] == "overspeed_violation":
            return f"""
🚨 OVERSPEED VIOLATION DETECTED 🚨

Vehicle ID: {event_data.get('vehicle_id', 'Unknown')}
License Plate: {event_data.get('plate_number', 'Unknown')}
Speed: {event_data.get('speed', 0)} km/h
Speed Limit: {event_data.get('speed_limit', 0)} km/h
Camera: {event_data.get('camera_name', 'Unknown')}
Location: {event_data.get('location', 'Unknown')}
Time: {event_data.get('timestamp', 'Unknown')}

Please take appropriate action.
            """.strip()
        
        elif event_data["event_type"] == "system_alert":
            severity_emoji = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌",
                "critical": "🚨"
            }
            
            emoji = severity_emoji.get(event_data.get("severity", "info"), "ℹ️")
            
            return f"""
{emoji} SYSTEM ALERT {emoji}

Alert Type: {event_data.get('alert_type', 'Unknown')}
Message: {event_data.get('message', 'No message')}
Severity: {event_data.get('severity', 'info').upper()}
Time: {event_data.get('timestamp', 'Unknown')}
            """.strip()
        
        return f"Event: {event_data.get('event_type', 'Unknown')}\nTime: {event_data.get('timestamp', 'Unknown')}"

    def _send_email(self, rule_id: int, message: str, recipients: List[str]):
        """Send email notification."""
        if not recipients or not self.config.email_username:
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.from_email or self.config.email_username
            msg['Subject'] = "Traffic Speed Analyzer Alert"
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            server.starttls()
            server.login(self.config.email_username, self.config.email_password)
            
            for recipient in recipients:
                msg['To'] = recipient
                server.send_message(msg)
                
                self._log_notification(rule_id, "email", recipient, message, "sent")
                logger.info(f"Email sent to {recipient}")
            
            server.quit()
            
        except Exception as e:
            for recipient in recipients:
                self._log_notification(rule_id, "email", recipient, message, "failed", str(e))
            logger.error(f"Failed to send email: {e}")

    def _send_sms(self, rule_id: int, message: str, recipients: List[str]):
        """Send SMS notification."""
        if not recipients or not self.config.sms_api_key:
            return

        try:
            for recipient in recipients:
                payload = {
                    'phone': recipient,
                    'message': message,
                    'key': self.config.sms_api_key
                }
                
                response = requests.post(self.config.sms_api_url, data=payload, timeout=10)
                
                if response.status_code == 200:
                    self._log_notification(rule_id, "sms", recipient, message, "sent")
                    logger.info(f"SMS sent to {recipient}")
                else:
                    self._log_notification(rule_id, "sms", recipient, message, "failed", response.text)
                    
        except Exception as e:
            for recipient in recipients:
                self._log_notification(rule_id, "sms", recipient, message, "failed", str(e))
            logger.error(f"Failed to send SMS: {e}")

    def _send_whatsapp(self, rule_id: int, message: str, recipients: List[str]):
        """Send WhatsApp notification using Twilio."""
        if not recipients or not self.config.whatsapp_account_sid:
            return

        try:
            from twilio.rest import Client
            
            client = Client(self.config.whatsapp_account_sid, self.config.whatsapp_auth_token)
            
            for recipient in recipients:
                message_obj = client.messages.create(
                    body=message,
                    from_=f'whatsapp:{self.config.whatsapp_from_number}',
                    to=f'whatsapp:{recipient}'
                )
                
                self._log_notification(rule_id, "whatsapp", recipient, message, "sent")
                logger.info(f"WhatsApp sent to {recipient}")
                
        except Exception as e:
            for recipient in recipients:
                self._log_notification(rule_id, "whatsapp", recipient, message, "failed", str(e))
            logger.error(f"Failed to send WhatsApp: {e}")

    def _send_webhook(self, rule_id: int, event_data: Dict, webhook_urls: List[str]):
        """Send webhook notification."""
        if not webhook_urls:
            return

        try:
            payload = {
                "event": event_data,
                "timestamp": datetime.now().isoformat(),
                "source": "traffic_speed_analyzer"
            }
            
            for webhook_url in webhook_urls:
                response = requests.post(
                    webhook_url, 
                    json=payload, 
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                
                if response.status_code in [200, 201, 202]:
                    self._log_notification(rule_id, "webhook", webhook_url, json.dumps(payload), "sent")
                    logger.info(f"Webhook sent to {webhook_url}")
                else:
                    self._log_notification(rule_id, "webhook", webhook_url, json.dumps(payload), "failed", response.text)
                    
        except Exception as e:
            for webhook_url in webhook_urls:
                self._log_notification(rule_id, "webhook", webhook_url, json.dumps(payload), "failed", str(e))
            logger.error(f"Failed to send webhook: {e}")

    def _log_notification(self, rule_id: int, notification_type: str, recipient: str,
                         message: str, status: str, error_message: str = None):
        """Log notification attempt to database."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO notification_history 
                    (rule_id, event_type, notification_type, recipient, message, status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (rule_id, "unknown", notification_type, recipient, message, status, error_message))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")

    def get_notification_history(self, limit: int = 100) -> List[Dict]:
        """Get notification history."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT nh.*, nr.name as rule_name
                    FROM notification_history nh
                    LEFT JOIN notification_rules nr ON nh.rule_id = nr.rule_id
                    ORDER BY nh.sent_at DESC
                    LIMIT ?
                """, (limit,))
                
                history = []
                for row in cursor.fetchall():
                    notification_id, rule_id, event_type, notification_type, recipient, message, status, error_message, sent_at, rule_name = row
                    history.append({
                        "notification_id": notification_id,
                        "rule_id": rule_id,
                        "rule_name": rule_name,
                        "event_type": event_type,
                        "notification_type": notification_type,
                        "recipient": recipient,
                        "message": message,
                        "status": status,
                        "error_message": error_message,
                        "sent_at": sent_at
                    })
                
                return history
                
        except Exception as e:
            logger.error(f"Failed to get notification history: {e}")
            return []

    def test_notification(self, notification_type: str, recipient: str) -> bool:
        """Test notification configuration."""
        try:
            test_message = f"Test notification from Traffic Speed Analyzer at {datetime.now()}"
            
            if notification_type == "email":
                self._send_email(0, test_message, [recipient])
            elif notification_type == "sms":
                self._send_sms(0, test_message, [recipient])
            elif notification_type == "whatsapp":
                self._send_whatsapp(0, test_message, [recipient])
            elif notification_type == "webhook":
                test_data = {"test": True, "message": test_message}
                self._send_webhook(0, test_data, [recipient])
            
            return True
            
        except Exception as e:
            logger.error(f"Test notification failed: {e}")
            return False