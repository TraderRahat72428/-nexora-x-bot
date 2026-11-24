
import os
import json
import telebot
import firebase_admin

from firebase_admin import credentials, firestore
from telebot.types import ReplyKeyboardMarkup

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6114927842
FIREBASE_KEY = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not FIREBASE_KEY:
    raise RuntimeError("FIREBASE_SERVICE_ACCOUNT is missing")

# Firebase connection
if not firebase_admin._apps:
    service_account = json.loads(FIREBASE_KEY)
    cred = credentials.Certificate(service_account)
    firebase_admin.initialize_app(cred)

db = firestore.client()
bot = telebot.TeleBot(TOKEN)


def get_user(user):
    user_id = str(user.id)
    ref = db.collection("users").document(user_id)
    doc = ref.get()

    if not doc.exists:
        ref.set({
            "user_id": user_id,
            "username": user.username or "",
            "balance": 0,
            "created_at": firestore.SERVER_TIMESTAMP
        })
def is_admin(user_id):
    return user_id == OWNER_ID
    return ref


@bot.message_handler(commands=['start'])
def start(message):
    try:
        get_user(message.from_user)

        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("🛍️ Shop", "💰 Balance")
        kb.row("💳 Deposit", "🎁 Gift Code")
        kb.row("📦 Orders", "📞 Support")

        bot.send_message(
            message.chat.id,
            "🚀 Welcome to NEXORA Xe!\n\nChoose an option below:",
            reply_markup=kb
        )
    except Exception as e:
        print("Firebase error:", e)
        bot.send_message(message.chat.id, "Please try again later.")


@bot.message_handler(func=lambda m: True)
def menu(message):
    try:
        ref = get_user(message.from_user)

        if message.text == "💰 Balance":
            data = ref.get().to_dict()
            balance = data.get("balance", 0)
            bot.reply_to(message, f"💰 Your balance: {balance} BDT")

        elif message.text == "🛍️ Shop":
            bot.reply_to(message, "Our digital services are coming soon.")

        elif message.text == "💳 Deposit":
            bot.reply_to(message, "Choose: bKash / Nagad / USDT")

        elif message.text == "🎁 Gift Code":
            bot.reply_to(message, "Send your gift code.")

        elif message.text == "📦 Orders":
            bot.reply_to(message, "You have no orders yet.")

        elif message.text == "📞 Support":
            bot.reply_to(message, "Contact Admin for support.")

        else:
            bot.reply_to(message, "Welcome to NEXORA Xe!")

    except Exception as e:
        print("Error:", e)
        bot.reply_to(message, "Something went wrong. Please try again.")


bot.infinity_polling()
