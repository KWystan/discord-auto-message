# Discord OAuth2 — Reference

Source: <https://docs.discord.com/developers/topics/oauth2>

OAuth2 lets applications authenticate with the Discord API on a user's behalf. Discord supports the **authorization code grant**, **implicit grant**, **client credentials**, plus special flows for **bots** and **webhooks**.

## Shared Resources

Register a developer application at <https://discord.com/developers/applications> and grab your `client_id` / `client_secret`. RFC 6749 applies for from-scratch implementations.

| URL | Description |
| --- | --- |
| `https://discord.com/oauth2/authorize` | Base authorization URL |
| `https://discord.com/api/oauth2/token` | Token URL |
| `https://discord.com/api/oauth2/token/revoke` | Token revocation URL (RFC 7009) |

> The token and token revocation URLs **only** accept `application/x-www-form-urlencoded`. JSON is rejected.

## OAuth2 Scopes

| Scope | Description |
| ----- | ----------- |
| `activities.read` / `activities.write` | Now Playing / activity data — not currently available |
| `applications.builds.read` | Read build data for a user's applications |
| `applications.builds.upload` | Upload/update builds — approved partners only |
| `applications.commands` | Add commands to a guild (included with `bot` scope) |
| `applications.commands.update` | Update commands via bearer token — client credentials grant only |
| `applications.commands.permissions.update` | Update command permissions in a guild |
| `applications.entitlements` | Read entitlements |
| `applications.store.update` | Read/update store data (SKUs, listings) |
| `bot` | Adds the bot to the user's selected guild |
| `connections` | `/users/@me/connections` returns linked third-party accounts |
| `dm_channels.read` | Read DM / group DM info — approved partners only |
| `email` | `/users/@me` returns `email` |
| `gdm.join` | Join users to a group DM |
| `guilds` | `/users/@me/guilds` returns basic guild info |
| `guilds.join` | Join users to a guild |
| `guilds.members.read` | Read a user's member info in a guild |
| `identify` | `/users/@me` without `email` |
| `identify.premium` | Read Nitro subscription type — approved partners only |
| `messages.read` | Read messages (local RPC server access) |
| `relationships.read` | Friends/pending/blocks lists — Social SDK |
| `role_connections.write` | Update a user's connection/metadata for the app |
| `rpc` | Control the local Discord client — approved partners only |
| `rpc.activities.write` / `rpc.notifications.read` / `rpc.voice.read` / `rpc.voice.write` | Local RPC extensions — approved partners only |
| `voice` | Connect to voice on the user's behalf — approved partners only |
| `webhook.incoming` | Creates a webhook returned in the token response |

Notes:
- Some scopes require Discord approval; requesting unapproved scopes may error or behave unexpectedly.
- To add a user to a guild, the bot must already be in that guild.
- `role_connections.write` cannot be used with the implicit grant.

## State and Security

Use the `state` parameter to defend against CSRF and clickjacking. Generate a value unique to the user's request (e.g. a hash of their session cookie), keep it where only client + user can access it (same-origin policy), and validate it matches on redirect. Discord supports but does not require `state`.

## Authorization Code Grant

The standard OAuth2 flow. The authorization server acts as an intermediary, so the resource owner's credentials are never shared directly with the client.

### Authorization URL

```
https://discord.com/oauth2/authorize?response_type=code&client_id=157730590492196864&scope=identify%20guilds.join&state=15773059ghq9183habn&redirect_uri=https%3A%2F%2Fnicememe.website&prompt=consent&integration_type=0
```

- `scope` — space-separated list, URL-encoded as `%20`
- `redirect_uri` — must match a registered URI, URL-encoded
- `state` — unique per request; validated on return
- `prompt` — `consent` forces re-approval; `none` skips the screen (passthrough scopes like `bot`/`webhook.incoming` always require authorization)
- `integration_type` — `0` = GUILD_INSTALL, `1` = USER_INSTALL (relevant when `applications.commands` is in scope)

### Redirect URL

```
https://nicememe.website/?code=NhhvTDYsFcdgNLnnLijcl7Ku7bEEeee&state=15773059ghq9183habn
```

### Exchange the code for a token

```python
import requests

API_ENDPOINT = 'https://discord.com/api/v10'
CLIENT_ID = '332269999912132097'
CLIENT_SECRET = '937it3ow87i4ery69876wqire'
REDIRECT_URI = 'https://nicememe.website'

def exchange_code(code):
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(f'{API_ENDPOINT}/oauth2/token', data=data, headers=headers,
                      auth=(CLIENT_ID, CLIENT_SECRET))
    r.raise_for_status()
    return r.json()
```

### Token response

```json
{
  "access_token": "6qrZcUqja7812RVdnEKjpzOL4CvHBFG",
  "token_type": "Bearer",
  "expires_in": 604800,
  "refresh_token": "D43f5y0ahjqew82jZ4NViEr2YafMKhue",
  "scope": "identify"
}
```

### Refresh a token

`grant_type=refresh_token` + `refresh_token` to the token URL.

```python
def refresh_token(refresh_token):
    data = {'grant_type': 'refresh_token', 'refresh_token': refresh_token}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(f'{API_ENDPOINT}/oauth2/token', data=data, headers=headers,
                      auth=(CLIENT_ID, CLIENT_SECRET))
    r.raise_for_status()
    return r.json()
```

### Revoke a token

`POST` to the revocation URL with `token` and optional `token_type_hint` (`access_token` | `refresh_token`).

> Revoking any token revokes **all** active access/refresh tokens for that authorization, regardless of the values passed.

```python
def revoke_access_token(access_token):
    data = {'token': access_token, 'token_type_hint': 'access_token'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    requests.post(f'{API_ENDPOINT}/oauth2/token/revoke', data=data, headers=headers,
                  auth=(CLIENT_ID, CLIENT_SECRET))
```

## Implicit Grant

Simplified flow for in-browser clients — the access token is returned directly, **no refresh token**.

### Authorization URL

```
https://discord.com/oauth2/authorize?response_type=token&client_id=290926444748734499&state=15773059ghq9183habn&scope=identify
```

### Redirect URL (token arrives in the URI fragment, not the querystring!)

```
https://findingfakeurlsisprettyhard.tv/#access_token=RTfP0OK99U3kbRtHOoKLmJbOn45PjL&token_type=Bearer&expires_in=604800&scope=identify&state=15773059ghq9183habn
```

Tradeoffs: quicker and easier to implement, but the token is exposed in the URI fragment, and the user must explicitly re-authorize when it expires.

## Client Credentials Grant

Quick way for bot developers to get their own bearer token for testing. Basic auth with `client_id` as username and `client_secret` as password.

```python
def get_token():
    data = {'grant_type': 'client_credentials', 'scope': 'identify connections'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(f'{API_ENDPOINT}/oauth2/token', data=data, headers=headers,
                      auth=(CLIENT_ID, CLIENT_SECRET))
    r.raise_for_status()
    return r.json()
```

Response has `access_token`, `token_type`, `expires_in`, `scope` — **no refresh token**.

> Team applications are limited to `identify` and `applications.commands.update`.

## Bot Users

Bots are a separate user type dedicated to automation, authenticated with a bot token. They have full access to most API routes without bearer tokens and can use the Gateway. Bots are added to guilds via OAuth2 (no normal invites), cannot have friends or join Group DMs, and have their own rate limits.

> Discord's Terms of Service prohibit automating standard user accounts ("self-bots").

### Bot Authorization Parameters

| Parameter | Description |
| --------- | ----------- |
| `client_id` | Your app's client id |
| `scope?` | Must include `bot` |
| `permissions?` | Permission integer being requested |
| `guild_id?` | Pre-fills the guild dropdown |
| `disable_guild_select?` | `true`/`false` — locks the guild dropdown |
| `integration_type?` | Installation context |

### URL Example

```
https://discord.com/oauth2/authorize?client_id=157730590492196864&scope=bot&permissions=1
```

No `response_type` or `redirect_uri` needed for the plain bot flow. Only `client_id` (with optional `permissions`/`guild_id`/`disable_guild_select`) uses the Developer Portal default install settings; specifying `scope`, `integration_type`, or `redirect_uri` overrides that.

### Advanced Bot Authorization

Requesting scopes beyond `bot` and `applications.commands` continues into a full authorization code grant and adds `guild_id` + `permissions` to the redirect querystring. Enabling "Require OAuth2 code grant" in the bot's settings forces every guild add through the full flow; the token response then includes the guild object the bot was added to.

### Two-Factor Authentication

Bots requesting elevated (asterisk) permissions require two-factor authentication on the owner's account when added to guilds with server-wide 2FA enabled.

## Webhooks

Webhook flow is a specialized authorization code grant with `scope=webhook.incoming`:

```
https://discord.com/oauth2/authorize?response_type=code&client_id=157730590492196864&scope=webhook.incoming&state=15773059ghq9183habn&redirect_uri=https%3A%2F%2Fnicememe.website
```

The user picks a channel; on acceptance you exchange the `code` for a token response that includes a `webhook` object:

```json
{
  "token_type": "Bearer",
  "access_token": "GNaVzEtATqdh173tNHEXY9ZYAuhiYxvy",
  "scope": "webhook.incoming",
  "expires_in": 604800,
  "refresh_token": "PvPL7ELyMDc1836457XCDh1Y8jPbRm",
  "webhook": {
    "application_id": "310954232226357250",
    "name": "testwebhook",
    "url": "https://discord.com/api/webhooks/347114750880120863/kKDdjXa1g9tKNs0-_yOwLyALC9gydEWP6gr9sHabuK1vuofjhQDDnlOclJeRIvYK-pj_",
    "channel_id": "345626669224982402",
    "token": "kKDdjXa1g9tKNs0-_yOwLyALC9gydEWP6gr9sHabuK1vuofjhQDDnlOclJeRIvYK-pj_",
    "type": 1,
    "guild_id": "290926792226357250",
    "id": "347114750880120863"
  }
}
```

Store `webhook.token` and `webhook.id` — a new webhook is created per authorization, so iterate over all stored id:token pairs to broadcast. Respect rate limits.

## Get Current Bot Application Information

`GET /oauth2/applications/@me` — returns the bot's application object.

## Get Current Authorization Information

`GET /oauth2/@me` — requires bearer token auth.

Response structure:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `application` | partial application object | The current application |
| `scopes` | array of strings | Scopes the user authorized |
| `expires` | ISO8601 timestamp | When the access token expires |
| `user?` | user object | The authorizing user (only with `identify` scope) |

Example:

```json
{
    "application": {
        "id": "159799960412356608",
        "name": "AIRHORN SOLUTIONS",
        "icon": "f03590d3eb764081d154a66340ea7d6d",
        "description": "",
        "hook": true,
        "bot_public": true,
        "bot_require_code_grant": false,
        "verify_key": "c8cde6a3c8c6e49d86af3191287b3ce255872be1fff6dc285bdb420c06a2c3c8"
    },
    "scopes": [
        "guilds.join",
        "identify"
    ],
    "expires": "2021-01-23T02:33:17.017000+00:00",
    "user": {
        "id": "268473310986240001",
        "username": "discord",
        "avatar": "f749bb0cbeeb26ef21eca719337d20f1",
        "discriminator": "0",
        "global_name": "Discord",
        "public_flags": 131072
    }
}
```