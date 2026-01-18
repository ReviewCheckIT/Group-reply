import os
import logging
import threading
import re
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ১. Render এর জন্য Web Server
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

# ৩. স্টার্ট কমান্ড (এডমিনের জন্য কমান্ড লিস্ট)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        msg = (
            "🛠 **বট কন্ট্রোল প্যানেল সচল**\n\n"
            "📌 **ম্যানেজমেন্ট কমান্ডস:**\n"
            "• `/reply [ID] [Text]` - মেসেজে রিপ্লাই দেওয়া\n"
            "• `/del [ID]` - নির্দিষ্ট মেসেজ ডিলিট করা\n"
            "• `/ban [User_ID]` - ইউজারকে ব্যান করা\n"
            "• `/mute [User_ID]` - ইউজারকে মিউট করা\n"
            "• `/unmute [User_ID]` - মিউট খোলা\n"
            "• `/kick [User_ID]` - গ্রুপ থেকে বের করা\n"
            "• `/pin [ID]` - মেসেজ পিন করা\n"
            "• `/purge [Amount]` - অনেক মেসেজ একসাথে ডিলিট\n\n"
            "💡 *টিপস:* গ্রুপে যা পাঠাতে চান, সরাসরি এখানে লিখুন।"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ৪. গ্রুপের মেসেজ স্ক্যান ও আইডি জেনারেশন
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID or update.effective_user.id == ADMIN_ID:
        return

    msg = update.message
    text = msg.text or msg.caption or ""

    # অটো লিঙ্ক ডিলিট
    if re.search(URL_PATTERN, text):
        try:
            await msg.delete()
            return
        except: pass

    # ইউজারের মেসেজ ডিলিট করে বটের মাধ্যমে পাঠানো (আইডি সহ)
    try:
        user_info = f"👤 **{msg.from_user.first_name}**\n"
        sent_msg = None

        if msg.text:
            sent_msg = await context.bot.send_message(GROUP_ID, f"{user_info}{msg.text}")
        elif msg.photo:
            sent_msg = await context.bot.send_photo(GROUP_ID, msg.photo[-1].file_id, caption=f"{user_info}{text}")
        elif msg.video:
            sent_msg = await context.bot.send_video(GROUP_ID, msg.video.file_id, caption=f"{user_info}{text}")

        if sent_msg:
            # নতুন আইডি আপডেট করা যাতে আপনি রিপ্লাই দিতে পারেন
            new_id = sent_msg.message_id
            header = f"🆔 ID: ` {new_id} ` | UserID: ` {msg.from_user.id} `\n"
            if sent_msg.text:
                await sent_msg.edit_text(f"{header}{user_info}{msg.text}", parse_mode=ParseMode.MARKDOWN)
            else:
                await sent_msg.edit_caption(caption=f"{header}{user_info}{text}", parse_mode=ParseMode.MARKDOWN)
            
            await msg.delete() # অরিজিনাল মেসেজ ডিলিট
    except Exception as e:
        logging.error(f"Error: {e}")

# ৫. সকল এডমিন একশন (Ban, Mute, Kick, Pin, Del)
async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text.split()
    cmd = text[0].lower()

    try:
        if cmd == "/reply":
            target_id = int(text[1])
            reply_txt = " ".join(text[2:])
            await context.bot.send_message(GROUP_ID, reply_txt, reply_to_message_id=target_id)
        
        elif cmd == "/del":
            await context.bot.delete_message(GROUP_ID, int(text[1]))

        elif cmd == "/ban":
            await context.bot.ban_chat_member(GROUP_ID, int(text[1]))
            await update.message.reply_text("✅ ইউজার ব্যান করা হয়েছে।")

        elif cmd == "/mute":
            await context.bot.restrict_chat_member(GROUP_ID, int(text[1]), permissions=ChatPermissions(can_send_messages=False))
            await update.message.reply_text("🔇 ইউজার মিউট করা হয়েছে।")

        elif cmd == "/unmute":
            perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            await context.bot.restrict_chat_member(GROUP_ID, int(text[1]), permissions=perms)
            await update.message.reply_text("🔊 মিউট খোলা হয়েছে।")

        elif cmd == "/pin":
            await context.bot.pin_chat_message(GROUP_ID, int(text[1]))
            await update.message.reply_text("📌 মেসেজ পিন করা হয়েছে।")

    except Exception as e:
        await update.message.reply_text(f"❌ এরর: {e}")

# ৬. প্রাইভেট মেসেজ সরাসরি গ্রুপে পাঠানো
async def private_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or update.message.text.startswith('/'): return
    try:
        if update.message.text:
            await context.bot.send_message(GROUP_ID, update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(GROUP_ID, update.message.photo[-1].file_id, caption=update.message.caption)
        await update.message.reply_text("✅ গ্রুপে পাঠানো হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"❌ এরর: {e}")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["reply", "del", "ban", "mute", "unmute", "pin"], admin_commands))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), private_to_group))
    
    app.run_polling()
