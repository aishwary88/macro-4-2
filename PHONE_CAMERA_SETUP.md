# 📱 Phone Camera Setup Guide - SentrySpeed Traffic Analyzer

## **Quick Start: Connect Your Phone Camera**

### **Step 1: Install IP Webcam App (Android/iPhone)**

**Android:**
- Download **IP Webcam Pro** from Google Play Store
- Or download **DailyRoads Voyager**
- Or download **Iriun WebCam**

**iPhone:**
- Download **Iriun WebCam** from App Store
- Or try **Reincubate Codeshot**

---

### **Step 2: Start the App on Your Phone**

1. Open the IP Camera app on your phone
2. Grant camera permissions when prompted
3. Tap **"Start Server"** or **"Start Broadcasting"**
4. **Note down the IP address and port shown** (example: `192.168.1.100:8080`)

⚠️ **IMPORTANT:** Your phone and laptop MUST be on the **SAME WiFi NETWORK**

---

### **Step 3: Find the Correct Stream URL**

The app will display something like:
```
http://192.168.x.x:8080
```

For OpenCV/Python, you need the full MJPEG stream endpoint. Common formats:

| App | Stream Endpoint |
|-----|-----------------|
| **IP Webcam Pro** | `http://192.168.x.x:8080/video` |
| **IP Webcam Pro** | `http://192.168.x.x:8080/video_feed.mjpeg` |
| **DailyRoads Voyager** | `http://192.168.x.x:8080/mjpegfeed` |
| **Iriun WebCam** | Check app settings for stream URL |

**Test your URL before using:**
Open this in your laptop browser:
```
http://192.168.x.x:8080/video
```
If you see video, you have the right URL! ✓

---

### **Step 4: Enter URL in Dashboard**

1. Go to http://localhost:8000/ on your laptop
2. Click **"Live Camera"** tab
3. In **"Camera Source"** field, paste the URL:
   ```
   http://192.168.x.x:8080/video
   ```
4. Click **"▶ Start Camera"** button
5. Live video appears! 🎥

---

## **Troubleshooting**

### ❌ **"Camera stream started but no frames appear"**
- **Solution 1:** Verify URL works in browser first
- **Solution 2:** Try different endpoint paths (see table above)
- **Solution 3:** Check both devices are on same WiFi

### ❌ **"Connection refused" error**
- **Solution 1:** Make sure IP Webcam app is actually running on phone
- **Solution 2:** Check IP address is correct (look in app display)
- **Solution 3:** Disable phone's firewall temporarily
- **Solution 4:** Try disabling WiFi sleep on phone

### ❌ **"No vehicles detected"**
- This is normal if camera shows no traffic
- Point camera at actual road/traffic area
- Detection threshold can be adjusted in `.env` file

---

## **Testing the Connection**

Use the dashboard to verify connection:

1. **Camera Source Field:** Shows connected URL
2. **Live Feed:** Should display real-time video
3. **Dashboard Stats:** Updates as vehicles pass by:
   - Total Vehicles
   - Average Speed
   - Overspeed Count
   - Plates Detected

---

## **Advanced: Manual URL Testing**

To find the correct endpoint manually:

```python
import requests

base_url = "http://192.168.x.x:8080"
endpoints = ['/video', '/video_feed', '/mjpegfeed', '/stream']

for ep in endpoints:
    try:
        r = requests.head(base_url + ep, timeout=2)
        if r.status_code == 200:
            print(f"✓ Working: {base_url}{ep}")
    except:
        pass
```

---

## **Real-World Example**

**Your IP Webcam Pro shows:**
```
IPv4: http://10.16.225.184:8080
```

**You would use:**
```
http://10.16.225.184:8080/video
```

Or if that doesn't work:
```
http://10.16.225.184:8080/video_feed.mjpeg
```

---

## **Features Once Connected**

✅ **Real-time vehicle detection** - YOLOv8 detects cars, trucks, buses, bikes
✅ **Speed calculation** - Measures vehicle speed across ROI lines  
✅ **License plate recognition** - Captures and reads plate numbers
✅ **Dashboard metrics** - Live analytics and statistics
✅ **Overspeed detection** - Flags vehicles exceeding speed limit
✅ **Vehicle classification** - Determines vehicle type

---

## **Performance Tips**

- **Laptop Camera (index 0):** Fast, low lag
- **Phone Camera (URL):** May have 1-2 second lag depending on WiFi
- **Lower FPS:** If laggy, reduce `CAMERA_FPS` in `.env` (default: 60)
- **Reduce Confidence:** Lower `DETECTION_CONFIDENCE` to catch more vehicles

Adjust in `.env`:
```
CAMERA_FPS=30
DETECTION_CONFIDENCE=0.3
```

Then restart the server.

---

## **Need Help?**

1. Verify phone and laptop on **same WiFi** network
2. Check app is actually running on phone
3. Test URL in browser first (`http://10.16.x.x:8080/...`)
4. Check server logs: `tail logs/app.log`
5. Try different endpoint paths

Good luck! 🚗📱
