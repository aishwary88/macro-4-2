"""
External API integrations for Traffic Speed Analyzer.
Includes Google Maps, Weather API, and Vehicle Registration Database.
"""

import requests
import json
from typing import Dict, Optional, List
from datetime import datetime
import sqlite3

from modules.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleMapsIntegration:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api"

    def get_location_info(self, latitude: float, longitude: float) -> Optional[Dict]:
        """Get location information from coordinates."""
        if not self.api_key:
            return None

        try:
            url = f"{self.base_url}/geocode/json"
            params = {
                'latlng': f"{latitude},{longitude}",
                'key': self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] == 'OK' and data['results']:
                result = data['results'][0]
                return {
                    'formatted_address': result.get('formatted_address'),
                    'place_id': result.get('place_id'),
                    'types': result.get('types', []),
                    'components': {
                        comp['types'][0]: comp['long_name'] 
                        for comp in result.get('address_components', [])
                    }
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Google Maps API error: {e}")
            return None

    def get_traffic_data(self, origin: str, destination: str) -> Optional[Dict]:
        """Get traffic data between two points."""
        if not self.api_key:
            return None

        try:
            url = f"{self.base_url}/directions/json"
            params = {
                'origin': origin,
                'destination': destination,
                'departure_time': 'now',
                'traffic_model': 'best_guess',
                'key': self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] == 'OK' and data['routes']:
                route = data['routes'][0]
                leg = route['legs'][0]
                
                return {
                    'distance': leg['distance']['text'],
                    'duration': leg['duration']['text'],
                    'duration_in_traffic': leg.get('duration_in_traffic', {}).get('text'),
                    'traffic_speed_entry': leg.get('traffic_speed_entry', []),
                    'via_waypoint': route.get('via_waypoint', [])
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Google Maps traffic API error: {e}")
            return None


class WeatherIntegration:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5"

    def get_current_weather(self, latitude: float, longitude: float) -> Optional[Dict]:
        """Get current weather conditions."""
        if not self.api_key:
            return None

        try:
            url = f"{self.base_url}/weather"
            params = {
                'lat': latitude,
                'lon': longitude,
                'appid': self.api_key,
                'units': 'metric'
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if response.status_code == 200:
                return {
                    'temperature': data['main']['temp'],
                    'humidity': data['main']['humidity'],
                    'pressure': data['main']['pressure'],
                    'visibility': data.get('visibility', 0) / 1000,  # Convert to km
                    'weather_main': data['weather'][0]['main'],
                    'weather_description': data['weather'][0]['description'],
                    'wind_speed': data['wind']['speed'],
                    'wind_direction': data['wind'].get('deg', 0),
                    'clouds': data['clouds']['all'],
                    'timestamp': datetime.now().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Weather API error: {e}")
            return None

    def get_weather_forecast(self, latitude: float, longitude: float, days: int = 5) -> Optional[List[Dict]]:
        """Get weather forecast."""
        if not self.api_key:
            return None

        try:
            url = f"{self.base_url}/forecast"
            params = {
                'lat': latitude,
                'lon': longitude,
                'appid': self.api_key,
                'units': 'metric',
                'cnt': days * 8  # 8 forecasts per day (3-hour intervals)
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if response.status_code == 200:
                forecasts = []
                for item in data['list']:
                    forecasts.append({
                        'datetime': item['dt_txt'],
                        'temperature': item['main']['temp'],
                        'humidity': item['main']['humidity'],
                        'weather_main': item['weather'][0]['main'],
                        'weather_description': item['weather'][0]['description'],
                        'wind_speed': item['wind']['speed'],
                        'visibility': item.get('visibility', 0) / 1000,
                        'precipitation': item.get('rain', {}).get('3h', 0) + item.get('snow', {}).get('3h', 0)
                    })
                
                return forecasts
            
            return None
            
        except Exception as e:
            logger.error(f"Weather forecast API error: {e}")
            return None


class VehicleRegistrationIntegration:
    def __init__(self, api_endpoint: str = "", api_key: str = ""):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.init_cache_table()

    def init_cache_table(self):
        """Initialize vehicle registration cache table."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vehicle_registration_cache (
                        plate_number TEXT PRIMARY KEY,
                        owner_name TEXT,
                        vehicle_make TEXT,
                        vehicle_model TEXT,
                        vehicle_year INTEGER,
                        vehicle_color TEXT,
                        registration_date TEXT,
                        expiry_date TEXT,
                        vehicle_type TEXT,
                        engine_number TEXT,
                        chassis_number TEXT,
                        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_valid BOOLEAN DEFAULT 1
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize vehicle registration cache: {e}")

    def lookup_vehicle(self, plate_number: str, use_cache: bool = True) -> Optional[Dict]:
        """Lookup vehicle registration information."""
        # Check cache first
        if use_cache:
            cached_data = self._get_cached_data(plate_number)
            if cached_data:
                return cached_data

        # Make API call if not in cache or cache disabled
        if self.api_endpoint and self.api_key:
            api_data = self._fetch_from_api(plate_number)
            if api_data:
                self._cache_data(plate_number, api_data)
                return api_data

        return None

    def _get_cached_data(self, plate_number: str) -> Optional[Dict]:
        """Get cached vehicle registration data."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM vehicle_registration_cache 
                    WHERE plate_number = ? AND is_valid = 1
                    AND datetime(cached_at, '+30 days') > datetime('now')
                """, (plate_number,))
                
                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached vehicle data: {e}")
            return None

    def _fetch_from_api(self, plate_number: str) -> Optional[Dict]:
        """Fetch vehicle data from external API."""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            params = {'plate_number': plate_number}
            
            response = requests.get(
                self.api_endpoint, 
                params=params, 
                headers=headers, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Standardize the response format
                return {
                    'plate_number': plate_number,
                    'owner_name': data.get('owner_name'),
                    'vehicle_make': data.get('make'),
                    'vehicle_model': data.get('model'),
                    'vehicle_year': data.get('year'),
                    'vehicle_color': data.get('color'),
                    'registration_date': data.get('registration_date'),
                    'expiry_date': data.get('expiry_date'),
                    'vehicle_type': data.get('vehicle_type'),
                    'engine_number': data.get('engine_number'),
                    'chassis_number': data.get('chassis_number'),
                    'is_valid': True
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Vehicle registration API error: {e}")
            return None

    def _cache_data(self, plate_number: str, data: Dict):
        """Cache vehicle registration data."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO vehicle_registration_cache 
                    (plate_number, owner_name, vehicle_make, vehicle_model, vehicle_year,
                     vehicle_color, registration_date, expiry_date, vehicle_type,
                     engine_number, chassis_number, cached_at, is_valid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """, (
                    plate_number, data.get('owner_name'), data.get('vehicle_make'),
                    data.get('vehicle_model'), data.get('vehicle_year'), data.get('vehicle_color'),
                    data.get('registration_date'), data.get('expiry_date'), data.get('vehicle_type'),
                    data.get('engine_number'), data.get('chassis_number'), data.get('is_valid', True)
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error caching vehicle data: {e}")


class TrafficLightIntegration:
    def __init__(self, controller_endpoint: str = "", api_key: str = ""):
        self.controller_endpoint = controller_endpoint
        self.api_key = api_key

    def get_traffic_light_status(self, intersection_id: str) -> Optional[Dict]:
        """Get current traffic light status."""
        if not self.controller_endpoint:
            return None

        try:
            url = f"{self.controller_endpoint}/status/{intersection_id}"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'intersection_id': intersection_id,
                    'current_phase': data.get('current_phase'),
                    'time_remaining': data.get('time_remaining'),
                    'next_phase': data.get('next_phase'),
                    'cycle_length': data.get('cycle_length'),
                    'timestamp': datetime.now().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Traffic light API error: {e}")
            return None

    def request_priority(self, intersection_id: str, direction: str, priority_level: int = 1) -> bool:
        """Request traffic light priority for emergency vehicles."""
        if not self.controller_endpoint:
            return False

        try:
            url = f"{self.controller_endpoint}/priority/{intersection_id}"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'direction': direction,
                'priority_level': priority_level,
                'requested_by': 'traffic_speed_analyzer',
                'timestamp': datetime.now().isoformat()
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            return response.status_code in [200, 201, 202]
            
        except Exception as e:
            logger.error(f"Traffic light priority request error: {e}")
            return False


class ExternalIntegrationManager:
    def __init__(self):
        self.google_maps = GoogleMapsIntegration()
        self.weather = WeatherIntegration()
        self.vehicle_registry = VehicleRegistrationIntegration()
        self.traffic_lights = TrafficLightIntegration()
        self.load_configuration()

    def load_configuration(self):
        """Load integration configuration from database."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                
                # Create config table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS integration_config (
                        service_name TEXT PRIMARY KEY,
                        config_json TEXT,
                        is_enabled BOOLEAN DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("SELECT service_name, config_json, is_enabled FROM integration_config")
                
                for service_name, config_json, is_enabled in cursor.fetchall():
                    if not is_enabled:
                        continue
                        
                    config = json.loads(config_json) if config_json else {}
                    
                    if service_name == "google_maps":
                        self.google_maps.api_key = config.get("api_key", "")
                    elif service_name == "weather":
                        self.weather.api_key = config.get("api_key", "")
                    elif service_name == "vehicle_registry":
                        self.vehicle_registry.api_endpoint = config.get("api_endpoint", "")
                        self.vehicle_registry.api_key = config.get("api_key", "")
                    elif service_name == "traffic_lights":
                        self.traffic_lights.controller_endpoint = config.get("controller_endpoint", "")
                        self.traffic_lights.api_key = config.get("api_key", "")
                
        except Exception as e:
            logger.error(f"Failed to load integration configuration: {e}")

    def save_configuration(self, service_name: str, config: Dict, is_enabled: bool = True):
        """Save integration configuration."""
        try:
            with sqlite3.connect("traffic_analyzer.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO integration_config 
                    (service_name, config_json, is_enabled, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (service_name, json.dumps(config), is_enabled))
                conn.commit()
                
                # Update runtime configuration
                if service_name == "google_maps" and is_enabled:
                    self.google_maps.api_key = config.get("api_key", "")
                elif service_name == "weather" and is_enabled:
                    self.weather.api_key = config.get("api_key", "")
                elif service_name == "vehicle_registry" and is_enabled:
                    self.vehicle_registry.api_endpoint = config.get("api_endpoint", "")
                    self.vehicle_registry.api_key = config.get("api_key", "")
                elif service_name == "traffic_lights" and is_enabled:
                    self.traffic_lights.controller_endpoint = config.get("controller_endpoint", "")
                    self.traffic_lights.api_key = config.get("api_key", "")
                
                logger.info(f"Configuration saved for {service_name}")
                
        except Exception as e:
            logger.error(f"Failed to save configuration for {service_name}: {e}")

    def test_integration(self, service_name: str) -> Dict:
        """Test external integration connectivity."""
        try:
            if service_name == "google_maps":
                # Test with a known location (New York City)
                result = self.google_maps.get_location_info(40.7128, -74.0060)
                return {
                    "service": service_name,
                    "status": "success" if result else "failed",
                    "message": "Google Maps API is working" if result else "Google Maps API failed",
                    "data": result
                }
            
            elif service_name == "weather":
                # Test with a known location
                result = self.weather.get_current_weather(40.7128, -74.0060)
                return {
                    "service": service_name,
                    "status": "success" if result else "failed",
                    "message": "Weather API is working" if result else "Weather API failed",
                    "data": result
                }
            
            elif service_name == "vehicle_registry":
                # Test with a dummy plate number
                result = self.vehicle_registry.lookup_vehicle("TEST123", use_cache=False)
                return {
                    "service": service_name,
                    "status": "success" if result else "failed",
                    "message": "Vehicle Registry API is working" if result else "Vehicle Registry API failed or no data",
                    "data": result
                }
            
            elif service_name == "traffic_lights":
                # Test with a dummy intersection
                result = self.traffic_lights.get_traffic_light_status("TEST_INTERSECTION")
                return {
                    "service": service_name,
                    "status": "success" if result else "failed",
                    "message": "Traffic Light API is working" if result else "Traffic Light API failed",
                    "data": result
                }
            
            else:
                return {
                    "service": service_name,
                    "status": "failed",
                    "message": f"Unknown service: {service_name}",
                    "data": None
                }
                
        except Exception as e:
            return {
                "service": service_name,
                "status": "error",
                "message": str(e),
                "data": None
            }

    def get_enriched_vehicle_data(self, plate_number: str, location: Dict = None) -> Dict:
        """Get enriched vehicle data with external information."""
        enriched_data = {"plate_number": plate_number}
        
        # Get vehicle registration data
        vehicle_info = self.vehicle_registry.lookup_vehicle(plate_number)
        if vehicle_info:
            enriched_data.update(vehicle_info)
        
        # Get location information if coordinates provided
        if location and "latitude" in location and "longitude" in location:
            location_info = self.google_maps.get_location_info(
                location["latitude"], location["longitude"]
            )
            if location_info:
                enriched_data["location_info"] = location_info
            
            # Get weather information
            weather_info = self.weather.get_current_weather(
                location["latitude"], location["longitude"]
            )
            if weather_info:
                enriched_data["weather_info"] = weather_info
        
        return enriched_data