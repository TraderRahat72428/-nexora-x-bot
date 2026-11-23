import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🛍️ Shop", "💰 Balance")
    kb.row("💳 Deposit", "🎁 Gift Code")
    kb.row("📦 Orders", "📞 Support")

    bot.send_message(
        message.chat.id,
        "🚀 Welcome to NEXORA Xe!\n\nChoose an option below:",
        reply_markup=kb
    )

@bot.message_handler(func=lambda m: True)
def menu(message):
    options = {
        "🛍️ Shop": "Our digital services are coming soon.",
        "💰 Balance": "Your balance: 0 BDT",
        "💳 Deposit": "Choose: bKash / Nagad / USDT",
        "🎁 Gift Code": "Send your gift code.",
        "📦 Orders": "You have no orders yet.",
        "📞 Support": "Contact Admin for support."
    }

    bot.reply_to(message, options.get(message.text, "Welcome to NEXORA Xe!"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

bot.infinity_polling()
