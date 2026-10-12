"""Read-only Solana Devnet account lookup. No key material or signing lives here."""

import json
import urllib.request


DEVNET_RPC = "https://api.devnet.solana.com"
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MAX_LAMPORTS = (1 << 64) - 1


def validate_public_key(address):
    if not isinstance(address, str) or not 32 <= len(address) <= 44:
        return False
    value = 0
    for char in address:
        digit = BASE58_ALPHABET.find(char)
        if digit < 0:
            return False
        value = value * 58 + digit
    leading_zeroes = len(address) - len(address.lstrip("1"))
    decoded_size = leading_zeroes + (value.bit_length() + 7) // 8
    return decoded_size == 32


def get_devnet_balance(address, opener=None):
    if not validate_public_key(address):
        raise ValueError("Invalid Solana public key")
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "getBalance",
        "params": [address, {"commitment": "confirmed"}],
    }).encode("utf-8")
    request = urllib.request.Request(
        DEVNET_RPC, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    transport = opener or urllib.request.urlopen
    with transport(request, timeout=5) as response:
        body = response.read(64 * 1024 + 1)
    if len(body) > 64 * 1024:
        raise ValueError("Solana RPC response is too large")
    data = json.loads(body)
    if not isinstance(data, dict) or "error" in data:
        raise ValueError("Solana RPC returned an error")
    if data.get("jsonrpc") != "2.0" or type(data.get("id")) is not int or data["id"] != 1:
        raise ValueError("Invalid Solana RPC response identity")
    result = data.get("result")
    if not isinstance(result, dict):
        raise ValueError("Invalid Solana RPC response")
    lamports = result.get("value")
    context = result.get("context")
    if (type(lamports) is not int or not 0 <= lamports <= MAX_LAMPORTS
            or not isinstance(context, dict)
            or type(context.get("slot")) is not int
            or context["slot"] < 0):
        raise ValueError("Invalid Solana RPC balance")
    return {"network": "devnet", "address": address,
            "lamports": str(lamports), "slot": context["slot"]}
