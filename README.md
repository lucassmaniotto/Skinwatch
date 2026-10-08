# <img src="./assets/overwatch.ico" alt="Overwatch" width="32"> Skinwatch

> 🔎 Find Overwatch skins available for purchase, directly from Discord.

Skinwatch searches for Overwatch skins using [Overhub](https://overhub.gg) as
the data source. Each result includes a link to the corresponding Blizzard
purchase page. 🎮

## ✨ Features

- 🔍 Search skins by hero and rarity
- 🛒 Filter skins that are currently available
- 📄 Browse results with pagination
- 🔗 Open the official Blizzard purchase page

## 🚀 Getting started

### 1. Install the dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the bot

Create a `.env` file from the example and add your Discord token:

```bash
cp .env.example .env
```

### 3. Start Skinwatch

```bash
python bot.py
```

## 🤖 Commands

### `/skins`

Search for Overwatch skins. All options are optional, and the item type is
always `Skin`.

| Option | Description | Example |
|---|---|---|
| `hero` | Filter by hero | `Ana` |
| `rarity` | Filter by rarity | `Legendary` |
| `available` | Show only available skins | `true` (default) |
| `sort` | Sort the results | `name` (default) |
| `page` | Choose the results page | `2` |

### 💡 Examples

```text
/skins hero:Ana rarity:Legendary
/skins rarity:Mythic page:2
/skins hero:Tracer available:true
```

Each page contains up to **24 skins**. 📚
