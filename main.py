import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- রেন্ডার পোর্ট সেটআপ ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- বটের কনফিগারেশন (Environment Variables) ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))

# লগিং সেটআপ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# অ্যাডমিন চেক ডেকোরেটর
def is_admin(user_id):
    return user_id == ADMIN_ID

# কমান্ড ফাংশনসমূহ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    help_text = (
        "👑 **Ultimate Admin Bot Control Panel**\n\n"
        "**ইউজার ম্যানেজমেন্ট:**\n"
        "/ban [ID] - ইউজারকে পার্মানেন্ট ব্যান করা\n"
        "/unban [ID] - ব্যান রিমুভ করা\n"
        "/kick [ID] - গ্রুপ থেকে বের করে দেওয়া\n"
        "/mute [ID] - মেসেজ দেওয়া বন্ধ করা\n"
        "/unmute [ID] - কথা বলার সুযোগ দেওয়া\n\n"
        "**গ্রুপ ম্যানেজমেন্ট:**\n"
        "/pin [ID] - মেসেজ পিন করা (রিপ্লাই দিয়েও হয়)\n"
        "/unpin - পিন রিমুভ করা\n"
        "/settitle [Text] - গ্রুপের নাম পরিবর্তন\n"
        "/setdesc [Text] - ডেসক্রিপশন পরিবর্তন\n"
        "/del - মেসেজ ডিলিট করা (রিপ্লাই দিন)\n"
        "/link - গ্রুপের ইনভাইট লিংক তৈরি"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    user_id = context.args[0]
    await context.bot.ban_chat_member(GROUP_ID, user_id)
    await update.message.reply_text(f"✅ User {user_id} banned successfully.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    user_id = context.args[0]
    permissions = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(GROUP_ID, user_id, permissions=permissions)
    await update.message.reply_text(f"🔇 User {user_id} muted.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    user_id = context.args[0]
    permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=False, can_invite_users=True, can_pin_messages=False)
    await context.bot.restrict_chat_member(GROUP_ID, user_id, permissions=permissions)
    await update.message.reply_text(f"🔊 User {user_id} unmuted.")

async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if update.message.reply_to_message:
        msg_id = update.message.reply_to_message.message_id
    else:
        msg_id = context.args[0]
    await context.bot.pin_chat_message(GROUP_ID, msg_id)
    await update.message.reply_text("📌 Message pinned.")

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    title = " ".join(context.args)
    await context.bot.set_chat_title(GROUP_ID, title)
    await update.message.reply_text("✅ Group title changed.")

async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    link = await context.bot.export_chat_invite_link(GROUP_ID)
    await update.message.reply_text(f"🔗 Group Invite Link: {link}")

if __name__ == '__main__':
    # ওয়েব সার্ভার আলাদা থ্রেডে চালানো
    Thread(target=run_web).start()

    # বট শুরু
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("pin", pin_message))
    application.add_handler(CommandHandler("settitle", set_title))
    application.add_handler(CommandHandler("link", get_link))
    
    application.run_polling()
