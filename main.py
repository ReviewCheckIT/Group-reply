import os
import logging
import threading
import re
import html
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# ১. Render এর জন্য Web Server
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Skyzone IT AI Bot (Pakiza) is Active!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# ২. কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) 
GROUP_ID = int(os.getenv("GROUP_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

URL_PATTERN = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/\S+'

client = Groq(api_key=GROQ_API_KEY)

user_first_seen = {}
admin_cache = {
    "ids": [],
    "last_updated": datetime.min
}

SYSTEM_PROMPT = """
আপনার নাম 'পাকিজা' (Pakiza)। আপনি Skyzone IT গ্রুপের একজন বিশ্বস্ত এবং প্রফেশনাল টিম মেম্বার। আপনি কোনো রোবট নন, আপনি একজন মানুষ হিসেবে কথা বলবেন।

আপনার কঠোর নিয়মাবলী (Strict Rules):
১. **প্রথমেই কোনো লিংক দেবেন না।** ইউজার যদি 'Hi', 'Hello', 'ভাই', 'আছেন?' ইত্যাদি বলে, তবে আপনি শুধু কুশল বিনিময় করবেন। যেমন: "জি ভাইয়া/আপু, বলুন কিভাবে সাহায্য করতে পারি?" অথবা "পাকিজা! আমাদের গ্রুপে স্বাগতম।"
২. যতক্ষণ না ইউজার কাজের ব্যাপারে বিস্তারিত জানতে চাইছে বা বলছে "কাজটা কী?", ততক্ষণ ভিডিও লিংক বা বটের লিংক দেবেন না।
৩. কথা বলার ধরন হবে খুবই স্বাভাবিক এবং আন্তরিক। রোবটের মতো বড় বড় মেসেজ দেবেন না। ছোট ছোট মেসেজে রিপ্লাই দিন।
৪. **লিংক দেওয়ার সময়:** যখন ইউজার কাজের আগ্রহ দেখাবে, তখন বলুন: "কাজটা শুরু করার জন্য আপনাকে প্রথমে এই ভিডিওটি দেখে নিতে হবে: https://youtu.be/Yh1No2eDBuU?si=wJvjBMrEjakBOEgb"
৫. ভিডিও দেখার পর যখন তারা পরবর্তী ধাপ চাইবে, তখন ইন্টারভিউ বটের লিংক দেবেন: https://t.me/SkyzoneIT_bot?start=welcome
৬. সাধারণ অবস্থায় এডমিনরা (Admin) মেসেজ দিলে আপনি চুপ থাকবেন। কিন্তু এডমিন যদি সুনির্দিষ্টভাবে আপনাকে নাম ধরে ডাকে (যেমন: 'Pakiza', 'পাকিজা'), তখন তাদের নির্দেশ পালন করবেন।
৭. মনে রাখবেন: আমরা ফেসবুকে পোস্ট করে লোক আনি, তারা রিভিউ দিয়ে টেস্ট পাশ করে এখানে এসেছে। তাই তাদের সাথে ভালো ব্যবহার করুন।

গোপন নির্দেশনা: আপনি জানেন যে ২৪ ঘণ্টা রিভিউ লাইভ থাকার পর তাদের নেওয়া হয়েছে, কিন্তু এই টেকনিক্যাল কথাগুলো ইউজারকে আগ বাড়িয়ে বলার দরকার নেই। শুধু নির্দেশনা দিন।
"""

# এরর হ্যান্ডলার (নতুন যুক্ত করা হয়েছে)
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)

async def get_ai_response(user_text, user_name, specific_instruction=None):
    try:
        system_content = SYSTEM_PROMPT
        if specific_instruction:
            system_content += f"\n\n[ADMIN INSTRUCTION: {specific_instruction}]"

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_content},
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

async def get_group_admins(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    global admin_cache
    now = datetime.now()
    
    if (now - admin_cache["last_updated"]).total_seconds() > 600 or not admin_cache["ids"]:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_ids = [admin.user.id for admin in admins]
            admin_cache["ids"] = admin_ids
            admin_cache["last_updated"] = now
            logging.info(f"Admin list updated: {len(admin_ids)} admins found.")
        except Exception as e:
            logging.error(f"Failed to get admins: {e}")
            return admin_cache["ids"]
            
    return admin_cache["ids"]

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_chat.id != GROUP_ID:
        return

    user = update.message.from_user
    text = update.message.text or update.message.caption or ""
    msg_date = datetime.now()

    current_admins = await get_group_admins(context, GROUP_ID)
    is_admin = user.id in current_admins or user.id == ADMIN_ID

    if is_admin:
        lower_text = text.lower()
        if "pakiza" in lower_text or "পাকিজা" in text:
            if any(w in lower_text for w in ['online', 'active', 'acho', 'aso', 'live', 'lines']):
                await update.message.reply_text("জি এডমিন, আমি অ্যাক্টিভ আছি। বলুন কিভাবে সাহায্য করতে পারি?")
                return

            if update.message.reply_to_message:
                target_user = update.message.reply_to_message.from_user
                original_user_text = update.message.reply_to_message.text or "Need Help"
                
                ai_reply = await get_ai_response(
                    original_user_text, 
                    target_user.first_name, 
                    specific_instruction="Admin has asked you to help this user based on their message. Be helpful and polite."
                )
                
                if ai_reply:
                    await update.message.reply_to_message.reply_text(
                        ai_reply,
                        parse_mode=ParseMode.HTML
                    )
                return
        return

    if re.search(URL_PATTERN, text):
        try:
            await update.message.delete()
            return 
        except: pass

    if update.message.reply_to_message:
        replied_user_id = update.message.reply_to_message.from_user.id
        if replied_user_id in current_admins or replied_user_id == ADMIN_ID:
            return

    if user.id not in user_first_seen:
        user_first_seen[user.id] = msg_date
    
    first_seen_time = user_first_seen[user.id]
    days_passed = (msg_date - first_seen_time).days

    if days_passed >= 7:
        logging.info(f"User {user.first_name} is old ({days_passed} days). Ignoring.")
        return

    try:
        await context.bot.send_chat_action(chat_id=GROUP_ID, action="typing")
        ai_reply = await get_ai_response(text, user.first_name)
        if ai_reply:
            await update.message.reply_text(ai_reply, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Reply Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("✅ পাকিজা (Pakiza) এখন অ্যাক্টিভ! এডমিন কন্ট্রোল যুক্ত করা হয়েছে।")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # এখানে হ্যান্ডলারগুলো অ্যাড করা হয়েছে
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & (~filters.COMMAND), handle_group_messages))
    
    # এরর হ্যান্ডলার রেজিস্ট্রেশন
    app.add_error_handler(error_handler)
    
    print("Pakiza Bot is polling with ERROR HANDLER...")
    app.run_polling()
