import sys
import os
import io
from starlette.testclient import TestClient

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.main import app
from app.database import init_db, get_db_path

def test_full_application_flow():
    p = get_db_path()
    if os.path.exists(p):
        os.remove(p)
    init_db()
    client = TestClient(app)

    # 1. Register User 1 (Alice)
    res_reg1 = client.post("/api/auth/register", json={
        "username": "alice",
        "display_name": "Alice Johnson",
        "email": "alice@example.com",
        "password": "Password123!",
        "bio": "Full stack developer & open source enthusiast",
        "avatar_color": "#10b981"
    })
    assert res_reg1.status_code == 200, res_reg1.text
    data1 = res_reg1.json()
    assert data1["success"] is True
    assert data1["user"]["username"] == "alice"
    token1 = data1["token"]

    # 2. Register User 2 (Bob)
    res_reg2 = client.post("/api/auth/register", json={
        "username": "bob",
        "display_name": "Bob Smith",
        "email": "bob@example.com",
        "password": "Password123!",
        "bio": "Backend & DevOps engineer",
        "avatar_color": "#3b82f6"
    })
    assert res_reg2.status_code == 200, res_reg2.text
    data2 = res_reg2.json()
    token2 = data2["token"]

    # 3. Test Login
    res_login = client.post("/api/auth/login", json={
        "username": "alice",
        "password": "Password123!"
    })
    assert res_login.status_code == 200
    assert res_login.json()["user"]["display_name"] == "Alice Johnson"

    # 4. Check /api/auth/me
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}
    res_me = client.get("/api/auth/me", headers=headers1)
    assert res_me.status_code == 200
    assert res_me.json()["user"]["username"] == "alice"

    # 5. List Rooms
    res_rooms = client.get("/api/rooms", headers=headers1)
    assert res_rooms.status_code == 200
    rooms = res_rooms.json()["rooms"]
    assert len(rooms) >= 4

    # 6. Create custom room
    res_new_room = client.post("/api/rooms", headers=headers1, json={
        "name": "Design & UI/UX",
        "description": "Figma mockups and styling discussions"
    })
    assert res_new_room.status_code == 200
    new_room = res_new_room.json()["room"]
    assert "design" in new_room["id"]

    # 7. List Users
    res_users = client.get("/api/users", headers=headers1)
    assert res_users.status_code == 200
    users = res_users.json()["users"]
    assert any(u["username"] == "bob" for u in users)

    # 8. Initiate Direct Message between Alice and Bob
    bob_id = data2["user"]["id"]
    res_dm = client.post(f"/api/rooms/dm/{bob_id}", headers=headers1)
    assert res_dm.status_code == 200
    dm_room = res_dm.json()["room"]
    assert dm_room["is_direct"] == 1
    assert "dm_" in dm_room["id"]

    # 9. Test Multimedia File Upload
    file_bytes = b"Hello, this is a shared text document test for chat attachments."
    res_upload = client.post(
        "/api/upload",
        headers=headers1,
        files={"file": ("project_notes.txt", io.BytesIO(file_bytes), "text/plain")}
    )
    assert res_upload.status_code == 200
    upload_data = res_upload.json()
    assert upload_data["success"] is True
    assert upload_data["file_name"] == "project_notes.txt"
    assert "/uploads/" in upload_data["file_url"]

    # 10. Test WebSocket Real-Time Messaging & Presence
    with client.websocket_connect(f"/ws?token={token1}") as ws1:
        # User 1 connected, receives presence update
        pres1 = ws1.receive_json()
        assert pres1["type"] == "presence_update"
        online_ids = [u["id"] for u in pres1["online_users"]]
        assert data1["user"]["id"] in online_ids

        # Subscribe Alice to 'general'
        ws1.send_json({"type": "subscribe", "room_id": "general"})

        with client.websocket_connect(f"/ws?token={token2}") as ws2:
            # User 2 connected, both get presence update
            pres_ws2 = ws2.receive_json()
            assert pres_ws2["type"] == "presence_update"

            # Alice also receives updated presence
            pres_ws1_update = ws1.receive_json()
            assert pres_ws1_update["type"] == "presence_update"

            # Subscribe Bob to 'general'
            ws2.send_json({"type": "subscribe", "room_id": "general"})

            # Bob sends a message in 'general'
            ws2.send_json({
                "type": "message",
                "room_id": "general",
                "content": "Hey Alice! Real-time WebSockets are working smoothly!",
                "message_type": "text"
            })

            # Alice receives Bob's message
            msg_for_alice = ws1.receive_json()
            assert msg_for_alice["type"] == "new_message"
            assert msg_for_alice["message"]["content"] == "Hey Alice! Real-time WebSockets are working smoothly!"
            assert msg_for_alice["message"]["sender_username"] == "bob"

            # Bob also receives his message broadcast confirmation
            msg_for_bob = ws2.receive_json()
            assert msg_for_bob["type"] == "new_message"

            # Bob sends typing indicator
            ws2.send_json({
                "type": "typing",
                "room_id": "general",
                "is_typing": True
            })
            typing_event_alice = ws1.receive_json()
            assert typing_event_alice["type"] == "typing_indicator"
            assert typing_event_alice["sender_name"] == "Bob Smith"
            assert typing_event_alice["is_typing"] is True
            typing_event_bob = ws2.receive_json()

            # Alice sends an attachment message
            ws1.send_json({
                "type": "message",
                "room_id": "general",
                "content": "Awesome! Here are the project notes attachment.",
                "message_type": "file",
                "file_url": upload_data["file_url"],
                "file_name": upload_data["file_name"],
                "file_size": upload_data["file_size"]
            })

            # Alice receives broadcast confirmation
            ws1.receive_json()

            # Bob receives Alice's file message
            incoming_file_msg = ws2.receive_json()
            assert incoming_file_msg["type"] == "new_message"
            assert incoming_file_msg["message"]["file_name"] == "project_notes.txt"
            assert incoming_file_msg["message"]["sender_username"] == "alice"

    # 11. Verify Chat History from REST endpoint
    res_history = client.get("/api/rooms/general/messages", headers=headers1)
    assert res_history.status_code == 200
    history = res_history.json()["messages"]
    assert len(history) >= 2
    contents = [m["content"] for m in history]
    assert "Hey Alice! Real-time WebSockets are working smoothly!" in contents

    print("\n>>> ALL AUTOMATED BACKEND & WEBSOCKET TESTS PASSED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    test_full_application_flow()
