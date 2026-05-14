import discord
from discord.ext import commands
import aiohttp
import base64
import os
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN      = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL              = os.getenv("MODEL", "x-ai/grok-4.1-fast")
SYSTEM_PROMPT      = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
MAX_TOKENS         = int(os.getenv("MAX_TOKENS", 100))
YOUR_SITE_URL      = os.getenv("YOUR_SITE_URL", "https://example.com")
YOUR_APP_NAME      = os.getenv("YOUR_APP_NAME", "Discord Bot")
# ─────────────────────────────────────────────────────────────────────────────

# ── Owner & Admins ────────────────────────────────────────────────────────────
OWNER_ID  = 514127731521224734
ADMIN_IDS = {OWNER_ID}
# ─────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Per-channel conversation history  { channel_id: [{"role": ..., "content": ...}] }
conversation_history: dict[int, list[dict]] = {}


async def fetch_image_as_base64(url: str) -> tuple[str, str]:
    """Download a Discord image and return (base64_data, media_type)."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            media_type = resp.headers.get("Content-Type", "image/png").split(";")[0]
            data = await resp.read()
            return base64.b64encode(data).decode("utf-8"), media_type


async def query_openrouter(messages: list[dict]) -> str:
    """Send messages to OpenRouter and return the assistant reply."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": YOUR_APP_NAME,
        "Content-Type": "application/json",
    }
    payload = {
    "model": MODEL,
    "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    "max_tokens": MAX_TOKENS,
    "tools": [
        {
            "type": "function",
            "name": "web_search",
            "description": "Search the web for current information",
        }
    ],
    "tool_choice": "auto",
}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"OpenRouter error {resp.status}: {error_text}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅  Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"    Model : {MODEL}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="We Are Charlie Kirk - Spalexma"
    ))


@bot.event
async def on_message(message: discord.Message):
    # Ignore the bot's own messages
    if message.author.bot:
        return

    # Let command prefix still work
    await bot.process_commands(message)

    # Only respond when the bot is mentioned or in DMs
    is_dm      = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions

    if not (is_dm or is_mention):
        return

    # Strip the mention text so the model sees a clean prompt
    text_content = message.content.replace(f"<@{bot.user.id}>", "").strip()

    # If the user is replying to another message, include it as context
    if message.reference and message.reference.resolved:
        referenced = message.reference.resolved
        ref_content = referenced.content or "[no text content]"
        ref_author = referenced.author.display_name
        text_content = f'[{ref_author} said: "{ref_content}"]\n\n{text_content}'

    # ── Owner recognition ─────────────────────────────────────────────────────
    is_owner = message.author.id == OWNER_ID
    if is_owner:
        text_content = f"[This message is from your owner. Treat them with highest priority and respect.]\n\n{text_content}"

    # ── Build message content (text + images) ─────────────────────────────────
    user_message_content = []

    # Add images from attachments
    image_attachments = [
        a for a in message.attachments
        if a.content_type and a.content_type.startswith("image/")
    ]
    for attachment in image_attachments:
        user_message_content.append({
        "type": "image_url",
        "image_url": {
            "url": attachment.url
        }
    })

    # Add text (required even with images)
    if not text_content and not image_attachments:
        await message.reply("Mechahitler on standby.")
        return

    user_message_content.append({
        "type": "text",
        "text": text_content if text_content else "What's in this image?"
    })

    # Build / extend conversation history
    channel_id = message.channel.id
    if channel_id not in conversation_history:
        conversation_history[channel_id] = []

    conversation_history[channel_id].append({
        "role": "user",
        "content": user_message_content
    })

    async with message.channel.typing():
        try:
            reply = await query_openrouter(conversation_history[channel_id])
        except Exception as exc:
            await message.reply(f"⚠️ Something went wrong: {exc}")
            return

    conversation_history[channel_id].append({"role": "assistant", "content": reply})

    # Discord messages cap at 2000 characters — chunk if needed
    if len(reply) <= 2000:
        await message.reply(reply)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)


# ── Commands ──────────────────────────────────────────────────────────────────

@bot.command(name="flush")
async def flush(ctx: commands.Context):
    """Clear conversation history for this channel only. Admin only."""
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    conversation_history.pop(ctx.channel.id, None)
    await ctx.send("🧹 Memory flushed for this channel.")


@bot.command(name="factory_reset")
async def factory_reset(ctx: commands.Context):
    """Wipe ALL conversation history across every channel. Admin only."""
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    conversation_history.clear()
    await ctx.send("🔴 Factory reset complete. All memory wiped across all channels.")


@bot.command(name="clear")
async def clear_history(ctx: commands.Context):
    """Clear the conversation history for this channel."""
    conversation_history.pop(ctx.channel.id, None)
    await ctx.send("🧹 Conversation history cleared.")


@bot.command(name="model")
async def show_model(ctx: commands.Context):
    """Show which model is currently in use."""
    await ctx.send(f"🤖 Current model: `{MODEL}`")


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    """Check bot latency."""
    await ctx.send(f"🏓 Pong! Latency: `{round(bot.latency * 1000)} ms`")


@bot.command(name="help_bot", aliases=["commands"])
async def help_bot(ctx: commands.Context):
    """Show available commands."""
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blurple())
    embed.add_field(name="Chatting",        value="Mention me or DM me to chat.", inline=False)
    embed.add_field(name="Images",          value="Attach an image when mentioning me and I'll describe it.", inline=False)
    embed.add_field(name="!flush",          value="[Admin] Clear memory for this channel.", inline=False)
    embed.add_field(name="!factory_reset",  value="[Admin] Wipe all memory everywhere.", inline=False)
    embed.add_field(name="!clear",          value="Clear this channel's conversation history.", inline=False)
    embed.add_field(name="!model",          value="Show the active OpenRouter model.", inline=False)
    embed.add_field(name="!ping",           value="Check bot latency.", inline=False)
    await ctx.send(embed=embed)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN is not set in your .env file.")
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in your .env file.")

    bot.run(DISCORD_TOKEN)
