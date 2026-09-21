import argparse
import getpass
import os
import sys
import time

import discord
from colorama import *

from cloner import Clone, say


def askid(prompt):
    while True:
        raw = input(f"{Style.BRIGHT}{prompt}{Style.RESET_ALL}: ").strip()
        if raw.isdigit():
            return raw
        say("must be a numeric guild ID", Fore.RED, "X")


def okay(prompt):
    return input(prompt).strip().lower() in ("y", "yes")


def token_prompt():
    while True:
        if not okay("do you already have your Discord token? [y/N]: "):
            show_token_trick()
            if not okay("got your token now? continue (Y) or quit (N): "):
                sys.exit(0)
            break
        break
    try:
        token = getpass.getpass("paste your token: ").strip()
    except Exception:
        token = input("paste your token: ").strip()
    if not token:
        say("no token provided", Fore.RED, "X")
        sys.exit(1)
    return token


async def do_clone(client, source_id, dest_id, clone_emojis, wipe, yes):
    started = time.time()
    src = client.get_guild(int(source_id))
    dst = client.get_guild(int(dest_id))

    if src is None:
        say("could not see source guild %s - being a member is enough (view permission), no admin needed" % source_id, Fore.RED, "X")
        return
    if dst is None:
        say(f"could not see destination guild {dest_id} - the account has to be in there", Fore.RED, "X")
        return

    clone = Clone(src, dst, use_emojis=clone_emojis)

    say(f"logged in as {client.user}", Fore.GREEN, "*")
    for line in clone.plan():
        print("  " + line)

    missing = await clone.perm_gaps()
    if missing:
        say("missing on destination account: " + ", ".join(missing), Fore.YELLOW, "!")
        say("clone will half-fail without these - only run this on a server you manage", Fore.YELLOW, "!")
        if not yes:
            if not okay("continue anyway? [y/N]: "):
                return

    invis = clone.hidden_src()
    if invis:
        say(f"{invis} source channels are invisible to this token - skipping them", Fore.YELLOW, "!")

    if wipe and dst.channels:
        say(f"this will DELETE every channel in '{dst.name}' before cloning", Fore.YELLOW, "!")
        if not yes:
            if input("type the destination server name to confirm, or N to abort: ").strip() != dst.name:
                say("aborted by user", Fore.GREEN, "*")
                return
    elif not wipe:
        say("merge mode: keeping existing destination channels, only adding what's missing", Fore.GREEN, "*")

    if not yes:
        if not okay("start cloning? [y/N]: "):
            say("aborted by user", Fore.GREEN, "*")
            return

    await clone.guild_meta()
    if wipe:
        await clone.wipe_channels()
    await clone.make_roles()
    await clone.make_cats()
    await clone.make_channels()
    if clone_emojis:
        await clone.grab_emojis()

    elapsed = time.strftime("%M:%S", time.gmtime(time.time() - started))
    say("done in {} - {} cloned into {}".format(elapsed, src.name, dst.name))


def show_token_trick():
    say("how to grab your own token (desktop client or web)", Fore.GREEN, "*")
    print()
    print("option 1 (works everywhere) - pull it from the Network tab:")
    print("  1. log into Discord, open DevTools (F12 / Cmd+Alt+I)")
    print("  2. reload Discord, then click any API request in the list")
    print("  3. find the 'authorization:' request header")
    print("  4. copy that value - the long random string is your token")
    print()
    print("option 2 (desktop app console) - webpack snippet:")
    print("  1. open DevTools console (F12, Console tab)")
    print("  2. paste this and hit Enter:")
    print()
    print("    (webpackChunkdiscord_app.push([[''],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]),m).find(m=>m?.exports?.default?.getToken!==void 0).exports.default.getToken()")
    print()
    print("  if that errors out, the module layout changed - use option 1.")
    print()
    print("the token is your account. only run code you pasted yourself, and never")
    print("send it anywhere. close Discord windows when done - tokens rotate on logout.")


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
        show_token_trick()
        return

    # argv first, then the env, then the interactive prompt
    token = args.token or os.environ.get("DISCORD_TOKEN") or ""
    if not token.strip():
        token = token_prompt()

    source_id = args.src or askid("source guild ID to copy from")
    dest_id = args.dest or askid("destination guild ID to paste into")
    if not source_id.isdigit() or not dest_id.isdigit():
        say("guild IDs must be numeric", Fore.RED, "X")
        sys.exit(1)

    clone_emojis = not args.no_emojis

    client = discord.Client()

    @client.event
    async def on_ready():
        try:
            await do_clone(client, source_id, dest_id, clone_emojis, wipe=not args.merge, yes=args.yes)
        finally:
            await client.close()

    try:
        client.run(token)
    except discord.LoginFailure:
        say("login failed: bad token (new tokens may take a moment to activate)", Fore.RED, "X")
        sys.exit(1)
    except discord.HTTPException as e:
        say(f"connection error: {e}", Fore.RED, "X")
        sys.exit(1)


if __name__ == "__main__":
    main()