# Task-4-PulseChat-Real-time-Chat-Application
> **Full Stack Web Development Internship Task-04 Submission**

PulseChat is a modern, high-performance, full-stack real-time messaging application engineered with **WebSocket technology**, **FastAPI**, **SQLite**, and an intuitive **Glassmorphism UI/UX design**.

---

## 🎯 Task Objectives & Deliverables Met

| Task-04 Requirement | Status | Implementation Details |
| :--- | :---: | :--- |
| **WebSocket Real-Time Messaging** |  Completed | Bi-directional WebSocket server using FastAPI & Starlette WebSocket engine with auto-reconnection. |
| **User Account & Authentication** |  Completed | User registration, login, logout, avatar personalization, PBKDF2-HMAC-SHA256 password hashing, secure token sessions. |
| **Chat Rooms / Channels** |  Completed | Pre-seeded community channels (`#general`, `#tech-talk`, `#project-hub`, `#random`) + dynamic channel creation with title & topic. |
| **Private 1-on-1 Conversations** |  Completed | Direct messaging (DM) with canonical room routing between any pair of registered users. |
| **Persistent Chat History** |  Completed | SQLite database storing all messages with foreign keys, sender metadata, message types, and formatted timestamps. |
| **User Presence Indicators** |  Completed | Real-time online/offline badges (green indicator) and active participant count. |
| **Notifications** |  Completed | Dual-layer notifications: Synthetic in-app audio chimes (Web Audio API) + browser HTML5 Web Notifications + unread count badges. |
| **Multimedia File Sharing** |  Completed | File uploads for images (PNG/JPG/GIF/WebP with inline preview & lightbox), audio (MP3/WAV with inline player), and documents (with size badges & download cards). |
| **Typing Indicators** |  Completed | Broadcasted typing events with animated pulsing dots (`Alice is typing...`). |
| **User-Friendly UI/UX Design** |  Completed | Dark mode glassmorphic interface, responsive sidebar with mobile drawer, Lucide-style inline SVGs, and zero CDN dependencies. |

---

## 🏗️ Architecture & Technology Stack

- **Backend**: Python 3.11, FastAPI, Uvicorn ASGI server
- **Protocol**: WebSockets (RFC 6455) for instant messaging + REST APIs for auth and uploads
- **Database**: SQLite3 with relational foreign keys, cascade deletes, and indexing
- **Security**: PBKDF2-HMAC-SHA256 password hashing with unique salts, secure session tokens
- **Frontend**: Vanilla HTML5, modern CSS3 (Custom Properties, Flexbox, Grid, Glassmorphism, animations), Vanilla JavaScript (ES6+ async/await, WebSocket API, Web Audio API)
- **Zero External UI Dependencies**: No heavy node_modules build step required; runs directly out of the box!

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.8 or higher installed on your computer.

### 2. Installation
Open your terminal or command prompt inside the project folder:
```bash
pip install -r requirements.txt
```

### 3. Run the Application
Run the startup script:
```bash
python run.py
```
Or run directly with Uvicorn:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Access the Application
Open your web browser and navigate to:
```
http://localhost:8000
```

## Deploy to Vercel

1. Import the repository into Vercel and set the project **Root Directory** to `realtime-chat-app`.
2. Leave the framework and build settings on **Automatic**, then deploy. Vercel reads the FastAPI entrypoint from `pyproject.toml` and dependencies from `requirements.txt`.
3. For CLI deployment, run `vercel` from the `realtime-chat-app` directory.

Vercel supports Python FastAPI functions and WebSockets (currently in beta); enable Fluid Compute for WebSocket support. This project uses SQLite and local uploads for its simple local setup. On Vercel, both use temporary `/tmp` storage, which can be cleared and is not shared across function instances. For durable production use, replace SQLite with a hosted database, move uploads to object storage, and use shared pub/sub such as Redis for presence and cross-instance message broadcasts. WebSocket connections also close at the function's configured maximum duration, so clients must reconnect.

---

## 👤 Quick Demo Evaluator Accounts

For quick testing across multiple browser windows or incognito tabs:

| Account | Username | Password | Role |
| :--- | :--- | :--- | :--- |
| **Alice** | `alice` | `Password123!` | Frontend Lead |
| **Bob** | `bob` | `Password123!` | Backend Engineer |

*(You can also click **"Login as Alice"** or **"Login as Bob"** on the sign-in modal, or register any new custom user account with your choice of avatar color and bio).*

---

## 📂 Project Directory Structure

```
realtime-chat-app/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI backend: REST endpoints & WebSocket routing
│   ├── database.py           # SQLite connection, table schemas & query helpers
│   ├── auth.py               # PBKDF2 hashing, session management & auth dependencies
│   ├── connection_manager.py # WebSocket connection pool, presence & room broadcasting
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css     # Modern, responsive Glassmorphic UI/UX stylesheet
│   │   ├── js/
│   │   │   └── app.js        # Client state, WebSockets, audio chimes, notifications
│   │   └── index.html        # Single-page application markup & embedded SVG icons
│   └── uploads/              # Storage directory for shared multimedia files
├── requirements.txt          # Python dependencies
├── run.py                    # One-command application launcher
├── test_app.py               # Automated end-to-end integration & WebSocket test suite
└── README.md                 # Complete project documentation
```

---

## 🧪 Automated Testing

Run the included automated test suite to verify all endpoints, database queries, and WebSocket broadcasting:
```bash
python test_app.py
```
