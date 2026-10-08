# Skinwatch

Searches Overwatch skins using Overhub (https://overhub.gg) as the data source. Each result links to the Blizzard purchase page.

## 1. Configure
```
pip install -r requirements.txt
cp .env.example .env   # fill in DISCORD_TOKEN
python bot.py
```
Never commit `.env` or share your token. If it leaks, reset it in the Developer Portal.

## 2. Commands
`/skins` — all options are optional (type is always `Skin`):

| Option | Overhub param | Notes |
|---|---|---|
| `hero` | `hero` | e.g. `Ana` |
| `rarity` | `rarity` | Common, Rare, Epic, Legendary, Mythic, Ultra |
| `available` | `enabled` | default: true |
| `sort` | `sort` | default: `name` |
| `page` | `page` | 24 skins per page |

Examples: `/skins hero:Ana rarity:Legendary`, `/skins rarity:Mythic page:2`
