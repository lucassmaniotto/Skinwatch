import os
import time
import logging
import unicodedata

import discord
import httpx
from aiohttp import web
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
OVERHUB_BASE = require_env("OVERHUB_BASE_URL").rstrip("/")  # prefix for relative image paths
USER_AGENT = require_env("USER_AGENT")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # seconds
PAGE_SIZE = min(int(os.getenv("PAGE_SIZE", "10")), 10)  # Discord allows max 10 embeds per message
VIEW_TIMEOUT = int(os.getenv("VIEW_TIMEOUT", "180"))  # seconds the buttons stay active
HEADERS = {"User-Agent": USER_AGENT}

RARITIES = ["Exclusive", "Mythic", "Ultra", "Legendary", "Epic", "Rare", "Common"]

RARITY_COLORS = {
    "exclusive": 0xEC4899, "mythic": 0xEF4444, "ultra": 0x14B8A6,
    "legendary": 0xF59E0B, "epic": 0xA855F7, "rare": 0x3B82F6, "common": 0x9AA0A6,
}

HEROES = [
    "Ana", "Anran", "Ashe", "Baptiste", "Bastion", "Brigitte", "Cassidy", "D.Va",
    "Doctrine", "Domina", "Doomfist", "Echo", "Emre", "Freja", "Genji", "Hanzo",
    "Hazard", "Illari", "Jetpack Cat", "Junker Queen", "Junkrat", "Juno", "Kiriko",
    "Lifeweaver", "Lúcio", "Mauga", "Mei", "Mercy", "Mizuki", "Moira", "Orisa",
    "Pharah", "Ramattra", "Reaper", "Reinhardt", "Roadhog", "Shion", "Sigma",
    "Sierra", "Sojourn", "Soldier: 76", "Sombra", "Symmetra", "Torbjörn", "Tracer",
    "Vendetta", "Venture", "Widowmaker", "Winston", "Wrecking Ball", "Wuyang",
    "Zarya", "Zenyatta", "D.Mon",
]


def fold(text: str) -> str:
    """Lowercase and strip accents so 'lucio' matches 'Lúcio'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


HERO_LOOKUP = {fold(h): h for h in HEROES}

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


async def start_health_server() -> None:
    """Tiny HTTP server so hosts that require an open port (e.g. Render Web Service)
    and uptime monitors have something to ping. Only runs when PORT is set."""
    port = os.getenv("PORT")
    if not port:
        return

    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(port)).start()
    log.info("Health server listening on port %s", port)


class SkinsBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await start_health_server()
        await self.tree.sync()


bot = SkinsBot()


def page_text(page: int, total: int, total_pages: int) -> str:
    return f"Found **{total}** skin(s) — page **{page}** of **{max(total_pages, 1)}**."


class PaginationView(discord.ui.View):
    """Previous/Next buttons. Only the user who ran the command can use them."""

    def __init__(self, owner_id: int, filters: dict, page: int, total_pages: int):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.owner_id = owner_id
        self.filters = filters  # rarity, hero, enabled, sort
        self.page = page
        self.total_pages = total_pages
        self.message: discord.WebhookMessage | None = None
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= self.total_pages

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who ran the command can change pages. Run /skins yourself!",
                ephemeral=True,
            )
            return False
        return True

    async def _go_to(self, interaction: discord.Interaction, page: int):
        await interaction.response.defer()
        try:
            items, total, total_pages = await fetch_skins(page=page, **self.filters)
        except Exception:
            log.exception("Failed to load page %s", page)
            await interaction.followup.send(
                "Couldn't load that page. Please try again.", ephemeral=True
            )
            return
        if not items:
            await interaction.followup.send("No more results.", ephemeral=True)
            return

        self.page = page
        self.total_pages = max(total_pages, 1)
        self._sync_buttons()
        await interaction.edit_original_response(
            content=page_text(page, total, total_pages),
            embeds=[build_embed(i) for i in items[:PAGE_SIZE]],
            view=self,
        )

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go_to(interaction, self.page - 1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go_to(interaction, self.page + 1)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@bot.tree.command(name="skins", description="Search Overwatch skins on Overhub")
@app_commands.describe(
    hero="Hero (start typing to see suggestions)",
    rarity="Skin rarity",
    available="Only skins that are enabled/purchasable (default: yes)",
    sort="Sort field (default: name)",
    page="Starting page (use the buttons to navigate)",
)
@app_commands.choices(rarity=[
    app_commands.Choice(name=n, value=n)
    for n in RARITIES
])
async def skins(
    interaction: discord.Interaction,
    hero: str | None = None,
    rarity: app_commands.Choice[str] | None = None,
    available: bool = True,
    sort: str = "name",
    page: app_commands.Range[int, 1, 500] = 1,
):
    canonical_hero = None
    if hero:
        canonical_hero = HERO_LOOKUP.get(fold(hero))
        if canonical_hero is None:
            await interaction.response.send_message(
                f"Unknown hero: **{hero}**. Pick one from the suggestions list.",
                ephemeral=True,
            )
            return

    await interaction.response.defer()
    filters = {
        "rarity": rarity.value if rarity else None,
        "hero": canonical_hero,
        "enabled": available,
        "sort": sort,
    }
    try:
        items, total, total_pages = await fetch_skins(page=page, **filters)
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

    view = (
        PaginationView(interaction.user.id, filters, page, max(total_pages, 1))
        if total_pages > 1
        else discord.utils.MISSING
    )
    message = await interaction.followup.send(
        content=page_text(page, total, total_pages),
        embeds=[build_embed(i) for i in items[:PAGE_SIZE]],
        view=view,
        wait=True,
    )
    if view is not discord.utils.MISSING:
        view.message = message


@skins.autocomplete("hero")
async def hero_autocomplete(interaction: discord.Interaction, current: str):
    query = fold(current)
    matches = [h for h in HEROES if query in fold(h)]
    return [app_commands.Choice(name=h, value=h) for h in matches[:25]]  # Discord max: 25


if __name__ == "__main__":
    bot.run(TOKEN)
