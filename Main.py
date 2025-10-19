import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import os
from datetime import timedelta, datetime
from typing import Optional
import json
import random
import asyncio
import time
import re
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot_start_time = datetime.now()

DB_FILE = "chrisbot_data.db"

message_history = defaultdict(lambda: defaultdict(list))

def init_database():
    """Initialize the database with all required tables"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS custom_commands (
        guild_id TEXT, name TEXT, response TEXT, creator_id TEXT, created_at TEXT,
        PRIMARY KEY (guild_id, name))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS infractions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT,
        type TEXT, reason TEXT, moderator_id TEXT, duration TEXT, timestamp TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
        message_id TEXT PRIMARY KEY, guild_id TEXT, channel_id TEXT, title TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS reaction_role_mappings (
        message_id TEXT, emoji TEXT, role_id TEXT, PRIMARY KEY (message_id, emoji))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id TEXT PRIMARY KEY, log_channel_id TEXT, mod_role_id TEXT,
        admin_role_id TEXT, welcome_channel_id TEXT, welcome_message TEXT,
        goodbye_channel_id TEXT, goodbye_message TEXT, leveling_enabled INTEGER DEFAULT 1,
        suggest_channel_id TEXT, verify_channel_id TEXT, verify_role_id TEXT,
        starboard_channel_id TEXT, starboard_threshold INTEGER DEFAULT 5)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS log_events (
        guild_id TEXT, event_type TEXT, enabled INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id, event_type))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS autoroles (
        guild_id TEXT, role_id TEXT, PRIMARY KEY (guild_id, role_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_levels (
        guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 0,
        last_xp_time TEXT, PRIMARY KEY (guild_id, user_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS level_rewards (
        guild_id TEXT, level INTEGER, role_id TEXT,
        PRIMARY KEY (guild_id, level))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (
        channel_id TEXT PRIMARY KEY, guild_id TEXT, user_id TEXT,
        ticket_number INTEGER, created_at TEXT, status TEXT DEFAULT 'open')''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS ticket_settings (
        guild_id TEXT PRIMARY KEY, category_id TEXT, ticket_counter INTEGER DEFAULT 0)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT,
        quote TEXT, author TEXT, added_by TEXT, timestamp TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, channel_id TEXT,
        remind_time TEXT, message TEXT, created_at TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT,
        suggestion TEXT, message_id TEXT, status TEXT DEFAULT 'pending', timestamp TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS mutes (
        guild_id TEXT, user_id TEXT, muted_until TEXT,
        PRIMARY KEY (guild_id, user_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_settings (
        guild_id TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 0,
        spam_enabled INTEGER DEFAULT 1,
        links_enabled INTEGER DEFAULT 0,
        invites_enabled INTEGER DEFAULT 1,
        caps_enabled INTEGER DEFAULT 0,
        mentions_enabled INTEGER DEFAULT 0,
        words_enabled INTEGER DEFAULT 0,
        emoji_enabled INTEGER DEFAULT 0,
        duplicate_enabled INTEGER DEFAULT 0,
        spam_threshold INTEGER DEFAULT 5,
        spam_interval INTEGER DEFAULT 5,
        caps_threshold INTEGER DEFAULT 70,
        mentions_threshold INTEGER DEFAULT 5,
        emoji_threshold INTEGER DEFAULT 10,
        default_punishment TEXT DEFAULT 'warn',
        log_channel_id TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_banned_words (
        guild_id TEXT, word TEXT, PRIMARY KEY (guild_id, word))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_whitelist (
        guild_id TEXT, link TEXT, PRIMARY KEY (guild_id, link))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_immune_roles (
        guild_id TEXT, role_id TEXT, PRIMARY KEY (guild_id, role_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_immune_channels (
        guild_id TEXT, channel_id TEXT, PRIMARY KEY (guild_id, channel_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT, user_id TEXT, violation_type TEXT,
        action_taken TEXT, timestamp TEXT, details TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS automod_user_violations (
        guild_id TEXT, user_id TEXT, violation_count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS economy (
        guild_id TEXT, user_id TEXT, balance INTEGER DEFAULT 0,
        last_daily TEXT, PRIMARY KEY (guild_id, user_id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT,
        name TEXT, datetime TEXT, description TEXT, created_by TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT,
        content TEXT, status TEXT DEFAULT 'pending', timestamp TEXT)''')
    
    conn.commit()
    conn.close()

init_database()

def get_db():
    return sqlite3.connect(DB_FILE)

async def log_event(guild_id, event_type, embed):
    """Log events to the configured log channel"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT log_channel_id FROM guild_settings WHERE guild_id = ?', (str(guild_id),))
    result = cursor.fetchone()
    
    if result and result[0]:
        cursor.execute('SELECT enabled FROM log_events WHERE guild_id = ? AND event_type = ?',
                      (str(guild_id), event_type))
        event_check = cursor.fetchone()
        
        if not event_check or event_check[0] == 1:
            try:
                channel = bot.get_channel(int(result[0]))
                if channel:
                    await channel.send(embed=embed)
            except:
                pass
    conn.close()

async def log_automod_action(guild_id, user_id, violation_type, action_taken, details=""):
    """Log auto-moderation actions to database and channel"""
    conn = get_db()
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    cursor.execute('''INSERT INTO automod_violations 
                   (guild_id, user_id, violation_type, action_taken, timestamp, details)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                 (str(guild_id), str(user_id), violation_type, action_taken, timestamp, details))
    
    cursor.execute('''INSERT INTO automod_user_violations (guild_id, user_id, violation_count)
                   VALUES (?, ?, 1)
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET violation_count = violation_count + 1''',
                 (str(guild_id), str(user_id)))
    
    conn.commit()
    
    cursor.execute('SELECT log_channel_id FROM automod_settings WHERE guild_id = ?', (str(guild_id),))
    result = cursor.fetchone()
    
    if result and result[0]:
        try:
            channel = bot.get_channel(int(result[0]))
            if channel:
                embed = discord.Embed(
                    title="🛡️ Auto-Moderation Action",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                guild = bot.get_guild(int(guild_id))
                user = guild.get_member(int(user_id)) if guild else None
                embed.add_field(name="User", value=user.mention if user else f"<@{user_id}>", inline=True)
                embed.add_field(name="Violation", value=violation_type, inline=True)
                embed.add_field(name="Action", value=action_taken, inline=True)
                if details:
                    embed.add_field(name="Details", value=details[:1024], inline=False)
                await channel.send(embed=embed)
        except:
            pass
    
    conn.close()

def check_automod_immunity(guild_id, member, channel_id):
    """Check if a member or channel is immune to auto-moderation"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT role_id FROM automod_immune_roles WHERE guild_id = ?', (str(guild_id),))
    immune_roles = [int(row[0]) for row in cursor.fetchall()]
    
    if any(role.id in immune_roles for role in member.roles):
        conn.close()
        return True
    
    cursor.execute('SELECT channel_id FROM automod_immune_channels WHERE guild_id = ?', (str(guild_id),))
    immune_channels = [int(row[0]) for row in cursor.fetchall()]
    
    conn.close()
    return int(channel_id) in immune_channels

async def automod_punish(member, violation_type, punishment_type, details=""):
    """Execute auto-moderation punishment"""
    try:
        if punishment_type == "warn":
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO infractions 
                           (guild_id, user_id, type, reason, moderator_id, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                         (str(member.guild.id), str(member.id), 'warn', 
                          f'Auto-mod: {violation_type}', str(bot.user.id), datetime.now().isoformat()))
            conn.commit()
            conn.close()
            try:
                await member.send(f"⚠️ You have been warned in **{member.guild.name}** for: {violation_type}")
            except:
                pass
        elif punishment_type == "mute":
            try:
                await member.timeout(timedelta(minutes=10), reason=f"Auto-mod: {violation_type}")
            except:
                pass
        elif punishment_type == "kick":
            try:
                await member.send(f"👢 You have been kicked from **{member.guild.name}** for: {violation_type}")
            except:
                pass
            await member.kick(reason=f"Auto-mod: {violation_type}")
        elif punishment_type == "ban":
            try:
                await member.send(f"🔨 You have been banned from **{member.guild.name}** for: {violation_type}")
            except:
                pass
            await member.ban(reason=f"Auto-mod: {violation_type}")
    except Exception as e:
        print(f"Error in automod_punish: {e}")

async def check_automod(message):
    """Main auto-moderation check function"""
    if message.author.bot or not message.guild:
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM automod_settings WHERE guild_id = ?', (str(message.guild.id),))
    settings = cursor.fetchone()
    
    if not settings or settings[1] == 0:
        conn.close()
        return False
    
    if check_automod_immunity(message.guild.id, message.author, message.channel.id):
        conn.close()
        return False
    
    enabled, spam_en, links_en, invites_en, caps_en, mentions_en, words_en, emoji_en, dup_en = settings[1:10]
    spam_thresh, spam_int, caps_thresh, ment_thresh, emoji_thresh = settings[10:15]
    punishment = settings[15]
    
    content = message.content
    
    if spam_en:
        user_id = str(message.author.id)
        guild_id = str(message.guild.id)
        current_time = time.time()
        message_history[guild_id][user_id].append(current_time)
        message_history[guild_id][user_id] = [t for t in message_history[guild_id][user_id] if current_time - t < spam_int]
        
        if len(message_history[guild_id][user_id]) > spam_thresh:
            await message.delete()
            await log_automod_action(message.guild.id, message.author.id, "Spam", punishment, 
                                    f"{len(message_history[guild_id][user_id])} messages in {spam_int}s")
            await automod_punish(message.author, "Spam", punishment)
            conn.close()
            return True
    
    if invites_en:
        invite_pattern = r'(discord\.gg|discord\.com\/invite|discordapp\.com\/invite)\/[a-zA-Z0-9]+'
        if re.search(invite_pattern, content, re.IGNORECASE):
            await message.delete()
            await log_automod_action(message.guild.id, message.author.id, "Discord Invite", punishment)
            await automod_punish(message.author, "Discord Invite", punishment)
            conn.close()
            return True
    
    if links_en:
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, content)
        if urls:
            cursor.execute('SELECT link FROM automod_whitelist WHERE guild_id = ?', (str(message.guild.id),))
            whitelist = [row[0] for row in cursor.fetchall()]
            
            if not any(wl in url for url in urls for wl in whitelist):
                await message.delete()
                await log_automod_action(message.guild.id, message.author.id, "Unauthorized Link", punishment)
                await automod_punish(message.author, "Unauthorized Link", punishment)
                conn.close()
                return True
    
    if caps_en and len(content) > 10:
        caps_count = sum(1 for c in content if c.isupper())
        caps_percent = (caps_count / len(content)) * 100
        if caps_percent > caps_thresh:
            await message.delete()
            await log_automod_action(message.guild.id, message.author.id, "Excessive Caps", punishment, 
                                    f"{int(caps_percent)}% caps")
            await automod_punish(message.author, "Excessive Caps", punishment)
            conn.close()
            return True
    
    if mentions_en:
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count > ment_thresh:
            await message.delete()
            await log_automod_action(message.guild.id, message.author.id, "Mass Mentions", punishment, 
                                    f"{mention_count} mentions")
            await automod_punish(message.author, "Mass Mentions", punishment)
            conn.close()
            return True
    
    if words_en:
        cursor.execute('SELECT word FROM automod_banned_words WHERE guild_id = ?', (str(message.guild.id),))
        banned_words = [row[0].lower() for row in cursor.fetchall()]
        content_lower = content.lower()
        
        for word in banned_words:
            if word in content_lower:
                await message.delete()
                await log_automod_action(message.guild.id, message.author.id, "Banned Word", punishment, 
                                        f"Word: {word}")
                await automod_punish(message.author, "Banned Word", punishment)
                conn.close()
                return True
    
    if emoji_en:
        emoji_count = len(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', content))
        emoji_count += len(re.findall(r'[\U0001F300-\U0001F9FF]', content))
        
        if emoji_count > emoji_thresh:
            await message.delete()
            await log_automod_action(message.guild.id, message.author.id, "Emoji Spam", punishment, 
                                    f"{emoji_count} emojis")
            await automod_punish(message.author, "Emoji Spam", punishment)
            conn.close()
            return True
    
    if dup_en:
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        
        if not hasattr(bot, 'duplicate_tracker'):
            bot.duplicate_tracker = defaultdict(lambda: defaultdict(list))
        
        bot.duplicate_tracker[guild_id][user_id].append((content, time.time()))
        bot.duplicate_tracker[guild_id][user_id] = [
            (msg, t) for msg, t in bot.duplicate_tracker[guild_id][user_id] 
            if time.time() - t < 30
        ]
        
        recent_messages = [msg for msg, _ in bot.duplicate_tracker[guild_id][user_id]]
        if recent_messages.count(content) >= 3:
            await message.delete()
            await log_automod_action(message.guild.id, message.author.id, "Duplicate Text", punishment)
            await automod_punish(message.author, "Duplicate Text", punishment)
            conn.close()
            return True
    
    conn.close()
    return False

@bot.event
async def on_ready():
    print(f'🤖 {bot.user} is now online!')
    print(f'🔧 Chris-bot is ready to moderate!')
    print(f'📊 Using database: {DB_FILE}')
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')
    check_reminders.start()
    check_mutes.start()

@bot.event
async def on_member_join(member):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT welcome_channel_id, welcome_message FROM guild_settings WHERE guild_id = ?',
                  (str(member.guild.id),))
    result = cursor.fetchone()
    
    if result and result[0] and result[1]:
        channel = bot.get_channel(int(result[0]))
        if channel:
            message = result[1].replace('{user}', member.mention).replace('{server}', member.guild.name)
            await channel.send(message)
    
    cursor.execute('SELECT role_id FROM autoroles WHERE guild_id = ?', (str(member.guild.id),))
    autoroles = cursor.fetchall()
    for (role_id,) in autoroles:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
    conn.close()
    
    embed = discord.Embed(title="👋 Member Joined", color=discord.Color.green())
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    await log_event(member.guild.id, 'member_join', embed)

@bot.event
async def on_member_remove(member):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT goodbye_channel_id, goodbye_message FROM guild_settings WHERE guild_id = ?',
                  (str(member.guild.id),))
    result = cursor.fetchone()
    
    if result and result[0] and result[1]:
        channel = bot.get_channel(int(result[0]))
        if channel:
            message = result[1].replace('{user}', str(member)).replace('{server}', member.guild.name)
            await channel.send(message)
    conn.close()
    
    embed = discord.Embed(title="👋 Member Left", color=discord.Color.red())
    embed.add_field(name="User", value=str(member), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    await log_event(member.guild.id, 'member_leave', embed)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.orange())
    embed.add_field(name="Author", value=message.author.mention, inline=True)
    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="Content", value=message.content[:1024] if message.content else "No content", inline=False)
    await log_event(message.guild.id, 'message_delete', embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.blue())
    embed.add_field(name="Author", value=before.author.mention, inline=True)
    embed.add_field(name="Channel", value=before.channel.mention, inline=True)
    embed.add_field(name="Before", value=before.content[:512] if before.content else "No content", inline=False)
    embed.add_field(name="After", value=after.content[:512] if after.content else "No content", inline=False)
    await log_event(before.guild.id, 'message_edit', embed)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    if await check_automod(message):
        return
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT leveling_enabled FROM guild_settings WHERE guild_id = ?', (str(message.guild.id),))
    result = cursor.fetchone()
    
    if not result or result[0] == 1:
        cursor.execute('SELECT xp, level, last_xp_time FROM user_levels WHERE guild_id = ? AND user_id = ?',
                      (str(message.guild.id), str(message.author.id)))
        user_data = cursor.fetchone()
        
        current_time = datetime.now()
        can_gain_xp = True
        
        if user_data and user_data[2]:
            last_xp = datetime.fromisoformat(user_data[2])
            if (current_time - last_xp).total_seconds() < 60:
                can_gain_xp = False
        
        if can_gain_xp:
            xp_gain = random.randint(15, 25)
            if user_data:
                new_xp = user_data[0] + xp_gain
                current_level = user_data[1]
                new_level = int(new_xp ** 0.5 / 10)
                
                cursor.execute('''UPDATE user_levels SET xp = ?, level = ?, last_xp_time = ?
                               WHERE guild_id = ? AND user_id = ?''',
                             (new_xp, new_level, current_time.isoformat(), str(message.guild.id), str(message.author.id)))
                
                if new_level > current_level:
                    await message.channel.send(f"🎉 {message.author.mention} leveled up to **Level {new_level}**!")
                    
                    cursor.execute('SELECT role_id FROM level_rewards WHERE guild_id = ? AND level = ?',
                                 (str(message.guild.id), new_level))
                    reward = cursor.fetchone()
                    if reward:
                        role = message.guild.get_role(int(reward[0]))
                        if role:
                            await message.author.add_roles(role)
                            await message.channel.send(f"🎁 {message.author.mention} earned the {role.mention} role!")
            else:
                cursor.execute('''INSERT INTO user_levels (guild_id, user_id, xp, level, last_xp_time)
                               VALUES (?, ?, ?, ?, ?)''',
                             (str(message.guild.id), str(message.author.id), xp_gain, 0, current_time.isoformat()))
        
        conn.commit()
    conn.close()
    
    if message.content.startswith("!"):
        command_name = message.content[1:].split()[0]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT response FROM custom_commands WHERE guild_id = ? AND name = ?',
                      (str(message.guild.id), command_name))
        result = cursor.fetchone()
        conn.close()
        if result:
            await message.channel.send(result[0])
    
    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT role_id FROM reaction_role_mappings
                   WHERE message_id = ? AND emoji = ?''',
                 (str(payload.message_id), str(payload.emoji)))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(int(result[0]))
        if role:
            try:
                member = await guild.fetch_member(payload.user_id)
                if member:
                    await member.add_roles(role)
            except:
                pass

@bot.event
async def on_raw_reaction_remove(payload):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT role_id FROM reaction_role_mappings
                   WHERE message_id = ? AND emoji = ?''',
                 (str(payload.message_id), str(payload.emoji)))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(int(result[0]))
        if role:
            try:
                member = await guild.fetch_member(payload.user_id)
                if member:
                    await member.remove_roles(role)
            except:
                pass

@tasks.loop(minutes=1)
async def check_reminders():
    conn = get_db()
    cursor = conn.cursor()
    current_time = datetime.now()
    
    cursor.execute('SELECT id, user_id, channel_id, message FROM reminders WHERE remind_time <= ?',
                  (current_time.isoformat(),))
    reminders = cursor.fetchall()
    
    for reminder_id, user_id, channel_id, message in reminders:
        try:
            channel = bot.get_channel(int(channel_id))
            if channel:
                await channel.send(f"⏰ <@{user_id}> Reminder: {message}")
        except:
            pass
        cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
    
    conn.commit()
    conn.close()

@tasks.loop(minutes=1)
async def check_mutes():
    conn = get_db()
    cursor = conn.cursor()
    current_time = datetime.now()
    
    cursor.execute('SELECT guild_id, user_id FROM mutes WHERE muted_until <= ?',
                  (current_time.isoformat(),))
    mutes = cursor.fetchall()
    
    for guild_id, user_id in mutes:
        try:
            guild = bot.get_guild(int(guild_id))
            if guild:
                member = await guild.fetch_member(int(user_id))
                if member and member.timed_out_until:
                    await member.timeout(None)
        except:
            pass
        cursor.execute('DELETE FROM mutes WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    
    conn.commit()
    conn.close()

@bot.tree.command(name="rules", description="Display War of Peaks Discord & In-Game Rules")
async def rules(interaction: discord.Interaction):
    embed1 = discord.Embed(
        title="📜 War of Peaks Discord Rules",
        description="Welcome to War of Peaks Discord Rules. To keep this place fun, safe, and drama free, here are our simple server rules:",
        color=discord.Color.blue()
    )
    
    embed1.add_field(
        name="🤝 Respect Each Other",
        value="We're all here to enjoy the game. No bullying, harassment, spamming, or stirring up drama. If someone asks you to stop, please respect that.",
        inline=False
    )
    
    embed1.add_field(
        name="🔞 Keep It Family-Friendly",
        value="No NSFW content, gore, or shock material, this also applies to nicknames, avatars, and emojis. Friendly jokes are fine, but know the limits.",
        inline=False
    )
    
    embed1.add_field(
        name="🗣️ No Hate or Discrimination",
        value="Racism, sexism, or any form of hate speech or offensive symbols are not tolerated. Keep it positive, jokes are alright but with some clear borderlines.",
        inline=False
    )
    
    embed1.add_field(
        name="🔒 Privacy Matters",
        value="Don't share personal details (your own or others'). This includes photos, addresses, private chats, or exact locations. Even if it's \"public online,\" leave it out.",
        inline=False
    )
    
    embed1.add_field(
        name="#️⃣ Stay on Topic",
        value="We're here to talk about the game and have fun. Politics, religion, or other debates are okay but we highly discourage them in heated or fragile situations.",
        inline=False
    )
    
    embed1.add_field(
        name="🏷️ No Unapproved Promotions",
        value="Posting other servers, streams, or socials is only allowed if leadership says so.",
        inline=False
    )
    
    embed1.add_field(
        name="🤗 Honesty Above All",
        value="Don't fake your role, spending type, or mess with forms. It breaks trust and can get you removed fast.",
        inline=False
    )
    
    embed2 = discord.Embed(
        title="⚔️ War of Peaks In-game Rules",
        description="Welcome to War of Peaks In-game Rules. To keep this place fun, safe, and drama free here are our rules if you want to stay:",
        color=discord.Color.gold()
    )
    
    embed2.add_field(
        name="🤝 Alliance Diplomacy",
        value="All members must remain friendly toward other alliances unless Rank 4s (R4) or Leaders (R5) instruct otherwise. No member should provoke or harass other alliances without leadership approval.",
        inline=False
    )
    
    embed2.add_field(
        name="🗣️ Player Conduct",
        value="Every player, whether in our alliance or outside of it, must be treated with respect at all times. Insults, harassment, or toxic behavior will not be tolerated under any circumstances.",
        inline=False
    )
    
    embed2.add_field(
        name="👨‍👩‍👧‍👦 Respecting Families",
        value="Families within the alliance are to be respected and never disrespected. Causing drama or showing disrespect toward family groups or members is strictly prohibited.",
        inline=False
    )
    
    embed2.add_field(
        name="🛡️ Alliance Unity",
        value="Members are expected to support one another and help maintain a positive and cooperative environment. Any internal conflicts must be handled respectfully, and leadership will step in when necessary.",
        inline=False
    )
    
    embed2.add_field(
        name="🎖️ Chain of Command",
        value="The guidance of R4s and Leaders must always be followed. If there is any uncertainty about diplomacy, wars, or actions toward other alliances, members should seek clarification from leadership before acting.",
        inline=False
    )
    
    await interaction.response.send_message(embeds=[embed1, embed2])

automod = app_commands.Group(name="automod", description="Auto-moderation system commands")

@automod.command(name="setup", description="Initialize the auto-moderation system")
@app_commands.checks.has_permissions(administrator=True)
async def automod_setup(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO automod_settings (guild_id, enabled)
                   VALUES (?, 1)''', (str(interaction.guild_id),))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(
        title="🛡️ Auto-Moderation Setup Complete",
        description="Auto-moderation has been initialized! Use `/automod config` to view settings.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@automod.command(name="config", description="View auto-moderation configuration")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_config(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM automod_settings WHERE guild_id = ?', (str(interaction.guild_id),))
    settings = cursor.fetchone()
    conn.close()
    
    if not settings:
        await interaction.response.send_message("❌ Auto-moderation is not set up. Use `/automod setup` first.", ephemeral=True)
        return
    
    embed = discord.Embed(title="🛡️ Auto-Moderation Configuration", color=discord.Color.blue())
    embed.add_field(name="Status", value="✅ Enabled" if settings[1] else "❌ Disabled", inline=False)
    embed.add_field(name="Spam Filter", value="✅" if settings[2] else "❌", inline=True)
    embed.add_field(name="Link Filter", value="✅" if settings[3] else "❌", inline=True)
    embed.add_field(name="Invite Filter", value="✅" if settings[4] else "❌", inline=True)
    embed.add_field(name="Caps Filter", value="✅" if settings[5] else "❌", inline=True)
    embed.add_field(name="Mention Filter", value="✅" if settings[6] else "❌", inline=True)
    embed.add_field(name="Word Filter", value="✅" if settings[7] else "❌", inline=True)
    embed.add_field(name="Emoji Filter", value="✅" if settings[8] else "❌", inline=True)
    embed.add_field(name="Duplicate Filter", value="✅" if settings[9] else "❌", inline=True)
    embed.add_field(name="Default Punishment", value=settings[15].upper(), inline=False)
    
    await interaction.response.send_message(embed=embed)

@automod.command(name="toggle", description="Enable or disable auto-moderation filters")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(
    filter="The filter to toggle",
    enabled="Enable or disable the filter"
)
@app_commands.choices(filter=[
    app_commands.Choice(name="Spam", value="spam"),
    app_commands.Choice(name="Links", value="links"),
    app_commands.Choice(name="Invites", value="invites"),
    app_commands.Choice(name="Caps", value="caps"),
    app_commands.Choice(name="Mentions", value="mentions"),
    app_commands.Choice(name="Words", value="words"),
    app_commands.Choice(name="Emoji", value="emoji"),
    app_commands.Choice(name="Duplicate", value="duplicate")
])
async def automod_toggle(interaction: discord.Interaction, filter: str, enabled: bool):
    conn = get_db()
    cursor = conn.cursor()
    
    filter_map = {
        "spam": "spam_enabled",
        "links": "links_enabled",
        "invites": "invites_enabled",
        "caps": "caps_enabled",
        "mentions": "mentions_enabled",
        "words": "words_enabled",
        "emoji": "emoji_enabled",
        "duplicate": "duplicate_enabled"
    }
    
    column = filter_map.get(filter)
    if column:
        cursor.execute(f'UPDATE automod_settings SET {column} = ? WHERE guild_id = ?',
                      (1 if enabled else 0, str(interaction.guild_id)))
        conn.commit()
    conn.close()
    
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"✅ {filter.capitalize()} filter has been **{status}**.")

@automod.command(name="settings", description="Adjust auto-moderation thresholds")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(
    spam_threshold="Number of messages to trigger spam filter (default: 5)",
    spam_interval="Time window in seconds for spam detection (default: 5)",
    caps_threshold="Percentage of caps to trigger filter (default: 70)",
    mentions_threshold="Number of mentions to trigger filter (default: 5)",
    emoji_threshold="Number of emojis to trigger filter (default: 10)"
)
async def automod_settings(
    interaction: discord.Interaction,
    spam_threshold: Optional[int] = None,
    spam_interval: Optional[int] = None,
    caps_threshold: Optional[int] = None,
    mentions_threshold: Optional[int] = None,
    emoji_threshold: Optional[int] = None
):
    conn = get_db()
    cursor = conn.cursor()
    
    updates = []
    if spam_threshold is not None:
        updates.append(("spam_threshold", spam_threshold))
    if spam_interval is not None:
        updates.append(("spam_interval", spam_interval))
    if caps_threshold is not None:
        updates.append(("caps_threshold", caps_threshold))
    if mentions_threshold is not None:
        updates.append(("mentions_threshold", mentions_threshold))
    if emoji_threshold is not None:
        updates.append(("emoji_threshold", emoji_threshold))
    
    for column, value in updates:
        cursor.execute(f'UPDATE automod_settings SET {column} = ? WHERE guild_id = ?',
                      (value, str(interaction.guild_id)))
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message("✅ Auto-moderation settings have been updated!")

@automod.command(name="punishment", description="Set the default punishment type")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(punishment="The default punishment for violations")
@app_commands.choices(punishment=[
    app_commands.Choice(name="Warn", value="warn"),
    app_commands.Choice(name="Mute (10 min)", value="mute"),
    app_commands.Choice(name="Kick", value="kick"),
    app_commands.Choice(name="Ban", value="ban")
])
async def automod_punishment(interaction: discord.Interaction, punishment: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE automod_settings SET default_punishment = ? WHERE guild_id = ?',
                  (punishment, str(interaction.guild_id)))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Default punishment set to: **{punishment.upper()}**")

@automod.command(name="words_add", description="Add a banned word")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(word="The word to ban")
async def automod_words_add(interaction: discord.Interaction, word: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO automod_banned_words (guild_id, word) VALUES (?, ?)',
                      (str(interaction.guild_id), word.lower()))
        conn.commit()
        await interaction.response.send_message(f"✅ Added `{word}` to banned words list.")
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"❌ `{word}` is already in the banned words list.", ephemeral=True)
    conn.close()

@automod.command(name="words_remove", description="Remove a banned word")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(word="The word to unban")
async def automod_words_remove(interaction: discord.Interaction, word: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM automod_banned_words WHERE guild_id = ? AND word = ?',
                  (str(interaction.guild_id), word.lower()))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Removed `{word}` from banned words list.")

@automod.command(name="words_list", description="List all banned words")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_words_list(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT word FROM automod_banned_words WHERE guild_id = ?', (str(interaction.guild_id),))
    words = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not words:
        await interaction.response.send_message("📝 No banned words configured.", ephemeral=True)
        return
    
    embed = discord.Embed(title="🚫 Banned Words", color=discord.Color.red())
    embed.description = ", ".join(f"`{word}`" for word in words)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@automod.command(name="words_clear", description="Clear all banned words")
@app_commands.checks.has_permissions(administrator=True)
async def automod_words_clear(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM automod_banned_words WHERE guild_id = ?', (str(interaction.guild_id),))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message("✅ Cleared all banned words.")

@automod.command(name="whitelist_add", description="Add a whitelisted link")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(link="The link domain to whitelist (e.g., youtube.com)")
async def automod_whitelist_add(interaction: discord.Interaction, link: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO automod_whitelist (guild_id, link) VALUES (?, ?)',
                      (str(interaction.guild_id), link))
        conn.commit()
        await interaction.response.send_message(f"✅ Added `{link}` to whitelist.")
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"❌ `{link}` is already whitelisted.", ephemeral=True)
    conn.close()

@automod.command(name="whitelist_remove", description="Remove a whitelisted link")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(link="The link to remove from whitelist")
async def automod_whitelist_remove(interaction: discord.Interaction, link: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM automod_whitelist WHERE guild_id = ? AND link = ?',
                  (str(interaction.guild_id), link))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Removed `{link}` from whitelist.")

@automod.command(name="whitelist_list", description="List all whitelisted links")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_whitelist_list(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT link FROM automod_whitelist WHERE guild_id = ?', (str(interaction.guild_id),))
    links = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not links:
        await interaction.response.send_message("📝 No whitelisted links configured.", ephemeral=True)
        return
    
    embed = discord.Embed(title="✅ Whitelisted Links", color=discord.Color.green())
    embed.description = "\n".join(f"`{link}`" for link in links)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@automod.command(name="immune_role", description="Make a role immune to auto-moderation")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(role="The role to make immune")
async def automod_immune_role(interaction: discord.Interaction, role: discord.Role):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO automod_immune_roles (guild_id, role_id) VALUES (?, ?)',
                      (str(interaction.guild_id), str(role.id)))
        conn.commit()
        await interaction.response.send_message(f"✅ {role.mention} is now immune to auto-moderation.")
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"❌ {role.mention} is already immune.", ephemeral=True)
    conn.close()

@automod.command(name="immune_channel", description="Make a channel immune to auto-moderation")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="The channel to make immune")
async def automod_immune_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO automod_immune_channels (guild_id, channel_id) VALUES (?, ?)',
                      (str(interaction.guild_id), str(channel.id)))
        conn.commit()
        await interaction.response.send_message(f"✅ {channel.mention} is now immune to auto-moderation.")
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"❌ {channel.mention} is already immune.", ephemeral=True)
    conn.close()

@automod.command(name="immune_list", description="List all immune roles and channels")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_immune_list(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT role_id FROM automod_immune_roles WHERE guild_id = ?', (str(interaction.guild_id),))
    roles = [f"<@&{row[0]}>" for row in cursor.fetchall()]
    
    cursor.execute('SELECT channel_id FROM automod_immune_channels WHERE guild_id = ?', (str(interaction.guild_id),))
    channels = [f"<#{row[0]}>" for row in cursor.fetchall()]
    
    conn.close()
    
    embed = discord.Embed(title="🛡️ Auto-Mod Immunity List", color=discord.Color.blue())
    embed.add_field(name="Immune Roles", value="\n".join(roles) if roles else "None", inline=False)
    embed.add_field(name="Immune Channels", value="\n".join(channels) if channels else "None", inline=False)
    
    await interaction.response.send_message(embed=embed)

@automod.command(name="immune_remove", description="Remove immunity from a role or channel")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    role="The role to remove immunity from",
    channel="The channel to remove immunity from"
)
async def automod_immune_remove(interaction: discord.Interaction, role: Optional[discord.Role] = None, channel: Optional[discord.TextChannel] = None):
    if not role and not channel:
        await interaction.response.send_message("❌ Please specify a role or channel.", ephemeral=True)
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    messages = []
    
    if role:
        cursor.execute('DELETE FROM automod_immune_roles WHERE guild_id = ? AND role_id = ?',
                      (str(interaction.guild_id), str(role.id)))
        messages.append(f"✅ Removed immunity from {role.mention}.")
    
    if channel:
        cursor.execute('DELETE FROM automod_immune_channels WHERE guild_id = ? AND channel_id = ?',
                      (str(interaction.guild_id), str(channel.id)))
        messages.append(f"✅ Removed immunity from {channel.mention}.")
    
    msg = "\n".join(messages)
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(msg)

@automod.command(name="logs", description="View auto-moderation logs")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(limit="Number of recent logs to view (default: 10)")
async def automod_logs(interaction: discord.Interaction, limit: int = 10):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT user_id, violation_type, action_taken, timestamp, details
                   FROM automod_violations WHERE guild_id = ?
                   ORDER BY id DESC LIMIT ?''',
                  (str(interaction.guild_id), min(limit, 25)))
    logs = cursor.fetchall()
    conn.close()
    
    if not logs:
        await interaction.response.send_message("📝 No auto-moderation logs found.", ephemeral=True)
        return
    
    embed = discord.Embed(title="📊 Auto-Moderation Logs", color=discord.Color.orange())
    
    for user_id, violation, action, timestamp, details in logs:
        time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M")
        value = f"**Action:** {action}\n**Time:** {time_str}"
        if details:
            value += f"\n**Details:** {details[:100]}"
        embed.add_field(
            name=f"👤 <@{user_id}> - {violation}",
            value=value,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@automod.command(name="reset", description="Reset violations count for a user")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(user="The user to reset violations for")
async def automod_reset(interaction: discord.Interaction, user: discord.Member):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM automod_user_violations WHERE guild_id = ? AND user_id = ?',
                  (str(interaction.guild_id), str(user.id)))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Reset violations for {user.mention}.")

bot.tree.add_command(automod)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(user="The member to kick", reason="Reason for kicking")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
    if user.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ You cannot kick this user (role hierarchy).", ephemeral=True)
        return
    
    try:
        await user.send(f"👢 You have been kicked from **{interaction.guild.name}**\nReason: {reason}")
    except:
        pass
    
    await user.kick(reason=reason)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO infractions (guild_id, user_id, type, reason, moderator_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                 (str(interaction.guild_id), str(user.id), 'kick', reason, 
                  str(interaction.user.id), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(title="👢 Member Kicked", color=discord.Color.orange())
    embed.add_field(name="User", value=user.mention, inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    await interaction.response.send_message(embed=embed)
    await log_event(interaction.guild_id, 'moderation', embed)

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(user="The member to ban", reason="Reason for banning")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
    if user.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ You cannot ban this user (role hierarchy).", ephemeral=True)
        return
    
    try:
        await user.send(f"🔨 You have been banned from **{interaction.guild.name}**\nReason: {reason}")
    except:
        pass
    
    await user.ban(reason=reason)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO infractions (guild_id, user_id, type, reason, moderator_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                 (str(interaction.guild_id), str(user.id), 'ban', reason, 
                  str(interaction.user.id), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
    embed.add_field(name="User", value=str(user), inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    await interaction.response.send_message(embed=embed)
    await log_event(interaction.guild_id, 'moderation', embed)

@bot.tree.command(name="unban", description="Unban a user by ID")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(user_id="The ID of the user to unban")
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"✅ Unbanned **{user}**")
    except:
        await interaction.response.send_message("❌ Could not find or unban that user.", ephemeral=True)

@bot.tree.command(name="mute", description="Timeout a member")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(user="The member to mute", duration="Duration in minutes", reason="Reason for muting")
async def mute(interaction: discord.Interaction, user: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
    try:
        await user.timeout(timedelta(minutes=duration), reason=reason)
        
        conn = get_db()
        cursor = conn.cursor()
        mute_until = (datetime.now() + timedelta(minutes=duration)).isoformat()
        cursor.execute('''INSERT OR REPLACE INTO mutes (guild_id, user_id, muted_until)
                       VALUES (?, ?, ?)''', (str(interaction.guild_id), str(user.id), mute_until))
        cursor.execute('''INSERT INTO infractions (guild_id, user_id, type, reason, moderator_id, duration, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (str(interaction.guild_id), str(user.id), 'mute', reason, 
                      str(interaction.user.id), f"{duration}m", datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(f"🔇 Muted {user.mention} for {duration} minutes. Reason: {reason}")
    except:
        await interaction.response.send_message("❌ Failed to mute user.", ephemeral=True)

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(user="The member to warn", reason="Reason for warning")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO infractions (guild_id, user_id, type, reason, moderator_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                 (str(interaction.guild_id), str(user.id), 'warn', reason, 
                  str(interaction.user.id), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    try:
        await user.send(f"⚠️ You have been warned in **{interaction.guild.name}**\nReason: {reason}")
    except:
        pass
    
    await interaction.response.send_message(f"⚠️ Warned {user.mention}. Reason: {reason}")

@bot.tree.command(name="clear", description="Delete recent messages")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def clear(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="slowmode", description="Set slowmode for a channel")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
async def slowmode(interaction: discord.Interaction, seconds: int):
    if seconds < 0 or seconds > 21600:
        await interaction.response.send_message("❌ Slowmode must be between 0 and 21600 seconds.", ephemeral=True)
        return
    
    await interaction.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await interaction.response.send_message("✅ Slowmode disabled.")
    else:
        await interaction.response.send_message(f"✅ Slowmode set to {seconds} seconds.")

@bot.tree.command(name="lock", description="Lock a channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔒 Channel locked.")

@bot.tree.command(name="unlock", description="Unlock a channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔓 Channel unlocked.")

@bot.tree.command(name="nick", description="Change a member's nickname")
@app_commands.checks.has_permissions(manage_nicknames=True)
@app_commands.describe(user="The member to rename", nickname="New nickname (leave empty to reset)")
async def nick(interaction: discord.Interaction, user: discord.Member, nickname: Optional[str] = None):
    try:
        await user.edit(nick=nickname)
        if nickname:
            await interaction.response.send_message(f"✅ Changed {user.mention}'s nickname to **{nickname}**")
        else:
            await interaction.response.send_message(f"✅ Reset {user.mention}'s nickname")
    except:
        await interaction.response.send_message("❌ Failed to change nickname.", ephemeral=True)

@bot.tree.command(name="announce", description="Send an announcement embed")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(title="Announcement title", message="Announcement message")
async def announce(interaction: discord.Interaction, title: str, message: str):
    embed = discord.Embed(title=f"📢 {title}", description=message, color=discord.Color.blue())
    embed.set_footer(text=f"Announcement by {interaction.user.name}")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="poll", description="Create a poll")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(question="Poll question", options="Options separated by commas (max 10)")
async def poll(interaction: discord.Interaction, question: str, options: str):
    option_list = [opt.strip() for opt in options.split(',')][:10]
    if len(option_list) < 2:
        await interaction.response.send_message("❌ You need at least 2 options.", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"📊 {question}", color=discord.Color.blue())
    reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    for i, option in enumerate(option_list):
        embed.add_field(name=f"{reactions[i]} Option {i+1}", value=option, inline=False)
    
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    for i in range(len(option_list)):
        await message.add_reaction(reactions[i])

@bot.tree.command(name="embed", description="Create a custom embed")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(title="Embed title", description="Embed description", color="Hex color (e.g., #ff0000)")
async def create_embed(interaction: discord.Interaction, title: str, description: str, color: Optional[str] = "#0099ff"):
    try:
        color_int = int(color.replace("#", ""), 16) if color.startswith("#") else int(color, 16)
        embed = discord.Embed(title=title, description=description, color=color_int)
        await interaction.response.send_message(embed=embed)
    except:
        await interaction.response.send_message("❌ Invalid color format.", ephemeral=True)

role_group = app_commands.Group(name="role", description="Role management commands")

@role_group.command(name="add", description="Add a role to a user")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(user="The user to give the role", role="The role to add")
async def role_add(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    try:
        await user.add_roles(role)
        await interaction.response.send_message(f"✅ Added {role.mention} to {user.mention}")
    except:
        await interaction.response.send_message("❌ Failed to add role.", ephemeral=True)

@role_group.command(name="remove", description="Remove a role from a user")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(user="The user to remove the role from", role="The role to remove")
async def role_remove(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    try:
        await user.remove_roles(role)
        await interaction.response.send_message(f"✅ Removed {role.mention} from {user.mention}")
    except:
        await interaction.response.send_message("❌ Failed to remove role.", ephemeral=True)

bot.tree.add_command(role_group)

@bot.tree.command(name="serverinfo", description="Display server information")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"📊 {guild.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="Display user information")
@app_commands.describe(user="The user to view info about")
async def userinfo(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"👤 {user.name}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Nickname", value=user.display_name, inline=True)
    embed.add_field(name="Joined Server", value=user.joined_at.strftime("%Y-%m-%d") if user.joined_at else "Unknown", inline=True)
    embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Top Role", value=user.top_role.mention, inline=True)
    roles = [role.mention for role in user.roles[1:]][:10]
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Check bot latency and uptime")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    uptime = datetime.now() - bot_start_time
    embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())
    embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
    embed.add_field(name="Uptime", value=str(uptime).split('.')[0], inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="apply", description="Submit an application to join the alliance")
async def apply(interaction: discord.Interaction):
    modal = discord.ui.Modal(title="Alliance Application")
    modal.add_item(discord.ui.TextInput(label="In-game Name", placeholder="Your name in War of Peaks"))
    modal.add_item(discord.ui.TextInput(label="Power Level", placeholder="Your current power"))
    modal.add_item(discord.ui.TextInput(label="Why join us?", style=discord.TextStyle.paragraph, 
                                       placeholder="Tell us why you want to join", max_length=500))
    
    async def modal_callback(modal_interaction: discord.Interaction):
        content = f"**In-game Name:** {modal.children[0].value}\n**Power:** {modal.children[1].value}\n**Reason:** {modal.children[2].value}"
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO applications (guild_id, user_id, content, timestamp)
                       VALUES (?, ?, ?, ?)''',
                     (str(interaction.guild_id), str(interaction.user.id), content, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        await modal_interaction.response.send_message("✅ Application submitted! Leadership will review it soon.", ephemeral=True)
    
    modal.on_submit = modal_callback
    await interaction.response.send_modal(modal)

event_group = app_commands.Group(name="event", description="Alliance event management")

@event_group.command(name="add", description="Schedule an alliance event")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(name="Event name", date_time="Date and time (YYYY-MM-DD HH:MM)", description="Event description")
async def event_add(interaction: discord.Interaction, name: str, date_time: str, description: Optional[str] = "No description"):
    try:
        event_datetime = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO events (guild_id, name, datetime, description, created_by)
                       VALUES (?, ?, ?, ?, ?)''',
                     (str(interaction.guild_id), name, event_datetime.isoformat(), description, str(interaction.user.id)))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(title=f"📅 Event Created: {name}", color=discord.Color.green())
        embed.add_field(name="Date & Time", value=event_datetime.strftime("%Y-%m-%d %H:%M"), inline=False)
        embed.add_field(name="Description", value=description, inline=False)
        embed.set_footer(text=f"Created by {interaction.user.name}")
        await interaction.response.send_message(embed=embed)
    except ValueError:
        await interaction.response.send_message("❌ Invalid date format. Use: YYYY-MM-DD HH:MM", ephemeral=True)

@event_group.command(name="list", description="Show upcoming events")
async def event_list(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT name, datetime, description FROM events 
                   WHERE guild_id = ? AND datetime >= ?
                   ORDER BY datetime LIMIT 10''',
                 (str(interaction.guild_id), datetime.now().isoformat()))
    events = cursor.fetchall()
    conn.close()
    
    if not events:
        await interaction.response.send_message("📅 No upcoming events scheduled.", ephemeral=True)
        return
    
    embed = discord.Embed(title="📅 Upcoming Alliance Events", color=discord.Color.blue())
    for name, dt, desc in events:
        event_dt = datetime.fromisoformat(dt)
        embed.add_field(
            name=f"**{name}**",
            value=f"📆 {event_dt.strftime('%Y-%m-%d %H:%M')}\n{desc}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

bot.tree.add_command(event_group)

@bot.tree.command(name="namecheck", description="Check if members have proper alliance tags")
@app_commands.checks.has_permissions(manage_guild=True)
async def namecheck(interaction: discord.Interaction):
    await interaction.response.defer()
    
    members_without_tag = []
    for member in interaction.guild.members:
        if not member.bot and not member.display_name.startswith("ˡᵛ "):
            members_without_tag.append(member.mention)
    
    if not members_without_tag:
        await interaction.followup.send("✅ All members have the proper alliance tag!")
    else:
        embed = discord.Embed(title="⚠️ Name Check Results", color=discord.Color.orange())
        embed.description = f"**{len(members_without_tag)} members** missing alliance tag 'ˡᵛ':"
        chunks = [members_without_tag[i:i+20] for i in range(0, len(members_without_tag), 20)]
        for i, chunk in enumerate(chunks[:5]):
            embed.add_field(name=f"Page {i+1}", value="\n".join(chunk), inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="stats", description="View your server stats")
async def stats(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?',
                  (str(interaction.guild_id), str(interaction.user.id)))
    result = cursor.fetchone()
    
    cursor.execute('SELECT COUNT(*) FROM infractions WHERE guild_id = ? AND user_id = ? AND type = ?',
                  (str(interaction.guild_id), str(interaction.user.id), 'warn'))
    warns = cursor.fetchone()[0]
    
    conn.close()
    
    xp, level = result if result else (0, 0)
    
    embed = discord.Embed(title=f"📊 Stats for {interaction.user.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="Level", value=level, inline=True)
    embed.add_field(name="XP", value=xp, inline=True)
    embed.add_field(name="Warnings", value=warns, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rank", description="View the server leaderboard")
async def rank(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT user_id, xp, level FROM user_levels 
                   WHERE guild_id = ? ORDER BY xp DESC LIMIT 10''',
                 (str(interaction.guild_id),))
    top_users = cursor.fetchall()
    conn.close()
    
    if not top_users:
        await interaction.response.send_message("📊 No leaderboard data yet.", ephemeral=True)
        return
    
    embed = discord.Embed(title="🏆 Server Leaderboard", color=discord.Color.gold())
    medals = ['🥇', '🥈', '🥉'] + ['📊'] * 7
    
    for i, (user_id, xp, level) in enumerate(top_users):
        user = interaction.guild.get_member(int(user_id))
        name = user.display_name if user else f"User {user_id}"
        embed.add_field(
            name=f"{medals[i]} #{i+1} {name}",
            value=f"Level {level} • {xp} XP",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Claim your daily coins")
async def daily(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT balance, last_daily FROM economy WHERE guild_id = ? AND user_id = ?',
                  (str(interaction.guild_id), str(interaction.user.id)))
    result = cursor.fetchone()
    
    now = datetime.now()
    can_claim = True
    
    if result and result[1]:
        last_daily = datetime.fromisoformat(result[1])
        if (now - last_daily).total_seconds() < 86400:
            time_left = timedelta(seconds=86400 - (now - last_daily).total_seconds())
            await interaction.response.send_message(
                f"⏰ You already claimed your daily! Come back in {str(time_left).split('.')[0]}", 
                ephemeral=True
            )
            can_claim = False
    
    if can_claim:
        reward = random.randint(100, 250)
        if result:
            new_balance = result[0] + reward
            cursor.execute('''UPDATE economy SET balance = ?, last_daily = ? 
                           WHERE guild_id = ? AND user_id = ?''',
                         (new_balance, now.isoformat(), str(interaction.guild_id), str(interaction.user.id)))
        else:
            new_balance = reward
            cursor.execute('''INSERT INTO economy (guild_id, user_id, balance, last_daily)
                           VALUES (?, ?, ?, ?)''',
                         (str(interaction.guild_id), str(interaction.user.id), reward, now.isoformat()))
        
        conn.commit()
        await interaction.response.send_message(f"💰 Daily reward claimed! You received **{reward} coins**. New balance: **{new_balance} coins**")
    
    conn.close()

@bot.tree.command(name="balance", description="Check your coin balance")
async def balance(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?',
                  (str(interaction.guild_id), str(target.id)))
    result = cursor.fetchone()
    conn.close()
    
    bal = result[0] if result else 0
    await interaction.response.send_message(f"💰 **{target.display_name}** has **{bal} coins**")

@bot.tree.command(name="duel", description="Challenge another user to a duel")
@app_commands.describe(opponent="The user to challenge")
async def duel(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.bot:
        await interaction.response.send_message("❌ You can't duel a bot!", ephemeral=True)
        return
    
    if opponent.id == interaction.user.id:
        await interaction.response.send_message("❌ You can't duel yourself!", ephemeral=True)
        return
    
    winner = random.choice([interaction.user, opponent])
    loser = opponent if winner == interaction.user else interaction.user
    
    embed = discord.Embed(title="⚔️ Duel Results!", color=discord.Color.red())
    embed.add_field(name="Combatants", value=f"{interaction.user.mention} vs {opponent.mention}", inline=False)
    embed.add_field(name="Winner", value=f"🏆 {winner.mention}", inline=True)
    embed.add_field(name="Loser", value=f"💀 {loser.mention}", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="quote", description="Get a random quote")
async def get_quote(interaction: discord.Interaction):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT quote, author FROM quotes WHERE guild_id = ? ORDER BY RANDOM() LIMIT 1',
                  (str(interaction.guild_id),))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        quote, author = result
        embed = discord.Embed(description=f'"{quote}"', color=discord.Color.blue())
        embed.set_footer(text=f"— {author}")
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("💭 No quotes available yet. Add some with the quote system!", ephemeral=True)

@bot.tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    memes = [
        "When you forget to claim your daily rewards... 💀",
        "That moment when the R5 says 'rally now' during dinner 🍕",
        "POV: You just got kicked for not following the alliance tag format 📝",
        "When you accidentally start drama in alliance chat 😬",
        "R4: We need more activity!\nAlso R4: *offline for 3 days* 🤔"
    ]
    await interaction.response.send_message(random.choice(memes))

@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your yes/no question")
async def eightball(interaction: discord.Interaction, question: str):
    responses = [
        "Yes, definitely! ✅",
        "Without a doubt! 💯",
        "Absolutely! 🎯",
        "My sources say yes. 📊",
        "Probably. 🤔",
        "Maybe... 🤷",
        "Ask again later. ⏰",
        "Cannot predict now. 🔮",
        "Doubtful. 😕",
        "Don't count on it. ❌",
        "My sources say no. 📉",
        "Very doubtful. 🚫",
        "Absolutely not! ⛔"
    ]
    
    embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.purple())
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=random.choice(responses), inline=False)
    await interaction.response.send_message(embed=embed)

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ Error: DISCORD_TOKEN environment variable not found!")
    print("Please add your Discord bot token to Secrets with key 'DISCORD_TOKEN'")
    exit(1)

bot.run(TOKEN)
