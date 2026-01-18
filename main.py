import os
import logging
import threading
import re
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ১. ফ্লাস্ক অ্যাপ (Render এর জন্য)
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Admin Control Bot is LIVE!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. টেলিগ্রাম বট কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))

URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        msg = ("🔥 এডমিন প্যানেল সচল!\n\n"
               "📌 /reply [ID] [Text] - রিপ্লাই দিতে\n"
               "📌 /edit [ID] [New Text] - বটের মেসেজ এডিট করতে\n"
               "📌 /delete [ID] - যেকোনো মেসেজ ডিলিট করতে\n"
               "📌 /ban [ID] - ইউজারকে ব্যান করতে (যদি ID পাওয়া যায়)\n")
        await update.message.reply_text(msg)

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID or update.effective_user.id == ADMIN_ID:
        return

    original_msg_id = update.message.message_id
    user_name = update.effective_user.first_name
    text_content = update.message.text or update.message.caption or ""

    # লিংক ফিল্টার
    if re.search(URL_PATTERN, text_content):
        try:
            await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)
            return
        except: pass

    # আইডি স্ক্যানার ও মেসেজ রিপোস্ট
    try:
        prefix_temp = f"👤 User: <b>{user_name}</b>\n\n"
        sent_msg = None
        if update.message.text:
            sent_msg = await context.bot.send_message(chat_id=GROUP_ID, text=prefix_temp + update.message.text, parse_mode=ParseMode.HTML)
        elif update.message.photo:
            sent_msg = await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=prefix_temp + (update.message.caption or ""), parse_mode=ParseMode.HTML)

        if sent_msg:
            new_id = sent_msg.message_id
            final_text = f"🆔 ID: <code>{new_id}</code>\n👤 User: <b>{user_name}</b>\n\n"
            if update.message.text:
                await sent_msg.edit_text(text=final_text + update.message.text, parse_mode=ParseMode.HTML)
            else:
                await sent_msg.edit_caption(caption=final_text + (update.message.caption or ""), parse_mode=ParseMode.HTML)

        await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)
    except Exception as e: logging.error(f"Scan error: {e}")

async def reply_to_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id, reply_text = context.args[0], " ".join(context.args[1:])
        await context.bot.send_message(chat_id=GROUP_ID, text=reply_text, reply_to_message_id=target_id)
        await update.message.reply_text("✅ রিপ্লাই পাঠানো হয়েছে।")
    except: await update.message.reply_text("❌ ভুল ID বা ফরম্যাট।")

async def edit_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বটের নিজের পাঠানো মেসেজ এডিট করা"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id, new_text = context.args[0], " ".join(context.args[1:])
        await context.bot.edit_message_text(chat_id=GROUP_ID, message_id=target_id, text=new_text)
        await update.message.reply_text("✅ মেসেজ এডিট করা হয়েছে।")
    except Exception as e: await update.message.reply_text(f"❌ এডিট করা যায়নি: {e}")

async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """যেকোনো মেসেজ (বটের বা ইউজারের) ডিলিট করা"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = context.args[0]
        await context.bot.delete_message(chat_id=GROUP_ID, message_id=target_id)
        await update.message.reply_text(f"🗑 মেসেজ {target_id} ডিলিট করা হয়েছে।")
    except Exception as e: await update.message.reply_text(f"❌ ডিলিট এরর: {e}")

async def handle_admin_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        await update.message.reply_text("🚀 গ্রুপে পাঠানো হয়েছে।")
    except Exception as e: await update.message.reply_text(f"❌ এরর: {e}")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_id))
    app.add_handler(CommandHandler("edit", edit_msg))
    app.add_handler(CommandHandler("delete", delete_msg))
    
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_admin_private))
    
    print("Full Admin Bot is Running...")
    app.run_polling()
