"""
Discord OAuth2 client (authorization code grant) for the web app.

"Login with Discord" is used purely as the identity gate: it identifies who is
using the app and keeps the dashboard behind a login. The target channel is
fixed in configuration (DISCORD_CHANNEL_ID), so no guild/channel browsing is
needed.

Capabilities by scope:

  identify          -> /users/@me profile (username, avatar, id)
  webhook.incoming  -> during authorization Discord asks the user to pick a
                       channel and creates a webhook in it; the token response
                       carries the ready-to-use webhook (id + url). The app
                       saves it automatically — no URLs are ever pasted.

The user's own servers are never requested: the fixed target server's card
(name, icon, member counts, emojis) comes from GET /guilds/{id}/preview and
its channels from GET /guilds/{id}/channels, both readable with the stored
account token.

Important limitation (by design of Discord's API): OAuth2 USER tokens cannot
post messages. Posting is done with a stored account token the user pastes
once (see POST /api/auth/token); Discord OAuth never issues a token that can
send messages for a regular member account. OAuth tokens live in the Flask
session only — nothing OAuth-related is persisted to Firestore/app_data.
"""

import os
import urllib.parse

import requests

API_BASE = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"

DEFAULT_SCOPES = "identify webhook.incoming"


def _env(name, default=""):
    return os.getenv(name, default)


def is_configured():
    return bool(_env("DISCORD_CLIENT_ID") and _env("DISCORD_CLIENT_SECRET"))


def target_guild_id():
    return _env("DISCORD_GUILD_ID", "").strip()


def target_channel_id():
    return _env("DISCORD_CHANNEL_ID", "").strip()


def redirect_uri():
    return _env("DISCORD_REDIRECT_URI", "http://localhost:5000/api/auth/callback")


def frontend_url():
    return _env("FRONTEND_URL", "http://localhost:5173")


def login_url(state):
    """Build the Discord authorization URL for the given CSRF state value."""
    params = {
        "client_id": _env("DISCORD_CLIENT_ID"),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": _env("DISCORD_OAUTH_SCOPES", DEFAULT_SCOPES),
        "state": state,
        "prompt": "consent",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code, expected_state, actual_state):
    """Validate state (CSRF), exchange the code for tokens, return the payload.

    Raises ValueError on state mismatch and requests.HTTPError on API failure.
    """
    if expected_state is None or expected_state != actual_state:
        raise ValueError("OAuth state mismatch — possible CSRF. Please try again.")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(
        TOKEN_URL,
        data=data,
        headers=headers,
        auth=(_env("DISCORD_CLIENT_ID"), _env("DISCORD_CLIENT_SECRET")),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def refresh_token(refresh_token):
    """Exchange a refresh token for a fresh access token payload."""
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(
        TOKEN_URL,
        data=data,
        headers=headers,
        auth=(_env("DISCORD_CLIENT_ID"), _env("DISCORD_CLIENT_SECRET")),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _auth_get(url, token):
    """GET with Discord auth: OAuth bearer tokens require the 'Bearer '
    prefix, raw user tokens reject it — try both."""
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if r.status_code == 401:
        r = requests.get(url, headers={"Authorization": token}, timeout=10)
    return r


def fetch_user(access_token):
    """Fetch /users/@me with an OAuth bearer token (identify scope)."""
    r = _auth_get(f"{API_BASE}/users/@me", access_token)
    r.raise_for_status()
    return r.json()


def fetch_user_guilds(access_token, with_counts=True):
    """GET /users/@me/guilds — the user's servers (guilds scope)."""
    url = f"{API_BASE}/users/@me/guilds"
    if with_counts:
        url += "?with_counts=true"
    r = _auth_get(url, access_token)
    r.raise_for_status()
    return r.json()


def fetch_guild_preview(access_token, guild_id):
    """GET /guilds/{id}/preview — icon, description, emojis, member counts.

    Works when the user is a member of the guild (or the guild is discoverable).
    """
    r = _auth_get(f"{API_BASE}/guilds/{guild_id}/preview", access_token)
    r.raise_for_status()
    return r.json()


def fetch_channels(access_token, guild_id):
    """GET /guilds/{id}/channels — the channels the account can see.

    May return 403 for accounts without channel-listing permission on the
    guild; callers should treat that as a fallback signal.
    """
    r = _auth_get(f"{API_BASE}/guilds/{guild_id}/channels", access_token)
    r.raise_for_status()
    return r.json()


def fetch_channel(access_token, channel_id):
    """GET /channels/{id} — a single channel's details."""
    r = _auth_get(f"{API_BASE}/channels/{channel_id}", access_token)
    r.raise_for_status()
    return r.json()