import os
import json
import base64
import hmac
import hashlib
import struct
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import telebot
import firebase_admin

from firebase_admin import credentials, firestore
from firebase_admin.firestore import FieldFilter
from telebot.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# =====================================
# CONFIGURATION
# =====================================

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6114927842
FIREBASE_KEY = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not TOKEN or not FIREBASE_KEY:
    raise RuntimeError("Missing bot secrets")

if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(FIREBASE_KEY))
    firebase_admin.initialize_app(cred)

db = firestore.client()
bot = telebot.TeleBot(TOKEN)

states = {}

BKASH_NUMBER = "01786142570"
NAGAD_NUMBER = "01644053747"
BINANCE_UID = "987753103"

# =====================================
# DAILY PASSWORD & 2FA / TOTP GENERATOR
# =====================================

def get_daily_password(prefix="redwan"):
    dhaka_now = datetime.now(ZoneInfo("Asia/Dhaka"))
    return f"{prefix}{dhaka_now.day}"


def generate_totp_code(secret_key, interval=30, digits=6):
    cleaned = "".join(secret_key.strip().split()).upper()
    if "SECRET=" in cleaned:
        cleaned = cleaned.split("SECRET=", 1)[1].split("&", 1)[0]
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    key_bytes = base64.b32decode(cleaned + padding, casefold=True)
    counter = int(time.time()) // interval
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    ) % (10 ** digits)
    return str(code_int).zfill(digits)


# =====================================
# USER SYSTEM
# =====================================

def is_admin(uid):
    return uid == OWNER_ID


def get_user(user):
    uid = str(user.id)
    ref = db.collection("users").document(uid)

    if not ref.get().exists:
        ref.set({
            "user_id": uid,
            "username": user.username or "",
            "balance": 0,
            "created_at": firestore.SERVER_TIMESTAMP
        })

    return ref


def cancel_state(chat_id):
    states.pop(chat_id, None)


def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🛍️ Shop", "💰 Balance")
    kb.row("💳 Deposit", "🎁 Gift Code")
    kb.row("📦 Orders", "📞 Support")
    kb.row("💼 Tasks", "🎙️ Podcasts")
    return kb


def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👑 Admin Dashboard")
    kb.row("💰 Manage Balance", "💳 Deposits")
    kb.row("🎁 Gift Codes", "👥 Users")
    kb.row("📢 Broadcast", "🎙️ Manage Podcasts")
    kb.row("📋 Service Orders")
    kb.row("🏠 Main Menu")
    return kb


# =====================================
# START
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    try:
        cancel_state(message.chat.id)
        get_user(message.from_user)

        kb = admin_keyboard() if is_admin(
            message.from_user.id
        ) else main_keyboard()

        bot.send_message(
            message.chat.id,
            "🚀 Welcome to NEXORA Xe!\n\n"
            "💎 Your Digital Shopping Platform\n\n"
            "✨ Choose an option below:",
            reply_markup=kb
        )
    except Exception as e:
        print("Start error:", e)


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access Denied!")
        return

    cancel_state(message.chat.id)
    bot.send_message(
        message.chat.id,
        "👑 NEXORA Xe ADMIN PANEL",
        reply_markup=admin_keyboard()
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    cancel_state(message.chat.id)

    kb = admin_keyboard() if is_admin(
        message.from_user.id
    ) else main_keyboard()

    bot.send_message(
        message.chat.id,
        "❌ Operation cancelled.",
        reply_markup=kb
    )


# =====================================
# DASHBOARD
# =====================================

def show_dashboard(chat_id):
    users = list(db.collection("users").stream())

    total_balance = sum(
        float((u.to_dict() or {}).get("balance", 0) or 0)
        for u in users
    )

    pending = list(
        db.collection("deposits")
        .where(filter=FieldFilter("status", "==", "pending"))
        .stream()
    )

    bot.send_message(
        chat_id,
        "👑 NEXORA Xe DASHBOARD\n\n"
        f"👥 Total Users: {len(users)}\n"
        f"💰 Total Balance: {total_balance:.2f} BDT\n"
        f"💳 Pending Deposits: {len(pending)}",
        reply_markup=admin_keyboard()
    )


# =====================================
# BALANCE
# =====================================

def update_balance(uid, amount, action):
    ref = db.collection("users").document(str(uid))
    doc = ref.get()

    if not doc.exists:
        return False, "User not found."

    current = float(doc.to_dict().get("balance", 0) or 0)

    if action == "remove" and current < amount:
        return False, "Insufficient balance."

    new_balance = (
        current + amount if action == "add"
        else current - amount
    )

    ref.update({"balance": new_balance})
    return True, new_balance


# =====================================
# GIFT CODE
# =====================================

def redeem_gift(uid, code):
    code_ref = db.collection("gift_codes").document(code)
    user_ref = db.collection("users").document(str(uid))

    transaction = db.transaction()

    @firestore.transactional
    def redeem(transaction):
        code_doc = code_ref.get(transaction=transaction)

        if not code_doc.exists:
            return "invalid"

        data = code_doc.to_dict()

        if not data.get("active", True):
            return "inactive"

        if str(uid) in data.get("used_by", []):
            return "used"

        amount = float(data.get("amount", 0))

        if amount <= 0:
            return "invalid"

        user_doc = user_ref.get(transaction=transaction)

        if not user_doc.exists:
            return "user_missing"

        transaction.update(
            code_ref,
            {"used_by": firestore.ArrayUnion([str(uid)])}
        )

        transaction.update(
            user_ref,
            {"balance": firestore.Increment(amount)}
        )

        return amount

    return redeem(transaction)


# =====================================
# SERVICES
# =====================================

SERVICES = {
    "🌐 Facebook Sell": "Facebook Sell",
    "✉️ Gmail Sell": "Gmail Sell",
    "🌸 Instagram Sell": "Instagram Sell"
}


def get_gmail_sell_instructions():
    daily_pass = get_daily_password("redwan")
    return (
        "✉️ GMAIL SELL DETAILS\n\n"
        "First name: Karole\n"
        "Last name: ✖️\n"
        "Email: igifuluh837@gmail.com\n"
        f"Password: {daily_pass}\n"
        "Year of birth: 2000\n\n"
        "📲 Send the QR code or 2FA key of the authenticator:"
    )


def get_instagram_sell_instructions():
    daily_pass = get_daily_password("redwan")
    return (
        "🌸 INSTAGRAM SELL DETAILS\n\n"
        "Username: karole_ig837\n"
        f"Password: {daily_pass}\n\n"
        "📲 Send the QR code or 2FA key of the authenticator:"
    )


def show_tasks(chat_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🌐 Facebook Sell")
    kb.row("✉️ Gmail Sell")
    kb.row("🌸 Instagram Sell")
    kb.row("🏠 Main Menu")

    bot.send_message(
        chat_id,
        "💼 NEXORA Xe SERVICES\n\n✨ Select Your Service:",
        reply_markup=kb
    )


def show_service_orders(chat_id):
    orders = list(
        db.collection("service_orders")
        .order_by(
            "created_at",
            direction=firestore.Query.DESCENDING
        )
        .limit(20)
        .stream()
    )

    if not orders:
        bot.send_message(chat_id, "📭 No Service Orders.")
        return

    for doc in orders:
        d = doc.to_dict()

        bot.send_message(
            chat_id,
            f"📋 SERVICE ORDER\n\n"
            f"🆔 Order ID: {doc.id}\n"
            f"👤 User: {d.get('user_id')}\n"
            f"💼 Service: {d.get('service')}\n"
            f"🌐 Link: {d.get('page_link')}\n"
            f"📧 Email: {d.get('email')}\n"
            f"📝 Details: {d.get('details')}\n"
            f"📌 Status: {d.get('status')}"
        )


# =====================================
# PODCAST SYSTEM
# =====================================

def show_podcasts(chat_id):
    podcasts = list(
        db.collection("podcasts")
        .order_by(
            "created_at",
            direction=firestore.Query.DESCENDING
        )
        .limit(30)
        .stream()
    )

    if not podcasts:
        bot.send_message(chat_id, "🎙️ No Podcasts Available.")
        return

    for doc in podcasts:
        d = doc.to_dict()

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton(
                "▶️ Play / Watch",
                callback_data=f"podcast:view:{doc.id}"
            )
        )

        bot.send_message(
            chat_id,
            f"🎙️ {d.get('title')}\n"
            f"🏷️ Category: {d.get('category')}\n"
            f"📀 Type: {d.get('media_type')}",
            reply_markup=kb
        )


def show_admin_podcasts(chat_id):
    podcasts = list(
        db.collection("podcasts").limit(30).stream()
    )

    if not podcasts:
        bot.send_message(chat_id, "📭 No Podcasts Found.")
        return

    for doc in podcasts:
        d = doc.to_dict()

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton(
                "🗑️ Delete",
                callback_data=f"podcast:delete:{doc.id}"
            )
        )

        bot.send_message(
            chat_id,
            f"🎙️ {d.get('title')}\n"
            f"🏷️ Category: {d.get('category')}",
            reply_markup=kb
        )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("podcast:")
)
def podcast_callback(call):
    try:
        _, action, podcast_id = call.data.split(":", 2)

        ref = db.collection("podcasts").document(podcast_id)
        doc = ref.get()

        if not doc.exists:
            bot.answer_callback_query(call.id, "Podcast not found.")
            return

        data = doc.to_dict()

        if action == "view":
            caption = (
                f"🎙️ {data['title']}\n"
                f"🏷️ {data['category']}"
            )

            if data["media_type"] == "audio":
                bot.send_audio(
                    call.message.chat.id,
                    data["file_id"],
                    caption=caption
                )
            elif data["media_type"] == "video":
                bot.send_video(
                    call.message.chat.id,
                    data["file_id"],
                    caption=caption
                )

            bot.answer_callback_query(call.id, "Enjoy!")

        elif action == "delete":
            if not is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "Access denied!")
                return

            ref.delete()

            bot.edit_message_text(
                "🗑️ Podcast Deleted Successfully.",
                call.message.chat.id,
                call.message.message_id
            )

            bot.answer_callback_query(call.id, "Deleted!")

    except Exception as e:
        print("Podcast error:", e)
        bot.answer_callback_query(call.id, "Error")


# =====================================
# RECEIVE PODCAST &
