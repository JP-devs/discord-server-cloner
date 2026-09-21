import argparse
import getpass
import os
import sys
import time

import discord
from colorama import *

from cloner import Clone, print_err, print_info, print_warn, print_add


def ask_id(prompt):
    while True:
        raw = input(f"{Style.BRIGHT}{prompt}{Style.RESET_ALL}: ").strip()
        if raw.isdigit():
            return raw
        print_err("must be a numeric guild ID")


def confirm(prompt):
    return input(prompt).strip().lower() in ("y", "yes")


def ask_token():
    while True:
        if not confirm("do you already have your Discord token? [y/N]: "):
            get_own_token()
            if not confirm("got your token now? continue (Y) or quit (N): "):
                sys.exit(0)
            break
        break
    try:
        token = getpass.getpass("paste your token: ").strip()
    except Exception:
        token = input("paste your token: ").strip()
    if not token:
        print_err("no token provided")
        sys.exit(1)
    return token


async def run(client, source_id, dest_id, clone_emojis, wipe, yes):
    started = time.time()
    src = client.get_guild(int(source_id))
    dst = client.get_guild(int(dest_id))

    if src is None:
        print_err(f"could not see source guild {source_id}. the account must be a member (view permission is enough, no admin needed).")
        return
    if dst is None:
        print_err(f"could not see destination guild {dest_id}. the account must be a member there.")
        return

    clone = Clone(src, dst, use_emojis=clone_emojis)

    print_info(f"logged in as {client.user}")
    for line in clone.plan():
        print(f"  {line}")

    missing = await clone.check_dest_perms()
    if missing:
        print_warn("destination account is missing: " + ", ".join(missing))
        print_warn("cloning will partially fail without these; only continue on a server where you manage it")
        if not yes:
            if not confirm("continue anyway? [y/N]: "):
                return

    invis = clone.invis_source_channels()
    if invis:
        print_warn(f"{invis} source channels are not visible to this account and will be skipped")

    if wipe and dst.channels:
        print_warn(f"this will DELETE every existing channel in destination '{dst.name}' before cloning")
        if not yes:
            if input("type the destination server name to confirm, or N to abort: ").strip() != dst.name:
                print_info("aborted by user")
                return
    elif not wipe:
        print_info("merge mode: existing destination channels are kept, only missing ones are added")

    if not yes:
        if not confirm("start cloning? [y/N]: "):
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
    print_add("done in %s - %s cloned into %s" % (elapsed, src.name, dst.name))


def get_own_token():
    print_info("how to grab your own token (desktop client or web)")
    print()

    print("option 1  (works everywhere) - pull it from the Network tab:")
    print("  1. log into Discord, open DevTools (F12 / Cmd+Alt+I)")
    print("  2. reload Discord, then click any API request in the list")
    print("  3. find the 'authorization:' request header")
    print("  4. copy that value - the long random string IS your token")
    print()

    print("option 2  (desktop app console) - webpack snippet:")
    print("  1. open DevTools console (F12, Console tab)")
    print("  2. paste this and hit Enter:")
    print()
    print("    (webpackChunkdiscord_app.push([[''],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]),m).find(m=>m?.exports?.default?.getToken!==void 0).exports.default.getToken()")
    print()
    print("  if that errors out, the module layout changed - use option 1.")
    print()

    print("notes:")
    print("  - the token IS your account. only run devtools code you pasted yourself, and never send the token anywhere.")
    print("  - close all Discord windows when done; tokens rotate on logout.")


def main():
    parser = argparse.ArgumentParser(
        prog="discord-server-cloner",
        description="copy a Discord server's structure (roles, channels, categories, emojis) into another server you manage",
    )
    parser.add_argument("--token", help="token to use (skips the prompt)")
    parser.add_argument("--src", help="source guild ID to copy from")
    parser.add_argument("--dest", help="destination guild ID to paste into")
    parser.add_argument("--no-emojis", action="store_true", help="skip emoji cloning")
    parser.add_argument("--merge", action="store_true", help="keep existing destination channels instead of wiping")
    parser.add_argument("--yes", action="store_true", help="skip all confirmation prompts")
    parser.add_argument("--get-token", action="store_true", help="print how to grab your own token and exit")
    args = parser.parse_args()

    if args.get_token:
        get_own_token()
        return

    token = (args.token or os.environ.get("DISCORD_TOKEN") or "").strip() or ask_token()

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
        print_err("login failed: bad token (new tokens may take a moment to activate)")
        sys.exit(1)
    except discord.HTTPException as e:
        print_err(f"connection error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()