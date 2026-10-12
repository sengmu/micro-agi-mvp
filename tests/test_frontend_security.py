"""Source guardrails for DOM rendering of data returned by the local API."""

from pathlib import Path
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "script.js").read_text(encoding="utf-8")


class FrontendSecurityTests(unittest.TestCase):
    def test_html_escaping_handles_optional_fields_consistently(self):
        self.assertEqual(SCRIPT.count("function escapeHtml("), 1)
        escape = SCRIPT.split("function escapeHtml(unsafe)", 1)[1].split(
            "function formatTerminalOutput", 1
        )[0]
        self.assertIn("unsafe === null || unsafe === undefined", escape)
        self.assertIn("String(unsafe)", escape)
        for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#039;"):
            self.assertIn(entity, escape)

    def test_chat_history_never_places_titles_in_html_or_inline_handlers(self):
        history = SCRIPT.split("async function loadChatSessions", 1)[1].split(
            "async function selectChatSession", 1)[0]
        self.assertIn("title.textContent = chat.title || '';", history)
        self.assertIn("renameChatSession(chat.chat_id, chat.title, event)", history)
        self.assertIn("deleteChatSession(chat.chat_id, event)", history)
        self.assertNotIn("${chat.title}", history)
        self.assertNotIn("onclick=", history)

    def test_image_artifact_modal_uses_dom_properties_for_untrusted_url(self):
        modal = SCRIPT.split("function openArtifactModal", 1)[1].split(
            "function closeArtifactModal", 1)[0]
        image_branch = modal.split("if (activeArtifact.type === 'image')", 1)[1].split(
            "} else {", 1)[0]
        self.assertIn("image.src = activeArtifact.content_url || '';", image_branch)
        self.assertIn("caption.textContent = '图片链接: '", image_branch)
        self.assertIn("image.referrerPolicy = 'no-referrer';", image_branch)
        self.assertNotIn("${activeArtifact.content_url}", image_branch)
        self.assertNotIn("onerror=", image_branch)

    def test_attachment_preview_treats_filename_as_text(self):
        preview = SCRIPT.split("function renderAttachmentsPreview", 1)[1].split(
            "// ===== Streaming helpers", 1
        )[0]
        self.assertIn("name.textContent = att.name;", preview)
        self.assertIn("name.title = att.name;", preview)
        self.assertIn("remove.addEventListener('click'", preview)
        self.assertNotIn("item.innerHTML", preview)
        self.assertNotIn("onclick=", preview)

    def test_aios_memories_use_text_nodes_and_bound_handlers(self):
        memory_list = SCRIPT.split("function aiosRenderMemories", 1)[1].split(
            "async function aiosRefreshEntry", 1
        )[0]
        self.assertIn("box.replaceChildren();", memory_list)
        self.assertIn("item.dataset.mid = id;", memory_list)
        self.assertIn("kind.textContent =", memory_list)
        self.assertIn("source.textContent = m.source;", memory_list)
        self.assertIn("content.textContent = m.content || '';", memory_list)
        self.assertIn("pin.addEventListener('click'", memory_list)
        self.assertIn("remove.addEventListener('click'", memory_list)
        self.assertNotIn("innerHTML", memory_list)
        self.assertNotIn("onclick=", memory_list)

    def test_stream_disconnect_never_auto_retries_nonstream_chat(self):
        send_flow = SCRIPT.split("async function sendMessage", 1)[1].split(
            "function handleAgentResponse", 1
        )[0]
        self.assertIn('fetch("/api/chat/stream"', send_flow)
        self.assertNotIn('fetch("/api/chat"', send_flow)
        self.assertIn("未自动重试", send_flow)
        self.assertIn("回答未完整结束", send_flow)
        self.assertIn("const partial = streamedText", send_flow)
        self.assertIn("partial + `⚠️ 回答未完整结束", send_flow)

    def test_embedded_ui_does_not_offer_unsupported_uploads(self):
        capabilities = SCRIPT.split("async function applyRuntimeCapabilities", 1)[1].split(
            "window.addEventListener('DOMContentLoaded'", 1
        )[0]
        self.assertIn("'attachBtn'", capabilities)
        self.assertIn("fileUpload.disabled = true", capabilities)
        self.assertIn("'toggle-terminal-btn'", capabilities)
        self.assertIn("document.documentElement.classList.add('embedded-host')", capabilities)

    def test_unknown_runtime_hides_desktop_only_controls(self):
        root = Path(__file__).resolve().parents[1]
        css = (root / "style.css").read_text(encoding="utf-8")
        capabilities = SCRIPT.split("async function applyRuntimeCapabilities", 1)[1].split(
            "window.addEventListener('DOMContentLoaded'", 1
        )[0]
        self.assertIn("classList.add('capabilities-pending')", SCRIPT)
        self.assertIn("if (typeof health.embedded !== 'boolean') return;", capabilities)
        self.assertIn("classList.remove('capabilities-pending')", capabilities)
        self.assertIn("window.microAgiEmbedded === false", SCRIPT.split(
            "function defaultChatPlaceholder()", 1
        )[1].split("function markEmbeddedGoogleAuth", 1)[0])
        for control in ("#toggle-terminal-btn", "#toggle-workspace-btn",
                        "#quickTerminal", "#attachBtn"):
            self.assertIn(f"html.capabilities-pending {control}", css)

    def test_embedded_code_blocks_do_not_offer_csp_blocked_html_preview(self):
        renderer = SCRIPT.split("function appendAssistantMessage(", 1)[1].split(
            "function toggleWeChatAccordion", 1
        )[0]
        self.assertIn("window.microAgiEmbedded === false &&", renderer)
        self.assertIn("onclick=\"openLivePreview(", renderer)
        preview = SCRIPT.split("window.openLivePreview = function(htmlContent)", 1)[1].split(
            "window.closePreviewPanel", 1
        )[0]
        self.assertIn("if (window.microAgiEmbedded !== false) return;", preview)
        backend = (Path(__file__).resolve().parents[1] / "app.py").read_text(
            encoding="utf-8")
        self.assertIn("frame-src 'none'", backend)

    def test_embedded_chat_placeholder_does_not_promise_uploads_or_shell(self):
        html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="chatInput" placeholder="输入消息，和日和聊天…"', html)
        capabilities = SCRIPT.split("async function applyRuntimeCapabilities", 1)[1].split(
            "window.addEventListener('DOMContentLoaded'", 1
        )[0]
        self.assertIn("chatInput.placeholder = defaultChatPlaceholder();", capabilities)
        self.assertIn(": '输入消息，和日和聊天…'", SCRIPT)
        self.assertNotIn('placeholder="输入一条控制指令或发张图', html)

    def test_embedded_stream_does_not_promise_command_approval(self):
        preview = SCRIPT.split("function updateStreamBubble(fullText)", 1)[1].split(
            "function clearStreamBubble", 1
        )[0]
        self.assertIn('const execIdx = display.indexOf("<execute>");', preview)
        self.assertIn('window.microAgiEmbedded === false', preview)
        self.assertIn('独立版不支持命令执行；本次不会执行任何命令。', preview)
        self.assertIn('准备申请执行命令', preview)

    def test_embedded_updater_waits_for_capabilities_before_probing(self):
        updater = SCRIPT.split("async function checkSystemUpdate()", 1)[1].split(
            "async function triggerSystemUpdate()", 1
        )[0]
        self.assertIn("await window.microAgiCapabilitiesReady;", updater)
        self.assertIn("window.microAgiEmbedded !== false", updater)
        self.assertLess(updater.index("window.microAgiEmbedded !== false"),
                        updater.index("fetch('/api/system/update')"))
        self.assertIn("verText.textContent = `有新版本可用:", updater)
        self.assertNotIn("verText.innerHTML", updater)

    def test_tunnel_status_does_not_interpolate_url_into_html(self):
        tunnel = SCRIPT.split("async function checkTunnelStatus()", 1)[1].split(
            "async function toggleTunnel", 1
        )[0]
        self.assertIn("await window.microAgiCapabilitiesReady;", tunnel)
        self.assertIn("if (window.microAgiEmbedded !== false) return;", tunnel)
        self.assertLess(tunnel.index("window.microAgiEmbedded !== false"),
                        tunnel.index('fetch("/api/system/tunnel")'))
        self.assertIn("parsed.protocol === 'https:'", tunnel)
        self.assertIn("parsed.hostname.endsWith('.lhr.life')", tunnel)
        self.assertIn("link.textContent = tunnelUrl.href;", tunnel)
        self.assertIn("link.rel = 'noopener noreferrer';", tunnel)
        self.assertNotIn("statusText.innerHTML", tunnel)
        self.assertNotIn("${data.url}", tunnel)

    def test_terminal_command_echo_is_plain_text(self):
        for function_name, next_marker in (
            ("window.executeQuickTerminalCommand = async function()", "async function executeTerminalCommand()"),
            ("async function executeTerminalCommand()", "window.addEventListener('DOMContentLoaded'"),
        ):
            section = SCRIPT.split(function_name, 1)[1].split(next_marker, 1)[0]
            echo = section.split("// Append command line with styled prompt", 1)[1].split(
                "outputEl.appendChild(cmdLine);", 1
            )[0]
            self.assertIn("commandText.textContent = ` ${cmd}`;", echo)
            self.assertNotIn("innerHTML", echo)

    def test_slash_command_dropdown_treats_extension_metadata_as_text(self):
        dropdown = SCRIPT.split("// Slash command dropdown listener on input", 1)[1].split(
            "item.onclick = () =>", 1
        )[0]
        self.assertIn("icon.textContent = ext.icon || '🧩';", dropdown)
        self.assertIn("command.textContent = `/${ext.id}`;", dropdown)
        self.assertIn("name.textContent = ext.name;", dropdown)
        self.assertIn("description.textContent = ext.description || '';", dropdown)
        self.assertNotIn("item.innerHTML", dropdown)


if __name__ == "__main__":
    unittest.main()
