import os
import logging
import threading
from flask import Flask
from telegram import Update
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
GROUP_ID = int(os.getenv("GROUP_ID")) # নিশ্চিত করুন এটি সংখ্যা (যেমন: -100123456)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("বট সচল আছে! আমি এখন গ্রুপের মেসেজ স্ক্যান করতে প্রস্তুত।")

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """গ্রুপের মেসেজ স্ক্যান করে আইডি সহ পুনরায় পোস্ট করা"""
    if update.effective_chat.id != GROUP_ID:
        return
    
    # এডমিন মেসেজ দিলে সেটাকে স্ক্যান করার দরকার নেই
    if update.effective_user.id == ADMIN_ID:
        return

    user_name = update.effective_user.first_name
    original_msg_id = update.message.message_id
    
    try:
        # মেসেজের ধরন অনুযায়ী আইডি সহ নতুন মেসেজ পাঠানো
        prefix = f"🆔 Message ID: {original_msg_id}\n👤 User: {user_name}\n\n"

        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=prefix + update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=prefix + (update.message.caption or ""))
        elif update.message.video:
            await context.bot.send_video(chat_id=GROUP_ID, video=update.message.video.file_id, caption=prefix + (update.message.caption or ""))
        elif update.message.document:
            await context.bot.send_document(chat_id=GROUP_ID, document=update.message.document.file_id, caption=prefix + (update.message.caption or ""))

        # ইউজারের মূল মেসেজটি ডিলিট করে দেওয়া (যাতে শুধু আইডি ওয়ালা মেসেজ থাকে)
        await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)

    except Exception as e:
        logging.error(f"Error in scanning: {e}")

async def handle_admin_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এডমিন প্রাইভেটে কিছু পাঠালে তা সরাসরি গ্রুপে যাবে (পরিচয় গোপন রেখে)"""
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        if update.message.text:
            await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
        elif update.message.photo:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        # এখানে এডমিনকে কনফার্মেশন দেওয়া
        await update.message.reply_text("গ্রুপে পাঠানো হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"ভুল হয়েছে: {e}")

async def reply_to_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এডমিন আইডি ব্যবহার করে রিপ্লাই দিবে"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        # ব্যবহার: /reply 1234 হ্যালো ভাই
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("সঠিক নিয়ম: /reply [Message_ID] [আপনার মেসেজ]")
            return

        target_id = args[0]
        reply_text = " ".join(args[1:])
        
        await context.bot.send_message(chat_id=GROUP_ID, text=reply_text, reply_to_message_id=target_id)
        await update.message.reply_text("রিপ্লাই দেওয়া হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"রিপ্লাই দেওয়া সম্ভব হয়নি। হয়তো আইডিটি ভুল। Error: {e}")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_id))
    
    # গ্রুপ মেসেজ হ্যান্ডলার (স্ক্যান করার জন্য)
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    # এডমিন প্রাইভেট মেসেজ হ্যান্ডলার (গ্রুপে কিছু পোস্ট করার জন্য)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_admin_private))
    
    print("Bot is starting with ID scanner...")
    app.run_polling()
