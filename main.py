import os
import logging
import threading
import re
import html
import asyncio
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# ১. কনফিগারেশন এবং লগিং
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

# Groq ক্লায়েন্ট
client = Groq(api_key=GROQ_API_KEY)

# এআই এর জন্য সিস্টেম প্রম্পট
SYSTEM_PROMPT = """
আপনি এই টেলিগ্রাম গ্রুপের একজন হেল্পফুল অ্যাসিস্ট্যান্ট। আপনার গ্রুপের কাজের ধরন নিম্নরূপ:
১. আমাদের কাজ হলো প্লে-স্টোরের নতুন অ্যাপগুলোতে রিভিউ দেওয়া।
২. আমরা লোক নিয়োগ দিচ্ছি যারা আমাদের সাথে কাজ করবে। 
৩. নতুন কেউ আসলে তাকে একটি 'টেস্ট' দিতে হয়। টেস্ট হলো: তাকে একটি অ্যাপ দেওয়া হবে, সে তাতে রিভিউ দিবে। ২৪ ঘণ্টা পর যদি রিভিউটি লাইভ হয়, তবেই সে গ্রুপে জয়েন করে কাজ শুরু করতে পারবে।
৪. নতুন মেম্বাররা জয়েন হওয়ার পর অন্যদেরও একইভাবে টেস্ট নিয়ে গ্রুপে নিয়ে আসতে পারবে। 
৫. কাজ শেখার জন্য একটি ভিডিও লিঙ্ক আছে, যা নতুনদের দিতে হবে।
৬. নতুন একটি ওয়েবসাইট তৈরি হচ্ছে যেখানে ভবিষ্যতে কাজ করা যাবে।
"""

# ২. Render এর জন্য Web Server (Flask)
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Active and Running!"

def run_web_server():
    # Render সাধারণত ১০০০০ পোর্ট ব্যবহার করে
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ৩. এআই রিপ্লাই ফাংশন (সেফ মোড)
async def get_ai_response(user_text):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            model="llama-3.3-70b-versatile",
        )
        response = chat_completion.choices[0].message.content
        # টেলিগ্রাম HTML এরর এড়াতে এস্কেপ করা
        return html.escape(response)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "দুঃখিত, আমি এই মুহূর্তে উত্তর দিতে পারছি না।"

# ৪. কমান্ড এবং মেসেজ হ্যান্ডলার
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        msg = (
            "<b>🛠 কন্ট্রোল প্যানেল সচল</b>\n\n"
            "• <code>/reply [ID] [Text]</code>\n"
            "• <code>/del [ID]</code>\n"
            "• <code>/ban [User_ID]</code>\n"
            "• <code>/mute [User_ID]</code>\n"
            "• <code>/unmute [User_ID]</code>\n"
            "• <code>/pin [ID]</code>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # শুধু নির্দিষ্ট গ্রুপ এবং সাধারণ ইউজারদের জন্য
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

    try:
        user_name = html.escape(msg.from_user.first_name)
        ai_reply = await get_ai_response(text)
        
        # মেসেজ পাঠানো এবং আইডি দেখানো
        sent_msg = await context.bot.send_message(
            GROUP_ID,
            f"👤 <b>{user_name}</b>\n\n{ai_reply}",
            parse_mode=ParseMode.HTML
        )
        
        # আইডি সহ আপডেট (যাতে এডমিন রিপ্লাই দিতে পারে)
        header = f"🆔 ID: <code>{sent_msg.message_id}</code> | UserID: <code>{msg.from_user.id}</code>\n\n"
        await sent_msg.edit_text(f"{header}👤 <b>{user_name}</b>\n\n{ai_reply}", parse_mode=ParseMode.HTML)
        
        await msg.delete()
    except Exception as e:
        logging.error(f"Error: {e}")

async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    args = update.message.text.split()
    cmd = args[0].lower()

    try:
        if cmd == "/reply" and len(args) > 2:
            await context.bot.send_message(GROUP_ID, " ".join(args[2:]), reply_to_message_id=int(args[1]))
        elif cmd == "/del":
            await context.bot.delete_message(GROUP_ID, int(args[1]))
        elif cmd == "/ban":
            await context.bot.ban_chat_member(GROUP_ID, int(args[1]))
            await update.message.reply_text("✅ ব্যান সফল।")
        elif cmd == "/mute":
            await context.bot.restrict_chat_member(GROUP_ID, int(args[1]), permissions=ChatPermissions(can_send_messages=False))
            await update.message.reply_text("🔇 মিউট সফল।")
        elif cmd == "/unmute":
            perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            await context.bot.restrict_chat_member(GROUP_ID, int(args[1]), permissions=perms)
            await update.message.reply_text("🔊 মিউট খোলা হয়েছে।")
        elif cmd == "/pin":
            await context.bot.pin_chat_message(GROUP_ID, int(args[1]))
    except Exception as e:
        await update.message.reply_text(f"❌ এরর: {e}")

async def private_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or update.message.text.startswith('/'): return
    try:
        await context.bot.send_message(GROUP_ID, update.message.text or update.message.caption)
        await update.message.reply_text("✅ গ্রুপে পাঠানো হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"❌ এরর: {e}")

# ৫. মেইন ফাংশন
if __name__ == '__main__':
    # ফ্লাস্ক ওয়েব সার্ভার থ্রেডে চালানো
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # টেলিগ্রাম বট সেটআপ
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["reply", "del", "ban", "mute", "unmute", "pin"], admin_commands))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), private_to_group))
    
    print("Bot is polling...")
    app.run_polling()
