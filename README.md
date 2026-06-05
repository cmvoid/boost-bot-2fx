# Boost Bot

A simple Telegram bot that sends **boosting services** (Telegram channel members,
post views, reactions, shares, etc.) through an **SMM panel** API.

The bot is used in **private chats (DMs)**. Only a fixed list of **authorized
users** can use it: they send a command with the link of the channel/post to
boost, and the bot creates the order automatically on the panel. The bot also
**notifies each authorized user privately when the panel balance runs low**, so
you can top it up and keep services running.

---

## Features

- Place orders with a single command: `/members <link> <quantity>`
- Check the panel balance: `/balance`
- List available services: `/services`
- Find raw panel service IDs: `/panelservices <search>`
- Check order status: `/status <order_id>`
- Automatic **low-balance / out-of-balance notifications** sent privately to every
  authorized user
- **Authorized-users access control**: anyone not in the list is rejected on every
  command

---

## Requirements

- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An SMM panel with API access (API URL + API key)

---

## 1. Install

```bash
cd "Boost Bot 2FX"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Configure (`.env`)

The project already includes a `.env` file with your bot token, panel API key, and
the two authorized user ids. You only need to fill in **one** thing:

- **`SMM_API_URL`** — your panel's API endpoint. Almost every SMM panel uses the
  standard format ending with `/api/v2`, for example:

  ```
  SMM_API_URL=https://your-panel.com/api/v2
  ```

  You can find this in your panel under **Account → API** (it shows the API URL
  and example requests).

Full list of settings (see `.env.example` for descriptions):

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from BotFather |
| `SMM_API_URL` | yes | Panel API URL (usually ends with `/api/v2`) |
| `SMM_API_KEY` | yes | Panel API key |
| `AUTHORIZED_USER_IDS` | yes | Comma-separated Telegram user ids allowed to use the bot |
| `BALANCE_LOW_THRESHOLD` | optional | Low-balance alert threshold (default 5) |
| `BALANCE_CHECK_INTERVAL_MIN` | optional | Balance check interval in minutes (default 30) |

> If `AUTHORIZED_USER_IDS` is left empty, the bot falls back to the two default
> ids hardcoded in `config.py` (`8494222081`, `7639762965`).

---

## 3. Authorized users & how to find a user id

Only the user ids listed in `AUTHORIZED_USER_IDS` can use the bot. Every command
(including `/balance`, `/services`, `/status` and all order commands) rejects
anyone else with:

```
You are not authorized to use this bot.
```

To find a Telegram **user id**:

- Start a private chat with the bot and send `/id` (works only if you're already
  authorized), **or**
- Message [@userinfobot](https://t.me/userinfobot) — it replies with your numeric
  user id.

To add a new authorized user, append their id to `AUTHORIZED_USER_IDS` in `.env`
(comma-separated) and restart the bot.

> Important: Telegram only lets a bot send a private message to a user **after that
> user has started a chat with the bot** (e.g. by sending `/start`). Make sure each
> authorized user opens the bot once, otherwise balance notifications can't reach
> them.

---

## 4. Configure the services (`services.py`)

Each command maps to a **panel service ID**. Open `services.py` and set the real
`service_id` for each service you want to offer:

```python
SERVICES = [
    BoostService(command="members",   service_id=1234, label="Telegram Channel Members"),
    BoostService(command="views",     service_id=5678, label="Telegram Post Views"),
    BoostService(command="reactions", service_id=9012, label="Telegram Post Reactions"),
    BoostService(command="shares",    service_id=3456, label="Telegram Post Shares"),
]
```

To find the service IDs, either look in your panel's **Services** page, or run
`/panelservices members` (or any search term) in the bot once it's running — it
lists the matching services with their IDs, rate, min and max.

You can add or remove entries freely; the bot automatically creates one command
per service.

---

## 5. Run

```bash
source .venv/bin/activate
python bot.py
```

The bot starts polling. Open a private chat with the bot and send `/start` or
`/help` to see the commands.

To keep it running on a server, you can use `screen`, `tmux`, `systemd`, or a
process manager like `pm2`.

---

## Command list

| Command | Description |
|---|---|
| `/start`, `/help` | Welcome message and command guide |
| `/id` | Show your user id and the chat id |
| `/balance` | Show the current panel balance |
| `/services` | List the services configured in the bot |
| `/panelservices <search>` | Search raw services from the panel |
| `/status <order_id>` | Show the status of an order |
| `/members <link> <qty>` | Order Telegram channel members |
| `/views <link> <qty>` | Order Telegram post views |
| `/reactions <link> <qty>` | Order Telegram post reactions |
| `/shares <link> <qty>` | Order Telegram post shares |
| `/order <service> <link> <qty>` | Generic order form |

Example:

```
/members https://t.me/your_channel 1000
/views https://t.me/your_channel/42 5000
```

---

## Balance notifications

- A background job checks the balance every `BALANCE_CHECK_INTERVAL_MIN` minutes.
- When the balance drops to/below `BALANCE_LOW_THRESHOLD`, the bot sends a warning
  privately to every authorized user (only once, until it's topped up again).
- If an order is rejected for insufficient funds, the bot sends an immediate alert.
- When the balance is topped up above the threshold, the bot sends an "all good"
  message and re-arms the alert.

---

## Security notes

- The `.env` file contains secrets (bot token and API key) and is git-ignored.
- Access is locked to `AUTHORIZED_USER_IDS`; keep this list minimal.
