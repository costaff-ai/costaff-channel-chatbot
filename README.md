# costaff-channel-chatbot

Shared runtime for CoStaff chatbot-style channels (Telegram / Discord / Slack /
LINE). Each platform repo only ships a thin `ChannelAdapter` implementation;
this package provides everything else: ADK connection, identity sync, approval
gating, rate limiting, message dedup, file delivery.

> Webchat is **not** a chatbot channel — it has its own backend/frontend
> architecture and does not consume this package.

## Install

```bash
pip install costaff-channel-chatbot
```

## Usage — minimal example

```python
from costaff_channel_chatbot import (
    ChannelAdapter, ChannelRuntime, IncomingMessage, setup_logging,
)

class MyAdapter(ChannelAdapter):
    platform_prefix = "my"        # session_id will be f"my_{uid}"
    max_message_length = 2000     # truncate longer replies

    async def reply(self, msg: IncomingMessage, text: str) -> None:
        # send `text` back via your platform SDK
        ...

    async def send_file(self, msg: IncomingMessage, path: str) -> None:
        # upload `path` and send it to msg.real_id
        ...

    async def download_attachment(self, attachment) -> tuple[bytes, str]:
        # return (file_bytes, suggested_filename)
        ...

setup_logging("INFO")
runtime = ChannelRuntime(MyAdapter())

# In your platform's event handler:
await runtime.handle_message(IncomingMessage(
    real_id=str(platform_user_id),
    text=text,
    attachments=[...],     # opaque platform-specific objects
    raw=platform_message,  # opaque, passed back to adapter methods
    message_id=str(platform_message_id),  # for dedup
))
```

## What the runtime does (in order)

1. **Dedup** — drops duplicate `message_id`s.
2. **Identity sync** — derives `uid = sha256(real_id + ID_SALT)[:16]`,
   persists the (`uid`, `real_id`) mapping in the identity table.
3. **Approval check** — replies with the pending message if the user is not
   approved; otherwise continues.
4. **Rate limit** — replies with the rate-limit message if the user has sent
   more than `RATE_LIMIT_MAX` messages in `RATE_LIMIT_WINDOW` seconds.
5. **ADK call** — sends text + inline attachments to the agent.
6. **Response delivery** — detects file path references in the agent reply,
   resolves them under `SHARED_DIR`, sends the files via the adapter, and
   then sends the cleaned text reply.

## Environment variables

| Var | Default | Used by |
|---|---|---|
| `ADK_API_BASE_URL` | `http://localhost:8000` | ADK client |
| `ADK_APP_NAME` | `costaff_agent` | ADK client |
| `ADK_SESSION_SERVICE_URI` | `sqlite:///./costaff_agent.db` | identity table |
| `ID_SALT` | `costaff_default_salt` | `get_user_id` |
| `RATE_LIMIT_MAX` | `10` | rate limiter |
| `RATE_LIMIT_WINDOW` | `60` | rate limiter |
| `SHARED_DIR` | `/app/data/shared` | response file resolver |
| `COSTAFF_PREFERRED_LANGUAGE` | `Traditional Chinese (繁體中文)` | ADK retry prompt |
| `LOG_LEVEL` | `INFO` | logging |

## License

Apache 2.0 — see `LICENSE`.
