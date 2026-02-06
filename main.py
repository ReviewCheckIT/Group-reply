import os
import json
import logging
import threading
import re
import html
import time
import asyncio
from datetime import datetime
from flask import Flask
# Telegram Imports Updated to include Inline Keyboard
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Third-party libraries
from groq import Groq
import firebase_admin
from firebase_admin import credentials, db

# ---------------------------------------------------------------------------
# 1. CONFIGURATION & SETUP
# ---------------------------------------------------------------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL") 
FIREBASE_CREDS_JSON = os.getenv("FIREBASE_CREDENTIALS")

# Initialize Firebase
if not firebase_admin._apps:
    try:
        cred_dict = json.loads(FIREBASE_CREDS_JSON)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_DB_URL
        })
        logger.info("✅ Firebase Connected Successfully.")
    except Exception as e:
        logger.error(f"❌ Firebase Connection Failed: {e}")

# Initialize Groq
client = Groq(api_key=GROQ_API_KEY)

# Web Server for Keep-Alive
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Skyzone IT AI Bot (Pakiza) is Active & Intelligent!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ---------------------------------------------------------------------------
# 2. LOGIC CONSTANTS & REGEX
# ---------------------------------------------------------------------------

# Regex for detecting unauthorized external links
UNAUTHORIZED_LINK_PATTERN = r'(https?://(?!nexstars\.site)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|t\.me/(?!SkyzoneIT_bot)[a-zA-Z0-9_]+)'

# Smart regex for asking about the website link
WEBSITE_ASK_PATTERN = r'(website|site|link|লিঙ্ক|ওয়েবসাইট)\s*(koi|ki|den|plz|dao|দাও|দেন|কি|কই|link|please|plz)?'

# Specific Link to provide
NEXSTARS_LINK = "https://nexstars.site/auth?mode=signup&ref=NEX-7944"

# Spam Control
spam_tracker = {}
SPAM_LIMIT = 3
SPAM_WINDOW = 10 

# Admin Cache
admin_cache = {"ids": [], "last_updated": datetime.min}

# ---------------------------------------------------------------------------
# 3. HELPER FUNCTIONS
# ---------------------------------------------------------------------------

async def get_user_data(user_id):
    """Fetch user data from Firebase asynchronously."""
    def _fetch():
        ref = db.reference(f'users/{user_id}')
        return ref.get()
    return await asyncio.to_thread(_fetch)

async def update_user_data(user_id, user_name, message_text):
    """Update user stats in Firebase asynchronously."""
    def _update():
        ref = db.reference(f'users/{user_id}')
        user_data = ref.get() or {}
        
        now_str = datetime.now().isoformat()
        
        if not user_data:
            user_data = {
                "first_seen": now_str,
                "msg_count": 0,
                "last_interaction": now_str,
                "name": user_name,
                "last_topic": ""
            }
        
        user_data['msg_count'] += 1
        user_data['last_interaction'] = now_str
        user_data['name'] = user_name
        user_data['last_topic'] = message_text[:50] 
        
        ref.set(user_data)
    
    await asyncio.to_thread(_update)

def is_spamming(user_id):
    """Check if user is flooding the chat."""
    current_time = time.time()
    if user_id not in spam_tracker:
        spam_tracker[user_id] = []
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if current_time - t < SPAM_WINDOW]
    spam_tracker[user_id].append(current_time)
    return len(spam_tracker[user_id]) > SPAM_LIMIT

# ---------------------------------------------------------------------------
# 4. AI LOGIC (Groq + Context)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are 'Pakiza' (পাকিজা), a dedicated and professional team member of 'Skyzone IT'. You are NOT a robot; you are a helpful human assistant.

**Your Persona:**
- Tone: Polite, professional, yet warm (Bangla/Banglish/English).
- Context: We recruit people via Facebook posts to give reviews. They passed a test to get here. Treat them with respect.

**Strict Rules:**
1. **No Links First:** Do not give video/bot links immediately upon "Hi/Hello". Only engage.
2. **Intent Analysis:** If the user specifically asks "Ki kaj?" (What is work?), only then guide them to the pinned video.
3. **Website Link Requests:** If user asks for website link, DO NOT provide the link. Politely ask them to check their inbox or use the button provided (The code handles the button, you just handle the text).
4. **Brevity:** Keep replies short and human-like.
"""

async def get_ai_response(user_text, user_name, user_data, specific_instruction=None):
    try:
        is_new_user = user_data.get('msg_count', 0) < 5
        last_topic = user_data.get('last_topic', 'None')
        
        context_note = f"\nUser Stats: {'New Member' if is_new_user else 'Old Member'}. Last topic: {last_topic}."
        
        system_content = SYSTEM_PROMPT + context_note
        if specific_instruction:
            system_content += f"\n\n[URGENT INSTRUCTION: {specific_instruction}]"

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"User: {user_name}\nMessage: {user_text}"},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.6,
            max_tokens=200
        )
        return html.escape(chat_completion.choices[0].message.content)
    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return None

# ---------------------------------------------------------------------------
# 5. TELEGRAM HANDLERS
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

async def get_group_admins(context, chat_id):
    global admin_cache
    now = datetime.now()
    if (now - admin_cache["last_updated"]).total_seconds() > 600 or not admin_cache["ids"]:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_cache["ids"] = [admin.user.id for admin in admins]
            admin_cache["last_updated"] = now
        except Exception as e:
            logger.error(f"Failed to fetch admins: {e}")
    return admin_cache["ids"]

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Professional Welcome System."""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        
        welcome_text = (
            f"আসসালামু আলাইকুম <b>{html.escape(member.first_name)}</b>! 🌟\n"
            "Skyzone IT পরিবারে আপনাকে স্বাগতম।\n\n"
            "আমি পাকিজা, এখানকার সাপোর্ট মেম্বার। আপনার কি কোনো সাহায্য লাগবে বা আপনি কি কাজ শুরু করতে চান?"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_text,
            parse_mode=constants.ParseMode.HTML
        )
        await update_user_data(member.id, member.first_name, "JOINED_GROUP")

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    # Only process specific group
    if update.effective_chat.id != GROUP_ID:
        return

    user = update.message.from_user
    text = update.message.text
    
    # 1. Check Admin Status
    admins = await get_group_admins(context, GROUP_ID)
    is_admin = user.id in admins or user.id == ADMIN_ID

    # 2. Delete Unauthorized External Links (Skip for Admins)
    if not is_admin:
        if re.search(UNAUTHORIZED_LINK_PATTERN, text):
            try:
                await update.message.delete()
                return 
            except Exception as e:
                logger.error(f"Delete error: {e}")

    # 3. Admin Interaction
    if is_admin:
        if "pakiza" in text.lower() or "পাকিজা" in text:
            await update.message.reply_text("জি, আমি আছি। বলুন কিভাবে সাহায্য করতে পারি? 👩‍💻")
        return

    # 4. Anti-Flood / Spam Control
    if is_spamming(user.id):
        warning_msg = await update.message.reply_text(f"⚠️ {user.first_name}, অনুগ্রহ করে স্প্যাম করবেন না। ধীরে মেসেজ দিন।")
        asyncio.create_task(delete_later(warning_msg, 5))
        return

    # 5. Smart Website Link Detection (UPDATED LOGIC)
    # Checks for "website link koi", "site link please", etc.
    if re.search(WEBSITE_ASK_PATTERN, text.lower()):
        # Generate a Deep Link to the bot's PM
        bot_username = context.bot.username
        # Using Deep Linking: t.me/botname?start=get_site_link
        deep_link_url = f"https://t.me/{bot_username}?start=get_site_link"
        
        keyboard = [
            [InlineKeyboardButton("📩 ইনবক্সে লিংক নিন", url=deep_link_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        reply_text = (
            f"⚠️ <b>{html.escape(user.first_name)}</b>, নিরাপত্তা ও স্প্যাম এড়াতে আমরা গ্রুপে সরাসরি লিংক দিচ্ছি না।\n\n"
            "অনুগ্রহ করে নিচের বাটনে ক্লিক করুন, আমি ইনবক্সে আপনাকে লিংক দিয়ে দিচ্ছি। 👇"
        )
        
        await update.message.reply_text(
            reply_text, 
            parse_mode=constants.ParseMode.HTML,
            reply_markup=reply_markup
        )
        await update_user_data(user.id, user.first_name, text)
        return

    # 6. Fetch User Context from Firebase
    user_data = await get_user_data(user.id) or {}
    
    # 7. AI Generation
    await context.bot.send_chat_action(chat_id=GROUP_ID, action=constants.ChatAction.TYPING)
    
    instruction = None
    if user_data.get('msg_count', 0) > 50:
         instruction = "User is a very old member. Be concise and professional."
    
    ai_reply = await get_ai_response(text, user.first_name, user_data, instruction)

    if ai_reply:
        await update.message.reply_text(ai_reply, parse_mode=constants.ParseMode.HTML)
    
    await update_user_data(user.id, user.first_name, text)

async def delete_later(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

# Updated Start Command to handle Deep Linking
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args # Get arguments passed with /start

    # CASE A: User clicked the button in Group (Deep Link Payload)
    if args and args[0] == "get_site_link":
        reply_text = (
            f"স্বাগতম <b>{html.escape(user.first_name)}</b>! 🎉\n\n"
            f"আমাদের অফিসিয়াল ওয়েবসাইটে যুক্ত হতে নিচের লিংকে ক্লিক করুন:\n\n"
            f"🔗 <a href='{NEXSTARS_LINK}'>Skyzone IT Website Registration</a>\n\n"
            "সাইন আপ করতে কোনো সমস্যা হলে আমাকে জানাবেন!"
        )
        await update.message.reply_text(reply_text, parse_mode=constants.ParseMode.HTML)
        # Log this interaction
        await update_user_data(user.id, user.first_name, "RECEIVED_LINK_IN_DM")
        return

    # CASE B: Normal Start by Admin
    if user.id == ADMIN_ID:
        await update.message.reply_text("✅ Pakiza is Online and synced with Firebase!")
        return
        
    # CASE C: Normal Start by User (No payload)
    welcome_text = (
        f"আসসালামু আলাইকুম <b>{html.escape(user.first_name)}</b>!\n"
        "আমি পাকিজা, Skyzone IT এর অ্যাসিস্ট্যান্ট। আমি আপনাকে কিভাবে সাহায্য করতে পারি?"
    )
    await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.HTML)
    await update_user_data(user.id, user.first_name, "STARTED_BOT_DM")

# ---------------------------------------------------------------------------
# 6. MAIN EXECUTION
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Start Web Server
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Bot Setup
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    
    # Welcome Handler
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Main Message Handler (Group Only, Exclude Commands)
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Pakiza AI Bot is Running with Deep-Link Feature...")
    app.run_polling()
