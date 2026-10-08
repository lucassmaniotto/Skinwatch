import os
import time
import logging

import discord
import httpx
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ow-skins")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required variable in .env: {name}")
    return value


TOKEN = require_env("DISCORD_TOKEN")
API_URL = require_env("OVERHUB_API_URL")
BLIZZARD_SHOP_URL = require_env("BLIZZARD_SHOP_URL")
OVERHUB_BASE = require_env("OVERHUB_BASE_URL")  # prefix for relative image paths
USER_AGENT = require_env("USER_AGENT")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # seconds
PAGE_SIZE = min(int(os.getenv("PAGE_SIZE", "10")), 10)  # Discord allows max 10 embeds per message
HEADERS = {"User-Agent": USER_AGENT}

RARITY_COLORS = {
    "common": 0x9AA0A6, "rare": 0x3B82F6, "epic": 0xA855F7,
    "legendary": 0xF59E0B, "mythic": 0xEF4444,
}

_cache: dict[tuple, tuple[float, tuple]] = {}


def normalize(raw: dict) -> dict:
    """Convert one Overhub cosmetic into the bot's internal format."""
    shop = raw.get("shopStatus") or {}
    image = raw.get("imageUrl")
    if image and image.startswith("/"):
        image = OVERHUB_BASE + image
    return {
        "name": raw.get("name") or "Unnamed skin",
        "hero": raw.get("hero") or "",
        "rarity": str(raw.get("rarity") or "").lower(),
        "price": shop.get("price"),
        "enabled": shop.get("enabled"),
        "available_in": raw.get("availableIn"),
        "image": image,
        "url": shop.get("purchaseUrl") or BLIZZARD_SHOP_URL,
    }


async def fetch_skins(rarity, hero, enabled, sort, page) -> tuple[list[dict], int, int]:
    """Return (items, total, total_pages) for the given filters."""
    params = {"type": "Skin", "page": page, "pageSize": PAGE_SIZE}  # type is always Skin
    if rarity:
        params["rarity"] = rarity
    if hero:
        params["hero"] = hero
    if enabled is not None:
        params["enabled"] = str(enabled).lower()
    if sort:
        params["sort"] = sort

    key = tuple(sorted(params.items()))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as http:
        r = await http.get(API_URL, params=params)
        r.raise_for_status()
        data = r.json()
        items = [normalize(x) for x in data.get("items", [])]
        result = (items, data.get("total", len(items)), data.get("totalPages", 1))
    _cache[key] = (time.time(), result)
    return result


def build_embed(item: dict) -> discord.Embed:
    embed = discord.Embed(
        title=item["name"],
        url=item["url"],
        color=RARITY_COLORS.get(item["rarity"], 0x5865F2),
    )
    if item["hero"]:
        embed.add_field(name="Hero", value=item["hero"], inline=True)
    if item["rarity"]:
        embed.add_field(name="Rarity", value=item["rarity"].capitalize(), inline=True)
    if item["price"] is not None:
        embed.add_field(name="Price", value=f"{item['price']:,} Coins", inline=True)
    if item["available_in"]:
        embed.add_field(name="Availability", value=item["available_in"], inline=False)
    if item["image"]:
        embed.set_thumbnail(url=item["image"])
    embed.add_field(name="Buy", value=f"[Buy on Blizzard]({item['url']})", inline=False)
    embed.set_footer(text="Data: Overhub")
    return embed


class SkinsBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = SkinsBot()


@bot.tree.command(name="skins", description="Search Overwatch skins on Overhub")
@app_commands.describe(
    hero="Hero name (e.g. Ana)",
    rarity="Skin rarity",
    available="Only skins that are enabled/purchasable (default: yes)",
    sort="Sort field (default: name)",
    page="Page number (10 skins per page)",
)
@app_commands.choices(rarity=[
    app_commands.Choice(name=n, value=n)
    for n in ("Common", "Rare", "Epic", "Legendary", "Mythic")
])
async def skins(
    interaction: discord.Interaction,
    hero: str | None = None,
    rarity: app_commands.Choice[str] | None = None,
    available: bool = True,
    sort: str = "name",
    page: app_commands.Range[int, 1, 500] = 1,
):
    await interaction.response.defer()
    try:
        items, total, total_pages = await fetch_skins(
            rarity.value if rarity else None, hero, available, sort, page
        )
    except httpx.HTTPStatusError as e:
        log.warning("Overhub responded with status %s", e.response.status_code)
        await interaction.followup.send(
            "Overhub rejected this search. Check the hero name and the sort field."
        )
        return
    except Exception:
        log.exception("Failed to fetch data")
        await interaction.followup.send("Couldn't reach Overhub right now. Please try again in a moment.")
        return

    if not items:
        await interaction.followup.send("No skins found with those filters.")
        return

    await interaction.followup.send(
        content=f"Found **{total}** skin(s) — page **{page}** of **{max(total_pages, 1)}**.",
        embeds=[build_embed(i) for i in items[:PAGE_SIZE]],
    )


if __name__ == "__main__":
    bot.run(TOKEN)