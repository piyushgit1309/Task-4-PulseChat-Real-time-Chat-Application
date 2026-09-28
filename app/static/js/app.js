/**
 * PulseChat - Full Stack Real-Time WebSocket Chat Application
 * Client Logic & State Management
 */

class PulseChatApp {
    constructor() {
        this.currentUser = null;
        this.token = localStorage.getItem("pulse_token") || null;
        this.currentRoom = "general";
        this.currentRoomName = "General Discussion";
        this.currentRoomDesc = "Welcome channel for all team members";
        this.isDirectMessage = false;
        this.directTargetUser = null;
        
        this.rooms = [];
        this.users = [];
        this.onlineUsers = new Set();
        this.unreadCounts = {}; // roomId -> count
        
        this.ws = null;
        this.wsReconnectInterval = 2000;
        this.typingTimeout = null;
        this.isTypingSent = false;
        
        this.soundEnabled = true;
        this.audioContext = null;
        
        this.pendingAttachment = null;
        
        this.init();
    }

    async init() {
        this.bindEvents();
        await this.checkAuth();
        this.setupAudio();
    }

    setupAudio() {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                this.audioContext = new AudioCtx();
            }
        } catch (e) {
            console.warn("AudioContext not supported", e);
        }
    }

    playNotificationSound() {
        if (!this.soundEnabled || !this.audioContext) return;
        try {
            if (this.audioContext.state === "suspended") {
                this.audioContext.resume();
            }
            const ctx = this.audioContext;
            const now = ctx.currentTime;
            
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            
            osc.type = "sine";
            osc.frequency.setValueAtTime(587.33, now); // D5
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.12); // A5
            
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            osc.start(now);
            osc.stop(now + 0.35);
        } catch (e) {
            console.error("Error playing chime:", e);
        }
    }

    requestBrowserNotification() {
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }
    }

    showDesktopNotification(sender, text) {
        if ("Notification" in window && Notification.permission === "granted" && document.hidden) {
            try {
                new Notification(`New message from ${sender}`, {
                    body: text,
                    icon: "/static/favicon.ico"
                });
            } catch (e) {}
        }
    }

    // --- Authentication ---
    async checkAuth() {
        if (!this.token) {
            this.showAuthModal(true);
            return;
        }

        try {
            const res = await fetch("/api/auth/me", {
                headers: { "Authorization": `Bearer ${this.token}` }
            });
            if (res.ok) {
                const data = await res.json();
                this.currentUser = data.user;
                this.onAuthenticated();
            } else {
                this.token = null;
                localStorage.removeItem("pulse_token");
                this.showAuthModal(true);
            }
        } catch (e) {
            this.showAuthModal(true);
        }
    }

    onAuthenticated() {
        this.showAuthModal(false);
        this.updateCurrentUserUI();
        this.connectWebSocket();
        this.loadRooms();
        this.loadUsers();
        this.switchRoom("general", "General Discussion", "Welcome channel for all team members");
    }

    updateCurrentUserUI() {
        if (!this.currentUser) return;
        const nameEl = document.getElementById("current-user-name");
        const statusEl = document.getElementById("current-user-status");
        const avatarEl = document.getElementById("current-user-avatar");
        
        nameEl.textContent = this.currentUser.display_name || this.currentUser.username;
        statusEl.textContent = `@${this.currentUser.username}`;
        avatarEl.textContent = (this.currentUser.display_name || this.currentUser.username)[0].toUpperCase();
        avatarEl.style.backgroundColor = this.currentUser.avatar_color || "#6366f1";
    }

    showAuthModal(show) {
        const modal = document.getElementById("auth-modal");
        if (show) {
            modal.classList.add("active");
        } else {
            modal.classList.remove("active");
        }
    }

    // --- WebSocket Connection ---
    connectWebSocket() {
        if (!this.token) return;
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws?token=${this.token}`;
        
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log("WebSocket connected.");
            // Subscribe to current room
            if (this.currentRoom) {
                this.ws.send(JSON.stringify({
                    type: "subscribe",
                    room_id: this.currentRoom
                }));
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleIncomingSocketMessage(data);
            } catch (e) {
                console.error("Malformed message:", e);
            }
        };

        this.ws.onclose = () => {
            console.warn("WebSocket disconnected. Retrying...");
            setTimeout(() => {
                if (this.currentUser) this.connectWebSocket();
            }, this.wsReconnectInterval);
        };
    }

    handleIncomingSocketMessage(data) {
        if (data.type === "presence_update") {
            this.handlePresenceUpdate(data.online_users);
        } else if (data.type === "new_message") {
            this.handleNewMessage(data.message);
        } else if (data.type === "typing_indicator") {
            this.handleTypingIndicator(data);
        }
    }

    handlePresenceUpdate(onlineList) {
        this.onlineUsers = new Set(onlineList.map(u => u.id));
        this.renderUserList();
        
        // Update room header online count
        const countEl = document.getElementById("room-online-count");
        if (countEl) {
            countEl.textContent = `${this.onlineUsers.size} Online`;
        }
    }

    handleNewMessage(msg) {
        const isCurrent = (msg.room_id === this.currentRoom);
        if (isCurrent) {
            this.appendMessage(msg);
            this.scrollToBottom();
            
            if (msg.sender_id !== this.currentUser.id) {
                this.playNotificationSound();
                this.showDesktopNotification(msg.sender_name, msg.content || "Sent an attachment");
            }
        } else {
            // Unread count
            this.unreadCounts[msg.room_id] = (this.unreadCounts[msg.room_id] || 0) + 1;
            this.renderRoomList();
            this.renderUserList();
            
            if (msg.sender_id !== this.currentUser.id) {
                this.playNotificationSound();
                this.showDesktopNotification(msg.sender_name, `[#${msg.room_id}] ${msg.content || "Sent a file"}`);
            }
        }
    }

    handleTypingIndicator(data) {
        if (data.room_id !== this.currentRoom || data.sender_id === this.currentUser.id) return;
        const bar = document.getElementById("typing-bar");
        const text = document.getElementById("typing-text");
        
        if (data.is_typing) {
            text.textContent = `${data.sender_name} is typing...`;
            bar.style.display = "flex";
        } else {
            bar.style.display = "none";
        }
    }

    // --- Room & Message Loading ---
    async loadRooms() {
        try {
            const res = await fetch("/api/rooms", {
                headers: { "Authorization": `Bearer ${this.token}` }
            });
            const data = await res.json();
            this.rooms = data.rooms || [];
            this.renderRoomList();
        } catch (e) {
            console.error("Failed to load rooms", e);
        }
    }

    async loadUsers() {
        try {
            const res = await fetch("/api/users", {
                headers: { "Authorization": `Bearer ${this.token}` }
            });
            const data = await res.json();
            this.users = (data.users || []).filter(u => u.id !== this.currentUser.id);
            this.renderUserList();
        } catch (e) {
            console.error("Failed to load users", e);
        }
    }

    async switchRoom(roomId, roomName, roomDesc, isDirect = false, targetUser = null) {
        if (this.ws && this.currentRoom) {
            this.ws.send(JSON.stringify({
                type: "unsubscribe",
                room_id: this.currentRoom
            }));
        }

        this.currentRoom = roomId;
        this.currentRoomName = roomName;
        this.currentRoomDesc = roomDesc;
        this.isDirectMessage = isDirect;
        this.directTargetUser = targetUser;
        
        // Reset unread count
        this.unreadCounts[roomId] = 0;
        this.renderRoomList();
        this.renderUserList();

        // Update header UI
        document.getElementById("current-channel-title").textContent = (isDirect ? `@ ${roomName}` : `# ${roomName}`);
        document.getElementById("current-channel-desc").textContent = roomDesc || "";
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: "subscribe",
                room_id: roomId
            }));
        }

        await this.loadMessages(roomId);
        
        // Close mobile drawer if open
        document.querySelector(".sidebar").classList.remove("open");
    }

    async loadMessages(roomId) {
        const container = document.getElementById("messages-container");
        container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 20px;">Loading chat history...</div>';
        
        try {
            const res = await fetch(`/api/rooms/${roomId}/messages`, {
                headers: { "Authorization": `Bearer ${this.token}` }
            });
            const data = await res.json();
            container.innerHTML = "";
            
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => this.appendMessage(msg));
            } else {
                container.innerHTML = `
                    <div style="text-align: center; color: var(--text-muted); margin: auto; padding: 40px;">
                        <div style="font-size: 2.2rem; margin-bottom: 8px;">👋</div>
                        <h3 style="color: var(--text-primary); margin-bottom: 4px;">Welcome to ${this.currentRoomName}!</h3>
                        <p style="font-size: 0.88rem;">This is the start of the conversation. Send a message to say hello!</p>
                    </div>
                `;
            }
            this.scrollToBottom();
        } catch (e) {
            container.innerHTML = '<div style="text-align: center; color: var(--danger); padding: 20px;">Failed to load messages.</div>';
        }
    }

    appendMessage(msg) {
        const container = document.getElementById("messages-container");
        const isOutgoing = (msg.sender_id === this.currentUser.id);
        
        const row = document.createElement("div");
        row.className = `message-row ${isOutgoing ? 'outgoing' : 'incoming'}`;
        
        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.style.backgroundColor = msg.sender_avatar || "#6366f1";
        avatar.style.width = "34px";
        avatar.style.height = "34px";
        avatar.style.fontSize = "0.85rem";
        avatar.textContent = (msg.sender_name || msg.sender_username || "U")[0].toUpperCase();
        
        const contentWrapper = document.createElement("div");
        contentWrapper.className = "message-content-wrapper";
        
        const meta = document.createElement("div");
        meta.className = "message-meta";
        
        const sender = document.createElement("span");
        sender.className = "sender-name";
        sender.textContent = isOutgoing ? "You" : (msg.sender_name || msg.sender_username);
        
        const time = document.createElement("span");
        time.className = "message-time";
        time.textContent = this.formatTime(msg.created_at);
        
        meta.appendChild(sender);
        meta.appendChild(time);
        
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        
        if (msg.content) {
            const textSpan = document.createElement("div");
            textSpan.textContent = msg.content;
            bubble.appendChild(textSpan);
        }
        
        // Attachments
        if (msg.file_url) {
            const attachDiv = document.createElement("div");
            attachDiv.className = "attachment-preview";
            
            if (msg.message_type === "image") {
                const img = document.createElement("img");
                img.src = msg.file_url;
                img.alt = msg.file_name || "Attachment";
                img.className = "attachment-img";
                img.onclick = () => this.openLightbox(msg.file_url);
                attachDiv.appendChild(img);
            } else if (msg.message_type === "audio") {
                const audio = document.createElement("audio");
                audio.controls = true;
                audio.src = msg.file_url;
                audio.className = "attachment-audio";
                attachDiv.appendChild(audio);
            } else {
                const card = document.createElement("a");
                card.href = msg.file_url;
                card.download = msg.file_name || "file";
                card.target = "_blank";
                card.className = "file-card";
                
                card.innerHTML = `
                    <div class="file-card-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                    </div>
                    <div class="file-card-info">
                        <span class="file-card-name">${msg.file_name || 'Attached file'}</span>
                        <span class="file-card-size">${this.formatBytes(msg.file_size)} • Click to download</span>
                    </div>
                `;
                attachDiv.appendChild(card);
            }
            bubble.appendChild(attachDiv);
        }
        
        contentWrapper.appendChild(meta);
        contentWrapper.appendChild(bubble);
        
        row.appendChild(avatar);
        row.appendChild(contentWrapper);
        container.appendChild(row);
    }

    scrollToBottom() {
        const container = document.getElementById("messages-container");
        container.scrollTop = container.scrollHeight;
    }

    // --- Sending Messages ---
    async sendMessage() {
        const input = document.getElementById("chat-input");
        const content = input.value.trim();
        
        if (!content && !this.pendingAttachment) return;
        
        let fileUrl = null;
        let fileName = null;
        let fileSize = null;
        let messageType = "text";
        
        if (this.pendingAttachment) {
            fileUrl = this.pendingAttachment.file_url;
            fileName = this.pendingAttachment.file_name;
            fileSize = this.pendingAttachment.file_size;
            messageType = this.pendingAttachment.message_type;
            this.clearAttachment();
        }

        const payload = {
            type: "message",
            room_id: this.currentRoom,
            content: content,
            message_type: messageType,
            file_url: fileUrl,
            file_name: fileName,
            file_size: fileSize,
            recipient_id: this.isDirectMessage && this.directTargetUser ? this.directTargetUser.id : null
        };

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(payload));
        }

        input.value = "";
        this.emitTyping(false);
    }

    emitTyping(isTyping) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        if (this.isTypingSent === isTyping) return;
        this.isTypingSent = isTyping;
        this.ws.send(JSON.stringify({
            type: "typing",
            room_id: this.currentRoom,
            is_typing: isTyping
        }));
    }

    // --- File Upload ---
    async handleFileUpload(file) {
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        
        const previewStrip = document.getElementById("file-preview-strip");
        const previewName = document.getElementById("preview-file-name");
        
        previewStrip.style.display = "flex";
        previewName.textContent = `Uploading ${file.name}...`;

        try {
            const res = await fetch("/api/upload", {
                method: "POST",
                headers: { "Authorization": `Bearer ${this.token}` },
                body: formData
            });
            const data = await res.json();
            if (data.success) {
                this.pendingAttachment = data;
                previewName.textContent = `${data.file_name} (${this.formatBytes(data.file_size)})`;
            } else {
                alert("Upload failed.");
                this.clearAttachment();
            }
        } catch (e) {
            alert("Upload failed.");
            this.clearAttachment();
        }
    }

    clearAttachment() {
        this.pendingAttachment = null;
        document.getElementById("file-preview-strip").style.display = "none";
        document.getElementById("file-input").value = "";
    }

    // --- Direct Message Creation ---
    async startDirectMessage(user) {
        try {
            const res = await fetch(`/api/rooms/dm/${user.id}`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${this.token}` }
            });
            const data = await res.json();
            if (data.success) {
                this.switchRoom(data.room.id, user.display_name || user.username, `Direct chat with @${user.username}`, true, user);
            }
        } catch (e) {
            console.error("Failed to start DM:", e);
        }
    }

    // --- Rendering Lists ---
    renderRoomList(filter = "") {
        const listEl = document.getElementById("rooms-list");
        listEl.innerHTML = "";
        
        const filtered = this.rooms.filter(r => r.name.toLowerCase().includes(filter.toLowerCase()));
        
        filtered.forEach(room => {
            const li = document.createElement("li");
            li.className = `nav-item ${this.currentRoom === room.id ? 'active' : ''}`;
            
            const left = document.createElement("div");
            left.className = "nav-item-left";
            
            const hash = document.createElement("span");
            hash.textContent = "#";
            hash.style.fontWeight = "bold";
            hash.style.color = "var(--text-muted)";
            
            const label = document.createElement("span");
            label.className = "nav-item-label";
            label.textContent = room.name;
            
            left.appendChild(hash);
            left.appendChild(label);
            li.appendChild(left);
            
            const unread = this.unreadCounts[room.id] || 0;
            if (unread > 0) {
                const badge = document.createElement("span");
                badge.className = "badge";
                badge.textContent = unread;
                li.appendChild(badge);
            }
            
            li.onclick = () => this.switchRoom(room.id, room.name, room.description, false, null);
            listEl.appendChild(li);
        });
    }

    renderUserList(filter = "") {
        const listEl = document.getElementById("users-list");
        listEl.innerHTML = "";
        
        const filtered = this.users.filter(u => 
            (u.display_name || u.username).toLowerCase().includes(filter.toLowerCase()) ||
            u.username.toLowerCase().includes(filter.toLowerCase())
        );
        
        filtered.forEach(user => {
            const isOnline = this.onlineUsers.has(user.id);
            const li = document.createElement("li");
            
            const dmRoomId = `dm_${Math.min(this.currentUser.id, user.id)}_${Math.max(this.currentUser.id, user.id)}`;
            const isActive = (this.currentRoom === dmRoomId);
            
            li.className = `nav-item ${isActive ? 'active' : ''}`;
            
            const left = document.createElement("div");
            left.className = "nav-item-left";
            
            const av = document.createElement("div");
            av.className = "avatar";
            av.style.backgroundColor = user.avatar_color || "#6366f1";
            av.style.width = "26px";
            av.style.height = "26px";
            av.style.fontSize = "0.75rem";
            av.textContent = (user.display_name || user.username)[0].toUpperCase();
            
            const dot = document.createElement("div");
            dot.className = `status-dot ${isOnline ? 'online' : 'offline'}`;
            av.appendChild(dot);
            
            const label = document.createElement("span");
            label.className = "nav-item-label";
            label.textContent = user.display_name || user.username;
            
            left.appendChild(av);
            left.appendChild(label);
            li.appendChild(left);
            
            const unread = this.unreadCounts[dmRoomId] || 0;
            if (unread > 0) {
                const badge = document.createElement("span");
                badge.className = "badge";
                badge.textContent = unread;
                li.appendChild(badge);
            }
            
            li.onclick = () => this.startDirectMessage(user);
            listEl.appendChild(li);
        });
    }

    // --- UI Helpers & Events ---
    bindEvents() {
        // Message Input & Typing
        const input = document.getElementById("chat-input");
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        input.addEventListener("input", () => {
            this.emitTyping(true);
            clearTimeout(this.typingTimeout);
            this.typingTimeout = setTimeout(() => {
                this.emitTyping(false);
            }, 1800);
        });

        document.getElementById("send-btn").onclick = () => this.sendMessage();

        // File upload trigger
        const fileInput = document.getElementById("file-input");
        document.getElementById("attach-btn").onclick = () => fileInput.click();
        fileInput.onchange = (e) => {
            if (e.target.files && e.target.files[0]) {
                this.handleFileUpload(e.target.files[0]);
            }
        };

        document.getElementById("clear-file-btn").onclick = () => this.clearAttachment();

        // Drag & Drop
        const dropArea = document.querySelector(".chat-area");
        ["dragenter", "dragover"].forEach(eventName => {
            dropArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropArea.style.backgroundColor = "rgba(99, 102, 241, 0.05)";
            }, false);
        });
        ["dragleave", "drop"].forEach(eventName => {
            dropArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropArea.style.backgroundColor = "";
            }, false);
        });
        dropArea.addEventListener("drop", (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files[0]) {
                this.handleFileUpload(files[0]);
            }
        });

        // Search Input
        document.getElementById("search-input").addEventListener("input", (e) => {
            const val = e.target.value.trim();
            this.renderRoomList(val);
            this.renderUserList(val);
        });

        // Notification Sound Toggle
        const soundBtn = document.getElementById("sound-toggle-btn");
        soundBtn.onclick = () => {
            this.soundEnabled = !this.soundEnabled;
            soundBtn.classList.toggle("active", this.soundEnabled);
            this.requestBrowserNotification();
        };

        // Create Room Modal
        const createRoomModal = document.getElementById("create-room-modal");
        document.getElementById("add-room-btn").onclick = () => createRoomModal.classList.add("active");
        document.getElementById("close-room-modal").onclick = () => createRoomModal.classList.remove("active");
        document.getElementById("create-room-form").onsubmit = async (e) => {
            e.preventDefault();
            const name = document.getElementById("new-room-name").value.trim();
            const desc = document.getElementById("new-room-desc").value.trim();
            if (!name) return;
            
            try {
                const res = await fetch("/api/rooms", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${this.token}`
                    },
                    body: JSON.stringify({ name, description: desc })
                });
                const data = await res.json();
                if (data.success) {
                    createRoomModal.classList.remove("active");
                    document.getElementById("new-room-name").value = "";
                    document.getElementById("new-room-desc").value = "";
                    await this.loadRooms();
                    this.switchRoom(data.room.id, data.room.name, data.room.description);
                } else {
                    alert(data.detail || "Error creating room.");
                }
            } catch (err) {
                alert("Error creating room.");
            }
        };

        // Emoji Tray
        const emojiBtn = document.getElementById("emoji-btn");
        const emojiTray = document.getElementById("emoji-tray");
        emojiBtn.onclick = (e) => {
            e.stopPropagation();
            emojiTray.style.display = emojiTray.style.display === "grid" ? "none" : "grid";
        };
        document.addEventListener("click", () => {
            emojiTray.style.display = "none";
        });
        document.querySelectorAll(".emoji-item").forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                input.value += btn.textContent;
                input.focus();
                emojiTray.style.display = "none";
            };
        });

        // Mobile drawer toggle
        const sidebar = document.querySelector(".sidebar");
        document.getElementById("mobile-menu-btn").onclick = () => {
            sidebar.classList.toggle("open");
        };

        // Logout
        document.getElementById("logout-btn").onclick = async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("pulse_token");
            this.token = null;
            this.currentUser = null;
            if (this.ws) this.ws.close();
            this.showAuthModal(true);
        };

        // Auth Form Tabs
        const tabLogin = document.getElementById("tab-login");
        const tabRegister = document.getElementById("tab-register");
        const loginForm = document.getElementById("login-form");
        const registerForm = document.getElementById("register-form");

        tabLogin.onclick = () => {
            tabLogin.classList.add("active");
            tabRegister.classList.remove("active");
            loginForm.style.display = "block";
            registerForm.style.display = "none";
        };

        tabRegister.onclick = () => {
            tabRegister.classList.add("active");
            tabLogin.classList.remove("active");
            loginForm.style.display = "none";
            registerForm.style.display = "block";
        };

        // Avatar Color Picker
        let selectedColor = "#6366f1";
        document.querySelectorAll(".color-swatch").forEach(swatch => {
            swatch.onclick = () => {
                document.querySelectorAll(".color-swatch").forEach(s => s.classList.remove("active"));
                swatch.classList.add("active");
                selectedColor = swatch.getAttribute("data-color");
            };
        });

        // Auth Submissions
        loginForm.onsubmit = async (e) => {
            e.preventDefault();
            const u = document.getElementById("login-username").value.trim();
            const p = document.getElementById("login-password").value;
            const errEl = document.getElementById("auth-error");
            errEl.textContent = "";

            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username: u, password: p })
                });
                const data = await res.json();
                if (data.success) {
                    this.token = data.token;
                    localStorage.setItem("pulse_token", data.token);
                    this.currentUser = data.user;
                    this.onAuthenticated();
                } else {
                    errEl.textContent = data.detail || "Login failed.";
                }
            } catch (err) {
                errEl.textContent = "Network error. Please try again.";
            }
        };

        registerForm.onsubmit = async (e) => {
            e.preventDefault();
            const u = document.getElementById("reg-username").value.trim();
            const d = document.getElementById("reg-name").value.trim();
            const em = document.getElementById("reg-email").value.trim();
            const p = document.getElementById("reg-password").value;
            const bio = document.getElementById("reg-bio").value.trim();
            const errEl = document.getElementById("auth-error");
            errEl.textContent = "";

            try {
                const res = await fetch("/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username: u,
                        display_name: d,
                        email: em,
                        password: p,
                        bio: bio,
                        avatar_color: selectedColor
                    })
                });
                const data = await res.json();
                if (data.success) {
                    this.token = data.token;
                    localStorage.setItem("pulse_token", data.token);
                    this.currentUser = data.user;
                    this.onAuthenticated();
                } else {
                    errEl.textContent = data.detail || "Registration failed.";
                }
            } catch (err) {
                errEl.textContent = "Network error. Please try again.";
            }
        };

        // Quick Demo Logins
        document.getElementById("demo-alice-btn").onclick = () => {
            document.getElementById("login-username").value = "alice";
            document.getElementById("login-password").value = "Password123!";
            loginForm.dispatchEvent(new Event("submit"));
        };

        document.getElementById("demo-bob-btn").onclick = () => {
            document.getElementById("login-username").value = "bob";
            document.getElementById("login-password").value = "Password123!";
            loginForm.dispatchEvent(new Event("submit"));
        };
    }

    openLightbox(src) {
        const modal = document.getElementById("lightbox-modal");
        const img = document.getElementById("lightbox-img");
        img.src = src;
        modal.classList.add("active");
        modal.onclick = () => modal.classList.remove("active");
    }

    formatTime(ts) {
        if (!ts) return "";
        const date = new Date(ts.replace(" ", "T") + "Z");
        if (isNaN(date.getTime())) return ts;
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
}

// Instantiate App when DOM is loaded
window.addEventListener("DOMContentLoaded", () => {
    window.chatApp = new PulseChatApp();
});
