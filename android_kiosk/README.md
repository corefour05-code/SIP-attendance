# SIP Kiosk Terminal — Android USB Camera Client

This Android application turns any Android mobile phone or tablet into a standalone **Biometric Attendance Kiosk** using an external USB webcam connected via a USB-C OTG / Multiport connector.

It connects to your hosted server's `/api/scan` endpoint in real-time, displays face bounding boxes, and speaks out loud to welcome staff.

---

## Features
- **Direct USB OTG Support:** Uses the native Android USB Host API (`libausbc`) to stream from any standard USB webcam (UVC).
- **Fast Biometric Verification:** Grabs video frames every ~150–200ms and verifies faces against your hosted InsightFace server.
- **Live Verification HUD:** Displays staff name, Morning IN time, Evening OUT time, and daily shift duration.
- **Native Voice Greetings:** Uses Android Text-to-Speech to announce staff clock-in/out with an anti-repetition cooldown.
- **Configurable Server URL:** Tap the ⚙️ icon in the top right corner to enter or change your server URL anytime without rebuilding.
- **Always-On Display:** Screen is locked awake so the terminal doesn't sleep while waiting for staff.

---

## How to Build the APK in Android Studio (3 Simple Steps)

### Step 1: Open the Project
1. Download or install [Android Studio](https://developer.android.com/studio) (if you don't already have it).
2. Open Android Studio, click **File > Open**, and select the folder:
   ```
   D:\SIP\android_kiosk
   ```
3. Wait 1–2 minutes for Gradle to sync dependencies automatically.

### Step 2: Build the APK File
1. In the top menu bar, click:
   **Build > Build Bundle(s) / APK(s) > Build APK(s)**
2. Android Studio will compile the app. When done, a popup will appear in the bottom-right corner:
   > *APK(s) generated successfully.* -> Click **locate**.
3. You will find the file:
   `app-debug.apk` inside `android_kiosk/app/build/outputs/apk/debug/`.

---

## How to Install and Run on Your Mobile Phone

1. **Transfer the APK to your phone:**
   * Send `app-debug.apk` to your phone via WhatsApp, Google Drive, Bluetooth, or USB cable.
2. **Install:**
   * Tap on the file on your phone.
   * If prompted with *"For your security, your phone is not allowed to install unknown apps from this source"*, tap **Settings** and toggle **Allow from this source**.
   * Tap **Install**.
3. **Connect Hardware:**
   * Plug your multiport adapter into the phone.
   * Plug your USB webcam into the multiport adapter.
   * *(Optional but recommended)* Plug your phone charger into the multiport adapter's PD port so the webcam has full, stable 5V power.
   * *(For Oppo, Vivo, Realme, OnePlus phones)*: Ensure **OTG connection** is turned ON in your phone's Android Settings.
4. **Launch the App:**
   * Open **SIP Kiosk**.
   * When Android prompts: *"Allow SIP Kiosk to access USB camera?"*, check **"Always open"** and tap **OK**.
   * Tap the ⚙️ icon in the top right, enter your hosted server URL (e.g., `https://your-domain.onrender.com`), and tap **Save & Connect**.
   * Face the camera to test attendance!

---

## Architecture

```
[External USB Camera]
         │ (UVC over USB-C OTG)
         ▼
[Android SIP Kiosk App] ──(HTTP POST /api/scan)──► [Your Hosted Server]
         │                                                   │
         │◄────────(JSON: Face match & punch log)────────────┘
         ▼
[Face Bounding Boxes + Voice Announcement]
```

