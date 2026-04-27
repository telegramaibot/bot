"""Channel and group creation helpers for the Telethon userbot."""

from __future__ import annotations

from telethon.tl import functions

from userbot_remote.safety.anti_ban import flood_safe, safe_send
from userbot_remote.userbot.contact_ops import resolve_entity


@flood_safe
async def create_channel(client, title: str, about: str = ""):
    """Create a new broadcast channel and return the created entity."""

    result = await client(
        functions.channels.CreateChannelRequest(
            title=title,
            about=about,
            megagroup=False,
        )
    )
    return result.chats[0]


@flood_safe
async def create_group(client, title: str, users: list | None = None):
    """Create a new supergroup and optionally invite initial members."""

    result = await client(
        functions.channels.CreateChannelRequest(
            title=title,
            about="",
            megagroup=True,
        )
    )
    entity = result.chats[0]
    if users:
        resolved_users = [await resolve_entity(client, item) for item in users]
        await client(functions.channels.InviteToChannelRequest(entity, resolved_users))
    return entity


@flood_safe
async def post_to_channel(client, channel, text: str) -> None:
    """Post a text message to a channel or group."""

    entity = await resolve_entity(client, channel)
    await safe_send(client, entity, text=text)


async def get_channel_info(client, channel) -> dict:
    """Fetch extended information about a channel or supergroup."""

    entity = await resolve_entity(client, channel)
    full = await client(functions.channels.GetFullChannelRequest(entity))
    full_chat = full.full_chat
    return {
        "id": getattr(entity, "id", None),
        "title": getattr(entity, "title", None),
        "username": getattr(entity, "username", None),
        "participants_count": getattr(full_chat, "participants_count", None),
        "about": getattr(full_chat, "about", ""),
        "broadcast": getattr(entity, "broadcast", False),
        "megagroup": getattr(entity, "megagroup", False),
    }
