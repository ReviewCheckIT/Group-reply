import os
import logging
import threading
import re
import html
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, ChatMember
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# ১. Render এর জন্য Web Server
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Skyzone IT AI Bot is Active (Human Mode with Admin & Time Logic)!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
# মেইন ওনারের আইডি (ব্যাকআপ হিসেবে)
ADMIN_ID = int(os.getenv("ADMIN_ID")) 
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# লিংক প্যাটার্ন
URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

client = Groq(api_key=GROQ_API_KEY)

# ইউজার ট্র্যাকিং মেমোরি (কে কখন জয়েন করেছে বা প্রথম মেসেজ দিয়েছে)
# Format: {user_id: first_seen_datetime}
user_first_seen = {}

# এডমিন ক্যাশ (বারবার এপিআই কল না করার জন্য)
admin_cache = {
    "ids": [],
    "last_updated": datetime.min
}

# ৩. সিস্টেম প্রম্পট (আগের মতোই)
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

# এআই রেসপন্স জেনারেটর
async def get_ai_response(user_text, user_name):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User's Name: {user_name}. User says: {user_text}"},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.6,
            max_tokens=250
        )
        response = chat_completion.choices[0].message.content
        return html.escape(response)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return None

# এডমিন লিস্ট আপডেট করার ফাংশন (প্রতি ১০ মিনিটে একবার আপডেট হবে)
async def get_group_admins(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    global admin_cache
    now = datetime.now()
    
    # যদি ক্যাশ ১০ মিনিটের বেশি পুরনো হয়, তবে নতুন করে এডমিন লিস্ট আনবে
    if (now - admin_cache["last_updated"]).total_seconds() > 600 or not admin_cache["ids"]:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_ids = [admin.user.id for admin in admins]
            admin_cache["ids"] = admin_ids
            admin_cache["last_updated"] = now
            logging.info(f"Admin list updated: {len(admin_ids)} admins found.")
        except Exception as e:
            logging.error(f"Failed to get admins: {e}")
            return admin_cache["ids"] # এরর হলে আগের লিস্টই রিটার্ন করবে
            
    return admin_cache["ids"]

# ৫. গ্রুপ মেসেজ হ্যান্ডলার (নতুন লজিক সহ)
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_chat.id != GROUP_ID:
        return

    user = update.message.from_user
    text = update.message.text or update.message.caption or ""
    msg_date = datetime.now()

    # ১. এডমিন চেক (Sender Admin কিনা)
    # ---------------------------------------------------------
    current_admins = await get_group_admins(context, GROUP_ID)
    
    # যদি মেসেজ সেন্ডার নিজেই এডমিন হয়, তাহলে চুপ থাকুন
    if user.id in current_admins or user.id == ADMIN_ID:
        return

    # ২. লিংক ডিলিট সেকশন
    # ---------------------------------------------------------
    if re.search(URL_PATTERN, text):
        try:
            await update.message.delete()
            return 
        except: pass

    # ৩. এডমিন ইন্টারঅ্যাকশন চেক (Reply to Admin)
    # ---------------------------------------------------------
    # যদি ইউজার কারো মেসেজের রিপ্লাই দেয় এবং সেই ব্যক্তিটি এডমিন হয়, তবে বট চুপ থাকবে
    if update.message.reply_to_message:
        replied_user_id = update.message.reply_to_message.from_user.id
        if replied_user_id in current_admins or replied_user_id == ADMIN_ID:
            logging.info(f"User {user.first_name} replied to an admin. Bot staying silent.")
            return

    # ৪. পুরাতন মেম্বার চেক (৭ দিনের লজিক)
    # ---------------------------------------------------------
    # যদি ইউজারকে আগে না দেখে থাকি, তবে আজকের সময় সেট করো
    if user.id not in user_first_seen:
        user_first_seen[user.id] = msg_date
    
    first_seen_time = user_first_seen[user.id]
    days_passed = (msg_date - first_seen_time).days

    # যদি ৭ দিনের বেশি হয়ে যায়, তাহলে রিপ্লাই দেবে না
    if days_passed >= 7:
        logging.info(f"User {user.first_name} is old ({days_passed} days). Ignoring.")
        return

    # ৫. এআই রেসপন্স (সব শর্ত পার হলে)
    # ---------------------------------------------------------
    try:
        await context.bot.send_chat_action(chat_id=GROUP_ID, action="typing")
        
        ai_reply = await get_ai_response(text, user.first_name)
        
        if ai_reply:
            await update.message.reply_text(
                ai_reply,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logging.error(f"Reply Error: {e}")

# ৬. স্টার্ট কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # স্টার্ট কমান্ড শুধুমাত্র প্রাইভেটে বা এডমিন চেক করার জন্য
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("✅ বট আপডেট হয়েছে (সকল এডমিন ইগনোর + ৭ দিনের পুরাতন মেম্বার ইগনোর মোড)।")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    print("Bot is polling with NEW rules...")
    app.run_polling()
