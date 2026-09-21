import asyncio
import time
from functools import partial

import discord
from colorama import *

# slow things down a bit - self-token accounts get rate limited fast
_delay = 0.2


def log(message, color=Fore.CYAN, symbol="+"):
    prefix = f" {symbol} " if symbol else ""
    print(f"{Style.BRIGHT}{color}{prefix}{message}{Style.RESET_ALL}")


def print_add(message):
    log(message, Fore.CYAN, "+")


def print_del(message):
    log(message, Fore.MAGENTA, "-")


def print_info(message):
    log(message, Fore.GREEN, "*")


def print_warn(message):
    log(message, Fore.YELLOW, "!")


def print_err(message):
    log(message, Fore.RED, "X")


class Clone:
    def __init__(self, source, dest, use_emojis=True):
        self.source = source
        self.dest = dest
        self.use_emojis = use_emojis
        self.role_lookup = {}

    async def _attempt(self, what, fn):
        # user-token clients get throttled hard, so loop on 429s instead of dying
        while True:
            try:
                return await fn()
            except discord.Forbidden:
                print_err(f"forbidden: {what}")
                return None
            except discord.NotFound:
                print_err(f"not found: {what}")
                return None
            except discord.HTTPException as e:
                if e.status != 429:
                    print_err(f"http {e.status}: {what}")
                    return None
                wait = float(getattr(e, "retry_after", 5))
                print_warn(f"rate limited on '{what}' - sleeping {wait:.1f}s")
                await asyncio.sleep(wait)

    async def check_dest_perms(self):
        p = self.dest.me.guild_permissions
        checks = {
            "MANAGE_CHANNELS": p.manage_channels,
            "MANAGE_ROLES": p.manage_roles,
            "MANAGE_GUILD": p.manage_guild,
        }
        if self.use_emojis:
            checks["MANAGE_EMOJIS_AND_STICKERS"] = p.manage_emojis or p.manage_expressions
        return [k for k, ok in checks.items() if not ok]

    def invis_source_channels(self):
        me = self.source.me
        return sum(
            1 for c in self.source.channels
            if not c.permissions_for(me).view_channel
        )

    async def edit_guild(self):
        if self.source.name != self.dest.name:
            await self._attempt(
                "rename guild",
                partial(self.dest.edit, name=self.source.name),
            )
            print_add(f"renamed to {self.source.name}")
        icon = self.source.icon
        if icon is None:
            return
        try:
            image = await icon.read()
        except Exception as e:
            print_err(f"could not fetch source icon: {e}")
            return
        await self._attempt("set guild icon", partial(self.dest.edit, icon=image))
        print_add("guild icon copied")

    async def delete_channels(self):
        all_channels = [c for c in self.dest.channels]
        # categories go last - deleting one while it still has children is flaky
        leaves = [c for c in all_channels if not isinstance(c, discord.CategoryChannel)]
        cats = [c for c in all_channels if isinstance(c, discord.CategoryChannel)]
        deleted = 0
        for ch in leaves + cats:
            try:
                await ch.delete()
                deleted += 1
            except discord.HTTPException as e:
                print_err("delete %s: http %s" % (ch.name, e.status))
            await asyncio.sleep(_delay)
        if deleted:
            print_del(f"deleted {deleted} channels")

    async def create_roles(self):
        src_roles = [
            r for r in sorted(self.source.roles, key=lambda r: r.position)
            if not r.is_default() and not r.managed
        ]
        admin_roles = [r for r in src_roles if r.permissions.administrator]
        if admin_roles:
            print_warn("source has admin roles: " + ", ".join(r.name for r in admin_roles))

        made = 0
        for r in src_roles:
            new = await self._attempt(
                f"create role {r.name}",
                partial(
                    self.dest.create_role,
                    name=r.name,
                    colour=r.colour,
                    hoist=r.hoist,
                    mentionable=r.mentionable,
                    permissions=r.permissions,
                ),
            )
            if new:
                made += 1
        if made:
            print_add("created %d roles" % made)

        # @everyone keeps its id, so set perms on it in place instead of re-creating
        await self._attempt(
            "set @everyone permissions",
            partial(self.dest.default_role.edit, permissions=self.source.default_role.permissions),
        )

        self.role_lookup = {r.name: r for r in self.dest.roles}

        for i, src_role in enumerate(src_roles, start=1):
            dst_role = self.role_lookup.get(src_role.name)
            if dst_role:
                await self._attempt(
                    f"position role {src_role.name}",
                    partial(dst_role.edit, position=i),
                )

    def _ov(self, overwrites):
        # members aren't copied over, so their overrides are useless - drop them
        mapped = {}
        for target, ov in overwrites.items():
            if isinstance(target, discord.Member):
                continue
            if isinstance(target, discord.Object):
                src_role = self.source.get_role(target.id)
                if src_role is None:
                    continue
                target = src_role
            dst_role = self.role_lookup.get(target.name)
            if dst_role is not None:
                mapped[dst_role] = ov
        return mapped

    async def create_categories(self):
        cats = sorted(self.source.categories, key=lambda c: c.position)
        made = 0
        for cat in cats:
            ow = self._ov(cat.overwrites)
            ok = await self._attempt(
                f"create category {cat.name}",
                partial(self.dest.create_category, name=cat.name, overwrites=ow),
            )
            if ok:
                made += 1
            await asyncio.sleep(_delay)
        if made:
            print_add(f"{made} categories created")

    async def create_channels(self):
        dest_cats = {c.name: c for c in self.dest.categories}

        made = 0
        for text in sorted(self.source.text_channels, key=lambda c: c.position):
            ow = self._ov(text.overwrites)
            cat = dest_cats.get(text.category.name) if text.category else None
            ok = await self._attempt(
                f"create text channel #{text.name}",
                partial(
                    self.dest.create_text_channel,
                    name=text.name,
                    topic=text.topic,
                    slowmode_delay=text.slowmode_delay,
                    nsfw=text.nsfw,
                    overwrites=ow or None,
                    category=cat,
                ),
            )
            if ok:
                made += 1
            await asyncio.sleep(_delay)
        if made:
            print_add(f"{made} text channels created")

        made = 0
        for voice in sorted(self.source.voice_channels, key=lambda c: c.position):
            ow = self._ov(voice.overwrites)
            cat = dest_cats.get(voice.category.name) if voice.category else None
            ok = await self._attempt(
                f"create voice channel {voice.name}",
                partial(
                    self.dest.create_voice_channel,
                    name=voice.name,
                    bitrate=voice.bitrate,
                    user_limit=voice.user_limit,
                    nsfw=voice.nsfw,
                    overwrites=ow or None,
                    category=cat,
                ),
            )
            if ok:
                made += 1
            await asyncio.sleep(_delay)
        if made:
            print_add(f"{made} voice channels done")

    async def copy_emojis(self):
        n = 0
        for emoji in self.source.emojis:
            try:
                image = await emoji.read()
            except Exception as e:
                print_err(f"could not fetch emoji {emoji.name}: {e}")
                continue
            ok = await self._attempt(
                f"create emoji {emoji.name}",
                partial(self.dest.create_custom_emoji, name=emoji.name, image=image),
            )
            if ok:
                n += 1
            await asyncio.sleep(0.3)
        if n:
            print_add(f"{n} emojis created")

    def plan(self):
        roles = len([r for r in self.source.roles if not r.is_default() and not r.managed])
        lines = [
            f"source: {self.source.name} ({self.source.id})",
            f"dest: {self.dest.name} ({self.dest.id})",
            f"roles: {roles}",
            f"categories: {len(self.source.categories)}",
            f"text: {len(self.source.text_channels)}",
            f"voice: {len(self.source.voice_channels)}",
        ]
        if self.use_emojis:
            lines.append(f"emojis: {len(self.source.emojis)}")
        return lines