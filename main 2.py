import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import asyncio
import random
import aiosqlite
import json
from datetime import datetime, date, timedelta
from typing import Optional
from difflib import SequenceMatcher
import hashlib
from collections import defaultdict

# ==================== IMPORTS FROM DATABASE ====================
from database import *
from image_generator import *

# ==================== ENVIRONMENT SETUP ====================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
ROBUX_ICON = "<:robux:1471290376043368498>"

# ==================== AUTHORIZED SERVERS ====================
AUTHORIZED_GUILDS = [
    1470876770449359003,  # REPLACE WITH YOUR SERVER ID
]

def is_authorized_guild(guild_id):
    """Check if guild is authorized"""
    return guild_id in AUTHORIZED_GUILDS

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ==================== GLOBAL VARIABLES ====================
invite_cache = {}
game_cooldowns = {}
message_cooldowns = {}
user_vc_states = defaultdict(dict)

# ==================== TRIVIA QUESTIONS ====================
TRIVIA_QUESTIONS = [
    {"question": "What is the capital of France?", "options": ["A) London", "B) Paris", "C) Berlin", "D) Madrid"], "answer": "B", "correct_text": "Paris"},
    {"question": "Which planet is known as the Red Planet?", "options": ["A) Venus", "B) Mars", "C) Jupiter", "D) Saturn"], "answer": "B", "correct_text": "Mars"},
    {"question": "What is 2 + 2?", "options": ["A) 3", "B) 4", "C) 5", "D) 6"], "answer": "B", "correct_text": "4"},
    {"question": "Which is the largest ocean?", "options": ["A) Atlantic", "B) Indian", "C) Pacific", "D) Arctic"], "answer": "C", "correct_text": "Pacific"},
    {"question": "Who painted the Mona Lisa?", "options": ["A) Van Gogh", "B) Leonardo da Vinci", "C) Michelangelo", "D) Raphael"], "answer": "B", "correct_text": "Leonardo da Vinci"},
]

QUIZ_QUESTIONS = [
    {"question": "What is our server called?", "options": ["A) Gaming Hub", "B) ZomyHub", "C) Discord Central", "D) Bot Server"], "answer": "B", "correct_text": "ZomyHub"},
    {"question": "How do you earn Robux in this server?", "options": ["A) Only by inviting", "B) Messages, invites, and daily claims", "C) Games only", "D) Buying them"], "answer": "B", "correct_text": "Messages, invites, and daily claims"},
    {"question": "What is the daily reward amount?", "options": ["A) R1", "B) R5", "C) R10", "D) R20"], "answer": "B", "correct_text": "R5"},
]

# ==================== DEFAULT AI RESPONSES ====================
DEFAULT_AI_RESPONSES = {
    "how do i earn": [f"You can earn Robux by:\n1. **Messages** (+{ROBUX_ICON}0.5 each)\n2. **Invites** (+{ROBUX_ICON}10 each)\n3. **Daily** (+{ROBUX_ICON}5)\n4. **Games** (Win big!)\n5. **Trivia** (+{ROBUX_ICON}0.25)\n\nUse `!announcements` for more! 💰"],
    "how to earn": [f"You can earn Robux by:\n1. **Messages** (+{ROBUX_ICON}0.5 each)\n2. **Invites** (+{ROBUX_ICON}10 each)\n3. **Daily** (+{ROBUX_ICON}5)\n4. **Games** (Win big!)\n5. **Trivia** (+{ROBUX_ICON}0.25)\n\nUse `!announcements` for more! 💰"],
    "how do i withdraw": [f"To withdraw:\n1. Have 50+ balance\n2. Use `!withdraw <amount> <gamepass_id>`\n3. Wait for approval\n4. Check Roblox!\n\nUse `!help` for more! 💸"],
    "hi": ["Hello! 👋 Welcome! Type `!help` to get started! 💰"],
    "hello": ["Hey there! 👋 Need help? Type `!help`! 💬"],
}

# ==================== HELPER FUNCTIONS ====================

async def get_ai_response(message_content: str) -> Optional[str]:
    """Get AI response"""
    message_lower = message_content.lower().strip()
    custom_answer = await get_ai_response_by_question(message_lower)
    if custom_answer:
        return custom_answer
    if message_lower in DEFAULT_AI_RESPONSES:
        return random.choice(DEFAULT_AI_RESPONSES[message_lower])
    return None

def parse_duration(duration_str):
    """Parse duration strings like '1d', '2h', '30m', '60s'"""
    duration_str = duration_str.lower().strip()
    
    if duration_str.endswith('d'):
        return int(duration_str[:-1]) * 86400
    elif duration_str.endswith('h'):
        return int(duration_str[:-1]) * 3600
    elif duration_str.endswith('m'):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith('s'):
        return int(duration_str[:-1])
    else:
        try:
            return int(duration_str)
        except:
            return None

async def check_game_cooldown(user_id, cooldown_seconds=None):
    """Check game cooldown"""
    if cooldown_seconds is None:
        cooldown_seconds = await get_game_cooldown()
    
    current_time = datetime.now()
    
    if user_id in game_cooldowns:
        last_game_time = game_cooldowns[user_id]
        time_diff = (current_time - last_game_time).total_seconds()
        
        if time_diff < cooldown_seconds:
            remaining = cooldown_seconds - int(time_diff)
            minutes = remaining // 60
            seconds = remaining % 60
            if minutes > 0:
                return False, f"⏳ Wait **{minutes}m {seconds}s**!"
            else:
                return False, f"⏳ Wait **{seconds}s**!"
    
    game_cooldowns[user_id] = current_time
    return True, None

async def check_message_cooldown(user_id, cooldown_seconds=None):
    """Check message cooldown"""
    if cooldown_seconds is None:
        cooldown_seconds = await get_msg_cooldown()
    
    current_time = datetime.now()
    
    if user_id in message_cooldowns:
        last_msg_time = message_cooldowns[user_id]
        time_diff = (current_time - last_msg_time).total_seconds()
        
        if time_diff < cooldown_seconds:
            return False, time_diff
    
    message_cooldowns[user_id] = current_time
    return True, 0

async def cache_invites():
    """Cache invites"""
    global invite_cache
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            invite_cache[guild.id] = {invite.code: invite.uses for invite in invites}
        except:
            pass

async def get_account_age_days(user):
    """Get account age in days"""
    created_at = user.created_at
    age = (datetime.now(created_at.tzinfo) - created_at).days
    return age

async def detect_alt_account(user):
    """Detect if account is alt"""
    age_days = await get_account_age_days(user)
    flags = []
    if age_days < 7:
        flags.append("⚠️ Account < 7 days old")
    if user.default_avatar:
        flags.append("⚠️ Default avatar")
    if not user.avatar:
        flags.append("⚠️ No avatar")
    return len(flags) >= 2, flags

# ==================== SELECT MENUS ====================

class HelpSelect(discord.ui.Select):
    """Help menu select"""
    def __init__(self):
        options = [
            discord.SelectOption(label="💰 Economy", value="economy", description="Earn and manage Robux"),
            discord.SelectOption(label="🛍️ Shop", value="shop", description="Buy items and roles"),
            discord.SelectOption(label="🎭 RP System", value="rp", description="Roleplay and rank up"),
            discord.SelectOption(label="👨‍💼 Staff", value="staff", description="Staff promotions"),
            discord.SelectOption(label="🎰 Games", value="games", description="Play games and win"),
            discord.SelectOption(label="📚 Learning", value="learning", description="Trivia and quests"),
            discord.SelectOption(label="⭐ Vouches", value="vouches", description="Leave reviews"),
            discord.SelectOption(label="💸 Withdraw", value="withdraw", description="Withdraw Robux"),
            discord.SelectOption(label="🎉 Giveaways", value="giveaway", description="Giveaway system"),
            discord.SelectOption(label="🔊 Voice", value="voice", description="Voice earning"),
            discord.SelectOption(label="🎫 Tickets", value="tickets", description="Support tickets"),
            discord.SelectOption(label="🤖 AI", value="ai", description="AI assistant"),
            discord.SelectOption(label="⚙️ Admin", value="admin", description="Admin commands"),
        ]
        super().__init__(placeholder="Choose category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        
        if value == "economy":
            embed = discord.Embed(
                title="💰 Economy Commands",
                color=discord.Color.gold(),
                description="Earn and manage your Robux!"
            )
            embed.add_field(name="🎁 `!daily`", value="Claim daily reward (+5 Robux)", inline=False)
            embed.add_field(name="💼 `!wallet [member]`", value="View wallet with stats", inline=False)
            embed.add_field(name="💵 `!balance [member]`", value="Check balance", inline=False)
            embed.add_field(name="📊 `!stats [member]`", value="View earning stats", inline=False)
            embed.add_field(name="👤 `!profile [member] [field] [value]`", value="View/edit profile", inline=False)
            embed.add_field(name="💸 `!give <@member> <amount>`", value="Give Robux (20% tax, need 3000+ msgs)", inline=False)
            embed.add_field(name="📈 `!invites [member]`", value="View invites", inline=False)
            embed.add_field(name="📱 `!m [member]`", value="View message counts", inline=False)
            embed.add_field(name="⏰ `!countdown`", value="Check next rewards", inline=False)
            embed.add_field(name="📣 `!announcements`", value="View earning ways", inline=False)
            embed.set_footer(text="Type !help to use this menu again")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "shop":
            embed = discord.Embed(
                title="🛍️ Shop Commands",
                color=discord.Color.gold(),
                description="Buy and sell items!"
            )
            embed.add_field(name="🛒 `!shop`", value="View all items", inline=False)
            embed.add_field(name="💳 `!buy <item_id>`", value="Purchase an item", inline=False)
            embed.add_field(name="➕ `!addshop <name> <type> <price> [@role]`", value="**Owner** - Add item", inline=False)
            embed.add_field(name="❌ `!delshop <item_id>`", value="**Owner** - Remove item", inline=False)
            embed.add_field(name="📋 `!msgroles`", value="View message roles", inline=False)
            embed.add_field(name="🔧 `!setmsgrole <messages> <@role>`", value="**Admin** - Set auto role", inline=False)
            embed.add_field(name="🗑️ `!delmsgrole <role_id>`", value="**Admin** - Remove role", inline=False)
            embed.set_footer(text="Message roles auto-assign at milestones!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "rp":
            embed = discord.Embed(
                title="🎭 RP Commands",
                color=discord.Color.purple(),
                description="Roleplay and rank up!"
            )
            embed.add_field(name="🎭 `!rp [member]`", value="Check your rank", inline=False)
            embed.add_field(name="👑 `!roles`", value="View all ranks", inline=False)
            embed.add_field(name="➕ `!role \"name\" <messages> [salary]`", value="**Owner** - Add role", inline=False)
            embed.add_field(name="❌ `!delrole <role_id>`", value="**Owner** - Remove role", inline=False)
            embed.add_field(name="📍 `!setrpchannel [#channel]`", value="**Admin** - Set RP channel", inline=False)
            embed.add_field(name="🗑️ `!delrpchannel [#channel]`", value="**Admin** - Remove RP channel", inline=False)
            embed.set_footer(text="Message in RP channels to gain XP!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "staff":
            embed = discord.Embed(
                title="👨‍💼 Staff Commands",
                color=discord.Color.blue(),
                description="Manage staff!"
            )
            embed.add_field(name="⭐ `!staff <@member>`", value=f"Promote staff (+{ROBUX_ICON}50 reward)", inline=False)
            embed.add_field(name="📊 `!staffstats [member]`", value="View staff stats", inline=False)
            embed.add_field(name="👑 `!staffrole <@role>`", value="**Owner** - Set staff role", inline=False)
            embed.add_field(name="🔐 `!reqstaff <@role>`", value="**Owner** - Set requirement", inline=False)
            embed.set_footer(text="Promote members to earn!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "games":
            embed = discord.Embed(
                title="🎰 Games Commands",
                color=discord.Color.red(),
                description="Play games! (2min cooldown)"
            )
            embed.add_field(name="🎲 `!dice <amount>`", value="Dice - 2% win, 3x payout (1-30)", inline=False)
            embed.add_field(name="🎡 `!roulette <amount> <red|black>`", value="Roulette - 15% win, 1.5x (1-40)", inline=False)
            embed.add_field(name="🎰 `!slots <amount>`", value="Slots - Ultra rare (1-25)", inline=False)
            embed.add_field(name="🌟 `!lucky <amount>`", value="Lucky - 30% win, variable (1-35)", inline=False)
            embed.add_field(name="💰 `!icf <amount>`", value="Coinflip - 5% win, 1.8x (1-50)", inline=False)
            embed.add_field(name="🎡 `!spin`", value="Daily spin - Once per 24h (1-5)", inline=False)
            embed.add_field(name="📊 `!gamestats [member]`", value="View game stats", inline=False)
            embed.set_footer(text="⚠️ Games are VERY HARD!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "learning":
            embed = discord.Embed(
                title="📚 Learning Commands",
                color=discord.Color.blue(),
                description="Learn and have fun!"
            )
            embed.add_field(name="🧠 `!trivia`", value=f"Trivia - +{ROBUX_ICON}0.25 correct, -{ROBUX_ICON}0.25 wrong", inline=False)
            embed.add_field(name="📚 `!quiz`", value="Fun quiz (no rewards)", inline=False)
            embed.add_field(name="👤 `!profile [member] [field] [value]`", value="Edit profile (bio, game, color, social)", inline=False)
            embed.add_field(name="📋 `!quest`", value="View message quest", inline=False)
            embed.add_field(name="🔗 `!referral [member]`", value="View referral code", inline=False)
            embed.add_field(name="🎓 `!accountage [member]`", value="Check account age", inline=False)
            embed.set_footer(text="Keep learning!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "vouches":
            embed = discord.Embed(
                title="⭐ Vouch Commands",
                color=discord.Color.gold(),
                description="Leave reviews!"
            )
            embed.add_field(name="⭐ `!vouch <rating 1-5> <comment>`", value="Leave a vouch", inline=False)
            embed.add_field(name="📜 `!vouches`", value="View all vouches", inline=False)
            embed.add_field(name="🔧 `!setvouchchannel [#channel]`", value="**Owner** - Set vouch channel", inline=False)
            embed.set_footer(text="Vouches help the community!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "withdraw":
            embed = discord.Embed(
                title="💸 Withdrawal Commands",
                color=discord.Color.green(),
                description="Withdraw your Robux!"
            )
            embed.add_field(name="💸 `!withdraw <robux> <gamepass_id>`", value="Request withdrawal (50+ min, 70-80 per tx)", inline=False)
            embed.add_field(name="📜 `!withdrawhistory [member]`", value="View withdrawal history", inline=False)
            embed.add_field(name="📋 `!withdrawals`", value="**Owner** - View pending", inline=False)
            embed.add_field(name="✅ `!paid <@member> <amount>`", value="**Owner** - Approve", inline=False)
            embed.add_field(name="❌ `!denywithdraw <@member> [reason]`", value="**Owner** - Deny", inline=False)
            embed.add_field(name="🔓 `!openwithdraw`", value="**Owner** - Open withdrawals", inline=False)
            embed.add_field(name="🔒 `!closewithdraw`", value="**Owner** - Close withdrawals", inline=False)
            embed.add_field(name="📊 `!withdrawstatus`", value="Check status", inline=False)
            embed.add_field(name="💾 `!setwithdrawdaily <amount>`", value="**Owner** - Set daily limit", inline=False)
            embed.set_footer(text="Set your withdrawal limit!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "giveaway":
            embed = discord.Embed(
                title="🎉 Giveaway Commands",
                color=discord.Color.from_rgb(255, 215, 0),
                description="Create giveaways!"
            )
            embed.add_field(name="🎉 `!giveaway <duration> <count> <prize>`", value="Start giveaway (1d, 2h, 30m, 60s)", inline=False)
            embed.add_field(name="🎟️ `!genter`", value="Enter giveaway", inline=False)
            embed.add_field(name="📊 `!gstatus`", value="Check giveaway status", inline=False)
            embed.set_footer(text="Winners picked automatically!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "voice":
            embed = discord.Embed(
                title="🔊 Voice Commands",
                color=discord.Color.from_rgb(100, 200, 255),
                description="Earn in voice channels!"
            )
            embed.add_field(name="🔊 `!vcrate`", value="Check VC earning rate", inline=False)
            embed.add_field(name="📊 `!vcstats [member]`", value="View voice earnings", inline=False)
            embed.add_field(name="⏱️ `!setvcrate <amount>`", value="**Owner** - Set rate per 5min", inline=False)
            embed.add_field(name="🟢 `!vcenabled <on/off>`", value="**Owner** - Enable/disable", inline=False)
            embed.set_footer(text="Earn while talking!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "tickets":
            embed = discord.Embed(
                title="🎫 Ticket Commands",
                color=discord.Color.from_rgb(100, 150, 255),
                description="Support tickets!"
            )
            embed.add_field(name="🎫 `!ticket`", value="Create ticket", inline=False)
            embed.add_field(name="❌ `!closeticket`", value="Close your ticket", inline=False)
            embed.add_field(name="📜 `!transcript`", value="Get chat transcript", inline=False)
            embed.add_field(name="🔧 `!setuptickets <#category> <@role>`", value="**Owner** - Setup", inline=False)
            embed.set_footer(text="Support will help soon!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "ai":
            embed = discord.Embed(
                title="🤖 AI Commands",
                color=discord.Color.from_rgb(100, 200, 255),
                description="AI responses!"
            )
            embed.add_field(name="🤖 `!ai <question>`", value="Ask AI anything", inline=False)
            embed.add_field(name="➕ `!addai <question> | <answer>`", value="**Owner** - Add response", inline=False)
            embed.add_field(name="❌ `!delai <question>`", value="**Owner** - Remove response", inline=False)
            embed.add_field(name="📋 `!ailist`", value="View all responses", inline=False)
            embed.add_field(name="🟢 `!aienabled <on/off>`", value="**Owner** - Enable/disable", inline=False)
            embed.set_footer(text="Ask me anything!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif value == "admin":
            embed = discord.Embed(
                title="⚙️ Admin Commands",
                color=discord.Color.red(),
                description="Server administration"
            )
            embed.add_field(name="🚫 `!ban <@member>`", value="**Owner** - Ban from bot", inline=False)
            embed.add_field(name="✅ `!unban <@member>`", value="**Owner** - Unban user", inline=False)
            embed.add_field(name="💰 `!addmoney <@member> <amount>`", value="**Owner** - Add Robux", inline=False)
            embed.add_field(name="💸 `!delmoney <@member> <amount>`", value="**Owner** - Remove Robux", inline=False)
            embed.add_field(name="🎯 `!setrate <type> <value>`", value="**Owner** - Set rates", inline=False)
            embed.add_field(name="💾 `!resetball [member]`", value="**Owner** - Reset balance", inline=False)
            embed.add_field(name="📝 `!welcome <on|off> <#channel> [message]`", value="**Owner** - Welcome system", inline=False)
            embed.add_field(name="👨 `!autorole <@role>`", value="**Owner** - Auto-assign role", inline=False)
            embed.add_field(name="🚫 `!addword <word>`", value="**Owner** - Blacklist word", inline=False)
            embed.add_field(name="✅ `!removeword <word>`", value="**Owner** - Unblacklist word", inline=False)
            embed.add_field(name="📋 `!blacklist`", value="**Owner** - View blacklist", inline=False)
            embed.add_field(name="👨‍💼 `!addadmin <@member>`", value="**Owner** - Add bot admin", inline=False)
            embed.add_field(name="❌ `!deladmin <@member>`", value="**Owner** - Remove bot admin", inline=False)
            embed.add_field(name="📊 `!admins`", value="**Owner** - View admins", inline=False)
            embed.add_field(name="📧 `!setlog [#channel]`", value="**Owner** - Set log channel", inline=False)
            embed.add_field(name="📊 `!status`", value="View bot status", inline=False)
            embed.add_field(name="⏳ `!setgamecooldown <seconds>`", value="**Owner** - Set cooldown", inline=False)
            embed.add_field(name="⏳ `!setmsgcooldown <seconds>`", value="**Owner** - Set msg cooldown", inline=False)
            embed.add_field(name="⚠️ `!warn <@member> [reason]`", value="**Mod** - Warn user", inline=False)
            embed.add_field(name="📋 `!warnings <@member>`", value="**Mod** - View warnings", inline=False)
            embed.add_field(name="🗑️ `!delwarning <@member> <warn_id>`", value="**Mod** - Delete warning", inline=False)
            embed.set_footer(text="Use carefully!")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class HelpView(discord.ui.View):
    """Help view"""
    def __init__(self):
        super().__init__()
        self.add_item(HelpSelect())

# ==================== BUTTONS & MODALS ====================

class WithdrawPanel(discord.ui.View):
    """Withdrawal panel"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Withdraw Robux", style=discord.ButtonStyle.green, custom_id="withdraw_btn")
    async def withdraw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WithdrawModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Withdraw History", style=discord.ButtonStyle.gray, custom_id="history_btn")
    async def history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = await get_withdraw_history(interaction.user.id)
        if not history:
            await interaction.response.send_message("No history", ephemeral=True)
            return
        
        embed = discord.Embed(title="📋 Withdrawal History", color=discord.Color.blue())
        for item in history[:10]:
            status_emoji = "✅" if item[2] == "paid" else "⏳"
            embed.add_field(
                name=f"ID: #{item[0]}", 
                value=f"{ROBUX_ICON}{item[1]}\n{status_emoji} {item[2]}", 
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Withdrawal Limit", style=discord.ButtonStyle.blurple, custom_id="limit_btn")
    async def limit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = await get_user_data(interaction.user.id)
        if not user:
            await interaction.response.send_message("No data", ephemeral=True)
            return
        
        global_limit = await get_global_withdraw_limit()
        
        embed = discord.Embed(title="💸 Your Limits", color=discord.Color.blue())
        embed.add_field(name="Balance", value=f"{ROBUX_ICON}{user[2]:.2f}", inline=True)
        embed.add_field(name="Min Required", value=f"{ROBUX_ICON}50", inline=True)
        embed.add_field(name="Max Per TX", value=f"{ROBUX_ICON}{global_limit}", inline=True)
        embed.add_field(name="Status", value="🟢 Open" if await get_withdrawal_status() else "🔴 Closed", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WithdrawModal(discord.ui.Modal):
    """Withdrawal modal"""
    def __init__(self):
        super().__init__(title="Withdraw Robux")
        self.amount_input = discord.ui.TextInput(
            label="Amount to Withdraw",
            placeholder="Min: 5",
            min_length=1,
            max_length=10,
            style=discord.TextStyle.short,
            required=True
        )
        self.gamepass_input = discord.ui.TextInput(
            label="Gamepass ID",
            placeholder="Your Roblox Gamepass ID",
            min_length=5,
            max_length=20,
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.amount_input)
        self.add_item(self.gamepass_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt_str = self.amount_input.value
            gp_id = self.gamepass_input.value
            amt = float(amt_str)
            
            if not is_authorized_guild(interaction.guild.id):
                await interaction.response.send_message("❌ Not authorized", ephemeral=True)
                return
            
            user = await get_user_data(interaction.user.id)
            if not user or user[2] < 50:
                await interaction.response.send_message(f"❌ Need 50+ {ROBUX_ICON}", ephemeral=True)
                return

            if amt < 5:
                await interaction.response.send_message(f"❌ Min is 5 {ROBUX_ICON}", ephemeral=True)
                return

            limit = await get_global_withdraw_limit()
            if amt > limit:
                await interaction.response.send_message(f"❌ Max is {ROBUX_ICON}{limit}", ephemeral=True)
                return

            if user[2] < amt:
                await interaction.response.send_message("❌ Insufficient balance", ephemeral=True)
                return

            wid = await create_withdrawal(interaction.user.id, interaction.user.name, amt, gp_id)
            await subtract_robux(interaction.user.id, amt)
            await add_withdraw_history(interaction.user.id, amt, "pending")

            await interaction.response.send_message(f"✅ Request #{wid} submitted for {ROBUX_ICON}{amt}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount", ephemeral=True)

# ==================== BACKGROUND TASKS ====================

@tasks.loop(seconds=10)
async def check_giveaways():
    """Check and end giveaways"""
    try:
        async with aiosqlite.connect("bot_data.db", timeout=20) as db:
            cursor = await db.execute(
                'SELECT giveaway_id, guild_id, host_id, prize, prize_count, message_id FROM giveaways WHERE status = "active"'
            )
            active_giveaways = await cursor.fetchall()
        
        for giveaway in active_giveaways:
            giveaway_id, guild_id, host_id, prize, prize_count, message_id = giveaway
            ga = await get_giveaway(giveaway_id)
            if ga:
                ends_at = datetime.fromisoformat(ga[7])
                
                if datetime.now() >= ends_at:
                    entries = await get_giveaway_entries(giveaway_id)
                    
                    if entries:
                        winners = random.sample(entries, min(int(prize_count), len(entries)))
                        winners_str = ",".join(map(str, winners))
                        
                        await set_giveaway_winners(giveaway_id, winners_str)
                        
                        try:
                            guild = bot.get_guild(guild_id)
                            if guild and message_id:
                                try:
                                    channel = guild.text_channels[0] if guild.text_channels else None
                                    if channel:
                                        embed = discord.Embed(
                                            title="🎉 GIVEAWAY ENDED",
                                            description=f"**Prize:** {prize}",
                                            color=discord.Color.gold()
                                        )
                                        embed.add_field(name="🏆 Winners", value="\n".join([f"<@{w}>" for w in winners]), inline=False)
                                        embed.add_field(name="👥 Entries", value=str(len(entries)), inline=True)
                                        
                                        await channel.send(content=" ".join([f"<@{w}>" for w in winners]), embed=embed)
                                except:
                                    pass
                        except:
                            pass
                        
                        print(f"✅ Giveaway {giveaway_id} ended")
    except Exception as e:
        print(f"Error in check_giveaways: {e}")

@tasks.loop(seconds=30)
async def process_voice_sessions():
    """Track voice channel earnings"""
    now = datetime.now()
    try:
        for guild in bot.guilds:
            try:
                if not is_authorized_guild(guild.id):
                    continue
                
                enabled = await get_vc_enabled(guild.id)
                if not enabled:
                    continue
                
                vc_rate = await get_vc_rate(guild.id)
                
                for member in guild.members:
                    if member.bot:
                        continue
                    
                    voice = member.voice
                    if not voice or not voice.channel:
                        continue
                    if voice.self_deaf or voice.self_mute:
                        continue
                    
                    uid = member.id
                    guild_id = guild.id
                    
                    session = await get_active_vc_session(uid, guild_id)
                    if not session:
                        sid = await start_vc_session(uid, guild_id, voice.channel.id)
                        if guild_id not in user_vc_states:
                            user_vc_states[guild_id] = {}
                        user_vc_states[guild_id][uid] = {
                            'session_id': sid,
                            'join_time': now,
                            'last_award_time': now
                        }
                    else:
                        join_time = datetime.fromisoformat(session[2])
                        
                        if guild_id in user_vc_states and uid in user_vc_states[guild_id]:
                            last_awarded = user_vc_states[guild_id][uid].get('last_award_time')
                            if last_awarded:
                                time_since_last = (now - last_awarded).total_seconds()
                                if time_since_last >= 300:
                                    reward = vc_rate
                                    await add_vc_earnings(uid, guild_id, reward, 300)
                                    user_vc_states[guild_id][uid]['last_award_time'] = now
            except Exception as e:
                print(f"Error processing voice for guild {guild.id}: {e}")
    except Exception as e:
        print(f"Error in process_voice_sessions: {e}")

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    """Bot ready event"""
    print(f'✅ Bot logged in as {bot.user}')
    print(f'📊 Connected to {len(bot.guilds)} servers')
    
    # Initialize all tables
    await init_db()
    await init_rates_table()
    await init_rp_tables()
    await init_staff_table()
    await init_moderation_tables()
    await init_withdrawal_limit_table()
    await init_game_history_table()
    await init_lucky_spin_table()
    await init_withdraw_history_table()
    await init_message_tracking_table()
    await init_logs_table()
    await init_alt_detection_table()
    await init_staff_promotions_table()
    await init_withdrawal_status_table()
    await init_staff_role_table()
    await init_staff_req_role_table()
    await init_ai_config_table()
    await init_ai_responses_table()
    await init_spin_table()
    await init_quest_table()
    await init_profile_table()
    await init_referral_table()
    await init_trivia_table()
    await init_welcome_table()
    await init_blacklist_table()
    await init_autorole_table()
    await init_shop_table()
    await init_message_role_table()
    await init_bot_admin_table()
    await init_bot_settings_table()
    await init_msg_req_role_table()
    await init_giveaway_table()
    await init_vc_tables()
    await init_ticket_tables()
    await init_vouch_table()
    await init_tip_table()
    
    await cache_invites()
    
    check_giveaways.start()
    process_voice_sessions.start()
    
    cooldown = await get_game_cooldown()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"🎉 Type !help | 💰 Earn {ROBUX_ICON} | {cooldown}s Cooldown"))

@bot.event
async def on_member_join(member):
    """Member join event"""
    await asyncio.sleep(2)
    try:
        guild = member.guild
        if not is_authorized_guild(guild.id):
            return
        
        # Auto-role
        autorole_id = await get_autorole(guild.id)
        if autorole_id:
            try:
                autorole = guild.get_role(autorole_id)
                if autorole:
                    await member.add_roles(autorole)
                    print(f"✅ {member.name} got auto-role")
            except Exception as e:
                print(f"⚠️ Auto-role failed: {e}")
        
        # Welcome message
        welcome_config = await get_welcome_config(guild.id)
        if welcome_config and welcome_config[2]:
            channel_id, message, enabled = welcome_config
            try:
                channel = guild.get_channel(channel_id)
                if channel:
                    welcome_msg = message.replace("{user}", member.mention).replace("{guild}", guild.name).replace("{count}", str(guild.member_count))
                    embed = discord.Embed(
                        title="🎉 Welcome to the Server!",
                        description=welcome_msg,
                        color=discord.Color.from_rgb(100, 200, 255)
                    )
                    embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
                    embed.add_field(name="👤 Member #", value=f"{guild.member_count}", inline=True)
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Welcome message failed: {e}")
        
        # Invite tracking
        if guild.id not in invite_cache:
            current_invites = await guild.invites()
            invite_cache[guild.id] = {invite.code: invite.uses for invite in current_invites}
            return
        
        current_invites = await guild.invites()
        invite_rate = await get_rate('invite_rate')
        
        for invite in current_invites:
            old_uses = invite_cache[guild.id].get(invite.code, 0)
            new_uses = invite.uses
            if new_uses > old_uses and invite.inviter:
                inviter_id = invite.inviter.id
                inviter_name = invite.inviter.name
                await create_user(inviter_id, inviter_name)
                await create_user(member.id, member.name)
                await add_invite(inviter_id, member.id, invite_rate)
                print(f"✅ {inviter_name} invited {member.name} | +{ROBUX_ICON}{invite_rate}")
                try:
                    inviter = await bot.fetch_user(inviter_id)
                    embed = discord.Embed(
                        title="🎉 Invite Successful!",
                        description=f"You invited **{member.name}**!",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="💰 Earned", value=f"**{ROBUX_ICON}{invite_rate}**", inline=False)
                    await inviter.send(embed=embed)
                except:
                    pass
                break
        
        invite_cache[guild.id] = {invite.code: invite.uses for invite in current_invites}
    except Exception as e:
        print(f"Error in on_member_join: {e}")

@bot.event
async def on_message(message):
    """Message event"""
    if message.author.bot:
        return
    
    if not is_authorized_guild(message.guild.id):
        return
    
    try:
        # Blacklist check
        blacklist = await get_blacklist_words(message.guild.id)
        content_lower = message.content.lower()
        
        for word_tuple in blacklist:
            word = word_tuple[0]
            if word in content_lower:
                try:
                    await message.delete()
                    embed = discord.Embed(
                        title="🚫 Message Deleted",
                        description=f"Contained blacklisted word: `{word}`",
                        color=discord.Color.red()
                    )
                    await message.author.send(embed=embed)
                except:
                    pass
                return
        
        # Message earnings
        is_msg_channel = await is_message_channel(message.channel.id)
        if is_msg_channel:
            await create_user(message.author.id, message.author.name)
            
            msg_req_role = await get_msg_req_role(message.guild.id)
            can_earn = False
            
            if msg_req_role:
                role = message.guild.get_role(msg_req_role)
                if role and role in message.author.roles:
                    can_earn = True
            else:
                can_earn = True
            
            if can_earn:
                is_cooldown_ok, _ = await check_message_cooldown(message.author.id)
                if is_cooldown_ok:
                    message_rate = await get_rate('message_rate')
                    await add_message(message.author.id, message_rate)
                    print(f"✅ {message.author.name} earned {ROBUX_ICON}{message_rate}")
        
        # RP tracking
        is_rp_ch = await is_rp_channel(message.channel.id)
        if is_rp_ch:
            await create_user(message.author.id, message.author.name)
            await init_user_rp(message.author.id)
            leveled_up, new_level = await add_rp_message(message.author.id)
            
            if leveled_up and new_level > 0:
                role_data = await get_rp_role_by_id(new_level)
                if role_data:
                    role_name = role_data[1]
                    salary = role_data[3]
                    
                    discord_role = discord.utils.get(message.guild.roles, name=role_name)
                    
                    if discord_role:
                        try:
                            all_rp_roles = await get_rp_roles()
                            roles_to_remove = []
                            for r_data in all_rp_roles:
                                r_obj = discord.utils.get(message.guild.roles, name=r_data[1])
                                if r_obj and r_obj in message.author.roles and r_obj.id != discord_role.id:
                                    roles_to_remove.append(r_obj)
                            
                            if roles_to_remove:
                                await message.author.remove_roles(*roles_to_remove)
                            
                            await message.author.add_roles(discord_role)
                        except Exception as e:
                            print(f"Failed to assign RP role: {e}")
                    
                    try:
                        image_path = create_level_up_image(message.author.name, message.author.avatar.url if message.author.avatar else "", role_name, salary)
                        if os.path.exists(image_path):
                            with open(image_path, 'rb') as f:
                                await message.reply(file=discord.File(f, filename=image_path), mention_author=False)
                        else:
                            embed = discord.Embed(
                                title="🎉 LEVEL UP!",
                                description=f"You've been promoted to **{role_name}**!",
                                color=discord.Color.gold()
                            )
                            embed.add_field(name="💰 Salary", value=f"{ROBUX_ICON}{salary}", inline=True)
                            await message.reply(embed=embed, mention_author=False)
                    except Exception as e:
                        print(f"Image generation failed: {e}")
                        embed = discord.Embed(
                            title="🎉 LEVEL UP!",
                            description=f"You've been promoted to **{role_name}**!",
                            color=discord.Color.gold()
                        )
                        embed.add_field(name="💰 Salary", value=f"{ROBUX_ICON}{salary}", inline=True)
                        await message.reply(embed=embed, mention_author=False)
                    
                    print(f"🎭 {message.author.name} leveled up to {role_name}")
        
        # AI responses
        ai_enabled = await get_ai_status()
        if ai_enabled and not message.content.startswith("!"):
            ai_response = await get_ai_response(message.content)
            if ai_response:
                embed = discord.Embed(
                    title="🤖 AI Assistant",
                    description=ai_response,
                    color=discord.Color.from_rgb(100, 200, 255)
                )
                try:
                    await message.reply(embed=embed, mention_author=False)
                except:
                    pass
    
    except Exception as e:
        print(f"Error in on_message: {e}")
    
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    """Voice state update event"""
    try:
        guild_id = member.guild.id
        if not is_authorized_guild(guild_id):
            return
        
        uid = member.id
        
        # User left VC
        if before.channel and not after.channel:
            session = await get_active_vc_session(uid, guild_id)
            if session:
                join_time = datetime.fromisoformat(session[2])
                leave_time = datetime.now()
                seconds = int((leave_time - join_time).total_seconds())
                vc_rate = await get_vc_rate(guild_id)
                groups = seconds // 300
                reward = vc_rate * groups if groups > 0 else 0
                
                await end_vc_session(session[0], seconds, reward)
                if reward > 0:
                    await add_vc_earnings(uid, guild_id, reward, seconds)
            
            if guild_id in user_vc_states and uid in user_vc_states[guild_id]:
                user_vc_states[guild_id].pop(uid, None)
        
        # User joined VC
        elif after.channel and (before.channel != after.channel):
            enabled = await get_vc_enabled(guild_id)
            if enabled:
                recent = await get_recent_vc_session(uid, guild_id)
                if recent and recent[3]:
                    leave_time = datetime.fromisoformat(recent[3])
                    time_since_leave = (datetime.now() - leave_time).total_seconds()
                    if time_since_leave <= 300:
                        session_id = await start_vc_session(uid, guild_id, after.channel.id)
                        if guild_id not in user_vc_states:
                            user_vc_states[guild_id] = {}
                        user_vc_states[guild_id][uid] = {
                            'session_id': session_id,
                            'join_time': datetime.now(),
                            'last_award_time': datetime.now()
                        }
                        return
                
                session_id = await start_vc_session(uid, guild_id, after.channel.id)
                if guild_id not in user_vc_states:
                    user_vc_states[guild_id] = {}
                user_vc_states[guild_id][uid] = {
                    'session_id': session_id,
                    'join_time': datetime.now(),
                    'last_award_time': datetime.now()
                }
    except Exception as e:
        print(f"Error in on_voice_state_update: {e}")

@bot.event
async def on_reaction_add(reaction, user):
    """Reaction add event"""
    if user.bot:
        return
    
    if reaction.emoji != "🎉":
        return
    
    try:
        if not is_authorized_guild(reaction.message.guild.id):
            return
        
        giveaway = await get_active_giveaway(reaction.message.guild.id)
        
        if not giveaway or giveaway[8] != reaction.message.id:
            return
        
        giveaway_id = giveaway[0]
        
        already_entered = await user_in_giveaway(giveaway_id, user.id)
        if already_entered:
            return
        
        await add_giveaway_entry(giveaway_id, user.id)
        print(f"✅ {user.name} entered giveaway {giveaway_id}")
        
    except Exception as e:
        print(f"Error in on_reaction_add: {e}")

# ==================== HELP COMMAND ====================

@bot.command(name='help', aliases=['commands', 'h'])
async def help_command(ctx):
    """Get help menu"""
    if not is_authorized_guild(ctx.guild.id):
        return
    
    embed = discord.Embed(
        title="✨ ZomyHub Premium Dashboard",
        description="Welcome to the next generation of Robux management. Select a module below to begin.",
        color=discord.Color.from_rgb(100, 200, 255)
    )
    
    await ctx.send(embed=embed, view=HelpView())
    await log_command(ctx.author.id, ctx.author.name, "help", "", True)

# ==================== ECONOMY COMMANDS ====================

@bot.command(name='daily')
async def daily(ctx):
    """Claim daily reward"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        banned = await is_user_banned(user_id)
        if banned:
            embed = discord.Embed(title="🚫 Banned", description="You are banned!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        user = await get_user_data(user_id)
        daily_reward = await get_rate('daily_reward')
        today = str(date.today())
        
        if user and user[8] == today:
            embed = discord.Embed(
                title="⏰ Already Claimed",
                description="Come back tomorrow!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        success, message = await claim_daily(user_id, daily_reward)
        if success:
            try:
                image_path = create_daily_image(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", daily_reward)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="🎁 Daily Reward",
                    description=f"You got {ROBUX_ICON}{daily_reward}!",
                    color=discord.Color.gold()
                )
                await ctx.send(embed=embed)
            
            await log_command(user_id, ctx.author.name, "daily", "", True)
        else:
            embed = discord.Embed(title="❌ Error", description=message, color=discord.Color.red())
            await ctx.send(embed=embed)
            await log_command(user_id, ctx.author.name, "daily", "", False, message)
    except Exception as e:
        print(f"Error: {e}")
        await log_command(ctx.author.id, ctx.author.name, "daily", "", False, str(e))

@bot.command(name='wallet')
async def wallet(ctx, member: discord.Member = None):
    """View wallet"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        user = await get_user_data(member.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", description=f"{member.name} hasn't earned yet!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        message_rate = await get_rate('message_rate')
        invite_rate = await get_rate('invite_rate')
        message_earnings = user[6] * message_rate
        invite_earnings = user[3] * invite_rate
        lifetime_earned = message_earnings + invite_earnings
        
        try:
            image_path = create_wallet_image(member.name, member.avatar.url if member.avatar else "", user[2], user[2], user[3], user[4], user[5], user[6])
            with open(image_path, 'rb') as f:
                await ctx.send(file=discord.File(f, filename=image_path))
        except:
            embed = discord.Embed(title=f"💳 Financial Overview: {member.name}", color=discord.Color.blue())
            embed.add_field(name="Balance", value=f"{ROBUX_ICON}{user[2]:.2f}", inline=True)
            embed.add_field(name="Lifetime", value=f"{ROBUX_ICON}{lifetime_earned:.2f}", inline=True)
            embed.add_field(name="Invites", value=f"{user[3]}", inline=True)
            embed.add_field(name="Today", value=f"{user[4]} msgs", inline=True)
            embed.add_field(name="Week", value=f"{user[5]} msgs", inline=True)
            embed.add_field(name="Lifetime", value=f"{user[6]} msgs", inline=True)
            await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "wallet", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='balance', aliases=['bal'])
async def balance(ctx, member: discord.Member = None):
    """Check balance"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        user = await get_user_data(member.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"📊 Current Holdings: {member.name}",
            color=discord.Color.green()
        )
        embed.add_field(name="Robux", value=f"**{ROBUX_ICON}{user[2]:.2f}**", inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "balance", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='m')
async def messages(ctx, member: discord.Member = None):
    """View messages"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        user = await get_user_data(member.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title=f"📱 {member.name}'s Messages", color=discord.Color.blue())
        embed.add_field(name="Today", value=f"**{user[4]}**", inline=True)
        embed.add_field(name="Week", value=f"**{user[5]}**", inline=True)
        embed.add_field(name="Lifetime", value=f"**{user[6]}**", inline=True)
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "m", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")


@bot.command(name='stats')
async def stats(ctx, member: discord.Member = None):
    """View stats"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        user = await get_user_data(member.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        message_rate = await get_rate('message_rate')
        invite_rate = await get_rate('invite_rate')
        message_earnings = user[6] * message_rate
        invite_earnings = user[3] * invite_rate
        lifetime_earned = message_earnings + invite_earnings
        
        vc_seconds, vc_earned = await get_user_vc_stats(member.id, ctx.guild.id)
        vc_mins = vc_seconds // 60
        
        embed = discord.Embed(title=f"📈 Performance Analytics: {member.name}", color=discord.Color.blue())
        embed.add_field(name="💬 Message Earnings", value=f"{ROBUX_ICON}{message_earnings:.2f}", inline=True)
        embed.add_field(name="👥 Invite Earnings", value=f"{ROBUX_ICON}{invite_earnings:.2f}", inline=True)
        embed.add_field(name="🔊 VC Robux", value=f"{ROBUX_ICON}{vc_earned:.2f}", inline=True)
        embed.add_field(name="💰 Current Balance", value=f"{ROBUX_ICON}{user[2]:.2f}", inline=True)
        embed.add_field(name="📈 Lifetime Earned", value=f"{ROBUX_ICON}{lifetime_earned:.2f}", inline=True)
        embed.add_field(name="🔊 VC Time", value=f"{vc_mins//60}h {vc_mins%60}m", inline=True)
        embed.add_field(name="📱 Total Messages", value=f"**{user[6]}**", inline=True)
        embed.add_field(name="👥 Total Invites", value=f"**{user[3]}**", inline=True)
        embed.set_footer(text="🚀 Elevate your status through active participation.")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "stats", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='countdown')
async def countdown(ctx):
    """Countdown timer for next rewards"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        user = await get_user_data(user_id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        last_daily = user[8]
        today_str = str(date.today())
        
        if last_daily == today_str:
            next_daily = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            time_until = next_daily - datetime.now()
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            daily_status = f"In **{hours}h {minutes}m**"
        else:
            daily_status = "**Available now!** 💰"
        
        can_spin_now, last_spin_date = await can_spin(user_id)
        if can_spin_now:
            spin_status = "**Available now!** 🎡"
        else:
            next_spin = datetime.now() + timedelta(days=1)
            time_until_spin = next_spin - datetime.now()
            hours = int(time_until_spin.total_seconds() // 3600)
            minutes = int((time_until_spin.total_seconds() % 3600) // 60)
            spin_status = f"In **{hours}h {minutes}m**"
        
        if user_id in game_cooldowns:
            cooldown = await get_game_cooldown()
            last_game_time = game_cooldowns[user_id]
            time_diff = (datetime.now() - last_game_time).total_seconds()
            if time_diff < cooldown:
                remaining = cooldown - int(time_diff)
                minutes = remaining // 60
                seconds = remaining % 60
                game_status = f"In **{minutes}m {seconds}s** ⏳"
            else:
                game_status = "**Available now!** 🎮"
        else:
            game_status = "**Available now!** 🎮"
        
        embed = discord.Embed(
            title="⏲️ Reward Availability Schedule",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎁 Daily Reward (R5)", value=daily_status, inline=False)
        embed.add_field(name="🎡 Daily Spin (R1-5)", value=spin_status, inline=False)
        cooldown_secs = await get_game_cooldown()
        embed.add_field(name=f"🎮 Games ({cooldown_secs}s)", value=game_status, inline=False)
        embed.set_footer(text="🔄 Schedules update in real-time based on activity.")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "countdown", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='announcements')
async def announcements(ctx):
    """View announcements"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        embed = discord.Embed(
            title="💎 Revenue Generation Guide",
            description="Maximize your dividends by engaging with the community through our verified streams.",
            color=discord.Color.gold()
        )
        embed.add_field(name="💬 Send Messages", value=f"**+{ROBUX_ICON}0.5** per message\n✅ Unlimited earning!", inline=False)
        embed.add_field(name="👥 Invite Friends", value=f"**+{ROBUX_ICON}10** per invite\n✅ Share the link!", inline=False)
        embed.add_field(name="🎁 Daily Claim", value=f"**+{ROBUX_ICON}5** once per 24h\n✅ Use `!daily`!", inline=False)
        embed.add_field(name="🎡 Daily Spin", value=f"**+{ROBUX_ICON}1-5** once per 24h\n✅ Use `!spin`!", inline=False)
        embed.add_field(name="🔊 Voice Channels", value=f"**+{ROBUX_ICON}** every 5 min\n✅ Use `!vcrate`!", inline=False)
        embed.add_field(name="⭐ Trivia", value=f"**+{ROBUX_ICON}0.25** correct\n✅ Use `!trivia`!", inline=False)
        embed.add_field(name="🎮 Games", value=f"**Win big!**\n✅ Use `!dice`, `!slots`, etc!", inline=False)
        embed.add_field(name="💡 Pro Tips", value="✅ Check `!countdown` for next rewards\n✅ Check `!stats` for breakdown\n✅ Stay active and invite friends!", inline=False)
        embed.set_footer(text="Maximum activity = Maximum earnings! 💰")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "announcements", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='give')
async def give(ctx, member: discord.Member = None, amount: float = None):
    """Give Robux to another user"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None or amount is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!give <@member> <amount>`\n\nRequirements:\n• 20% tax\n• 3000+ lifetime messages",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if amount <= 0:
            embed = discord.Embed(title="❌ Error", description="Amount must be positive!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        sender = await get_user_data(ctx.author.id)
        if not sender:
            embed = discord.Embed(title="❌ No Data", description="You haven't started earning yet!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if sender[6] < 3000:
            embed = discord.Embed(
                title="❌ Not Eligible",
                description=f"You need 3000+ lifetime messages!\n\nYour messages: **{sender[6]}**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if sender[2] < amount:
            embed = discord.Embed(title="❌ Insufficient Balance", description=f"You only have {ROBUX_ICON}{sender[2]:.2f}", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await create_user(member.id, member.name)
        
        tax = amount * 0.20
        net_amount = amount - tax
        
        await subtract_robux(ctx.author.id, amount)
        await add_robux(member.id, net_amount)
        
        embed = discord.Embed(title="💸 Transaction Successful", color=discord.Color.green())
        embed.add_field(name="To", value=f"{member.mention}", inline=True)
        embed.add_field(name="Amount", value=f"{ROBUX_ICON}{amount:.2f}", inline=True)
        embed.add_field(name="Tax (20%)", value=f"{ROBUX_ICON}{tax:.2f}", inline=True)
        embed.add_field(name="Received", value=f"{ROBUX_ICON}{net_amount:.2f}", inline=True)
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "give", f"target: {member.name}, amount: {amount}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='invites')
async def invites(ctx, member: discord.Member = None):
    """View invites"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        user = await get_user_data(member.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        invite_rate = await get_rate('invite_rate')
        invite_earnings = user[3] * invite_rate
        
        embed = discord.Embed(title=f"👥 {member.name}'s Invites", color=discord.Color.blue())
        embed.add_field(name="Total Invites", value=f"**{user[3]}**", inline=True)
        embed.add_field(name="Earnings", value=f"**{ROBUX_ICON}{invite_earnings:.2f}**", inline=True)
        embed.add_field(name="Rate", value=f"**{ROBUX_ICON}{invite_rate}** per invite", inline=True)
        embed.set_footer(text="Share your invite link!")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "invites", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='profile')
async def profile(ctx, member: discord.Member = None, field: str = None, *, value: str = None):
    """View or edit profile"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        if field is None:
            profile_data = await get_profile(member.id)
            
            embed = discord.Embed(title=f"👤 {member.name}'s Profile", color=discord.Color.blue())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
            
            if profile_data:
                bio = profile_data[1] or "No bio"
                game = profile_data[2] or "Not set"
                color = profile_data[3] or "Not set"
                social = profile_data[4] or "Not set"
            else:
                bio = "No bio"
                game = "Not set"
                color = "Not set"
                social = "Not set"
            
            embed.add_field(name="📝 Bio", value=bio, inline=False)
            embed.add_field(name="🎮 Favorite Game", value=game, inline=True)
            embed.add_field(name="🎨 Favorite Color", value=color, inline=True)
            embed.add_field(name="🔗 Social Link", value=social, inline=False)
            embed.set_footer(text="Use !profile @member <field> <value> to edit")
            
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "profile", f"view: {member.name}", True)
        else:
            if ctx.author.id != member.id:
                embed = discord.Embed(title="❌ Error", description="You can only edit your own profile!", color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            field = field.lower()
            if field not in ['bio', 'game', 'color', 'social']:
                embed = discord.Embed(
                    title="❌ Invalid Field",
                    description="Valid: bio, game, color, social",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            if value is None or len(value) == 0:
                embed = discord.Embed(title="❌ Error", description="You must provide a value!", color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            
            if field == 'bio':
                await set_profile(member.id, bio=value)
            elif field == 'game':
                await set_profile(member.id, favorite_game=value)
            elif field == 'color':
                await set_profile(member.id, favorite_color=value)
            elif field == 'social':
                await set_profile(member.id, social_link=value)
            
            embed = discord.Embed(title="✅ Profile Updated", color=discord.Color.green())
            embed.add_field(name=f"📝 {field.capitalize()}", value=value, inline=False)
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "profile", f"update: {field}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='quest')
async def quest(ctx):
    """View quest progress"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user = await get_user_data(ctx.author.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title="📋 Message Quest", color=discord.Color.blue())
        embed.add_field(name="Today", value=f"**{user[4]}**", inline=True)
        embed.add_field(name="Week", value=f"**{user[5]}**", inline=True)
        embed.add_field(name="Lifetime", value=f"**{user[6]}**", inline=True)
        embed.add_field(name="Quest", value="Reach message milestones to unlock roles!", inline=False)
        embed.set_footer(text="Keep messaging to progress!")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "quest", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='referral')
async def referral(ctx, member: discord.Member = None):
    """View referral code"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        code = await get_referral_code(member.id)
        uses = await get_referral_uses(member.id)
        
        embed = discord.Embed(title=f"🔗 {member.name}'s Referral", color=discord.Color.blue())
        embed.add_field(name="Code", value=f"`{code}`", inline=False)
        embed.add_field(name="Uses", value=f"**{uses}**", inline=True)
        embed.add_field(name="Share", value="Give to friends!", inline=True)
        embed.set_footer(text="Earn from referrals!")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "referral", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='accountage')
async def accountage(ctx, member: discord.Member = None):
    """Check account age"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        age_days = await get_account_age_days(member)
        is_alt, flags = await detect_alt_account(member)
        
        embed = discord.Embed(title=f"🎓 {member.name}'s Account", color=discord.Color.blue())
        embed.add_field(name="Age", value=f"**{age_days}** days", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
        
        if is_alt:
            embed.color = discord.Color.orange()
            embed.add_field(name="⚠️ Alt Detection", value="**Possible Alt** 🚩", inline=False)
            flags_str = "\n".join(flags)
            embed.add_field(name="Flags", value=flags_str, inline=False)
        else:
            embed.color = discord.Color.green()
            embed.add_field(name="Status", value="**Legitimate**", inline=False)
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "accountage", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='airdrop')
async def airdrop(ctx, amount: float = None):
    """Start a Robux airdrop (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
            
        if not is_authorized_guild(ctx.guild.id):
            return
            
        if amount is None or amount <= 0:
            embed = discord.Embed(
                title="❌ Missing Amount",
                description="Please specify the amount of Robux to drop.\nExample: `!airdrop 100`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="🎁 ROBUX AIRDROP INCOMING!",
            description=f"A massive airdrop of **{ROBUX_ICON}{amount:.2f}** is landing!\n\nBe the first to click the button below to claim it!",
            color=discord.Color.gold()
        )
        
        view = AirdropView(amount)
        await ctx.send(embed=embed, view=view)
        await log_command(ctx.author.id, ctx.author.name, "airdrop", f"amount: {amount}", True)
    except Exception as e:
        print(f"Error in airdrop: {e}")

class AirdropView(discord.ui.View):
    def __init__(self, amount):
        super().__init__(timeout=300)
        self.amount = amount
        self.claimed = False

    @discord.ui.button(label="Claim Airdrop", style=discord.ButtonStyle.green, emoji="💰")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            await interaction.response.send_message("❌ This airdrop has already been claimed!", ephemeral=True)
            return

        self.claimed = True
        button.disabled = True
        button.label = "Claimed"
        button.style = discord.ButtonStyle.gray
        await interaction.message.edit(view=self)
        
        await create_user(interaction.user.id, interaction.user.name)
        await add_robux(interaction.user.id, self.amount)
        
        embed = discord.Embed(
            title="🎉 Airdrop Claimed!",
            description=f"Congratulations {interaction.user.mention}! You successfully intercepted the airdrop and received **{ROBUX_ICON}{self.amount:.2f}**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        self.stop()

@bot.command(name='trivia')
async def trivia(ctx):
    """Play trivia"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        banned = await is_user_banned(user_id)
        if banned:
            embed = discord.Embed(title="🚫 Banned", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        question_data = random.choice(TRIVIA_QUESTIONS)
        
        embed = discord.Embed(
            title="🧠 Trivia Question",
            description=question_data["question"],
            color=discord.Color.blue()
        )
        for option in question_data["options"]:
            embed.add_field(name="​", value=option, inline=False)
        embed.add_field(name="Reward", value=f"✅ +{ROBUX_ICON}0.25 | ❌ -{ROBUX_ICON}0.25", inline=False)
        embed.add_field(name="​", value="React with A, B, C, or D!", inline=False)
        embed.set_footer(text="You have 15 seconds!")
        
        msg = await ctx.send(embed=embed)
        
        reactions = ['🇦', '🇧', '🇨', '🇩']
        for reaction in reactions:
            await msg.add_reaction(reaction)
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in reactions

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=15.0, check=check)
            
            answer_map = {'🇦': 'A', '🇧': 'B', '🇨': 'C', '🇩': 'D'}
            user_answer = answer_map[str(reaction.emoji)]
            correct_answer = question_data["answer"]
            
            is_correct = user_answer == correct_answer
            
            if is_correct:
                await add_trivia_score(user_id, True)
                embed = discord.Embed(
                    title="🎉 Correct!",
                    description=f"Answer: **{correct_answer}) {question_data['correct_text']}**\n\n**+{ROBUX_ICON}0.25**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                await log_command(user_id, ctx.author.name, "trivia", "correct", True)
            else:
                await add_trivia_score(user_id, False)
                embed = discord.Embed(
                    title="❌ Wrong!",
                    description=f"Answer: **{correct_answer}) {question_data['correct_text']}**\n\n**-{ROBUX_ICON}0.25**",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                await log_command(user_id, ctx.author.name, "trivia", "wrong", True)
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ Time's Up!",
                description=f"Answer: **{question_data['answer']}) {question_data['correct_text']}**",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            await log_command(user_id, ctx.author.name, "trivia", "timeout", False, "Timeout")
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='quiz')
async def quiz(ctx):
    """Fun quiz"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        question_data = random.choice(QUIZ_QUESTIONS)
        
        embed = discord.Embed(
            title="📚 Server Quiz",
            description=question_data["question"],
            color=discord.Color.blue()
        )
        for option in question_data["options"]:
            embed.add_field(name="​", value=option, inline=False)
        embed.add_field(name="​", value="React with A, B, C, or D!", inline=False)
        embed.set_footer(text="15 seconds!")
        
        msg = await ctx.send(embed=embed)
        
        reactions = ['🇦', '🇧', '🇨', '🇩']
        for reaction in reactions:
            await msg.add_reaction(reaction)
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in reactions

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=15.0, check=check)
            
            answer_map = {'🇦': 'A', '🇧': 'B', '🇨': 'C', '🇩': 'D'}
            user_answer = answer_map[str(reaction.emoji)]
            correct_answer = question_data["answer"]
            
            is_correct = user_answer == correct_answer
            
            if is_correct:
                embed = discord.Embed(
                    title="🎉 Correct!",
                    description=f"Answer: **{correct_answer}) {question_data['correct_text']}**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                await log_command(ctx.author.id, ctx.author.name, "quiz", "correct", True)
            else:
                embed = discord.Embed(
                    title="❌ Wrong!",
                    description=f"Answer: **{correct_answer}) {question_data['correct_text']}**",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                await log_command(ctx.author.id, ctx.author.name, "quiz", "wrong", True)
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ Time's Up!",
                description=f"Answer: **{question_data['answer']}) {question_data['correct_text']}**",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "quiz", "timeout", False, "Timeout")
    except Exception as e:
        print(f"Error: {e}")

# ==================== WITHDRAWAL COMMANDS ====================

@bot.command(name='withdraw')
async def withdraw(ctx, amount: float = None, gamepass_id: str = None):
    """Request withdrawal"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if amount is None or gamepass_id is None:
            global_limit = await get_global_withdraw_limit()
            embed = discord.Embed(
                title="❌ Usage",
                description=f"**Usage:** `!withdraw <amount> <gamepass_id>`\n\nExample: `!withdraw 75 123456`\n\n**Requirements:**\n• Min: 50 {ROBUX_ICON}\n• Max: {global_limit} {ROBUX_ICON}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        withdraw_open = await get_withdrawal_status()
        if not withdraw_open:
            embed = discord.Embed(
                title="🔒 Withdrawals Closed",
                description="Try again later!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        user = await get_user_data(ctx.author.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if user[2] < 50:
            embed = discord.Embed(
                title="❌ Insufficient Balance",
                description=f"You need 50 {ROBUX_ICON}\n\nYour balance: {ROBUX_ICON}{user[2]:.2f}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if amount < 5:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description=f"Min is {ROBUX_ICON}5",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        global_limit = await get_global_withdraw_limit()
        if amount > global_limit:
            embed = discord.Embed(
                title="❌ Over Daily Limit",
                description=f"Max is {ROBUX_ICON}{global_limit}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        last_withdraw = await get_last_withdraw(ctx.author.id)
        if last_withdraw:
            try:
                last_withdraw_dt = datetime.strptime(last_withdraw, '%Y-%m-%d %H:%M:%S')
                if datetime.now() - last_withdraw_dt < timedelta(days=1):
                    time_remaining = timedelta(days=1) - (datetime.now() - last_withdraw_dt)
                    hours, remainder = divmod(int(time_remaining.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    embed = discord.Embed(
                        title="⏰ Cooldown",
                        description=f"Next withdrawal in `{hours}h {minutes}m {seconds}s`",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
            except:
                pass
        
        if user[2] < amount:
            embed = discord.Embed(
                title="❌ Insufficient Balance",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        withdrawal_id = await create_withdrawal(ctx.author.id, ctx.author.name, amount, gamepass_id)
        
        await set_last_withdraw(ctx.author.id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        await subtract_robux(ctx.author.id, amount)
        await add_withdraw_history(ctx.author.id, amount, "pending")
        
        embed = discord.Embed(
            title="✅ Withdrawal Requested",
            description=f"Your request has been submitted!",
            color=discord.Color.green()
        )
        embed.add_field(name="Amount", value=f"{ROBUX_ICON}{amount}", inline=True)
        embed.add_field(name="Gamepass ID", value=f"`{gamepass_id}`", inline=True)
        embed.add_field(name="Status", value="⏳ Pending", inline=True)
        embed.add_field(name="Reference", value=f"`#{withdrawal_id}`", inline=False)
        embed.set_footer(text="Owner will review within 24-48 hours")
        
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "withdraw", f"amount: {amount}, gamepass_id: {gamepass_id}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='withdrawpanel')
async def withdraw_panel(ctx):
    """Show withdrawal panel"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.administrator:
            return
        
        embed = discord.Embed(
            title="🏧 Robux Withdrawal Portal",
            description="Click buttons below to withdraw your earnings!",
            color=discord.Color.gold()
        )
        embed.add_field(name="📋 Rules", value="• Min: 50 Robux\n• Max: Per transaction limit\n• Once per 24 hours", inline=False)
        embed.add_field(name="💡 Steps", value="1. Have 50+ balance\n2. Create gamepass on Roblox\n3. Click button to submit\n4. Wait for approval", inline=False)
        
        await ctx.send(embed=embed, view=WithdrawPanel())
        await log_command(ctx.author.id, ctx.author.name, "withdrawpanel", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='withdrawhistory')
async def withdrawhistory(ctx, member: discord.Member = None):
    """View withdrawal history"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        history = await get_withdraw_history(member.id)
        
        if not history:
            embed = discord.Embed(title="❌ No History", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title=f"📜 {member.name}'s Withdrawals", color=discord.Color.blue())
        
        for withdrawal in history:
            withdrawal_id, amount, status, requested_at = withdrawal
            status_emoji = "✅" if status == "paid" else "⏳" if status == "pending" else "❌"
            embed.add_field(
                name=f"{status_emoji} #{withdrawal_id}",
                value=f"{ROBUX_ICON}{amount} | {status}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "withdrawhistory", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='withdrawals')
async def withdrawals(ctx):
    """View pending withdrawals (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        pending = await get_pending_withdrawals()
        
        if not pending:
            embed = discord.Embed(title="✅ No Pending", color=discord.Color.green())
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title="📋 Pending Withdrawals", color=discord.Color.orange())
        
        for withdrawal in pending:
            withdrawal_id, user_id, username, amount, gamepass_id, requested_at = withdrawal
            embed.add_field(
                name=f"#{withdrawal_id} - {username}",
                value=f"{ROBUX_ICON}{amount} | Gamepass: `{gamepass_id}`",
                inline=False
            )
        
        embed.add_field(name="✅ Approve", value="`!paid <@user> <amount>`", inline=True)
        embed.add_field(name="❌ Deny", value="`!denywithdraw <@user> [reason]`", inline=True)
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "withdrawals", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='paid')
async def paid(ctx, member: discord.Member = None, amount: float = None):
    """Mark withdrawal as paid (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None or amount is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!paid <@member> <amount>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        pending = await get_pending_withdrawals()
        withdrawal_id = None
        
        for withdrawal in pending:
            w_id, user_id, username, w_amount, gamepass_id, requested_at = withdrawal
            if user_id == member.id and w_amount == amount:
                withdrawal_id = w_id
                break
        
        if withdrawal_id is None:
            embed = discord.Embed(title="❌ Not Found", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await mark_withdrawal_paid(withdrawal_id)
        await add_withdraw_history(member.id, amount, "paid")
        
        embed = discord.Embed(
            title="✅ Withdrawal Approved",
            description=f"#{withdrawal_id} for {member.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Amount", value=f"{ROBUX_ICON}{amount}", inline=True)
        
        await ctx.send(embed=embed)
        
        try:
            await member.send(embed=discord.Embed(
                title="✅ Withdrawal Processed",
                description=f"Your {ROBUX_ICON}{amount} withdrawal was approved!",
                color=discord.Color.green()
            ))
        except:
            pass
        
        await log_command(ctx.author.id, ctx.author.name, "paid", f"member: {member.name}, amount: {amount}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='denywithdraw')
async def denywithdraw(ctx, member: discord.Member = None, *, reason: str = None):
    """Deny withdrawal (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!denywithdraw <@member> [reason]`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if reason is None:
            reason = "No reason provided"
        
        pending = await get_pending_withdrawals()
        withdrawal_id = None
        amount = 0
        
        for withdrawal in pending:
            w_id, user_id, username, w_amount, gamepass_id, requested_at = withdrawal
            if user_id == member.id:
                withdrawal_id = w_id
                amount = w_amount
                break
        
        if withdrawal_id is None:
            embed = discord.Embed(title="❌ Not Found", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await add_robux(member.id, amount)
        
        embed = discord.Embed(
            title="❌ Withdrawal Denied",
            description=f"#{withdrawal_id} for {member.mention}",
            color=discord.Color.red()
        )
        embed.add_field(name="Refunded", value=f"{ROBUX_ICON}{amount}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        
        try:
            await member.send(embed=discord.Embed(
                title="❌ Withdrawal Denied",
                description=f"Your {ROBUX_ICON}{amount} withdrawal was denied.\n\n**Reason:** {reason}",
                color=discord.Color.red()
            ))
        except:
            pass
        
        await log_command(ctx.author.id, ctx.author.name, "denywithdraw", f"member: {member.name}, reason: {reason}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='openwithdraw')
async def openwithdraw(ctx):
    """Open withdrawals (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        await set_withdrawal_status('open')
        
        embed = discord.Embed(
            title="🔓 Withdrawals Opened",
            description="Withdrawals are now **OPEN**!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "openwithdraw", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='closewithdraw')
async def closewithdraw(ctx):
    """Close withdrawals (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        await set_withdrawal_status('closed')
        
        embed = discord.Embed(
            title="🔒 Withdrawals Closed",
            description="Withdrawals are now **CLOSED**!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "closewithdraw", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setwithdrawdaily')
async def setwithdrawdaily(ctx, amount: float = None):
    """Set daily withdrawal limit (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if amount is None or amount < 1:
            current = await get_global_withdraw_limit()
            embed = discord.Embed(
                title="❌ Usage",
                description=f"**Usage:** `!setwithdrawdaily <amount>`\n\nCurrent: {ROBUX_ICON}{current}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_global_withdraw_limit(amount)
        
        embed = discord.Embed(
            title="✅ Daily Limit Updated",
            description=f"Max per transaction: {ROBUX_ICON}{amount}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "setwithdrawdaily", f"amount: {amount}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setdaily')
async def setdaily(ctx, amount: float = None):
    """Set daily reward amount (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if amount is None or amount < 0:
            current = await get_rate('daily_reward')
            embed = discord.Embed(
                title="❌ Usage",
                description=f"**Usage:** `!setdaily <amount>`\n\nCurrent: {ROBUX_ICON}{current}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_rate('daily_reward', amount)
        
        embed = discord.Embed(
            title="✅ Daily Reward Updated",
            description=f"New daily reward: {ROBUX_ICON}{amount}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "setdaily", f"amount: {amount}", True)
    except Exception as e:
        print(f"Error in setdaily: {e}")
        await ctx.send(f"❌ Error: {e}")

@bot.command(name='withdrawstatus')
async def withdrawstatus(ctx):
    """Check withdrawal status"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        is_open = await get_withdrawal_status()
        
        if is_open:
            embed = discord.Embed(
                title="🔓 Withdrawals OPEN",
                description="You can request withdrawals now!",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="🔒 Withdrawals CLOSED",
                description="Withdrawals are temporarily closed!",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "withdrawstatus", "", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== GAMES ====================

@bot.command(name='spin')
async def spin(ctx):
    """Daily spin"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        banned = await is_user_banned(user_id)
        if banned:
            return
        
        await create_user(user_id, ctx.author.name)
        can_claim, last_spin = await can_spin(user_id)
        if not can_claim:
            embed = discord.Embed(
                title="⏰ Already Spun",
                description="Come back tomorrow!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        reward = random.randint(1, 5)
        await add_robux(user_id, reward)
        await set_spin_claimed(user_id)
        
        embed = discord.Embed(
            title="🎡 SPIN!",
            description=f"🎉 You won **{ROBUX_ICON}{reward}**!",
            color=discord.Color.gold()
        )
        embed.add_field(name="Next Spin", value="In 24 hours", inline=True)
        
        await ctx.send(embed=embed)
        await log_command(user_id, ctx.author.name, "spin", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='dice')
async def dice(ctx, amount: float = None):
    """Dice game - 2% win, 3x payout"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        
        cooldown = await get_game_cooldown()
        can_play, cooldown_msg = await check_game_cooldown(user_id, cooldown)
        if not can_play:
            embed = discord.Embed(title="⏳ Cooldown", description=cooldown_msg, color=discord.Color.orange())
            await ctx.send(embed=embed)
            return
        
        banned = await is_user_banned(user_id)
        if banned:
            return
        
        if amount is None or amount < 1 or amount > 30:
            embed = discord.Embed(
                title="🎲 Dice Game",
                description=f"**Usage:** `!dice <amount>`\n\n• Min: 1 {ROBUX_ICON}\n• Max: 30 {ROBUX_ICON}\n• Win: 2%\n• Payout: 3x",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        user = await get_user_data(user_id)
        
        if user[2] < amount:
            embed = discord.Embed(title="❌ Insufficient", description=f"You have {ROBUX_ICON}{user[2]:.2f}", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        win_chance = random.randint(1, 100)
        won = win_chance <= 2
        
        await subtract_robux(user_id, amount)
        
        if won:
            winnings = amount * 3
            await add_robux(user_id, winnings)
            try:
                image_path = create_dice_result(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", amount, True, win_chance)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="🎲 YOU WON!",
                    description=f"**{ROBUX_ICON}{amount:.2f}** → **{ROBUX_ICON}{winnings:.2f}**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
        else:
            try:
                image_path = create_dice_result(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", amount, False, win_chance)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="🎲 YOU LOST",
                    description=f"Lost **{ROBUX_ICON}{amount:.2f}**",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
            winnings = 0
        
        await add_game_history(user_id, "dice", amount, won, winnings)
        await log_command(user_id, ctx.author.name, "dice", f"amount: {amount}, won: {won}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='roulette')
async def roulette(ctx, amount: float = None, color: str = None):
    """Roulette - 15% win, 1.5x payout"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        
        cooldown = await get_game_cooldown()
        can_play, cooldown_msg = await check_game_cooldown(user_id, cooldown)
        if not can_play:
            embed = discord.Embed(title="⏳ Cooldown", description=cooldown_msg, color=discord.Color.orange())
            await ctx.send(embed=embed)
            return
        
        banned = await is_user_banned(user_id)
        if banned:
            return
        
        if amount is None or color is None or amount < 1 or amount > 40:
            embed = discord.Embed(
                title="🎡 Roulette",
                description=f"**Usage:** `!roulette <amount> <red|black>`\n\n• Min: 1 {ROBUX_ICON}\n• Max: 40 {ROBUX_ICON}\n• Win: 15%\n• Payout: 1.5x",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        color = color.lower()
        if color not in ['red', 'black']:
            embed = discord.Embed(title="❌ Error", description="Choose red or black!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        user = await get_user_data(user_id)
        
        if user[2] < amount:
            embed = discord.Embed(title="❌ Insufficient", description=f"You have {ROBUX_ICON}{user[2]:.2f}", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        win_chance = random.randint(1, 100)
        won = win_chance <= 15
        
        await subtract_robux(user_id, amount)
        
        if won:
            winnings = amount * 1.5
            await add_robux(user_id, winnings)
            embed = discord.Embed(
                title="🎡 YOU WON!",
                description=f"**{ROBUX_ICON}{amount:.2f}** → **{ROBUX_ICON}{winnings:.2f}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Your Bet", value=f"**{color.upper()}**", inline=True)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="🎡 YOU LOST",
                description=f"Lost **{ROBUX_ICON}{amount:.2f}**",
                color=discord.Color.red()
            )
            embed.add_field(name="Your Bet", value=f"**{color.upper()}**", inline=True)
            await ctx.send(embed=embed)
            winnings = 0
        
        await add_game_history(user_id, "roulette", amount, won, winnings)
        await log_command(user_id, ctx.author.name, "roulette", f"amount: {amount}, color: {color}, won: {won}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='slots')
async def slots(ctx, amount: float = None):
    """Slots game"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        
        cooldown = await get_game_cooldown()
        can_play, cooldown_msg = await check_game_cooldown(user_id, cooldown)
        if not can_play:
            embed = discord.Embed(title="⏳ Cooldown", description=cooldown_msg, color=discord.Color.orange())
            await ctx.send(embed=embed)
            return
        
        banned = await is_user_banned(user_id)
        if banned:
            return
        
        if amount is None or amount < 1 or amount > 25:
            embed = discord.Embed(
                title="🎰 Slots",
                description=f"**Usage:** `!slots <amount>`\n\n• Min: 1 {ROBUX_ICON}\n• Max: 25 {ROBUX_ICON}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        user = await get_user_data(user_id)
        
        if user[2] < amount:
            embed = discord.Embed(title="❌ Insufficient", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        symbols = ["🍒", "💎", "🔔"]
        result = [random.choice(symbols) for _ in range(3)]
        
        await subtract_robux(user_id, amount)
        
        winnings = 0
        won = False
        
        if result[0] == result[1] == result[2]:
            if result[0] == "🍒":
                winnings = amount * 2
                won = True
            elif result[0] == "💎":
                winnings = amount * 1.5
                won = True
            elif result[0] == "🔔":
                winnings = amount * 1.2
                won = True
        
        if won:
            await add_robux(user_id, winnings)
            try:
                image_path = create_slots_result(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", amount, True, result)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="🎰 YOU WON!",
                    description=f"{'  '.join(result)}\n\n**{ROBUX_ICON}{amount:.2f}** → **{ROBUX_ICON}{winnings:.2f}**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
        else:
            try:
                image_path = create_slots_result(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", amount, False, result)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="🎰 YOU LOST",
                    description=f"{'  '.join(result)}\n\nLost **{ROBUX_ICON}{amount:.2f}**",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        
        await add_game_history(user_id, "slots", amount, won, winnings)
        await log_command(user_id, ctx.author.name, "slots", f"amount: {amount}, won: {won}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='lucky')
async def lucky(ctx, amount: float = None):
    """Lucky spin - 30% win"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        
        cooldown = await get_game_cooldown()
        can_play, cooldown_msg = await check_game_cooldown(user_id, cooldown)
        if not can_play:
            embed = discord.Embed(title="⏳ Cooldown", description=cooldown_msg, color=discord.Color.orange())
            await ctx.send(embed=embed)
            return
        
        banned = await is_user_banned(user_id)
        if banned:
            return
        
        if amount is None or amount < 1 or amount > 35:
            embed = discord.Embed(
                title="🌟 Lucky Spin",
                description=f"**Usage:** `!lucky <amount>`\n\n• Min: 1 {ROBUX_ICON}\n• Max: 35 {ROBUX_ICON}\n• Win: 30%\n• Multiplier: 1.2x-2x",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        user = await get_user_data(user_id)
        
        if user[2] < amount:
            embed = discord.Embed(title="❌ Insufficient", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        win_chance = random.randint(1, 100)
        won = win_chance <= 30
        
        await subtract_robux(user_id, amount)
        
        if won:
            multiplier = random.uniform(1.2, 2.0)
            winnings = amount * multiplier
            await add_robux(user_id, winnings)
            embed = discord.Embed(
                title="🌟 YOU WON!",
                description=f"**{ROBUX_ICON}{amount:.2f}** → **{ROBUX_ICON}{winnings:.2f}** ({multiplier:.2f}x)",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="🌟 YOU LOST",
                description=f"Lost **{ROBUX_ICON}{amount:.2f}**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            winnings = 0
        
        await add_game_history(user_id, "lucky", amount, won, winnings)
        await log_command(user_id, ctx.author.name, "lucky", f"amount: {amount}, won: {won}", True)
    except Exception as e:
        print(f"Error: {e}")


@bot.command(name='icf')
async def icf(ctx, amount: float = None):
    """Instant Coinflip - 5% win, 1.8x payout"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        user_id = ctx.author.id
        
        cooldown = await get_game_cooldown()
        can_play, cooldown_msg = await check_game_cooldown(user_id, cooldown)
        if not can_play:
            embed = discord.Embed(title="⏳ Cooldown", description=cooldown_msg, color=discord.Color.orange())
            await ctx.send(embed=embed)
            return
        
        banned = await is_user_banned(user_id)
        if banned:
            return
        
        if amount is None or amount < 1 or amount > 50:
            embed = discord.Embed(
                title="💰 Coinflip",
                description=f"**Usage:** `!icf <amount>`\n\n• Min: 1 {ROBUX_ICON}\n• Max: 50 {ROBUX_ICON}\n• Win: 5%\n• Payout: 1.8x",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await create_user(user_id, ctx.author.name)
        user = await get_user_data(user_id)
        
        if user[2] < amount:
            embed = discord.Embed(title="❌ Insufficient", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        win_chance = random.randint(1, 100)
        won = win_chance <= 5
        result = "Heads" if random.choice([True, False]) else "Tails"
        
        await subtract_robux(user_id, amount)
        
        if won:
            winnings = amount * 1.8
            await add_robux(user_id, winnings)
            try:
                image_path = create_coinflip_win(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", amount, winnings)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="💰 YOU WON!",
                    description=f"**{result}**\n\n**{ROBUX_ICON}{amount:.2f}** → **{ROBUX_ICON}{winnings:.2f}**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
        else:
            try:
                image_path = create_coinflip_lose(ctx.author.name, ctx.author.avatar.url if ctx.author.avatar else "", amount)
                with open(image_path, 'rb') as f:
                    await ctx.send(file=discord.File(f, filename=image_path))
            except:
                embed = discord.Embed(
                    title="💰 YOU LOST",
                    description=f"**{result}**\n\nLost **{ROBUX_ICON}{amount:.2f}**",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
            winnings = 0
        
        await add_game_history(user_id, "icf", amount, won, winnings)
        await log_command(user_id, ctx.author.name, "icf", f"amount: {amount}, won: {won}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='gamestats')
async def gamestats(ctx, member: discord.Member = None):
    """View game stats"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        stats = await get_game_stats(member.id)
        
        if not stats:
            embed = discord.Embed(title="❌ No History", description=f"{member.name} hasn't played yet!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        total_games, total_wagered, total_won, wins, losses = stats
        
        if total_wagered:
            roi = ((total_won - total_wagered) / total_wagered) * 100
        else:
            roi = 0
        
        try:
            image_path = create_game_stats_image(member.name, member.avatar.url if member.avatar else "", total_games, wins, losses, total_wagered, total_won)
            with open(image_path, 'rb') as f:
                await ctx.send(file=discord.File(f, filename=image_path))
        except:
            embed = discord.Embed(title=f"🎰 {member.name}'s Stats", color=discord.Color.gold())
            embed.add_field(name="Total Games", value=f"**{total_games}**", inline=True)
            embed.add_field(name="Wins", value=f"**{wins}**", inline=True)
            embed.add_field(name="Losses", value=f"**{losses}**", inline=True)
            embed.add_field(name="Wagered", value=f"**{ROBUX_ICON}{total_wagered:.2f}**", inline=True)
            embed.add_field(name="Won", value=f"**{ROBUX_ICON}{total_won:.2f}**", inline=True)
            embed.add_field(name="Win Rate", value=f"**{(wins/total_games*100):.2f}%**", inline=True)
            embed.add_field(name="ROI", value=f"**{roi:.2f}%**", inline=False)
            
            if roi > 0:
                embed.color = discord.Color.green()
            else:
                embed.color = discord.Color.red()
            
            embed.set_footer(text="Play responsibly!")
            await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "gamestats", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")


# ==================== RP SYSTEM - COMPLETE CODE ====================

@bot.command(name='rp')
async def rp(ctx, member: discord.Member = None):
    """Check RP rank"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        rp_data = await get_user_rp_progress(member.id)
        
        if not rp_data:
            embed = discord.Embed(
                title=f"🎭 Career Progression: {member.name}",
                description="No RP data yet. Start messaging in RP channels!",
                color=discord.Color.purple()
            )
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "rp", f"target: {member.name}", True)
            return
        
        level_id = rp_data[2]
        messages_count = rp_data[3]
        
        role_data = await get_rp_role_by_id(level_id) if level_id else None
        
        if role_data:
            role_id, role_name, required_msgs, salary = role_data[0], role_data[1], role_data[2], role_data[3]
            progress_percent = (messages_count / required_msgs) * 100 if required_msgs > 0 else 100
            
            discord_role = discord.utils.get(ctx.guild.roles, name=role_name)
            if discord_role and discord_role not in member.roles:
                try:
                    await member.add_roles(discord_role)
                except:
                    pass
        else:
            role_name = "No Rank"
            required_msgs = 0
            salary = 0
            progress_percent = 0
        
        all_roles = await get_rp_roles()
        next_role_data = None
        for r in all_roles:
            if r[2] > messages_count:
                next_role_data = r
                break
        
        next_role_name = next_role_data[1] if next_role_data else "Max Rank"
        next_role_msgs = next_role_data[2] if next_role_data else required_msgs
        
        embed = discord.Embed(
            title=f"🎭 Career Progression: {member.name}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
        embed.add_field(name="Current Rank", value=role_name, inline=True)
        embed.add_field(name="Salary", value=f"{ROBUX_ICON}{salary}", inline=True)
        embed.add_field(name="Messages", value=f"{messages_count}/{required_msgs}", inline=True)
        embed.add_field(name="Next Rank", value=next_role_name, inline=True)
        embed.add_field(name="Progress", value=f"**{progress_percent:.1f}%**", inline=True)
        
        # Progress bar
        filled = int(progress_percent / 10)
        bar = "█" * filled + "░" * (10 - filled)
        embed.add_field(name="Progress Bar", value=f"`{bar}`", inline=False)
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "rp", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='roles')
async def roles(ctx):
    """View all RP roles"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        roles_list = await get_rp_roles()
        
        if not roles_list:
            embed = discord.Embed(
                title="❌ No RP Roles",
                description="No RP roles set up yet!\n\nUse `!rprolespanel` to add!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title="🏛️ Organizational Hierarchy", color=discord.Color.purple())
        
        for role in roles_list:
            role_id, role_name, required_msgs, salary = role
            embed.add_field(
                name=f"#{role_id} - {role_name}",
                value=f"**Required:** {required_msgs} messages\n**Salary:** {ROBUX_ICON}{salary}",
                inline=False
            )
        
        embed.set_footer(text="Message in RP channels to rank up! | Use !rprolespanel to manage")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "roles", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='role')
async def role(ctx, name: str = None, messages: int = None, salary: float = None):
    """Add RP role (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not all([name, messages]):
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!role <name> <messages> [salary]`\n\nExample: `!role Admin 5000 50`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if salary is None:
            salary = 0
        
        role_id = await add_rp_role(name, messages, salary)
        
        embed = discord.Embed(title="✅ RP Role Added", color=discord.Color.green())
        embed.add_field(name="ID", value=f"`{role_id}`", inline=True)
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Messages", value=str(messages), inline=True)
        embed.add_field(name="Salary", value=f"{ROBUX_ICON}{salary}", inline=True)
        await ctx.send(embed=embed)
        
        print(f"✅ RP role '{name}' added (ID: {role_id})")
        await log_command(ctx.author.id, ctx.author.name, "role", f"name: {name}, messages: {messages}, salary: {salary}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='delrole')
async def delrole(ctx, role_id: int = None):
    """Delete RP role (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if role_id is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!delrole <role_id>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await delete_rp_role(role_id)
        
        embed = discord.Embed(
            title="✅ RP Role Deleted",
            description=f"Role ID **{role_id}** removed!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        print(f"✅ RP role {role_id} deleted")
        await log_command(ctx.author.id, ctx.author.name, "delrole", f"role_id: {role_id}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setrpchannel')
async def setrpchannel(ctx, channel: discord.TextChannel = None):
    """Set RP channel"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.administrator:
            return
        
        if channel is None:
            channel = ctx.channel
        
        await add_rp_channel(channel.id)
        
        embed = discord.Embed(
            title="✅ RP Channel Set",
            description=f"{channel.mention} is now an RP channel!\n\nUsers gain RP XP here!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "setrpchannel", f"channel: {channel.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='delrpchannel')
async def delrpchannel(ctx, channel: discord.TextChannel = None):
    """Remove RP channel"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.administrator:
            return
        
        if channel is None:
            channel = ctx.channel
        
        await remove_rp_channel(channel.id)
        
        embed = discord.Embed(
            title="✅ RP Channel Removed",
            description=f"{channel.mention} is no longer an RP channel!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "delrpchannel", f"channel: {channel.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='rpreqrole')
async def rpreqrole(ctx, role: discord.Role = None):
    """Require role for RP (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if role is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!rpreqrole <@role>`\n\nExample: `!rpreqrole @RPMember`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_rp_req_role(role.id)
        
        embed = discord.Embed(
            title="✅ RP Role Requirement Set",
            description=f"Users need {role.mention} to use RP!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        print(f"✅ RP req role set to {role.name}")
        await log_command(ctx.author.id, ctx.author.name, "rpreqrole", f"role: {role.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='rpstats')
async def rpstats(ctx, member: discord.Member = None):
    """View RP statistics"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        rp_data = await get_user_rp_progress(member.id)
        
        if not rp_data:
            embed = discord.Embed(
                title=f"🎭 {member.name}'s RP Stats",
                description="No RP data yet!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        messages_count = rp_data[3]
        all_roles = await get_rp_roles()
        
        embed = discord.Embed(
            title=f"🎭 {member.name}'s RP Statistics",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
        embed.add_field(name="Total RP Messages", value=f"**{messages_count}**", inline=True)
        embed.add_field(name="Total Ranks", value=f"**{len(all_roles)}**", inline=True)
        
        # Calculate earnings potential
        total_salary = 0
        for role in all_roles:
            if messages_count >= role[2]:
                total_salary = role[3]
        
        embed.add_field(name="Current Salary", value=f"**{ROBUX_ICON}{total_salary}**", inline=True)
        embed.set_footer(text="Keep messaging to rank up!")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "rpstats", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='rpinfo')
async def rpinfo(ctx):
    """Get RP system information"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        rp_channels = await get_rp_channels()
        rp_roles = await get_rp_roles()
        
        embed = discord.Embed(
            title="📊 RP System Information",
            description="Learn about the RP system!",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="🔊 What is RP?",
            value="RP = Role Play System\nMessage in RP channels to gain XP and unlock ranks!",
            inline=False
        )
        
        embed.add_field(
            name="📈 How to Rank Up?",
            value="1. Message in RP channels\n2. Gain RP XP with each message\n3. Unlock ranks at message milestones\n4. Earn salary with higher ranks!",
            inline=False
        )
        
        if rp_channels:
            channel_list = ", ".join([f"<#{ch}>" for ch in rp_channels])
            embed.add_field(name=f"🎭 RP Channels ({len(rp_channels)})", value=channel_list, inline=False)
        else:
            embed.add_field(name="🎭 RP Channels", value="None set up yet!", inline=False)
        
        if rp_roles:
            embed.add_field(name=f"👑 Available Ranks ({len(rp_roles)})", value=f"Use `!roles` to see all ranks!", inline=False)
        else:
            embed.add_field(name="👑 Available Ranks", value="None set up yet!", inline=False)
        
        embed.add_field(
            name="💡 Commands",
            value="`!rp` - Check your rank\n`!roles` - View all ranks\n`!rpstats` - View your stats",
            inline=False
        )
        
        embed.set_footer(text="Use !rp to check your current rank!")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "rpinfo", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='resetrp')
async def resetrp(ctx, member: discord.Member = None):
    """Reset RP progress (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!resetrp <@member>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await reset_all_rp_progress()  # This resets all - modify as needed
        
        embed = discord.Embed(
            title="✅ RP Progress Reset",
            description=f"{member.mention}'s RP progress reset!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "resetrp", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== RP COMMANDS SUMMARY ====================
# !rp [member] - Check your RP rank and progress
# !roles - View all available RP roles
# !role <name> <messages> [salary] - Add new RP role (Owner)
# !delrole <id> - Delete RP role (Owner)
# !setrpchannel [#channel] - Set RP channel (Admin)
# !delrpchannel [#channel] - Remove RP channel (Admin)
# !rpreqrole <@role> - Require role for RP (Owner)
# !rpstats [member] - View RP statistics
# !rpinfo - Get RP system info
# !resetrp <@member> - Reset RP progress (Owner)
        
# ==================== STAFF SYSTEM ====================

@bot.command(name='staff')
async def staff(ctx, member: discord.Member = None):
    """Promote staff"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        req_role_id = await get_staff_req_role()
        if req_role_id:
            req_role = ctx.guild.get_role(req_role_id)
            if req_role and req_role not in ctx.author.roles and ctx.author.id != OWNER_ID:
                return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!staff <@member>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        staff_role_id = await get_staff_role()
        if not staff_role_id:
            embed = discord.Embed(title="❌ Config Error", description="Staff role not set!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        staff_role = ctx.guild.get_role(staff_role_id)
        if not staff_role:
            embed = discord.Embed(title="❌ Role Error", description="Staff role doesn't exist!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        if staff_role in member.roles:
            embed = discord.Embed(title="ℹ️ Already Staff", description=f"{member.mention} already has staff role!", color=discord.Color.blue())
            await ctx.send(embed=embed)
            return

        try:
            await member.add_roles(staff_role, reason=f"Staff promotion by {ctx.author.name}")
            await add_staff_role(ctx.author.id)
            await add_staff_promotion(ctx.author.id, member.id, member.name)
            
            embed = discord.Embed(title="✨ Staff Promotion", color=discord.Color.gold())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
            embed.add_field(name="Promoted", value=member.mention, inline=True)
            embed.add_field(name="By", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reward", value=f"**+{ROBUX_ICON}50.00**", inline=False)
            await ctx.send(embed=embed)
            
            await log_command(ctx.author.id, ctx.author.name, "staff", f"target: {member.name}", True)
        except Exception as e:
            print(f"Error: {e}")

    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='staffstats')
async def staffstats(ctx, member: discord.Member = None):
    """View staff stats"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        stats = await get_staff_stats(member.id)
        
        if not stats:
            embed = discord.Embed(
                title=f"👨‍💼 {member.name}'s Stats",
                description="No promotions yet!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
        
        promotion_count = await get_staff_promotion_count(member.id)
        
        embed = discord.Embed(title=f"👨‍💼 {member.name}'s Stats", color=discord.Color.blue())
        embed.add_field(name="Promotions", value=f"**{promotion_count}**", inline=True)
        embed.add_field(name="Earnings", value=f"**{ROBUX_ICON}{promotion_count * 50:.2f}**", inline=True)
        
        embed.set_footer(text="Promote more members!")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "staffstats", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='staffrole')
async def staffrole(ctx, role: discord.Role = None):
    """Set staff role (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if role is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!staffrole <@role>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await set_staff_role(role.id)
        
        embed = discord.Embed(
            title="✅ Staff Role Set",
            description=f"Staff will get {role.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "staffrole", f"role: {role.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='reqstaff')
async def reqstaff(ctx, role: discord.Role = None):
    """Require role for staff (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if role is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!reqstaff <@role>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await set_staff_req_role(role.id)
        
        embed = discord.Embed(
            title="✅ Requirement Set",
            description=f"Must have {role.mention} to use !staff",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "reqstaff", f"role: {role.name}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== VOUCHES ====================

@bot.command(name='vouch')
async def vouch(ctx, rating: int = None, *, comment: str = None):
    """Leave a vouch"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if rating is None or comment is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!vouch <rating 1-5> <comment>`\n\nExample: `!vouch 5 Great server!`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if rating < 1 or rating > 5:
            embed = discord.Embed(title="❌ Error", description="Rating must be 1-5!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await add_vouch(ctx.author.id, ctx.author.name, rating, comment)
        
        stars = "⭐" * rating
        embed = discord.Embed(
            title="✅ Vouch Added",
            description=f"{stars}\n\n{comment}",
            color=discord.Color.green()
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else "")
        embed.set_footer(text="Thank you!")
        
        await ctx.send(embed=embed)
        
        vouch_channel_id = await get_vouch_channel()
        if vouch_channel_id:
            try:
                channel = ctx.guild.get_channel(vouch_channel_id)
                if channel:
                    await channel.send(embed=embed)
            except:
                pass
        
        await log_command(ctx.author.id, ctx.author.name, "vouch", f"rating: {rating}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='vouches')
async def vouches(ctx):
    """View all vouches"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        vouches_list = await get_all_vouches()
        
        if not vouches_list:
            embed = discord.Embed(
                title="❌ No Vouches",
                description="Be the first to leave one!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title="⭐ Server Vouches", color=discord.Color.gold())
        
        for vouch in vouches_list[:10]:
            vouch_id, user_id, username, rating, comment = vouch
            stars = "⭐" * rating
            embed.add_field(
                name=f"{stars} {username}",
                value=comment,
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(vouches_list)}")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "vouches", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setvouchchannel')
async def setvouchchannel(ctx, channel: discord.TextChannel = None):
    """Set vouch channel"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if channel is None:
            channel = ctx.channel
        
        await set_vouch_channel(channel.id)
        
        embed = discord.Embed(
            title="✅ Vouch Channel Set",
            description=f"Vouches will go to {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "setvouchchannel", f"channel: {channel.name}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== SHOP SYSTEM ====================

@bot.command(name='shop')
async def shop(ctx):
    """View shop"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        items = await get_shop_items()
        
        if not items:
            embed = discord.Embed(
                title="🛍️ Shop",
                description="No items available!",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🛍️ Shop",
            description="Purchase items with Robux!",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        for item in items:
            item_id, item_name, item_type, price, role_id, description = item
            emoji = "👑" if item_type == "role" else "🎁"
            embed.add_field(
                name=f"{emoji} [{item_id}] {item_name}",
                value=f"**{ROBUX_ICON}{price}** | {description}",
                inline=False
            )
        
        embed.add_field(name="💳 Buy", value=f"`!buy <item_id>`", inline=False)
        embed.set_footer(text="Use !buy <id> to purchase")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "shop", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='buy')
async def buy(ctx, item_id: int = None):
    """Buy item"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if item_id is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!buy <item_id>`\n\nUse `!shop` to see items",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        item = await get_shop_item(item_id)
        if not item:
            embed = discord.Embed(title="❌ Item Not Found", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        item_id_check, item_name, item_type, price, role_id, description = item
        
        user = await get_user_data(ctx.author.id)
        if not user:
            embed = discord.Embed(title="❌ No Data", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if user[2] < price:
            embed = discord.Embed(
                title="❌ Insufficient",
                description=f"You need {ROBUX_ICON}{price} but have {ROBUX_ICON}{user[2]:.2f}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await subtract_robux(ctx.author.id, price)
        
        if item_type == "role" and role_id:
            try:
                role = ctx.guild.get_role(role_id)
                if role:
                    await ctx.author.add_roles(role)
                    embed = discord.Embed(
                        title="✅ Purchase Successful!",
                        description=f"You've purchased **{item_name}**!",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Role", value=f"{role.mention}", inline=True)
                    embed.add_field(name="Cost", value=f"{ROBUX_ICON}{price}", inline=True)
                    embed.add_field(name="New Balance", value=f"{ROBUX_ICON}{user[2] - price:.2f}", inline=True)
                    await ctx.send(embed=embed)
                    await log_command(ctx.author.id, ctx.author.name, "buy", f"item_id: {item_id}, item_name: {item_name}", True)
                else:
                    embed = discord.Embed(title="❌ Role Not Found", color=discord.Color.red())
                    await ctx.send(embed=embed)
                    await add_robux(ctx.author.id, price)
            except Exception as e:
                print(f"Error: {e}")
                embed = discord.Embed(title="❌ Failed", color=discord.Color.red())
                await ctx.send(embed=embed)
                await add_robux(ctx.author.id, price)
        else:
            embed = discord.Embed(
                title="✅ Purchase Successful!",
                description=f"You've purchased **{item_name}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="Item", value=item_name, inline=True)
            embed.add_field(name="Cost", value=f"{ROBUX_ICON}{price}", inline=True)
            embed.add_field(name="New Balance", value=f"{ROBUX_ICON}{user[2] - price:.2f}", inline=True)
            embed.add_field(name="Description", value=description, inline=False)
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "buy", f"item_id: {item_id}, item_name: {item_name}", True)
    
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='addshop')
async def addshop(ctx, item_name: str = None, item_type: str = None, price: float = None, role: discord.Role = None, *, description: str = ""):
    """Add shop item (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not all([item_name, item_type, price]):
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!addshop <name> <type> <price> [@role] [description]`\n\n**Types:** role, item",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        item_type = item_type.lower()
        if item_type not in ['role', 'item']:
            embed = discord.Embed(title="❌ Error", description="Type must be 'role' or 'item'", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        role_id = role.id if role else None
        
        item_id = await add_shop_item(item_name, item_type, price, role_id, description)
        
        embed = discord.Embed(title="✅ Shop Item Added", color=discord.Color.green())
        embed.add_field(name="ID", value=f"`{item_id}`", inline=True)
        embed.add_field(name="Name", value=item_name, inline=True)
        embed.add_field(name="Type", value=item_type, inline=True)
        embed.add_field(name="Price", value=f"{ROBUX_ICON}{price}", inline=True)
        if role:
            embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Description", value=description, inline=False)
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "addshop", f"name: {item_name}, type: {item_type}, price: {price}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='delshop')
async def delshop(ctx, item_id: int = None):
    """Delete shop item (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if item_id is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!delshop <item_id>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        item = await get_shop_item(item_id)
        if not item:
            embed = discord.Embed(title="❌ Item Not Found", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await remove_shop_item(item_id)
        
        embed = discord.Embed(
            title="✅ Shop Item Deleted",
            description=f"**{item[1]}** removed!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "delshop", f"item_id: {item_id}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== MESSAGE ROLES ====================

@bot.command(name='setmsgrole')
async def setmsgrole(ctx, messages: int = None, role: discord.Role = None):
    """Set auto role at message count"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.administrator:
            return
        
        if messages is None or role is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!setmsgrole <messages> <@role>`\n\nExample: `!setmsgrole 500 @Trusted`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if messages < 1:
            embed = discord.Embed(title="❌ Error", description="Messages must be >= 1!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        success = await add_message_role(ctx.guild.id, messages, role.id)
        
        if success:
            embed = discord.Embed(
                title="✅ Message Role Added",
                description=f"{role.mention} at **{messages}** messages!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "setmsgrole", f"messages: {messages}, role: {role.name}", True)
        else:
            embed = discord.Embed(
                title="❌ Error",
                description=f"That message count already has a role!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='delmsgrole')
async def delmsgrole(ctx, role_id: int = None):
    """Delete message role"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.administrator:
            return
        
        if role_id is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!delmsgrole <role_id>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await delete_message_role(role_id)
        
        embed = discord.Embed(
            title="✅ Message Role Deleted",
            description=f"Role ID **{role_id}** removed!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "delmsgrole", f"role_id: {role_id}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='msgroles')
async def msgroles(ctx):
    """View message roles"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        roles = await get_message_roles(ctx.guild.id)
        
        if not roles:
            embed = discord.Embed(
                title="❌ No Message Roles",
                description="Use `!setmsgrole <messages> <@role>` to add one",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title="📊 Message Roles", color=discord.Color.blue())
        
        for role_id, message_count, discord_role_id in roles:
            role = ctx.guild.get_role(discord_role_id)
            role_name = role.mention if role else f"Unknown"
            embed.add_field(
                name=f"ID: {role_id}",
                value=f"**{message_count}** msgs → {role_name}",
                inline=False
            )
        
        embed.set_footer(text="Use !delmsgrole <id> to remove")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "msgroles", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setmsgreq')
async def setmsgreq(ctx, role: discord.Role = None):
    """Set required role for message earnings"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.administrator:
            return
        
        if role is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!setmsgreq <@role>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_msg_req_role(ctx.guild.id, role.id)
        
        embed = discord.Embed(
            title="✅ Requirement Set",
            description=f"Must have {role.mention} to earn from messages!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "setmsgreq", f"role: {role.name}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== GIVEAWAY COMMANDS ====================

@bot.command(name='giveaway')
async def giveaway(ctx, duration: str = None, prize_count: int = None, *, prize_name: str = None):
    """Create giveaway"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if duration is None or prize_count is None or prize_name is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!giveaway <duration> <count> <prize>`\n\nDuration: 1d, 2h, 30m, 60s\n\nExample: `!giveaway 1h 2 50 Robux`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        duration_seconds = parse_duration(duration)
        if duration_seconds is None:
            embed = discord.Embed(title="❌ Invalid Duration", description="Use: 1d, 2h, 30m, 60s", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        giveaway_id = await create_giveaway(ctx.guild.id, ctx.author.id, prize_name, prize_count, duration_seconds)
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY STARTED!",
            description=f"**Prize:** {prize_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Count", value=f"**{prize_count}**", inline=True)
        embed.add_field(name="Duration", value=f"**{duration}**", inline=True)
        embed.add_field(name="Winners", value=f"**{prize_count}** will be selected", inline=False)
        embed.add_field(name="Enter", value="React with 🎉 to this message!", inline=False)
        embed.set_footer(text=f"ID: {giveaway_id}")
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")
        
        await set_giveaway_message_id(giveaway_id, msg.id)
        
        await log_command(ctx.author.id, ctx.author.name, "giveaway", f"duration: {duration}, count: {prize_count}, prize: {prize_name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='genter')
async def genter(ctx):
    """Enter giveaway"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        giveaway = await get_active_giveaway(ctx.guild.id)
        
        if not giveaway:
            embed = discord.Embed(
                title="❌ No Active Giveaway",
                description="There's no giveaway right now!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        giveaway_id = giveaway[0]
        
        already_entered = await user_in_giveaway(giveaway_id, ctx.author.id)
        if already_entered:
            embed = discord.Embed(
                title="❌ Already Entered",
                description="You're already in this giveaway!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        await add_giveaway_entry(giveaway_id, ctx.author.id)
        
        embed = discord.Embed(
            title="✅ Entered!",
            description=f"You've entered!\n\nPrize: **{giveaway[3]}**",
            color=discord.Color.green()
        )
        embed.set_footer(text="Good luck! 🍀")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "genter", f"giveaway_id: {giveaway_id}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='gstatus')
async def gstatus(ctx):
    """Check giveaway status"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        giveaway = await get_active_giveaway(ctx.guild.id)
        
        if not giveaway:
            embed = discord.Embed(
                title="❌ No Active Giveaway",
                description="There's no giveaway right now!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        giveaway_id, guild_id, host_id, prize, prize_count, duration, created_at, ends_at, message_id, status = giveaway
        
        entries = await get_giveaway_entries(giveaway_id)
        
        ends_at_dt = datetime.fromisoformat(ends_at)
        time_left = ends_at_dt - datetime.now()
        
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        seconds = time_left.seconds % 60
        
        embed = discord.Embed(
            title="🎉 Giveaway Status",
            description=f"**Prize:** {prize}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Count", value=f"**{prize_count}**", inline=True)
        embed.add_field(name="Entries", value=f"**{len(entries)}**", inline=True)
        embed.add_field(name="Time Left", value=f"**{hours}h {minutes}m {seconds}s**", inline=True)
        embed.add_field(name="Status", value=f"**{status.upper()}**", inline=False)
        embed.set_footer(text=f"ID: {giveaway_id}")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "gstatus", f"giveaway_id: {giveaway_id}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== ADMIN COMMANDS ====================

@bot.command(name='delmoney')
async def delmoney(ctx, member: discord.Member = None, amount: float = None):
    """Remove money from user (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None or amount is None or amount <= 0:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!delmoney <@member> <amount>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        user = await get_user_data(member.id)
        if not user:
            embed = discord.Embed(title="❌ Error", description=f"{member.name} has no data!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await subtract_robux(member.id, amount)
        
        embed = discord.Embed(
            title="✅ Money Removed",
            description=f"Removed {ROBUX_ICON}{amount} from {member.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="New Balance", value=f"{ROBUX_ICON}{user[2] - amount:.2f}", inline=True)
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "delmoney", f"target: {member.name}, amount: {amount}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='addmoney')
async def addmoney(ctx, member: discord.Member = None, amount: float = None):
    """Add money to user (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None or amount is None or amount <= 0:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!addmoney <@member> <amount>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await create_user(member.id, member.name)
        await add_robux(member.id, amount)
        
        embed = discord.Embed(
            title="✅ Money Added",
            description=f"Added {ROBUX_ICON}{amount} to {member.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "addmoney", f"target: {member.name}, amount: {amount}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='ban')
async def ban(ctx, member: discord.Member = None):
    """Ban user from bot"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!ban <@member>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        if member.id == OWNER_ID:
            await add_warning(ctx.author.id, bot.user.id, "Attempting to ban owner")
            embed = discord.Embed(title="🛡️ Protection", description=f"You cannot ban the owner!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await ban_user(member.id)
        
        embed = discord.Embed(
            title="🚫 User Banned",
            description=f"{member.mention} has been banned from the bot!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "ban", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='unban')
async def unban(ctx, member: discord.Member = None):
    """Unban user from bot"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!unban <@member>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await unban_user(member.id)
        
        embed = discord.Embed(
            title="✅ User Unbanned",
            description=f"{member.mention} has been unbanned!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "unban", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='warn')
async def warn(ctx, member: discord.Member = None, *, reason: str = None):
    """Warn user"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.manage_messages:
            return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!warn <@member> [reason]`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

        if member.id == OWNER_ID:
            await add_warning(ctx.author.id, bot.user.id, "Attempting to warn owner")
            embed = discord.Embed(title="🛡️ Protection", description=f"You cannot warn the owner!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if reason is None:
            reason = "No reason provided"
        
        await add_warning(member.id, ctx.author.id, reason)
        
        warnings = await get_warnings(member.id)
        warning_count = len(warnings) if warnings else 0
        
        embed = discord.Embed(
            title="⚠️ User Warned",
            description=f"{member.mention} has been warned!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
        
        await ctx.send(embed=embed)
        
        try:
            await member.send(embed=discord.Embed(
                title="⚠️ You've been warned",
                description=f"**Reason:** {reason}",
                color=discord.Color.orange()
            ))
        except:
            pass
        
        await log_command(ctx.author.id, ctx.author.name, "warn", f"target: {member.name}, reason: {reason}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='warnings')
async def warnings(ctx, member: discord.Member = None):
    """View warnings"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        warns = await get_warnings(member.id)
        
        if not warns:
            embed = discord.Embed(
                title="✅ No Warnings",
                description=f"{member.name} has no warnings!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title=f"⚠️ {member.name}'s Warnings", color=discord.Color.orange())
        
        for warning in warns:
            warning_id, moderator_id, reason, issued_at = warning
            embed.add_field(
                name=f"ID: {warning_id}",
                value=f"**Reason:** {reason}",
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(warns)}")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "warnings", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='delwarning')
async def delwarning(ctx, member: discord.Member = None, warning_id: int = None):
    """Delete warning"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not ctx.author.guild_permissions.manage_messages:
            return
        
        if member is None or warning_id is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!delwarning <@member> <warn_id>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Note: delete_warning is not in database.py, using clear_warnings instead for now
        await clear_warnings(member.id)
        
        embed = discord.Embed(
            title="✅ Warnings Cleared",
            description=f"All warnings for {member.mention} deleted!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "delwarning", f"target: {member.name}, warning_id: {warning_id}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setrate')
async def setrate(ctx, rate_type: str = None, value: float = None):
    """Set earning rates (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if rate_type is None or value is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!setrate <type> <value>`\n\n**Types:**\n• message_rate\n• invite_rate\n• daily_reward",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        rate_type = rate_type.lower()
        if rate_type not in ['message_rate', 'invite_rate', 'daily_reward']:
            embed = discord.Embed(title="❌ Error", description="Invalid rate type!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await set_rate(rate_type, value)
        
        embed = discord.Embed(
            title="✅ Rate Updated",
            description=f"**{rate_type}** → **{value}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "setrate", f"type: {rate_type}, value: {value}", True)
    except Exception as e:
        print(f"Error: {e}")

# ADD THIS FIXED VERSION OF RESETBALL COMMAND

@bot.command(name='resetball')
async def resetball(ctx, member: discord.Member = None):
    """Reset balance (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            embed = discord.Embed(title="❌ Owner Only", description="Only the bot owner can use this!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            # Reset ALL users
            await ctx.send("⏳ Resetting all balances... This may take a moment...")
            await reset_all_balance()
            
            embed = discord.Embed(
                title="✅ All Balances Reset",
                description="All user balances have been reset to 0!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            print("✅ All balances reset")
            await log_command(ctx.author.id, ctx.author.name, "resetball", "all users", True)
        else:
            # Reset specific user
            await reset_user_balance(member.id)
            
            embed = discord.Embed(
                title="✅ Balance Reset",
                description=f"{member.mention}'s balance has been reset to 0!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            print(f"✅ {member.name}'s balance reset")
            await log_command(ctx.author.id, ctx.author.name, "resetball", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error in resetball: {e}")
        embed = discord.Embed(title="❌ Error", description=f"Error: {str(e)[:100]}", color=discord.Color.red())
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "resetball", "", False, str(e))


@bot.command(name='welcome')
async def welcome(ctx, status: str = None, channel: discord.TextChannel = None, *, message: str = None):
    """Setup welcome messages (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if status is None:
            current_config = await get_welcome_config(ctx.guild.id)
            if current_config:
                embed = discord.Embed(
                    title="✅ Welcome Enabled",
                    description=f"Channel: <#{current_config[0]}>\n\nMessage: {current_config[1]}",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Welcome Disabled",
                    color=discord.Color.red()
                )
            await ctx.send(embed=embed)
            return
        
        status = status.lower()
        if status == "on":
            if channel is None or message is None:
                embed = discord.Embed(
                    title="❌ Usage",
                    description="**Usage:** `!welcome on <#channel> <message>`\n\n**Variables:**\n• {user}\n• {guild}\n• {count}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            await set_welcome_channel(ctx.guild.id, channel.id, message)
            
            embed = discord.Embed(
                title="✅ Welcome Enabled",
                description=f"Channel: {channel.mention}\n\nMessage: {message}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "welcome", "on", True)
        
        elif status == "off":
            await set_welcome_status(ctx.guild.id, False)
            
            embed = discord.Embed(
                title="✅ Welcome Disabled",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "welcome", "off", True)
        
        else:
            embed = discord.Embed(title="❌ Error", description="Status must be 'on' or 'off'", color=discord.Color.red())
            await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='autorole')
async def autorole(ctx, role: discord.Role = None):
    """Set autorole (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if role is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!autorole <@role>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_autorole(ctx.guild.id, role.id)
        
        embed = discord.Embed(
            title="✅ Autorole Set",
            description=f"New members get {role.mention}!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "autorole", f"role: {role.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='addword')
async def addword(ctx, *, word: str = None):
    """Add word to blacklist (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if word is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!addword <word>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await add_blacklist_word(ctx.guild.id, word)
        
        embed = discord.Embed(
            title="✅ Word Blacklisted",
            description=f"`{word}` added!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "addword", f"word: {word}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='removeword')
async def removeword(ctx, *, word: str = None):
    """Remove word from blacklist (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if word is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!removeword <word>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await remove_blacklist_word(ctx.guild.id, word)
        
        embed = discord.Embed(
            title="✅ Word Removed",
            description=f"`{word}` removed!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "removeword", f"word: {word}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='blacklist')
async def blacklist(ctx):
    """View blacklisted words (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        words = await get_blacklist_words(ctx.guild.id)
        
        if not words:
            embed = discord.Embed(
                title="✅ No Blacklisted Words",
                description="No words blacklisted yet!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return
        
        word_list = ", ".join([f"`{w[0]}`" for w in words])
        
        embed = discord.Embed(
            title="🚫 Blacklisted Words",
            description=word_list,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Total: {len(words)}")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "blacklist", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='afk')
async def afk(ctx, *, reason: str = None):
    """Set yourself as AFK"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if reason is None:
            reason = "AFK"
        
        await set_afk(ctx.author.id, reason)
        
        embed = discord.Embed(
            title="⏳ AFK Status Set",
            description=f"You are now AFK!\n\n**Reason:** {reason}",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "afk", f"reason: {reason}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='addadmin')
async def addadmin(ctx, member: discord.Member = None):
    """Add bot admin (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!addadmin <@member>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        success = await add_admin(member.id)
        
        if success is not False:
            embed = discord.Embed(
                title="✅ Bot Admin Added",
                description=f"{member.mention} is now a bot admin!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            await log_command(ctx.author.id, ctx.author.name, "addadmin", f"target: {member.name}", True)
        else:
            embed = discord.Embed(title="❌ Error", description="Already a bot admin!", color=discord.Color.red())
            await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='deladmin')
async def deladmin(ctx, member: discord.Member = None):
    """Remove bot admin (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(title="❌ Usage", description="**Usage:** `!deladmin <@member>`", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await remove_admin(member.id)
        
        embed = discord.Embed(
            title="✅ Bot Admin Removed",
            description=f"{member.mention} is no longer a bot admin!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "deladmin", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='admins')
async def admins(ctx):
    """View all bot admins (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        admins_list = await get_all_admins()
        
        if not admins_list:
            embed = discord.Embed(title="❌ No Admins", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(title="👨‍💼 Bot Admins", color=discord.Color.blue())
        
        for admin_id in admins_list:
            try:
                user = await bot.fetch_user(admin_id)
                embed.add_field(name=user.name, value=f"ID: {admin_id}", inline=True)
            except:
                embed.add_field(name="Unknown", value=f"ID: {admin_id}", inline=True)
        
        embed.set_footer(text="Bot admins can use admin commands")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "admins", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setgamecooldown')
async def setgamecooldown(ctx, seconds: int = None):
    """Change game cooldown (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if seconds is None or seconds < 1:
            current_cooldown = await get_game_cooldown()
            embed = discord.Embed(
                title="❌ Usage",
                description=f"**Usage:** `!setgamecooldown <seconds>`\n\nCurrent: {current_cooldown}s",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_game_cooldown(seconds)
        
        minutes = seconds // 60
        secs = seconds % 60
        
        embed = discord.Embed(
            title="✅ Game Cooldown Updated",
            description=f"Cooldown: **{seconds}s** ({minutes}m {secs}s)",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "setgamecooldown", f"seconds: {seconds}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setmsgcooldown')
async def setmsgcooldown(ctx, seconds: int = None):
    """Change message cooldown (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if seconds is None or seconds < 1:
            current_cooldown = await get_msg_cooldown()
            embed = discord.Embed(
                title="❌ Usage",
                description=f"**Usage:** `!setmsgcooldown <seconds>`\n\nCurrent: {current_cooldown}s",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_msg_cooldown(seconds)
        
        embed = discord.Embed(
            title="✅ Message Cooldown Updated",
            description=f"Users wait **{seconds}s** between message earnings",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "setmsgcooldown", f"seconds: {seconds}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='setlog')
async def setlog(ctx, channel: discord.TextChannel = None):
    """Set bot log channel (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if channel is None:
            channel = ctx.channel
        
        await set_bot_log_channel(channel.id)
        
        embed = discord.Embed(
            title="✅ Bot Log Channel Set",
            description=f"Logs: {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "setlog", f"channel: {channel.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='status')
async def status(ctx):
    """Get bot statistics"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        total_users = await get_total_users()
        total_robux = await get_total_robux_distributed()
        total_messages = await get_total_messages()
        total_invites = await get_total_invites()
        cooldown = await get_game_cooldown()
        
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="👥 Total Users", value=f"**{total_users}**", inline=True)
        embed.add_field(name="💰 Robux Distributed", value=f"**{ROBUX_ICON}{total_robux:.2f}**", inline=True)
        embed.add_field(name="💬 Messages Tracked", value=f"**{total_messages}**", inline=True)
        embed.add_field(name="👥 Total Invites", value=f"**{total_invites}**", inline=True)
        embed.add_field(name="🟢 Bot Status", value="**Online**", inline=True)
        embed.add_field(name="📡 Servers", value=f"**{len(bot.guilds)}**", inline=True)
        embed.add_field(name="⏳ Game Cooldown", value=f"**{cooldown}s**", inline=True)
        embed.set_footer(text="Made with ❤️ for Discord")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "status", "", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== VOICE CHANNEL COMMANDS ====================

@bot.command(name='setvcrate')
async def setvcrate(ctx, amount: float = None):
    """Set VC earning rate (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if not amount or amount <= 0:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!setvcrate <amount>`\n\nThis is PER 5 MINUTES",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await set_vc_rate(ctx.guild.id, amount)
        
        embed = discord.Embed(
            title="✅ VC Rate Updated",
            description=f"Rate: **{ROBUX_ICON}{amount:.2f}** per 5 min",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "setvcrate", f"amount: {amount}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='vcenabled')
async def vc_enabled(ctx, onoff: str = None):
    """Enable/disable VC economy (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if onoff not in ["on", "off"]:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!vcenabled <on/off>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        enabled = onoff.lower() == "on"
        await set_vc_enabled(ctx.guild.id, enabled)
        
        status = "🟢 ENABLED" if enabled else "🔴 DISABLED"
        embed = discord.Embed(
            title=f"✅ VC Economy {status}",
            description=f"VC earning is now {status}!",
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "vcenabled", f"status: {onoff}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='vcrate')
async def vcrate(ctx):
    """Check VC earning rate"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        rate = await get_vc_rate(ctx.guild.id)
        enabled = await get_vc_enabled(ctx.guild.id)
        
        if not enabled:
            embed = discord.Embed(
                title="🔒 VC Economy Disabled",
                description="Voice earning is disabled!",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="🔊 Voice Channel Rate",
                color=discord.Color.blue()
            )
            embed.add_field(name="💰 Rate", value=f"**{ROBUX_ICON}{rate:.2f}** per 5 min", inline=False)
            embed.add_field(name="⏱️ Duration", value="Earn every 5 minutes", inline=False)
            embed.add_field(name="🔇 Muted?", value="❌ No earning if muted/deafened", inline=False)
            embed.set_footer(text="Use !vcstats to see your earnings!")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "vcrate", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='vcstats')
async def vcstats(ctx, member: discord.Member = None):
    """View VC earnings stats"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            member = ctx.author
        
        vc_seconds, vc_earned = await get_user_vc_stats(member.id, ctx.guild.id)
        
        hours = vc_seconds // 3600
        minutes = (vc_seconds % 3600) // 60
        seconds = vc_seconds % 60
        
        embed = discord.Embed(
            title=f"🔊 {member.name}'s VC Stats",
            color=discord.Color.blue()
        )
        embed.add_field(name="💰 Earned", value=f"**{ROBUX_ICON}{vc_earned:.2f}**", inline=True)
        embed.add_field(name="⏱️ Time", value=f"**{hours}h {minutes}m {seconds}s**", inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
        embed.set_footer(text="Keep talking to earn more! 🎙️")
        
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "vcstats", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='resetvc')
async def resetvc(ctx, member: discord.Member = None):
    """Reset VC stats (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if member is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!resetvc <@member>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await reset_vc_stats(member.id, ctx.guild.id)
        
        embed = discord.Embed(
            title="✅ VC Stats Reset",
            description=f"{member.mention}'s stats reset!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "resetvc", f"target: {member.name}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== AI SYSTEM ====================

@bot.command(name='ai')
async def ai(ctx, *, question: str = None):
    """Ask AI"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if question is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!ai <question>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        ai_response = await get_ai_response(question)
        
        if ai_response:
            embed = discord.Embed(
                title="🤖 AI Assistant",
                description=ai_response,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Powered by ZomyHub AI")
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="🤖 AI Assistant",
                description="I don't have an answer for that!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "ai", f"question: {question}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='addai')
async def addai(ctx, *, content: str = None):
    """Add custom AI response (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if content is None or '|' not in content:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!addai <question> | <answer>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        parts = content.split('|', 1)
        question = parts[0].strip()
        answer = parts[1].strip()
        
        if not question or not answer:
            embed = discord.Embed(title="❌ Error", description="Both are required!", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        await add_ai_response(question, answer)
        
        embed = discord.Embed(
            title="✅ AI Response Added",
            description=f"**Q:** {question}\n**A:** {answer}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "addai", f"question: {question}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='delai')
async def delai(ctx, *, question: str = None):
    """Remove AI response (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if question is None:
            embed = discord.Embed(
                title="❌ Usage",
                description="**Usage:** `!delai <question>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        await remove_ai_response(question)
        
        embed = discord.Embed(
            title="✅ AI Response Deleted",
            description=f"Removed: **{question}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "delai", f"question: {question}", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='ailist')
async def ailist(ctx):
    """View custom AI responses"""
    try:
        if not is_authorized_guild(ctx.guild.id):
            return
        
        responses = await get_all_ai_responses()
        
        if not responses:
            embed = discord.Embed(
                title="❌ No Custom AI Responses",
                description="No custom responses yet!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🤖 Custom AI Responses",
            color=discord.Color.blue()
        )
        
        for question, answer in responses[:20]:
            embed.add_field(
                name=f"❓ {question}",
                value=f"**A:** {answer[:100]}{'...' if len(answer) > 100 else ''}",
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(responses)}")
        await ctx.send(embed=embed)
        await log_command(ctx.author.id, ctx.author.name, "ailist", "", True)
    except Exception as e:
        print(f"Error: {e}")

@bot.command(name='aienabled')
async def aienabled(ctx, onoff: str = None):
    """Enable/disable AI (Owner only)"""
    try:
        if ctx.author.id != OWNER_ID:
            return
        
        if not is_authorized_guild(ctx.guild.id):
            return
        
        if onoff not in ["on", "off"]:
            current_status = await get_ai_status()
            status_text = "🟢 ENABLED" if current_status else "🔴 DISABLED"
            embed = discord.Embed(
                title="❌ Usage",
                description=f"**Usage:** `!aienabled <on/off>`\n\nCurrent: {status_text}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        enabled = onoff.lower() == "on"
        await set_ai_status(enabled)
        
        status = "🟢 ENABLED" if enabled else "🔴 DISABLED"
        embed = discord.Embed(
            title=f"✅ AI System {status}",
            description=f"AI is now {status}!",
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        await ctx.send(embed=embed)
        
        await log_command(ctx.author.id, ctx.author.name, "aienabled", f"status: {onoff}", True)
    except Exception as e:
        print(f"Error: {e}")

# ==================== ERROR HANDLER ====================

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❌ Command Not Found",
            description="That command doesn't exist! Use `!help`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You don't have permission!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Arguments",
            description=f"Missing: {error.param}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Bad Argument",
            description="One of your arguments is invalid!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        print(f"Error: {error}")

# ==================== AUTHORIZATION CHECK ====================

def is_authorized_guild(guild_id):
    """Check if guild is authorized to use bot"""
    # You can add a list of authorized guild IDs here
    # For now, allowing all guilds
    return True

# ==================== RUN BOT ====================

if __name__ == "__main__":
    print("🤖 Starting ZomyHub Bot...")
    print("✅ All systems initialized!")
    print("📊 Database connected!")
    print("🎉 Bot is ready!")
    bot.run(TOKEN)