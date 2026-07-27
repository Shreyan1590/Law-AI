# Indian Constitution Legal Assistant — Mobile App (Flutter)

This is the mobile application frontend for the Indian Constitution Legal Assistant, built using Flutter (Dart). It is a thin-client chat application that communicates with our FastAPI backend to provide grounded legal answers with constitutional article citations.

---

## 1. Setup Instructions for Beginners

### Installing Flutter & Android Studio on Windows

If you have never built a mobile app before, follow these steps to set up your environment:

1. **Install Git:**
   - Download and install Git from [git-scm.com](https://git-scm.com/).

2. **Download Flutter SDK:**
   - Go to [flutter.dev](https://docs.flutter.dev/get-started/install/windows/mobile) and download the latest stable Flutter bundle.
   - Extract the zip file to a path without spaces (e.g., `C:\src\flutter`).
   - Add `C:\src\flutter\bin` to your system's **PATH** environment variable.

3. **Install Android Studio:**
   - Download and install Android Studio from [developer.android.com/studio](https://developer.android.com/studio).
   - During setup, install the **Android SDK**, **Android SDK Command-line Tools**, and **Android Virtual Device (Emulator)**.
   - Open Android Studio, go to **SDK Manager** > **SDK Tools** tab, check **Android SDK Command-line Tools (latest)**, and click **Apply** to install.

4. **Agree to Android Licenses:**
   - Open your PowerShell/Command Prompt and run:
     ```bash
     flutter doctor --android-licenses
     ```
     *Press `y` to accept every license prompt.*

5. **Verify Installation:**
   - Run `flutter doctor` in your terminal to ensure everything is set up. You should see checkmarks next to Flutter, Android toolchain, and Android Studio.

---

## 2. Running the App Locally

### Step A: Start the Backend Server
Make sure your FastAPI backend is running locally on port `8000`:
```bash
# In f:\Law AI\backend\
.venv\Scripts\python.exe api\main.py
```

### Step B: Run an Emulator/Phone
1. Open Android Studio.
2. Go to **Device Manager** and start your Android Emulator (Virtual Device).
3. Alternatively, connect a physical Android phone to your PC via USB and enable **USB Debugging** in Developer Options.

### Step C: Configure Endpoint Address
If you are running the backend locally:
- **Android Emulator:** Build/run with `--dart-define=BACKEND_URL=http://10.0.2.2:8000`, which redirects emulator traffic to your local computer's port `8000` automatically.
- **Physical Device:** Build/run with `--dart-define=BACKEND_URL=http://YOUR_COMPUTER_LAN_IP:8000` (for example, `http://192.168.1.50:8000`). Ensure your phone and computer are on the same Wi-Fi network.
- **Deployed Backend:** Build/run with your public Render URL. If you do not pass a value, the app defaults to `https://arasamaippu-ai-backend.onrender.com`.

### Step D: Launch the App
In your terminal, navigate to the `mobile_app` folder and run:
```bash
cd mobile_app
flutter run
```
*Select your active device/emulator from the list to launch the app.*

### Release APK with Backend URL Packed In

Use `--dart-define` so the backend URL is compiled directly into the release APK:

```bash
flutter build apk --release --dart-define=BACKEND_URL=https://arasamaippu-ai-backend.onrender.com
```

---

## ⚠️ Things to Know Before Publishing

- **Render Free Tier Sleep (Cold Start):**
  When your backend is hosted on Render's free tier, the first request sent by the phone after 15 minutes of inactivity will trigger a boot-up sequence. The app shows a **"Searching constitutional text..."** spinner, and the API client is configured with a **45-second timeout** to ensure it waits for the server to wake up without failing immediately.
- **Google Play Store Publisher Fee:**
  To publish your app on the Google Play Store, you must register for a Google Play Developer Account. Google charges a **one-time $25 USD developer registration fee**. There are no recurring fees for publishing free apps.
- **India's DPDP Act 2023 Compliance:**
  If you launch this commercially in India, you must comply with the Digital Personal Data Protection Act 2023. You will need to add a **Privacy Policy** to the app, explain what user data is processed (even though we do not log PII, you must specify this clearly), and add consent checkmarks if you expand features to collect personal information (like email or phone number).
