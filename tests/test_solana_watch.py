"""Devnet watch-only wallet tests; no network calls."""

import io
import json
import unittest

import solana_watch


ADDRESS = "11111111111111111111111111111111"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class SolanaWatchTests(unittest.TestCase):
    def test_public_key_must_decode_to_exactly_32_bytes(self):
        self.assertTrue(solana_watch.validate_public_key(ADDRESS))
        self.assertTrue(solana_watch.validate_public_key(
            "83astBRguLMdt2h5U1Tpdq5tjFoJ6noeGwaY3mDLVcri"))
        for invalid in ("", "1" * 31, "1" * 33, "0" * 32, "O" * 32,
                        "I" * 32, "l" * 32, " " + ADDRESS, "1" * 44, None):
            with self.subTest(invalid=invalid):
                self.assertFalse(solana_watch.validate_public_key(invalid))

    def test_rpc_query_is_fixed_to_devnet_and_preserves_u64(self):
        seen = []

        def fake_open(request, timeout):
            seen.append((request, timeout))
            return _Response(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
                "context": {"slot": 42}, "value": 18446744073709551615,
            }}).encode())

        result = solana_watch.get_devnet_balance(ADDRESS, opener=fake_open)
        self.assertEqual(result["lamports"], "18446744073709551615")
        self.assertEqual(result["network"], "devnet")
        request, timeout = seen[0]
        self.assertEqual(request.full_url, "https://api.devnet.solana.com")
        self.assertEqual(timeout, 5)
        self.assertEqual(json.loads(request.data)["method"], "getBalance")
        self.assertEqual(json.loads(request.data)["params"][0], ADDRESS)

    def test_invalid_address_never_calls_network(self):
        def unexpected_open(*args, **kwargs):
            self.fail("network called for invalid address")

        with self.assertRaises(ValueError):
            solana_watch.get_devnet_balance("not-a-public-key", unexpected_open)

    def test_malformed_rpc_results_are_rejected(self):
        for response in ({"error": {"code": -1}}, {"result": {"value": -1, "context": {"slot": 1}}},
                         {"result": {"value": True, "context": {"slot": 1}}},
                         {"result": {"value": 1, "context": {"slot": -1}}},
                         {"jsonrpc": "2.0", "id": 2, "result": {"value": 1, "context": {"slot": 1}}},
                         {"jsonrpc": "1.0", "id": 1, "result": {"value": 1, "context": {"slot": 1}}}):
            with self.subTest(response=response):
                def fake_open(*args, **kwargs):
                    return _Response(json.dumps({"jsonrpc": "2.0", "id": 1, **response}).encode())
                with self.assertRaises(ValueError):
                    solana_watch.get_devnet_balance(ADDRESS, fake_open)

    def test_oversized_rpc_response_is_rejected(self):
        def fake_open(*args, **kwargs):
            return _Response(json.dumps({"jsonrpc": "2.0", "id": 1,
                                         "result": {"value": 1, "context": {"slot": 1}},
                                         "padding": " " * 65536}).encode())
        with self.assertRaisesRegex(ValueError, "too large"):
            solana_watch.get_devnet_balance(ADDRESS, fake_open)


if __name__ == "__main__":
    unittest.main()
