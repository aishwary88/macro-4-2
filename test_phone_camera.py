import requests
import time
import json
import os

print("=" * 70)
print("PHONE CAMERA CONNECTION TEST - CORRECT API FORMAT")
print("=" * 70)

# Test configuration
api_base = "http://localhost:8000"
phone_camera_url = "http://10.16.225.184:8080/video"

print(f"\nPhone Camera URL: {phone_camera_url}")
print(f"API Base: {api_base}")

# 1. STOP any running camera
print("\n" + "=" * 70)
print("1. STOPPING any running camera...")
print("=" * 70)
stop_url = f"{api_base}/api/camera/stop"
print(f"Request: POST to {stop_url}")
try:
    response = requests.post(stop_url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {str(e)}")

# 2. Wait 1 second
print("\n2. Waiting 1 second...")
time.sleep(1)
print("   Done.")

# 3. START the phone camera with query parameter
print("\n" + "=" * 70)
print("3. STARTING phone camera with camera_source as query parameter...")
print("=" * 70)
start_url = f"{api_base}/api/camera/start"
params = {"camera_source": phone_camera_url}
print(f"Request: POST to {start_url}")
print(f"Query Parameters: {params}")
try:
    response = requests.post(start_url, params=params)
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"Response Body: {response.text}")
    try:
        json_response = response.json()
        print(f"Response JSON: {json.dumps(json_response, indent=2)}")
    except:
        pass
except Exception as e:
    print(f"Error: {str(e)}")

# 4. Wait 3 seconds
print("\n4. Waiting 3 seconds...")
time.sleep(3)
print("   Done.")

# 5. Get camera stats
print("\n" + "=" * 70)
print("5. GETTING camera stats...")
print("=" * 70)
stats_url = f"{api_base}/api/camera/stats"
print(f"Request: GET to {stats_url}")
try:
    response = requests.get(stats_url)
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"Response Body: {response.text}")
    try:
        json_response = response.json()
        print(f"Response JSON: {json.dumps(json_response, indent=2)}")
        
        # Check if phone camera URL is in the response
        response_text = json.dumps(json_response)
        if "10.16" in response_text:
            print("✓ Phone camera URL (10.16.225.184) found in stats response!")
        else:
            print("✗ Phone camera URL (10.16.225.184) NOT found in stats response")
    except:
        pass
except Exception as e:
    print(f"Error: {str(e)}")

# 6. Get frame from camera
print("\n" + "=" * 70)
print("6. GETTING frame from camera...")
print("=" * 70)
frame_url = f"{api_base}/api/camera/frame"
print(f"Request: GET to {frame_url}")
try:
    response = requests.get(frame_url)
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"Response Content Length: {len(response.content)} bytes")
    if response.status_code == 200:
        if len(response.content) > 0:
            print("✓ Frame received successfully (got image data)")
            # Check for JPEG or PNG magic bytes
            content_start = response.content[:20]
            if response.content[:2] == b'\xff\xd8':
                print("  Image format: JPEG detected")
            elif response.content[:8] == b'\x89PNG\r\n\x1a\n':
                print("  Image format: PNG detected")
            else:
                print(f"  Image format: Unknown (first bytes: {response.content[:20].hex()})")
        else:
            print("✗ No data received")
    else:
        print(f"Error response: {response.text}")
except Exception as e:
    print(f"Error: {str(e)}")

# 7. Check app logs for phone camera URL
print("\n" + "=" * 70)
print("7. CHECKING app logs for phone camera URL (10.16)...")
print("=" * 70)
log_path = r"C:\vs code\macro-4-2\app.log"
if os.path.exists(log_path):
    with open(log_path, "r") as f:
        lines = f.readlines()
    
    print(f"Log file found: {log_path}")
    print(f"Total lines: {len(lines)}")
    
    # Look for recent entries with phone camera URL
    print("\nSearching for phone camera URL in last 100 log entries:")
    print("-" * 68)
    found_count = 0
    for line in lines[-100:]:
        if "10.16" in line or "camera_source" in line.lower():
            print(line.rstrip())
            found_count += 1
    
    if found_count == 0:
        print("   (No entries with phone camera URL found in last 100 lines)")
    else:
        print(f"   Found {found_count} entries with phone camera URL")
    
    print("-" * 68)
else:
    print(f"Log file not found: {log_path}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
