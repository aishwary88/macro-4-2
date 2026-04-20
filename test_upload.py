import requests
import time
import os
from pathlib import Path

# First, let's create a test video (5 seconds, MP4)
print('Creating test video (5 seconds, MP4)...')

try:
    # Try to import moviepy first
    from moviepy.editor import ColorClip, concatenate_videoclips
    
    # Create a simple 5-second video
    test_video_path = 'test_video_5sec.mp4'
    
    # Create a simple colored clip (blue background, 1280x720, 5 seconds)
    clip = ColorClip(size=(1280, 720), color=(0, 100, 255), duration=5)
    clip.write_videofile(test_video_path, fps=24, verbose=False, logger=None)
    
    print(f'Test video created: {test_video_path}')
    print(f'  File size: {os.path.getsize(test_video_path)} bytes')
except ImportError:
    print('MoviePy not available, trying alternative method...')
    # Try opencv-python
    try:
        import cv2
        import numpy as np
        
        test_video_path = 'test_video_5sec.mp4'
        
        # Video properties
        width, height = 1280, 720
        fps = 24
        duration_seconds = 5
        total_frames = fps * duration_seconds
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(test_video_path, fourcc, fps, (width, height))
        
        # Generate frames with a simple pattern (blue background)
        for frame_idx in range(total_frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :] = [255, 100, 0]  # BGR format - cyan color
            
            # Add text showing frame number
            cv2.putText(frame, f'Frame {frame_idx+1}/{total_frames}', (50, 100), 
                       cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 2)
            
            out.write(frame)
        
        out.release()
        print(f'Test video created with OpenCV: {test_video_path}')
        print(f'  File size: {os.path.getsize(test_video_path)} bytes')
        
    except ImportError:
        print('ERROR: Neither moviepy nor opencv-python is available')
        exit(1)

# Upload the video
print('\nUploading video to http://localhost:8000/api/upload...')

try:
    with open(test_video_path, 'rb') as video_file:
        files = {'file': video_file}
        response = requests.post('http://localhost:8000/api/upload', files=files, timeout=30)
    
    print(f'Upload Status Code: {response.status_code}')
    print(f'Upload Response: {response.text}')
    
    if response.status_code == 200:
        try:
            upload_response = response.json()
            print(f'Upload Response (JSON): {upload_response}')
        except:
            pass
except Exception as e:
    print(f'Upload Error: {str(e)}')
    exit(1)

# Wait 60 seconds for processing
print('\nWaiting 60 seconds for video processing...')
for i in range(60):
    if i % 10 == 0:
        print(f'  {i+1}/60 seconds...')
    time.sleep(1)
print('  Processing complete!')

# Check the final status at /api/status/5
print('\nChecking final status at http://localhost:8000/api/status/5...')

try:
    response = requests.get('http://localhost:8000/api/status/5', timeout=10)
    
    print(f'Status Code: {response.status_code}')
    print(f'Status Response: {response.text}')
    
    try:
        status_response = response.json()
        print(f'\nStatus Response (JSON): {status_response}')
        
        # Extract relevant information
        if isinstance(status_response, dict):
            print(f'\nFinal Status Summary:')
            print(f'  Status: {status_response.get("status", "N/A")}')
            print(f'  Progress: {status_response.get("progress", "N/A")}')
            print(f'  Output File: {status_response.get("output_file", "N/A")}')
            print(f'  Error: {status_response.get("error", "None")}')
            
            # Check if output file exists
            output_file = status_response.get('output_file', '')
            if output_file and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f'\nOutput file exists: {output_file}')
                print(f'  File size: {file_size} bytes')
                if file_size > 1024:
                    print(f'  Size check: PASS (greater than 1KB)')
                else:
                    print(f'  Size check: FAIL (less than 1KB)')
            else:
                print(f'\nOutput file not found or not specified')
                
    except Exception as json_err:
        print(f'Could not parse JSON response: {json_err}')
        
except Exception as e:
    print(f'Status Check Error: {str(e)}')

print('\nTest completed!')
