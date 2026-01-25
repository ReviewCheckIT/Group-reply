import os
import logging
import threading
import re
import html
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# ১. Render এর জন্য Web Server
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Skyzone IT AI Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

# Groq এআই ক্লায়েন্ট সেটআপ
client = Groq(api_key=GROQ_API_KEY)

# এআই এর জন্য নির্দেশনাবলী (System Prompt)
SYSTEM_PROMPT = """
আপনি 'Skyzone IT' গ্রুপের একজন অত্যন্ত পেশাদার এবং উন্নত মানের এআই অ্যাসিস্ট্যান্ট। 

আপনার নিয়মাবলী:
১. নতুন বা বিদ্যমান মেম্বারদের 'পাকিজা' বলে সম্বোধন করবেন। 
২. তারা যেহেতু গ্রুপে এসেছে, তার মানে তারা টেস্ট দিয়ে পাশ করেছে। তাদের স্বাগতম জানান।
৩. আপনার প্রধান কাজ তাদের সঠিক নির্দেশনা দেওয়া:
   - প্রথমে এই মাস্টার ভিডিওটি দেখে কাজ শিখতে হবে: https://youtu.be/Yh1No2eDBuU?si=wJvjBMrEjakBOEgb
   - ভিডিও দেখার পর এই বটে গিয়ে ১০টি প্রশ্নের ইন্টারভিউ দিতে হবে: https://t.me/SkyzoneIT_bot?start=welcome
   - ইন্টারভিউতে পাশ করলে বট থেকে পাওয়া স্লিপ এবং ফরম পূরণের স্ক্রিনশট এডমিনকে পাঠাতে হবে। এরপর এডমিন কাজ ও ওয়েবসাইট লিংক দিবেন।
৪. এডমিনদের মেসেজে আপনি কখনোই রিপ্লাই দিবেন না। এডমিনদের সর্বোচ্চ সম্মান দিবেন।
৫. যদি কোনো বিষয় আপনার বুঝতে সমস্যা হয় বা আপনি উত্তর না জানেন, তবে বিনয়ের সাথে মেম্বারকে এডমিনের সাথে কথা বলতে বলবেন।
৬. গোপন তথ্য (মানুষকে দিয়ে রিভিউ করানো বা ফেসবুক রিক্রুটমেন্ট) কখনোই ইউজারদের সাথে শেয়ার করবেন না। এটি আপনার ইন্টারনাল নলেজ।
৭. আপনার কথা বলার ধরণ হবে অত্যন্ত প্রফেশনাল এবং পেশাদার। ফালতু কথা বলবেন না।
"""

# ৩. এআই থেকে উত্তর পাওয়ার ফাংশন
async def get_ai_response(user_text):
    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            model="llama-3.3-70b-versatile",
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "পাকিজা, আমি আন্তরিকভাবে দুঃখিত। এই বিষয়ে আমি সঠিক তথ্য দিতে পারছি না, অনুগ্রহ করে এডমিনের সাহায্য নিন।"

# ৪. নতুন মেম্বার জয়েন হলে স্বাগতম জানানো
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        welcome_text = (
            f"স্বাগতম পাকিজা <b>{html.escape(member.first_name)}</b>!\n\n"
            "আমাদের গ্রুপে আসার জন্য আপনাকে অভিনন্দন। আপনি যেহেতু টেস্ট পাশ করে এসেছেন, এখন আপনার পরবর্তী কাজ হলো:\n"
            "১. নিচের মাস্টার ভিডিওটি সম্পূর্ণ দেখে কাজ শিখুন:\n"
            "🔗 <a href='https://youtu.be/Yh1No2eDBuU?si=wJvjBMrEjakBOEgb'>ভিডিও লিংক এখানে</a>\n\n"
            "২. ভিডিও দেখা শেষ হলে ইন্টারভিউ দিন এই বটে:\n"
            "🔗 <a href='https://t.me/SkyzoneIT_bot?start=welcome'>ইন্টারভিউ বট লিংক</a>\n\n"
            "ধন্যবাদ!"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

# ৫. গ্রুপের মেসেজ হ্যান্ডল করা
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text or update.message.caption or ""

    # ১. লিঙ্ক ডিলিট করা (এডমিন ছাড়া অন্য কেউ লিঙ্ক দিলে)
    if re.search(URL_PATTERN, text) and user_id != ADMIN_ID:
        try:
            await update.message.delete()
            return
        except: pass

    # ২. এডমিন মেসেজ দিলে এআই চুপ থাকবে
    if user_id == ADMIN_ID or chat_id != GROUP_ID:
        return

    # ৩. সাধারণ মেম্বারদের জন্য এআই রিপ্লাই
    ai_reply = await get_ai_response(text)
    await update.message.reply_text(ai_reply)

# ৬. এডমিনের জন্য স্টার্ট কমান্ড (বট চেক করার জন্য)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("✅ Skyzone IT Professional AI Bot সচল আছে।")

if __name__ == '__main__':
    # ওয়েব সার্ভার রান করা
    threading.Thread(target=run_web_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # হ্যান্ডলার সেটআপ
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_messages))
    
    # বট চালানো
    print("Bot is running...")
    app.run_polling()
