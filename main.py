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
# Telegram Imports
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
    return "Skyzone IT AI Bot (Pakiza) is Active!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ---------------------------------------------------------------------------
# 2. LOGIC CONSTANTS
# ---------------------------------------------------------------------------

UNAUTHORIZED_LINK_PATTERN = r'(https?://(?!nexstars\.site)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|t\.me/(?!SkyzoneIT_bot)[a-zA-Z0-9_]+)'
NEXSTARS_LINK = "https://nexstars.site/auth?mode=signup&ref=NEX-7944"

# Spam Control
spam_tracker = {}
SPAM_LIMIT = 3
SPAM_WINDOW = 10 

# Admin Cache
admin_cache = {"ids": [], "last_updated": datetime.min}

# ---------------------------------------------------------------------------
# 3. HELPER FUNCTIONS (Delete Logic Added)
# ---------------------------------------------------------------------------

async def delete_later(message, delay):
    """Waits for 'delay' seconds and then deletes the message."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Message already deleted or error: {e}")

async def get_user_data(user_id):
    def _fetch():
        ref = db.reference(f'users/{user_id}')
        return ref.get()
    return await asyncio.to_thread(_fetch)

async def update_user_data(user_id, user_name, message_text):
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
    current_time = time.time()
    if user_id not in spam_tracker:
        spam_tracker[user_id] = []
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if current_time - t < SPAM_WINDOW]
    spam_tracker[user_id].append(current_time)
    return len(spam_tracker[user_id]) > SPAM_LIMIT

# ---------------------------------------------------------------------------
# 4. AI LOGIC
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are 'Pakiza' (পাকিজা), a team member of 'Skyzone IT'. 

**Strict Rules:**
1. If user asks for "Link", "Website", or "Signup", DO NOT REPLY. The python code handles this with a button.
2. Only answer questions about work, payment, or general support.
3. Be polite and professional.
"""

async def get_ai_response(user_text, user_name, user_data):
    try:
        system_content = SYSTEM_PROMPT + f"\nUser: {user_name}"
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_text},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.6,
            max_tokens=150
        )
        return html.escape(chat_completion.choices[0].message.content)
    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return None

# ---------------------------------------------------------------------------
# 5. TELEGRAM HANDLERS
# ---------------------------------------------------------------------------

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

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main Handler: Button with Auto-Delete
    """
    if not update.message or not update.message.text:
        return
    
    if update.effective_chat.id != GROUP_ID:
        return

    user = update.message.from_user
    text = update.message.text.lower()
    
    # 1. Spam Check
    if is_spamming(user.id):
        return 

    # 2. LINK REQUEST HANDLING (Auto-Delete Added)
    link_keywords = ["link", "site", "web", "লিংক", "লিঙ্ক", "ওয়েবসাইট", "রেজিষ্ট্রেশন", "রেজিস্ট্রেশন", "signup", "sign up", "join"]
    
    if any(keyword in text for keyword in link_keywords):
        try:
            bot_info = await context.bot.get_me()
            bot_username = bot_info.username
            deep_link = f"https://t.me/{bot_username}?start=get_site_link"
            
            keyboard = [
                [InlineKeyboardButton("📩 ইনবক্সে লিংক নিন (Click Here)", url=deep_link)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send Message
            sent_message = await update.message.reply_text(
                f"⚠️ <b>{html.escape(user.first_name)}</b>, লিংকটি নিতে নিচের বাটনে ক্লিক করুন।\n"
                "<i>(এই মেসেজটি ৩০ সেকেন্ড পর মুছে যাবে)</i>",
                parse_mode=constants.ParseMode.HTML,
                reply_markup=reply_markup
            )
            
            # --- AUTO DELETE TASK ---
            # Run the delete timer in background so bot doesn't freeze
            asyncio.create_task(delete_later(sent_message, 30)) # 30 Seconds Delay
            
            # Log and Stop
            await update_user_data(user.id, user.first_name, "ASKED_FOR_LINK_GROUP")
            return 

        except Exception as e:
            logger.error(f"Button Error: {e}")
            return

    # 3. Admin & Other Logic
    admins = await get_group_admins(context, GROUP_ID)
    is_admin = user.id in admins or user.id == ADMIN_ID

    if not is_admin and re.search(UNAUTHORIZED_LINK_PATTERN, update.message.text):
        try:
            await update.message.delete()
            return
        except:
            pass

    # 4. AI Logic
    user_data = await get_user_data(user.id) or {}
    await context.bot.send_chat_action(chat_id=GROUP_ID, action=constants.ChatAction.TYPING)
    
    ai_reply = await get_ai_response(update.message.text, user.first_name, user_data)
    
    if ai_reply:
        await update.message.reply_text(ai_reply, parse_mode=constants.ParseMode.HTML)
    
    await update_user_data(user.id, user.first_name, update.message.text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles Inbox Delivery
    """
    user = update.effective_user
    args = context.args

    if args and args[0] == "get_site_link":
        welcome_text = (
            f"স্বাগতম <b>{html.escape(user.first_name)}</b>! 🎉\n\n"
            f"✅ আপনার অনুরোধ করা ওয়েবসাইট লিংকটি নিচে দেওয়া হলো:\n\n"
            f"🔗 <b>Registration Link:</b>\n{NEXSTARS_LINK}\n\n"
            "অ্যাকাউন্ট করতে কোনো সমস্যা হলে গ্রুপে স্ক্রিনশটসহ জানাবেন।"
        )
        await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.HTML, disable_web_page_preview=False)
        return

    await update.message.reply_text(f"আসসালামু আলাইকুম {user.first_name}! আমি পাকিজা।")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: continue
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Welcome {html.escape(member.first_name)}! কেমন আছেন?",
            parse_mode=constants.ParseMode.HTML
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception:", exc_info=context.error)

# ---------------------------------------------------------------------------
# 6. MAIN EXECUTION
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Pakiza AI Bot is Running (Auto-Delete Enabled)...")
    app.run_polling()
