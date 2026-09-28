import os
import shutil
import uuid
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, UploadFile, File, Form, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from app.database import (
    init_db,
    create_user,
    get_user_by_username,
    get_user_by_email,
    get_user_by_id,
    get_all_users,
    create_room,
    get_rooms,
    get_room_by_id,
    join_room,
    get_or_create_dm_room,
    create_message,
    get_room_messages,
    delete_session
)
from app.auth import (
    hash_password,
    verify_password,
    create_user_session,
    get_current_user,
    get_current_user_from_token
)
from app.connection_manager import manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IS_VERCEL = os.environ.get("VERCEL") == "1"
UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.join("/tmp", "pulsechat-uploads") if IS_VERCEL else os.path.join(BASE_DIR, "uploads")
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Real-Time Chat Application", version="1.0.0")

# Initialize database tables on startup
@app.on_event("startup")
def on_startup():
    init_db()
    demo_accounts = [
        ("alice", "Alice Johnson", "alice@example.com", "#10b981", "Frontend Lead"),
        ("bob", "Bob Smith", "bob@example.com", "#3b82f6", "Backend Engineer")
    ]
    for username, display_name, email, avatar_color, bio in demo_accounts:
        if get_user_by_username(username) or get_user_by_email(email):
            continue
        password_hash, salt = hash_password("Password123!")
        create_user(
            username=username,
            display_name=display_name,
            email=email,
            password_hash=password_hash,
            salt=salt,
            avatar_color=avatar_color,
            bio=bio
        )

# Serve static files and uploaded files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if IS_VERCEL:
    @app.get("/uploads/{filename}")
    def serve_upload(filename: str):
        upload_path = os.path.join(UPLOAD_DIR, os.path.basename(filename))
        if not os.path.isfile(upload_path):
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(upload_path)
else:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# --- Pydantic Request Models ---
class RegisterRequest(BaseModel):
    username: str
    display_name: str
    email: str
    password: str
    bio: Optional[str] = ""
    avatar_color: Optional[str] = "#6366f1"

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateRoomRequest(BaseModel):
    name: str
    description: Optional[str] = ""

# --- HTTP Endpoints ---

@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)

@app.post("/api/auth/register")
def register(req: RegisterRequest, response: Response):
    username = req.username.strip()
    display_name = req.display_name.strip()
    email = req.email.strip().lower()
    
    if len(username) < 3 or len(username) > 30:
        raise HTTPException(status_code=400, detail="Username must be between 3 and 30 characters.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if not display_name:
        display_name = username
        
    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists. Please choose another.")
    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email is already registered. Please log in.")
        
    pwd_hash, salt = hash_password(req.password)
    user_id = create_user(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=pwd_hash,
        salt=salt,
        avatar_color=req.avatar_color or "#6366f1",
        bio=req.bio or ""
    )
    
    token = create_user_session(user_id)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=60*60*24*7, samesite="lax")
    
    user = get_user_by_id(user_id)
    return {
        "success": True,
        "token": token,
        "user": dict(user)
    }

@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    user_row = get_user_by_username(req.username.strip())
    if not user_row or not verify_password(req.password, user_row["salt"], user_row["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid username or password.")
        
    user_id = user_row["id"]
    token = create_user_session(user_id)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=60*60*24*7, samesite="lax")
    
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": user_row["username"],
            "display_name": user_row["display_name"],
            "email": user_row["email"],
            "avatar_color": user_row["avatar_color"],
            "bio": user_row["bio"]
        }
    }

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    response.delete_cookie("session_token")
    return {"success": True, "message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}

@app.get("/api/users")
def list_users(user: dict = Depends(get_current_user)):
    all_users = get_all_users()
    user_list = []
    for u in all_users:
        u_dict = dict(u)
        u_dict["is_online"] = u_dict["id"] in manager.online_users
        user_list.append(u_dict)
    return {"users": user_list}

@app.get("/api/rooms")
def list_rooms(user: dict = Depends(get_current_user)):
    rooms = get_rooms()
    return {"rooms": [dict(r) for r in rooms]}

@app.post("/api/rooms")
def make_room(req: CreateRoomRequest, user: dict = Depends(get_current_user)):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Room name cannot be empty.")
        
    # Generate clean room id slug
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    if not slug:
        slug = f"room-{uuid.uuid4().hex[:6]}"
    else:
        # Check uniqueness
        if get_room_by_id(slug):
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
            
    create_room(slug, name, req.description.strip(), is_direct=0, created_by=user["id"])
    new_room = get_room_by_id(slug)
    return {"success": True, "room": dict(new_room)}

@app.post("/api/rooms/dm/{target_user_id}")
def get_dm_conversation(target_user_id: int, user: dict = Depends(get_current_user)):
    if target_user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot initiate direct chat with yourself.")
    target_user = get_user_by_id(target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found.")
        
    dm_room = get_or_create_dm_room(user["id"], target_user_id)
    return {
        "success": True,
        "room": dict(dm_room),
        "target_user": dict(target_user)
    }

@app.get("/api/rooms/{room_id}/messages")
def get_messages(room_id: str, limit: int = 100, user: dict = Depends(get_current_user)):
    msgs = get_room_messages(room_id, limit=limit)
    return {"messages": [dict(m) for m in msgs]}

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    # Determine message type
    content_type = file.content_type or ""
    original_name = file.filename or "uploaded_file"
    
    msg_type = "file"
    if content_type.startswith("image/"):
        msg_type = "image"
    elif content_type.startswith("audio/"):
        msg_type = "audio"
    elif content_type.startswith("video/"):
        msg_type = "video"
        
    # Generate unique filename to prevent overwriting
    ext = os.path.splitext(original_name)[1]
    unique_name = f"{uuid.uuid4().hex[:12]}_{original_name}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)
    
    file_size = 0
    with open(save_path, "wb") as buffer:
        content = await file.read()
        file_size = len(content)
        buffer.write(content)
        
    file_url = f"/uploads/{unique_name}"
    
    return {
        "success": True,
        "file_url": file_url,
        "file_name": original_name,
        "file_size": file_size,
        "message_type": msg_type
    }

# --- WebSocket Real-Time Communication Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    # Try token from query param or cookies
    if not token:
        token = websocket.cookies.get("session_token")
        
    user = get_current_user_from_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await manager.connect(websocket, user)
    current_user_id = user["id"]
    current_username = user["username"]
    current_display_name = user["display_name"]
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "subscribe":
                room_id = data.get("room_id")
                if room_id:
                    manager.subscribe(websocket, room_id)
                    join_room(room_id, current_user_id)
                    
            elif msg_type == "unsubscribe":
                room_id = data.get("room_id")
                if room_id:
                    manager.unsubscribe(websocket, room_id)
                    
            elif msg_type == "message":
                room_id = data.get("room_id")
                content = data.get("content", "").strip()
                message_type = data.get("message_type", "text")
                file_url = data.get("file_url")
                file_name = data.get("file_name")
                file_size = data.get("file_size")
                recipient_id = data.get("recipient_id")
                
                if (content or file_url) and room_id:
                    saved_msg = create_message(
                        room_id=room_id,
                        sender_id=current_user_id,
                        content=content,
                        recipient_id=recipient_id,
                        message_type=message_type,
                        file_url=file_url,
                        file_name=file_name,
                        file_size=file_size
                    )
                    broadcast_payload = {
                        "type": "new_message",
                        "message": dict(saved_msg)
                    }
                    await manager.broadcast_to_room(room_id, broadcast_payload)
                    
            elif msg_type == "typing":
                room_id = data.get("room_id")
                is_typing = bool(data.get("is_typing", False))
                if room_id:
                    await manager.broadcast_typing(
                        room_id=room_id,
                        sender_id=current_user_id,
                        sender_name=current_display_name,
                        is_typing=is_typing
                    )
                    
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        await manager.disconnect(websocket)
