import requests
import json
import time
import sys

print('='*70)
print('CAMERA TEST WITH IMPROVED SETTINGS')
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

# 2. Wait 8 seconds for detection to run
print('\n2. Waiting 8 seconds for vehicle detection to run...')
for i in range(8):
    print(f'   [{i+1}/8]', end='\r')
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
        total_vehicles = stats_json.get('total_vehicles', 0)
        avg_speed = stats_json.get('avg_speed', 'N/A')
        overspeed = stats_json.get('overspeed_count', 0)
        plates = stats_json.get('plates_detected', 0)
        vehicle_types = stats_json.get('vehicle_type_counts', {})
        
        print(f'   - Total Vehicles: {total_vehicles}')
        print(f'   - Average Speed: {avg_speed}')
        print(f'   - Overspeed Count: {overspeed}')
        print(f'   - Plates Detected: {plates}')
        print(f'   - Vehicle Type Counts: {vehicle_types}')
    else:
        print(f'   Error: Received status code {stats_response.status_code}')
        print(f'   Response: {stats_response.text}')
        
except Exception as e:
    print(f'   Error retrieving stats: {str(e)}')
    sys.exit(1)

# 4. Check frame endpoint
print('\n6. Checking frame endpoint for JPEG data...')
try:
    frame_response = requests.get('http://localhost:8000/api/camera/frame')
    print(f'   Status Code: {frame_response.status_code}')
    print(f'   Content-Type: {frame_response.headers.get("Content-Type", "N/A")}')
    print(f'   Frame Size: {len(frame_response.content)} bytes')
    
    # Check if its valid JPEG data
    if frame_response.content[:2] == b'\xff\xd8':
        print('   ✓ Valid JPEG data detected (starts with JPEG magic bytes)')
    else:
        print('   ✗ Frame data does not appear to be valid JPEG')
        print(f'   First 20 bytes: {frame_response.content[:20]}')
        
except Exception as e:
    print(f'   Error retrieving frame: {str(e)}')

print('\n' + '='*70)
print('DETECTION STATUS:')
if 'stats_json' in locals():
    total_vehicles = stats_json.get('total_vehicles', 0)
    if total_vehicles > 0:
        print('✓ Vehicle detection is WORKING - vehicles detected!')
    else:
        print('⚠ No vehicles detected yet.')
        print('  This could mean:')
        print('  - The camera view does not contain any vehicles')
        print('  - The detection point needs adjustment')
        print('  - The detection model needs to be tuned')
print('='*70)
