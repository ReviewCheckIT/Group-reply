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
        await update.message.reply_text("বট সচল! এখন আপনি নিজের আইডি গোপন রেখে মেসেজ পাঠাতে, রিপ্লাই দিতে এবং যেকোনো মেসেজ ডিলিট করতে পারবেন।")

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """গ্রুপের মেসেজ স্ক্যান করা ও সঠিক আইডি প্রদান করা"""
    if update.effective_chat.id != GROUP_ID:
        return
    
    # এডমিন মেসেজ দিলে বট কোনো হস্তক্ষেপ করবে না, তবে এডমিনের মেসেজ আইডিও দেখাবে না
    # যদি আপনি চান নিজের পাঠানো মেসেজেরও আইডি দেখাবে তবে নিচের ৩ লাইন রিমুভ করতে পারেন
    if update.effective_user.id == ADMIN_ID:
        return

    original_msg_id = update.message.message_id
    user_name = update.effective_user.first_name
    text_content = update.message.text or update.message.caption or ""

    # ৩. লিংক ফিল্টার (ইউজার লিংক দিলে সাথে সাথে ডিলিট)
    if re.search(URL_PATTERN, text_content):
        try:
            await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)
            return
        except:
            pass

    # ৪. মেসেজ পুনরায় পাঠানো এবং বটের নিজের মেসেজের ID সংগ্রহ করা
    try:
        prefix_temp = f"👤 User: <b>{user_name}</b>\n\n"
        sent_msg = None

        if update.message.text:
            sent_msg = await context.bot.send_message(chat_id=GROUP_ID, text=prefix_temp + update.message.text, parse_mode=ParseMode.HTML)
        elif update.message.photo:
            sent_msg = await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=prefix_temp + (update.message.caption or ""), parse_mode=ParseMode.HTML)
        elif update.message.video:
            sent_msg = await context.bot.send_video(chat_id=GROUP_ID, video=update.message.video.file_id, caption=prefix_temp + (update.message.caption or ""), parse_mode=ParseMode.HTML)
        elif update.message.document:
            sent_msg = await context.bot.send_document(chat_id=GROUP_ID, document=update.message.document.file_id, caption=prefix_temp + (update.message.caption or ""), parse_mode=ParseMode.HTML)

        if sent_msg:
            # বটের পাঠানো মেসেজের নতুন ID দিয়ে টেক্সট আপডেট (কপি-টু-ক্লিক সুবিধা)
            new_id = sent_msg.message_id
            final_text = f"🆔 ID: <code>{new_id}</code>\n👤 User: <b>{user_name}</b>\n\n"
            
            if update.message.text:
                await sent_msg.edit_text(text=final_text + update.message.text, parse_mode=ParseMode.HTML)
            else:
                await sent_msg.edit_caption(caption=final_text + (update.message.caption or ""), parse_mode=ParseMode.HTML)

        # ইউজারের মূল মেসেজ ডিলিট করা
        await context.bot.delete_message(chat_id=GROUP_ID, message_id=original_msg_id)

    except Exception as e:
        logging.error(f"Scanning error: {e}")

async def reply_to_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বটের ইনবক্স থেকে গ্রুপে রিপ্লাই দেওয়া"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("সঠিক নিয়ম: /reply [ID] [Message]")
            return
        
        target_id = int(args[0])
        reply_text = " ".join(args[1:])
        
        # রিপ্লাই পাঠানো
        await context.bot.send_message(chat_id=GROUP_ID, text=reply_text, reply_to_message_id=target_id)
        await update.message.reply_text("সফলভাবে রিপ্লাই দেওয়া হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"ভুল: {e}")

async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """যেকোনো মেসেজ আইডি দিয়ে ডিলিট করা (বটের নিজের বা অন্য এডমিনের)"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        if not context.args:
            await update.message.reply_text("সঠিক নিয়ম: /delete [ID]")
            return
        
        target_id = int(context.args[0])
        
        # গ্রুপ থেকে মেসেজটি ডিলিট করা
        await context.bot.delete_message(chat_id=GROUP_ID, message_id=target_id)
        await update.message.reply_text(f"মেসেজ (ID: {target_id}) সফলভাবে ডিলিট করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"ডিলিট করা যায়নি! ভুল: {e}\n(সম্ভবত মেসেজটি ডিলিট হয়ে গেছে বা বট এডমিন নয়)")

async def handle_admin_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এডমিন প্রাইভেটে কিছু পাঠালে তা গ্রুপে বটের নামে যাবে"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        sent_msg = None
        if update.message.text:
            sent_msg = await context.bot.send_message(chat_id=GROUP_ID, text=update.message.text)
        elif update.message.photo:
            sent_msg = await context.bot.send_photo(chat_id=GROUP_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        
        if sent_msg:
            # আপনি যদি চান আপনার পাঠানো মেসেজ ডিলিট করতে হতে পারে, তবে আইডিটি আপনাকে জানিয়ে দিবে
            await update.message.reply_text(f"গ্রুপে পাঠানো হয়েছে।\nমেসেজ আইডি: <code>{sent_msg.message_id}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"ভুল: {e}")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_id))
    app.add_handler(CommandHandler("delete", delete_msg))
    
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), handle_admin_private))
    
    app.run_polling()
