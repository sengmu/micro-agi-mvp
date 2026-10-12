(function () {
    'use strict';
    const BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
    const addressInput = document.getElementById('solana-address');
    const status = document.getElementById('solana-wallet-status');
    const button = document.getElementById('solana-balance-btn');
    if (!addressInput || !status || !button) return;

    function validPublicKey(address) {
        if (address.length < 32 || address.length > 44) return false;
        let value = 0n;
        for (const char of address) {
            const digit = BASE58.indexOf(char);
            if (digit < 0) return false;
            value = value * 58n + BigInt(digit);
        }
        const zeros = (address.match(/^1*/) || [''])[0].length;
        const bytes = value === 0n ? 0 : Math.ceil(value.toString(16).length / 2);
        return zeros + bytes === 32;
    }

    function formatSol(lamports) {
        const value = BigInt(lamports);
        const fractional = (value % 1000000000n).toString().padStart(9, '0').replace(/0+$/, '');
        return (value / 1000000000n).toString() + (fractional ? '.' + fractional : '');
    }

    addressInput.addEventListener('input', function () {
        status.textContent = '未查询 · 不连接钱包、不签名、不转账';
    });

    window.lookupSolanaBalance = async function () {
        const address = addressInput.value.trim();
        if (!validPublicKey(address)) {
            status.textContent = '地址无效：请输入 32 字节的 Solana 公钥，不要输入私钥或助记词。';
            return;
        }
        button.disabled = true;
        status.textContent = '正在查询 Devnet…';
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
            const response = await fetch('/api/solana/devnet/balance?address=' + encodeURIComponent(address), {
                signal: controller.signal,
                cache: 'no-store',
            });
            if (!response.ok) throw new Error('RPC unavailable');
            const data = await response.json();
            if (data.network !== 'devnet' || data.address !== address || !/^\d+$/.test(data.lamports)) {
                throw new Error('Invalid response');
            }
            if (addressInput.value.trim() === address) {
                status.textContent = 'Devnet 余额：' + formatSol(data.lamports) + ' SOL · 区块 slot ' + data.slot;
            }
        } catch (error) {
            if (addressInput.value.trim() === address) {
                status.textContent = error.name === 'AbortError'
                    ? '查询超时，请稍后重试。'
                    : 'Devnet 查询失败，请检查网络并稍后重试。';
            }
        } finally {
            clearTimeout(timeout);
            button.disabled = false;
        }
    };
})();
