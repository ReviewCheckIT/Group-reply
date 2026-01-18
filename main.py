import os
import logging
import threading
import re
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ১. ফ্লাস্ক অ্যাপ (Render এর পোর্টের জন্য)
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. টেলিগ্রাম বট লজিক
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))

# লিংক চেক করার জন্য Regex
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("বট সচল! আমি এখন আইডি স্ক্যান ও লিংক প্রোটেকশন করতে প্রস্তুত।")

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """গ্রুপের মেসেজ স্ক্যান করা ও লিংক ফিল্টার করা"""
    if update.effective_chat.id != GROUP_ID:
        return
    
    # এডমিন মেসেজ দিলে বট কোনো হস্তক্ষেপ করবে না
    if update.effective_user.id == ADMIN_ID:
        return

    original_msg_id = update.message.message_id
    user_name = update.effective_user.first_name
    text_content = update.message.text or update.message.caption or ""

    # ৩. লিংক ফিল্টার (ইউজার লিংক দিলে ডিলিট হবে)
    if re.search(URL_PATTERN, text_content):
        try:
            await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)
            # একটি অস্থায়ী সতর্কবার্তা (৫ সেকেন্ড পর ডিলিট হবে)
            warn = await context.bot.send_message(chat_id=GROUP_ID, text=f"⚠️ {user_name}, গ্রুপে লিংক পাঠানো নিষেধ!")
            context.job_queue.run_once(lambda c: warn.delete(), 5)
            return
        except:
            pass

    # ৪. মেসেজ আইডি জেনারেট ও কপি করার সুবিধা (HTML code tag ব্যবহার করে)
    try:
        # <code> ট্যাগ ব্যবহার করলে মোবাইল থেকে আইডিতে ক্লিক করলেই কপি হয়ে যাবে
        prefix = f"🆔 ID: <code>{original_msg_id}</code>\n👤 User: <b>{user_name}</b>\n\n"

        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=prefix + update.message.text, parse_mode=ParseMode.HTML)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=prefix + (update.message.caption or ""), parse_mode=ParseMode.HTML)
        elif update.message.video:
            await context.bot.send_video(chat_id=GROUP_ID, video=update.message.video.file_id, caption=prefix + (update.message.caption or ""), parse_mode=ParseMode.HTML)
        elif update.message.document:
            await context.bot.send_document(chat_id=GROUP_ID, document=update.message.document.file_id, caption=prefix + (update.message.caption or ""), parse_mode=ParseMode.HTML)

        # ইউজারের মূল মেসেজটি ডিলিট করা
        await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)

    except Exception as e:
        logging.error(f"Scanning error: {e}")

async def reply_to_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """আইডি দিয়ে রিপ্লাই দেওয়া"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("ব্যবহার: /reply [ID] [Message]")
            return
        target_id, reply_text = args[0], " ".join(args[1:])
        await context.bot.send_message(chat_id=GROUP_ID, text=reply_text, reply_to_message_id=target_id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """আইডি দিয়ে যে কোনো মেসেজ ডিলিট করা"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        if not context.args:
            await update.message.reply_text("ব্যবহার: /delete [Message_ID]")
            return
        target_id = context.args[0]
        await context.bot.delete_message(chat_id=GROUP_ID, message_id=target_id)
        await update.message.reply_text(f"মেসেজ {target_id} ডিলিট করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"ডিলিট করা যায়নি: {e}")

async def handle_admin_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এডমিন সরাসরি মেসেজ বা ছবি দিলে গ্রুপে যাবে"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        await update.message.reply_text("পাঠানো হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_id))
    app.add_handler(CommandHandler("delete", delete_msg)) # ডিলিট কমান্ড যুক্ত করা হলো
    
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_admin_private))
    
    print("Bot is LIVE with Link Filter and Click-to-Copy ID...")
    app.run_polling()
