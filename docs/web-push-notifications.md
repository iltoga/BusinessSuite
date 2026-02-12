# Web Push Notifications Implementation Guide

This document details the implementation of Web Push Notifications in the BusinessSuite application, utilizing **Django** (backend), **Angular** (frontend), and **Firebase Cloud Messaging (FCM)**.

It serves as a guide for developers setting up the environment and for AI agents to understand the architecture.

## 1. Architecture Overview

The system uses **Firebase Cloud Messaging (FCM) HTTP v1 API** for delivering push notifications to web browsers.

- **Frontend (Angular):** Uses the Firebase JS SDK (compat version) and a Service Worker (`firebase-messaging-sw.js`) to generate a registration token (VAPID) and handle incoming background messages.
- **Backend (Django):** Stores the registration tokens linked to authenticated users and uses `google-auth` + `requests` to send authenticated requests to the FCM v1 API.

## 2. Prerequisites & Firebase Setup

To enable push notifications, you must configure a Firebase project.

### Step 1: Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com/).
2. Click **Add project** and follow the prompts.

### Step 2: Register a Web App

1. In the Project Overview, click the **Web** icon (</>) to add a new app.
2. Register the app (e.g., "BusinessSuite Prod").
3. **Important:** Copy the `firebaseConfig` object displayed. You will need these values for your environment variables.
   - `apiKey`
   - `authDomain`
   - `projectId`
   - `storageBucket`
   - `messagingSenderId`
   - `appId`
   - `measurementId`

### Step 3: Generate VAPID Keys (Web Push Certificates)

1. Go to **Project Settings** > **Cloud Messaging** tab.
2. Scroll to **Web configuration**.
3. In the **Web Push certificates** section, click **Generate key pair**.
4. Copy the **Key pair** (this is your `FCM_VAPID_PUBLIC_KEY`). The private key is not explicitly needed by the frontend but is part of the key pair generation.

### Step 4: Generate Service Account (For Backend Sending)

1. Go to **Project Settings** > **Service accounts** tab.
2. Click **Generate new private key**.
3. This will download a JSON file.
4. **Security:** Place this file in a secure location on your server (e.g., inside the `backend/` directory, added to `.gitignore`).
5. Set the `GOOGLE_FCM_SERVICE_ACCOUNT_FILE` environment variable to point to this file (relative to `backend/`).

## 3. Configuration

### Backend Environment Variables (`.env`)

Add the following variables to your `backend/.env` file:

```dotenv
# Firebase Cloud Messaging (FCM) Configuration
# --------------------------------------------

# The path to the Service Account JSON file (relative to backend/ root)
# REQUIRED for sending notifications from Django
GOOGLE_FCM_SERVICE_ACCOUNT_FILE="firebase-service-account.json"

# VAPID Public Key (Generated in Step 3)
# REQUIRED for Frontend to request permission
FCM_VAPID_PUBLIC_KEY="<YOUR_VAPID_PUBLIC_KEY>"

# VAPID Private Key (Optional, depending on library usage, usually implied by Service Account)
FCM_VAPID_PRIVATE_KEY="<YOUR_VAPID_PRIVATE_KEY>"

# Web App Config (From Step 2) - Exposed to Angular
FCM_API_KEY="<apiKey>"
FCM_PROJECT_ID="<projectId>"
FCM_MESSAGING_SENDER_ID="<messagingSenderId>"
FCM_APP_ID="<appId>"
FCM_MEASUREMENT_ID="<measurementId>"
```

### Django Settings (`backend/business_suite/settings/base.py`)

The settings file loads these variables and exposes them to the frontend via the `/api/app-config/` endpoint (or similar injection mechanism).

### Frontend Configuration (`frontend/`)

The Angular app initializes Firebase using these settings.

1. **Service:** `frontend/src/app/core/services/push-notifications.service.ts`
   - Fetches config from `ConfigService`.
   - Registers `firebase-messaging-sw.js`.
   - Requests permission and gets the token.
   - Sends the token to `/api/push-notifications/register/`.

2. **Service Worker:** `frontend/public/firebase-messaging-sw.js`
   - This file must exist in the root of the serving directory.
   - It imports Firebase scripts and handles background messages.

## 4. Implementation Details

### API Endpoints

- **`POST /api/push-notifications/register/`**
  - **Payload:** `{"token": "...", "device_label": "...", "user_agent": "..."}`
  - **Action:** Creates or updates a `WebPushSubscription` for the current user.

- **`POST /api/push-notifications/unregister/`**
  - **Payload:** `{"token": "..."}`
  - **Action:** Marks the subscription as inactive.

- **`POST /api/push-notifications/test/`**
  - **Payload:** `{"title": "Test", "body": "Hello"}`
  - **Action:** Sends a test notification to _all_ active devices of the current user.

### Backend Services

- **`core.services.push_notifications.PushNotificationService`**: High-level service to send messages.
- **`core.services.push_notifications.FcmClient`**: Low-level client wrapping HTTP v1 API.

## 5. Usage

### How to Send a Notification (Code)

```python
from core.services.push_notifications import PushNotificationService

def notify_user(user, message):
    service = PushNotificationService()
    service.send_to_user(
        user=user,
        title="New Update",
        body=message,
        data={"type": "update", "id": "123"}, # Optional data payload
        link="/dashboard/updates/123"          # Optional click action
    )
```

### How to Send a Notification (Admin)

Superusers can send test notifications via the API:

1. **GET** `/api/push-notifications/users/`: List users and their subscription counts.
2. **POST** `/api/push-notifications/send-test/`: Send to a specific `user_id`.

## 6. Troubleshooting

1. **"Permission denied" in Console:**
   - Ensure the site is served over **HTTPS** (or `localhost`).
   - Check if the user has blocked notifications in browser settings.

2. **"Missing Config" Warning:**
   - Verify all `FCM_*` environment variables are set in the backend.
   - Ensure the frontend `ConfigService` is correctly loading these values.

3. **Notification not received (Background):**
   - Verify `firebase-messaging-sw.js` is loaded correctly in the Network tab.
   - Ensure the payload sent from backend contains the `notification` key (for auto-display) or you are handling `data` messages manually in the SW.

4. **401/403 Error from Backend Sending:**
   - Verify `GOOGLE_FCM_SERVICE_ACCOUNT_FILE` path is correct.
   - Ensure the Service Account has "Firebase Cloud Messaging API Admin" permissions.

## 7. Official References

- [Firebase: Set up a JavaScript client](https://firebase.google.com/docs/cloud-messaging/js/client)
- [Firebase: Migrate from legacy FCM APIs to HTTP v1](https://firebase.google.com/docs/cloud-messaging/migrate-v1)
