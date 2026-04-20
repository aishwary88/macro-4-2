import requests
import json
import time
import sys

print('='*70)
print('CAMERA DETECTION AND STATS TEST')
print('='*70)

# 1. Start the camera
print('\n1. Starting camera with POST request...')
try:
    start_response = requests.post('http://localhost:8000/api/camera/start')
    print(f'   Status Code: {start_response.status_code}')
    print(f'   Response: {start_response.text}')
except Exception as e:
    print(f'   Error: {str(e)}')
    sys.exit(1)

# 2. Wait 5 seconds for vehicle detection
print('\n2. Waiting 5 seconds for vehicle detection to run...')
for i in range(5):
    print(f'   [{i+1}/5]', end='\r')
    time.sleep(1)
print('   Wait complete.     ')

# 3. Check stats endpoint
print('\n3. Retrieving camera statistics from /api/camera/stats...')
try:
    stats_response = requests.get('http://localhost:8000/api/camera/stats')
    print(f'   Status Code: {stats_response.status_code}')
    
    if stats_response.status_code == 200:
        stats_json = stats_response.json()
        
        print('\n4. Full Stats Response:')
        print('-' * 70)
        print(json.dumps(stats_json, indent=2))
        print('-' * 70)
        
        print('\n5. Stats Summary:')
        print(f'   - Total Vehicles: {stats_json.get("total_vehicles", "N/A")}')
        print(f'   - Average Speed: {stats_json.get("avg_speed", "N/A")}')
        print(f'   - Overspeed Count: {stats_json.get("overspeed_count", "N/A")}')
        print(f'   - Plates Detected: {stats_json.get("plates_detected", "N/A")}')
        print(f'   - Vehicle Type Counts: {stats_json.get("vehicle_type_counts", "N/A")}')
    else:
        print(f'   Error: Received status code {stats_response.status_code}')
        print(f'   Response: {stats_response.text}')
        
except Exception as e:
    print(f'   Error retrieving stats: {str(e)}')
    sys.exit(1)

print('\n' + '='*70)
print('Test complete.')
print('='*70)
