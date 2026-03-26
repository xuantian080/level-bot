import discord
from discord.ext import commands
import json
import os
import random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
from io import BytesIO
import asyncio
from flask import Flask
from threading import Thread

# ─────────────────────────────────────────
#  KEEP ALIVE SERVER (for UptimeRobot)
# ─────────────────────────────────────────
app = Flask("")

@app.route("/")
def home():
    return "✅ Bot is running!"

def run_server():
    app.run(host="0.0.0.0", port=5000)

Thread(target=run_server, daemon=True).start()

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DEFAULT_PREFIX = "!"
_domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0].strip()
BASE_URL = f"https://{_domain}" if _domain else ""

# ─────────────────────────────────────────
#  XP / LEVEL SETTINGS
# ─────────────────────────────────────────
XP_PER_MESSAGE_MIN = 10
XP_PER_MESSAGE_MAX = 25

def xp_for_level(level):
    return 50 * level * (level + 1)

# ─────────────────────────────────────────
#  DATA FILE
# ─────────────────────────────────────────
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "xp": 0, "level": 1, "bg": "default",
            "coins": 0, "username": "Unknown",
            "owned_bgs": ["default"],
            "last_daily": None, "last_train": None
        }
    # migrate old users
    u = data[uid]
    if "coins" not in u:        u["coins"] = 0
    if "owned_bgs" not in u:    u["owned_bgs"] = ["default", u.get("bg","default")]
    if "last_daily" not in u:   u["last_daily"] = None
    if "last_train" not in u:   u["last_train"] = None
    return u

def get_settings(data):
    if "_settings" not in data:
        data["_settings"] = {"prefix": DEFAULT_PREFIX, "levelup_channel": None}
    s = data["_settings"]
    if "prefix" not in s:           s["prefix"] = DEFAULT_PREFIX
    if "levelup_channel" not in s:  s["levelup_channel"] = None
    return s

# ─────────────────────────────────────────
#  SHOP ITEMS  (name → {price, file/color})
#  Put your background images in a folder
#  called "backgrounds/" inside Replit.
#  Each entry needs a filename OR a hex color.
# ─────────────────────────────────────────
SHOP_ITEMS = {
    "sky":      {"price": 2000, "color": (135, 206, 235), "desc": "Sunny sky with clouds ☁️"},
    "nature":   {"price": 2500, "color": (34,  85,  34),  "desc": "Sunlit pine forest 🌲"},
    "fire":     {"price": 3000, "color": (180, 50,  10),  "desc": "Engulfed in flames 🔥"},
    "blossom":  {"price": 4000, "color": (255, 160, 180), "desc": "Cherry blossom night 🌸"},
}

# default bg color
DEFAULT_BG_COLOR = (30, 30, 50)

def get_bg_color(bg_name):
    if bg_name in SHOP_ITEMS:
        return SHOP_ITEMS[bg_name]["color"]
    return DEFAULT_BG_COLOR

# ─────────────────────────────────────────
#  DYNAMIC PREFIX
# ─────────────────────────────────────────
def get_prefix(bot, message):
    data = load_data()
    settings = get_settings(data)
    return settings.get("prefix", DEFAULT_PREFIX)

# ─────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.remove_command("help")
DOUBLE_XP = False

# ─────────────────────────────────────────
#  IMAGE PROFILE CARD GENERATOR
# ─────────────────────────────────────────
def make_profile_card(username, level, xp, needed_xp, rank, bg_name, avatar_bytes, coins):
    W, H = 600, 200
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background
    bg_color = get_bg_color(bg_name)
    # Check for custom image bg
    bg_path = f"backgrounds/{bg_name}.png"
    if os.path.exists(bg_path):
        bg_img = Image.open(bg_path).convert("RGBA").resize((W, H))
        img.paste(bg_img, (0, 0))
    else:
        # Gradient-like bg using two rectangles
        draw.rectangle([0, 0, W, H], fill=bg_color)
        # subtle darker overlay on right
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 60))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

    # Card overlay (semi-transparent dark panel)
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rounded_rectangle([10, 10, W-10, H-10], radius=20, fill=(0, 0, 0, 140))
    img = Image.alpha_composite(img, panel)
    draw = ImageDraw.Draw(img)

    # Avatar
    try:
        av_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((110, 110))
        # Circle mask
        mask = Image.new("L", (110, 110), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, 110, 110], fill=255)
        av_img.putalpha(mask)
        # White border circle
        border = Image.new("RGBA", (118, 118), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border)
        border_draw.ellipse([0, 0, 118, 118], fill=(255, 255, 255, 220))
        img.paste(border, (31, 41), border)
        img.paste(av_img, (35, 45), av_img)
    except:
        draw.ellipse([35, 45, 145, 155], fill=(100, 100, 100))

    # Username
    try:
        font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except:
        font_big = font_med = font_small = ImageFont.load_default()

    draw.text((170, 30), username, font=font_big, fill=(255, 255, 255))

    # Level & Rank row
    draw.text((170, 68), f"Level {level}", font=font_med, fill=(255, 220, 80))
    draw.text((310, 68), f"Rank #{rank}", font=font_med, fill=(180, 220, 255))
    draw.text((450, 68), f"🪙 {coins}", font=font_med, fill=(255, 200, 80))

    # XP bar background
    bar_x, bar_y, bar_w, bar_h = 170, 105, 390, 18
    draw.rounded_rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], radius=9, fill=(60, 60, 80))

    # XP bar fill
    progress = min(xp / needed_xp, 1.0)
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        r, g, b = bg_color
        bar_color = (min(r+80, 255), min(g+80, 255), min(b+150, 255))
        draw.rounded_rectangle([bar_x, bar_y, bar_x+fill_w, bar_y+bar_h], radius=9, fill=bar_color)

    # XP text
    draw.text((170, 128), f"{xp} / {needed_xp} XP", font=font_small, fill=(200, 200, 200))

    # Background label
    draw.text((170, 152), f"Background: {bg_name}", font=font_small, fill=(160, 160, 160))

    # Convert to RGB for saving as PNG
    final = Image.new("RGB", (W, H), (20, 20, 30))
    final.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
    buf = BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ─────────────────────────────────────────
#  EVENTS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot online as {bot.user}")
    os.makedirs("backgrounds", exist_ok=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_data()
    user = get_user(data, message.author.id)
    user["username"] = message.author.name

    xp_gain = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
    if DOUBLE_XP:
        xp_gain *= 2
    user["xp"] += xp_gain

    settings = get_settings(data)

    while user["xp"] >= xp_for_level(user["level"]):
        user["xp"] -= xp_for_level(user["level"])
        user["level"] += 1
        # coin reward on level up
        reward = user["level"] * 20
        user["coins"] += reward

        embed = discord.Embed(
            title="⬆️ Level Up!",
            description=f"🎉 **{message.author.display_name}** reached **Level {user['level']}**!\n🪙 Earned **{reward} coins** as reward!",
            color=discord.Color.gold()
        )
        channel_id = settings.get("levelup_channel")
        target = bot.get_channel(channel_id) if channel_id else message.channel
        if target:
            await target.send(embed=embed)

    save_data(data)
    await bot.process_commands(message)

# ─────────────────────────────────────────
#  !profile
# ─────────────────────────────────────────
@bot.command(name="profile")
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    user = get_user(data, member.id)
    save_data(data)

    level     = user["level"]
    xp        = user["xp"]
    needed    = xp_for_level(level)
    coins     = user.get("coins", 0)
    bg_name   = user.get("bg", "default")

    sorted_users = sorted(
        [v for k,v in data.items() if not k.startswith("_")],
        key=lambda u: (u["level"], u["xp"]), reverse=True
    )
    rank = next((i+1 for i,u in enumerate(sorted_users) if u is user), 1)

    # Get avatar
    async with ctx.typing():
        try:
            av_url = member.display_avatar.url
            resp = requests.get(str(av_url), timeout=5)
            av_bytes = resp.content
        except:
            av_bytes = b""

        try:
            buf = await asyncio.get_event_loop().run_in_executor(
                None, make_profile_card,
                member.display_name, level, xp, needed, rank, bg_name, av_bytes, coins
            )
            await ctx.send(file=discord.File(buf, filename="profile.png"))
        except Exception as e:
            await ctx.send(f"❌ Could not generate profile image: {e}")

# ─────────────────────────────────────────
#  !rank
# ─────────────────────────────────────────
@bot.command(name="rank")
async def rank_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    user = get_user(data, member.id)
    save_data(data)

    sorted_users = sorted(
        [v for k,v in data.items() if not k.startswith("_")],
        key=lambda u: (u["level"], u["xp"]), reverse=True
    )
    rank_pos = next((i+1 for i,u in enumerate(sorted_users) if u is user), "?")

    embed = discord.Embed(
        title=f"📊 {member.display_name}'s Rank",
        description=f"**Rank:** `#{rank_pos}` / `{len(sorted_users)}`\n**Level:** `{user['level']}`\n**XP:** `{user['xp']} / {xp_for_level(user['level'])}`\n**Coins:** `🪙 {user.get('coins',0)}`",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !leaderboard
# ─────────────────────────────────────────
@bot.command(name="leaderboard", aliases=["lb", "top"])
async def leaderboard(ctx):
    data = load_data()
    users = [v for k,v in data.items() if not k.startswith("_")]
    if not users:
        await ctx.send("❌ No data yet!"); return

    sorted_users = sorted(users, key=lambda u: (u["level"], u["xp"]), reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"]
    embed = discord.Embed(title="🏆 Server Leaderboard — Top 10", color=discord.Color.gold())
    desc = ""
    for i, u in enumerate(sorted_users):
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        desc += f"{medal} **{u.get('username','Unknown')}** — Lv `{u['level']}` | XP `{u['xp']}` | 🪙 `{u.get('coins',0)}`\n"
    embed.description = desc
    embed.set_footer(text="Keep chatting to climb the ranks!")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !coins
# ─────────────────────────────────────────
@bot.command(name="coins")
async def coins_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    user = get_user(data, member.id)
    save_data(data)
    embed = discord.Embed(
        title=f"🪙 {member.display_name}'s Coins",
        description=f"**{user.get('coins', 0)} coins**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !daily  — claim daily coins
# ─────────────────────────────────────────
@bot.command(name="daily")
async def daily(ctx):
    data = load_data()
    user = get_user(data, ctx.author.id)

    now = datetime.utcnow()
    last = user.get("last_daily")

    if last:
        last_dt = datetime.fromisoformat(last)
        diff = now - last_dt
        if diff < timedelta(hours=24):
            remaining = timedelta(hours=24) - diff
            hours, rem = divmod(int(remaining.total_seconds()), 3600)
            mins = rem // 60
            await ctx.send(f"⏰ You already claimed your daily! Come back in **{hours}h {mins}m**.")
            save_data(data)
            return

    reward = random.randint(100, 250)
    user["coins"] += reward
    user["last_daily"] = now.isoformat()
    save_data(data)

    embed = discord.Embed(
        title="🎁 Daily Reward!",
        description=f"You claimed **🪙 {reward} coins**!\nTotal: **{user['coins']} coins**",
        color=discord.Color.green()
    )
    embed.set_footer(text="Come back in 24 hours for more!")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !train  — earn coins every 1 hour
# ─────────────────────────────────────────
@bot.command(name="train")
async def train(ctx):
    data = load_data()
    user = get_user(data, ctx.author.id)

    now = datetime.utcnow()
    last = user.get("last_train")

    if last:
        last_dt = datetime.fromisoformat(last)
        diff = now - last_dt
        if diff < timedelta(hours=1):
            remaining = timedelta(hours=1) - diff
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            await ctx.send(f"💪 You're still tired! Train again in **{mins}m {secs}s**.")
            save_data(data)
            return

    reward = random.randint(30, 80)
    xp_reward = random.randint(15, 40)
    user["coins"] += reward
    user["xp"] += xp_reward
    user["last_train"] = now.isoformat()

    # Check level up
    leveled = False
    while user["xp"] >= xp_for_level(user["level"]):
        user["xp"] -= xp_for_level(user["level"])
        user["level"] += 1
        leveled = True

    save_data(data)

    desc = f"You trained hard and earned **🪙 {reward} coins** and **⭐ {xp_reward} XP**!\nTotal coins: **{user['coins']}**"
    if leveled:
        desc += f"\n\n⬆️ You leveled up to **Level {user['level']}**!"

    embed = discord.Embed(title="💪 Training Complete!", description=desc, color=discord.Color.orange())
    embed.set_footer(text="Train again in 1 hour!")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !shop
# ─────────────────────────────────────────
@bot.command(name="shop")
async def shop(ctx):
    data = load_data()
    user = get_user(data, ctx.author.id)
    owned = user.get("owned_bgs", ["default"])

    embed = discord.Embed(title="🛍️ Profile Background Shop", color=discord.Color.purple())
    embed.description = "Click a background name to preview it!\nUse `!buy <name>` to purchase.\n\n"

    items_text = ""
    for name, item in SHOP_ITEMS.items():
        preview_url = f"{BASE_URL}/api/bg/{name}" if BASE_URL else None
        name_display = f"[**{name}**]({preview_url})" if preview_url else f"**{name}**"
        if name in owned:
            status = "✅ Owned"
        else:
            status = f"🪙 {item['price']} coins"
        items_text += f"{name_display} — {item['desc']}\n> {status}\n\n"

    embed.description += items_text
    embed.add_field(name="Your Coins", value=f"🪙 {user.get('coins', 0)}", inline=False)
    embed.set_footer(text="Use !setbg <name> to equip a background you own • !inventory to see yours")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !buy
# ─────────────────────────────────────────
@bot.command(name="buy")
async def buy(ctx, item_name: str = None):
    if item_name is None:
        await ctx.send("❌ Usage: `!buy <item name>`\nCheck `!shop` for available items."); return

    item_name = item_name.lower()
    if item_name not in SHOP_ITEMS:
        await ctx.send(f"❌ Item `{item_name}` not found in shop. Check `!shop`!"); return

    data = load_data()
    user = get_user(data, ctx.author.id)

    if item_name in user.get("owned_bgs", []):
        await ctx.send(f"✅ You already own **{item_name}**! Use `!setbg {item_name}` to equip it."); return

    price = SHOP_ITEMS[item_name]["price"]
    if user.get("coins", 0) < price:
        short = price - user.get("coins", 0)
        await ctx.send(f"❌ Not enough coins! You need **🪙 {price}** but have **🪙 {user.get('coins',0)}**.\nYou're short by **{short} coins**."); return

    user["coins"] -= price
    if "owned_bgs" not in user:
        user["owned_bgs"] = ["default"]
    user["owned_bgs"].append(item_name)
    save_data(data)

    embed = discord.Embed(
        title="🎉 Purchase Successful!",
        description=f"You bought the **{item_name}** background for 🪙 **{price} coins**!\nUse `!setbg {item_name}` to equip it.",
        color=discord.Color.green()
    )
    embed.add_field(name="Remaining Coins", value=f"🪙 {user['coins']}")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !setbg
# ─────────────────────────────────────────
@bot.command(name="setbg")
async def setbg(ctx, bg_name: str = None):
    if bg_name is None:
        await ctx.send("❌ Usage: `!setbg <name>`"); return

    bg_name = bg_name.lower()
    data = load_data()
    user = get_user(data, ctx.author.id)

    owned = user.get("owned_bgs", ["default"])

    # allow "default" always
    if bg_name != "default" and bg_name not in owned:
        await ctx.send(f"❌ You don't own **{bg_name}**! Buy it from `!shop` first."); return

    if bg_name != "default" and bg_name not in SHOP_ITEMS and not os.path.exists(f"backgrounds/{bg_name}.png"):
        await ctx.send(f"❌ Background `{bg_name}` doesn't exist."); return

    user["bg"] = bg_name
    save_data(data)

    embed = discord.Embed(
        title="🎨 Background Updated!",
        description=f"Your profile background is now **{bg_name}**!",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !inventory
# ─────────────────────────────────────────
@bot.command(name="inventory", aliases=["inv", "mybgs"])
async def inventory(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    user = get_user(data, member.id)
    owned = user.get("owned_bgs", ["default"])
    equipped = user.get("bg", "default")

    embed = discord.Embed(
        title=f"🎒 {member.display_name}'s Backgrounds",
        color=discord.Color.purple()
    )

    if not owned:
        embed.description = "No backgrounds owned yet! Check `!shop` to buy some."
    else:
        lines = ""
        for name in owned:
            equipped_tag = " ◀ **equipped**" if name == equipped else ""
            if name in SHOP_ITEMS and BASE_URL:
                preview_url = f"{BASE_URL}/api/bg/{name}"
                lines += f"[**{name}**]({preview_url}){equipped_tag}\n"
            elif name == "default":
                lines += f"**{name}**{equipped_tag}\n"
            else:
                lines += f"**{name}**{equipped_tag}\n"
        embed.description = lines

    embed.set_footer(text="Click a name to preview • Use !setbg <name> to equip")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !setprefix  (admin only)
# ─────────────────────────────────────────
def is_admin(ctx):
    return ctx.author.guild_permissions.administrator or ctx.author == ctx.guild.owner

@bot.command(name="setprefix")
async def setprefix(ctx, new_prefix: str = None):
    if not is_admin(ctx):
        await ctx.send("❌ Admins only!"); return
    if new_prefix is None:
        await ctx.send("❌ Usage: `!setprefix <prefix>`"); return

    data = load_data()
    settings = get_settings(data)
    settings["prefix"] = new_prefix
    save_data(data)

    embed = discord.Embed(
        title="✅ Prefix Updated",
        description=f"Bot prefix is now `{new_prefix}`\nExample: `{new_prefix}profile`",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !setlevelchannel  (admin only)
# ─────────────────────────────────────────
@bot.command(name="setlevelchannel")
async def setlevelchannel(ctx, channel: discord.TextChannel = None):
    if not is_admin(ctx):
        await ctx.send("❌ Admins only!"); return
    if channel is None:
        await ctx.send("❌ Usage: `!setlevelchannel #channel`"); return

    data = load_data()
    settings = get_settings(data)
    settings["levelup_channel"] = channel.id
    save_data(data)

    embed = discord.Embed(
        title="✅ Level Up Channel Set",
        description=f"Level up messages will go to {channel.mention}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────
@bot.command(name="addxp")
async def addxp(ctx, member: discord.Member = None, amount: int = 0):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    if not member or amount <= 0: await ctx.send("❌ Usage: `!addxp @user <amount>`"); return
    data = load_data()
    user = get_user(data, member.id)
    user["xp"] += amount
    while user["xp"] >= xp_for_level(user["level"]):
        user["xp"] -= xp_for_level(user["level"])
        user["level"] += 1
    save_data(data)
    await ctx.send(embed=discord.Embed(title="✅ XP Added", description=f"Gave **{amount} XP** to **{member.display_name}**. Now Level `{user['level']}`", color=discord.Color.green()))

@bot.command(name="removexp")
async def removexp(ctx, member: discord.Member = None, amount: int = 0):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    if not member or amount <= 0: await ctx.send("❌ Usage: `!removexp @user <amount>`"); return
    data = load_data()
    user = get_user(data, member.id)
    user["xp"] = max(0, user["xp"] - amount)
    save_data(data)
    await ctx.send(embed=discord.Embed(title="✅ XP Removed", description=f"Removed **{amount} XP** from **{member.display_name}**", color=discord.Color.orange()))

@bot.command(name="addcoins")
async def addcoins(ctx, member: discord.Member = None, amount: int = 0):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    if not member or amount <= 0: await ctx.send("❌ Usage: `!addcoins @user <amount>`"); return
    data = load_data()
    user = get_user(data, member.id)
    user["coins"] += amount
    save_data(data)
    await ctx.send(embed=discord.Embed(title="✅ Coins Added", description=f"Gave **🪙 {amount}** to **{member.display_name}**. Total: `{user['coins']}`", color=discord.Color.green()))

@bot.command(name="removecoins")
async def removecoins(ctx, member: discord.Member = None, amount: int = 0):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    if not member or amount <= 0: await ctx.send("❌ Usage: `!removecoins @user <amount>`"); return
    data = load_data()
    user = get_user(data, member.id)
    user["coins"] = max(0, user["coins"] - amount)
    save_data(data)
    await ctx.send(embed=discord.Embed(title="✅ Coins Removed", description=f"Removed **🪙 {amount}** from **{member.display_name}**", color=discord.Color.orange()))

@bot.command(name="setlevel")
async def setlevel(ctx, member: discord.Member = None, level: int = None):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    if not member or not level or level < 1: await ctx.send("❌ Usage: `!setlevel @user <level>`"); return
    data = load_data()
    user = get_user(data, member.id)
    user["level"] = level
    user["xp"] = 0
    save_data(data)
    await ctx.send(embed=discord.Embed(title="✅ Level Set", description=f"**{member.display_name}** set to Level **{level}**", color=discord.Color.blurple()))

@bot.command(name="resetuser")
async def resetuser(ctx, member: discord.Member = None):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    if not member: await ctx.send("❌ Usage: `!resetuser @user`"); return
    data = load_data()
    uid = str(member.id)
    if uid in data: del data[uid]
    save_data(data)
    await ctx.send(embed=discord.Embed(title="✅ User Reset", description=f"**{member.display_name}** wiped to Level 1", color=discord.Color.red()))

@bot.command(name="doublexp")
async def doublexp(ctx):
    if not is_admin(ctx): await ctx.send("❌ Admins only!"); return
    global DOUBLE_XP
    DOUBLE_XP = not DOUBLE_XP
    status = "🟢 ON" if DOUBLE_XP else "🔴 OFF"
    await ctx.send(embed=discord.Embed(title=f"⚡ Double XP: {status}", description="2x XP for all messages!" if DOUBLE_XP else "Back to normal XP.", color=discord.Color.gold() if DOUBLE_XP else discord.Color.greyple()))

@bot.command(name="botinfo")
async def botinfo(ctx):
    data = load_data()
    users = [v for k,v in data.items() if not k.startswith("_")]
    total_xp = sum(u["xp"] for u in users)
    top = max(users, key=lambda u: (u["level"], u["xp"]), default=None)
    embed = discord.Embed(title="🤖 Bot Info", color=discord.Color.blurple())
    embed.add_field(name="Members Tracked", value=f"`{len(users)}`", inline=True)
    embed.add_field(name="Total XP", value=f"`{total_xp}`", inline=True)
    embed.add_field(name="Double XP", value=f"`{'ON' if DOUBLE_XP else 'OFF'}`", inline=True)
    if top: embed.add_field(name="👑 Top Member", value=f"`{top.get('username','?')}` — Lv `{top['level']}`", inline=False)
    embed.set_footer(text=f"Server: {ctx.guild.name}")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  !help
# ─────────────────────────────────────────
@bot.command(name="help")
async def help_cmd(ctx):
    data = load_data()
    settings = get_settings(data)
    p = settings.get("prefix", "!")

    embed = discord.Embed(title="📖 Bot Commands", color=discord.Color.blurple())
    embed.add_field(name="👤 Profile", value=f"`{p}profile` `{p}rank` `{p}leaderboard`", inline=False)
    embed.add_field(name="🪙 Coins", value=f"`{p}coins` `{p}daily` `{p}train`", inline=False)
    embed.add_field(name="🛍️ Shop", value=f"`{p}shop` `{p}buy <name>` `{p}setbg <name>` `{p}inventory`", inline=False)
    if is_admin(ctx):
        embed.add_field(name="🔒 Admin", value=f"`{p}addxp` `{p}removexp` `{p}setlevel` `{p}resetuser`\n`{p}addcoins` `{p}removecoins` `{p}doublexp` `{p}botinfo`\n`{p}setprefix` `{p}setlevelchannel`", inline=False)
    embed.set_footer(text="Earn XP by chatting! Use !daily and !train for coins!")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────
bot.run(TOKEN)
