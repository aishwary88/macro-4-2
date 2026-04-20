import requests
import time

print('=' * 60)
print('CAMERA FRAME TEST')
print('=' * 60)

# 1. Start the camera
print('\n1. Starting camera...')
try:
    start_response = requests.post('http://localhost:8000/api/camera/start')
    print(f'   POST /api/camera/start')
    print(f'   Status Code: {start_response.status_code}')
    print(f'   Response: {start_response.text}')
except Exception as e:
    print(f'   Error: {str(e)}')

# 2. Wait 2 seconds
print('\n2. Waiting 2 seconds...')
time.sleep(2)
print('   Wait complete.')

# 3. Get a single frame
print('\n3. Getting single frame from /api/camera/frame...')
try:
    frame_response = requests.get('http://localhost:8000/api/camera/frame')
    print(f'   GET /api/camera/frame')
    print(f'   Status Code: {frame_response.status_code}')
    print(f'   Response Length: {len(frame_response.content)} bytes')
    content_type = frame_response.headers.get('Content-Type', 'Not specified')
    print(f'   Content-Type: {content_type}')
    
    # Check for JPEG magic bytes (FF D8 FF)
    if len(frame_response.content) >= 3:
        magic_bytes = frame_response.content[:3]
        print(f'   First 3 bytes (hex): {magic_bytes.hex().upper()}')
        
        if magic_bytes[0] == 0xFF and magic_bytes[1] == 0xD8 and magic_bytes[2] == 0xFF:
            print(f'   SUCCESS: Frame is valid JPEG image data (FF D8 FF magic bytes detected)')
        else:
            print(f'   ERROR: Invalid JPEG magic bytes (expected FF D8 FF)')
    else:
        print(f'   ERROR: Response too short to contain JPEG data')
        print(f'   Response preview: {frame_response.content[:100]}')
    
except Exception as e:
    print(f'   Error: {str(e)}')

print('\n' + '=' * 60)
