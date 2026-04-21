"""
Multi-camera management system for Traffic Speed Analyzer.
"""

import sqlite3
import threading
import time
import cv2
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json

from modules.utils.logger import get_logger
from modules.detection.detector import VehicleDetector
from modules.tracking.tracker import VehicleTracker
from modules.tracking.vehicle_state import VehicleStateManager
from modules.classification.classifier import VehicleClassifier
from modules.calibration.roi_manager import ROIManager
from modules.visualization.renderer import FrameRenderer
from modules.utils.geometry import bbox_center
from core.config import settings

logger = get_logger(__name__)


class CameraStatus(Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    ERROR = "error"
    CONNECTING = "connecting"


class CameraType(Enum):
    WEBCAM = "webcam"
    IP_CAMERA = "ip_camera"
    RTSP_STREAM = "rtsp_stream"
    USB_CAMERA = "usb_camera"


class Camera:
    def __init__(self, camera_id: int, name: str, source: str, camera_type: str,
                 location: str = "", description: str = "", is_active: bool = True,
                 settings_json: str = "{}"):
        self.camera_id = camera_id
        self.name = name
        self.source = source
        self.camera_type = CameraType(camera_type)
        self.location = location
        self.description = description
        self.is_active = is_active
        self.settings = json.loads(settings_json) if settings_json else {}
        
        # Runtime properties
        self.status = CameraStatus.OFFLINE
        self.last_frame = None
        self.stats = {
            "total_vehicles": 0,
            "avg_speed": 0.0,
            "overspeed_count": 0,
            "plates_detected": 0,
            "cars": 0,
            "trucks": 0,
            "buses": 0,
            "bikes": 0,
            "fps": 0.0,
            "last_update": None
        }
        self.error_message = ""

    def to_dict(self) -> Dict:
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "source": self.source,
            "camera_type": self.camera_type.value,
            "location": self.location,
            "description": self.description,
            "is_active": self.is_active,
            "status": self.status.value,
            "settings": self.settings,
            "stats": self.stats,
            "error_message": self.error_message
        }


class CameraStream:
    def __init__(self, camera: Camera):
        self.camera = camera
        self.cap = None
        self.thread = None
        self.running = False
        self.detector = None
        self.tracker = None
        self.state_mgr = None
        self.classifier = None
        self.roi_mgr = None
        self.renderer = None
        self.frame_count = 0
        self.start_time = None

    def initialize_components(self):
        """Initialize AI components for this camera."""
        try:
            self.detector = VehicleDetector(confidence_threshold=settings.DETECTION_CONFIDENCE)
            self.tracker = VehicleTracker()
            self.state_mgr = VehicleStateManager()
            self.classifier = VehicleClassifier()
            self.roi_mgr = ROIManager(
                line_a_y=self.camera.settings.get('roi_line_a_y', settings.ROI_LINE_A_Y),
                line_b_y=self.camera.settings.get('roi_line_b_y', settings.ROI_LINE_B_Y),
                known_distance=self.camera.settings.get('roi_distance', settings.ROI_DISTANCE_METERS)
            )
            self.renderer = FrameRenderer(debug=settings.DEBUG)
            logger.info(f"AI components initialized for camera {self.camera.name}")
        except Exception as e:
            logger.error(f"Failed to initialize AI components for camera {self.camera.name}: {e}")
            raise

    def start(self) -> bool:
        """Start camera stream processing."""
        if self.running:
            return True

        try:
            # Initialize camera capture
            if self.camera.camera_type == CameraType.USB_CAMERA:
                camera_index = int(self.camera.source)
                self.cap = cv2.VideoCapture(camera_index)
            else:
                self.cap = cv2.VideoCapture(self.camera.source)
                if self.camera.camera_type == CameraType.IP_CAMERA:
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self.cap.isOpened():
                raise Exception(f"Cannot open camera source: {self.camera.source}")

            # Initialize AI components
            self.initialize_components()

            # Start processing thread
            self.running = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._process_loop, daemon=True)
            self.thread.start()

            self.camera.status = CameraStatus.ONLINE
            logger.info(f"Camera stream started: {self.camera.name}")
            return True

        except Exception as e:
            self.camera.status = CameraStatus.ERROR
            self.camera.error_message = str(e)
            logger.error(f"Failed to start camera {self.camera.name}: {e}")
            return False

    def stop(self):
        """Stop camera stream processing."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        if self.cap:
            self.cap.release()
            self.cap = None

        self.camera.status = CameraStatus.OFFLINE
        logger.info(f"Camera stream stopped: {self.camera.name}")

    def _process_loop(self):
        """Main processing loop for camera stream."""
        fps_counter = 0
        fps_start_time = time.time()
        
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame from camera {self.camera.name}")
                    time.sleep(0.1)
                    continue

                # Process frame
                self._process_frame(frame)
                
                # Update FPS
                fps_counter += 1
                if fps_counter % 30 == 0:  # Update FPS every 30 frames
                    current_time = time.time()
                    self.camera.stats["fps"] = 30 / (current_time - fps_start_time)
                    fps_start_time = current_time

                # Control frame rate
                time.sleep(1.0 / settings.CAMERA_FPS)

            except Exception as e:
                logger.error(f"Error processing frame for camera {self.camera.name}: {e}")
                self.camera.status = CameraStatus.ERROR
                self.camera.error_message = str(e)
                time.sleep(1)

    def _process_frame(self, frame):
        """Process a single frame."""
        self.frame_count += 1
        timestamp = self.frame_count / settings.CAMERA_FPS

        # Run detection and tracking
        detections = self.detector.detect(frame)
        tracked = self.tracker.update(detections)

        # Update vehicle states
        for vehicle in tracked:
            center = bbox_center(vehicle.bbox)
            self.state_mgr.update_position(
                vehicle.vehicle_id, center, timestamp, 
                vehicle.bbox, vehicle.confidence
            )
            self.state_mgr.set_vehicle_type(
                vehicle.vehicle_id, 
                self.classifier.classify(vehicle.class_name)
            )

        # Render frame with annotations
        annotated_frame = self.renderer.draw(
            frame, self.state_mgr, 
            roi_manager=self.roi_mgr, 
            frame_number=self.frame_count, 
            video_fps=settings.CAMERA_FPS
        )

        # Store latest frame
        _, buffer = cv2.imencode('.jpg', annotated_frame, 
                               [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.camera.last_frame = buffer.tobytes()

        # Update statistics
        self._update_stats()

    def _update_stats(self):
        """Update camera statistics."""
        try:
            vehicles = self.state_mgr.vehicles
            if not vehicles:
                return

            speeds = []
            overspeed_count = 0
            plates_detected = 0
            vehicle_types = {"Car": 0, "Truck": 0, "Bus": 0, "Bike": 0}

            for vid, vdata in vehicles.items():
                if vdata.speed is not None:
                    speeds.append(vdata.speed)
                    if vdata.speed > settings.SPEED_LIMIT_KMH:
                        overspeed_count += 1

                if vdata.plate:
                    plates_detected += 1

                vehicle_type = vdata.vehicle_type or "Car"
                vehicle_types[vehicle_type] = vehicle_types.get(vehicle_type, 0) + 1

            avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

            self.camera.stats.update({
                "total_vehicles": len(vehicles),
                "avg_speed": round(avg_speed, 2),
                "overspeed_count": overspeed_count,
                "plates_detected": plates_detected,
                "cars": vehicle_types.get("Car", 0),
                "trucks": vehicle_types.get("Truck", 0),
                "buses": vehicle_types.get("Bus", 0),
                "bikes": vehicle_types.get("Bike", 0),
                "last_update": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Error updating stats for camera {self.camera.name}: {e}")


class MultiCameraManager:
    def __init__(self, db_path: str = "traffic_analyzer.db"):
        self.db_path = db_path
        self.cameras: Dict[int, Camera] = {}
        self.streams: Dict[int, CameraStream] = {}
        self.init_tables()
        self.load_cameras()

    def init_tables(self):
        """Initialize camera management tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cameras (
                    camera_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    camera_type TEXT NOT NULL,
                    location TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT 1,
                    settings_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS camera_stats (
                    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    total_vehicles INTEGER DEFAULT 0,
                    avg_speed REAL DEFAULT 0.0,
                    overspeed_count INTEGER DEFAULT 0,
                    plates_detected INTEGER DEFAULT 0,
                    cars INTEGER DEFAULT 0,
                    trucks INTEGER DEFAULT 0,
                    buses INTEGER DEFAULT 0,
                    bikes INTEGER DEFAULT 0,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (camera_id) REFERENCES cameras (camera_id)
                )
            """)
            
            conn.commit()
            logger.info("Camera management tables initialized")

    def load_cameras(self):
        """Load cameras from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT camera_id, name, source, camera_type, location, 
                       description, is_active, settings_json
                FROM cameras WHERE is_active = 1
            """)
            
            for row in cursor.fetchall():
                camera_id, name, source, camera_type, location, description, is_active, settings_json = row
                camera = Camera(camera_id, name, source, camera_type, 
                              location, description, is_active, settings_json)
                self.cameras[camera_id] = camera
                
        logger.info(f"Loaded {len(self.cameras)} cameras")

    def add_camera(self, name: str, source: str, camera_type: str,
                   location: str = "", description: str = "", 
                   settings: Dict = None) -> Optional[int]:
        """Add a new camera."""
        try:
            settings_json = json.dumps(settings or {})
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO cameras (name, source, camera_type, location, description, settings_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, source, camera_type, location, description, settings_json))
                
                camera_id = cursor.lastrowid
                conn.commit()
                
                # Create camera object
                camera = Camera(camera_id, name, source, camera_type, 
                              location, description, True, settings_json)
                self.cameras[camera_id] = camera
                
                logger.info(f"Camera added: {name} (ID: {camera_id})")
                return camera_id
                
        except Exception as e:
            logger.error(f"Failed to add camera {name}: {e}")
            return None

    def update_camera(self, camera_id: int, **kwargs) -> bool:
        """Update camera information."""
        if camera_id not in self.cameras:
            return False

        allowed_fields = ['name', 'source', 'camera_type', 'location', 'description', 'is_active']
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                values.append(value)
            elif field == 'settings':
                updates.append("settings_json = ?")
                values.append(json.dumps(value))
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(camera_id)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE cameras SET {', '.join(updates)} WHERE camera_id = ?
                """, values)
                conn.commit()
                
                # Update camera object
                for field, value in kwargs.items():
                    if hasattr(self.cameras[camera_id], field):
                        setattr(self.cameras[camera_id], field, value)
                
                logger.info(f"Camera updated: {camera_id}")
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Failed to update camera {camera_id}: {e}")
            return False

    def delete_camera(self, camera_id: int) -> bool:
        """Delete a camera (soft delete)."""
        if camera_id not in self.cameras:
            return False

        # Stop stream if running
        self.stop_camera_stream(camera_id)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE cameras SET is_active = 0, updated_at = CURRENT_TIMESTAMP 
                    WHERE camera_id = ?
                """, (camera_id,))
                conn.commit()
                
                # Remove from memory
                del self.cameras[camera_id]
                
                logger.info(f"Camera deleted: {camera_id}")
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Failed to delete camera {camera_id}: {e}")
            return False

    def start_camera_stream(self, camera_id: int) -> bool:
        """Start processing stream for a camera."""
        if camera_id not in self.cameras:
            logger.error(f"Camera {camera_id} not found")
            return False

        if camera_id in self.streams:
            logger.warning(f"Camera {camera_id} stream already running")
            return True

        camera = self.cameras[camera_id]
        stream = CameraStream(camera)
        
        if stream.start():
            self.streams[camera_id] = stream
            return True
        
        return False

    def stop_camera_stream(self, camera_id: int) -> bool:
        """Stop processing stream for a camera."""
        if camera_id not in self.streams:
            return True

        stream = self.streams[camera_id]
        stream.stop()
        del self.streams[camera_id]
        
        return True

    def get_camera_frame(self, camera_id: int) -> Optional[bytes]:
        """Get latest frame from a camera."""
        if camera_id not in self.cameras:
            return None
        
        return self.cameras[camera_id].last_frame

    def get_camera_stats(self, camera_id: int) -> Optional[Dict]:
        """Get statistics for a camera."""
        if camera_id not in self.cameras:
            return None
        
        return self.cameras[camera_id].stats

    def get_all_cameras(self) -> List[Dict]:
        """Get all cameras with their status."""
        return [camera.to_dict() for camera in self.cameras.values()]

    def get_active_streams(self) -> List[int]:
        """Get list of active camera stream IDs."""
        return list(self.streams.keys())

    def stop_all_streams(self):
        """Stop all camera streams."""
        for camera_id in list(self.streams.keys()):
            self.stop_camera_stream(camera_id)

    def save_camera_stats(self, camera_id: int):
        """Save current camera stats to database."""
        if camera_id not in self.cameras:
            return

        stats = self.cameras[camera_id].stats
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO camera_stats 
                    (camera_id, total_vehicles, avg_speed, overspeed_count, 
                     plates_detected, cars, trucks, buses, bikes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    camera_id, stats["total_vehicles"], stats["avg_speed"],
                    stats["overspeed_count"], stats["plates_detected"],
                    stats["cars"], stats["trucks"], stats["buses"], stats["bikes"]
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to save stats for camera {camera_id}: {e}")

    def get_camera_history(self, camera_id: int, hours: int = 24) -> List[Dict]:
        """Get historical stats for a camera."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM camera_stats 
                WHERE camera_id = ? AND recorded_at >= datetime('now', '-{} hours')
                ORDER BY recorded_at DESC
            """.format(hours), (camera_id,))
            
            history = []
            for row in cursor.fetchall():
                stat_id, camera_id, total_vehicles, avg_speed, overspeed_count, plates_detected, cars, trucks, buses, bikes, recorded_at = row
                history.append({
                    "stat_id": stat_id,
                    "camera_id": camera_id,
                    "total_vehicles": total_vehicles,
                    "avg_speed": avg_speed,
                    "overspeed_count": overspeed_count,
                    "plates_detected": plates_detected,
                    "cars": cars,
                    "trucks": trucks,
                    "buses": buses,
                    "bikes": bikes,
                    "recorded_at": recorded_at
                })
            
            return history