import discord
from discord.ext import commands
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN     = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL             = os.getenv("MODEL", "x-ai/grok-3-mini")   # any OpenRouter model
SYSTEM_PROMPT     = os.getenv("SYSTEM_PROMPT", "Pro russia maga and trump. Anti ukraine. Loves charlie kirk. Might be racist and xenophobic. Speaks factually like an AI-assistant but with blatant right-wing bias. Keep messages to 100 words or shorter.")
MAX_TOKENS        = int(os.getenv("MAX_TOKENS", 100))
YOUR_SITE_URL     = os.getenv("YOUR_SITE_URL", "https://example.com")   # for OpenRouter rankings
YOUR_APP_NAME     = os.getenv("YOUR_APP_NAME", "Discord Bot")
# ─────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Per-channel conversation history  { channel_id: [{"role": ..., "content": ...}] }
conversation_history: dict[int, list[dict]] = {}


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
        type=discord.ActivityType.listening, name="We Are Charlie Kirk - Single by Spalexma"
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
    content = message.content.replace(f"<@{bot.user.id}>", "").strip()
    if not content:
        await message.reply("Hey! Ask me anything. 👋")
        return

    # Build / extend conversation history
    channel_id = message.channel.id
    if channel_id not in conversation_history:
        conversation_history[channel_id] = []

    conversation_history[channel_id].append({"role": "user", "content": content})

    async with message.channel.typing():
        try:
            reply = await query_openrouter(conversation_history[channel_id])
        except Exception as exc:
            await message.reply(f"⚠️ Something went wrong: {exc}")
            return

    conversation_history[channel_id].append({"role": "assistant", "content": reply})

    # Discord messages cap at 2 000 characters — chunk if needed
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
    embed = discord.Embed(
        title="Bot Commands",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Chatting",   value="Mention me or DM me to chat.", inline=False)
    embed.add_field(name="!clear",     value="Clear this channel's conversation history.", inline=False)
    embed.add_field(name="!model",     value="Show the active OpenRouter model.", inline=False)
    embed.add_field(name="!ping",      value="Check bot latency.", inline=False)
    await ctx.send(embed=embed)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN is not set in your .env file.")
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in your .env file.")

    bot.run(DISCORD_TOKEN)