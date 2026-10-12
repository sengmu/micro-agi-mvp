package com.sg.magi

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.funkatronics.encoders.Base58
import com.solana.mobilewalletadapter.clientlib.ActivityResultSender
import com.solana.mobilewalletadapter.clientlib.ConnectionIdentity
import com.solana.mobilewalletadapter.clientlib.MobileWalletAdapter
import com.solana.mobilewalletadapter.clientlib.Solana
import com.solana.mobilewalletadapter.clientlib.TransactionResult
import kotlinx.coroutines.launch

/** Native, non-custodial MWA entrypoint. Never exposes signing or auth tokens to WebView. */
class WalletActivity : AppCompatActivity() {
    companion object {
        // The SDK owns the auth token. Keep it only for this app process, never on disk.
        private var sessionAdapter: MobileWalletAdapter? = null
        private var sessionIdentity: Pair<String, String>? = null
        private var sessionPublicKeys: List<String> = emptyList()
    }

    private lateinit var status: TextView
    private lateinit var stateTitle: TextView
    private lateinit var connectButton: Button
    private lateinit var disconnectButton: Button
    private lateinit var sender: ActivityResultSender
    private var adapter: MobileWalletAdapter? = null
    private var busy = false
    // A cached auth token/account is not proof that the wallet still grants access.
    // Only a successful connect in this Activity instance may show "已经连接".
    private var verifiedInThisOpening = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // registerForActivityResult must happen before the Activity reaches STARTED.
        sender = ActivityResultSender(this)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(14), dp(20), dp(18))
            background = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.rgb(25, 40, 60), Color.rgb(13, 21, 35))
            ).apply {
                cornerRadii = floatArrayOf(dp(30).toFloat(), dp(30).toFloat(),
                    dp(30).toFloat(), dp(30).toFloat(), 0f, 0f, 0f, 0f)
            }
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        header.addView(TextView(this).apply {
            text = "×"
            textSize = 30f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(241, 247, 250))
            contentDescription = "关闭钱包面板"
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(dp(44), dp(48)))
        header.addView(TextView(this).apply {
            text = "钱包"
            textSize = 20f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(248, 247, 246))
        }, LinearLayout.LayoutParams(0, dp(48), 1f))
        header.addView(TextView(this).apply {
            text = "●  DEVNET"
            textSize = 11f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(146, 228, 211))
            background = rounded(Color.rgb(36, 58, 79), 22, Color.rgb(119, 156, 176))
        }, LinearLayout.LayoutParams(dp(92), dp(36)))
        layout.addView(header)

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(22), dp(30), dp(22), dp(26))
            background = rounded(Color.rgb(37, 50, 75), 30, Color.rgb(105, 130, 156))
        }
        card.addView(TextView(this).apply {
            text = "✧"
            textSize = 42f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(173, 206, 226))
        }, LinearLayout.LayoutParams(dp(70), dp(64)))
        stateTitle = TextView(this).apply {
            textSize = 25f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            setPadding(0, dp(9), 0, dp(8))
        }
        card.addView(stateTitle)
        status = TextView(this).apply {
            textSize = 14f
            gravity = Gravity.CENTER
            setLineSpacing(dp(4).toFloat(), 1f)
            setTextColor(Color.rgb(204, 215, 229))
            setPadding(0, dp(6), 0, dp(22))
        }
        card.addView(status)
        connectButton = Button(this).apply {
            text = "连接手机钱包"
            textSize = 16f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                intArrayOf(Color.rgb(57, 97, 150), Color.rgb(63, 119, 161))
            ).apply { cornerRadius = dp(28).toFloat(); setStroke(dp(1), Color.rgb(121, 191, 215)) }
            setOnClickListener { connectWallet() }
        }
        card.addView(connectButton, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(56)))
        disconnectButton = Button(this).apply {
            text = "断开授权"
            textSize = 14f
            isAllCaps = false
            setTextColor(Color.rgb(218, 228, 240))
            background = rounded(Color.rgb(38, 53, 75), 24, Color.rgb(109, 133, 155))
            setOnClickListener { disconnectWallet() }
        }
        card.addView(disconnectButton, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(48)).apply { topMargin = dp(12) })
        card.addView(View(this).apply { setBackgroundColor(Color.rgb(104, 127, 151)) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply {
                topMargin = dp(28); bottomMargin = dp(20)
            })
        card.addView(TextView(this).apply {
            text = "由你在手机钱包中确认授权\n不读取私钥，不自动签名或转账\n如应用已被关闭，可在钱包内撤销旧授权"
            textSize = 13f
            setLineSpacing(dp(3).toFloat(), 1f)
            setTextColor(Color.rgb(198, 211, 227))
            gravity = Gravity.CENTER_HORIZONTAL
        })
        layout.addView(card, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        layout.addView(TextView(this).apply {
            text = "仅支持 Devnet 测试网络"
            textSize = 12f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(160, 178, 200))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(36)))
        setContentView(ScrollView(this).apply {
            isFillViewport = false
            addView(layout)
            setBackgroundColor(Color.TRANSPARENT)
        })

        val site = getString(R.string.solana_identity_uri).trim()
        val icon = getString(R.string.solana_icon_path).trim()
        val parsed = Uri.parse(site)
        val parsedIcon = Uri.parse(icon)
        val iconHasTraversal = !parsedIcon.isHierarchical || parsedIcon.pathSegments.any { segment ->
            segment == "." || segment == ".." || segment.contains('/') || segment.contains('\\')
        }
        if (site.isBlank() || icon.isBlank()) {
            status.text = "钱包连接尚未启用：应用的 HTTPS 身份网址和图标仍待配置。当前只可使用网页中的 Devnet 公钥余额查询。"
        } else if (parsed.scheme != "https" || !parsed.isHierarchical
            || parsed.host.isNullOrBlank() || parsed.userInfo != null || parsed.port != -1
            || parsed.query != null || parsed.fragment != null
            || parsedIcon.scheme != null || parsedIcon.authority != null
            || parsedIcon.path.isNullOrBlank() || parsedIcon.query != null
            || parsedIcon.fragment != null || iconHasTraversal) {
            status.text = "应用身份或图标地址格式不安全；钱包连接已禁用。"
        } else {
            val identity = site to icon
            if (sessionAdapter == null || sessionIdentity != identity) {
                sessionAdapter = MobileWalletAdapter(
                    connectionIdentity = ConnectionIdentity(
                        identityUri = parsed,
                        iconUri = parsedIcon,
                        identityName = "Micro-AGI"
                    )
                )
                sessionIdentity = identity
                sessionPublicKeys = emptyList()
            }
            adapter = sessionAdapter
            adapter?.blockchain = Solana.Devnet
            status.text = when {
                adapter?.authToken == null -> "连接后可查看授权账户。钱包将显示 Micro-AGI 与 ${parsed.host}；应用身份尚未完成正式验证，请核对后再决定是否授权。"
                sessionPublicKeys.isNotEmpty() -> "本次会话授权的 Devnet 账户（如已在钱包撤销，请重新连接核验授权）：\n${sessionPublicKeys.joinToString("\n")}" 
                else -> "本次运行可能已有授权；请重新连接核验账户，或断开授权。"
            }
        }
        refreshButtons()
    }

    private fun refreshButtons() {
        connectButton.isEnabled = adapter != null && !busy
        disconnectButton.isEnabled = adapter?.authToken != null && !busy
        disconnectButton.visibility = if (adapter?.authToken != null) View.VISIBLE else View.GONE
        connectButton.text = if (adapter?.authToken != null) "重新连接核验" else "连接手机钱包"
        connectButton.alpha = if (connectButton.isEnabled) 1f else .45f
        disconnectButton.alpha = if (disconnectButton.isEnabled) 1f else .4f
        stateTitle.text = when {
            adapter == null -> "暂不可用"
            busy -> "正在等待钱包"
            verifiedInThisOpening && sessionPublicKeys.isNotEmpty() -> "已经连接"
            sessionPublicKeys.isNotEmpty() -> "授权待核验"
            else -> "尚未连接"
        }
    }

    override fun onStart() {
        super.onStart()
        window.setBackgroundDrawableResource(android.R.color.transparent)
        window.setGravity(Gravity.BOTTOM)
        window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
        window.attributes = window.attributes.apply { dimAmount = .45f }
        window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density + .5f).toInt()

    private fun rounded(fill: Int, radius: Int, stroke: Int): GradientDrawable =
        GradientDrawable().apply {
            setColor(fill)
            cornerRadius = dp(radius).toFloat()
            setStroke(dp(1), stroke)
        }

    private fun connectWallet() {
        val client = adapter ?: return
        if (busy) return
        busy = true
        verifiedInThisOpening = false
        refreshButtons()
        sessionPublicKeys = emptyList()
        status.text = "等待手机钱包授权…"
        lifecycleScope.launch {
            try {
                when (val result = client.connect(sender)) {
                    is TransactionResult.Success -> {
                        val accounts = result.authResult.accounts
                        if (accounts.isEmpty()) {
                            // Keep disconnect available for a token with no displayable account.
                            status.text = "钱包没有返回账户，请断开授权并重试。"
                        } else if (accounts.any { it.publicKey.size != 32 }) {
                            // Solana addresses are exactly 32 bytes; do not label malformed
                            // wallet data as a verified account. The token may still exist.
                            status.text = "钱包返回的 Solana 公钥无效，请断开授权并重试。"
                        } else {
                            sessionPublicKeys = accounts.map { Base58.encodeToString(it.publicKey) }.distinct()
                            verifiedInThisOpening = true
                            status.text = "已连接 Devnet 钱包；钱包本次授权 ${sessionPublicKeys.size} 个账户：\n${sessionPublicKeys.joinToString("\n")}" 
                        }
                    }
                    is TransactionResult.NoWalletFound -> status.text = "未找到支持 Mobile Wallet Adapter 的手机钱包。请先确认兼容钱包已安装并启用。"
                    is TransactionResult.Failure -> status.text = "钱包拒绝、取消或连接失败。请查看钱包中的提示，并核对 Devnet 支持与应用域名验证状态。"
                    else -> status.text = "钱包连接未完成。"
                }
            } catch (_: Exception) {
                status.text = "钱包连接发生错误，请稍后重试。"
            } finally {
                busy = false
                refreshButtons()
            }
        }
    }

    private fun disconnectWallet() {
        val client = adapter ?: return
        if (busy || client.authToken == null) return
        busy = true
        refreshButtons()
        lifecycleScope.launch {
            try {
                when (client.disconnect(sender)) {
                    is TransactionResult.Success -> {
                        sessionPublicKeys = emptyList()
                        verifiedInThisOpening = false
                        status.text = "已断开钱包授权。"
                    }
                    else -> status.text = "断开失败，请重试。"
                }
            } catch (_: Exception) {
                status.text = "断开失败，请重试。"
            } finally {
                busy = false
                refreshButtons()
            }
        }
    }
}
