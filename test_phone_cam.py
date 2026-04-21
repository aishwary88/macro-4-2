"""
Phone Camera Auto-Tester
Usage: python test_phone_cam.py 192.168.1.100:8080
"""
import cv2, sys, time, os

if len(sys.argv) < 2:
    print("Usage: python test_phone_cam.py <IP:PORT>")
    print("Example: python test_phone_cam.py 192.168.1.100:8080")
    sys.exit(1)

ip = sys.argv[1].strip()
if not ip.startswith("http"):
    ip = "http://" + ip

endpoints = [
    "/video",
    "/video_feed",
    "/video_feed.mjpeg",
    "/mjpegfeed",
    "/stream",
    "/shot.jpg",
    "/videofeed",
    "",
]

print(f"\nTesting: {ip}")
print("-"*50)

working = []
for ep in endpoints:
    url = ip + ep
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok = False
        for _ in range(20):
            ret, frame = cap.read()
            if ret and frame is not None:
                ok = True
                break
            time.sleep(0.1)
        cap.release()
        print(f"  {'OK  ' if ok else 'FAIL'} {url}")
        if ok:
            working.append(url)
    except Exception as e:
        print(f"  FAIL {url} ({e})")

print("-"*50)
if working:
    best = working[0]
    print(f"\nWorking URL: {best}")
    # Save a test frame
    cap = cv2.VideoCapture(best, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    for _ in range(30):
        ret, frame = cap.read()
        if ret and frame is not None:
            cv2.imwrite("phone_test_frame.jpg", frame)
            print(f"Frame saved: phone_test_frame.jpg ({frame.shape[1]}x{frame.shape[0]})")
            break
        time.sleep(0.1)
    cap.release()
    print(f"\nDashboard mein yeh URL use karo:\n  {best}")
else:
    print("\nKoi URL kaam nahi kiya.")
    print("Check: same WiFi? App running? IP correct?")
