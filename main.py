import os
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ১. ফ্লাস্ক অ্যাপ তৈরি (Render এর পোর্ট সমস্যা সমাধানের জন্য)
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_web_server():
    # Render অটোমেটিক 'PORT' এনভায়রনমেন্ট ভ্যারিয়েবল দেয়
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. টেলিগ্রাম বট লজিক
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = os.getenv("GROUP_ID")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("বট সচল আছে এডমিন!")

async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # টেক্সট, ছবি বা লিংক গ্রুপে ফরোয়ার্ড করা
    try:
        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        elif update.message.document:
            await context.bot.send_document(chat_id=GROUP_ID, document=update.message.document.file_id, caption=update.message.caption)
        elif update.message.video:
            await context.bot.send_video(chat_id=GROUP_ID, video=update.message.video.file_id, caption=update.message.caption)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        # ব্যবহার: /reply [message_id] [আপনার মেসেজ]
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("সঠিক নিয়ম: /reply [Msg_ID] [Text]")
            return

        msg_id = args[0]
        reply_text = " ".join(args[1:])
        await context.bot.send_message(chat_id=GROUP_ID, text=reply_text, reply_to_message_id=msg_id)
    except Exception as e:
        await update.message.reply_text(f"ভুল হয়েছে: {e}")

if __name__ == '__main__':
    # ওয়েব সার্ভারটি আলাদা থ্রেডে চালানো
    threading.Thread(target=run_web_server, daemon=True).start()

    # টেলিগ্রাম বট রান করা
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_user))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_admin_messages))
    
    print("Bot is starting...")
    app.run_polling()
