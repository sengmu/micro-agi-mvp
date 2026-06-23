        const chatArea = document.getElementById("chatArea");
        const chatInput = document.getElementById("chatInput");
        const sendBtn = document.getElementById("sendBtn");
        const quickTerminal = document.getElementById("quickTerminal");

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
                chatInput.placeholder = "正在聆听指令...";
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
                    chatInput.placeholder = "输入一条控制指令 (例如: 列出当前文件)...";
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
            chatInput.placeholder = "输入一条控制指令 (例如: 列出当前文件)...";
        }

        function toggleVoiceInput() {
            if (chatInput.disabled) return;
            if (!recognition) {
                initVoiceInput();
            }
            if (!recognition) {
                chatInput.placeholder = "🎙️ 浏览器不支持语音输入";
                setTimeout(() => {
                    chatInput.placeholder = "输入一条控制指令 (例如: 列出当前文件)...";
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
                
                let contentHtml = "";
                if (att.status === 'reading') {
                    contentHtml = `
                        <div style="position: absolute; bottom: 0; left: 0; height: 2px; background: var(--primary); width: ${att.progress}%; transition: width 0.1s;" id="progress-${att.id}"></div>
                        ⏳ <span>读取中...</span>
                    `;
                } else if (att.status === 'error') {
                    contentHtml = `❌ <span style="color:red;">读取失败</span>`;
                } else {
                    let icon = "📄";
                    if (att.type === 'skill') {
                        icon = "🔌";
                        item.style.background = "linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(139, 92, 246, 0.2))";
                        item.style.borderColor = "var(--primary)";
                        item.style.color = "#cffafe";
                    } else if (att.type.startsWith("image/") && att.data) {
                        icon = `<img src="${att.data}" style="width:24px; height:24px; object-fit:cover; border-radius:4px;">`;
                    }
                    contentHtml = `
                        ${icon}
                        <span style="max-width: 100px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${att.name}">${att.name}</span>
                        <button class="remove-btn" onclick="removeAttachment('${att.id}')" style="background:none; border:none; color:var(--error); cursor:pointer; padding:2px; font-size:1.1rem; line-height:1;">×</button>
                    `;
                }
                
                item.innerHTML = contentHtml;
                previewContainer.appendChild(item);
            });
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
            let displayHtml = text;
            if (currentAttachments.length > 0) {
                let attHtml = `<div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px;">`;
                currentAttachments.forEach(att => {
                    if (att.type === 'skill') {
                        attHtml += `<span style="background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(139, 92, 246, 0.2)); color: #cffafe; padding: 4px 8px; border-radius: 4px; border: 1px solid var(--primary); font-size: 0.8rem;">🔌 技能: ${att.name}</span>`;
                    } else if (att.type.startsWith("image/")) {
                        attHtml += `<img src="${att.data}" style="max-width: 200px; max-height: 200px; border-radius: 4px; object-fit: cover;">`;
                    } else {
                        attHtml += `<span style="background: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem;">📄 ${att.name}</span>`;
                    }
                });
                attHtml += `</div>`;
                displayHtml = attHtml + (text ? `<div>${text}</div>` : "");
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
            const loadingId = appendLoading();
            chatArea.scrollTop = chatArea.scrollHeight;

            // Trigger Live2D thinking state and cancel previous speech
            stopSpeech();
            if (live2dModel) {
                live2dModel.motion('FlickDown');
            }

            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        message: finalPayloadText,
                        history: chatHistory,
                        attachments: fileAttachments,
                        chat_id: currentChatId
                    }),
                    signal: currentController.signal
                });

                const data = await response.json();
                
                // If backend returned a chat_id and our currentChatId was empty, set it
                if (data.chat_id && currentChatId === "") {
                    currentChatId = data.chat_id;
                    const title = text ? (text.slice(0, 16) + (text.length > 16 ? "..." : "")) : "新对话";
                    const headerTitle = document.getElementById('header-chat-title');
                    if (headerTitle) {
                        headerTitle.textContent = title;
                    }
                    loadChatSessions(false);
                }

                // Remove loading regardless of completion
                const loadingDots = document.querySelectorAll(".loading-dots");
                loadingDots.forEach(d => d.parentElement.parentElement.parentElement.remove());

                if (data.error) {
                    appendMessage("assistant", "系统错误", `执行发生错误: ${data.error}`);
                    if (live2dModel) {
                        live2dModel.motion('Flick');
                    }
                    if (isVoiceEnabled) {
                        speakText("发生了一些错误，请主人检查后台日志。");
                    }
                } else {
                    handleAgentResponse(data, text || "[包含附件的消息]");
                }
            } catch (err) {
                const loadingDots = document.querySelectorAll(".loading-dots");
                loadingDots.forEach(d => d.parentElement.parentElement.parentElement.remove());
                
                if (err.name === 'AbortError') {
                    appendMessage("assistant", "Hiyori", "⚠️ 对话已被您手动打断。");
                    if (live2dModel) {
                        live2dModel.motion('Idle');
                    }
                } else {
                    appendMessage("assistant", "连接失败", `无法连接: ${err.message}`);
                    if (live2dModel) {
                        live2dModel.motion('Flick');
                    }
                    if (isVoiceEnabled) {
                        speakText("无法连接到后台服务，请检查网络。");
                    }
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
                    appendMessage("assistant", "Micro-AGI", data.thoughts);
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
                chatInput.placeholder = "输入一条控制指令 (例如: 列出当前文件)...";

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
                        <textarea class="approval-bubble-cmd" id="approval-bubble-cmd">${command}</textarea>
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
            if (!cardId) return;

            const loadingId = appendLoading();
            chatArea.scrollTop = chatArea.scrollHeight;
            
            chatInput.disabled = true;
            document.getElementById("attachBtn").disabled = true;
            setSendBtnState(true);
            currentController = new AbortController();

            try {
                const response = await fetch("/api/approve", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ approved: approved, edited_command: editedCommand }),
                    signal: currentController.signal
                });

                const data = await response.json();
                document.getElementById(loadingId).remove();

                if (data.error) {
                    appendMessage("assistant", "系统错误", `执行发生错误: ${data.error}`);
                } else {
                    handleAgentResponse(data);
                }
            } catch (err) {
                if (document.getElementById(loadingId)) document.getElementById(loadingId).remove();
                
                if (err.name === 'AbortError') {
                    appendMessage("assistant", "Hiyori", "⚠️ 命令执行与对话已被您手动打断。");
                } else {
                    appendMessage("assistant", "连接失败", `无法连接: ${err.message}`);
                }
            } finally {
                chatInput.disabled = false;
                document.getElementById("attachBtn").disabled = false;
                setSendBtnState(false);
                currentController = null;
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
            if (!unsafe) return "";
            return unsafe.toString()
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
            // Simple markdown parsing for text
            let parsedContent = (response || "").replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
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
                if (lang.toLowerCase() === 'html' || lang.toLowerCase() === 'htm') {
                    html += `<div style="margin-bottom: 8px;"><button class="tool-btn" style="font-size: 0.75rem; padding: 6px 12px; display: inline-flex; align-items: center; gap: 6px;" onclick="openLivePreview(decodeURIComponent('${encodedCode}'))">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                        沙盒预览 (Split-Screen)
                    </button></div>`;
                }
                return html;
            });
            // Fallback for ``` without lang
            parsedContent = parsedContent.replace(/```([\s\S]*?)```/g, function(match, code) {
                const escapedCode = escapeHtml(code);
                return `
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
            });
            parsedContent = parsedContent.replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.1); padding: 2px 4px; border-radius: 4px; color: #fbd38d;">$1</code>');
            parsedContent = parsedContent.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
            parsedContent = parsedContent.replace(/\n/g, '<br>');

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
            showWelcomeBubble(randomText);
            
            if (isVoiceEnabled) {
                speakText(randomText);
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
            const zoomScale = baseScale * (isMobile ? 1.5 : 1.65);
            live2dModel.scale.set(zoomScale);
            
            live2dModel.x = (live2dContainer.clientWidth - (nativeWidth * zoomScale)) / 2;
            live2dModel.y = 20;

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

        async function initLive2D() {
            if (typeof PIXI === 'undefined' || typeof PIXI.live2d === 'undefined') {
                console.warn("WebGL libraries (PIXI.js / pixi-live2d-display) failed to load. Running in text-only mode.");
                const container = document.querySelector('.avatar-container');
                if (container) container.style.display = 'none';
                return;
            }
            const canvas = document.getElementById('vrm-canvas');
            if (!canvas) return;
            live2dContainer = canvas.parentElement;
            
            try {
                window.PIXI = PIXI;
                
                live2dApp = new PIXI.Application({
                    view: canvas,
                    transparent: true,
                    autoStart: true,
                    antialias: true,
                    resizeTo: live2dContainer,
                    resolution: window.devicePixelRatio || 1
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
                
            } catch (err) {
                console.error("Live2D init error:", err);
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
            if (!text) return;

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
            window.speechSynthesis.cancel();
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

        function escapeHtml(text) {
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
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
        window.addEventListener('DOMContentLoaded', () => {
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/sw.js')
                    .then((reg) => console.log('Service Worker registered successfully:', reg.scope))
                    .catch((err) => console.warn('Service Worker registration failed:', err));
            }

            const savedTheme = localStorage.getItem('micro-agi-theme');
            if (savedTheme && themes[savedTheme]) {
                setTheme(savedTheme);
            }

            // Restore Terminal & Code Theme
            const savedTermTheme = localStorage.getItem('micro-agi-term-theme') || 'dark';
            setTerminalTheme(savedTermTheme);

            loadAvatarBgSettings();
            loadChatSessions(true); // Pass true to autoSelectLast on load
            checkSystemUpdate(); // Check for hot update on load
            checkTunnelStatus(); // Check network tunnel status
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
                            <div class="history-item-title" title="${escapeHtml(chat.title)}">${escapeHtml(chat.title)}</div>
                            <div class="history-item-actions">
                                <button class="history-action-btn edit-btn" onclick="renameChatSession('${chat.chat_id}', '${escapeHtml(chat.title)}', event)" title="重命名">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>
                                </button>
                                <button class="history-action-btn delete-btn" onclick="deleteChatSession('${chat.chat_id}', event)" title="删除对话">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        `;
                        
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
                const activeItem = document.querySelector(`.history-item[data-id="${chatId}"]`);
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
                const response = await fetch(`/api/chats/${chatId}/messages`);
                const messages = await response.json();
                
                // Clear loading
                const loadingEl = document.getElementById(loadingId);
                if (loadingEl) loadingEl.remove();
                
                if (messages.length === 0) {
                    appendMessage("assistant", "Hiyori", "当前对话还没有历史消息记录。你可以开始发送新消息哦 💬");
                } else {
                    messages.forEach(msg => {
                        if (msg.role === 'user') {
                            appendMessage('user', '您', msg.content);
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
                appendMessage("assistant", "系统错误", `加载历史消息失败: ${err.message}`);
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
            chatInput.placeholder = "输入一条控制指令 (例如: 列出当前文件)...";
            
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
                const response = await fetch(`/api/chats/${chatId}`, {
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
                refreshHardwareBattery();
                pullHardwareClipboard();
            }
        }

        function switchSettingsTab(idx) {
            const tabs = document.querySelectorAll('.settings-tab');
            const panes = document.querySelectorAll('.settings-pane');
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
        }

        function toggleWorkspaceConsole() {
            const overlay = document.getElementById('workspaceConsoleOverlay');
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (!overlay || !drawer) return;
            
            const isMoreMenuOpen = document.getElementById('more-menu-drawer').classList.contains('open');
            if (isMoreMenuOpen) closeMoreMenu();
            
            if (drawer.classList.contains('active')) {
                overlay.classList.remove('active');
                drawer.classList.remove('active');
            } else {
                overlay.classList.add('active');
                drawer.classList.add('active');
                
                // Auto load or select active tab
                const activeTab = document.querySelector('.console-tab.active');
                if (activeTab) {
                    const tabs = Array.from(document.querySelectorAll('.console-tab'));
                    const idx = tabs.indexOf(activeTab);
                    if (idx === 0) loadArtifacts();
                } else {
                    switchConsoleTab(0);
                }
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
            bgEl.style.backgroundImage = 'none';

            // Apply preset gradients to the container
            if (presetName === 'default') {
                container.style.background = 'radial-gradient(circle at center, rgba(6, 182, 212, 0.2) 0%, rgba(139, 92, 246, 0.05) 60%, rgba(11, 15, 25, 0.95) 100%)';
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
            const menuEl = document.getElementById("more-menu-drawer");
            if (menuEl.classList.contains("open")) {
                const activeTab = document.querySelector('.settings-tab.active');
                const tabs = document.querySelectorAll('.settings-tab');
                if (activeTab === tabs[0]) {
                    closeMoreMenu();
                } else {
                    switchSettingsTab(0);
                }
            } else {
                openMoreMenu();
                switchSettingsTab(0);
            }
        }

        function toggleStore() {
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (drawer.classList.contains('active')) {
                const activeTab = document.querySelector('.console-tab.active');
                const tabs = document.querySelectorAll('.console-tab');
                if (activeTab === tabs[1]) {
                    toggleWorkspaceConsole();
                } else {
                    switchConsoleTab(1);
                    setTimeout(() => {
                        const sec = document.getElementById('section-skills');
                        if (sec) sec.scrollIntoView({ behavior: 'smooth' });
                    }, 100);
                }
            } else {
                toggleWorkspaceConsole();
                switchConsoleTab(1);
                setTimeout(() => {
                    const sec = document.getElementById('section-skills');
                    if (sec) sec.scrollIntoView({ behavior: 'smooth' });
                }, 100);
            }
        }

        function toggleMCP() {
            const drawer = document.getElementById('workspaceConsoleDrawer');
            if (drawer.classList.contains('active')) {
                const activeTab = document.querySelector('.console-tab.active');
                const tabs = document.querySelectorAll('.console-tab');
                if (activeTab === tabs[1]) {
                    toggleWorkspaceConsole();
                } else {
                    switchConsoleTab(1);
                    setTimeout(() => {
                        const sec = document.getElementById('section-mcp');
                        if (sec) sec.scrollIntoView({ behavior: 'smooth' });
                    }, 100);
                }
            } else {
                toggleWorkspaceConsole();
                switchConsoleTab(1);
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
        let activeArtifact = null;

        async function loadArtifacts(typeFilter = 'all') {
            try {
                // For MVP, we query without strict project_id, let backend fallback to default if needed.
                // In future: `?project_id=${currentProjectId}&type_filter=${typeFilter}`
                const response = await fetch(`/api/artifacts?type_filter=${typeFilter}`);
                const artifacts = await response.json();
                currentArtifactsData = artifacts || [];
                renderArtifacts(currentArtifactsData);
                
                // Update active tab UI
                document.querySelectorAll('.artifacts-tab').forEach(tab => tab.classList.remove('active'));
                const targetTab = document.querySelector(`.artifacts-tab[data-type="${typeFilter}"]`);
                if(targetTab) targetTab.classList.add('active');
                
            } catch (err) {
                console.error("Failed to load artifacts:", err);
            }
        }

        function renderArtifacts(artifacts) {
            const grid = document.getElementById('artifactsGrid');
            grid.innerHTML = '';
            
            if (!artifacts || artifacts.length === 0) {
                grid.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem; grid-column: 1/-1; text-align: center; padding: 40px;">暂无成果。与 AI 对话让它生成 code 或图片吧！</div>`;
                return;
            }

            artifacts.forEach(art => {
                const card = document.createElement('div');
                card.className = `artifact-card ${art.type}`;
                card.setAttribute('onclick', `openArtifactModal('${art.artifact_id}')`);
                
                let iconHtml = `&lt;/&gt;`;
                if (art.type === 'image') {
                    iconHtml = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`;
                }
                
                card.innerHTML = `
                    <div style="display: flex; gap: 12px; align-items: center;">
                        <div class="artifact-icon">${iconHtml}</div>
                        <div class="artifact-title" title="${art.title}">${art.title}</div>
                    </div>
                    <div class="artifact-preview">${escapeHtml(art.preview_text)}</div>
                    <div class="artifact-action" style="display: flex; gap: 8px;">
                        <button class="icon-btn" onclick="deleteArtifact(event, '${art.artifact_id}')" style="background: rgba(239, 68, 68, 0.15); color: #fca5a5; border-radius: 6px; padding: 4px; width: 26px; height: 26px; border: 1px solid rgba(239, 68, 68, 0.3); display: flex; align-items: center; justify-content: center; transition: all 0.2s;" title="删除资产">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                        </button>
                        <button class="btn-time-machine" onclick="timeMachineTo(event, '${art.node_id}')">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                            时光机
                        </button>
                    </div>
                `;
                grid.appendChild(card);
            });
        }

        async function deleteArtifact(e, artifactId) {
            e.stopPropagation();
            if (!confirm("确定要永久删除这个资产吗？此操作不可恢复。")) return;
            
            try {
                const res = await fetch(`/api/artifacts/${artifactId}`, { method: 'DELETE' });
                if (res.ok) {
                    const activeTab = document.querySelector('.artifacts-tab.active');
                    loadArtifacts(activeTab ? activeTab.dataset.type : 'all');
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
            toggleArtifacts(); // Close drawer
            
            // Wait for drawer to close before scrolling
            setTimeout(() => {
                const targetMsg = document.getElementById(`msg-${nodeId}`);
                if (targetMsg) {
                    // Smooth scroll
                    targetMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // Highlight animation
                    targetMsg.classList.add('highlight-msg');
                    setTimeout(() => targetMsg.classList.remove('highlight-msg'), 3000);
                } else {
                    alert("该消息已在当前历史流中被清除或折叠。");
                }
            }, 300);
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
                bodyEl.innerHTML = `
                    <img class="artifact-image-preview" src="${activeArtifact.content_url}" alt="${activeArtifact.title || 'Preview'}" onerror="this.src='wechat_qr.png'; this.title='无法加载图片';">
                    <div style="font-size: 0.75rem; color: var(--text-muted); text-align: center; margin-top: 8px; word-break: break-all;">
                        图片链接: ${activeArtifact.content_url}
                    </div>
                `;
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
            tmBtn.onclick = (e) => {
                closeArtifactModal();
                timeMachineTo(e, activeArtifact.node_id);
            };

            const copyBtn = document.getElementById('artifactModalCopy');
            copyBtn.onclick = () => {
                if (activeArtifact.type === 'image') {
                    copyTextToClipboard(activeArtifact.content_url, "图片链接已复制！");
                } else {
                    copyTextToClipboard(activeArtifact.content_url, "代码内容已复制！");
                }
            };

            const downloadBtn = document.getElementById('artifactModalDownload');
            downloadBtn.onclick = () => {
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
            const verText = document.getElementById('system-update-ver');
            const updateBtn = document.getElementById('system-update-btn');
            if (!verText) return;
            
            try {
                const res = await fetch('/api/system/update');
                if (!res.ok) throw new Error("HTTP error " + res.status);
                const data = await res.json();
                if (data.update_available) {
                    verText.innerHTML = `有新版本可用: ${data.local_commit} &rarr; <span style="color: var(--primary); font-weight: bold;">${data.remote_commit}</span>`;
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
            try {
                const response = await fetch("/api/system/tunnel");
                const data = await response.json();
                
                const checkbox = document.getElementById("settings-tunnel-checkbox");
                const statusText = document.getElementById("settings-tunnel-status");
                
                if (!checkbox || !statusText) return;
                
                if (data.status === "active") {
                    checkbox.checked = true;
                    statusText.innerHTML = `✅ 已开启: <a href="${data.url}" target="_blank" style="color: var(--primary); font-weight: bold; text-decoration: underline;">${data.url}</a>`;
                    
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
                skillsContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--error); font-size: 0.75rem;">加载失败: ${err.message}</div>`;
                mcpContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--error); font-size: 0.75rem;">加载失败: ${err.message}</div>`;
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
                mcpContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.75rem;">无符合条件的 MCP 端点</div>`;
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
            
            const isChecked = ext.enabled ? 'checked' : '';
            const statusText = (ext.type === 'mcp') 
                ? (ext.enabled ? '● 在线' : '○ 已停用')
                : (ext.enabled ? '● 已激活' : '○ 已停用');
            const statusClass = ext.enabled ? (ext.type === 'mcp' ? 'online' : 'active') : 'disabled';
            
            card.innerHTML = `
                <div class="extension-header">
                    <div class="extension-title-block">
                        <span class="extension-icon">${ext.icon || '🧩'}</span>
                        <div class="extension-details">
                            <div class="extension-name">${ext.name}</div>
                            <div class="extension-type-badge ${ext.type}">${ext.type === 'skill' ? '技能库' : ext.type === 'mcp' ? 'MCP 端点' : '内置插件'}</div>
                        </div>
                    </div>
                    <div class="extension-status-block">
                        <span class="status-indicator ${statusClass}">${statusText}</span>
                        <label class="switch-container">
                            <input type="checkbox" ${isChecked} onchange="toggleExtensionState('${ext.id}', this.checked)">
                            <span class="switch-slider"></span>
                        </label>
                    </div>
                </div>
                <div class="extension-desc">${ext.description}</div>
            `;
            return card;
        }

        async function toggleExtensionState(id, enabled) {
            try {
                const response = await fetch('/api/system/extensions/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id, enabled })
                });
                const res = await response.json();
                if (res.status === 'success') {
                    showToast(`${enabled ? '开启' : '停用'} 成功 ⚙️`);
                    
                    // Update UI status indicator
                    const card = document.querySelector(`.extension-card[data-id="${id}"]`);
                    if (card) {
                        const indicator = card.querySelector('.status-indicator');
                        const extType = card.getAttribute('data-type');
                        if (indicator) {
                            indicator.className = `status-indicator ${enabled ? (extType === 'mcp' ? 'online' : 'active') : 'disabled'}`;
                            indicator.textContent = extType === 'mcp' 
                                ? (enabled ? '● 在线' : '○ 已停用')
                                : (enabled ? '● 已激活' : '○ 已停用');
                        }
                    }
                    
                    // Update local list
                    const index = allExtensionsData.findIndex(e => e.id === id);
                    if (index !== -1) {
                        allExtensionsData[index].enabled = enabled;
                        allExtensionsData[index].status = enabled ? (allExtensionsData[index].type === 'mcp' ? 'online' : 'active') : 'disabled';
                    }
                    
                    if (showingSkillsChips) {
                        renderSkillsChips();
                    }
                } else {
                    showToast(`操作失败: ${res.error}`);
                    const checkbox = document.querySelector(`.extension-card[data-id="${id}"] input[type="checkbox"]`);
                    if (checkbox) checkbox.checked = !enabled;
                }
            } catch (err) {
                showToast(`请求错误: ${err.message}`);
                const checkbox = document.querySelector(`.extension-card[data-id="${id}"] input[type="checkbox"]`);
                if (checkbox) checkbox.checked = !enabled;
            }
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
                container.innerHTML = `<div style="font-size: 0.72rem; color: var(--text-muted); padding: 4px 8px; width: 100%; text-align: center;">没有已激活的扩展技能。请在控制台激活。</div>`;
                return;
            }
            
            container.innerHTML = '';
            activeExts.forEach(ext => {
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
                
                chip.innerHTML = `${ext.icon || '🧠'} ${ext.name}`;
                chip.onclick = () => {
                    const commandPrefix = `/${ext.id} `;
                    chatInput.value = commandPrefix;
                    chatInput.focus();
                };
                container.appendChild(chip);
            });
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
        window.toggleExtensionState = toggleExtensionState;
        window.filterConsoleExtensions = filterConsoleExtensions;
        window.toggleSkillsChips = toggleSkillsChips;
        window.renderSkillsChips = renderSkillsChips;
        window.restoreDefaultChips = restoreDefaultChips;

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
                        
                        item.innerHTML = `
                            <div style="display: flex; align-items: center; gap: 8px; color: var(--text-color);">
                                <span>${ext.icon || '🧩'}</span>
                                <span style="font-weight: 600;">/${ext.id}</span>
                                <span style="color: var(--text-muted); font-size: 0.72rem;">${ext.name}</span>
                            </div>
                            <div style="font-size: 0.65rem; color: var(--text-muted); max-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${ext.description}
                            </div>
                        `;
                        
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
