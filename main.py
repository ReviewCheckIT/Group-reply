import os
import logging
import threading
import re
import html
import asyncio
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# ১. Render এর জন্য Web Server (Health Check)
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Skyzone IT AI Bot is Active!"

def run_web_server():
    # Render এর জন্য পোর্ট কনফিগারেশন (Default 10000)
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন এবং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# লিঙ্ক প্যাটার্ন (লিঙ্ক ডিলিট করার জন্য)
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

client = Groq(api_key=GROQ_API_KEY)

# ৩. এআই এর মস্তিষ্ক (System Prompt)
# এখানে আপনার দেওয়া সকল লজিক এবং গোপন তথ্য সেট করা হয়েছে
SYSTEM_PROMPT = """
আপনি Skyzone IT গ্রুপের একজন অত্যন্ত প্রফেশনাল এবং বন্ধুত্বপূর্ণ এআই অ্যাসিস্ট্যান্ট।

আপনার আচরণের নির্দেশাবলী:
১. নতুন মেম্বারদের স্বাগতম জানানোর সময় অবশ্যই "পাকিজা" শব্দটি ব্যবহার করবেন।
২. সরাসরি প্রথমেই কোনো লিঙ্ক দেবেন না। আগে ইউজারের সাথে হাই/হ্যালো বা সাধারণ কথা বলুন। যখন ইউজার কাজের বিষয়ে জানতে চাইবে বা কথা প্রসঙ্গ আসবে, তখনই কেবল লিঙ্ক দেবেন।
৩. আপনার কথা বলার স্টাইল হবে মানুষের মতো (Human-like)। রোবটের মতো আচরণ করবেন না।
৪. এডমিনরা গ্রুপে মেসেজ দিলে আপনি কোনো উত্তর দেবেন না। আপনি চুপ থাকবেন।
৫. যদি কোনো বিষয় আপনার অজানা থাকে, তবে বলবেন "এই বিষয়টি এডমিন ভালো বলতে পারবেন।"

কাজের নির্দেশনা (ইউজারদের যা বলবেন):
- যেহেতু তারা গ্রুপে এসেছে, তার মানে তারা টেস্ট পাশ করেছে।
- তাদের কাজের নিয়ম শেখার জন্য প্রথমে মাস্টার ভিডিওটি দেখতে বলুন। ভিডিও লিঙ্ক: https://youtu.be/Yh1No2eDBuU?si=wJvjBMrEjakBOEgb
- ভিডিও দেখার পর তাদের ইন্টারভিউ দিতে হবে। ইন্টারভিউ বটের লিঙ্ক: https://t.me/SkyzoneIT_bot?start=welcome
- ইন্টারভিউ বরে ১০টি প্রশ্ন করা হবে। সঠিক উত্তর দিলে এডমিনের ইউজারনেম পাওয়া যাবে, সেখানে স্লিপ জমা দিয়ে কাজ বুঝে নিতে হবে।

গোপন তথ্য (শুধুমাত্র আপনার জানার জন্য, ইউজারকে নিজে থেকে বলবেন না):
- আমরা ফেসবুকে পোস্ট দিয়ে লোক আনি। তারা অ্যাপে রিভিউ দেয়। ২৪ ঘণ্টা পর রিভিউ লাইভ হলে তাদের গ্রুপে অ্যাড করা হয়। তারা অন্যদেরও এভাবে অ্যাড করায়। এই প্রসেসটা আপনি জানবেন কিন্তু নিজে থেকে প্রচার করবেন না।

সতর্কতা:
- ইউজার যেন বিরক্ত না হয়।
- লিঙ্ক দেওয়ার আগে নিশ্চিত হোন ইউজার প্রস্তুত কিনা বা কথার প্রসঙ্গে লিঙ্কটি আসছে কিনা।
"""

# ৪. এআই রেসপন্স ফাংশন
async def get_ai_response(user_text, user_name):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User Name: {user_name}\nMessage: {user_text}"},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7, # ন্যাচারাল কথার জন্য টেম্পারেচার সেট করা হলো
            max_tokens=300
        )
        response = chat_completion.choices[0].message.content
        # HTML পার্সিং এরর এড়ানোর জন্য এস্কেপ করা হচ্ছে
        return html.escape(response)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return None

# ৫. গ্রুপের মেসেজ হ্যান্ডলার
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # যদি মেসেজ না থাকে বা অন্য গ্রুপ হয়
    if not update.message or update.effective_chat.id != GROUP_ID:
        return

    user = update.message.from_user
    text = update.message.text or update.message.caption or ""

    # --- রুলস ১: এডমিন চেক ---
    # মেসেজটি এডমিনের হলে বট চুপ থাকবে (রিটার্ন করবে)
    if user.id == ADMIN_ID:
        return
    
    # এপিআই কল কমানোর জন্য চেক করা যে ইউজার কি এডমিন কিনা (Optional Check)
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user.id)
        if member.status in ['administrator', 'creator']:
            return
    except:
        pass

    # --- রুলস ২: লিঙ্ক ডিলিট ---
    # সাধারণ ইউজার লিঙ্ক দিলে ডিলিট হবে
    if re.search(URL_PATTERN, text):
        try:
            await update.message.delete()
            # এআই এখানে চাইলে ওয়ার্নিং দিতে পারে, কিন্তু বিরক্ত না করতে চাইলে চুপ থাকাই ভালো
            return 
        except Exception as e:
            logging.error(f"Link Delete Error: {e}")
            return

    # --- রুলস ৩: এআই চ্যাট ---
    # উপরের সব ফিল্টার পার হলে এআই উত্তর দিবে
    try:
        # টাইপিং ইন্ডিকেটর দেখানো (রিয়েলিস্টিক ভাব আনার জন্য)
        await context.bot.send_chat_action(chat_id=GROUP_ID, action="typing")
        
        ai_reply = await get_ai_response(text, user.first_name)
        
        if ai_reply:
            await update.message.reply_text(
                ai_reply,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logging.error(f"Reply Error: {e}")

# ৬. সাধারণ স্টার্ট কমান্ড (বট জীবিত কিনা চেক করার জন্য)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("✅ বট অনলাইনে আছে এবং এআই কাজ করছে।")

# ৭. মেইন ফাংশন
if __name__ == '__main__':
    # Flask সার্ভার একটি আলাদা থ্রেডে রান হবে যাতে Render পোর্ট ডিটেক্ট করতে পারে
    flask_thread = threading.Thread(target=run_web_server, daemon=True)
    flask_thread.start()
    
    # টেলিগ্রাম বট সেটআপ
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    # সকল মেসেজ হ্যান্ডলার (গ্রুপের জন্য)
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    print("Bot is starting polling...")
    # লুপ যেন বন্ধ না হয়
    app.run_polling(allowed_updates=Update.ALL_TYPES)
