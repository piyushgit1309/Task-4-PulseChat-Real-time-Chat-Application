import json
import logging
from typing import Dict, Set, List
from fastapi import WebSocket

logger = logging.getLogger("connection_manager")

class ConnectionManager:
    def __init__(self):
        # user_id -> List[WebSocket]
        self.user_sockets: Dict[int, List[WebSocket]] = {}
        # websocket -> user_id
        self.socket_user: Dict[WebSocket, int] = {}
        # websocket -> Set[room_id]
        self.socket_rooms: Dict[WebSocket, Set[str]] = {}
        # user_id -> user dict (id, username, display_name, avatar_color)
        self.online_users: Dict[int, dict] = {}

    async def connect(self, websocket: WebSocket, user: dict):
        await websocket.accept()
        user_id = user["user_id"] if "user_id" in user else user["id"]
        
        if user_id not in self.user_sockets:
            self.user_sockets[user_id] = []
        self.user_sockets[user_id].append(websocket)
        
        self.socket_user[websocket] = user_id
        self.socket_rooms[websocket] = set()
        
        self.online_users[user_id] = {
            "id": user_id,
            "username": user["username"],
            "display_name": user["display_name"],
            "avatar_color": user.get("avatar_color", "#6366f1")
        }
        
        # Broadcast updated presence to all connected clients
        await self.broadcast_presence()

    async def disconnect(self, websocket: WebSocket):
        user_id = self.socket_user.pop(websocket, None)
        self.socket_rooms.pop(websocket, None)
        
        if user_id and user_id in self.user_sockets:
            if websocket in self.user_sockets[user_id]:
                self.user_sockets[user_id].remove(websocket)
            if not self.user_sockets[user_id]:
                del self.user_sockets[user_id]
                self.online_users.pop(user_id, None)
                # Broadcast updated presence
                await self.broadcast_presence()

    def subscribe(self, websocket: WebSocket, room_id: str):
        if websocket in self.socket_rooms:
            self.socket_rooms[websocket].add(room_id)

    def unsubscribe(self, websocket: WebSocket, room_id: str):
        if websocket in self.socket_rooms:
            self.socket_rooms[websocket].discard(room_id)

    async def broadcast_to_room(self, room_id: str, message: dict):
        """Send message to all sockets subscribed to this room, or direct message participants."""
        payload = json.dumps(message)
        
        # If it's a DM room: dm_{u1}_{u2}, ensure participants receive it even if not explicitly viewing the room
        if room_id.startswith("dm_"):
            parts = room_id.split("_")
            if len(parts) == 3:
                try:
                    u1, u2 = int(parts[1]), int(parts[2])
                    target_users = [u1, u2]
                    for uid in target_users:
                        for ws in self.user_sockets.get(uid, []):
                            try:
                                await ws.send_text(payload)
                            except Exception:
                                pass
                    return
                except ValueError:
                    pass

        # For normal public rooms
        for ws, rooms in self.socket_rooms.items():
            if room_id in rooms:
                try:
                    await ws.send_text(payload)
                except Exception:
                    pass

    async def send_personal_message(self, user_id: int, message: dict):
        payload = json.dumps(message)
        for ws in self.user_sockets.get(user_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    async def broadcast_presence(self):
        online_list = list(self.online_users.values())
        payload = json.dumps({
            "type": "presence_update",
            "online_users": online_list,
            "count": len(online_list)
        })
        for sockets in self.user_sockets.values():
            for ws in sockets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    pass

    async def broadcast_typing(self, room_id: str, sender_id: int, sender_name: str, is_typing: bool):
        payload = {
            "type": "typing_indicator",
            "room_id": room_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "is_typing": is_typing
        }
        await self.broadcast_to_room(room_id, payload)

manager = ConnectionManager()
