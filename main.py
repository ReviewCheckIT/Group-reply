import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment Variables (Render এ সেট করতে হবে)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = os.getenv("GROUP_ID")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("স্বাগতম এডমিন! আপনি এখন গ্রুপে পোস্ট করতে পারেন।")
    else:
        await update.message.reply_text("দুঃখিত, আপনি এই বটটি ব্যবহার করার অনুমতি নেই।")

async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # শুধুমাত্র এডমিন মেসেজ দিলে কাজ করবে
    if update.effective_user.id != ADMIN_ID:
        return

    # যদি কোনো মেসেজের রিপ্লাই হিসেবে এডমিন কিছু লেখে
    if update.message.reply_to_message:
        # এখানে এডমিন গ্রুপের কোনো মেসেজ ফরওয়ার্ড করে তার ওপর রিপ্লাই দিলে সেটা গ্রুপে যাবে
        # অথবা আপনি সরাসরি Message ID ব্যবহার করতে পারেন
        pass

    # টেক্সট, ছবি বা লিংক গ্রুপে পাঠানো
    if update.message.text:
        await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
    elif update.message.photo:
        await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
    elif update.message.document:
        await context.bot.send_document(chat_id=GROUP_ID, document=update.message.document.file_id, caption=update.message.caption)

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ব্যবহার: /reply [message_id] [আপনার মেসেজ]
    """
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        args = context.args
        msg_id = args[0]
        reply_text = " ".join(args[1:])
        await context.bot.send_message(chat_id=GROUP_ID, text=reply_text, reply_to_message_id=msg_id)
        await update.message.reply_text("রিপ্লাই পাঠানো হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"ভুল হয়েছে: {e}\nব্যবহার করুন: /reply [ID] [Message]")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_user))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_admin_messages))
    
    app.run_polling()
