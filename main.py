import os
import logging
import threading
import re
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq # Groq লাইব্রেরি

# ১. Render এর জন্য Web Server
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Bot is Running with AI!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY") # Render এ GROQ_API_KEY নামে কী সেট করবেন
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

# Groq ক্লায়েন্ট সেটআপ
client = Groq(api_key=GROQ_API_KEY)

# এআই এর জন্য সিস্টেম প্রম্পট (আপনার ব্যবসার তথ্য)
SYSTEM_PROMPT = """
আপনি এই টেলিগ্রাম গ্রুপের একজন হেল্পফুল অ্যাসিস্ট্যান্ট। আপনার গ্রুপের কাজের ধরন নিম্নরূপ:
১. আমাদের কাজ হলো প্লে-স্টোরের নতুন অ্যাপগুলোতে (যেখানে কোনো রিভিউ নেই) রিভিউ দেওয়া।
২. আমরা লোক নিয়োগ দিচ্ছি যারা আমাদের সাথে কাজ করবে। 
৩. নতুন কেউ আসলে তাকে একটি 'টেস্ট' দিতে হয়। টেস্ট হলো: তাকে একটি অ্যাপ দেওয়া হবে, সে তাতে রিভিউ দিবে। ২৪ ঘণ্টা পর যদি রিভিউটি লাইভ হয়, তবেই সে গ্রুপে জয়েন করে কাজ শুরু করতে পারবে।
৪. নতুন মেম্বাররা জয়েন হওয়ার পর অন্যদেরও একইভাবে টেস্ট নিয়ে গ্রুপে নিয়ে আসতে পারবে। 
৫. কাজ শেখার জন্য একটি নির্দিষ্ট ভিডিও আছে। নতুন মেম্বারদের সেই ভিডিওর লিঙ্ক দেওয়া হয় যাতে তারা কাজ শিখতে পারে। (ইউজারকে ভিডিও লিঙ্ক চাইলে দিতে হবে)।
৬. আমাদের একটি নতুন ওয়েবসাইট তৈরি হচ্ছে যেখানে ভবিষ্যতে কাজ করা যাবে।
৭. আপনার কথা বলার ধরণ হবে বন্ধুত্বপূর্ণ এবং পেশাদার। কেউ কাজে আগ্রহ দেখালে তাকে প্রসেস বুঝিয়ে বলুন।
"""

# ৩. এআই রিপ্লাই ফাংশন
async def get_ai_response(user_text):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            model="llama-3.3-70b-versatile", # আপনি চাইলে অন্য মডেল ব্যবহার করতে পারেন
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "দুঃখিত, আমি এই মুহূর্তে উত্তর দিতে পারছি না। অনুগ্রহ করে একটু পরে চেষ্টা করুন।"

# ৪. স্টার্ট কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        msg = (
            "🛠 **এআই বট কন্ট্রোল প্যানেল সচল**\n\n"
            "📌 **ম্যানেজমেন্ট কমান্ডস:**\n"
            "• `/reply [ID] [Text]` - মেসেজে রিপ্লাই দেওয়া\n"
            "• `/del [ID]` - নির্দিষ্ট মেসেজ ডিলিট করা\n"
            "• `/ban [User_ID]` - ইউজারকে ব্যান করা\n"
            "• `/mute [User_ID]` - ইউজারকে মিউট করা\n"
            "• `/unmute [User_ID]` - মিউট খোলা\n"
            "• `/pin [ID]` - মেসেজ পিন করা\n\n"
            "💡 এআই এখন গ্রুপের মেম্বারদের প্রশ্নের উত্তর দিবে।"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ৫. গ্রুপের মেসেজ স্ক্যান, আইডি জেনারেশন এবং এআই রিপ্লাই
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID or update.effective_user.id == ADMIN_ID:
        return

    msg = update.message
    text = msg.text or msg.caption or ""

    # অটো লিঙ্ক ডিলিট (আগের ফিচার)
    if re.search(URL_PATTERN, text):
        try:
            await msg.delete()
            return
        except: pass

    # ইউজারের মেসেজ প্রসেস করা এবং এআই রিপ্লাই জেনারেট করা
    try:
        user_info = f"👤 **{msg.from_user.first_name}**\n"
        
        # এআই থেকে উত্তর নেওয়া
        ai_reply = await get_ai_response(text)
        
        # বটের মাধ্যমে মেসেজ পাঠানো (আগের মতো আইডি সহ)
        sent_msg = await context.bot.send_message(
            GROUP_ID, 
            f"🆔 ID: Processing...\n\n{user_info}{ai_reply}", 
            parse_mode=ParseMode.MARKDOWN
        )

        if sent_msg:
            new_id = sent_msg.message_id
            header = f"🆔 ID: ` {new_id} ` | UserID: ` {msg.from_user.id} `\n\n"
            await sent_msg.edit_text(f"{header}{user_info}{ai_reply}", parse_mode=ParseMode.MARKDOWN)
            
            await msg.delete() # অরিজিনাল মেসেজ ডিলিট
    except Exception as e:
        logging.error(f"Error: {e}")

# ৬. সকল এডমিন একশন (Ban, Mute, Kick, Pin, Del) - অপরিবর্তিত
async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text.split()
    if not text: return
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

# ৭. প্রাইভেট মেসেজ সরাসরি গ্রুপে পাঠানো
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
