# Sales Dashboard – Dua Kelinci build test

A small web app and Telegram bot over `data/sales.csv` (September–October 2026, 1,891 invoice lines). It shows:

- net sales by region and by brand, per month, plus a region × brand table;
- the 5 weakest outlets, with the reason each one is flagged;
- a one-paragraph summary in Bahasa Indonesia for a sales manager, in the web app and on Telegram;
- reports sent on Telegram to chosen people: each regional sales manager gets their own region, the head of sales gets the overall result;
- a data-quality tab listing every fix applied to the raw CSV.

## Quick start

You need [Docker Desktop](https://docs.docker.com/get-docker/), running.

```bash
./setup.sh
```

The script creates `.env`, asks once for a Telegram bot token (press Enter to skip), checks the token with Telegram, builds the containers and prints the links. The first build takes 2–3 minutes.

- Dashboard: http://localhost:8000
- Bot: the script prints its `t.me/...` link. Send `/help`.

Other commands:

```bash
./setup.sh down          # stop (data is kept)
./setup.sh logs          # follow the logs
./setup.sh data-status   # what sales data is loaded (see "Sales data")
./setup.sh reseed        # replace the sales data from data/sales.csv
./setup.sh clean-data    # delete the sales data; it is seeded again on the next start
./setup.sh reset         # stop and delete all saved data (sales, recipients, send log)
TELEGRAM_BOT_TOKEN=123456:ABC... ./setup.sh   # no prompt
```

## Configuration

All settings live in `.env`. `./setup.sh` copies it from `.env.example`. Only the bot token is needed for the bot; everything else has a default.

| Variable | Needed? | Default | What to put |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | For the bot | empty (bot off) | Token from [@BotFather](https://t.me/BotFather): send `/newbot`, pick a name, copy the token. |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Recommended | empty (anyone) | Chat IDs that may use the bot, comma-separated. Send `/chatid` to the bot to get one. Group IDs start with `-`. |
| `TELEGRAM_ADMIN_CHAT_IDS` | For `/kirim` | empty (nobody) | Chat IDs that may send reports from the bot with `/kirim`. Not needed to send from the dashboard. |
| `TELEGRAM_DIGEST_CHAT_IDS` | No | empty (off) | Chat IDs that get the summary automatically every day. |
| `DIGEST_TIME` | No | `08:00` | Time of the daily summary, 24-hour, in `TZ`. |
| `DASHBOARD_URL` | No | `http://localhost:8000` | Link the bot sends for `/dashboard`. |
| `APP_PORT` | No | `8000` | Port for the dashboard on your machine. |
| `TZ` | No | `Asia/Jakarta` | Time zone for the daily summary. |

After you edit `.env`, run `./setup.sh` again.

Typical bot setup:

1. Put the token in `.env` (or paste it when `./setup.sh` asks).
2. Send `/chatid` to the bot from your chat or group.
3. Put that ID in `TELEGRAM_ALLOWED_CHAT_IDS`, in `TELEGRAM_ADMIN_CHAT_IDS` to use `/kirim`, and, for a daily summary, in `TELEGRAM_DIGEST_CHAT_IDS`.
4. Run `./setup.sh` again.

## Reports per sales manager

| Recipient | Area | Report |
| --- | --- | --- |
| Sales Manager | One region | Region sales and rank among regions, each branch, top and falling brands, the 3 weakest outlets in the region, new outlets |
| Atasan (head of sales) | All regions | The national summary paragraph plus every region with its change |

A recipient can be sent a report only when their data is complete: a name, a role, a region (for a sales manager) and a Telegram chat ID. Rows without a chat ID show "Belum ada" in the dashboard and cannot be ticked.

### Recipients file (placeholders)

`./setup.sh` copies `config/recipients.example.csv` to `config/recipients.csv`. Edit it, then run `./setup.sh` again. Add or remove as many rows as you like; one region can have more than one manager.

```csv
name,role,region,chat_id
Sales Manager Jabodetabek,manager,Jabodetabek,<CHAT_ID_JABODETABEK>
Sales Manager Jawa Barat,manager,Jawa Barat,<CHAT_ID_JAWA_BARAT>
Sales Manager Jawa Tengah,manager,Jawa Tengah,<CHAT_ID_JAWA_TENGAH>
Sales Manager Jawa Timur,manager,Jawa Timur,<CHAT_ID_JAWA_TIMUR>
Sales Manager Kalimantan,manager,Kalimantan,<CHAT_ID_KALIMANTAN>
Sales Manager Sumatera,manager,Sumatera,<CHAT_ID_SUMATERA>
Kepala Penjualan Nasional,head,,<CHAT_ID_HEAD>
```

Replace each `<CHAT_ID_...>` with a number, or leave the cell empty to fill it in later. In the shipped file the cells are already empty.

| Column | Values |
| --- | --- |
| `name` | Any name. Together with `role`, it identifies the row on the next import. |
| `role` | `manager` (one region) or `head` (all regions). |
| `region` | For a manager: `Jabodetabek`, `Jawa Barat`, `Jawa Tengah`, `Jawa Timur`, `Kalimantan` or `Sumatera`. Empty for a head. |
| `chat_id` | The person's Telegram chat ID, for example `123456789`. A group chat ID is negative, for example `-1001234567890`. |

How the import works at each start:
- A new name + role is added.
- An existing one gets the region from the file. It also gets the chat ID when the cell is filled; an empty cell keeps a chat ID set in the dashboard or by an invite link.
- A row with an unknown region or a non-numeric chat ID is skipped. The **Kirim ke Telegram** tab lists the skipped rows and the reason for each.
- Deleting a row from the file does not delete the recipient; use "Hapus" in the dashboard.

### Getting a chat ID

Use one of these:
1. **Invite link (easiest).** In **Kirim ke Telegram**, click "Salin link undangan" next to the person and send it to them. When they open it and press Start, the bot saves their chat ID. Nobody has to look it up.
2. **`/chatid`.** The person sends `/chatid` to the bot, then you type the number with "Isi" in the dashboard or put it in `recipients.csv`.
3. **Group chat.** Add the bot to the group, send `/chatid` in the group, and use that negative number.

### Sending

1. In **Kirim ke Telegram**, tick recipients, or use "Semua manager", "Atasan" or "Semua siap".
2. Click "Preview" to see exactly what one person will get.
3. Click "Kirim ke N orang". The result for each person shows below the table, and "Terakhir dikirim" records it.

From Telegram, an admin can do the same with `/kirim`: the bot shows a button per ready recipient plus "Semua sales manager" and "Semua (manager + atasan)".

To try it alone, add yourself twice (as a manager and as a head) with your own chat ID.

The dashboard has no login. It is meant to run on a reviewer's machine or a company network, not on the public internet.

## Telegram bot

| Command | Reply |
| --- | --- |
| `/ringkasan` | The one-paragraph summary for a sales manager |
| `/region` | Net sales per region this month, with change vs last month |
| `/brand` | Net sales per brand this month, with change vs last month |
| `/terlemah` | The 5 weakest outlets, with salesman and reason |
| `/kirim` | Admins only: choose who gets their report |
| `/start <code>` | Sent automatically by an invite link; connects the chat to a recipient |
| `/dashboard` | Link to the web dashboard |
| `/chatid` | The ID of the current chat, for `.env` |
| `/help` | The command list |

The bot only relays text. Every message is built by the backend (`GET /api/messages/<name>`), so the bot and the dashboard always show the same numbers.

## Sales data

The sales data is static and kept in SQLite. The dashboard has no upload and no way to change it.

### Where the data lives

| What | Where |
| --- | --- |
| Source CSV | `data/sales.csv` on your machine, mounted read-only at `/app/data` |
| Database | `/app/var/sales.db` inside the container, stored in the Docker volume `sales-db` |
| Tables | `sales` and `meta` (source file name, cleaning report, CSV SHA-256, `seeded_at`), plus `recipients` and `send_log` |

The volume belongs to Docker, not to the container, so removing or rebuilding the container does not touch it.

| Action | Sales data | Recipients and send log |
| --- | --- | --- |
| Container restart, `docker compose restart` | kept | kept |
| `./setup.sh down`, `docker compose down` then `up` | kept | kept |
| `docker compose up --build` (new image) | kept | kept |
| `./setup.sh reseed` | replaced | kept |
| `./setup.sh clean-data` | deleted, seeded again on the next start | kept |
| `./setup.sh clean-data --all` | deleted, seeded again on the next start | deleted |
| `./setup.sh reset` (`docker compose down -v`) | deleted | deleted |

### When it is seeded

- **First setup:** the database is empty, so the app cleans `data/sales.csv` and saves it. The log shows `first setup: seeded 1888 rows from sales.csv`.
- **Every start after that:** the app reads the saved data and does not touch the CSV. Restarting, `docker compose down` / `up` and `./setup.sh down` all keep it. Only `./setup.sh reset` (which runs `docker compose down -v`) deletes the volume.
- **If `data/sales.csv` is edited later:** the app keeps serving the saved data and logs a warning. `GET /api/health` shows `"csv_changed_since_seed": true`. Run `./setup.sh reseed` to load the new file.

Manage it with the seeder:

| Command | What it does |
| --- | --- |
| `./setup.sh data-status` | Shows the source file, row count and when it was seeded, and whether the CSV has changed since. |
| `./setup.sh reseed` | Replaces the sales data from `data/sales.csv`, then restarts the app. Recipients are kept. |
| `./setup.sh reseed data/other.csv` | Same, from another CSV with the same 15 columns. Put the file in `data/` first. |
| `./setup.sh clean-data` | Deletes the sales data (asks first); the app seeds again from `data/sales.csv` on restart. Recipients are kept. |
| `./setup.sh clean-data --all` | Also deletes the recipients and the send log. |
| `./setup.sh reset` | Stops everything and deletes the whole volume (asks first). |

Rules:

- `reseed` only takes a CSV inside `data/` (the folder the container can see). Any other path is refused with a message saying where to put the file.
- A CSV that is missing columns, or covers fewer than two months, is refused. The saved data stays as it was.
- `clean-data` and `reset` ask you to type `ya` before deleting anything. Add `--yes` to skip the question in scripts. Without a terminal and without `--yes`, they stop and delete nothing.
- `reseed` and `clean-data` restart the app if it is running, so the dashboard and the bot use the new data right away.

Example `./setup.sh data-status` output:

```
Data: sales.csv, 1888 baris, di-seed 2026-11-23T12:32:06+00:00
```

If `data/sales.csv` was edited after seeding, it adds a line saying so and suggesting `reseed`.

Without `setup.sh`, the same seeder runs as `docker compose run --rm app python -m sales.seed status|seed|reseed [--csv PATH]|clear --yes [--all]`, or `python -m sales.seed ...` from `backend/` when running without Docker.

## Design

The dashboard follows the look of [duakelinci.com](https://www.duakelinci.com/), read from its stylesheet: green `#09A94F` for the main band and headings, red `#D61A21` for navigation and buttons, near-black `#1C1C1C` text on white, Montserrat, 20px cards and fully rounded pill buttons, and the site's dotted texture and wavy edge on the green band.

A "Mode gelap" switch in the top bar turns on a soft dark theme: green-tinted charcoal (`#1D2320`) instead of black, off-white text instead of pure white, and calmer, lighter versions of the brand green and red. The first visit follows the computer's setting; after that the switch's choice is remembered in the browser.

Deliberately left out: gradients, glass effects, drop shadows, icon-per-card KPI grids and pure-black dark mode. The headline is one number with its change; the other figures sit beside it as plain facts. The summary is shown as a Telegram message, since that is where a sales manager reads it.

## Stack

| Part | Tool | Why |
| --- | --- | --- |
| Data processing | Python, pandas | Cleaning and aggregating a few thousand rows; the logic is easy to read and test. |
| API | FastAPI | Small, typed, and serves the built frontend too, so there is one URL. |
| Storage | SQLite, in a Docker volume | Holds the sales data, the Telegram recipients and a send log. One file, no database server to set up. |
| Frontend | React, Vite, TypeScript | A single page; Vite builds it to static files. |
| Charts | Recharts | Bar charts for region and brand by month. |
| Bot | python-telegram-bot | Long polling, so no public URL or webhook is needed; built-in daily job for the digest. |
| Packaging | Docker Compose | `app` (API + frontend) and `bot` (starts only when a token is set). |

```
Browser ──► app (FastAPI) ──► SQLite (volume): sales, recipients, send_log
               │  ▲
   sendMessage │  │ /api/messages, /api/recipients, /api/send
               ▼  │
Telegram ◄─────► bot (commands, invite links, /kirim)
```

Reports are always sent by the backend, whether the request comes from the dashboard or from `/kirim`, so both paths produce the same text and the same send log.

## How "weakest outlet" is defined

The lowest raw sales would only list the smallest warungs, which tells a sales manager nothing new. Each outlet is scored on two things:

1. Trend: October net sales vs September.
2. Size vs peers: October net sales vs the median outlet of the same type (Grosir, Minimarket, Toko Kelontong, Warung).

Each measure becomes a percentile rank, and the two ranks are averaged. The 5 lowest scores are flagged. An outlet with no September sales is new: it has no trend yet, so it is listed separately and never flagged.

A large outlet with a big drop (for example a grosir down 30%) is not flagged by this rule, because it is still large for its type. The summary names it separately as the biggest mover in its region.

## Data problems found and handled

| Problem in the CSV | Count | Handling |
| --- | --- | --- |
| Region spelled differently (`Jabar`, `JAWA BARAT`, `JABODETABEK`, `JAWA TIMUR`) | 10 rows | Mapped to one name per region |
| Exact duplicate lines | 3 rows | Removed |
| Trailing space in outlet name (`Grosir Berkah `) | 4 rows | Trimmed |
| Empty salesman | 5 rows | Kept, labelled `(tidak tercatat)` |
| Return line (`RTR900001`, qty −2) | 1 row | Kept as negative sales |
| qty × price ≠ gross, or gross − discount ≠ net | 0 rows | Checked and counted |

Outlets are keyed by `outlet_id`, not by name: several different outlets share a name (for example `Toko Sinar Abadi` is OUT1001, OUT1003 and OUT1040).

## Summary text

The summary is built from a template, not by an LLM, so every number in it matches the dashboard. It is plain text with no Markdown and stays under Telegram's 4,096-character limit.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/dashboard?region=Jawa%20Barat` | Everything the page shows. `region` is optional and can repeat. |
| `GET /api/messages/<name>` | Bot message text: `ringkasan`, `region`, `brand`, `terlemah`. |
| `GET /api/recipients` | Recipients with role, region, chat ID, whether they are ready, invite link and last send. |
| `PATCH /api/recipients/<id>` | Change `name`, `region` or `chat_id` (send `null` to clear the chat ID). |
| `POST /api/recipients` | Add a recipient: `{"name", "role": "manager" or "head", "region"}`. |
| `DELETE /api/recipients/<id>` | Remove a recipient. |
| `GET /api/recipients/<id>/preview` | The report text that recipient would get. |
| `POST /api/send` | Send each listed recipient their report: `{"recipient_ids": [1, 2]}`. Returns a result per recipient. |
| `POST /api/recipients/register` | Used by the bot when an invite link is opened. |
| `GET /api/telegram` | Whether a bot token is set, the bot's username, and the result of importing `config/recipients.csv`. |
| `GET /api/health` | Health check: `status`, `rows`, `source` (CSV the data came from), `seeded_at`, and `csv_changed_since_seed`. |

### Postman

Import `postman/collection.json` in Postman (**Import** > select the file). It has every endpoint above, with example bodies, descriptions and tests.

- Variables live on the collection: `baseUrl` (default `http://localhost:8000`; change it if you set `APP_PORT`), `region`, `chatId` (a placeholder), and `recipientIds` for sending.
- The whole collection can run in the Collection Runner. The Recipients folder adds two test recipients and deletes them again at the end. Its one send goes to the placeholder chat ID, so nothing reaches anyone; without a bot token it returns 503.
- The **Send to Telegram** folder sends real messages to the ids in `recipientIds`. Run it by hand.

## Run without Docker

Requires Python 3.10+ and Node.js 18+.

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
cd ../backend && uvicorn api:app --port 8000            # dashboard on http://localhost:8000
cd ../bot && pip install -r requirements.txt && \
  TELEGRAM_BOT_TOKEN=... API_URL=http://localhost:8000 python bot.py   # optional
```

For frontend development with hot reload, run `npm run dev` in `frontend/` and open http://localhost:5173 (Vite forwards `/api` to port 8000).

Tests:

```bash
cd backend && pip install -r requirements-dev.txt
pytest                              # 95 tests; fails below 98% coverage
                                    # coverage report is printed on every run
```

Checked by hand with Docker (not part of `pytest`):

- After a restart and after `down` / `up`, `seeded_at` stays the same, so nothing is seeded again.
- `clean-data --yes` deletes the sales data and keeps the 7 recipients. On restart the log shows `first setup: seeded 1888 rows from sales.csv`.
- `reseed data/<test>.csv` loads the other file (1,497 rows in the test) and `csv_changed_since_seed` stays `false`.
- `reseed` with a path outside `data/` is refused.
- `clean-data` without a terminal and without `--yes` deletes nothing.

Not tested yet: the bot against a real Telegram bot token. Sending is covered by unit tests with a mocked Telegram API only.

The analysis tests use a six-outlet fixture (`tests/conftest.py`) small enough to check every weakness score by hand; the expected values are written out in the test.

## Structure

```
setup.sh                    one-command setup
postman/collection.json     Postman collection for the API (import-ready, v2.1)
docker-compose.yml          app + bot services
.env.example                every setting, with comments
config/recipients.example.csv  sales managers and heads, with empty chat IDs to fill in
data/sales.csv              sample data from the brief
backend/api.py              FastAPI endpoints; serves the built frontend
backend/sales/clean.py      load the CSV, fix data problems, build the cleaning report
backend/sales/analysis.py   aggregations and the weakest-outlet score
backend/sales/summary.py    summary paragraph and IDR formatting
backend/sales/messages.py   Telegram message texts
backend/sales/storage.py    sales data in SQLite
backend/sales/seed.py       seeder: first-setup seed, reseed, clear (python -m sales.seed)
backend/sales/recipients.py recipients, invite codes and send log (SQLite)
backend/sales/telegram.py   sends messages through the Telegram Bot API
backend/tests/              tests for cleaning, analysis, API and messages
bot/bot.py                  Telegram bot
frontend/src/               React dashboard (SendTab.tsx: the Kirim Telegram tab)
```
