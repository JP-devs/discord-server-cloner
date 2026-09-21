import asyncio
import time
from functools import partial

import discord
from colorama import *

# user-token accounts trip the 429 wall fast, so keep a beat between calls
_pace = 0.2


def say(msg, colour=Fore.CYAN, mark="+"):
    print(f"{Style.BRIGHT}{colour} {mark} {msg}{Style.RESET_ALL}")


class Clone:
    def __init__(self, source, dest, use_emojis=True):
        self.source = source
        self.dest = dest
        self.use_emojis = use_emojis
        self.name2role = {}

    async def _poke(self, what, task):
        # 429s are the norm on self-tokens - sleep them off instead of dying
        while True:
            try:
                return await task()
            except discord.Forbidden:
                say(f"forbidden: {what}", Fore.RED, "X")
                return None
            except discord.NotFound:
                say(f"not found: {what}", Fore.RED, "X")
                return None
            except discord.HTTPException as e:
                if e.status != 429:
                    say(f"http {e.status}: {what}", Fore.RED, "X")
                    return None
                backoff = float(getattr(e, "retry_after", 5))
                say(f"rate limited on '{what}' - waiting {backoff:.1f}s", Fore.YELLOW, "!")
                await asyncio.sleep(backoff)

    async def perm_gaps(self):
        # the destination token needs these three, plus emoji perms when enabled
        g = self.dest.me.guild_permissions
        want = {
            "MANAGE_CHANNELS": g.manage_channels,
            "MANAGE_ROLES": g.manage_roles,
            "MANAGE_GUILD": g.manage_guild,
        }
        if self.use_emojis:
            want["MANAGE_EMOJIS_AND_STICKERS"] = g.manage_emojis or g.manage_expressions
        return [k for k, ok in want.items() if not ok]

    def hidden_src(self):
        # channels below this token's visibility line - can't be read, so skip them
        me = self.source.me
        return sum(1 for c in self.source.channels if not c.permissions_for(me).view_channel)

    async def guild_meta(self):
        # order matters: meta first, then wipe, roles, cats, channels, emojis last
        if self.source.name != self.dest.name:
            await self._poke("rename", partial(self.dest.edit, name=self.source.name))
            say(f"renamed to {self.source.name}")
        icon = self.source.icon
        if icon is None:
            return
        try:
            image = await icon.read()
        except Exception as e:
            say(f"could not fetch source icon: {e}", Fore.RED, "X")
            return
        await self._poke("guild icon", partial(self.dest.edit, icon=image))
        say("guild icon copied")

    async def wipe_channels(self):
        # categories come last - deleting one that still holds children is flaky
        everything = [c for c in self.dest.channels]
        leaves = [c for c in everything if not isinstance(c, discord.CategoryChannel)]
        cats = [c for c in everything if isinstance(c, discord.CategoryChannel)]
        cleared = 0
        for ch in leaves + cats:
            try:
                await ch.delete()
                cleared += 1
            except discord.HTTPException as e:
                say("delete %s: http %s" % (ch.name, e.status), Fore.RED, "X")
            await asyncio.sleep(_pace)
        if cleared:
            say(f"deleted {cleared} channels", Fore.MAGENTA, "-")

    async def make_roles(self):
        src_roles = [
            r for r in sorted(self.source.roles, key=lambda r: r.position)
            if not r.is_default() and not r.managed
        ]
        admins = [r for r in src_roles if r.permissions.administrator]
        if admins:
            say("source has admin roles: " + ", ".join(r.name for r in admins), Fore.YELLOW, "!")

        made = 0
        for r in src_roles:
            new = await self._poke(
                f"role {r.name}",
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
            say("made %d roles" % made)

        # @everyone is the reserved id in every guild - it can't be deleted or
        # recreated, so its permissions get edited in place to match the source
        await self._poke(
            "@everyone perms",
            partial(self.dest.default_role.edit, permissions=self.source.default_role.permissions),
        )

        self.name2role = {r.name: r for r in self.dest.roles}
        # newly created roles all land at the bottom of the stack, so re-poke
        # positions afterwards to roughly mirror the source's order
        for i, src_role in enumerate(src_roles, start=1):
            dst_role = self.name2role.get(src_role.name)
            if dst_role:
                await self._poke(f"position {src_role.name}", partial(dst_role.edit, position=i))

    def _map_ow(self, overwrites):
        # member-level overrides die here - members aren't cloned, so a per-member
        # lock would just silently vanish; only role overrides survive
        mapped = {}
        for target, ov in overwrites.items():
            if isinstance(target, discord.Member):
                continue
            if isinstance(target, discord.Object):
                src_role = self.source.get_role(target.id)
                if src_role is None:
                    continue
                target = src_role
            dst_role = self.name2role.get(target.name)
            if dst_role is not None:
                mapped[dst_role] = ov
        return mapped

    async def make_cats(self):
        cats = sorted(self.source.categories, key=lambda c: c.position)
        done = 0
        for cat in cats:
            ow = self._map_ow(cat.overwrites)
            got = await self._poke(
                f"category {cat.name}",
                partial(self.dest.create_category, name=cat.name, overwrites=ow),
            )
            if got:
                done += 1
            await asyncio.sleep(_pace)
        if done:
            say(f"{done} categories created")

    async def make_channels(self):
        byname = {c.name: c for c in self.dest.categories}

        did = 0
        for text in sorted(self.source.text_channels, key=lambda c: c.position):
            ow = self._map_ow(text.overwrites)
            parent = byname.get(text.category.name) if text.category else None
            ch = await self._poke(
                f"text #{text.name}",
                partial(
                    self.dest.create_text_channel,
                    name=text.name,
                    topic=text.topic,
                    slowmode_delay=text.slowmode_delay,
                    nsfw=text.nsfw,
                    overwrites=ow or None,
                    category=parent,
                ),
            )
            if ch:
                did += 1
            await asyncio.sleep(_pace)
        if did:
            say(f"{did} text channels in")

        got = 0
        for voice in sorted(self.source.voice_channels, key=lambda c: c.position):
            ow = self._map_ow(voice.overwrites)
            parent = byname.get(voice.category.name) if voice.category else None
            ch = await self._poke(
                f"voice {voice.name}",
                partial(
                    self.dest.create_voice_channel,
                    name=voice.name,
                    bitrate=voice.bitrate,
                    user_limit=voice.user_limit,
                    nsfw=voice.nsfw,
                    overwrites=ow or None,
                    category=parent,
                ),
            )
            if ch:
                got += 1
            await asyncio.sleep(_pace)
        if got:
            say(f"{got} voice channels done")

    async def grab_emojis(self):
        up = 0
        for emoji in self.source.emojis:
            if emoji.managed:
                continue  # managed/partner emojis belong to the pack owner - can't copy them
            try:
                image = await emoji.read()
            except Exception as e:
                say(f"could not fetch emoji {emoji.name}: {e}", Fore.RED, "X")
                continue
            made = await self._poke(
                f"emoji {emoji.name}",
                partial(self.dest.create_custom_emoji, name=emoji.name, image=image),
            )
            if made:
                up += 1
            await asyncio.sleep(0.3)
        if up:
            say(f"{up} emojis copied")

    def plan(self):
        roles = len([r for r in self.source.roles if not r.is_default() and not r.managed])
        lines = [
            "source: %s (%s)" % (self.source.name, self.source.id),
            "dest: %s (%s)" % (self.dest.name, self.dest.id),
            "roles: %d" % roles,
            "categories: %d" % len(self.source.categories),
            "text: %d" % len(self.source.text_channels),
            "voice: %d" % len(self.source.voice_channels),
        ]
        if self.use_emojis:
            lines.append("emojis: %d" % len(self.source.emojis))
        return lines