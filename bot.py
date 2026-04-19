"""
NexHub Deobfuscator Discord Bot
Deobfuscate Lua scripts via file upload or chat paste.
"""

import os
import io
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from deobfuscator import DeobfuscationEngine
from obfuscator import ObfuscatorEngine

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max
MAX_PASTE_LENGTH = 50000  # 50K chars max for paste

# Bot setup
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
engine = DeobfuscationEngine()
obf_engine = ObfuscatorEngine()


# ============================================
# EVENTS
# ============================================
@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} is online!")
    print(f"   Servers: {len(bot.guilds)}")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"   Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"   Failed to sync commands: {e}")
    
    # Set status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="for obfuscated scripts 🔓"
        )
    )


# ============================================
# HELPER: PROCESS & SEND RESULT
# ============================================
async def process_and_reply(interaction_or_ctx, code: str, filename: str = "script.lua"):
    """Process code and send the deobfuscation result."""
    
    # Determine reply method
    is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
    
    async def send(content=None, embed=None, file=None):
        if is_interaction:
            if interaction_or_ctx.response.is_done():
                await interaction_or_ctx.followup.send(content=content, embed=embed, file=file)
            else:
                await interaction_or_ctx.response.send_message(content=content, embed=embed, file=file)
        else:
            await interaction_or_ctx.reply(content=content, embed=embed, file=file)
    
    # Send "processing" message
    if is_interaction:
        await interaction_or_ctx.response.defer(thinking=True)
    else:
        processing_msg = await interaction_or_ctx.reply("🔄 **Processing...** Analyzing obfuscation layers...")
    
    # Process
    result = engine.process(code, beautify=True)
    
    # Build embed
    embed = discord.Embed(
        title="🔓 NexHub Deobfuscator",
        color=discord.Color.green() if result.success else discord.Color.red()
    )
    
    # Detection info
    difficulty_emoji = {
        "trivial": "🟢", "easy": "🟢",
        "medium": "🟡", "hard": "🔴", "unknown": "⚪"
    }
    emoji = difficulty_emoji.get(result.difficulty, "⚪")
    
    embed.add_field(
        name="📋 Detection",
        value=f"**Obfuscator:** {result.obfuscator_name}\n**Difficulty:** {emoji} {result.difficulty.upper()}",
        inline=False
    )
    
    # Layers info
    if result.layers_unwrapped:
        layers_text = "\n".join(f"✅ {l}" for l in result.layers_unwrapped)
        embed.add_field(name="🧅 Layers Unwrapped", value=layers_text, inline=False)
    
    # Stats
    orig_size = len(code)
    deob_size = len(result.deobfuscated_code) if result.deobfuscated_code else 0
    embed.add_field(
        name="📊 Stats",
        value=f"**Input:** {orig_size:,} chars\n**Output:** {deob_size:,} chars\n**Time:** {result.time_taken:.2f}s",
        inline=True
    )
    
    # Status
    if result.success:
        embed.add_field(name="Status", value="✅ Berhasil!", inline=True)
    elif result.error:
        embed.add_field(name="Status", value=f"❌ Error: {result.error}", inline=True)
    else:
        embed.add_field(name="Status", value="⚠️ Tidak bisa deobfuscate sepenuhnya", inline=True)
    
    embed.set_footer(text="NexHub Deobfuscator Bot • Powered by NexHub")
    
    # Send result as file
    output_code = result.deobfuscated_code if result.deobfuscated_code else code
    output_filename = f"deobfuscated_{filename}"
    
    file = discord.File(
        io.BytesIO(output_code.encode("utf-8")),
        filename=output_filename
    )
    
    if is_interaction:
        await interaction_or_ctx.followup.send(embed=embed, file=file)
    else:
        # Delete processing message
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await interaction_or_ctx.reply(embed=embed, file=file)


async def process_obfuscation_reply(interaction_or_ctx, code: str, obf_type: str, filename: str = "script.lua"):
    """Process code and send the obfuscated result."""
    is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
    
    if is_interaction:
        await interaction_or_ctx.response.defer(thinking=True)
    else:
        processing_msg = await interaction_or_ctx.reply("🔄 **Processing...** Obfuscating code...")
        
    obf_type_upper = obf_type.upper()
    try:
        if obf_type_upper == "B64" or obf_type_upper == "BASE64":
            result = obf_engine.obfuscate_b64(code)
            type_name = "Base64 Wrapper"
        elif obf_type_upper == "XOR":
            result = obf_engine.obfuscate_xor(code)
            type_name = "XOR Byte Wrapper"
        else:
            result = obf_engine.obfuscate_b64(code)
            type_name = "Base64 Wrapper (Default)"
            obf_type_upper = "B64"
            
        embed = discord.Embed(title="🔒 NexHub Obfuscator", color=discord.Color.purple())
        embed.add_field(name="Method", value=type_name, inline=True)
        embed.add_field(name="Stats", value=f"**Input:** {len(code):,} chars\n**Output:** {len(result):,} chars", inline=True)
        embed.add_field(name="Status", value="✅ Obfuscated Successfully", inline=False)
        embed.set_footer(text="NexHub Discord Bot")
        
        output_filename = filename.replace(".lua", f"_{obf_type_upper}.lua")
        if not output_filename.endswith(".lua"):
            output_filename += ".lua"
            
        file = discord.File(io.BytesIO(result.encode("utf-8")), filename=output_filename)
        
        if is_interaction:
            await interaction_or_ctx.followup.send(embed=embed, file=file)
        else:
            try: await processing_msg.delete()
            except: pass
            await interaction_or_ctx.reply(embed=embed, file=file)
            
    except Exception as e:
        err_msg = f"❌ Error during obfuscation: {e}"
        if is_interaction:
            await interaction_or_ctx.followup.send(err_msg)
        else:
            await interaction_or_ctx.reply(err_msg)


# ============================================
# SLASH COMMAND: /deobfuscate
# ============================================
@bot.tree.command(name="deobfuscate", description="Deobfuscate a Lua script (upload file)")
@app_commands.describe(file="Upload file .lua yang ingin di-deobfuscate")
async def slash_deobfuscate(interaction: discord.Interaction, file: discord.Attachment):
    """Deobfuscate an uploaded Lua file."""
    
    # Validate file
    if file.size > MAX_FILE_SIZE:
        await interaction.response.send_message(
            f"❌ File terlalu besar! Max {MAX_FILE_SIZE // (1024*1024)}MB.",
            ephemeral=True
        )
        return
    
    if not file.filename.endswith((".lua", ".txt", ".luac")):
        await interaction.response.send_message(
            "❌ Format file tidak didukung. Gunakan `.lua` atau `.txt`",
            ephemeral=True
        )
        return
    
    # Download file content
    try:
        content = (await file.read()).decode("utf-8", errors="replace")
    except Exception as e:
        await interaction.response.send_message(f"❌ Gagal membaca file: {e}", ephemeral=True)
        return
    
    await process_and_reply(interaction, content, file.filename)


# ============================================
# SLASH COMMAND: /deob (paste code)
# ============================================
@bot.tree.command(name="deob", description="Deobfuscate Lua code dari text paste")
@app_commands.describe(code="Paste kode Lua yang ingin di-deobfuscate")
async def slash_deob_paste(interaction: discord.Interaction, code: str):
    """Deobfuscate pasted Lua code."""
    
    if len(code) > MAX_PASTE_LENGTH:
        await interaction.response.send_message(
            f"❌ Code terlalu panjang! Max {MAX_PASTE_LENGTH:,} chars. Gunakan file upload.",
            ephemeral=True
        )
        return
    
    # Strip markdown code blocks if present
    if code.startswith("```") and code.endswith("```"):
        code = code[3:-3]
        if code.startswith("lua\n"):
            code = code[4:]
    
    await process_and_reply(interaction, code)


# ============================================
# SLASH COMMAND: /obfuscate (file upload)
# ============================================
@bot.tree.command(name="obfuscate", description="Obfuscate a Lua script (upload file)")
@app_commands.describe(file="Upload file .lua yang ingin di-obfuscate", obf_type="Tipe: B64 atau XOR")
@app_commands.choices(obf_type=[
    app_commands.Choice(name="Base64", value="B64"),
    app_commands.Choice(name="XOR Byte", value="XOR")
])
async def slash_obfuscate(interaction: discord.Interaction, file: discord.Attachment, obf_type: str = "B64"):
    """Obfuscate an uploaded Lua file."""
    if file.size > MAX_FILE_SIZE:
        await interaction.response.send_message(f"❌ File terlalu besar! Max {MAX_FILE_SIZE // (1024*1024)}MB.", ephemeral=True)
        return
    if not file.filename.endswith((".lua", ".txt")):
        await interaction.response.send_message("❌ Format file tidak didukung. Gunakan `.lua` atau `.txt`", ephemeral=True)
        return
    try:
        content = (await file.read()).decode("utf-8", errors="replace")
    except Exception as e:
        await interaction.response.send_message(f"❌ Gagal membaca file: {e}", ephemeral=True)
        return
        
    await process_obfuscation_reply(interaction, content, obf_type, file.filename)

# ============================================
# SLASH COMMAND: /ob (paste code)
# ============================================
@bot.tree.command(name="ob", description="Obfuscate Lua code dari text paste")
@app_commands.describe(code="Paste kode Lua yang ingin di-obfuscate", obf_type="Tipe: B64 atau XOR")
@app_commands.choices(obf_type=[
    app_commands.Choice(name="Base64", value="B64"),
    app_commands.Choice(name="XOR Byte", value="XOR")
])
async def slash_ob_paste(interaction: discord.Interaction, code: str, obf_type: str = "B64"):
    if len(code) > MAX_PASTE_LENGTH:
        await interaction.response.send_message(f"❌ Code terlalu panjang! Max {MAX_PASTE_LENGTH:,} chars.", ephemeral=True)
        return
        
    if code.startswith("```") and code.endswith("```"):
        code = code[3:-3]
        if code.startswith("lua\n"): code = code[4:]
        
    await process_obfuscation_reply(interaction, code, obf_type, "paste_script.lua")


# ============================================
# PREFIX COMMAND: !deob
# ============================================
@bot.command(name="deob")
async def cmd_deob(ctx: commands.Context):
    """Deobfuscate via prefix command. Attach a file or paste code after !deob"""
    
    # Check for file attachments
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        
        if attachment.size > MAX_FILE_SIZE:
            await ctx.reply(f"❌ File terlalu besar! Max {MAX_FILE_SIZE // (1024*1024)}MB.")
            return
        
        try:
            content = (await attachment.read()).decode("utf-8", errors="replace")
        except Exception as e:
            await ctx.reply(f"❌ Gagal membaca file: {e}")
            return
        
        await process_and_reply(ctx, content, attachment.filename)
        return
    
    # Check for code in message
    content = ctx.message.content
    # Remove the command prefix
    code = content.replace("!deob", "", 1).strip()
    
    # Check for code blocks
    if "```" in code:
        # Extract from code block
        import re
        match = re.search(r'```(?:lua)?\n?(.*?)```', code, re.DOTALL)
        if match:
            code = match.group(1).strip()
    
    if not code:
        embed = discord.Embed(
            title="🔓 NexHub Deobfuscator",
            description=(
                "**Cara Penggunaan:**\n\n"
                "**1. Upload File:**\n"
                "`!deob` + lampirkan file .lua\n\n"
                "**2. Paste Code:**\n"
                "```\n!deob loadstring(\"code\")()```\n\n"
                "**3. Slash Command:**\n"
                "`/deobfuscate` → upload file\n"
                "`/deob` → paste code\n\n"
                "**Supported:**\n"
                "🟢 Base64, Loadstring, String.char, XOR\n"
                "🟡 WeAreDevs\n"
                "🔴 MoonSec (string extraction only)"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="NexHub Deobfuscator Bot")
        await ctx.reply(embed=embed)
        return
    
    if len(code) > MAX_PASTE_LENGTH:
        await ctx.reply(f"❌ Code terlalu panjang! Max {MAX_PASTE_LENGTH:,} chars. Gunakan file upload.")
        return
    
    await process_and_reply(ctx, code)


# ============================================
# PREFIX COMMAND: !help
# ============================================
@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    """Show help message."""
    embed = discord.Embed(
        title="🔓 NexHub Deobfuscator - Help",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📁 Upload File",
        value="`!deob` + lampirkan file `.lua`\natau `/deobfuscate` + pilih file",
        inline=False
    )
    
    embed.add_field(
        name="📝 Paste Code",
        value="```\n!deob <kode lua disini>```\natau `/deob code:<kode lua>`",
        inline=False
    )
    
    embed.add_field(
        name="🧅 Supported Obfuscators",
        value=(
            "🟢 **Easy:** Base64, Loadstring wrapper, String.char, Byte table\n"
            "🟡 **Medium:** WeAreDevs, XOR cipher, Multi-layer\n"
            "🔴 **Hard:** MoonSec, IronBrew (string extraction only)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ Info",
        value=(
            "• Max file size: 5MB\n"
            "• Auto-detect obfuscator type\n"
            "• Auto-beautify output\n"
            "• Multi-layer unwrapping"
        ),
        inline=False
    )
    
    embed.set_footer(text="NexHub Deobfuscator Bot • Powered by NexHub")
    await ctx.reply(embed=embed)


# ============================================
# PREFIX COMMAND: !ob
# ============================================
@bot.command(name="ob")
async def cmd_ob(ctx: commands.Context, obf_type: str = "B64", *, code: str = ""):
    """Obfuscate via prefix command. Format: !ob <B64/XOR> <code> or attach a file."""
    
    # Check for file attachments
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.size > MAX_FILE_SIZE:
            await ctx.reply(f"❌ File terlalu besar! Max {MAX_FILE_SIZE // (1024*1024)}MB.")
            return
        try:
            content = (await attachment.read()).decode("utf-8", errors="replace")
            await process_obfuscation_reply(ctx, content, obf_type, attachment.filename)
            return
        except Exception as e:
            await ctx.reply(f"❌ Gagal membaca file: {e}")
            return
            
    # Process code string
    if not code:
        await ctx.reply("❌ Error: Berikan kode yang ingin diobfuscate! Contoh:\n`!ob XOR print('hello')`\natau lampirkan file.")
        return
        
    if "```" in code:
        import re
        match = re.search(r'```(?:lua)?\n?(.*?)```', code, re.DOTALL)
        if match:
            code = match.group(1).strip()
            
    await process_obfuscation_reply(ctx, code, obf_type, "paste_script.lua")


# ============================================
# AUTO-DETECT: Reply to messages with .lua files
# ============================================
@bot.event
async def on_message(message: discord.Message):
    # Don't respond to self
    if message.author == bot.user:
        return
    
    # Process commands first
    await bot.process_commands(message)


# ============================================
# RUN
# ============================================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not found!")
        print("   Set it in .env file or as environment variable.")
        exit(1)
    
    print("🚀 Starting NexHub Deobfuscator Bot...")
    bot.run(TOKEN)
