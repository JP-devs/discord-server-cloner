# Discord Server Cloner

Copies the structure of one Discord server into another server you manage - roles, categories, text and voice channels, channel permissions, emojis, even the server name and icon.

Run it with your own account token. It works on servers you can see and manage, no bot setup needed.

## License

Free to use, modify, and share. Keep the credit, don't sell it. Full terms in [LICENSE](LICENSE).

## What gets copied

- server name and icon
- roles (name, color, hoist, mentionable, permissions, position)
- categories and their permission overrides
- text channels (name, topic, slowmode, nsfw, overrides)
- voice channels (name, bitrate, user limit, nsfw, overrides)
- custom emojis

## What doesn't

- messages
- members (roles are re-created empty, so members keep whatever they hand)
- member-specific channel overrides
- threads, stickers, scheduled events
- channel sort order

## Requirements

- Python 3.8+
- a Discord account with **Manage Channels**, **Manage Roles**, and **Manage Server** on the destination server
- your own Discord token (never anyone else's)

## Install

```
install.bat
```

or by hand:

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Usage

```
start.bat
```

It will ask for the source guild ID, the destination guild ID, and your token. Options:

```
start.bat --token <token> --src <source-id> --dest <dest-id>
```

| flag | effect |
| --- | --- |
| `--token` | token to use (skips the prompt) |
| `--src` / `--dest` | guild IDs, skips the prompts |
| `--no-emojis` | skip emoji cloning |
| `--merge` | keep existing destination channels; only add missing ones |
| `--yes` | skip all confirmation prompts |
| `--get-token` | print instructions for grabbing your own token |
| `DISCORD_TOKEN` env var | used when `--token` isn't passed |

By default the destination server is wiped before cloning. Hand `--merge` if you want to keep what's already there.

## Getting your token

`start.bat --get-token` prints two ways to grab it - from the Network tab in DevTools, or a console snippet in the desktop app.

A token is the same as your account. Keep it to yourself, put it in `--token` or an env var rather than a file, and log Discord out/in to rotate it if it ever leaks.

## Notes

- Runs on a user account via `discord.py-self`. Discord does not like user tokens doing bulk API work - the script paces its requests and retries on rate limits, but heavy runs can still get the account flagged.
- Configured for your own servers. Cloning into a server you don't manage will fail on permissions.