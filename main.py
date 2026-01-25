import os
import logging
import threading
import re
import html
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# ১. Render এর জন্য Web Server
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Skyzone IT AI Bot is Running!"

def run_web_server():
    # Render ডিফল্টভাবে ১০০০০ পোর্ট ব্যবহার করে
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) # প্রধান এডমিন
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

# Groq ক্লায়েন্ট সেটআপ
client = Groq(api_key=GROQ_API_KEY)

# এআই এর জন্য গাইডলাইন (System Prompt)
SYSTEM_PROMPT = """
আপনি Skyzone IT গ্রুপের একজন অত্যন্ত পেশাদার এআই অ্যাসিস্ট্যান্ট। 
১. আপনার মূল কাজ হলো গ্রুপের সদস্যদের সাথে চ্যাট করা এবং তাদের সাহায্য করা।
২. নতুন সদস্য এলে তাকে 'পাকিজা' বলে সম্বোধন করবেন এবং স্বাগতম জানাবেন।
৩. সদস্যরা যেহেতু টেস্ট পাশ করে গ্রুপে এসেছে, তাই তাদের নির্দেশ দিন প্রথমে আমাদের মাস্টার ভিডিওটি দেখতে। ভিডিও লিঙ্ক: https://youtu.be/Yh1No2eDBuU?si=wJvjBMrEjakBOEgb
৪. ভিডিও দেখার পর তাদের ইন্টারভিউ দিতে বলুন এই বটে: https://t.me/SkyzoneIT_bot?start=welcome। সেখানে ১০টি প্রশ্নের উত্তর দিতে হবে।
৫. ১০টি প্রশ্নের উত্তর দিলে তারা এডমিনের ইউজারনেম পাবে এবং কাজ শুরু করতে পারবে।
৬. এডমিনদের সাথে সবসময় বিনয়ী থাকবেন। এডমিন মেসেজ দিলে আপনি চুপ থাকবেন।
৭. কোনো বিষয়ে উত্তর না জানলে সরাসরি বলবেন "এই বিষয়ে এডমিন ভালো বলতে পারবেন, অনুগ্রহ করে এডমিনের সাথে যোগাযোগ করুন।"
৮. কাজের গোপন প্রসেস (রিভিউ প্রসেস/ফেসবুক হায়ার) নিয়ে সদস্যদের সাথে আলোচনা করবেন না, এটি শুধু আপনার ব্যাকগ্রাউন্ড নলেজ।
৯. অযথা লিঙ্ক দেবেন না। কথা বলার প্রসঙ্গে যদি ভিডিও বা বটের কথা আসে, তখনই লিঙ্ক দেবেন।
১০. আপনার কথা বলার ধরণ হবে অত্যন্ত উন্নত মানের এবং পেশাদার।
"""

# ৩. এআই রিপ্লাই ফাংশন
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
        return html.escape(response) # HTML এরর এড়াতে
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "পাকিজা, আমি এই মুহূর্তে উত্তর দিতে পারছি না। অনুগ্রহ করে এডমিনের সাথে যোগাযোগ করুন।"

# ৪. হ্যান্ডলার ফাংশন
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    # ১. লিঙ্ক প্রটেকশন (সবাইর জন্য, শুধু এডমিন ছাড়া)
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(GROUP_ID, user_id)
    is_admin = chat_member.status in ['administrator', 'creator']

    text = update.message.text or update.message.caption or ""

    if not is_admin and re.search(URL_PATTERN, text):
        try:
            await update.message.delete()
            return
        except: pass

    # ২. এডমিন মেসেজ দিলে এআই রিপ্লাই দিবে না
    if is_admin:
        return

    # ৩. শুধু নির্দিষ্ট গ্রুপে এআই কাজ করবে
    if update.effective_chat.id == GROUP_ID:
        ai_reply = await get_ai_response(text)
        await update.message.reply_text(ai_reply, parse_mode=ParseMode.HTML)

# ৫. স্টার্ট কমান্ড (এডমিনের জন্য)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("✅ **পাকিজা, এআই সিস্টেম সফলভাবে চালু হয়েছে।**")

if __name__ == '__main__':
    # ওয়েব সার্ভার থ্রেড
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # টেলিগ্রাম বট
    app = ApplicationBuilder().token(TOKEN).build()
    
    # হ্যান্ডলার যুক্ত করা
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_messages))
    
    print("Bot is running...")
    app.run_polling()
