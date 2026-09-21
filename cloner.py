import asyncio
import time

import discord
from colorama import Fore, Style


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
    def __init__(self, source, dest, use_emojis=True, rate_guard=True):
        self.source = source
        self.dest = dest
        self.use_emojis = use_emojis
        self.rate_guard = rate_guard
        self.role_lookup = {}

    async def _attempt(self, desc, coro_fn):
        while True:
            try:
                return await coro_fn()
            except discord.Forbidden:
                print_err(f"forbidden: {desc}")
                return None
            except discord.NotFound:
                print_err(f"not found: {desc}")
                return None
            except discord.HTTPException as e:
                if e.status == 429:
                    wait = float(getattr(e, "retry_after", None) or 5)
                    print_warn(f"rate limited on '{desc}', sleeping {wait:.1f}s")
                    await asyncio.sleep(wait)
                    continue
                print_err(f"http {e.status}: {desc}")
                return None

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
                lambda: self.dest.edit(name=self.source.name),
            )
            print_add(f"guild renamed to {self.source.name}")
        icon = self.source.icon
        if icon is not None:
            try:
                image = await icon.read()
            except Exception as e:
                print_err(f"could not fetch source icon: {e}")
                return
            await self._attempt("set guild icon", lambda i=image: self.dest.edit(icon=i))
            print_add("guild icon copied")

    async def delete_channels(self):
        all_channels = [c for c in self.dest.channels]
        leaves = [c for c in all_channels if not isinstance(c, discord.CategoryChannel)]
        cats = [c for c in all_channels if isinstance(c, discord.CategoryChannel)]
        for ch in leaves + cats:
            await self._attempt(f"delete channel {ch.name}", lambda x=ch: x.delete())
            await asyncio.sleep(0.2)
        print_del(f"deleted {len(all_channels)} existing channels")

    async def create_roles(self):
        src_roles = [
            r for r in sorted(self.source.roles, key=lambda r: r.position)
            if not r.is_default() and not r.managed
        ]
        admin_roles = [r for r in src_roles if r.permissions.administrator]
        if admin_roles:
            print_warn("source has admin roles: " + ", ".join(r.name for r in admin_roles))

        for r in src_roles:
            new = await self._attempt(
                f"create role {r.name}",
                lambda src=r: self.dest.create_role(
                    name=src.name,
                    colour=src.colour,
                    hoist=src.hoist,
                    mentionable=src.mentionable,
                    permissions=src.permissions,
                ),
            )
            if new:
                print_add(f"role '{r.name}' created")

        await self._attempt(
            "set @everyone permissions",
            lambda: self.dest.default_role.edit(permissions=self.source.default_role.permissions),
        )

        self.role_lookup = {r.name: r for r in self.dest.roles}

        for i, src_role in enumerate(src_roles, start=1):
            dst_role = self.role_lookup.get(src_role.name)
            if dst_role:
                await self._attempt(
                    f"position role {src_role.name}",
                    lambda r=dst_role, p=i: r.edit(position=p),
                )

    def _map_overwrites(self, overwrites):
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
        cats = [c for c in self.source.categories]
        cats.sort(key=lambda c: c.position)
        for cat in cats:
            ow = self._map_overwrites(cat.overwrites)
            new = await self._attempt(
                f"create category {cat.name}",
                lambda n=cat.name, o=ow: self.dest.create_category(name=n, overwrites=o),
            )
            if new:
                print_add(f"category '{cat.name}' created")
            await asyncio.sleep(0.15)

    async def create_channels(self):
        dest_cats = {c.name: c for c in self.dest.categories}

        for text in sorted(self.source.text_channels, key=lambda c: c.position):
            ow = self._map_overwrites(text.overwrites)
            cat = dest_cats.get(text.category.name) if text.category else None
            new = await self._attempt(
                f"create text channel #{text.name}",
                lambda t=text, o=ow, c=cat: self.dest.create_text_channel(
                    name=t.name,
                    topic=t.topic,
                    slowmode_delay=t.slowmode_delay,
                    nsfw=t.nsfw,
                    overwrites=o or None,
                    category=c,
                ),
            )
            if new:
                print_add(f"text channel '#{text.name}' created")
            await asyncio.sleep(0.15)

        for voice in sorted(self.source.voice_channels, key=lambda c: c.position):
            ow = self._map_overwrites(voice.overwrites)
            cat = dest_cats.get(voice.category.name) if voice.category else None
            new = await self._attempt(
                f"create voice channel {voice.name}",
                lambda v=voice, o=ow, c=cat: self.dest.create_voice_channel(
                    name=v.name,
                    bitrate=v.bitrate,
                    user_limit=v.user_limit,
                    nsfw=v.nsfw,
                    overwrites=o or None,
                    category=c,
                ),
            )
            if new:
                print_add(f"voice channel '{voice.name}' created")
            await asyncio.sleep(0.15)

    async def copy_emojis(self):
        for emoji in self.source.emojis:
            try:
                image = await emoji.read()
            except Exception as e:
                print_err(f"could not fetch emoji {emoji.name}: {e}")
                continue
            new = await self._attempt(
                f"create emoji {emoji.name}",
                lambda n=emoji.name, i=image: self.dest.create_custom_emoji(name=n, image=i),
            )
            if new:
                print_add(f"emoji ':{emoji.name}:' created")
            await asyncio.sleep(0.3)

    def plan(self):
        roles = len([r for r in self.source.roles if not r.is_default() and not r.managed])
        lines = [
            f"source:   {self.source.name} ({self.source.id})",
            f"dest:     {self.dest.name} ({self.dest.id})",
            f"roles:    {roles}",
            f"categories: {len(self.source.categories)}",
            f"text:     {len(self.source.text_channels)}",
            f"voice:    {len(self.source.voice_channels)}",
        ]
        if self.use_emojis:
            lines.append(f"emojis:   {len(self.source.emojis)}")
        return lines