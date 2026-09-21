import argparse
import getpass
import os
import sys
import time

import discord
from colorama import Style

from cloner import Clone, print_add, print_err, print_info, print_warn


def ask_id(prompt):
    while True:
        raw = input(f"{Style.BRIGHT}{prompt}{Style.RESET_ALL}: ").strip()
        if raw.isdigit():
            return raw
        print_err("must be a numeric guild ID")


def ask_token():
    while True:
        have = input("do you already have your Discord token? [y/N]: ").strip().lower()
        if have in ("", "n", "no"):
            get_own_token()
            if input("got your token now? you can continue (Y) or quit (N): ").strip().lower() != "y":
                sys.exit(0)
            break
        if have in ("y", "yes"):
            break
        print_err("invalid choice")
    try:
        token = getpass.getpass("paste your token: ").strip()
    except Exception:
        token = input("paste your token: ").strip()
    if not token:
        print_err("no token provided")
        sys.exit(1)
    return token


def resolve_token(args):
    if args.token:
        return args.token.strip()
    env = os.environ.get("DISCORD_TOKEN")
    if env:
        return env.strip()
    return ask_token()


async def run(client, source_id, dest_id, clone_emojis, wipe, yes):
    started = time.time()
    source = client.get_guild(int(source_id))
    dest = client.get_guild(int(dest_id))

    if source is None:
        print_err(f"could not see source guild {source_id}. the account must be a member (view permission is enough, no admin needed).")
        return
    if dest is None:
        print_err(f"could not see destination guild {dest_id}. the account must be a member there.")
        return

    clone = Clone(source, dest, use_emojis=clone_emojis)

    print_info(f"logged in as {client.user}")
    for line in clone.plan():
        print(f"  {line}")

    missing = await clone.check_dest_perms()
    if missing:
        print_warn("destination account is missing: " + ", ".join(missing))
        print_warn("cloning will partially fail without these; only continue on a server where you manage it")
        if not yes:
            if input("continue anyway? [y/N]: ").strip().lower() != "y":
                return

    invis = clone.invis_source_channels()
    if invis:
        print_warn(f"{invis} source channels are not visible to this account and will be skipped")

    if wipe and dest.channels:
        print_warn(f"this will DELETE every existing channel in destination '{dest.name}' before cloning")
        if not yes:
            if input("type the destination server name to confirm, or N to abort: ").strip() != dest.name:
                print_info("aborted by user")
                return
    elif not wipe:
        print_info("merge mode: existing destination channels are kept, only missing ones are added")

    if not yes:
        if input("start cloning? [y/N]: ").strip().lower() != "y":
            print_info("aborted by user")
            return

    await clone.edit_guild()
    if wipe:
        await clone.delete_channels()
    await clone.create_roles()
    await clone.create_categories()
    await clone.create_channels()
    if clone_emojis:
        await clone.copy_emojis()

    elapsed = time.strftime("%M:%S", time.gmtime(time.time() - started))
    print_add(f"done in {elapsed} — {source.name} cloned into {dest.name}")


def get_own_token():
    print_info("how to grab your own token from the Discord client (desktop or web)")
    print()

    print("method 1  (no code, works everywhere) - Network tab:")
    print("  1. log into Discord (desktop app or browser)")
    print("  2. open DevTools: desktop app or browser = F12 / Cmd+Option+I / Ctrl+Shift+I")
    print("  3. go to the Network tab, then reload Discord (F5)")
    print("  4. click any API request in the list (e.g. '@me' or a 'guilds' request)")
    print("  5. in the request Headers, scroll to 'Request Headers'")
    print("  6. copy the value of 'authorization:' -- that value IS your token")
    print()

    print("method 2  (desktop app console) - webpack snippet:")
    print("  1. open DevTools console (F12, Console tab) in the DESKTOP app")
    print("  2. paste this, press Enter:")
    print()
    print("    (webpackChunkdiscord_app.push([[''],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]),m).find(m=>m?.exports?.default?.getToken!==void 0).exports.default.getToken()")
    print()
    print("  if that errors out, the module layout changed - use method 1 instead.")
    print()

    print("safety notes:")
    print("  - this token IS your account. only run devtools code that you pasted yourself.")
    print("  - never send the token to anybody, and never paste it into a random website/tool.")
    print("  - when done, close all Discord windows; tokens rotate on logout.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="discord-server-cloner",
        description="clone a Discord server's structure into another server you manage",
    )
    parser.add_argument("--token", help="token (skips the token prompt; nothing is stored)")
    parser.add_argument("--src", help="source guild ID to copy from")
    parser.add_argument("--dest", help="destination guild ID to paste into (needs manage perms)")
    parser.add_argument("--no-emojis", action="store_true", help="skip emoji cloning")
    parser.add_argument("--merge", action="store_true", help="keep existing destination channels instead of wiping")
    parser.add_argument("--yes", action="store_true", help="skip all confirmation prompts")
    parser.add_argument("--get-token", action="store_true", help="show how to obtain your own token and exit")
    args = parser.parse_args()

    if args.get_token:
        sys.exit(get_own_token())

    token = resolve_token(args)

    source_id = args.src or ask_id("source guild ID to copy from")
    dest_id = args.dest or ask_id("destination guild ID to paste into")
    if not source_id.isdigit() or not dest_id.isdigit():
        print_err("guild IDs must be numeric")
        sys.exit(1)

    clone_emojis = not args.no_emojis

    client = discord.Client()

    @client.event
    async def on_ready():
        try:
            await run(client, source_id, dest_id, clone_emojis, wipe=not args.merge, yes=args.yes)
        finally:
            await client.close()

    try:
        client.run(token)
    except discord.LoginFailure:
        print_err("login failed: the token is invalid, expired, or not accepted")
        print_warn("if the token was just generated, it may take a moment to activate")
        sys.exit(1)
    except discord.HTTPException as e:
        print_err(f"connection error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()