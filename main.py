import os
import logging
import threading
import re
import asyncio
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ১. Render এর পোর্টের জন্য ফ্লাস্ক অ্যাপ
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. লগিং কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ৩. এনভায়রনমেন্ট ভেরিয়েবল (Render-এ সেট করবেন)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))

# ৪. সুরক্ষা ও ফিল্টার Regex
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

# ৫. কমান্ড লিস্ট (শুধুমাত্র এডমিনের জন্য)
HELP_TEXT = """
🔥 **Super Admin Control Panel** 🔥

🚀 **ইউজার ম্যানেজমেন্ট:**
• `/ban [User_ID]` - ইউজারকে পার্মানেন্ট ব্যান করা।
• `/unban [User_ID]` - ব্যন রিমুভ করা।
• `/kick [User_ID]` - গ্রুপ থেকে বের করে দেয়া।
• `/mute [User_ID]` - ইউজারকে মিউট করা (কথা বলতে পারবে না)।
• `/unmute [User_ID]` - মিউট রিমুভ করা।

🛠 **গ্রুপ কন্ট্রোল:**
• `/pin [Msg_ID]` - যেকোনো মেসেজ পিন করা।
• `/unpin` - পিন মেসেজ রিমুভ করা।
• `/slow [সেকেন্ড]` - মেসেজ পাঠানোর গতি নিয়ন্ত্রণ করা।
• `/delete [Msg_ID]` - নির্দিষ্ট মেসেজ ডিলিট করা।
• `/set_title [নাম]` - গ্রুপের নাম পরিবর্তন।
• `/set_desc [বর্ণনা]` - গ্রুপের ডেসক্রিপশন পরিবর্তন।

💬 **মেসেজ রিপ্লাই:**
• `/reply [Msg_ID] [Text]` - ইউজারের মেসেজে রিপ্লাই দেয়া।
"""

# --- হ্যান্ডলার ফাংশনসমূহ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        user_id = int(context.args[0])
        await context.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await update.message.reply_text(f"✅ User {user_id} কে ব্যান করা হয়েছে।")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        user_id = int(context.args[0])
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(chat_id=GROUP_ID, user_id=user_id, permissions=permissions)
        await update.message.reply_text(f"🔇 User {user_id} কে মিউট করা হয়েছে।")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        user_id = int(context.args[0])
        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True)
        await context.bot.restrict_chat_member(chat_id=GROUP_ID, user_id=user_id, permissions=permissions)
        await update.message.reply_text(f"🔊 User {user_id} এখন কথা বলতে পারবে।")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def slow_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        seconds = int(context.args[0])
        await context.bot.set_chat_slow_mode_delay(chat_id=GROUP_ID, delay=seconds)
        await update.message.reply_text(f"⏳ স্লো-মোড {seconds} সেকেন্ড সেট করা হয়েছে।")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        msg_id = int(context.args[0])
        await context.bot.pin_chat_message(chat_id=GROUP_ID, message_id=msg_id)
        await update.message.reply_text("📌 মেসেজ পিন করা হয়েছে।")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def handle_group_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """গ্রুপের মেসেজ মনিটর এবং অটো-আইডি জেনারেট করা"""
    if update.effective_chat.id != GROUP_ID or update.effective_user.id == ADMIN_ID:
        return

    text = update.message.text or update.message.caption or ""
    
    # লিঙ্ক ডিটেকশন ও ডিলিট
    if re.search(URL_PATTERN, text):
        await update.message.delete()
        return

    # ইউজারের মেসেজটি বটের মাধ্যমে নতুন করে পাঠানো (যাতে আপনি আইডি পান)
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    original_msg_id = update.message.message_id

    try:
        prefix = f"🆔 ID: <code>{original_msg_id}</code>\n👤 User: <b>{user_name}</b> (<code>{user_id}</code>)\n\n"
        
        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=prefix + text, parse_mode=ParseMode.HTML)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=prefix + text, parse_mode=ParseMode.HTML)
        
        # আসল মেসেজ ডিলিট (যাতে বটের মেসেজটাই গ্রুপে থাকে)
        await update.message.delete()
    except Exception as e:
        logging.error(f"Error in group logic: {e}")

async def admin_private_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এডমিন প্রাইভেটে যা লিখবে তা গ্রুপে যাবে (বট হিসেবে)"""
    if update.effective_user.id != ADMIN_ID: return
    
    try:
        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        await update.message.reply_text("✅ গ্রুপে প্রচার করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# --- মেইন ফাংশন ---

if __name__ == '__main__':
    # ফ্লাস্ক সার্ভার থ্রেড চালু
    threading.Thread(target=run_web_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # কমান্ড হ্যান্ডলার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("slow", slow_mode))
    app.add_handler(CommandHandler("pin", pin_message))
    app.add_handler(CommandHandler("reply", admin_private_proxy)) # আপনি চাইলে আরও কাস্টমাইজ করতে পারেন

    # গ্রুপ ফিল্টার এবং প্রাইভেট মেসেজ প্রক্সি
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_logic))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), admin_private_proxy))

    print("Bot is running...")
    app.run_polling()
