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
    return "Skyzone IT AI Bot is Active (Human Mode)!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# লিংক প্যাটার্ন (লিঙ্ক ডিলিট করার জন্য)
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

client = Groq(api_key=GROQ_API_KEY)

# ৩. এআই-এর জন্য কড়া নির্দেশ (System Prompt)
# এখানে এআই-কে বাধ্য করা হয়েছে যেন সে হুট করে লিংক না দেয়
SYSTEM_PROMPT = """
আপনি Skyzone IT গ্রুপের একজন বিশ্বস্ত এবং প্রফেশনাল টিম মেম্বার। আপনি কোনো রোবট নন, আপনি একজন মানুষ হিসেবে কথা বলবেন।

আপনার কঠোর নিয়মাবলী (Strict Rules):
১. **প্রথমেই কোনো লিংক দেবেন না।** ইউজার যদি 'Hi', 'Hello', 'ভাই', 'আছেন?' ইত্যাদি বলে, তবে আপনি শুধু কুশল বিনিময় করবেন। যেমন: "জি ভাইয়া/আপু, বলুন কিভাবে সাহায্য করতে পারি?" অথবা "পাকিজা! আমাদের গ্রুপে স্বাগতম।"
২. যতক্ষণ না ইউজার কাজের ব্যাপারে বিস্তারিত জানতে চাইছে বা বলছে "কাজটা কী?", ততক্ষণ ভিডিও লিংক বা বটের লিংক দেবেন না।
৩. কথা বলার ধরন হবে খুবই স্বাভাবিক এবং আন্তরিক। রোবটের মতো বড় বড় মেসেজ দেবেন না। ছোট ছোট মেসেজে রিপ্লাই দিন।
৪. **লিংক দেওয়ার সময়:** যখন ইউজার কাজের আগ্রহ দেখাবে, তখন বলুন: "কাজটা শুরু করার জন্য আপনাকে প্রথমে এই ভিডিওটি দেখে নিতে হবে: https://youtu.be/Yh1No2eDBuU?si=wJvjBMrEjakBOEgb"
৫. ভিডিও দেখার পর যখন তারা পরবর্তী ধাপ চাইবে, তখন ইন্টারভিউ বটের লিংক দেবেন: https://t.me/SkyzoneIT_bot?start=welcome
৬. এডমিনরা (Admin) মেসেজ দিলে আপনি সম্পূর্ণ চুপ থাকবেন। কোনো উত্তর দেবেন না।
৭. মনে রাখবেন: আমরা ফেসবুকে পোস্ট করে লোক আনি, তারা রিভিউ দিয়ে টেস্ট পাশ করে এখানে এসেছে। তাই তাদের সাথে ভালো ব্যবহার করুন।

গোপন নির্দেশনা: আপনি জানেন যে ২৪ ঘণ্টা রিভিউ লাইভ থাকার পর তাদের নেওয়া হয়েছে, কিন্তু এই টেকনিক্যাল কথাগুলো ইউজারকে আগ বাড়িয়ে বলার দরকার নেই। শুধু নির্দেশনা দিন।
"""

# ৪. এআই রেসপন্স জেনারেটর
async def get_ai_response(user_text, user_name):
    try:
        # আগের মেসেজ বা কন্টেক্সট ছাড়া শুধু বর্তমান মেসেজের উত্তর দেবে, কিন্তু প্রম্পট অনুযায়ী লিংক হোল্ড করে রাখবে
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User's Name: {user_name}. User says: {user_text}"},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.6, # টেম্পারেচার কমানো হয়েছে যাতে সে উল্টাপাল্টা কথা না বলে রুলস ফলো করে
            max_tokens=250
        )
        response = chat_completion.choices[0].message.content
        return html.escape(response)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return None

# ৫. গ্রুপ মেসেজ হ্যান্ডলার
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_chat.id != GROUP_ID:
        return

    user = update.message.from_user
    text = update.message.text or update.message.caption or ""

    # এডমিন চেক: এডমিন হলে বট চুপ থাকবে
    if user.id == ADMIN_ID:
        return
    
    # ইউজার যদি কোনো লিংক শেয়ার করে, তা ডিলিট হবে
    if re.search(URL_PATTERN, text):
        try:
            await update.message.delete()
            return 
        except: pass

    # এআই উত্তর জেনারেট করবে
    try:
        # টাইপিং একশন (মানুষের মতো ভাব আনার জন্য)
        await context.bot.send_chat_action(chat_id=GROUP_ID, action="typing")
        
        ai_reply = await get_ai_response(text, user.first_name)
        
        if ai_reply:
            # সরাসরি রিপ্লাই
            await update.message.reply_text(
                ai_reply,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logging.error(f"Reply Error: {e}")

# ৬. স্টার্ট কমান্ড (বট চেক করার জন্য)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("✅ বট এখন হিউম্যান মোডে আছে।")

if __name__ == '__main__':
    # Flask সার্ভার ব্যাকগ্রাউন্ডে রান হবে
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # টেলিগ্রাম বট সেটআপ
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    print("Bot is polling...")
    app.run_polling()
