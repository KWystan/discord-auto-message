"""
Tests for server/auth.py (Discord OAuth2 client) — all network calls mocked.

Run:  server/venv/Scripts/python.exe server/test_auth.py
"""

import os
import sys
import unittest
from unittest.mock import patch

import auth

REAL_REQUESTS = __import__("requests")


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise REAL_REQUESTS.HTTPError(response=self)


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "DISCORD_CLIENT_ID": "test-client-id",
                "DISCORD_CLIENT_SECRET": "test-client-secret",
                "DISCORD_REDIRECT_URI": "http://localhost:5000/api/auth/callback",
                "DISCORD_OAUTH_SCOPES": "identify webhook.incoming",
                "DISCORD_GUILD_ID": "571992648190263317",
                "DISCORD_CHANNEL_ID": "997645910769160202",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_is_configured(self):
        self.assertTrue(auth.is_configured())

    def test_is_configured_false_without_secret(self):
        with patch.dict(os.environ, {"DISCORD_CLIENT_SECRET": ""}):
            self.assertFalse(auth.is_configured())

    def test_target_ids(self):
        self.assertEqual(auth.target_guild_id(), "571992648190263317")
        self.assertEqual(auth.target_channel_id(), "997645910769160202")

    def test_login_url_contains_state_and_identify_scope(self):
        url = auth.login_url("abc123state")
        self.assertIn("https://discord.com/oauth2/authorize", url)
        self.assertIn("client_id=test-client-id", url)
        self.assertIn("state=abc123state", url)
        self.assertIn("scope=identify+webhook.incoming", url)
        self.assertNotIn("guilds", url)
        self.assertNotIn("bot", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fapi%2Fauth%2Fcallback", url)

    def test_exchange_code_state_mismatch_raises(self):
        with self.assertRaises(ValueError):
            auth.exchange_code("code123", "expected", "different")

    def test_exchange_code_posts_form_and_basic_auth(self):
        payload = {"access_token": "tok", "refresh_token": "ref", "expires_in": 604800}
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(200, payload)) as post:
            result = auth.exchange_code("code123", "st8", "st8")
            self.assertEqual(result["access_token"], "tok")
            post.assert_called_once()
            args, kwargs = post.call_args
            self.assertEqual(kwargs["auth"], ("test-client-id", "test-client-secret"))
            self.assertEqual(kwargs["headers"]["Content-Type"], "application/x-www-form-urlencoded")
            self.assertEqual(kwargs["data"]["grant_type"], "authorization_code")
            self.assertEqual(kwargs["data"]["code"], "code123")

    def test_exchange_code_raises_http_error(self):
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(400)):
            with self.assertRaises(REAL_REQUESTS.HTTPError):
                auth.exchange_code("code123", "st8", "st8")

    def test_refresh_token(self):
        payload = {"access_token": "fresh", "expires_in": 604800}
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(200, payload)) as post:
            result = auth.refresh_token("old-refresh")
            self.assertEqual(result["access_token"], "fresh")
            self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "refresh_token")
            self.assertEqual(post.call_args.kwargs["data"]["refresh_token"], "old-refresh")

    def test_fetch_user_sends_bearer(self):
        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, {"id": "42", "username": "x"})) as get:
            user = auth.fetch_user("the-token")
            self.assertEqual(user["id"], "42")
            self.assertEqual(
                get.call_args.kwargs["headers"]["Authorization"],
                "Bearer the-token",
            )

    # ── server scan fetches ────────────────────────────────────────────
    def test_fetch_user_guilds_uses_with_counts(self):
        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, [{"id": "g", "name": "x"}])) as get:
            guilds = auth.fetch_user_guilds("tok")
            self.assertEqual(guilds[0]["name"], "x")
            self.assertIn("/users/@me/guilds", get.call_args.args[0])
            self.assertIn("with_counts=true", get.call_args.args[0])
            self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_fetch_user_guilds_without_counts(self):
        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, [])) as get:
            auth.fetch_user_guilds("tok", with_counts=False)
            self.assertNotIn("with_counts", get.call_args.args[0])

    def test_fetch_guild_preview(self):
        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, {"id": "g", "emojis": []})) as get:
            preview = auth.fetch_guild_preview("tok", "123")
            self.assertIn("/guilds/123/preview", get.call_args.args[0])

    def test_fetch_channels(self):
        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, [{"id": "c", "type": 0}])) as get:
            channels = auth.fetch_channels("tok", "123")
            self.assertIn("/guilds/123/channels", get.call_args.args[0])
            self.assertEqual(channels[0]["type"], 0)

    def test_fetch_channel(self):
        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, {"id": "c", "name": "general"})) as get:
            ch = auth.fetch_channel("tok", "c")
            self.assertIn("/channels/c", get.call_args.args[0])
            self.assertEqual(ch["name"], "general")


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))