        const chatArea = document.getElementById("chatArea");
        const chatInput = document.getElementById("chatInput");
        const sendBtn = document.getElementById("sendBtn");
        const quickTerminal = document.getElementById("quickTerminal");
        window.microAgiEmbedded = null;
        document.documentElement.classList.add('capabilities-pending');

        function defaultChatPlaceholder() {
            return window.microAgiEmbedded === false
                ? '输入一条控制指令 (例如: 列出当前文件)...'
                : '输入消息，和日和聊天…';
        }

        function markEmbeddedGoogleAuth(configured = false) {
            const login = document.getElementById('google-settings-auth-btn');
            if (login) {
                login.disabled = true;
                login.textContent = '账号登录待适配；可配置 API Key';
                login.onclick = null;
            }
            const status = document.getElementById('google-login-status');
            if (status) status.textContent = configured
                ? '模型 API Key 已配置'
                : '独立版需配置模型服务';
            const hint = document.querySelector('#google-login-section .settings-hint');
            if (hint) hint.textContent = '独立版请使用 API Key；密钥保存在应用私有目录，并用于调用模型服务。';
        }

        async function applyRuntimeCapabilities() {
            try {
                const response = await fetch('/api/health', { cache: 'no-store' });
                if (!response.ok) return;
                const health = await response.json();
                if (typeof health.embedded !== 'boolean') return;
                window.microAgiEmbedded = health.embedded;
                chatInput.placeholder = defaultChatPlaceholder();
                document.documentElement.classList.remove('capabilities-pending');
                if (!window.microAgiEmbedded) return;
                document.documentElement.classList.add('embedded-host');
                for (const id of ['toggle-terminal-btn', 'suggestionsContainer',
                                  'quickTerminal', 'settings-pane-wechat-section',
                                  'settings-tunnel-section', 'settings-termux-row',
                                  'aios-termux-controls', 'attachBtn']) {
                    const element = document.getElementById(id);
                    if (element) element.style.setProperty('display', 'none', 'important');
                }
                const fileUpload = document.getElementById('file-upload');
                if (fileUpload) fileUpload.disabled = true;
                markEmbeddedGoogleAuth();
                simplifyEmbeddedSettings();
                const update = document.getElementById('system-update-ver');
                if (update) update.textContent = '独立版请通过安装包更新';
                const updateButton = document.getElementById('system-update-btn');
                if (updateButton) updateButton.style.display = 'none';
                const memoryHint = document.getElementById('aios-memory-hint');
                if (memoryHint) memoryHint.textContent =
                    '长期记忆保存在应用内；主动通知和简报待 Android 原生适配。';
            } catch (error) {
                console.warn('Unable to read runtime capabilities', error);
            }
        }
        function setModelProvider(provider) {
            if (!window.microAgiEmbedded) return;
            const choice = provider === 'gemini' ? 'gemini' : 'compatible';
            const select = document.getElementById('model-provider');
            if (select) select.value = choice;
            for (const [id, visible] of [
                ['gemini-model-fields', choice === 'gemini'],
                ['compatible-model-fields', choice === 'compatible']
            ]) {
                const group = document.getElementById(id);
                if (group) group.hidden = !visible;
            }
        }

        function simplifyEmbeddedSettings() {
            if (typeof document.querySelectorAll !== 'function') return;
            const names = {1: '外观', 2: '桌宠', 3: '聊天模型'};
            document.querySelectorAll('.settings-tab').forEach(tab => {
                const index = Number(tab.dataset.settingsTab);
                tab.hidden = !names[index];
                if (names[index]) tab.textContent = names[index];
            });
            const modelStatus = document.getElementById('google-login-status');
            if (modelStatus && modelStatus.parentElement) {
                modelStatus.parentElement.replaceChildren(modelStatus);
                const heading = modelStatus.closest('section').querySelector('h4');
                if (heading) heading.textContent = '聊天模型';
            }
            const pet = document.getElementById('settings-native-pet');
            if (pet) {
                const title = pet.querySelector('.settings-row-title');
                const description = pet.querySelector('.settings-row-desc');
                if (title) title.textContent = '悬浮桌宠';
                if (description) description.textContent = '让角色陪你使用其他应用，可随时关闭。首次开启需允许悬浮窗权限。';
            }
            const petSection = document.getElementById('settings-pet-section');
            if (petSection) {
                const subtitle = petSection.querySelector('.settings-section-head p');
                if (subtitle) subtitle.textContent = '开启或关闭手机上的悬浮角色';
                const localPetRow = document.getElementById('settings-pet-checkbox');
                if (localPetRow) localPetRow.closest('label').hidden = true;
            }
            const interact = document.getElementById('settings-pane-interact');
            const memory = document.getElementById('settings-memory-section');
            if (interact && memory && !document.getElementById('embedded-memory-details')) {
                const details = document.createElement('details');
                details.id = 'embedded-memory-details';
                details.className = 'settings-disclosure';
                const summary = document.createElement('summary');
                summary.textContent = '记忆与对话偏好';
                details.append(summary, memory);
                const chatToggle = document.getElementById('settings-chat-checkbox');
                if (chatToggle) details.append(chatToggle.closest('label'));
                interact.append(details);
            }
            setModelProvider('compatible');
            const tab = Number(localStorage.getItem('micro-agi-settings-tab'));
            switchSettingsTab([1, 2, 3].includes(tab) ? tab : 3);
        }
        window.addEventListener('DOMContentLoaded', () => {
            window.microAgiCapabilitiesReady = applyRuntimeCapabilities();
        });

        let chatHistory = [];
        let currentChatId = "";
        let currentCardId = null;
        let currentController = null;

        function handleSendOrStop() {
            if (currentController) {
                currentController.abort();
                stopSpeech();
                return;
            }
            sendMessage();
        }

        function setSendBtnState(isSending) {
            const btn = document.getElementById("sendBtn");
            if (isSending) {
                btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect></svg>`;
                btn.style.background = "rgba(239, 68, 68, 0.2)";
                btn.style.color = "#fca5a5";
                btn.style.borderColor = "rgba(239, 68, 68, 0.4)";
                btn.disabled = false;
            } else {
                btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`;
                btn.style.background = "";
                btn.style.color = "";
                btn.style.borderColor = "";
                btn.disabled = false;
            }
        }

        // --- Voice Input (Speech Recognition) Support ---
        let recognition = null;
        let isRecording = false;

        function initVoiceInput() {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                console.warn("Speech recognition not supported in this browser.");
                const micBtn = document.getElementById("micBtn");
                if (micBtn) micBtn.style.display = "none";
                return;
            }

            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.lang = 'zh-CN';

            recognition.onstart = () => {
                isRecording = true;
                const micBtn = document.getElementById("micBtn");
                if (micBtn) micBtn.classList.add("recording");
                chatInput.placeholder = "正在聆听…";
            };

            recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }

                if (finalTranscript) {
                    chatInput.value = finalTranscript;
                    // Auto-send voice command 800ms after final speech transcript is received
                    setTimeout(() => {
                        if (chatInput.value === finalTranscript && finalTranscript.trim().length > 0) {
                            sendMessage();
                        }
                    }, 800);
                } else if (interimTranscript) {
                    chatInput.value = interimTranscript;
                }
            };

            recognition.onerror = (event) => {
                console.error("Speech recognition error:", event.error);
                stopVoiceRecognition();
                if (event.error === 'not-allowed') {
                    chatInput.placeholder = "🔒 麦克风权限被拒绝，请开启权限";
                } else {
                    chatInput.placeholder = "🎙️ 语音识别出错: " + event.error;
                }
                setTimeout(() => {
                    chatInput.placeholder = defaultChatPlaceholder();
                }, 3000);
            };

            recognition.onend = () => {
                stopVoiceRecognition();
            };
        }

        function stopVoiceRecognition() {
            if (!isRecording) return;
            isRecording = false;
            if (recognition) {
                try {
                    recognition.stop();
                } catch(e) {}
            }
            const micBtn = document.getElementById("micBtn");
            if (micBtn) micBtn.classList.remove("recording");
            chatInput.placeholder = defaultChatPlaceholder();
        }

        function toggleVoiceInput() {
            if (chatInput.disabled) return;
            if (!recognition) {
                initVoiceInput();
            }
            if (!recognition) {
                chatInput.placeholder = "🎙️ 浏览器不支持语音输入";
                setTimeout(() => {
                    chatInput.placeholder = defaultChatPlaceholder();
                }, 3000);
                return;
            }

            if (isRecording) {
                recognition.stop();
            } else {
                chatInput.value = "";
                try {
                    recognition.start();
                } catch (e) {
                    console.error("Failed to start voice recognition:", e);
                }
            }
        }

        let wakeWordPollInterval = null;
        function toggleWakeWordDetection() {
            const chk = document.getElementById("settings-wakeword-checkbox");
            const isChecked = chk ? chk.checked : false;
            
            if (isChecked) {
                if (!wakeWordPollInterval) {
                    wakeWordPollInterval = setInterval(checkWakeWordStatus, 1500);
                    showToast("语音唤醒监测已开启 🎙️");
                }
            } else {
                if (wakeWordPollInterval) {
                    clearInterval(wakeWordPollInterval);
                    wakeWordPollInterval = null;
                    showToast("语音唤醒监测已关闭 🔇");
                }
            }
        }

        async function checkWakeWordStatus() {
            try {
                const response = await fetch("/api/hardware/wake");
                const data = await response.json();
                if (data.woken) {
                    triggerAgentWakeUp();
                }
            } catch (e) {
                console.error("唤醒状态轮询失败", e);
            }
        }

        function triggerAgentWakeUp() {
            if (live2dModel) {
                live2dModel.motion("Tap@Body");
            }
            
            const greetText = "主人，日和在这里！请吩咐我做事吧～✨";
            showWelcomeBubble(greetText);
            
            if (isVoiceEnabled) {
                speakText(greetText);
            }
            
            if (isRecording) {
                stopVoiceRecognition();
                setTimeout(startVoiceListening, 500);
            } else {
                startVoiceListening();
            }
        }

        function startVoiceListening() {
            if (chatInput.disabled) return;
            if (!recognition) {
                initVoiceInput();
            }
            if (recognition) {
                chatInput.value = "";
                try {
                    recognition.start();
                    showToast("日和听到唤醒词，正在聆听您的指令...");
                } catch (e) {
                    console.error("唤醒后启动语音输入失败", e);
                }
            }
        }
        // ------------------------------------------------

        // Add Enter Key Listener
        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!chatInput.disabled) {
                    sendMessage();
                }
            }
        });

        // Auto-scroll on input focus for mobile virtual keyboards
        chatInput.addEventListener("focus", () => {
            setTimeout(() => {
                chatArea.scrollTop = chatArea.scrollHeight;
            }, 250);
        });

        function sendSuggestion(text) {
            if (chatInput.disabled) return;
            chatInput.value = text;
            sendMessage();
        }

        let pendingAttachments = [];

        function compressImage(file, callback) {
            if (!file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => callback(e.target.result);
                reader.onerror = () => callback(null);
                reader.readAsDataURL(file);
                return;
            }

            const reader = new FileReader();
            reader.onload = function(e) {
                const img = new Image();
                img.onload = function() {
                    const maxW = 800;
                    const maxH = 800;
                    let width = img.width;
                    let height = img.height;

                    if (width > maxW || height > maxH) {
                        if (width > height) {
                            height = Math.round((height * maxW) / width);
                            width = maxW;
                        } else {
                            width = Math.round((width * maxH) / height);
                            height = maxH;
                        }
                    }

                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;

                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);

                    // Compress as JPEG format with 0.7 quality to keep size tiny
                    const compressedDataUrl = canvas.toDataURL('image/jpeg', 0.7);
                    callback(compressedDataUrl);
                };
                img.onerror = function() {
                    callback(e.target.result); // fallback to original on load error
                };
                img.src = e.target.result;
            };
            reader.onerror = function() {
                callback(null);
            };
            reader.readAsDataURL(file);
        }

        function handleFileSelect(event) {
            const files = event.target.files;
            if (!files || files.length === 0) return;
            
            Array.from(files).forEach(file => {
                const attId = 'att-' + Date.now() + Math.random().toString(36).substr(2, 9);
                const attObj = {
                    id: attId,
                    name: file.name,
                    type: file.type.startsWith('image/') ? 'image/jpeg' : file.type,
                    data: null,
                    progress: 30, // Show mock initial reading progress
                    status: 'reading'
                };
                pendingAttachments.push(attObj);
                renderAttachmentsPreview();
                updateAttachmentProgress(attId, 30);

                compressImage(file, (dataUrl) => {
                    if (dataUrl) {
                        attObj.data = dataUrl;
                        attObj.status = 'done';
                        attObj.progress = 100;
                    } else {
                        attObj.status = 'error';
                    }
                    renderAttachmentsPreview();
                });
            });
            event.target.value = "";
        }

        function removeAttachment(id) {
            pendingAttachments = pendingAttachments.filter(a => a.id !== id);
            renderAttachmentsPreview();
        }

        function updateAttachmentProgress(id, progress) {
            const progressEl = document.getElementById(`progress-${id}`);
            if (progressEl) progressEl.style.width = `${progress}%`;
        }

        function renderAttachmentsPreview() {
            const previewContainer = document.getElementById("attachments-preview");
            if (pendingAttachments.length === 0) {
                previewContainer.style.display = "none";
                previewContainer.innerHTML = "";
                return;
            }
            
            previewContainer.style.display = "flex";
            previewContainer.innerHTML = "";
            
            pendingAttachments.forEach(att => {
                const item = document.createElement("div");
                item.style.position = "relative";
                item.style.overflow = "hidden";
                item.style.background = "rgba(0,0,0,0.3)";
                item.style.borderRadius = "6px";
                item.style.padding = "4px 8px";
                item.style.fontSize = "0.7rem";
                item.style.color = "var(--text-color)";
                item.style.display = "flex";
                item.style.alignItems = "center";
                item.style.gap = "6px";
                item.style.border = "1px solid rgba(255,255,255,0.1)";
                
                if (att.status === 'reading') {
                    const progress = document.createElement('div');
                    progress.style.cssText = 'position:absolute;bottom:0;left:0;height:2px;background:var(--primary);transition:width 0.1s;';
                    progress.style.width = `${Math.max(0, Math.min(100, Number(att.progress) || 0))}%`;
                    progress.id = `progress-${att.id}`;
                    item.append(progress, document.createTextNode('⏳ 读取中...'));
                } else if (att.status === 'error') {
                    const error = document.createElement('span');
                    error.style.color = 'red';
                    error.textContent = '读取失败';
                    item.append(document.createTextNode('❌ '), error);
                } else {
                    if (att.type === 'skill') {
                        item.append(document.createTextNode('🔌'));
                        item.style.background = "linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(139, 92, 246, 0.2))";
                        item.style.borderColor = "var(--primary)";
                        item.style.color = "#cffafe";
                    } else if (att.type.startsWith("image/") && att.data) {
                        const image = document.createElement('img');
                        image.src = att.data;
                        image.style.cssText = 'width:24px;height:24px;object-fit:cover;border-radius:4px;';
                        item.appendChild(image);
                    } else {
                        item.append(document.createTextNode('📄'));
                    }
                    const name = document.createElement('span');
                    name.style.cssText = 'max-width:100px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
                    name.title = att.name;
                    name.textContent = att.name;
                    const remove = document.createElement('button');
                    remove.className = 'remove-btn';
                    remove.style.cssText = 'background:none;border:none;color:var(--error);cursor:pointer;padding:2px;font-size:1.1rem;line-height:1;';
                    remove.textContent = '×';
                    remove.addEventListener('click', () => removeAttachment(att.id));
                    item.append(name, remove);
                }
                previewContainer.appendChild(item);
            });
        }

        // ===== Streaming helpers (SSE) =====
        function removeLoadingBubbles() {
            document.querySelectorAll(".loading-dots").forEach(d => {
                try { d.parentElement.parentElement.parentElement.remove(); } catch (e) {}
            });
            const legacy = document.getElementById("stream-msg");
            // keep stream-msg if actively streaming
        }

        function ensureStreamBubble() {
            let msg = document.getElementById("stream-msg");
            if (msg) return msg;
            removeLoadingBubbles();
            msg = document.createElement("div");
            msg.className = "message assistant";
            msg.id = "stream-msg";
            msg.innerHTML = `
                <div class="message-avatar">HY</div>
                <div class="message-content">
                    <span class="message-sender">Hiyori <span style="opacity:.5;font-size:.7rem;">流式</span></span>
                    <div class="message-bubble stream-bubble-body" style="white-space:pre-wrap;word-break:break-word;"><span class="stream-cursor" style="opacity:.7;animation:blink 1s step-end infinite;">▋</span></div>
                </div>
            `;
            chatArea.appendChild(msg);
            if (!document.getElementById("stream-blink-style")) {
                const st = document.createElement("style");
                st.id = "stream-blink-style";
                st.textContent = "@keyframes blink{50%{opacity:0}}";
                document.head.appendChild(st);
            }
            return msg;
        }

        function updateStreamBubble(fullText) {
            const msg = ensureStreamBubble();
            const body = msg.querySelector(".stream-bubble-body");
            // Hide raw execute tags mid-stream without promising a command
            // approval flow which the standalone app deliberately disables.
            let display = fullText;
            const execIdx = display.indexOf("<execute>");
            if (execIdx !== -1) {
                display = display.slice(0, execIdx).trimEnd() +
                    (window.microAgiEmbedded === false
                        ? "\n\n⏳ 准备申请执行命令…"
                        : "\n\n（独立版不支持命令执行；本次不会执行任何命令。）");
            }
            body.innerHTML = escapeHtml(display).replace(/\n/g, "<br>") +
                '<span class="stream-cursor" style="opacity:.7;animation:blink 1s step-end infinite;">▋</span>';
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function clearStreamBubble() {
            const msg = document.getElementById("stream-msg");
            if (msg) msg.remove();
        }

        async function consumeSSE(response, handlers) {
            if (!response.ok) {
                const t = await response.text().catch(() => "");
                throw new Error("HTTP " + response.status + " " + t.slice(0, 120));
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let sep;
                while ((sep = buffer.indexOf("\n\n")) !== -1) {
                    const block = buffer.slice(0, sep);
                    buffer = buffer.slice(sep + 2);
                    const lines = block.split("\n");
                    for (const line of lines) {
                        if (!line.startsWith("data:")) continue;
                        const raw = line.slice(5).trim();
                        if (!raw || raw === "[DONE]") continue;
                        let ev;
                        try { ev = JSON.parse(raw); } catch (e) { continue; }
                        if (handlers && handlers.onEvent) handlers.onEvent(ev);
                    }
                }
            }
        }

        async function sendMessage() {
            const text = chatInput.value.trim();
            const isReading = pendingAttachments.some(a => a.status === 'reading');
            if (isReading) return; // Prevent sending while files are still loading into memory
            
            if (!text && pendingAttachments.length === 0) return;

            // If starting a new session, create it in SQLite first
            if (currentChatId === "") {
                const title = text ? (text.slice(0, 16) + (text.length > 16 ? "..." : "")) : "新对话";
                try {
                    const res = await fetch("/api/chats", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ title: title })
                    });
                    const d = await res.json();
                    if (d.chat_id) {
                        currentChatId = d.chat_id;
                        const headerTitle = document.getElementById('header-chat-title');
                        if (headerTitle) {
                            headerTitle.textContent = title;
                        }
                        loadChatSessions(false); // Update sidebar with the new session
                    }
                } catch (e) {
                    console.error("Failed to auto-create chat session:", e);
                }
            }
            
            const currentAttachments = pendingAttachments.map(a => ({
                name: a.name, type: a.type, data: a.data
            }));
            
            // Clear Input
            chatInput.value = "";
            chatInput.disabled = true;
            document.getElementById("attachBtn").disabled = true;
            setSendBtnState(true);
            
            currentController = new AbortController();
            pendingAttachments = [];
            renderAttachmentsPreview();

            const mainContainer = document.querySelector(".main-container");
            if (mainContainer && mainContainer.classList.contains("chat-collapsed")) {
                toggleChatLogs();
            }

            // Append User Message UI
            let displayHtml = escapeHtml(text).replace(/\n/g, "<br>");
            if (currentAttachments.length > 0) {
                let attHtml = `<div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px;">`;
                currentAttachments.forEach(att => {
                    if (att.type === 'skill') {
                        attHtml += `<span style="background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(139, 92, 246, 0.2)); color: #cffafe; padding: 4px 8px; border-radius: 4px; border: 1px solid var(--primary); font-size: 0.8rem;">🔌 技能: ${escapeHtml(att.name)}</span>`;
                    } else if (att.type.startsWith("image/")) {
                        attHtml += `<img src="${att.data}" style="max-width: 200px; max-height: 200px; border-radius: 4px; object-fit: cover;">`;
                    } else {
                        attHtml += `<span style="background: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem;">📄 ${escapeHtml(att.name)}</span>`;
                    }
                });
                attHtml += `</div>`;
                displayHtml = attHtml + (text ? `<div>${escapeHtml(text).replace(/\n/g, "<br>")}</div>` : "");
            }

            // Construct payload for LLM
            let finalPayloadText = text;
            const skillAttachments = currentAttachments.filter(a => a.type === 'skill');
            const fileAttachments = currentAttachments.filter(a => a.type !== 'skill');

            if (skillAttachments.length > 0) {
                let skillPrompt = "";
                skillAttachments.forEach(skill => {
                    if (skill.data === 'search') skillPrompt += "[调用内置搜索技能] ";
                    else if (skill.data === 'bilibili') skillPrompt += "[调用B站总结技能] ";
                    else if (skill.data === 'github') skillPrompt += "[调用代码分析师技能] ";
                });
                
                if (!text) {
                    if (skillAttachments[0].data === 'search') finalPayloadText = skillPrompt + "请帮我全网检索关于“2026年最新具身智能机器人的发展趋势”，并生成一份简报。";
                    else if (skillAttachments[0].data === 'bilibili') finalPayloadText = skillPrompt + "请帮我获取并总结这个 Bilibili 视频的内容核心摘要：https://www.bilibili.com/video/BV1xxx";
                    else if (skillAttachments[0].data === 'github') finalPayloadText = skillPrompt + "请帮我 clone 并分析一下这个开源项目的核心架构：https://github.com/fastai/fastai";
                } else {
                    finalPayloadText = skillPrompt + text;
                }
            }

            appendMessage("user", "您", displayHtml, true);
            appendLoading();
            chatArea.scrollTop = chatArea.scrollHeight;

            // Trigger Live2D thinking state and cancel previous speech
            stopSpeech();
            if (live2dModel) {
                live2dModel.motion('FlickDown');
            }

            let streamedText = "";
            let finalData = null;
            let streamError = null;

            try {
                const response = await fetch("/api/chat/stream", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
                    body: JSON.stringify({
                        message: finalPayloadText,
                        history: chatHistory,
                        attachments: fileAttachments,
                        chat_id: currentChatId
                    }),
                    signal: currentController.signal
                });

                await consumeSSE(response, {
                    onEvent: (ev) => {
                        if (ev.type === "meta" && ev.chat_id) {
                            if (!currentChatId) {
                                currentChatId = ev.chat_id;
                                loadChatSessions(false);
                            } else {
                                currentChatId = ev.chat_id;
                            }
                        } else if (ev.type === "token" && ev.text) {
                            streamedText += ev.text;
                            updateStreamBubble(streamedText);
                        } else if (ev.type === "done") {
                            finalData = ev;
                        } else if (ev.type === "error") {
                            streamError = ev.error || "未知流式错误";
                        }
                    }
                });

                if (streamError) {
                    clearStreamBubble();
                    removeLoadingBubbles();
                    const partial = streamedText
                        ? escapeHtml(streamedText).replace(/\n/g, "<br>") + "<br><br>"
                        : "";
                    appendMessage("assistant", streamedText ? "Hiyori" : "系统错误",
                        partial + `⚠️ 回答未完整结束；未自动重试。${escapeHtml(streamError)}`);
                    if (live2dModel) live2dModel.motion('Flick');
                } else if (finalData) {
                    // Replace raw stream bubble with polished final render
                    clearStreamBubble();
                    removeLoadingBubbles();
                    if (finalData.chat_id && !currentChatId) {
                        currentChatId = finalData.chat_id;
                    }
                    handleAgentResponse(finalData, text || "[包含附件的消息]");
                } else if (streamedText) {
                    clearStreamBubble();
                    removeLoadingBubbles();
                    appendMessage("assistant", "Hiyori",
                        escapeHtml(streamedText).replace(/\n/g, "<br>") +
                        "<br><br>⚠️ 回答未完整结束；未自动重试，以避免重复消耗 API 额度。");
                } else {
                    removeLoadingBubbles();
                    appendMessage("assistant", "Hiyori", "（没有收到模型输出）");
                }
            } catch (err) {
                clearStreamBubble();
                removeLoadingBubbles();
                
                if (err.name === 'AbortError') {
                    appendMessage("assistant", "Hiyori", streamedText
                        ? escapeHtml(streamedText).replace(/\n/g, "<br>") + "<br><br>⚠️ 对话已被您手动打断。"
                        : "⚠️ 对话已被您手动打断。");
                    if (live2dModel) {
                        live2dModel.motion('Idle');
                    }
                } else {
                    const partial = streamedText
                        ? escapeHtml(streamedText).replace(/\n/g, "<br>") + "<br><br>"
                        : "";
                    appendMessage("assistant", "连接中断", partial +
                        `⚠️ 流式请求失败；为避免重复消耗 API 额度，未自动重试。请确认后手动重发。${escapeHtml(err.message || '')}`);
                    if (live2dModel) live2dModel.motion('Flick');
                }
            } finally {
                chatInput.disabled = false;
                document.getElementById("attachBtn").disabled = false;
                setSendBtnState(false);
                currentController = null;
            }
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function handleAgentResponse(data, originalText) {
            // Restore UI
            chatInput.disabled = false;
            sendBtn.disabled = false;
            document.getElementById("attachBtn").disabled = false;

            if (data.status === "waiting_approval") {
                // 1. Show Thoughts
                if (data.thoughts) {
                    appendMessage("assistant", "Micro-AGI", escapeHtml(data.thoughts).replace(/\n/g, "<br>"));
                }
                
                // 2. Render Approval Card
                appendApprovalCard(data.command);
                
                // 3. Keep inputs disabled, prompt user
                chatInput.placeholder = "请批准或拒绝上方的指令...";
                chatInput.disabled = true;
                sendBtn.disabled = true;
                document.getElementById("attachBtn").disabled = true;

                // Live2D feedback
                if (live2dModel) {
                    live2dModel.motion('Tap');
                }
                if (isVoiceEnabled) {
                    speakText("主人，我申请运行这行终端命令，请您审批。");
                }
            } else {
                // Completed!
                appendAssistantMessage(data.response, data.steps, data.node_id);
                
                // Save to history
                if (originalText) {
                    chatHistory.push({ role: "user", content: originalText });
                }
                chatHistory.push({ role: "assistant", content: typeof data.response === 'string' ? data.response : "[Complex Message]" });
                
                if (chatHistory.length > 10) {
                    chatHistory = chatHistory.slice(chatHistory.length - 10);
                }
                
                // Re-enable inputs
                chatInput.placeholder = defaultChatPlaceholder();

                // Live2D feedback and speak
                if (live2dModel) {
                    live2dModel.motion('Tap');
                }
                if (isVoiceEnabled) {
                    speakText(data.response);
                }
            }
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function appendApprovalCard(command) {
            currentCardId = "card-" + Date.now();
            
            // Note: We intentionally skip adding a passive card to the chat area here.
            // Only the floating bubble will be shown to avoid cluttering the chat history.
            // The execution steps will be appended natively once the command completes.

            // 2. Create and append the interactive floating approval bubble next to Hiyori's head
            const existingBubble = document.getElementById('approval-bubble');
            if (existingBubble) existingBubble.remove();
            
            const appBubble = document.createElement("div");
            appBubble.className = "approval-bubble";
            appBubble.id = "approval-bubble";
            
            appBubble.innerHTML = `
                <div class="approval-bubble-bg"></div>
                <div class="approval-bubble-pointer"></div>
                <div class="approval-bubble-content">
                    <div class="approval-bubble-title">
                        <span>🌸 主人，请批准运行命令：</span>
                    </div>
                    <div class="approval-bubble-cmd-container">
                        <textarea class="approval-bubble-cmd" id="approval-bubble-cmd">${escapeHtml(command)}</textarea>
                    </div>
                    <div class="approval-bubble-actions">
                        <button class="approval-bubble-btn deny" onclick="submitBubbleApproval(false)">拒绝</button>
                        <button class="approval-bubble-btn approve" onclick="submitBubbleApproval(true)">批准</button>
                    </div>
                </div>
            `;
            
            const tabChat = document.getElementById('tab-content-chat');
            tabChat.appendChild(appBubble);
            
            // Position the bubble immediately
            const container = document.querySelector('.avatar-container');
            if (container && live2dModel) {
                const isMobile = container.clientWidth < 600;
                const offsetX = isMobile ? 22 : 40;
                const headX = container.clientWidth / 2;
                const leftPos = headX + offsetX;
                const maxAllowedWidth = container.clientWidth - leftPos - 12;
                const targetMaxWidth = isMobile ? 170 : 260;
                
                appBubble.style.left = `${leftPos}px`;
                appBubble.style.right = 'auto';
                appBubble.style.maxWidth = `${Math.max(100, Math.min(targetMaxWidth, maxAllowedWidth))}px`;
                
                live2dModel.scale.set(1);
                const nativeHeight = live2dModel.height;
                const baseScale = container.clientHeight / nativeHeight;
                const zoomScale = baseScale * (isMobile ? 1.5 : 1.65);
                live2dModel.scale.set(zoomScale);
                const headY = 20 + (nativeHeight * 0.14) * zoomScale;
                appBubble.style.top = `${headY}px`;
            }
        }

        async function submitBubbleApproval(approved) {
            const bubble = document.getElementById('approval-bubble');
            const bubbleCmdInput = document.getElementById('approval-bubble-cmd');
            const editedCommand = bubbleCmdInput ? bubbleCmdInput.value.trim() : "";
            
            if (bubble) {
                bubble.classList.add('fade-out');
                setTimeout(() => bubble.remove(), 500);
            }
            
            const cardId = currentCardId;
            if (cardId) {
                const logEl = document.getElementById(`${cardId}-cmd-log`);
                if (logEl) logEl.innerText = editedCommand;
                const actionsDiv = document.getElementById(`${cardId}-actions`);
                if (actionsDiv) {
                    actionsDiv.style.display = "block";
                    actionsDiv.innerHTML = `<span style="font-size:0.8rem;color:var(--text-muted);">${approved ? '⏳ 正在执行...' : '❌ 已拒绝执行'}</span>`;
                }
            }
            
            // Play motion & speak feedback
            if (live2dModel) {
                if (approved) {
                    live2dModel.motion('Tap');
                    if (isVoiceEnabled) {
                        speakText("收到，正在为您运行指令！");
                    }
                } else {
                    live2dModel.motion('Flick');
                    if (isVoiceEnabled) {
                        speakText("好的，已取消运行。");
                    }
                }
            }
            
            await submitApprovalFlow(approved, editedCommand);
        }

        async function submitApprovalFlow(approved, editedCommand) {
            const cardId = currentCardId;
            // cardId optional for bubble-only flow

            appendLoading();
            chatArea.scrollTop = chatArea.scrollHeight;
            
            chatInput.disabled = true;
            document.getElementById("attachBtn").disabled = true;
            setSendBtnState(true);
            currentController = new AbortController();

            let streamedText = "";
            let finalData = null;
            let streamError = null;

            try {
                const response = await fetch("/api/approve/stream", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
                    body: JSON.stringify({ approved: approved, edited_command: editedCommand, chat_id: currentChatId }),
                    signal: currentController.signal
                });

                await consumeSSE(response, {
                    onEvent: (ev) => {
                        if (ev.type === "token" && ev.text) {
                            streamedText += ev.text;
                            updateStreamBubble(streamedText);
                        } else if (ev.type === "done") {
                            finalData = ev;
                        } else if (ev.type === "error") {
                            streamError = ev.error || "审批流错误";
                        } else if (ev.type === "step") {
                            // command finished; keep loading until tokens arrive
                        }
                    }
                });

                clearStreamBubble();
                removeLoadingBubbles();

                if (streamError) {
                    appendMessage("assistant", "系统错误", `执行发生错误: ${escapeHtml(streamError)}`);
                } else if (finalData) {
                    handleAgentResponse(finalData);
                } else if (streamedText) {
                    handleAgentResponse({ status: "completed", response: streamedText, steps: [] });
                } else {
                    // fallback non-stream
                    const response2 = await fetch("/api/approve", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ approved: approved, edited_command: editedCommand, chat_id: currentChatId }),
                        signal: currentController.signal
                    });
                    const data = await response2.json();
                    if (data.error) {
                        appendMessage("assistant", "系统错误", `执行发生错误: ${escapeHtml(data.error)}`);
                    } else {
                        handleAgentResponse(data);
                    }
                }
            } catch (err) {
                clearStreamBubble();
                removeLoadingBubbles();
                try {
                    const response = await fetch("/api/approve", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ approved: approved, edited_command: editedCommand, chat_id: currentChatId }),
                        signal: currentController.signal
                    });
                    const data = await response.json();
                    if (data.error) {
                        appendMessage("assistant", "系统错误", `执行发生错误: ${escapeHtml(data.error)}`);
                    } else {
                        handleAgentResponse(data);
                    }
                } catch (err2) {
                    appendMessage("assistant", "连接失败", `无法连接: ${escapeHtml(err.message)}`);
                }
            } finally {
                chatInput.disabled = false;
                document.getElementById("attachBtn").disabled = false;
                setSendBtnState(false);
                currentController = null;
                chatInput.placeholder = defaultChatPlaceholder();
            }
        }

        function appendMessage(role, sender, text, removeLoading = false, nodeId = null) {
            if (removeLoading) {
                const ls = document.querySelectorAll(".loading-dots");
                ls.forEach(l => l.parentElement.parentElement.parentElement.remove());
            }

            const msgDiv = document.createElement("div");
            msgDiv.className = `message ${role}`;
            if (nodeId) msgDiv.id = `msg-${nodeId}`;

            msgDiv.innerHTML = `
                <div class="message-avatar">${role === "user" ? "ME" : "HY"}</div>
                <div class="message-content">
                    <span class="message-sender">${sender}</span>
                    <div class="message-bubble">${text}</div>
                </div>
            `;

            chatArea.appendChild(msgDiv);
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function appendLoading() {
            const id = "loading-" + Date.now();
            const msgDiv = document.createElement("div");
            msgDiv.className = "message assistant";
            msgDiv.id = id;
            msgDiv.innerHTML = `
                <div class="message-avatar">HY</div>
                <div class="message-content">
                    <span class="message-sender">执行中...</span>
                    <div class="message-bubble"><div class="loading-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>
                </div>
            `;
            chatArea.appendChild(msgDiv);
            return id;
        }

        function toggleStepDetails(id) {
            const details = document.getElementById(id);
            details.style.display = details.style.display === "none" ? "block" : "none";
        }

        function escapeHtml(unsafe) {
            if (unsafe === null || unsafe === undefined) return "";
            return String(unsafe)
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
        }

        function formatTerminalOutput(output) {
            if (!output) return "";
            try {
                // Try to parse as JSON for pretty highlighting
                let parsed = JSON.parse(output);
                let jsonStr = escapeHtml(JSON.stringify(parsed, null, 2));
                // Add simple regex-based syntax highlighting for JSON keys/values
                jsonStr = jsonStr.replace(/(".*?"|null|true|false|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, match => {
                    if (match.startsWith('"')) {
                        // Check if it's a key
                        if (jsonStr.indexOf(match + ':') !== -1) {
                            return `<span style="color:#63b3ed;">${match}</span>`;
                        }
                        return `<span style="color:#a6e22e;">${match}</span>`;
                    }
                    if (match === 'true' || match === 'false') return `<span style="color:#fd971f;">${match}</span>`;
                    if (match === 'null') return `<span style="color:#f92672;">${match}</span>`;
                    return `<span style="color:#ae81ff;">${match}</span>`; // numbers
                });
                return jsonStr;
            } catch(e) {
                // Plain text output
                return escapeHtml(output);
            }
        }

        function appendAssistantMessage(response, steps, nodeId = null) {
            // Keep generated code-block HTML separate while escaping all model text.
            const codeBlocks = [];
            let parsedContent = String(response || "").replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
                const encodedCode = encodeURIComponent(code).replace(/'/g, "%27");
                const escapedCode = escapeHtml(code);
                let html = `
                    <div class="code-block-container" style="margin: 12px 0; border-radius: 8px; border: 1px solid var(--term-border); overflow: hidden; background: var(--term-bg); box-shadow: var(--term-glow);">
                        <div class="code-block-header" style="background: var(--term-header-bg); padding: 6px 12px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--term-border); user-select: none;">
                            <span class="code-block-lang" style="font-size: 0.65rem; color: var(--term-text); font-weight: bold; text-transform: uppercase;">${lang || 'text'}</span>
                            <button class="code-block-copy-btn" onclick="copyCodeBlock(this)">
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                复制
                            </button>
                        </div>
                        <pre class="code-pre" style="margin: 0; padding: 10px; overflow-x: auto; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.78rem; color: var(--term-text); line-height: 1.4; max-width: 100%; box-sizing: border-box; background: var(--code-block-bg);"><code>${escapedCode}</code></pre>
                    </div>
                `;
                // Embedded CSP intentionally forbids frames. Do not advertise
                // a preview action which cannot load inside the Android host.
                if (window.microAgiEmbedded === false &&
                        (lang.toLowerCase() === 'html' || lang.toLowerCase() === 'htm')) {
                    html += `<div style="margin-bottom: 8px;"><button class="tool-btn" style="font-size: 0.75rem; padding: 6px 12px; display: inline-flex; align-items: center; gap: 6px;" onclick="openLivePreview(decodeURIComponent('${encodedCode}'))">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                        沙盒预览 (Split-Screen)
                    </button></div>`;
                }
                return `\u0000CODE_${codeBlocks.push(html) - 1}\u0000`;
            });
            // Fallback for ``` without lang
            parsedContent = parsedContent.replace(/```([\s\S]*?)```/g, function(match, code) {
                const escapedCode = escapeHtml(code);
                const html = `
                    <div class="code-block-container" style="margin: 12px 0; border-radius: 8px; border: 1px solid var(--term-border); overflow: hidden; background: var(--term-bg); box-shadow: var(--term-glow);">
                        <div class="code-block-header" style="background: var(--term-header-bg); padding: 6px 12px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--term-border); user-select: none;">
                            <span class="code-block-lang" style="font-size: 0.65rem; color: var(--term-text); font-weight: bold; text-transform: uppercase;">text</span>
                            <button class="code-block-copy-btn" onclick="copyCodeBlock(this)">
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                复制
                            </button>
                        </div>
                        <pre class="code-pre" style="margin: 0; padding: 10px; overflow-x: auto; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.78rem; color: var(--term-text); line-height: 1.4; max-width: 100%; box-sizing: border-box; background: var(--code-block-bg);"><code>${escapedCode}</code></pre>
                    </div>
                `;
                return `\u0000CODE_${codeBlocks.push(html) - 1}\u0000`;
            });
            parsedContent = escapeHtml(parsedContent);
            parsedContent = parsedContent.replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.1); padding: 2px 4px; border-radius: 4px; color: #fbd38d;">$1</code>');
            parsedContent = parsedContent.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
            parsedContent = parsedContent.replace(/\n/g, '<br>');
            parsedContent = parsedContent.replace(/\u0000CODE_(\d+)\u0000/g, (_, index) => codeBlocks[Number(index)] || "");

            const stepsHtml = (steps || []).map((step, idx) => {
                const stepId = `step-detail-${Date.now()}-${idx}`;
                const isSuccess = step.exit_code === 0;
                const statusColor = isSuccess ? '#27c93f' : '#ff5f56';
                const statusText = isSuccess ? '✅ SUCCESS' : '❌ FAILED';
                
                return `
                    <div class="terminal-card" style="background: var(--term-bg); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); border-radius: 10px; border: 1px solid var(--term-border); overflow: hidden; margin: 12px 0 4px 0; box-shadow: var(--term-glow), 0 4px 16px rgba(0,0,0,0.4);">
                        <div class="terminal-header" onclick="toggleStepDetails('${stepId}')" style="background: var(--term-header-bg); padding: 8px 12px; display: flex; align-items: center; cursor: pointer; border-bottom: 1px solid var(--term-border); transition: background 0.2s;">
                            <div style="display: flex; gap: 6px; margin-right: 12px;">
                                <div style="width: 10px; height: 10px; border-radius: 50%; background: #ff5f56; box-shadow: inset 0 0 2px rgba(0,0,0,0.5);"></div>
                                <div style="width: 10px; height: 10px; border-radius: 50%; background: #ffbd2e; box-shadow: inset 0 0 2px rgba(0,0,0,0.5);"></div>
                                <div style="width: 10px; height: 10px; border-radius: 50%; background: #27c93f; box-shadow: inset 0 0 2px rgba(0,0,0,0.5);"></div>
                            </div>
                            <div style="font-size: 0.75rem; color: var(--term-text); font-family: 'Consolas', 'Monaco', monospace; flex-grow: 1; text-align: center; letter-spacing: 0.5px;">TERMINAL EXECUTION</div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 0.7rem; color: ${statusColor}; font-weight: 700; letter-spacing: 0.5px;">${statusText}</span>
                                <button class="term-copy-btn" onclick="event.stopPropagation(); copyTerminalOutput(this, '${stepId}')">
                                    复制结果
                                </button>
                            </div>
                        </div>
                        <div class="step-details" id="${stepId}" style="display:block;">
                            <div style="padding: 12px;">
                                <div style="color: var(--term-cmd-text); font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem; margin-bottom: 10px; word-break: break-all; font-weight: 600; text-shadow: var(--term-glow);">
                                    <span style="color: #4a5568; margin-right: 6px; user-select: none;">$</span>${escapeHtml(step.command)}
                                </div>
                                <div style="background: var(--code-block-bg); border-radius: 6px; border: 1px solid var(--term-border); border-left: 2px solid ${statusColor}; max-height: 250px; overflow-y: auto; overflow-x: auto;">
                                    <pre class="term-output-text" style="margin: 0; padding: 10px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.75rem; color: var(--term-text); white-space: pre-wrap; word-wrap: break-word; line-height: 1.4;">${formatTerminalOutput(step.output)}</pre>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
            
            appendMessage("assistant", "Micro-AGI", parsedContent + (stepsHtml ? `<div class="execution-steps">${stepsHtml}</div>` : ""), true);
            triggerMotionByText(response);
        }

        function toggleWeChatAccordion() {
            const section = document.getElementById('wechat-menu-section');
            const arrow = document.getElementById('wechat-accordion-arrow');
            if (section.style.display === 'none') {
                section.style.display = 'block';
                arrow.style.transform = 'rotate(90deg)';
            } else {
                section.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            }
        }

        let wechatPollInterval = null;

        function startWeChatPolling() {
            if (wechatPollInterval) return;
            checkWeChatStatus();
            wechatPollInterval = setInterval(checkWeChatStatus, 5000);
        }

        function stopWeChatPolling() {
            if (wechatPollInterval) {
                clearInterval(wechatPollInterval);
                wechatPollInterval = null;
            }
        }

        async function checkWeChatStatus() {
            try {
                const response = await fetch("/api/wechat/status");
                const data = await response.json();
                
                const indicator = document.getElementById("wechat-status-indicator");
                const userItem = document.getElementById("wechat-user-item");
                const userVal = document.getElementById("wechat-user-val");
                const clearBtn = document.getElementById("wechat-clear-btn");
                const qrBtn = document.getElementById("wechat-qr-btn");
                const qrBtnText = document.getElementById("wechat-qr-btn-text");
                const qrDisplay = document.getElementById("wechat-qr-display");

                if (data.status === "configured") {
                    if (indicator) {
                        indicator.textContent = "✅ 已连接";
                        indicator.style.color = "var(--success)";
                        indicator.style.background = "rgba(16, 185, 129, 0.15)";
                    }
                    userItem.style.display = "flex";
                    userVal.textContent = data.bot_id || "-";
                    
                    const pushRulesSection = document.getElementById("wechat-push-rules-section");
                    const pushRulesInput = document.getElementById("wechat-push-rules-input");
                    if (pushRulesSection) pushRulesSection.style.display = "flex";
                    if (pushRulesInput && document.activeElement !== pushRulesInput) pushRulesInput.value = data.push_rules || "";
                    
                    const approvalChk = document.getElementById("wechat-push-approval");
                    if (approvalChk) approvalChk.checked = (data.push_approval === "true");
                    const errorChk = document.getElementById("wechat-push-error");
                    if (errorChk) errorChk.checked = (data.push_error === "true");
                    const successChk = document.getElementById("wechat-push-success");
                    if (successChk) successChk.checked = (data.push_success === "true");
                    const batteryChk = document.getElementById("wechat-push-battery");
                    if (batteryChk) batteryChk.checked = (data.push_battery === "true");
                    
                    clearBtn.style.display = "flex";
                    qrBtn.disabled = false;
                    qrBtnText.textContent = "📷 重新生成授权链接";
                    qrDisplay.style.display = "none";
                } else {
                    if (indicator) {
                        indicator.textContent = "未配置";
                        indicator.style.color = "var(--text-muted)";
                        indicator.style.background = "rgba(255,255,255,0.1)";
                    }
                    userItem.style.display = "none";
                    clearBtn.style.display = "none";
                }
            } catch (err) {
                console.error("Failed to fetch WeChat status:", err);
            }
        }

        async function generateWeChatQR() {
            const btn = document.getElementById("wechat-qr-btn");
            const btnText = document.getElementById("wechat-qr-btn-text");
            const display = document.getElementById("wechat-qr-display");
            const link = document.getElementById("wechat-qr-link");
            
            try {
                btn.disabled = true;
                btnText.textContent = "⏳ 正在获取...";
                
                const response = await fetch("/api/wechat/qr_login", { method: "POST" });
                const data = await response.json();
                
                if (data.url) {
                    display.style.display = "block";
                    link.href = data.url;
                    btnText.textContent = "✅ 链接已生成";
                    startWeChatPolling();
                } else {
                    alert("获取二维码失败: " + (data.error || "未知错误"));
                    btn.disabled = false;
                    btnText.textContent = "📷 生成授权链接";
                }
            } catch (err) {
                alert("请求失败，请检查服务。");
                btn.disabled = false;
                btnText.textContent = "📷 生成授权链接";
            }
        }

        async function saveWeChatPushRules() {
            const rulesInput = document.getElementById("wechat-push-rules-input");
            const approvalChk = document.getElementById("wechat-push-approval");
            const errorChk = document.getElementById("wechat-push-error");
            const successChk = document.getElementById("wechat-push-success");
            const batteryChk = document.getElementById("wechat-push-battery");
            const saveBtn = document.getElementById("wechat-push-save-btn");
            
            saveBtn.disabled = true;
            saveBtn.innerHTML = "⏳...";
            
            try {
                const response = await fetch("/api/wechat/config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ 
                        push_rules: rulesInput.value,
                        push_approval: approvalChk ? approvalChk.checked : false,
                        push_error: errorChk ? errorChk.checked : false,
                        push_success: successChk ? successChk.checked : false,
                        push_battery: batteryChk ? batteryChk.checked : false
                    })
                });
                const data = await response.json();
                if (data.ok) {
                    saveBtn.innerHTML = "✅ 已保存";
                    setTimeout(() => { saveBtn.disabled = false; saveBtn.innerHTML = "保存设置"; }, 2000);
                } else {
                    alert("保存失败: " + data.message);
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = "保存设置";
                }
            } catch (err) {
                alert("请求出错: " + err.message);
                saveBtn.disabled = false;
                saveBtn.innerHTML = "保存设置";
            }
        }

        async function clearWeChatConfig() {
            if (!confirm("确定要清除微信配置并断开连接吗？")) return;
            const clearBtn = document.getElementById("wechat-clear-btn");
            clearBtn.disabled = true;
            try {
                const response = await fetch("/api/wechat/stop", { method: "POST" });
                const data = await response.json();
                if (data.ok) alert("微信配置清除成功！");
                checkWeChatStatus();
            } catch (err) { alert("请求出错: " + err.message); }
            finally { clearBtn.disabled = false; }
        }

        function openMoreMenu() {
            const menuEl = document.getElementById("more-menu-drawer");
            const backdrop = document.getElementById("menuBackdrop");
            menuEl.style.display = "flex";
            menuEl.offsetHeight;
            menuEl.classList.add("open");
            backdrop.classList.add("open");
            
            // Sync checkbox states
            const voiceChk = document.getElementById('settings-voice-checkbox');
            if (voiceChk) {
                voiceChk.checked = !!isVoiceEnabled;
            }
            const chatChk = document.getElementById('settings-chat-checkbox');
            if (chatChk) {
                const container = document.querySelector(".main-container");
                chatChk.checked = container ? container.classList.contains("chat-collapsed") : false;
            }
            checkTunnelStatus(); // Fetch tunnel status on open
            
            startWeChatPolling();

            // Restore last settings tab (default 总控=0); refresh AIOS status
            try {
                let tab = parseInt(localStorage.getItem('micro-agi-settings-tab') || '0', 10);
                if (isNaN(tab) || tab < 0 || tab > 4) tab = 0;
                if (typeof switchSettingsTab === 'function') switchSettingsTab(tab);
            } catch (e) {
                if (typeof switchSettingsTab === 'function') switchSettingsTab(0);
            }
            if (typeof aiosLoadStatus === 'function') {
                setTimeout(aiosLoadStatus, 120);
            }
        }

        function closeMoreMenu() {
            const menuEl = document.getElementById("more-menu-drawer");
            const backdrop = document.getElementById("menuBackdrop");
            menuEl.classList.remove("open");
            setTimeout(() => { menuEl.style.display = "none"; }, 300);
            backdrop.classList.remove("open");
            stopWeChatPolling();
        }

        function toggleMoreMenu() {
            const menuEl = document.getElementById("more-menu-drawer");
            
            // Close workspace console if open
            const consoleDrawer = document.getElementById('workspaceConsoleDrawer');
            const consoleOverlay = document.getElementById('workspaceConsoleOverlay');
            if (consoleDrawer && consoleDrawer.classList.contains('active')) {
                consoleDrawer.classList.remove('active');
                if (consoleOverlay) consoleOverlay.classList.remove('active');
            }
            
            menuEl.classList.contains("open") ? closeMoreMenu() : openMoreMenu();
        }

        function handleMenuAction(action) {
            closeMoreMenu();
            setTimeout(() => {
                if (action === 'clear-chat') {
                    if (confirm("确定要清理当前对话记录吗？")) {
                        chatArea.innerHTML = "";
                        chatHistory = [];
                        appendMessage("assistant", "Hiyori", "对话已清理。你好，有什么我可以帮你的吗？🌸");
                    }
                } else if (action === 'reload-avatar') {
                    initLive2D();
                } else if (action === 'toggle-chat') {
                    toggleChatLogs();
                } else if (action === 'open-tools') {
                    openToolsPanel();
                }
            }, 300);
        }

        function openToolsPanel() {
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (!drawer.classList.contains('active')) {
                toggleWorkspaceConsole();
            }
            switchConsoleTab(1);
        }

        function closeToolsPanel() {
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (drawer.classList.contains('active')) {
                toggleWorkspaceConsole();
            }
        }

        function toggleToolsPanel() {
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (drawer.classList.contains('active')) {
                const activeTab = document.querySelector('.console-tab.active');
                const tabs = document.querySelectorAll('.console-tab');
                if (activeTab === tabs[1]) {
                    toggleWorkspaceConsole();
                } else {
                    switchConsoleTab(1);
                }
            } else {
                toggleWorkspaceConsole();
                switchConsoleTab(1);
            }
        }

        function toggleChatLogs() {
            const container = document.querySelector(".main-container");
            if (!container) return;
            
            const chk = document.getElementById('settings-chat-checkbox');
            let isCollapsed;
            if (chk) {
                isCollapsed = chk.checked;
                if (isCollapsed) {
                    container.classList.add("chat-collapsed");
                } else {
                    container.classList.remove("chat-collapsed");
                }
            } else {
                isCollapsed = container.classList.toggle("chat-collapsed");
            }
            
            // Sync checkbox
            const settingsChk = document.getElementById('settings-chat-checkbox');
            if (settingsChk) settingsChk.checked = isCollapsed;
            
            // Update eye SVG icon (if any, though it's removed, we guard it)
            const eyeIcon = document.getElementById("eye-icon");
            if (eyeIcon) {
                if (isCollapsed) {
                    eyeIcon.innerHTML = `
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                    `;
                } else {
                    eyeIcon.innerHTML = `
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                    `;
                }
            }
            
            if (!isCollapsed) {
                setTimeout(() => {
                    chatArea.scrollTop = chatArea.scrollHeight;
                }, 150);
            }
        }

        function triggerVideoDownload() {
            const urlInput = document.getElementById("tool-video-url");
            const url = urlInput.value.trim();
            if (!url) {
                alert("请输入视频链接！");
                return;
            }
            urlInput.value = "";
            closeToolsPanel();
            
            chatInput.value = `[快捷下载视频] 请帮我运行 yt-dlp 视频下载工具。将此视频下载并自动保存到手机的公共 Download 文件夹下，视频链接为：${url}`;
            sendMessage();
        }

        function triggerWallpaperChange() {
            closeToolsPanel();
            chatInput.value = "[一键壁纸更换] 请从 Bing 官网获取今天的每日高清主图，并使用 termux-wallpaper 工具自动将其设置为我的手机桌面壁纸。";
            sendMessage();
        }

        function triggerSkill(skillType) {
            // Close consolidated drawer if open
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (drawer && drawer.classList.contains('active')) {
                toggleWorkspaceConsole();
            }
            
            let skillName = "";
            if (skillType === 'search') skillName = "实时全网检索";
            else if (skillType === 'bilibili') skillName = "B站视频摘要";
            else if (skillType === 'github') skillName = "代码分析师";
            
            // Add as a special attachment
            const attId = 'att-skill-' + Date.now();
            
            // Check if already added
            if (pendingAttachments.some(a => a.type === 'skill' && a.data === skillType)) {
                return; // Already added
            }

            const attObj = {
                id: attId,
                name: skillName,
                type: 'skill',
                data: skillType, // storing the skill identifier
                progress: 100,
                status: 'done'
            };
            
            pendingAttachments.push(attObj);
            renderAttachmentsPreview();
        }


        function triggerTTS() {
            const textInput = document.getElementById("tool-tts-text");
            const text = textInput.value.trim();
            if (!text) {
                alert("请输入朗读文本！");
                return;
            }
            textInput.value = "";
            closeToolsPanel();
            
            chatInput.value = `[语音朗读播报] 请调用 termux-tts-speak 工具，用大声、清晰的普通话帮我朗读以下文本："${text}"`;
            sendMessage();
        }

        function triggerCleanUpScan() {
            closeToolsPanel();
            chatInput.value = "[系统清理扫描] 请分析 Termux 中的日志目录、缓存文件等临时文件夹的大小，并给出一份安全的垃圾清理方案建议。";
            sendMessage();
        }

        // ==========================================
        // Mobile Hardware Control Functions
        // ==========================================
        let isHardwareTorchOn = false;
        async function toggleHardwareTorch() {
            const btn = document.getElementById("hw-torch-btn");
            const newStatus = isHardwareTorchOn ? "off" : "on";
            try {
                const response = await fetch("/api/hardware/torch", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ status: newStatus })
                });
                const data = await response.json();
                if (data.ok) {
                    isHardwareTorchOn = !isHardwareTorchOn;
                    if (isHardwareTorchOn) {
                        btn.innerText = "🔦 关闭手电筒";
                        btn.style.background = "linear-gradient(135deg, #eab308, #ca8a04)";
                    } else {
                        btn.innerText = "🔦 开启手电筒";
                        btn.style.background = "linear-gradient(135deg, #f59e0b, #d97706)";
                    }
                } else {
                    alert("手电筒控制失败: " + (data.error || "未知错误"));
                }
            } catch (e) {
                console.error("手电筒控制请求失败", e);
                alert("请求失败，请检查网络或服务端状态");
            }
        }

        async function triggerHardwareVibrate() {
            const durationInput = document.getElementById("hw-vibrate-duration");
            const duration = parseInt(durationInput.value) || 200;
            try {
                const response = await fetch("/api/hardware/vibrate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ duration: duration })
                });
                const data = await response.json();
                if (!data.ok) {
                    alert("震动触发失败: " + (data.error || "未知错误"));
                }
            } catch (e) {
                console.error("震动控制请求失败", e);
            }
        }

        async function refreshHardwareBattery() {
            try {
                const response = await fetch("/api/hardware/battery");
                const data = await response.json();
                document.getElementById("hw-battery-percentage").innerText = (data.percentage !== undefined ? data.percentage : "--") + " %";
                document.getElementById("hw-battery-status").innerText = data.status || "--";
                document.getElementById("hw-battery-temp").innerText = (data.temperature !== undefined ? data.temperature : "--") + " °C";
                document.getElementById("hw-battery-health").innerText = data.health || "--";
                
                const warningDiv = document.getElementById("hw-battery-warning");
                if (data.warning) {
                    warningDiv.style.display = "flex";
                } else {
                    warningDiv.style.display = "none";
                }
            } catch (e) {
                console.error("电池状态获取失败", e);
            }
        }

        async function pullHardwareClipboard() {
            try {
                const response = await fetch("/api/hardware/clipboard");
                const data = await response.json();
                if (data.text !== undefined) {
                    document.getElementById("hw-clipboard-text").value = data.text;
                }
            } catch (e) {
                console.error("剪贴板拉取失败", e);
            }
        }

        async function pushHardwareClipboard() {
            const textarea = document.getElementById("hw-clipboard-text");
            const text = textarea.value;
            try {
                const response = await fetch("/api/hardware/clipboard", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: text })
                });
                const data = await response.json();
                if (data.ok) {
                    showToast("写入手机剪贴板成功！");
                } else {
                    alert("写入剪贴板失败: " + (data.error || "未知错误"));
                }
            } catch (e) {
                console.error("剪贴板写入请求失败", e);
                alert("请求失败，请检查服务端状态");
            }
        }

        // ==========================================
        // Live2D Avatar Render Engine & TTS (PIXI.js)
        // ==========================================
        let live2dApp, live2dModel, live2dContainer;
        let isVoiceEnabled = false;
        let speechUtterance = null;
        let isSpeaking = false;
        let targetMouthOpen = 0;
        let currentMouthOpen = 0;
        let lipSyncTimer = null;
        let lipSyncAnimationId = null;
        let welcomeBubbleTimeout = null;

        let gazeTargetX = window.innerWidth / 2;
        let gazeTargetY = window.innerHeight / 2;
        let gazeCurrentX = window.innerWidth / 2;
        let gazeCurrentY = window.innerHeight / 2;
        function gazeTrackingUpdate() {
            if (live2dModel) {
                gazeCurrentX += (gazeTargetX - gazeCurrentX) * 0.08;
                gazeCurrentY += (gazeTargetY - gazeCurrentY) * 0.08;
                live2dModel.focusOn(gazeCurrentX, gazeCurrentY);
            }
        }

        function mouthSyncUpdate() {
            if (isSpeaking && live2dModel && live2dModel.internalModel && live2dModel.internalModel.coreModel) {
                currentMouthOpen += (targetMouthOpen - currentMouthOpen) * 0.22;
                currentMouthOpen = Math.max(0, Math.min(1, currentMouthOpen));
                live2dModel.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', currentMouthOpen);
            }
        }

        function handleModelTap(event) {
            if (!live2dModel) return;
            
            // Get local tap coordinate ratios relative to the model bounds
            const localPoint = event.data.getLocalPosition(live2dModel);
            const ratioY = localPoint.y / (live2dModel.originalHeight || live2dModel.height || 400);
            const ratioX = localPoint.x / (live2dModel.originalWidth || live2dModel.width || 400);
            
            let randomMotion = '';
            let randomText = '';
            
            if (ratioY < 0.35) {
                // Head / Face Tap
                if (ratioX < 0.35) {
                    // Right Ear / Hair Tap
                    const rightReplies = [
                        "哎呀，不要拉我的右边耳朵啦，痒痒的～👂",
                        "唔……主人的手碰到我的右发带了，是不是歪了？🎀",
                        "右边耳朵好像听到了悄悄话哦～"
                    ];
                    randomText = rightReplies[Math.floor(Math.random() * rightReplies.length)];
                    randomMotion = 'Tap'; // Head movement
                } else if (ratioX > 0.65) {
                    // Left Ear / Hair Tap
                    const leftReplies = [
                        "左边耳朵也很敏感的哦，主人坏心眼～👂",
                        "摸我的左耳……是要跟我说什么悄悄话吗？",
                        "头发被碰乱了啦，等下要主人帮我重新扎好！🎀"
                    ];
                    randomText = leftReplies[Math.floor(Math.random() * leftReplies.length)];
                    randomMotion = 'Tap';
                } else {
                    // Center Face / Forehead Tap
                    const faceReplies = [
                        "唔……摸摸头，感觉超级暖和呢～🌸",
                        "哎呀，主人不可以一直盯着我的脸看啦，会害羞的……😳",
                        "脑门被弹了一下！哼，主人大坏蛋～",
                        "额头贴贴！感觉今天温度刚好哦～✨"
                    ];
                    randomText = faceReplies[Math.floor(Math.random() * faceReplies.length)];
                    randomMotion = 'Tap';
                }
            } else if (ratioY >= 0.35 && ratioY < 0.75) {
                // Body / Hands Tap
                if (ratioX < 0.3) {
                    // Right Hand / Arm Tap
                    const rightHandReplies = [
                        "右手给你牵着，要带我去哪里冒险吗？🤝",
                        "牵拉右手，我们达成AI和人类的特别协定啦！",
                        "这是在跟我握手吗？你好呀，主人！✨"
                    ];
                    randomText = rightHandReplies[Math.floor(Math.random() * rightHandReplies.length)];
                    randomMotion = 'Flick';
                } else if (ratioX > 0.7) {
                    // Left Hand / Arm Tap
                    const leftHandReplies = [
                        "左手被牵住了……不许放开哦，我们要一直在一起～🤝",
                        "左边手臂痒痒的，主人在做什么小动作呢？",
                        "嘿哈！击个掌吧，今天的工作也要加油哦！🙌"
                    ];
                    randomText = leftHandReplies[Math.floor(Math.random() * leftHandReplies.length)];
                    randomMotion = 'Flick';
                } else {
                    // Chest / Belly Tap
                    const bodyReplies = [
                        "主人戳我肚子，感觉痒痒的～嘻嘻。😆",
                        "怎么啦？有什么任务需要我立刻在 Termux 运行吗？💻",
                        "摸摸衣服，今天这一身未来感风格的打扮你喜欢吗？👚",
                        "戳肚子……是不是在提醒我该吃下午茶了？🍰"
                    ];
                    randomText = bodyReplies[Math.floor(Math.random() * bodyReplies.length)];
                    randomMotion = Math.random() > 0.5 ? 'Tap@Body' : 'Flick';
                }
            } else {
                // Lower Skirt / Legs Tap
                const lowerReplies = [
                    "哇！主人碰我的裙子了，不可以做奇怪的事哦～⚠️",
                    "嘻嘻，脚底痒痒的，主人别闹啦～",
                    "哎呀，差点站不稳了，主人快扶我一下！"
                ];
                randomText = lowerReplies[Math.floor(Math.random() * lowerReplies.length)];
                randomMotion = 'Flick@Body';
            }
            
            live2dModel.motion(randomMotion);
            if (isPetMode()) {
                showPetMiniBubble(randomText);
            } else {
                showWelcomeBubble(randomText);
            }
            
            if (isVoiceEnabled) {
                speakText(randomText);
            }
        }

        function triggerMotionByText(text) {
            if (!live2dModel || !text) return;
            
            const lowerText = text.toLowerCase();
            let selectedMotion = 'Idle';
            
            if (lowerText.includes('错') || lowerText.includes('坏') || lowerText.includes('警告') || lowerText.includes('危险') || lowerText.includes('失败') || lowerText.includes('error')) {
                selectedMotion = 'Flick@Body';
            } else if (lowerText.includes('好') || lowerText.includes('成功') || lowerText.includes('完成') || lowerText.includes('完成啦') || lowerText.includes('喜') || lowerText.includes('谢')) {
                selectedMotion = 'Tap@Body';
            } else if (lowerText.includes('听') || lowerText.includes('问') || lowerText.includes('想') || lowerText.includes('思考') || lowerText.includes('呢')) {
                selectedMotion = 'Tap';
            } else if (lowerText.includes('跑') || lowerText.includes('启动') || lowerText.includes('运行') || lowerText.includes('命令行')) {
                selectedMotion = 'Flick';
            } else {
                // Random motion
                selectedMotion = Math.random() > 0.5 ? 'Tap' : 'Idle';
            }
            
            try {
                live2dModel.motion(selectedMotion);
            } catch (e) {
                console.error("Failed to trigger Live2D motion:", e);
            }
        }

        function showWelcomeBubble(text) {
            let bubble = document.getElementById('welcome-bubble');
            if (!bubble) {
                const tabChat = document.getElementById('tab-content-chat');
                if (!tabChat) return;
                bubble = document.createElement('div');
                bubble.id = 'welcome-bubble';
                bubble.className = 'welcome-bubble';
                bubble.innerHTML = `
                    <div class="welcome-bubble-bg"></div>
                    <div class="welcome-bubble-pointer"></div>
                    <div class="welcome-bubble-text"></div>
                `;
                tabChat.appendChild(bubble);
            }

            if (welcomeBubbleTimeout) {
                clearTimeout(welcomeBubbleTimeout);
                welcomeBubbleTimeout = null;
            }

            const textEl = bubble.querySelector('.welcome-bubble-text');
            if (textEl) textEl.textContent = text;
            bubble.classList.remove('fade-out');

            adjustModelLayout();

            welcomeBubbleTimeout = setTimeout(() => {
                bubble.classList.add('fade-out');
            }, 5500);
        }

        function adjustModelLayout() {
            if (!live2dModel || !live2dContainer) return;
            
            // Force PIXI to resize its renderer to the container's current dimensions
            if (live2dApp && typeof live2dApp.resize === 'function') {
                live2dApp.resize();
            }
            
            // Use cached original width/height to avoid resizing back and forth, preventing distortion/errors
            const nativeWidth = live2dModel.originalWidth || live2dModel.width || 400;
            const nativeHeight = live2dModel.originalHeight || live2dModel.height || 400;
            
            const baseScale = nativeHeight > 0 ? (live2dContainer.clientHeight / nativeHeight) : 0.5;
            const isMobile = live2dContainer.clientWidth < 600;
            const isPet = document.body.classList.contains('pet-mode');
            // 桌宠模式：尽量填满小窗；正常模式保持原有构图
            const zoomScale = isPet
                ? baseScale * 1.35
                : baseScale * (isMobile ? 1.5 : 1.65);
            live2dModel.scale.set(zoomScale);
            
            live2dModel.x = (live2dContainer.clientWidth - (nativeWidth * zoomScale)) / 2;
            live2dModel.y = isPet ? (live2dContainer.clientHeight * 0.02) : 20;

            if (isPet) return; // 桌宠模式用迷你气泡，不走大气泡定位

            const positionBubble = (id, targetMobileW, targetDesktopW) => {
                const bubbleEl = document.getElementById(id);
                if (bubbleEl) {
                    const headX = live2dContainer.clientWidth / 2;
                    const headY = live2dModel.y + (nativeHeight * 0.14) * zoomScale;
                    
                    const offsetX = isMobile ? 22 : 40;
                    const leftPos = headX + offsetX;
                    bubbleEl.style.left = `${leftPos}px`;
                    
                    const maxAllowedWidth = live2dContainer.clientWidth - leftPos - 12;
                    const targetMaxWidth = isMobile ? targetMobileW : targetDesktopW;
                    bubbleEl.style.maxWidth = `${Math.max(100, Math.min(targetMaxWidth, maxAllowedWidth))}px`;
                    bubbleEl.style.top = `${headY}px`;
                }
            };

            positionBubble('welcome-bubble', 155, 185);
            positionBubble('approval-bubble', 170, 260);
        }

        // ---------- 桌宠模式（App 内悬浮小人） ----------
        let petDragBound = false;
        let petBubbleTimer = null;

        function isPetMode() {
            return document.body.classList.contains('pet-mode');
        }

        function ensurePetFab() {
            const container = document.querySelector('.avatar-container');
            if (!container) return;
            let fab = container.querySelector('.pet-mode-fab');
            if (!fab) {
                fab = document.createElement('button');
                fab.type = 'button';
                fab.className = 'pet-mode-fab';
                fab.title = '退出桌宠';
                fab.textContent = '✕';
                fab.addEventListener('click', (e) => {
                    e.stopPropagation();
                    togglePetMode(false);
                });
                container.appendChild(fab);
            }
        }

        function showPetMiniBubble(text) {
            if (!isPetMode() || !text) return;
            let el = document.getElementById('pet-mini-bubble');
            if (!el) {
                el = document.createElement('div');
                el.id = 'pet-mini-bubble';
                el.className = 'pet-mini-bubble';
                document.body.appendChild(el);
            }
            el.textContent = text;
            const box = document.querySelector('.avatar-container');
            if (box) {
                const r = box.getBoundingClientRect();
                // 气泡优先放在桌宠左侧
                const left = Math.max(8, r.left - 158);
                const top = Math.max(8, r.top + 12);
                el.style.left = left + 'px';
                el.style.top = top + 'px';
            }
            el.classList.add('show');
            if (petBubbleTimer) clearTimeout(petBubbleTimer);
            petBubbleTimer = setTimeout(() => el.classList.remove('show'), 4200);
        }

        function bindPetDrag() {
            if (petDragBound) return;
            const box = document.querySelector('.avatar-container');
            if (!box) return;
            petDragBound = true;
            let dragging = false;
            let startX = 0, startY = 0, origLeft = 0, origTop = 0;
            let moved = false;

            const onDown = (e) => {
                if (!isPetMode()) return;
                // 点关闭按钮不拖
                if (e.target && e.target.closest && e.target.closest('.pet-mode-fab')) return;
                const pt = e.touches ? e.touches[0] : e;
                dragging = true;
                moved = false;
                startX = pt.clientX;
                startY = pt.clientY;
                const r = box.getBoundingClientRect();
                origLeft = r.left;
                origTop = r.top;
                box.classList.add('pet-dragging');
                e.preventDefault();
            };
            const onMove = (e) => {
                if (!dragging || !isPetMode()) return;
                const pt = e.touches ? e.touches[0] : e;
                const dx = pt.clientX - startX;
                const dy = pt.clientY - startY;
                if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
                let nx = origLeft + dx;
                let ny = origTop + dy;
                const maxX = window.innerWidth - box.offsetWidth - 4;
                const maxY = window.innerHeight - box.offsetHeight - 4;
                nx = Math.max(4, Math.min(maxX, nx));
                ny = Math.max(4, Math.min(maxY, ny));
                box.style.left = nx + 'px';
                box.style.top = ny + 'px';
                box.style.right = 'auto';
                box.style.bottom = 'auto';
            };
            const onUp = () => {
                if (!dragging) return;
                dragging = false;
                box.classList.remove('pet-dragging');
                // 记住位置
                try {
                    const r = box.getBoundingClientRect();
                    localStorage.setItem('micro-agi-pet-pos', JSON.stringify({ left: r.left, top: r.top }));
                } catch (err) {}
            };

            box.addEventListener('pointerdown', onDown);
            window.addEventListener('pointermove', onMove);
            window.addEventListener('pointerup', onUp);
            box.addEventListener('touchstart', onDown, { passive: false });
            window.addEventListener('touchmove', onMove, { passive: false });
            window.addEventListener('touchend', onUp);
        }

        function applyPetPosition() {
            const box = document.querySelector('.avatar-container');
            if (!box || !isPetMode()) return;
            try {
                const raw = localStorage.getItem('micro-agi-pet-pos');
                if (raw) {
                    const p = JSON.parse(raw);
                    if (typeof p.left === 'number' && typeof p.top === 'number') {
                        box.style.left = p.left + 'px';
                        box.style.top = p.top + 'px';
                        box.style.right = 'auto';
                        box.style.bottom = 'auto';
                        return;
                    }
                }
            } catch (e) {}
            // 默认右下角
            box.style.left = 'auto';
            box.style.top = 'auto';
            box.style.right = '10px';
            box.style.bottom = 'calc(88px + env(safe-area-inset-bottom, 0px))';
        }

        function togglePetMode(enabled) {
            const on = !!enabled;
            document.body.classList.toggle('pet-mode', on);
            const chk = document.getElementById('settings-pet-checkbox');
            if (chk) chk.checked = on;
            try { localStorage.setItem('micro-agi-pet-mode', on ? '1' : '0'); } catch (e) {}

            if (on) {
                // 桌宠与「折叠对话」互斥：桌宠时要看聊天
                const chatChk = document.getElementById('settings-chat-checkbox');
                if (chatChk && chatChk.checked) {
                    chatChk.checked = false;
                    toggleChatLogs();
                }
                ensurePetFab();
                bindPetDrag();
                applyPetPosition();
                showPetMiniBubble('桌宠模式已开启，拖我可以换位置～');
            } else {
                const box = document.querySelector('.avatar-container');
                if (box) {
                    box.style.left = '';
                    box.style.top = '';
                    box.style.right = '';
                    box.style.bottom = '';
                }
                const mini = document.getElementById('pet-mini-bubble');
                if (mini) mini.classList.remove('show');
            }
            // 等布局生效后再缩放模型
            requestAnimationFrame(() => {
                setTimeout(() => adjustModelLayout(), 50);
            });
        }

        // 恢复桌宠设置
        (function restorePetMode() {
            try {
                if (localStorage.getItem('micro-agi-pet-mode') === '1') {
                    // 等 DOM/模型准备好后再开
                    setTimeout(() => togglePetMode(true), 800);
                }
            } catch (e) {}
        })();

        async function initLive2D() {
            const status = document.getElementById('live2d-status');
            const showLive2DError = (message) => {
                if (status) {
                    status.textContent = message;
                    status.hidden = false;
                }
            };
            if (typeof PIXI === 'undefined' || typeof PIXI.live2d === 'undefined') {
                console.warn("WebGL libraries (PIXI.js / pixi-live2d-display) failed to load. Running in text-only mode.");
                showLive2DError('角色库未加载，请重新打开应用。');
                return;
            }
            const canvas = document.getElementById('vrm-canvas');
            if (!canvas) return;
            live2dContainer = canvas.parentElement;
            
            try {
                window.PIXI = PIXI;
                const isAndroid = /Android/i.test(navigator.userAgent);
                
                live2dApp = new PIXI.Application({
                    view: canvas,
                    transparent: true,
                    autoStart: true,
                    antialias: !isAndroid,
                    resizeTo: live2dContainer,
                    resolution: isAndroid ? 1 : (window.devicePixelRatio || 1)
                });
                
                console.log("Loading Live2D model (Hiyori)...");
                const modelUrl = '/Hiyori/Hiyori.model3.json';
                
                live2dModel = await PIXI.live2d.Live2DModel.from(modelUrl);
                
                // Store original dimensions before scaling to prevent distortion during updates
                live2dModel.originalWidth = live2dModel.width;
                live2dModel.originalHeight = live2dModel.height;
                
                live2dApp.stage.addChild(live2dModel);
                
                // Add interactive tap behavior to model
                live2dModel.buttonMode = true;
                live2dModel.interactive = true;
                live2dModel.on('pointertap', handleModelTap);
                
                adjustModelLayout();
                
                // Register smooth gaze tracking update loop
                live2dModel.on('update', gazeTrackingUpdate);
                
                let idleGazeTimeout = null;
                const updateGaze = (x, y) => {
                    gazeTargetX = x;
                    gazeTargetY = y;
                    
                    if (idleGazeTimeout) clearTimeout(idleGazeTimeout);
                    idleGazeTimeout = setTimeout(() => {
                        const r = canvas.getBoundingClientRect();
                        gazeTargetX = r.left + r.width / 2;
                        gazeTargetY = r.top + r.height / 2;
                    }, 4000);
                };
                window.addEventListener('pointermove', (e) => updateGaze(e.clientX, e.clientY));
                window.addEventListener('touchmove', (e) => {
                    if (e.touches && e.touches[0]) {
                        updateGaze(e.touches[0].clientX, e.touches[0].clientY);
                    }
                }, { passive: true });
                document.addEventListener('mouseleave', () => {
                    const r = canvas.getBoundingClientRect();
                    gazeTargetX = r.left + r.width / 2;
                    gazeTargetY = r.top + r.height / 2;
                });
                
                const resizeObserver = new ResizeObserver(() => {
                    adjustModelLayout();
                });
                resizeObserver.observe(live2dContainer);
                
                console.log("Live2D model loaded successfully!");
                if (status) status.hidden = true;
                
            } catch (err) {
                console.error("Live2D init error:", err);
                showLive2DError('角色加载失败：' + (err && err.message ? err.message : 'WebGL 或模型资源不可用'));
            }
        }

        // --- TTS Speech Synthesis Integration ---
        let availableVoices = [];
        let selectedVoice = null;
        let voiceRate = 1.0;
        let voicePitch = 1.1; // Default slightly higher pitch for Hiyori

        function populateVoiceList() {
            if (typeof speechSynthesis === 'undefined') return;
            availableVoices = speechSynthesis.getVoices();
            const voiceSelect = document.getElementById('voice-select');
            if (!voiceSelect) return;

            voiceSelect.innerHTML = '';
            
            // Filter Chinese voices (zh-CN, zh-HK, zh-TW, etc.)
            const filteredVoices = availableVoices.filter(v => 
                v.lang.toLowerCase().includes('zh') || 
                v.lang.toLowerCase().includes('cn')
            );
            
            const displayList = filteredVoices.length > 0 ? filteredVoices : availableVoices;
            
            displayList.forEach(v => {
                const option = document.createElement('option');
                option.value = v.name;
                
                let displayName = v.name;
                const nameLower = v.name.toLowerCase();
                // Flag high quality voices
                if (nameLower.includes('natural') || nameLower.includes('google') || nameLower.includes('xiaoxiao') || nameLower.includes('xiaoyi') || nameLower.includes('siri')) {
                    displayName += ' ⭐ (优质高保真)';
                }
                option.textContent = displayName;
                voiceSelect.appendChild(option);
            });

            // Try to set default to natural/female Chinese voice if possible
            let defaultVoice = filteredVoices.find(v => {
                const nameLower = v.name.toLowerCase();
                return nameLower.includes('xiaoxiao') || nameLower.includes('xiaoyi') || nameLower.includes('female') || nameLower.includes('google');
            });
            
            if (!defaultVoice && filteredVoices.length > 0) {
                defaultVoice = filteredVoices[0];
            }
            
            if (defaultVoice) {
                voiceSelect.value = defaultVoice.name;
                selectedVoice = defaultVoice;
            }
        }

        if (typeof speechSynthesis !== 'undefined' && speechSynthesis.onvoiceschanged !== undefined) {
            speechSynthesis.onvoiceschanged = populateVoiceList;
        }
        window.addEventListener('DOMContentLoaded', populateVoiceList);

        function changeActiveVoice() {
            const voiceSelect = document.getElementById('voice-select');
            if (!voiceSelect) return;
            const vName = voiceSelect.value;
            selectedVoice = availableVoices.find(v => v.name === vName) || null;
            
            if (isVoiceEnabled) {
                speakText("你好，这是我全新的声音哦，听起来怎么样？");
            }
        }

        function changeVoiceParams() {
            const rateInput = document.getElementById('voice-rate');
            const pitchInput = document.getElementById('voice-pitch');
            const rateVal = document.getElementById('voice-rate-val');
            const pitchVal = document.getElementById('voice-pitch-val');
            
            if (rateInput && rateVal) {
                voiceRate = parseFloat(rateInput.value);
                rateVal.textContent = voiceRate.toFixed(1);
            }
            if (pitchInput && pitchVal) {
                voicePitch = parseFloat(pitchInput.value);
                pitchVal.textContent = voicePitch.toFixed(1);
            }
        }

        function toggleVoiceSpeech() {
            const chk = document.getElementById('settings-voice-checkbox');
            if (chk) {
                isVoiceEnabled = chk.checked;
            } else {
                isVoiceEnabled = !isVoiceEnabled;
            }
            
            // Sync checkbox check state
            const settingsChk = document.getElementById('settings-voice-checkbox');
            if (settingsChk) settingsChk.checked = isVoiceEnabled;
            
            if (isVoiceEnabled) {
                showToast("语音播报已开启 🔊");
                speakText("语音播报已开启，我会为您朗读所有回复哦！");
            } else {
                stopSpeech();
                showToast("语音播报已关闭 🔇");
            }
        }

        function speakText(text) {
            stopSpeech();
            if (!text || !window.speechSynthesis ||
                typeof window.speechSynthesis.speak !== 'function' ||
                typeof SpeechSynthesisUtterance === 'undefined') return;

            // Strip code blocks and Markdown formatting to read cleanly
            let cleanText = text
                .replace(/```[\s\S]*?```/g, " [这里有一段代码已经为您保存到成果箱。] ")
                .replace(/<[^>]*>/g, "")
                .replace(/[\*\#\`\_\-\[\]\(\)]/g, " ")
                .trim();

            if (!cleanText) return;

            speechUtterance = new SpeechSynthesisUtterance(cleanText);
            if (selectedVoice) {
                speechUtterance.voice = selectedVoice;
            }
            speechUtterance.rate = voiceRate;
            speechUtterance.pitch = voicePitch;
            speechUtterance.lang = 'zh-CN';
            
            speechUtterance.onstart = () => {
                isSpeaking = true;
                startLipSync();
                triggerMotionByText(cleanText);
            };

            speechUtterance.onend = () => {
                stopSpeech();
            };

            speechUtterance.onerror = () => {
                stopSpeech();
            };

            window.speechSynthesis.speak(speechUtterance);
        }

        function stopSpeech() {
            if (window.speechSynthesis && typeof window.speechSynthesis.cancel === 'function') {
                window.speechSynthesis.cancel();
            }
            isSpeaking = false;
            stopLipSync();
        }

        function startLipSync() {
            stopLipSync();

            const ring = document.querySelector('.avatar-ring');
            if (ring) ring.classList.add('speaking');
            const backdrop = document.querySelector('.avatar-backdrop');
            if (backdrop) backdrop.classList.add('speaking');
            
            // Update target mouth opening every 220ms (slowed down for natural speech syllable rhythm)
            lipSyncTimer = setInterval(() => {
                if (!isSpeaking) {
                    stopLipSync();
                    return;
                }
                const rand = Math.random();
                if (rand < 0.25) {
                    targetMouthOpen = 0.0; // Closed mouth pause
                } else if (rand < 0.7) {
                    targetMouthOpen = 0.25 + Math.random() * 0.35; // Medium speaking opening
                } else {
                    targetMouthOpen = 0.6 + Math.random() * 0.4; // Large opening
                }
            }, 220);

            // Set up update listener on the Live2D model to override ParamMouthOpenY after motions calculate
            if (live2dModel) {
                live2dModel.off('update', mouthSyncUpdate); // Clear previous bindings if any
                live2dModel.on('update', mouthSyncUpdate);
            }

            // Interpolate DOM elements toward target for smooth, fluid visualization
            function updateMouthVisuals() {
                if (!isSpeaking) {
                    stopLipSync();
                    return;
                }
                
                // We use currentMouthOpen directly from the model update loop
                const r = document.querySelector('.avatar-ring');
                if (r) {
                    const scaleVal = 0.95 + (currentMouthOpen * 0.22);
                    const opacityVal = 0.25 + (currentMouthOpen * 0.45);
                    const glowRadius = currentMouthOpen * 25;
                    r.style.transform = `scale(${scaleVal})`;
                    r.style.opacity = `${opacityVal}`;
                    r.style.boxShadow = `0 0 ${glowRadius}px var(--primary-glow)`;
                    r.style.borderColor = `rgba(6, 182, 212, ${0.15 + currentMouthOpen * 0.55})`;
                }
                
                const b = document.querySelector('.avatar-backdrop');
                if (b) {
                    const scaleVal = 0.98 + (currentMouthOpen * 0.12);
                    b.style.transform = `scale(${scaleVal})`;
                }
                
                lipSyncAnimationId = requestAnimationFrame(updateMouthVisuals);
            }
            
            updateMouthVisuals();
        }

        function stopLipSync() {
            if (lipSyncTimer) {
                clearInterval(lipSyncTimer);
                lipSyncTimer = null;
            }
            if (lipSyncAnimationId) {
                cancelAnimationFrame(lipSyncAnimationId);
                lipSyncAnimationId = null;
            }
            targetMouthOpen = 0;
            currentMouthOpen = 0;
            
            // Safely detach our model update listener and reset mouth opening
            if (live2dModel) {
                live2dModel.off('update', mouthSyncUpdate);
                if (live2dModel.internalModel && live2dModel.internalModel.coreModel) {
                    live2dModel.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', 0);
                }
            }
            
            const ring = document.querySelector('.avatar-ring');
            if (ring) {
                ring.classList.remove('speaking');
                ring.style.transform = '';
                ring.style.opacity = '';
                ring.style.boxShadow = '';
                ring.style.borderColor = '';
            }
            const backdrop = document.querySelector('.avatar-backdrop');
            if (backdrop) {
                backdrop.classList.remove('speaking');
                backdrop.style.transform = '';
            }
        }

        // Run Live2D engine and init voice input with welcome bubble timeout
        function runInit() {
            initLive2D();
            initVoiceInput();
            setTimeout(() => {
                const bubble = document.getElementById('welcome-bubble');
                if (bubble) {
                    bubble.classList.add('fade-out');
                }
            }, 5500);
        }

        if (document.readyState === 'loading') {
            window.addEventListener('DOMContentLoaded', runInit);
        } else {
            runInit();
        }

        // --- Theme System UI Logic ---
        const themes = {
            cyan: {
                '--bg-color': '#0b0f19',
                '--card-bg': 'rgba(17, 24, 39, 0.7)',
                '--border-color': 'rgba(255, 255, 255, 0.08)',
                '--primary': '#06b6d4',
                '--primary-glow': 'rgba(6, 182, 212, 0.35)',
                '--secondary': '#8b5cf6',
                '--secondary-glow': 'rgba(139, 92, 246, 0.35)',
                '--text-color': '#f3f4f6',
                '--text-muted': '#9ca3af',
                '--terminal-bg': '#030712',
                '--primary-bg-glow': 'rgba(6, 182, 212, 0.08)',
                '--secondary-bg-glow': 'rgba(139, 92, 246, 0.08)'
            },
            green: {
                '--bg-color': '#040d06',
                '--card-bg': 'rgba(6, 18, 10, 0.75)',
                '--border-color': 'rgba(16, 185, 129, 0.12)',
                '--primary': '#10b981',
                '--primary-glow': 'rgba(16, 185, 129, 0.35)',
                '--secondary': '#059669',
                '--secondary-glow': 'rgba(5, 150, 105, 0.35)',
                '--text-color': '#e6f4ea',
                '--text-muted': '#76a084',
                '--terminal-bg': '#020603',
                '--primary-bg-glow': 'rgba(16, 185, 129, 0.08)',
                '--secondary-bg-glow': 'rgba(5, 150, 105, 0.08)'
            },
            purple: {
                '--bg-color': '#0f0919',
                '--card-bg': 'rgba(24, 15, 41, 0.75)',
                '--border-color': 'rgba(139, 92, 246, 0.12)',
                '--primary': '#8b5cf6',
                '--primary-glow': 'rgba(139, 92, 246, 0.35)',
                '--secondary': '#ec4899',
                '--secondary-glow': 'rgba(236, 72, 153, 0.35)',
                '--text-color': '#f8f4ff',
                '--text-muted': '#ac9cb8',
                '--terminal-bg': '#0b0512',
                '--primary-bg-glow': 'rgba(139, 92, 246, 0.08)',
                '--secondary-bg-glow': 'rgba(236, 72, 153, 0.08)'
            },
            amber: {
                '--bg-color': '#140c02',
                '--card-bg': 'rgba(31, 18, 5, 0.75)',
                '--border-color': 'rgba(245, 158, 11, 0.12)',
                '--primary': '#f59e0b',
                '--primary-glow': 'rgba(245, 158, 11, 0.35)',
                '--secondary': '#ef4444',
                '--secondary-glow': 'rgba(239, 68, 68, 0.35)',
                '--text-color': '#fffaf0',
                '--text-muted': '#bda184',
                '--terminal-bg': '#0a0501',
                '--primary-bg-glow': 'rgba(245, 158, 11, 0.08)',
                '--secondary-bg-glow': 'rgba(239, 68, 68, 0.08)'
            },
            mono: {
                '--bg-color': '#111111',
                '--card-bg': 'rgba(24, 24, 24, 0.8)',
                '--border-color': 'rgba(255, 255, 255, 0.1)',
                '--primary': '#e5e7eb',
                '--primary-glow': 'rgba(229, 231, 235, 0.25)',
                '--secondary': '#9ca3af',
                '--secondary-glow': 'rgba(156, 163, 175, 0.25)',
                '--text-color': '#f9fafb',
                '--text-muted': '#9ca3af',
                '--terminal-bg': '#090909',
                '--primary-bg-glow': 'rgba(255, 255, 255, 0.03)',
                '--secondary-bg-glow': 'rgba(255, 255, 255, 0.02)'
            }
        };

        function setTheme(themeName) {
            const theme = themes[themeName] || themes.cyan;
            const root = document.documentElement;
            
            // Set styles
            Object.keys(theme).forEach(key => {
                root.style.setProperty(key, theme[key]);
            });
            
            // Update active states on buttons
            document.querySelectorAll('.theme-chip').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Highlight current button
            const buttons = Array.from(document.querySelectorAll('.theme-chip'));
            const targetBtn = buttons.find(btn => btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(`'${themeName}'`));
            if (targetBtn) {
                targetBtn.classList.add('active');
            }
            
            // Save preference
            localStorage.setItem('micro-agi-theme', themeName);
        }

        // Initialize Theme from localStorage
        window.addEventListener('DOMContentLoaded', async () => {
            const savedTheme = localStorage.getItem('micro-agi-theme');
            if (savedTheme && themes[savedTheme]) {
                setTheme(savedTheme);
            }

            // Restore Terminal & Code Theme
            const savedTermTheme = localStorage.getItem('micro-agi-term-theme') || 'dark';
            setTerminalTheme(savedTermTheme);

            // Wait for the native room mode before reading a saved value above
            // the desktop slider's 100% max. Reading it earlier clamps and
            // persists 120% as 100% on every reload.
            await window.microAgiCapabilitiesReady;
            loadAvatarBgSettings();
            loadChatSessions(true); // Pass true to autoSelectLast on load
            checkSystemUpdate(); // Check for hot update on load
            checkTunnelStatus(); // Check network tunnel status
            
            updateGoogleLoginStatus(); // Load Google login & custom key settings
            window.addEventListener('focus', () => {
                updateGoogleLoginStatus();
            });
        });

        // --- Chat History Management System UI & Logic ---
        let isHistoryLoading = false;

        function toggleChatHistory() {
            const drawer = document.getElementById("chat-history-drawer");
            const backdrop = document.getElementById("historyBackdrop");
            
            // Close settings if open
            const settingsDrawer = document.getElementById("more-menu-drawer");
            const settingsBackdrop = document.getElementById("menuBackdrop");
            if (settingsDrawer && settingsDrawer.classList.contains("open")) {
                settingsDrawer.classList.remove("open");
                if (settingsBackdrop) settingsBackdrop.classList.remove("open");
            }

            if (drawer) {
                if (drawer.classList.contains("open")) {
                    drawer.classList.remove("open");
                    if (backdrop) backdrop.classList.remove("open");
                } else {
                    drawer.classList.add("open");
                    drawer.style.display = "flex";
                    if (backdrop) backdrop.classList.add("open");
                    loadChatSessions(false); // Refresh list on manual open (don't force auto-select)
                }
            }
        }

        async function loadChatSessions(autoSelectLast = false) {
            if (isHistoryLoading) return;
            isHistoryLoading = true;
            
            const listContainer = document.getElementById("chat-history-list");
            if (!listContainer) return;
            
            try {
                const response = await fetch("/api/chats");
                const chats = await response.json();
                
                listContainer.innerHTML = "";
                
                if (chats.length === 0) {
                    listContainer.innerHTML = `
                        <div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.72rem;">
                            暂无历史对话记录
                        </div>
                    `;
                } else {
                    chats.forEach(chat => {
                        const item = document.createElement("div");
                        item.className = `history-item ${chat.chat_id === currentChatId ? 'active' : ''}`;
                        item.setAttribute("data-id", chat.chat_id);
                        item.onclick = (e) => {
                            if (e.target.closest('.history-action-btn')) return;
                            selectChatSession(chat.chat_id);
                        };
                        
                        item.innerHTML = `
                            <div class="history-item-title"></div>
                            <div class="history-item-actions">
                                <button class="history-action-btn edit-btn" title="重命名">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>
                                </button>
                                <button class="history-action-btn delete-btn" title="删除对话">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        `;
                        const title = item.querySelector('.history-item-title');
                        title.textContent = chat.title || '';
                        title.title = chat.title || '';
                        item.querySelector('.edit-btn').addEventListener('click', (event) => {
                            renameChatSession(chat.chat_id, chat.title, event);
                        });
                        item.querySelector('.delete-btn').addEventListener('click', (event) => {
                            deleteChatSession(chat.chat_id, event);
                        });
                        
                        listContainer.appendChild(item);
                    });

                    // Auto select the first chat session if currentChatId is empty and autoSelectLast is true
                    if (autoSelectLast && currentChatId === "" && chats.length > 0) {
                        selectChatSession(chats[0].chat_id, false);
                    }
                }
            } catch (err) {
                console.error("Failed to load chat history:", err);
            } finally {
                isHistoryLoading = false;
            }
        }

        async function selectChatSession(chatId, shouldCloseDrawer = true) {
            currentChatId = chatId;
            
            // Close live preview panel when switching sessions
            if (window.closePreviewPanel) {
                window.closePreviewPanel();
            }

            if (shouldCloseDrawer) {
                const drawer = document.getElementById("chat-history-drawer");
                if (drawer && drawer.classList.contains("open")) {
                    toggleChatHistory(); // Close drawer
                }
            }
            
            // Highlight selected item in history list
            document.querySelectorAll(".history-item").forEach(item => {
                if (item.getAttribute("data-id") === chatId) {
                    item.classList.add("active");
                } else {
                    item.classList.remove("active");
                }
            });

            // Update title in header
            const headerTitle = document.getElementById('header-chat-title');
            if (headerTitle) {
                const activeItem = Array.from(document.querySelectorAll('.history-item'))
                    .find(item => item.getAttribute('data-id') === chatId);
                if (activeItem) {
                    const titleEl = activeItem.querySelector('.history-item-title');
                    if (titleEl) {
                        headerTitle.textContent = titleEl.textContent;
                    }
                } else {
                    headerTitle.textContent = "对话会话";
                }
            }
            
            const loadingId = appendLoading();
            chatArea.innerHTML = "";
            chatHistory = [];
            
            try {
                const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/messages`);
                const messages = await response.json();
                
                // Clear loading
                const loadingEl = document.getElementById(loadingId);
                if (loadingEl) loadingEl.remove();
                
                if (messages.length === 0) {
                    appendMessage("assistant", "Hiyori", "当前对话还没有历史消息记录。你可以开始发送新消息哦 💬");
                } else {
                    messages.forEach(msg => {
                        if (msg.role === 'user') {
                            appendMessage('user', '您', escapeHtml(msg.content).replace(/\n/g, '<br>'));
                        } else {
                            appendAssistantMessage(msg.content, [], null);
                        }
                        chatHistory.push({ role: msg.role, content: msg.content });
                    });
                    
                    // Slice to keep context size healthy
                    if (chatHistory.length > 10) {
                        chatHistory = chatHistory.slice(chatHistory.length - 10);
                    }
                }
            } catch (err) {
                const loadingEl = document.getElementById(loadingId);
                if (loadingEl) loadingEl.remove();
                appendMessage("assistant", "系统错误", `加载历史消息失败: ${escapeHtml(err.message)}`);
            }
            
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function startNewChat() {
            // Close live preview panel when starting new chat
            if (window.closePreviewPanel) {
                window.closePreviewPanel();
            }

            currentChatId = "";
            chatHistory = [];
            chatArea.innerHTML = "";
            
            // Update title in header
            const headerTitle = document.getElementById('header-chat-title');
            if (headerTitle) {
                headerTitle.textContent = "新对话";
            }
            
            // Clear input box
            chatInput.value = "";
            chatInput.placeholder = defaultChatPlaceholder();
            
            // Add a floating welcome message
            const welcomeDiv = document.createElement("div");
            welcomeDiv.style.padding = "20px";
            welcomeDiv.style.textAlign = "center";
            welcomeDiv.style.color = "var(--text-muted)";
            welcomeDiv.style.fontSize = "0.8rem";
            welcomeDiv.innerHTML = "🌸 对话已重置，开始你的新提问吧！";
            chatArea.appendChild(welcomeDiv);
            
            // Clear active styling in sidebar
            document.querySelectorAll(".history-item").forEach(item => {
                item.classList.remove("active");
            });

            toggleChatHistory();
        }

        async function deleteChatSession(chatId, event) {
            if (event) event.stopPropagation();
            if (!confirm("确定要删除这段对话历史记录吗？此操作无法撤销。")) return;
            
            try {
                const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
                    method: "DELETE"
                });
                const data = await response.json();
                
                if (data.status === "success") {
                    showToast("对话已删除 🗑️");
                    if (currentChatId === chatId) {
                        currentChatId = "";
                        chatHistory = [];
                        chatArea.innerHTML = "";
                        const headerTitle = document.getElementById('header-chat-title');
                        if (headerTitle) {
                            headerTitle.textContent = "新对话";
                        }
                    }
                    loadChatSessions(true); // Auto-select first remaining chat
                } else {
                    showToast("删除失败: " + data.error);
                }
            } catch (err) {
                showToast("连接失败: " + err.message);
            }
        }

        async function renameChatSession(chatId, oldTitle, event) {
            if (event) event.stopPropagation();
            const newTitle = prompt("请输入对话新名称:", oldTitle);
            if (!newTitle || newTitle.trim() === "" || newTitle === oldTitle) return;
            
            try {
                const response = await fetch("/api/chats/rename", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ chat_id: chatId, title: newTitle.trim() })
                });
                const data = await response.json();
                
                if (data.status === "success") {
                    showToast("名称已更新 ✏️");
                    if (chatId === currentChatId) {
                        const headerTitle = document.getElementById('header-chat-title');
                        if (headerTitle) {
                            headerTitle.textContent = newTitle.trim();
                        }
                    }
                    loadChatSessions(false);
                } else {
                    showToast("重命名失败: " + data.error);
                }
            } catch (err) {
                showToast("连接失败: " + err.message);
            }
        }

        // --- Tab switching for Wardrobe Drawer ---
        function switchConsoleTab(idx) {
            const tabs = document.querySelectorAll('.console-tab');
            const panes = document.querySelectorAll('.console-pane');
            tabs.forEach((tab, i) => {
                if (i === idx) {
                    tab.classList.add('active');
                } else {
                    tab.classList.remove('active');
                }
            });
            panes.forEach((pane, i) => {
                if (i === idx) {
                    pane.classList.add('active');
                    pane.style.display = 'flex';
                } else {
                    pane.classList.remove('active');
                    pane.style.display = 'none';
                }
            });
            
            if (idx === 0) {
                loadArtifacts();
            } else if (idx === 1) {
                loadExtensions();
            }
        }

        function switchSettingsTab(idx) {
            const tabs = document.querySelectorAll('.settings-tab');
            const panes = document.querySelectorAll('.settings-pane');
            let n = Number(idx);
            if (window.microAgiEmbedded && ![1, 2, 3].includes(n)) n = 3;
            tabs.forEach((tab, i) => {
                const on = i === n;
                tab.classList.toggle('active', on);
                tab.setAttribute('aria-selected', on ? 'true' : 'false');
            });
            panes.forEach((pane) => {
                const paneIdx = pane.hasAttribute('data-settings-pane')
                    ? Number(pane.getAttribute('data-settings-pane'))
                    : Array.prototype.indexOf.call(panes, pane);
                const on = paneIdx === n;
                pane.classList.toggle('active', on);
                pane.style.display = on ? 'flex' : 'none';
            });
            try { localStorage.setItem('micro-agi-settings-tab', String(n)); } catch (e) {}
            // Keep active pill visible in horizontal nav
            const active = document.querySelector('.settings-nav-item.active, .settings-tab.active');
            if (active && typeof active.scrollIntoView === 'function') {
                try { active.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' }); } catch (e) {}
            }
            if (n === 0 && typeof aiosLoadStatus === 'function') {
                setTimeout(aiosLoadStatus, 80);
            }
        }

        function closeWorkspaceConsole() {
            const overlay = document.getElementById('workspaceConsoleOverlay');
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (overlay) overlay.classList.remove('active');
            if (drawer) drawer.classList.remove('active');
            document.body.style.overflow = '';
        }

        function toggleWorkspaceConsole() {
            const overlay = document.getElementById('workspaceConsoleOverlay');
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (!overlay || !drawer) return;

            const moreMenu = document.getElementById('more-menu-drawer');
            if (moreMenu && moreMenu.classList.contains('open')) {
                try { closeMoreMenu(); } catch (e) {}
            }

            if (drawer.classList.contains('active')) {
                closeWorkspaceConsole();
            } else {
                overlay.classList.add('active');
                drawer.classList.add('active');
                document.body.style.overflow = 'hidden';
                loadArtifacts(window._artifactTypeFilter || 'all');
            }
        }

        // --- Custom Background Image Upload & Logic ---
        function handleAvatarBgUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            // Compress image using existing compressImage helper
            compressImage(file, (compressedDataUrl) => {
                if (!compressedDataUrl) {
                    showToast("背景图片读取失败 ⚠️");
                    return;
                }
                
                // Store in localStorage
                try {
                    localStorage.setItem('micro-agi-custom-bg', compressedDataUrl);
                } catch(e) {
                    console.error("Local storage quota exceeded:", e);
                    showToast("图片体积过大，储存受限，请尝试其他图片 ⚠️");
                    return;
                }

                // Apply the background image
                applyCustomBg(compressedDataUrl);
                showToast("背景替换成功 ✨");
            });
        }

        function applyCustomBg(dataUrl) {
            const bgEl = document.getElementById('avatarCustomBg');
            if (bgEl) {
                bgEl.style.backgroundImage = `url(${dataUrl})`;
            }
        }

        function applyPresetBg(presetName) {
            const bgEl = document.getElementById('avatarCustomBg');
            const container = document.querySelector('.avatar-container');
            if (!bgEl || !container) return;

            // Remove custom bg from storage and element
            localStorage.removeItem('micro-agi-custom-bg');
            if (presetName === 'default' && document.documentElement.classList.contains('embedded-host')) {
                bgEl.style.removeProperty('background-image');
            } else {
                bgEl.style.backgroundImage = 'none';
            }

            // Apply preset gradients to the container
            if (presetName === 'default') {
                if (document.documentElement.classList.contains('embedded-host')) {
                    container.style.removeProperty('background');
                } else {
                    container.style.background = 'radial-gradient(circle at center, rgba(6, 182, 212, 0.2) 0%, rgba(139, 92, 246, 0.05) 60%, rgba(11, 15, 25, 0.95) 100%)';
                }
            } else if (presetName === 'nebula') {
                container.style.background = 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%)';
            } else if (presetName === 'cyberpunk') {
                container.style.background = 'linear-gradient(45deg, #090514 0%, #18031d 50%, #25021f 100%)';
            } else if (presetName === 'sunset') {
                container.style.background = 'linear-gradient(135deg, #180905 0%, #290805 50%, #140501 100%)';
            }
            
            showToast("背景预设应用成功 💫");
        }

        function adjustAvatarBg() {
            const brightness = document.getElementById('bg-brightness-slider').value;
            const blur = document.getElementById('bg-blur-slider').value;
            const opacity = document.getElementById('bg-opacity-slider').value;

            // Update UI slider text
            document.getElementById('bg-brightness-val').textContent = `${brightness}%`;
            document.getElementById('bg-blur-val').textContent = `${blur}px`;
            document.getElementById('bg-opacity-val').textContent = `${opacity}%`;

            // Update CSS variables on custom bg element
            const bgEl = document.getElementById('avatarCustomBg');
            if (bgEl) {
                bgEl.style.setProperty('--avatar-bg-brightness', brightness / 100);
                bgEl.style.setProperty('--avatar-bg-blur', `${blur}px`);
                bgEl.style.setProperty('--avatar-bg-opacity', opacity / 100);
            }

            // Save adjustments to localStorage
            const settings = { brightness, blur, opacity };
            localStorage.setItem('micro-agi-bg-settings', JSON.stringify(settings));
        }

        function loadAvatarBgSettings() {
            // 1. Load background image if exists
            const customBg = localStorage.getItem('micro-agi-custom-bg');
            if (customBg) {
                applyCustomBg(customBg);
            }

            const embeddedRoom = !customBg && document.documentElement.classList.contains('embedded-host');
            if (embeddedRoom) {
                // The room illustration needs a wider adjustment range than the
                // older gradient presets. Keep the slider truthful to the image.
                document.getElementById('bg-brightness-slider').max = '150';
            }

            // The standalone room is a complete illustration, not the old
            // holographic gradient. Migrate the old 50%/60% defaults once so
            // its first appearance is not unintentionally dimmed.
            if (embeddedRoom
                    && localStorage.getItem('micro-agi-room-bg-v1') !== '1') {
                const oldRaw = localStorage.getItem('micro-agi-bg-settings');
                let oldSettings = null;
                try { oldSettings = oldRaw ? JSON.parse(oldRaw) : null; } catch (_) {}
                if (!oldSettings || (Number(oldSettings.brightness) === 50
                        && Number(oldSettings.blur) === 0
                        && Number(oldSettings.opacity) === 60)) {
                    document.getElementById('bg-brightness-slider').value = '100';
                    document.getElementById('bg-opacity-slider').value = '100';
                    localStorage.removeItem('micro-agi-bg-settings');
                }
                localStorage.setItem('micro-agi-room-bg-v1', '1');
            }

            // 2. Load sliders configuration
            const savedSettings = localStorage.getItem('micro-agi-bg-settings');
            if (savedSettings) {
                try {
                    const settings = JSON.parse(savedSettings);
                    
                    const brightSlider = document.getElementById('bg-brightness-slider');
                    const blurSlider = document.getElementById('bg-blur-slider');
                    const opacitySlider = document.getElementById('bg-opacity-slider');

                    if (brightSlider && settings.brightness !== undefined) brightSlider.value = settings.brightness;
                    if (blurSlider && settings.blur !== undefined) blurSlider.value = settings.blur;
                    if (opacitySlider && settings.opacity !== undefined) opacitySlider.value = settings.opacity;
                } catch(e) {
                    console.error("Failed to parse bg settings:", e);
                }
            }

            // Previous Android builds could leave the room at a dark legacy
            // brightness/opacity even after the original migration. Bring the
            // bundled scene to the new readable default once; never modify a
            // user-uploaded image, and keep subsequent manual adjustments.
            if (embeddedRoom && localStorage.getItem('micro-agi-room-bg-v2') !== '1') {
                const brightSlider = document.getElementById('bg-brightness-slider');
                const opacitySlider = document.getElementById('bg-opacity-slider');
                // Only migrate an untouched default or the exact legacy 50/60
                // preset. Lower values may be an intentional user adjustment.
                const legacyPreset = Number(brightSlider.value) === 50
                    && Number(opacitySlider.value) === 60;
                if (!savedSettings || legacyPreset) {
                    brightSlider.value = '120';
                    opacitySlider.value = '100';
                }
                localStorage.setItem('micro-agi-room-bg-v2', '1');
            }
            
            // Apply current slider values
            adjustAvatarBg();
        }

        // Wardrobe UI Logic
        let currentHue = 0;

        function applyOutfitChange(outfitId, element) {
            console.log(`[API] Triggering outfit change for: ${outfitId}`);
            
            // 1. Update UI Selection State
            document.querySelectorAll('.wardrobe-item').forEach(item => {
                item.classList.remove('equipped');
                const statusEl = item.querySelector('.outfit-status');
                if (statusEl) {
                    statusEl.textContent = '点击换装';
                    statusEl.style.color = 'var(--text-muted)';
                }
            });
            
            if (element) {
                element.classList.add('equipped');
                const statusEl = element.querySelector('.outfit-status');
                if (statusEl) {
                    statusEl.textContent = '当前装备';
                    statusEl.style.color = 'var(--primary)';
                }
            }

            // 2. Apply simulated "model swap" using CSS filters
            const canvas = document.getElementById('vrm-canvas');
            const ring = document.querySelector('.avatar-ring');
            const backdrop = document.querySelector('.avatar-backdrop');
            
            // Add a quick flash/smoke effect using opacity
            canvas.style.transition = 'filter 0.5s ease, opacity 0.2s';
            canvas.style.opacity = '0';
            if (ring) { ring.style.transition = 'all 0.5s'; ring.style.opacity = '0'; }
            
            setTimeout(() => {
                // Determine hue shift based on outfit
                if (outfitId === 'default') {
                    currentHue = 0;
                } else if (outfitId === 'epic_cat') {
                    currentHue = 260; // Purple shift
                } else if (outfitId === 'legendary_mech') {
                    currentHue = 45;  // Orange/Gold shift
                } else {
                    currentHue = Math.floor(Math.random() * 360);
                }
                
                // Apply the color shift
                canvas.style.filter = `hue-rotate(${currentHue}deg) drop-shadow(0 0 20px rgba(255,255,255,0.15))`;
                
                // Change environmental glowing colors to match the vibe
                if (ring) {
                    ring.style.filter = `hue-rotate(${currentHue}deg)`;
                    ring.style.opacity = '1';
                }
                if (backdrop) {
                    backdrop.style.filter = `hue-rotate(${currentHue}deg)`;
                }
                
                // Fade back in
                canvas.style.opacity = '1';
                
                // Close the drawer automatically for better UX
                toggleWardrobe();
                
            }, 300);
        }

        // Wrapper functions for legacy drawers redirects
        function toggleWardrobe() {
            // 形象 tab index after settings IA redesign
            const WARDROBE_TAB = 1;
            const menuEl = document.getElementById("more-menu-drawer");
            if (menuEl.classList.contains("open")) {
                const activeTab = document.querySelector('.settings-tab.active');
                const tabs = document.querySelectorAll('.settings-tab');
                if (activeTab === tabs[WARDROBE_TAB]) {
                    closeMoreMenu();
                } else {
                    switchSettingsTab(WARDROBE_TAB);
                }
            } else {
                openMoreMenu();
                switchSettingsTab(WARDROBE_TAB);
            }
        }

        function toggleStore() {
            const drawer = document.getElementById('skillsStoreDrawer');
            const overlay = document.getElementById('skillsStoreOverlay');
            if (!drawer || !overlay) return;
            
            // Close console drawer if open
            const consoleDrawer = document.getElementById('workspaceConsoleDrawer');
            const consoleOverlay = document.getElementById('workspaceConsoleOverlay');
            if (consoleDrawer && consoleDrawer.classList.contains('active')) {
                consoleDrawer.classList.remove('active');
                if (consoleOverlay) consoleOverlay.classList.remove('active');
            }
            
            const isMoreMenuOpen = document.getElementById('more-menu-drawer').classList.contains('open');
            if (isMoreMenuOpen) closeMoreMenu();
            
            if (drawer.classList.contains('active')) {
                overlay.classList.remove('active');
                drawer.classList.remove('active');
            } else {
                overlay.classList.add('active');
                drawer.classList.add('active');
                
                loadExtensions();
            }
        }

        function toggleMCP() {
            const drawer = document.getElementById('skillsStoreDrawer');
            if (drawer && drawer.classList.contains('active')) {
                const sec = document.getElementById('section-mcp');
                if (sec) sec.scrollIntoView({ behavior: 'smooth' });
            } else {
                toggleStore();
                setTimeout(() => {
                    const sec = document.getElementById('section-mcp');
                    if (sec) sec.scrollIntoView({ behavior: 'smooth' });
                }, 100);
            }
        }

        function toggleArtifacts() {
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (drawer.classList.contains('active')) {
                const activeTab = document.querySelector('.console-tab.active');
                const tabs = document.querySelectorAll('.console-tab');
                if (activeTab === tabs[0]) {
                    toggleWorkspaceConsole();
                } else {
                    switchConsoleTab(0);
                }
            } else {
                toggleWorkspaceConsole();
                switchConsoleTab(0);
            }
        }

        let currentArtifactsData = [];
        let filteredArtifactsData = [];
        let activeArtifact = null;
        window._artifactTypeFilter = 'all';

        function formatArtifactTime(iso) {
            if (!iso) return '';
            try {
                // sqlite CURRENT_TIMESTAMP is UTC-ish 'YYYY-MM-DD HH:MM:SS'
                const s = String(iso).replace(' ', 'T');
                const d = new Date(s.includes('T') ? (s.endsWith('Z') ? s : s + 'Z') : s);
                if (isNaN(d.getTime())) return String(iso).slice(0, 16);
                const diff = (Date.now() - d.getTime()) / 1000;
                if (diff < 60) return '刚刚';
                if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
                if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
                if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' 天前';
                return d.toLocaleDateString();
            } catch (e) {
                return '';
            }
        }

        function formatArtifactSize(n) {
            n = Number(n) || 0;
            if (n < 1024) return n + ' B';
            if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
            return (n / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function langBadge(art) {
            const lang = (art.lang || art.key_prompt || '').trim();
            if (lang) return lang.toUpperCase().slice(0, 8);
            if (art.type === 'image') return 'IMG';
            const t = (art.title || '').toLowerCase();
            const keys = ['python','js','ts','html','css','json','bash','sql','go','rust','java'];
            for (const k of keys) if (t.includes(k)) return k.toUpperCase();
            return art.type === 'code' ? 'CODE' : 'FILE';
        }

        async function loadArtifacts(typeFilter = 'all') {
            window._artifactTypeFilter = typeFilter || 'all';
            const grid = document.getElementById('artifactsGrid');
            if (grid) {
                grid.innerHTML = `<div class="aa-empty"><h3>加载中…</h3></div>`;
            }
            document.querySelectorAll('.aa-chip').forEach(tab => {
                tab.classList.toggle('active', tab.getAttribute('data-type') === window._artifactTypeFilter);
            });
            try {
                const response = await fetch(`/api/artifacts?project_id=all&type_filter=${encodeURIComponent(window._artifactTypeFilter)}`);
                const artifacts = await response.json();
                currentArtifactsData = Array.isArray(artifacts) ? artifacts : [];
                filterArtifactsLocal();
            } catch (err) {
                console.error("Failed to load artifacts:", err);
                if (grid) {
                    grid.innerHTML = `<div class="aa-empty"><h3>加载失败</h3><p>${escapeHtml(err.message || '网络异常')}</p></div>`;
                }
            }
        }

        function filterArtifactsLocal() {
            const q = ((document.getElementById('artifactsSearch') || {}).value || '').trim().toLowerCase();
            let list = currentArtifactsData.slice();
            if (q) {
                list = list.filter(a => {
                    const hay = [a.title, a.preview_text, a.lang, a.key_prompt, a.type, a.content_url]
                        .map(x => String(x || '').toLowerCase()).join(' ');
                    return hay.includes(q);
                });
            }
            filteredArtifactsData = list;
            renderArtifacts(list);
        }

        function renderArtifacts(artifacts) {
            const grid = document.getElementById('artifactsGrid');
            if (!grid) return;
            const badge = document.getElementById('artifactsCountBadge');
            if (badge) badge.textContent = String((artifacts || []).length);

            if (!artifacts || artifacts.length === 0) {
                const hasAny = (currentArtifactsData || []).length > 0;
                grid.innerHTML = hasAny
                    ? `<div class="aa-empty"><h3>没有匹配结果</h3><p>换个关键词，或切换上方分类。</p></div>`
                    : `<div class="aa-empty"><h3>资产箱是空的</h3><p>让 AI 输出代码块（\`\`\`python）或图片链接，会自动归档到这里。</p></div>`;
                return;
            }

            grid.innerHTML = '';
            artifacts.forEach(art => {
                const id = art.artifact_id;
                const lang = langBadge(art);
                const typeLabel = art.type === 'image' ? '图片' : '代码';
                const typeClass = art.type === 'image' ? 'image' : 'code';
                const metaTime = formatArtifactTime(art.created_at);
                const sizeLabel = art.type === 'code'
                    ? `${art.lines || (String(art.content_url || '').split('\n').length)} 行`
                    : formatArtifactSize(art.size || (art.content_url || '').length);

                const row = document.createElement('div');
                row.className = 'aa-item';
                row.onclick = () => openArtifactModal(id);
                row.innerHTML = `
                    <div class="aa-item-top">
                        <div class="aa-item-title">${escapeHtml(art.title || '未命名资产')}</div>
                        <span class="aa-item-type ${typeClass}">${typeLabel}</span>
                    </div>
                    <div class="aa-item-meta">
                        <span class="aa-tag">${escapeHtml(lang)}</span>
                        <span class="aa-tag">${escapeHtml(sizeLabel)}</span>
                        ${metaTime ? `<span class="aa-tag">${escapeHtml(metaTime)}</span>` : ''}
                    </div>
                    <div class="aa-item-preview">${escapeHtml(art.preview_text || (art.type === 'image' ? art.content_url : '') || '无预览')}</div>
                    <div class="aa-item-actions">
                        <button type="button" class="aa-act primary" data-act="copy">复制</button>
                        <button type="button" class="aa-act" data-act="insert">插入</button>
                        <button type="button" class="aa-act" data-act="ask">继续问</button>
                        <button type="button" class="aa-act danger" data-act="del">删除</button>
                    </div>
                `;
                row.querySelectorAll('[data-act]').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const act = btn.getAttribute('data-act');
                        if (act === 'copy') quickCopyArtifact(id);
                        else if (act === 'insert') insertArtifactToInput(id);
                        else if (act === 'ask') askAboutArtifact(id);
                        else if (act === 'del') deleteArtifact(e, id);
                    });
                });
                grid.appendChild(row);
            });
        }

        function getArtifactById(id) {
            return (currentArtifactsData || []).find(a => a.artifact_id === id);
        }

        function quickCopyArtifact(id) {
            const art = getArtifactById(id);
            if (!art) return;
            const text = art.type === 'image' ? art.content_url : art.content_url;
            copyTextToClipboard(text, art.type === 'image' ? '图片链接已复制' : '代码已复制');
        }

        function insertArtifactToInput(id) {
            const art = getArtifactById(id);
            if (!art) return;
            const input = document.getElementById('chatInput');
            if (!input) return;
            let snippet = '';
            if (art.type === 'image') {
                snippet = art.content_url || '';
            } else {
                const lang = art.lang || art.key_prompt || '';
                snippet = '```' + lang + '\n' + (art.content_url || '') + '\n```';
            }
            input.value = (input.value ? input.value + '\n\n' : '') + snippet;
            input.focus();
            closeWorkspaceConsole();
            showToast('已插入到输入框');
        }

        function askAboutArtifact(id) {
            const art = getArtifactById(id);
            if (!art) return;
            const input = document.getElementById('chatInput');
            if (!input) return;
            if (art.type === 'image') {
                input.value = `请基于这张图继续说明/改进：${art.content_url}`;
            } else {
                const lang = art.lang || art.key_prompt || 'code';
                input.value = `请基于下面这段 ${lang} 代码继续优化/解释：\n\n\`\`\`${lang}\n${art.content_url}\n\`\`\``;
            }
            input.focus();
            closeWorkspaceConsole();
            showToast('已填入提问，可直接发送');
        }

        async function deleteArtifact(e, artifactId) {
            e.stopPropagation();
            if (!confirm("确定要永久删除这个资产吗？此操作不可恢复。")) return;
            
            try {
                const res = await fetch(`/api/artifacts/${artifactId}`, { method: 'DELETE' });
                if (res.ok) {
                    loadArtifacts(window._artifactTypeFilter || 'all');
                    if (activeArtifact && activeArtifact.artifact_id === artifactId) {
                        closeArtifactModal();
                    }
                } else {
                    const data = await res.json();
                    alert("删除失败: " + data.error);
                }
            } catch (err) {
                console.error("Delete failed:", err);
                alert("删除失败，网络异常");
            }
        }

        function timeMachineTo(e, nodeId) {
            if (e) e.stopPropagation();
            closeWorkspaceConsole();
            
            // Wait for drawer to close before scrolling
            setTimeout(() => {
                const targetMsg = document.getElementById(`msg-${nodeId}`);
                if (targetMsg) {
                    targetMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    targetMsg.classList.add('highlight-msg');
                    setTimeout(() => targetMsg.classList.remove('highlight-msg'), 3000);
                    showToast('已定位到对话中的原消息');
                } else {
                    showToast('当前会话里找不到原消息（可能已换对话或不在屏幕缓存中）');
                }
            }, 320);
        }

        function openArtifactModal(artifactId) {
            activeArtifact = currentArtifactsData.find(a => a.artifact_id === artifactId);
            if (!activeArtifact) return;

            const modalOverlay = document.getElementById('artifactModalOverlay');
            const modal = document.getElementById('artifactModal');
            const titleEl = document.getElementById('artifactModalTitle');
            const bodyEl = document.getElementById('artifactModalBody');
            
            titleEl.textContent = activeArtifact.title || "成果详情";
            
            // Render body content depending on type
            if (activeArtifact.type === 'image') {
                bodyEl.textContent = '';
                const image = document.createElement('img');
                image.className = 'artifact-image-preview';
                image.alt = activeArtifact.title || 'Preview';
                image.referrerPolicy = 'no-referrer';
                image.src = activeArtifact.content_url || '';
                const caption = document.createElement('div');
                caption.style.cssText = 'font-size:0.75rem;color:var(--text-muted);text-align:center;margin-top:8px;word-break:break-all;';
                caption.textContent = '图片链接: ' + (activeArtifact.content_url || '');
                image.addEventListener('error', () => {
                    image.style.display = 'none';
                    caption.textContent = '无法加载图片 · ' + caption.textContent;
                }, { once: true });
                bodyEl.appendChild(image);
                bodyEl.appendChild(caption);
                document.getElementById('artifactModalCopy').innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    复制链接
                `;
            } else {
                bodyEl.innerHTML = `
                    <pre class="artifact-code-pre"><code id="modal-code-block">${escapeHtml(activeArtifact.content_url)}</code></pre>
                `;
                document.getElementById('artifactModalCopy').innerHTML = `
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    复制代码
                `;
            }
            
            // Set up footer actions
            const tmBtn = document.getElementById('artifactModalTimeMachine');
            if (tmBtn) tmBtn.onclick = (e) => {
                closeArtifactModal();
                timeMachineTo(e, activeArtifact.node_id);
            };

            const copyBtn = document.getElementById('artifactModalCopy');
            if (copyBtn) copyBtn.onclick = () => {
                if (activeArtifact.type === 'image') {
                    copyTextToClipboard(activeArtifact.content_url, "图片链接已复制！");
                } else {
                    copyTextToClipboard(activeArtifact.content_url, "代码内容已复制！");
                }
            };

            const insertBtn = document.getElementById('artifactModalInsert');
            if (insertBtn) insertBtn.onclick = () => {
                closeArtifactModal();
                insertArtifactToInput(activeArtifact.artifact_id);
            };
            const askBtn = document.getElementById('artifactModalAsk');
            if (askBtn) askBtn.onclick = () => {
                closeArtifactModal();
                askAboutArtifact(activeArtifact.artifact_id);
            };

            const downloadBtn = document.getElementById('artifactModalDownload');
            if (downloadBtn) downloadBtn.onclick = () => {
                downloadArtifactFile(activeArtifact);
            };

            modalOverlay.classList.add('active');
            modal.classList.add('active');
        }

        function closeArtifactModal() {
            const modalOverlay = document.getElementById('artifactModalOverlay');
            const modal = document.getElementById('artifactModal');
            if (modalOverlay) modalOverlay.classList.remove('active');
            if (modal) modal.classList.remove('active');
            activeArtifact = null;
        }

        function copyTextToClipboard(text, successMsg) {
            navigator.clipboard.writeText(text).then(() => {
                showToast(successMsg);
            }).catch(err => {
                console.error("Clipboard copy failed:", err);
                const textarea = document.createElement("textarea");
                textarea.value = text;
                textarea.style.position = "fixed";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                try {
                    document.execCommand('copy');
                    showToast(successMsg);
                } catch (copyErr) {
                    alert("复制失败，请手动选择复制。");
                }
                document.body.removeChild(textarea);
            });
        }

        function showToast(msg) {
            let toast = document.getElementById('copyToast');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'copyToast';
                toast.className = 'copy-toast';
                document.body.appendChild(toast);
            }
            toast.textContent = msg;
            toast.classList.add('active');
            setTimeout(() => {
                toast.classList.remove('active');
            }, 2000);
        }

        function downloadArtifactFile(artifact) {
            const blob = new Blob([artifact.content_url], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = artifact.type === 'image' ? artifact.content_url : url;
            a.download = artifact.title ? artifact.title.replace(/\s+/g, '_') : 'artifact';
            if (artifact.type !== 'image') {
                const extensionMap = {
                    'python': 'py', 'javascript': 'js', 'js': 'js', 'html': 'html', 'css': 'css',
                    'json': 'json', 'bash': 'sh', 'sh': 'sh', 'sql': 'sql', 'markdown': 'md', 'md': 'md'
                };
                const titleLower = (artifact.title || '').toLowerCase();
                let ext = 'txt';
                for (const [key, val] of Object.entries(extensionMap)) {
                    if (titleLower.includes(key)) {
                        ext = val;
                        break;
                    }
                }
                a.download += '.' + ext;
            }
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            if (artifact.type !== 'image') {
                URL.revokeObjectURL(url);
            }
            showToast("文件下载已启动！");
        }

        // --- Live Preview Feature ---
        let currentPreviewHtml = "";
        
        window.openLivePreview = function(htmlContent) {
            if (window.microAgiEmbedded !== false) return;
            currentPreviewHtml = htmlContent;
            const previewPanel = document.getElementById('previewPanel');
            const iframe = document.getElementById('previewIframe');
            
            // Adjust layouts for split screen
            const isDesktop = window.innerWidth >= 768;
            if (isDesktop) {
                const workspaceDrawer = document.getElementById('workspaceConsoleDrawer');
                if (workspaceDrawer) {
                    workspaceDrawer.style.setProperty('display', 'none', 'important');
                }
            } else {
                // On mobile, maybe close other drawers if needed
            }
            
            previewPanel.style.display = 'flex';
            
            // Construct Blob and URL
            const blob = new Blob([htmlContent], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            iframe.src = url;
            
            // Set pseudo url
            document.getElementById('previewUrlText').textContent = 'live-sandbox://' + Math.random().toString(16).substr(2, 8) + '/preview';
            
            // Note: We don't revoke URL immediately so it can load assets
        };

        window.closePreviewPanel = function() {
            document.getElementById('previewPanel').style.display = 'none';
            document.getElementById('previewIframe').src = 'about:blank';
            
            if (window.innerWidth >= 768) {
                const workspaceDrawer = document.getElementById('workspaceConsoleDrawer');
                if (workspaceDrawer) {
                    workspaceDrawer.style.setProperty('display', 'flex', 'important');
                }
            }
        };

        window.refreshPreview = function() {
            if (!currentPreviewHtml) return;
            const iframe = document.getElementById('previewIframe');
            const blob = new Blob([currentPreviewHtml], { type: 'text/html' });
            iframe.src = URL.createObjectURL(blob);
        };

        async function checkSystemUpdate() {
            // Capability detection is asynchronous. Never probe the disabled
            // updater before the embedded Android mode is known.
            if (window.microAgiCapabilitiesReady) {
                await window.microAgiCapabilitiesReady;
            }
            if (window.microAgiEmbedded !== false) {
                const version = document.getElementById('system-update-ver');
                if (version && window.microAgiEmbedded) {
                    version.textContent = '独立版请通过安装包更新';
                }
                return;
            }
            const verText = document.getElementById('system-update-ver');
            const updateBtn = document.getElementById('system-update-btn');
            if (!verText) return;
            
            try {
                const res = await fetch('/api/system/update');
                if (!res.ok) throw new Error("HTTP error " + res.status);
                const data = await res.json();
                if (data.update_available) {
                    verText.textContent = `有新版本可用: ${data.local_commit || '未知'} → ${data.remote_commit || '未知'}`;
                    if (updateBtn) updateBtn.style.display = 'block';
                } else {
                    verText.textContent = `已是最新版本 (当前: ${data.local_commit || '未知'})`;
                    if (updateBtn) updateBtn.style.display = 'none';
                }
            } catch (err) {
                console.error("Failed to check system update:", err);
                verText.textContent = "检查更新失败";
                if (updateBtn) updateBtn.style.display = 'none';
            }
        }

        async function triggerSystemUpdate() {
            if (window.microAgiEmbedded !== false) return;
            const verText = document.getElementById('system-update-ver');
            const updateBtn = document.getElementById('system-update-btn');
            
            if (!confirm("确定要进行系统热更新吗？这将会拉取最新代码并重启服务。")) return;
            
            if (updateBtn) {
                updateBtn.disabled = true;
                updateBtn.textContent = "更新中...";
            }
            if (verText) {
                verText.textContent = "正在拉取代码并重启服务，请稍候...";
            }
            
            try {
                const res = await fetch('/api/system/update', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    if (verText) verText.textContent = "更新成功！正在重新载入界面...";
                    setTimeout(() => {
                        location.reload();
                    }, 3000);
                } else {
                    alert("更新失败: " + (data.error || "未知错误"));
                    if (updateBtn) {
                        updateBtn.disabled = false;
                        updateBtn.textContent = "立即更新";
                    }
                    if (verText) {
                        verText.textContent = "更新失败";
                    }
                }
            } catch (err) {
                console.error("System update error:", err);
                alert("更新请求发送失败，请检查网络或稍后重试");
                if (updateBtn) {
                    updateBtn.disabled = false;
                    updateBtn.textContent = "立即更新";
                }
            }
        }

        // Attach functions to window scope for immediate HTML inline onclick access
        window.checkSystemUpdate = checkSystemUpdate;
        window.triggerSystemUpdate = triggerSystemUpdate;
        window.sendSuggestion = sendSuggestion;
        window.togglePetMode = togglePetMode;

        // ========== AI OS: entry / memory / digest ==========
        let _aiosMemoriesCache = [];

        function aiosFmtTime(ts) {
            if (!ts) return '';
            try {
                const d = new Date(String(ts).replace(' ', 'T'));
                if (isNaN(d.getTime())) return String(ts).slice(0, 16);
                const m = d.getMonth() + 1;
                const day = d.getDate();
                const hh = String(d.getHours()).padStart(2, '0');
                const mm = String(d.getMinutes()).padStart(2, '0');
                return `${m}/${day} ${hh}:${mm}`;
            } catch (e) {
                return String(ts).slice(0, 16);
            }
        }

        function aiosSetNotifBadge(notif) {
            const el = document.getElementById('aios-notif-badge');
            if (!el) return;
            notif = notif || {};
            el.className = 'aios-badge';
            if (notif.available === false) {
                el.classList.add('aios-badge--err');
                el.textContent = '通知：不可用（需 Termux:API）';
                el.title = notif.tip || '';
            } else if (notif.available === true) {
                el.classList.add('aios-badge--ok');
                el.textContent = '通知：Termux:API 可用';
                el.title = notif.tip || '';
            } else {
                el.classList.add('aios-badge--muted');
                el.textContent = '通知：检测中…';
            }
        }

        function aiosShowDigestPreview(text, meta) {
            const pre = document.getElementById('aios-digest-preview');
            if (!pre) return;
            if (!text) {
                pre.hidden = true;
                pre.textContent = '';
                return;
            }
            let head = '';
            if (meta) {
                const bits = [];
                if (meta.kind) bits.push('类型 ' + meta.kind);
                if (meta.preview_only) bits.push('仅预览');
                if (meta.skipped) bits.push('今日已发过（展示内容）');
                if (meta.notification === true) bits.push('通知已推送');
                if (meta.notification === false && !meta.preview_only) bits.push('通知未推送');
                if (meta.notif_reason) bits.push(meta.notif_reason);
                if (bits.length) head = '【' + bits.join(' · ') + '】\n';
            }
            pre.textContent = head + text;
            pre.hidden = false;
        }

        async function aiosLoadStatus() {
            const line = document.getElementById('aios-status-line');
            try {
                const res = await fetch('/api/aios/status');
                const data = await res.json();
                if (!data.ok) throw new Error(data.error || 'status fail');
                const s = data.snapshot || {};
                const bat = (s.battery && s.battery.percentage != null) ? s.battery.percentage + '%' : '?';
                const free = s.disk_home_free_gb != null ? s.disk_home_free_gb + 'G' : '?';
                const svc = s.services || {};
                const svcOk = Object.values(svc).filter(Boolean).length;
                if (line) {
                    line.textContent = `电量 ${bat} · 盘剩 ${free} · 服务 ${svcOk}/${Object.keys(svc).length} · 记忆 ${s.memories || 0} · 资产24h ${s.artifacts_24h || 0} · ${s.time || ''}`;
                }
                aiosSetNotifBadge(data.notification || s.notification);
                _aiosMemoriesCache = data.memories || [];
                const qEl = document.getElementById('aios-memory-search');
                const q = qEl ? qEl.value : '';
                aiosRenderMemories(_aiosMemoriesCache, q);
            } catch (e) {
                if (line) line.textContent = '状态获取失败: ' + (e.message || e);
                aiosSetNotifBadge({ available: false, tip: String(e.message || e) });
            }
        }

        function aiosFilterMemories(q) {
            aiosRenderMemories(_aiosMemoriesCache, q);
        }

        function aiosRenderMemories(items, filterQ) {
            const box = document.getElementById('aios-memory-list');
            if (!box) return;
            let list = items || [];
            const q = (filterQ || '').trim().toLowerCase();
            if (q) {
                list = list.filter(m => ((m.content || '') + ' ' + (m.kind || '')).toLowerCase().includes(q));
            }
            box.replaceChildren();
            if (!list.length) {
                const empty = document.createElement('div');
                empty.style.cssText = 'color:var(--text-muted);padding:6px 0;';
                empty.textContent = q
                    ? '没有匹配的记忆'
                    : '暂无记忆。可添加，或聊天说「记住：…」';
                box.appendChild(empty);
                return;
            }
            list.forEach(m => {
                const id = String(m.memory_id || '');
                const imp = Number(m.importance || 1);
                const pinned = imp >= 5;
                const t = aiosFmtTime(m.updated_at || m.created_at);
                const item = document.createElement('div');
                item.className = `aios-mem-item${pinned ? ' is-pinned' : ''}`;
                item.dataset.mid = id;

                const body = document.createElement('div');
                body.className = 'aios-mem-body';
                const meta = document.createElement('div');
                meta.className = 'aios-mem-meta';
                const kind = document.createElement('span');
                kind.className = 'aios-mem-kind';
                kind.textContent = `${pinned ? '📌 ' : ''}[${m.kind || 'fact'}]`;
                meta.appendChild(kind);
                if (m.source) {
                    const source = document.createElement('span');
                    source.textContent = m.source;
                    meta.appendChild(source);
                }
                if (t) {
                    const time = document.createElement('span');
                    time.textContent = t;
                    meta.appendChild(time);
                }
                const content = document.createElement('div');
                content.textContent = m.content || '';
                body.append(meta, content);

                const actions = document.createElement('div');
                actions.className = 'aios-mem-actions';
                const pin = document.createElement('button');
                pin.type = 'button';
                if (pinned) pin.className = 'pin-on';
                pin.textContent = pinned ? '取消置顶' : '置顶';
                pin.addEventListener('click', () => aiosPinMemory(id, !pinned));
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'danger';
                remove.textContent = '删除';
                remove.addEventListener('click', () => aiosDeleteMemory(id));
                actions.append(pin, remove);
                item.append(body, actions);
                box.appendChild(item);
            });
        }

        async function aiosRefreshEntry() {
            const btn = document.getElementById('aios-refresh-btn');
            if (btn) { btn.disabled = true; btn.textContent = '刷新中…'; }
            try {
                const res = await fetch('/api/aios/entry/refresh', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: '{}'
                });
                const data = await res.json();
                const detail = data.notification_detail || {};
                const msg = data.message || detail.reason || (data.notification ? '通知栏入口已刷新' : '状态已刷新，通知可能失败');
                if (typeof showToast === 'function') showToast(msg);
                else alert(msg);
                if (detail.available === false || data.notification === false) {
                    aiosSetNotifBadge(detail.available === false
                        ? { available: false, tip: detail.reason }
                        : { available: true, tip: detail.reason });
                } else if (data.notification) {
                    aiosSetNotifBadge({ available: true, tip: detail.reason || 'OK' });
                }
                aiosLoadStatus();
            } catch (e) {
                if (typeof showToast === 'function') showToast('刷新失败: ' + e.message);
                else alert('刷新失败: ' + e.message);
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = '刷新入口'; }
            }
        }

        /**
         * @param {string} kind
         * @param {boolean} push  false = preview only
         */
        async function aiosSendDigest(kind, push) {
            if (push === undefined) push = true;
            try {
                const res = await fetch('/api/aios/digest', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        kind: kind || 'now',
                        push: !!push,
                        force: true  // manual always force
                    })
                });
                const data = await res.json();
                const detail = data.notification_detail || {};
                const meta = {
                    kind: data.kind,
                    skipped: data.skipped,
                    notification: data.notification,
                    preview_only: !push || data.preview_only,
                    notif_reason: detail.reason
                };
                if (data.content) aiosShowDigestPreview(data.content, meta);

                let toast = '';
                if (data.skipped && push) {
                    toast = '今日该简报已发过，已展示内容';
                } else if (!push) {
                    toast = '已生成预览（未推送通知）';
                } else if (data.ok && data.notification) {
                    toast = '简报已推送到通知栏';
                } else if (data.ok) {
                    toast = '简报已生成 · ' + (detail.reason || '通知未成功');
                } else {
                    toast = data.error || '推送失败';
                }
                if (typeof showToast === 'function') showToast(toast);
                else if (!data.content) alert(toast);
                aiosLoadStatus();
            } catch (e) {
                if (typeof showToast === 'function') showToast('简报失败: ' + e.message);
                else alert('简报失败: ' + e.message);
            }
        }

        async function aiosAddMemory() {
            const input = document.getElementById('aios-memory-input');
            let text = (input && input.value || '').trim();
            if (!text) return;
            text = text.replace(/^(记住|请记住|记一下|帮我记住|记着|别忘了)[:：]?\s*/i, '');
            text = text.replace(/^remember(?:\s+that)?[:：]?\s*/i, '');
            if (!text) return;
            try {
                const res = await fetch('/api/aios/memories', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({ content: text, kind: 'fact', importance: 2 })
                });
                const data = await res.json();
                if (data.ok) {
                    if (input) input.value = '';
                    if (typeof showToast === 'function') showToast('已写入长期记忆');
                    aiosLoadStatus();
                } else {
                    if (typeof showToast === 'function') showToast(data.error || '添加失败');
                    else alert(data.error || '添加失败');
                }
            } catch (e) {
                if (typeof showToast === 'function') showToast('添加失败: ' + e.message);
                else alert('添加失败: ' + e.message);
            }
        }

        async function aiosDeleteMemory(id) {
            if (!id || !confirm('删除这条记忆？')) return;
            try {
                const res = await fetch('/api/aios/memories/' + encodeURIComponent(id), { method: 'DELETE' });
                const data = await res.json();
                if (data.ok || data.status === 'success') {
                    if (typeof showToast === 'function') showToast('已删除');
                    aiosLoadStatus();
                } else {
                    alert(data.error || '删除失败');
                }
            } catch (e) {
                alert('删除失败: ' + e.message);
            }
        }

        async function aiosPinMemory(id, pinned) {
            if (!id) return;
            try {
                const res = await fetch('/api/aios/memories/pin', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({ memory_id: id, pinned: !!pinned })
                });
                const data = await res.json();
                if (data.ok) {
                    if (typeof showToast === 'function') showToast(pinned ? '已置顶' : '已取消置顶');
                    aiosLoadStatus();
                } else {
                    alert(data.error || '操作失败');
                }
            } catch (e) {
                alert('操作失败: ' + e.message);
            }
        }

        window.aiosLoadStatus = aiosLoadStatus;
        window.aiosRefreshEntry = aiosRefreshEntry;
        window.aiosSendDigest = aiosSendDigest;
        window.aiosAddMemory = aiosAddMemory;
        window.aiosDeleteMemory = aiosDeleteMemory;
        window.aiosPinMemory = aiosPinMemory;
        window.aiosFilterMemories = aiosFilterMemories;

        window.closeWorkspaceConsole = closeWorkspaceConsole;
        window.startSystemPet = function startSystemPet() {
            // 通过 deep link 调起 AGI-Bot 宿主开启悬浮窗
            const url = 'magi://pet/start';
            try {
                // 优先 location（WebView 可拦截）
                window.location.href = url;
            } catch (e) {}
            // 同时尝试 iframe / a 标签，兼容部分 WebView
            try {
                const a = document.createElement('a');
                a.href = url;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                setTimeout(() => a.remove(), 500);
            } catch (e2) {}
            if (typeof showToast === 'function') {
                showToast('正在请求系统桌宠…若无反应请打开 AGI-Bot App');
            } else {
                alert('正在请求系统桌宠。\n若无反应，请打开 AGI-Bot 宿主 App 并点「开启系统桌宠」。\n需授予悬浮窗权限，且 8087 服务已运行。');
            }
        };
        window.stopSystemPet = function stopSystemPet() {
            try { window.location.href = 'magi://pet/stop'; } catch (e) {}
            try {
                const a = document.createElement('a');
                a.href = 'magi://pet/stop';
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                setTimeout(() => a.remove(), 500);
            } catch (e2) {}
            if (typeof showToast === 'function') showToast('已发送关闭桌宠请求');
        };

        window.copyCodeBlock = function(btn) {
            const container = btn.closest('.code-block-container');
            const codeEl = container.querySelector('code');
            const textToCopy = codeEl ? codeEl.textContent : "";
            
            navigator.clipboard.writeText(textToCopy).then(() => {
                const oldHTML = btn.innerHTML;
                btn.textContent = "已复制 ✅";
                setTimeout(() => { btn.innerHTML = oldHTML; }, 2000);
            }).catch(err => {
                alert("复制失败，请手动选择复制。");
            });
        };

        window.copyTerminalOutput = function(btn, stepId) {
            const detailEl = document.getElementById(stepId);
            const preEl = detailEl ? detailEl.querySelector('.term-output-text') : null;
            const textToCopy = preEl ? preEl.textContent : "";
            
            navigator.clipboard.writeText(textToCopy).then(() => {
                const oldText = btn.textContent;
                btn.textContent = "已复制 ✅";
                setTimeout(() => { btn.textContent = oldText; }, 2000);
            }).catch(err => {
                alert("复制失败，请手动选择复制。");
            });
        };

        window.setTerminalTheme = function(themeName) {
            document.body.setAttribute('data-terminal-theme', themeName);
            
            document.querySelectorAll('.term-theme-chip').forEach(btn => {
                btn.classList.remove('active');
            });
            
            const activeBtn = document.getElementById(`term-theme-btn-${themeName}`);
            if (activeBtn) {
                activeBtn.classList.add('active');
            }
            
            localStorage.setItem('micro-agi-term-theme', themeName);
        };

        let tunnelPollInterval = null;

        async function checkTunnelStatus() {
            // The capability check completes after DOMContentLoaded. Do not
            // probe a desktop-only tunnel route from the standalone app.
            if (window.microAgiCapabilitiesReady) {
                await window.microAgiCapabilitiesReady;
            }
            if (window.microAgiEmbedded !== false) return;
            try {
                const response = await fetch("/api/system/tunnel");
                const data = await response.json();
                
                const checkbox = document.getElementById("settings-tunnel-checkbox");
                const statusText = document.getElementById("settings-tunnel-status");
                
                if (!checkbox || !statusText) return;
                
                if (data.status === "active") {
                    checkbox.checked = true;
                    let tunnelUrl = null;
                    try {
                        const parsed = new URL(data.url);
                        if (parsed.protocol === 'https:' && parsed.hostname.endsWith('.lhr.life') &&
                            !parsed.username && !parsed.password) {
                            tunnelUrl = parsed;
                        }
                    } catch (_) {
                        // A malformed tunnel address must never become HTML or a link.
                    }
                    statusText.textContent = tunnelUrl ? '✅ 已开启: ' : '✅ 已开启，地址暂不可用';
                    if (tunnelUrl) {
                        const link = document.createElement('a');
                        link.href = tunnelUrl.href;
                        link.target = '_blank';
                        link.rel = 'noopener noreferrer';
                        link.style.cssText = 'color: var(--primary); font-weight: bold; text-decoration: underline;';
                        link.textContent = tunnelUrl.href;
                        statusText.appendChild(link);
                    }
                    
                    if (tunnelPollInterval) {
                        clearInterval(tunnelPollInterval);
                        tunnelPollInterval = setInterval(checkTunnelStatus, 8000);
                    }
                } else if (data.status === "starting") {
                    checkbox.checked = true;
                    statusText.textContent = "⏳ 正在建立穿透通道，请稍候...";
                    
                    if (!tunnelPollInterval) {
                        tunnelPollInterval = setInterval(checkTunnelStatus, 2000);
                    }
                } else if (data.status === "failed") {
                    checkbox.checked = false;
                    statusText.textContent = "❌ 连接失败，请重试";
                    if (tunnelPollInterval) {
                        clearInterval(tunnelPollInterval);
                        tunnelPollInterval = null;
                    }
                } else {
                    checkbox.checked = false;
                    statusText.textContent = "已关闭";
                    if (tunnelPollInterval) {
                        clearInterval(tunnelPollInterval);
                        tunnelPollInterval = null;
                    }
                }
            } catch (err) {
                console.error("Failed to check tunnel status:", err);
            }
        }

        async function toggleTunnelConnection() {
            const checkbox = document.getElementById("settings-tunnel-checkbox");
            const statusText = document.getElementById("settings-tunnel-status");
            const active = checkbox.checked;
            
            if (active) {
                statusText.textContent = "⏳ 正在请求分配域名...";
            } else {
                statusText.textContent = "⏳ 正在断开连接...";
            }
            
            try {
                const response = await fetch("/api/system/tunnel", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ active: active })
                });
                
                setTimeout(checkTunnelStatus, 1000);
                
                if (active) {
                    if (tunnelPollInterval) clearInterval(tunnelPollInterval);
                    tunnelPollInterval = setInterval(checkTunnelStatus, 2000);
                } else {
                    if (tunnelPollInterval) {
                        clearInterval(tunnelPollInterval);
                        tunnelPollInterval = null;
                    }
                }
            } catch (err) {
                console.error("Failed to toggle tunnel:", err);
                alert("操作请求发送失败");
                checkbox.checked = !active;
                checkTunnelStatus();
            }
        }

        window.checkTunnelStatus = checkTunnelStatus;
        window.toggleTunnelConnection = toggleTunnelConnection;

        // --- Extensions, Skills & MCP Integration ---
        let allExtensionsData = [];
        let showingSkillsChips = false;

        async function loadExtensions() {
            const skillsContainer = document.getElementById('dynamic-skills-container');
            const mcpContainer = document.getElementById('dynamic-mcp-container');
            if (!skillsContainer || !mcpContainer) return;
            
            try {
                const response = await fetch('/api/system/extensions');
                allExtensionsData = await response.json();
                renderExtensions(allExtensionsData);
            } catch (err) {
                console.error("加载扩展/技能失败:", err);
                skillsContainer.textContent = `加载失败: ${err.message}`;
                mcpContainer.textContent = `加载失败: ${err.message}`;
            }
        }

        function renderExtensions(extensions) {
            const skillsContainer = document.getElementById('dynamic-skills-container');
            const mcpContainer = document.getElementById('dynamic-mcp-container');
            if (!skillsContainer || !mcpContainer) return;
            
            skillsContainer.innerHTML = '';
            mcpContainer.innerHTML = '';
            
            const skillsList = extensions.filter(e => e.type === 'skill' || e.type === 'plugin');
            const mcpList = extensions.filter(e => e.type === 'mcp');
            
            if (skillsList.length === 0) {
                skillsContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.75rem;">无符合条件的自研技能</div>`;
            } else {
                skillsList.forEach(ext => {
                    skillsContainer.appendChild(createExtensionCard(ext));
                });
            }
            
            if (mcpList.length === 0) {
                mcpContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.75rem;">尚未接入 MCP 端点</div>`;
            } else {
                mcpList.forEach(ext => {
                    mcpContainer.appendChild(createExtensionCard(ext));
                });
            }
        }

        function createExtensionCard(ext) {
            const card = document.createElement('div');
            card.className = 'extension-card';
            card.setAttribute('data-id', ext.id);
            card.setAttribute('data-type', ext.type);
            
            const safeType = ['skill', 'plugin', 'mcp'].includes(ext.type) ? ext.type : 'plugin';
            
            card.innerHTML = `
                <div class="extension-header">
                    <div class="extension-title-block">
                        <span class="extension-icon">${escapeHtml(ext.icon || '🧩')}</span>
                        <div class="extension-details">
                            <div class="extension-name">${escapeHtml(ext.name)}</div>
                            <div class="extension-type-badge ${safeType}">${safeType === 'skill' ? '技能库' : safeType === 'mcp' ? 'MCP 端点' : '本地脚本'}</div>
                        </div>
                    </div>
                    <div class="extension-status-block">
                        <span class="status-indicator active">● 已检测</span>
                    </div>
                </div>
                <div class="extension-desc">${escapeHtml(ext.description)}</div>
            `;
            return card;
        }

        function filterConsoleExtensions() {
            const query = document.getElementById('extension-search').value.toLowerCase().trim();
            if (!query) {
                renderExtensions(allExtensionsData);
                return;
            }
            const filtered = allExtensionsData.filter(ext => 
                ext.name.toLowerCase().includes(query) || 
                ext.description.toLowerCase().includes(query) ||
                ext.id.toLowerCase().includes(query)
            );
            renderExtensions(filtered);
        }

        function toggleSkillsChips() {
            showingSkillsChips = !showingSkillsChips;
            const toggleBtn = document.getElementById('skills-toggle-btn');
            if (toggleBtn) {
                if (showingSkillsChips) {
                    toggleBtn.style.color = '#ef4444'; // Highlight Rose color when active
                    toggleBtn.title = "显示默认指令";
                } else {
                    toggleBtn.style.color = 'var(--primary)';
                    toggleBtn.title = "快捷技能与扩展";
                }
            }
            
            if (showingSkillsChips) {
                renderSkillsChips();
            } else {
                restoreDefaultChips();
            }
        }

        function renderSkillsChips() {
            const container = document.querySelector('.suggestions-container');
            if (!container) return;
            
            const activeExts = allExtensionsData.filter(e => e.enabled);
            if (activeExts.length === 0) {
                container.innerHTML = `<div style="font-size: 0.72rem; color: var(--text-muted); padding: 4px 8px; width: 100%; text-align: center;">没有检测到本地技能。</div>`;
                return;
            }
            
            container.innerHTML = '';
            
            // Limit to top 4 active skills to prevent overflowing screen
            const displayLimit = 4;
            const toDisplay = activeExts.slice(0, displayLimit);
            
            toDisplay.forEach(ext => {
                const chip = document.createElement('button');
                chip.className = 'suggestion-chip';
                chip.style.marginRight = '8px';
                
                if (ext.type === 'skill') {
                    chip.style.borderColor = 'rgba(6, 182, 212, 0.4)';
                } else if (ext.type === 'mcp') {
                    chip.style.borderColor = 'rgba(34, 211, 238, 0.4)';
                } else {
                    chip.style.borderColor = 'rgba(139, 92, 246, 0.4)';
                }
                
                chip.textContent = `${ext.icon || '🧠'} ${ext.name}`;
                chip.onclick = () => {
                    chatInput.value = `请使用${ext.name}帮我：`;
                    chatInput.focus();
                };
                container.appendChild(chip);
            });
            
            // Add trailing expand button
            const moreBtn = document.createElement('button');
            moreBtn.className = 'suggestion-chip more-skills-pulsate-btn';
            moreBtn.innerHTML = `✨ 更多...`;
            moreBtn.onclick = () => {
                toggleStore();
            };
            container.appendChild(moreBtn);
        }

        function restoreDefaultChips() {
            const container = document.querySelector('.suggestions-container');
            if (!container) return;
            container.innerHTML = `
                <div class="suggestion-chip" onclick="sendSuggestion('查看当前系统硬件配置')">🔍 查系统信息</div>
                <div class="suggestion-chip" onclick="sendSuggestion('列出当前文件夹下的全部文件')">📂 看当前文件</div>
                <div class="suggestion-chip" onclick="sendSuggestion('生成一个名叫 test_hello.txt 的文件并在里面写上 Hello World')">📝 写测试文件</div>
                <div class="suggestion-chip" onclick="sendSuggestion('检查我的本地 IP 地址 and 网络状态')">🌐 查网络 IP</div>
            `;
        }

        // Attach them to window
        window.loadExtensions = loadExtensions;
        window.filterConsoleExtensions = filterConsoleExtensions;
        window.toggleSkillsChips = toggleSkillsChips;
        window.renderSkillsChips = renderSkillsChips;
        window.restoreDefaultChips = restoreDefaultChips;
        window.toggleStore = toggleStore;
        window.toggleMCP = toggleMCP;

        // Auto fetch list at startup to populate allExtensionsData
        loadExtensions();

        // Slash command dropdown listener on input
        chatInput.addEventListener('input', () => {
            const val = chatInput.value;
            const dropdown = document.getElementById('slash-command-dropdown');
            if (!dropdown) return;
            
            if (val.startsWith('/')) {
                const search = val.substring(1).toLowerCase();
                const matches = allExtensionsData.filter(e => 
                    e.enabled && (
                        e.id.toLowerCase().includes(search) || 
                        e.name.toLowerCase().includes(search)
                    )
                );
                
                if (matches.length > 0) {
                    dropdown.innerHTML = '';
                    matches.forEach(ext => {
                        const item = document.createElement('div');
                        item.style.padding = '8px 12px';
                        item.style.cursor = 'pointer';
                        item.style.display = 'flex';
                        item.style.alignItems = 'center';
                        item.style.justifyContent = 'space-between';
                        item.style.fontSize = '0.8rem';
                        item.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                        item.style.transition = 'background 0.2s';
                        
                        item.addEventListener('mouseenter', () => {
                            item.style.background = 'rgba(255, 255, 255, 0.05)';
                        });
                        item.addEventListener('mouseleave', () => {
                            item.style.background = 'transparent';
                        });
                        
                        const summary = document.createElement('div');
                        summary.style.cssText = 'display: flex; align-items: center; gap: 8px; color: var(--text-color);';
                        const icon = document.createElement('span');
                        icon.textContent = ext.icon || '🧩';
                        const command = document.createElement('span');
                        command.style.fontWeight = '600';
                        command.textContent = `/${ext.id}`;
                        const name = document.createElement('span');
                        name.style.cssText = 'color: var(--text-muted); font-size: 0.72rem;';
                        name.textContent = ext.name;
                        summary.append(icon, command, name);
                        const description = document.createElement('div');
                        description.style.cssText = 'font-size: 0.65rem; color: var(--text-muted); max-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;';
                        description.textContent = ext.description || '';
                        item.append(summary, description);
                        
                        item.onclick = () => {
                            chatInput.value = `/${ext.id} `;
                            dropdown.style.display = 'none';
                            chatInput.focus();
                        };
                        dropdown.appendChild(item);
                    });
                    dropdown.style.display = 'block';
                } else {
                    dropdown.style.display = 'none';
                }
            } else {
                dropdown.style.display = 'none';
            }
        });

        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('slash-command-dropdown');
            if (dropdown && !chatInput.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });

        // --- Google Login & API Configuration Helpers ---
        // --- Google Login & API Configuration Helpers ---
        async function updateGoogleLoginStatus() {
            try {
                const response = await fetch("/api/system/google_status");
                if (!response.ok) return;
                const data = await response.json();
                if (window.microAgiEmbedded) {
                    const urlInput = document.getElementById('custom-ai-url');
                    const modelInput = document.getElementById('custom-ai-model');
                    if (urlInput && document.activeElement !== urlInput) urlInput.value = data.ai_url || '';
                    if (modelInput && document.activeElement !== modelInput) modelInput.value = data.ai_model || '';
                    setModelProvider(data.ai_url ? 'compatible' : 'gemini');
                    const editor = document.getElementById('model-config-editor');
                    if (editor) editor.open = !(data.gemini_key_configured || data.ai_key_configured);
                    markEmbeddedGoogleAuth(data.gemini_key_configured ||
                        (data.ai_url && data.ai_key_configured));
                    return;
                }
                
                const statusEl = document.getElementById("google-login-status");
                const authBtn = document.getElementById("google-settings-auth-btn");
                const authZone = document.getElementById("google-settings-auth-input-zone");
                const keyInput = document.getElementById("custom-gemini-key");
                
                if (data.gemini_key) {
                    keyInput.value = data.gemini_key;
                }
                
                const isAgy = data.llm_backend === "agy";
                
                if (data.status === "connected") {
                    if (statusEl) {
                        statusEl.innerHTML = isAgy 
                            ? '<span style="color: #34a853; font-weight: bold;">🟢 已绑定 Antigravity (agy)</span>'
                            : '<span style="color: #34a853; font-weight: bold;">已关联 Google</span>';
                    }
                    if (authBtn) {
                        authBtn.innerHTML = isAgy ? "🔄 重新登录绑定 (Antigravity CLI)" : "🔓 断开 Google 账号关联";
                        authBtn.style.background = isAgy ? "rgba(255,255,255,0.05)" : "rgba(239, 68, 68, 0.1)";
                        authBtn.style.color = isAgy ? "#fff" : "var(--error)";
                        authBtn.style.borderColor = isAgy ? "rgba(255,255,255,0.1)" : "rgba(239, 68, 68, 0.3)";
                        authBtn.onclick = isAgy ? triggerGoogleLogin : triggerGoogleLogout;
                    }
                } else {
                    if (statusEl) {
                        statusEl.innerHTML = isAgy 
                            ? '<span style="color: #ef4444; font-weight: bold;">🔴 未关联 (Antigravity CLI)</span>'
                            : '<span style="color: #ef4444; font-weight: bold;">未关联</span>';
                    }
                    if (authBtn) {
                        authBtn.innerHTML = `
                            <span aria-hidden="true">G</span>
                            关联 Google 账号登录 (免 Key)
                        `;
                        authBtn.style.background = "rgba(66, 133, 244, 0.15)";
                        authBtn.style.color = "#8ab4f8";
                        authBtn.style.borderColor = "rgba(66, 133, 244, 0.4)";
                        authBtn.onclick = triggerGoogleLogin;
                    }
                }
            } catch (err) {
                console.error("Error fetching google status:", err);
            }
        }

        async function triggerGoogleLogin() {
            if (window.microAgiEmbedded !== false) return;
            const btn = document.getElementById('google-settings-auth-btn');
            const zone = document.getElementById('google-settings-auth-input-zone');
            if (!btn || !zone) return;
            
            try {
                const checkRes = await fetch("/api/system/google_status");
                const checkData = await checkRes.json();
                if (checkData.llm_backend !== "agy") {
                    window.open("/google_login", "_blank", "width=500,height=600,location=no,menubar=no,status=no");
                    return;
                }
            } catch(e) {}
            
            btn.innerText = "正在拉起授权...";
            btn.disabled = true;
            
            try {
                const response = await fetch('/api/system/auth/init', { method: 'POST' });
                const data = await response.json();
                
                if (data.ok && data.url) {
                    btn.innerText = "请在浏览器中登录";
                    zone.style.display = "flex";
                    if (window.AndroidBridge && typeof window.AndroidBridge.openExternalBrowser === 'function') {
                        window.AndroidBridge.openExternalBrowser(data.url);
                    } else {
                        window.location.href = data.url;
                    }
                } else {
                    btn.innerText = "获取失败，重试";
                    btn.disabled = false;
                    alert("错误: " + (data.message || "无法拉起 OAuth 链接"));
                }
            } catch (e) {
                btn.innerText = "连接失败，重试";
                btn.disabled = false;
                alert("连接服务失败: " + e.message);
            }
        }

        async function submitGoogleAuthCode() {
            const input = document.getElementById('google-settings-auth-code');
            const zone = document.getElementById('google-settings-auth-input-zone');
            const btn = document.getElementById('google-settings-auth-btn');
            if (!input || !zone || !btn) return;
            
            const code = input.value.trim();
            if (!code) {
                alert("请输入您获取到的验证 Code！");
                return;
            }
            
            try {
                const response = await fetch('/api/system/auth/confirm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
                const data = await response.json();
                
                if (data.ok) {
                    alert("🔑 恭喜，Google 账号在手机本地的 Antigravity CLI (agy) 下已成功授权绑定！");
                    zone.style.display = "none";
                    input.value = "";
                    btn.disabled = false;
                    updateGoogleLoginStatus();
                } else {
                    alert("绑定失败: " + data.message);
                }
            } catch (e) {
                alert("提交 Code 失败: " + e.message);
            }
        }

        async function triggerGoogleLogout() {
            if (!confirm("确定要断开 Google 账号的关联吗？")) return;
            try {
                const response = await fetch("/api/system/google_logout", { method: "POST" });
                if (response.ok) {
                    updateGoogleLoginStatus();
                }
            } catch (err) {
                console.error("Error logging out:", err);
            }
        }

        async function saveCustomKeys() {
            const keyInput = document.getElementById("custom-gemini-key");
            const geminiKey = keyInput.value.trim();
            const statusEl = document.getElementById("google-login-status");
            try {
                const response = await fetch("/api/system/save_gemini_key", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ gemini_key: geminiKey })
                });
                if (response.ok) {
                    keyInput.value = '';
                    updateGoogleLoginStatus();
                } else if (statusEl) {
                    statusEl.textContent = 'API Key 保存失败，请重试';
                }
            } catch (err) {
                console.error("Error saving keys:", err);
                if (statusEl) statusEl.textContent = 'API Key 保存失败，请重试';
            }
        }

        function clearCustomKey() {
            if (!confirm('确定清除已保存的 Gemini API Key 吗？')) return;
            document.getElementById('custom-gemini-key').value = '';
            saveCustomKeys();
        }

        async function saveCompatibleModel() {
            const urlInput = document.getElementById('custom-ai-url');
            const modelInput = document.getElementById('custom-ai-model');
            const keyInput = document.getElementById('custom-ai-key');
            const statusEl = document.getElementById('google-login-status');
            let aiUrl = urlInput.value.trim().replace(/\/$/, '');
            if (aiUrl.endsWith('/v1')) aiUrl += '/chat/completions';
            try {
                const parsed = new URL(aiUrl);
                if (parsed.protocol !== 'https:' || !parsed.pathname.endsWith('/chat/completions') ||
                    !modelInput.value.trim() || !keyInput.value.trim()) {
                    statusEl.textContent = '请填写 HTTPS 聊天地址、模型名称和 Key';
                    return;
                }
                const response = await fetch('/api/system/save_gemini_key', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({gemini_key: '', ai_url: aiUrl,
                        ai_model: modelInput.value.trim(), ai_key: keyInput.value.trim()})
                });
                if (!response.ok) {
                    statusEl.textContent = '模型配置保存失败，请检查地址和输入';
                    return;
                }
                keyInput.value = '';
                document.getElementById('custom-gemini-key').value = '';
                urlInput.value = aiUrl;
                await updateGoogleLoginStatus();
            } catch (_) {
                statusEl.textContent = '模型配置保存失败，请检查地址和连接';
            }
        }

        function triggerTerminalToggle() {
            if (window.microAgiEmbedded !== false) return;
            const agiApp = window.MicroAGI || window.MicroAgi || window.microAgi || window.TermuxApp;
            if (agiApp && typeof agiApp.toggleTerminal === 'function') {
                agiApp.toggleTerminal();
            } else {
                alert("提示：当前运行环境不是 Micro-AGI 安卓 App，无法调用底层终端窗口。若是在普通浏览器中，请在 Termux 终端内直接使用 'tmux attach' 命令访问控制台。");
            }
        }

        window.openTerminalTab = function() {
            toggleQuickTerminal();
        };

        window.toggleQuickTerminal = function() {
            if (window.microAgiEmbedded !== false) return;
            const term = document.getElementById('quickTerminal');
            const chatArea = document.getElementById('chatArea');
            const suggestions = document.getElementById('suggestionsContainer');
            const outputEl = document.getElementById('quick-terminal-output');
            
            if (term) {
                const isHidden = window.getComputedStyle(term).display === 'none';
                if (isHidden) {
                    term.style.setProperty('display', 'flex', 'important');
                    if (chatArea) chatArea.style.setProperty('display', 'none', 'important');
                    if (suggestions) suggestions.style.setProperty('display', 'none', 'important');
                    
                    term.style.maxHeight = '80vh';
                    if (outputEl) outputEl.style.maxHeight = '70vh';
                    
                    const inp = document.getElementById('quick-terminal-input');
                    if (inp) {
                        inp.focus();
                        setTimeout(() => {
                            term.scrollIntoView({ behavior: 'smooth', block: 'end' });
                        }, 100);
                    }
                } else {
                    term.style.setProperty('display', 'none', 'important');
                    if (chatArea) chatArea.style.setProperty('display', 'flex', 'important');
                    if (suggestions) suggestions.style.setProperty('display', 'flex', 'important');
                    
                    term.style.maxHeight = '250px';
                    if (outputEl) outputEl.style.maxHeight = '160px';
                }
            }
        };

        window.clearQuickTerminal = function() {
            const out = document.getElementById('quick-terminal-output');
            if (out) {
                out.innerHTML = "Welcome to Micro-AGI Web Terminal.<br>Type your shell command below and press Enter or click Execute.";
            }
        };

        window.executeQuickTerminalCommand = async function() {
            if (window.microAgiEmbedded !== false) return;
            const inputEl = document.getElementById('quick-terminal-input');
            const outputEl = document.getElementById('quick-terminal-output');
            if (!inputEl || !outputEl) return;
            
            const cmd = inputEl.value.trim();
            if (!cmd) return;
            
            // Append command line with styled prompt
            const cmdLine = document.createElement('div');
            cmdLine.style.marginTop = '8px';
            const prompt = document.createElement('span');
            prompt.style.cssText = 'color: #a6e22e; font-weight: bold; font-family: monospace;';
            prompt.textContent = '$';
            const commandText = document.createElement('span');
            commandText.style.cssText = 'color: #f8f8f2; font-family: monospace;';
            commandText.textContent = ` ${cmd}`;
            cmdLine.append(prompt, commandText);
            outputEl.appendChild(cmdLine);
            outputEl.scrollTop = outputEl.scrollHeight;
            
            inputEl.value = '';
            
            try {
                const response = await fetch('/api/system/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cmd: cmd })
                });
                const data = await response.json();
                
                if (data.stdout) {
                    const pre = document.createElement('pre');
                    pre.style.margin = '0';
                    pre.style.whiteSpace = 'pre-wrap';
                    pre.style.color = '#38bdf8';
                    pre.style.fontFamily = 'monospace';
                    pre.textContent = data.stdout;
                    outputEl.appendChild(pre);
                }
                if (data.stderr) {
                    const pre = document.createElement('pre');
                    pre.style.margin = '0';
                    pre.style.whiteSpace = 'pre-wrap';
                    pre.style.color = '#ef4444';
                    pre.style.fontFamily = 'monospace';
                    pre.textContent = data.stderr;
                    outputEl.appendChild(pre);
                }
                if (!data.stdout && !data.stderr) {
                    const div = document.createElement('div');
                    div.style.color = '#a1a1aa';
                    div.style.fontSize = '0.7rem';
                    div.style.fontFamily = 'monospace';
                    div.textContent = `(命令执行完毕，返回值: ${data.exit_code})`;
                    outputEl.appendChild(div);
                }
                outputEl.scrollTop = outputEl.scrollHeight;
            } catch (err) {
                const div = document.createElement('div');
                div.style.color = '#ef4444';
                div.style.fontFamily = 'monospace';
                div.textContent = `请求失败: ${err.message}`;
                outputEl.appendChild(div);
                outputEl.scrollTop = outputEl.scrollHeight;
            }
        };

        async function executeTerminalCommand() {
            if (window.microAgiEmbedded !== false) return;
            const inputEl = document.getElementById('terminal-input');
            const outputEl = document.getElementById('terminal-output');
            if (!inputEl || !outputEl) return;
            
            const cmd = inputEl.value.trim();
            if (!cmd) return;
            
            // Append command line with styled prompt
            const cmdLine = document.createElement('div');
            cmdLine.style.marginTop = '8px';
            const prompt = document.createElement('span');
            prompt.style.cssText = 'color: #a6e22e; font-weight: bold;';
            prompt.textContent = '$';
            const commandText = document.createElement('span');
            commandText.style.cssText = 'color: #f8f8f2; font-family: monospace;';
            commandText.textContent = ` ${cmd}`;
            cmdLine.append(prompt, commandText);
            outputEl.appendChild(cmdLine);
            outputEl.scrollTop = outputEl.scrollHeight;
            
            inputEl.value = '';
            
            try {
                const response = await fetch('/api/system/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cmd: cmd })
                });
                const data = await response.json();
                
                if (data.stdout) {
                    const pre = document.createElement('pre');
                    pre.style.margin = '0';
                    pre.style.whiteSpace = 'pre-wrap';
                    pre.style.color = '#38bdf8';
                    pre.style.fontFamily = 'monospace';
                    pre.textContent = data.stdout;
                    outputEl.appendChild(pre);
                }
                if (data.stderr) {
                    const pre = document.createElement('pre');
                    pre.style.margin = '0';
                    pre.style.whiteSpace = 'pre-wrap';
                    pre.style.color = '#ef4444';
                    pre.style.fontFamily = 'monospace';
                    pre.textContent = data.stderr;
                    outputEl.appendChild(pre);
                }
                if (!data.stdout && !data.stderr) {
                    const div = document.createElement('div');
                    div.style.color = '#a1a1aa';
                    div.style.fontSize = '0.7rem';
                    div.style.fontFamily = 'monospace';
                    div.textContent = `(命令执行完毕，返回值: ${data.exit_code})`;
                    outputEl.appendChild(div);
                }
                outputEl.scrollTop = outputEl.scrollHeight;
            } catch (err) {
                const div = document.createElement('div');
                div.style.color = '#ef4444';
                div.style.fontFamily = 'monospace';
                div.textContent = `请求失败: ${err.message}`;
                outputEl.appendChild(div);
                outputEl.scrollTop = outputEl.scrollHeight;
            }
        }

        function clearTerminalScreen() {
            const outputEl = document.getElementById('terminal-output');
            if (outputEl) {
                outputEl.innerHTML = "Welcome to Micro-AGI Web Terminal.<br>Type your shell command below and press Enter or click Execute.";
            }
        }

        function sendCtrlC() {
            const outputEl = document.getElementById('terminal-output');
            if (outputEl) {
                const div = document.createElement('div');
                div.style.color = '#f87171';
                div.style.fontFamily = 'monospace';
                div.textContent = '^C (已发送中断信号)';
                outputEl.appendChild(div);
                outputEl.scrollTop = outputEl.scrollHeight;
            }
        }


        window.addEventListener('DOMContentLoaded', () => {
            const inputEl = document.getElementById('terminal-input');
            if (inputEl) {
                inputEl.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        executeTerminalCommand();
                    }
                });
            }
            
            const quickInputEl = document.getElementById('quick-terminal-input');
            if (quickInputEl) {
                quickInputEl.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        executeQuickTerminalCommand();
                    }
                });
            }
            
            // Add Ctrl + ` keyboard shortcut to toggle terminal
            window.addEventListener('keydown', function(e) {
                if (e.ctrlKey && (e.key === '`' || e.key === '~')) {
                    e.preventDefault();
                    openTerminalTab();
                }
            });
        });
