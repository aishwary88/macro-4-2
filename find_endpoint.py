import requests
import sys

base_url = 'http://10.16.225.184:8080'
endpoints = [
    '/video_feed.mjpeg',
    '/video_feed',
    '/mjpegfeed',
    '/stream',
    '/mjpeg',
    '/videostream.cgi',
    '/nphMotionJpeg',
    '/axis-cgi/mjpg/video.cgi',
    '',
]

print('=' * 70)
print('FINDING CORRECT IP WEBCAM STREAM ENDPOINT')
print('=' * 70)
print(f'\nBase URL: {base_url}')
print(f'Testing {len(endpoints)} common endpoints...\n')

found_working = []

for endpoint in endpoints:
    url = base_url + endpoint
    print(f'Testing: {endpoint if endpoint else "(root)":30s}', end=' ... ')
    try:
        response = requests.head(url, timeout=3, allow_redirects=False)
        content_type = response.headers.get('content-type', '')
        status = response.status_code
        
        is_stream = 'mjpeg' in content_type.lower() or 'video' in content_type.lower()
        
        print(f'Status: {status}', end=' ')
        
        if status == 200 and is_stream:
            print(f'✓ FOUND (Content-Type: {content_type})')
            found_working.append((endpoint or '(root)', url))
        elif status == 200:
            print(f'(Content-Type: {content_type})')
        else:
            print(f'(Status: {status})')
            
    except requests.Timeout:
        print('TIMEOUT (no response)')
    except Exception as e:
        print(f'ERROR: {str(e)[:30]}')

print('\n' + '=' * 70)
if found_working:
    print(f'\nFOUND {len(found_working)} WORKING ENDPOINT(S):')
    for name, url in found_working:
        print(f'  ✓ {url}')
        print(f'    Use this URL in the camera source field!')
else:
    print('\nNo working endpoints found.')
    print('Possible issues:')
    print('  - Phone camera app is not running')
    print('  - Phone and laptop are not on the same WiFi network')
    print('  - IP address or port is incorrect')
    print('  - Firewall is blocking the connection')
print('=' * 70)
