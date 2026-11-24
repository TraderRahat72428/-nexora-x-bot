import os
import json
import telebot
import firebase_admin

from firebase_admin import credentials, firestore
from telebot.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# CONFIGURATION
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


# USER SYSTEM

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


# KEYBOARDS

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


def cancel_state(chat_id):
    states.pop(chat_id, None)


# START COMMAND

@bot.message_handler(commands=["start"])
def start(message):
    try:
        cancel_state(message.chat.id)
        get_user(message.from_user)

        bot.send_message(
            message.chat.id,
            "🚀 Welcome to NEXORA Xe!\n\n"
            "💎 Your Digital Shopping Platform\n\n"
            "Choose an option below:",
            reply_markup=main_keyboard()
        )

    except Exception as e:
        print("Start error:", e)
        bot.reply_to(message, "Please try again later.")


# ADMIN COMMAND

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access Denied!")
        return

    cancel_state(message.chat.id)

    bot.send_message(
        message.chat.id,
        "👑 NEXORA Xe ADMIN PANEL\n\n"
        "Welcome, Owner!",
        reply_markup=admin_keyboard()
    )


# CANCEL COMMAND

@bot.message_handler(commands=["cancel"])
def cancel(message):
    cancel_state(message.chat.id)

    kb = admin_keyboard() if is_admin(message.from_user.id) else main_keyboard()

    bot.send_message(
        message.chat.id,
        "❌ Operation cancelled.",
        reply_markup=kb
    )


# DASHBOARD

def show_dashboard(chat_id):
    users = list(db.collection("users").stream())

    total_balance = sum(
        float((u.to_dict() or {}).get("balance", 0) or 0)
        for u in users
    )

    pending = list(
        db.collection("deposits")
        .where("status", "==", "pending")
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


# BALANCE MANAGEMENT

def update_balance(uid, amount, action):
    ref = db.collection("users").document(str(uid))
    doc = ref.get()

    if not doc.exists:
        return False, "User not found."

    current = float(doc.to_dict().get("balance", 0) or 0)

    if action == "remove" and current < amount:
        return False, "Insufficient balance."

    new_balance = current + amount if action == "add" else current - amount

    ref.update({"balance": new_balance})

    return True, new_balance


# GIFT CODE REDEMPTION

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

        if not user_ref.get(transaction=transaction).exists:
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

# TASKS SYSTEM

SERVICES = {
    "🌐 Facebook Marketing Service": "Facebook Marketing Service",
    "✉️ Gmail Setup Service": "Gmail Setup Service",
    "🌸 Instagram Marketing Service": "Instagram Marketing Service"
}


def show_tasks(chat_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🌐 Facebook Marketing Service")
    kb.row("✉️ Gmail Setup Service")
    kb.row("🌸 Instagram Marketing Service")
    kb.row("🔙 Main Menu")

    bot.send_message(
        chat_id,
        "💼 NEXORA Xe SERVICES\n\n"
        "✨ Select Your Service:",
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


# PODCAST SYSTEM

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
            f"🏷️ {d.get('category')}",
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
            else:
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


# RECEIVE PODCAST MEDIA

@bot.message_handler(content_types=["audio", "video"])
def receive_podcast(message):
    chat_id = message.chat.id
    state = states.get(chat_id)

    if not state or state.get("step") != "podcast_media":
        return

    if not is_admin(message.from_user.id):
        return

    try:
        if message.audio:
            media_type = "audio"
            file_id = message.audio.file_id
        elif message.video:
            media_type = "video"
            file_id = message.video.file_id
        else:
            bot.reply_to(message, "Send Audio or Video.")
            return

        db.collection("podcasts").add({
            "title": state["title"],
            "category": state["category"],
            "media_type": media_type,
            "file_id": file_id,
            "created_at": firestore.SERVER_TIMESTAMP,
            "created_by": str(message.from_user.id)
        })

        cancel_state(chat_id)

        bot.reply_to(
            message,
            "✅ Podcast Uploaded!\n\n"
            f"🎙️ Title: {state['title']}\n"
            f"🏷️ Category: {state['category']}\n"
            f"📀 Type: {media_type}",
            reply_markup=admin_keyboard()
        )

    except Exception as e:
        print("Upload error:", e)
        bot.reply_to(message, "❌ Upload failed.")
# DEPOSIT LIST

def show_deposits(chat_id):
    deposits = list(
        db.collection("deposits")
        .where("status", "==", "pending")
        .limit(20)
        .stream()
    )

    if not deposits:
        bot.send_message(chat_id, "✅ No pending deposits.")
        return

    for doc in deposits:
        d = doc.to_dict()

        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"dep:approve:{doc.id}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"dep:reject:{doc.id}"
            )
        )

        bot.send_message(
            chat_id,
            "💳 DEPOSIT REQUEST\n\n"
            f"🆔 Request: {doc.id}\n"
            f"👤 User: {d.get('user_id')}\n"
            f"💰 Amount: {d.get('amount')} BDT\n"
            f"💳 Method: {d.get('method')}\n"
            f"🧾 Transaction: {d.get('transaction_id')}",
            reply_markup=kb
        )


# DEPOSIT APPROVE / REJECT

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("dep:")
)
def process_deposit(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Access denied")
        return

    try:
        _, action, deposit_id = call.data.split(":", 2)

        if action not in ("approve", "reject"):
            bot.answer_callback_query(call.id, "Invalid action")
            return

        dep_ref = db.collection("deposits").document(deposit_id)
        transaction = db.transaction()

        @firestore.transactional
        def process(transaction):
            dep_doc = dep_ref.get(transaction=transaction)

            if not dep_doc.exists:
                return "missing", None

            data = dep_doc.to_dict()

            if data.get("status") != "pending":
                return "processed", None

            if action == "approve":
                user_ref = db.collection("users").document(
                    str(data["user_id"])
                )

                if not user_ref.get(transaction=transaction).exists:
                    return "user_missing", None

                transaction.update(
                    user_ref,
                    {"balance": firestore.Increment(float(data["amount"]))}
                )

            status = "approved" if action == "approve" else "rejected"

            transaction.update(
                dep_ref,
                {
                    "status": status,
                    "processed_at": firestore.SERVER_TIMESTAMP
                }
            )

            return status, data

        result, data = process(transaction)

        if result == "approved":
            bot.send_message(
                int(data["user_id"]),
                f"✅ Deposit Approved!\n"
                f"💰 Added: {data['amount']} BDT"
            )

        elif result == "rejected":
            bot.send_message(
                int(data["user_id"]),
                "❌ Your deposit request was rejected."
            )

        bot.answer_callback_query(call.id, result.capitalize())

        if result in ("approved", "rejected"):
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )

    except Exception as e:
        print("Deposit error:", e)
        bot.answer_callback_query(call.id, "Processing error")


# MAIN MESSAGE HANDLER

@bot.message_handler(func=lambda m: True)
def menu(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    text = (message.text or "").strip()

    try:
        get_user(message.from_user)

           # CANCEL ACTIVE OPERATION
        if text == "🔙 Main Menu":
            cancel_state(chat_id)

            if is_admin(uid):
                bot.send_message(
                    chat_id,
                    "👑 Admin Main Menu",
                    reply_markup=admin_keyboard()
                )
            else:
                bot.send_message(
                    chat_id,
                    "🏠 Main Menu",
                    reply_markup=main_keyboard()
                )
            return

        state = states.get(chat_id)

        # CONVERSATION STATES

        if state:

            step = state["step"]
        # TASK ORDER STATES

            if step == "task_link":
                if not text.startswith(("https://", "http://")):
                    bot.reply_to(message, "🌐 Send a valid link.")
                    return

                states[chat_id]["page_link"] = text
                states[chat_id]["step"] = "task_email"

                bot.reply_to(
                    message,
                    "📧 Send your Contact Email:"
                )
                return

            elif step == "task_email":
                import re

                if not re.match(
                    r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                    text
                ):
                    bot.reply_to(message, "❌ Invalid Email.")
                    return

                states[chat_id]["email"] = text
                states[chat_id]["step"] = "task_details"

                bot.reply_to(
                    message,
                    "📋 Send your Service Details:"
                )
                return

            elif step == "task_details":
                if len(text) < 3 or len(text) > 1000:
                    bot.reply_to(message, "Invalid details.")
                    return

                order = {
                    "user_id": str(uid),
                    "service": state["service"],
                    "page_link": state["page_link"],
                    "email": state["email"],
                    "details": text,
                    "status": "pending",
                    "created_at": firestore.SERVER_TIMESTAMP
                }

                ref = db.collection("service_orders").document()
                ref.set(order)

                cancel_state(chat_id)

                bot.reply_to(
                    message,
                    "✅ ORDER SUBMITTED!\n\n"
                    f"🆔 Order ID: {ref.id}\n"
                    f"💼 Service: {order['service']}\n"
                    "⏳ Waiting for Admin.",
                    reply_markup=main_keyboard()
                )

                bot.send_message(
                    OWNER_ID,
                    "📋 NEW SERVICE ORDER!\n\n"
                    f"🆔 ID: {ref.id}\n"
                    f"👤 User: {uid}\n"
                    f"💼 Service: {order['service']}\n"
                    f"🌐 Link: {order['page_link']}\n"
                    f"📧 Email: {order['email']}\n"
                    f"📝 Details: {order['details']}"
                )
                return

            # PODCAST UPLOAD STATES

            elif step == "podcast_title":
                if not text or len(text) > 100:
                    bot.reply_to(message, "Invalid title.")
                    return

                states[chat_id]["title"] = text
                states[chat_id]["step"] = "podcast_category"

                bot.reply_to(message, "🏷️ Send Podcast Category:")
                return

            elif step == "podcast_category":
                if not text or len(text) > 50:
                    bot.reply_to(message, "Invalid category.")
                    return

                states[chat_id]["category"] = text
                states[chat_id]["step"] = "podcast_media"

                bot.reply_to(
                    message,
                    "🎧 Send Podcast Audio or 🎬 Video:"
                )
                return

            elif step == "podcast_media":
                bot.reply_to(
                    message,
                    "⚠️ Please send Audio or Video."
                )
                return

            if step == "balance_user":
                if not text.isdigit():
                    bot.reply_to(message, "Send a valid User ID.")
                    return

                states[chat_id]["user_id"] = text
                states[chat_id]["step"] = "balance_amount"

                bot.reply_to(message, "💰 Send amount in BDT:")
                return

            elif step == "balance_amount":
                try:
                    amount = float(text)
                    if amount <= 0:
                        raise ValueError()
                except ValueError:
                    bot.reply_to(message, "Invalid amount.")
                    return

                ok, result = update_balance(
                    state["user_id"],
                    amount,
                    state["action"]
                )

                cancel_state(chat_id)

                if ok:
                    bot.reply_to(
                        message,
                        f"✅ Balance Updated!\n"
                        f"💰 New Balance: {result} BDT",
                        reply_markup=admin_keyboard()
                    )

                    try:
                        bot.send_message(
                            int(state["user_id"]),
                            f"💰 Your balance has been updated.\n"
                            f"New balance: {result} BDT"
                        )
                    except Exception:
                        pass
                else:
                    bot.reply_to(message, f"❌ {result}")

                return

            elif step == "gift_code":
                code = text.upper()

                if len(code) < 3 or len(code) > 40:
                    bot.reply_to(message, "Invalid code. Try again.")
                    return

                states[chat_id]["code"] = code
                states[chat_id]["step"] = "gift_amount"

                bot.reply_to(message, "🎁 Send gift code amount:")
                return

            elif step == "gift_amount":
                try:
                    amount = float(text)
                    if amount <= 0:
                        raise ValueError()
                except ValueError:
                    bot.reply_to(message, "Invalid amount.")
                    return

                code = state["code"]
                ref = db.collection("gift_codes").document(code)

                if ref.get().exists:
                    bot.reply_to(message, "❌ Code already exists.")
                else:
                    ref.set({
                        "code": code,
                        "amount": amount,
                        "used_by": [],
                        "active": True,
                        "created_at": firestore.SERVER_TIMESTAMP
                    })

                    bot.reply_to(
                        message,
                        f"✅ Gift Code Created!\n\n"
                        f"🎁 Code: {code}\n"
                        f"💰 Amount: {amount} BDT"
                    )

                cancel_state(chat_id)
                return

            elif step == "redeem":
                code = text.upper()

                result = redeem_gift(uid, code)
                cancel_state(chat_id)

                if result == "invalid":
                    bot.reply_to(message, "❌ Invalid gift code.")
                elif result == "inactive":
                    bot.reply_to(message, "❌ Gift code inactive.")
                elif result == "used":
                    bot.reply_to(message, "❌ You already used this code.")
                elif result == "user_missing":
                    bot.reply_to(message, "❌ User account not found.")
                else:
                    bot.reply_to(
                        message,
                        f"🎉 Gift Redeemed!\n"
                        f"💰 Added: {result} BDT"
                    )

                return

            elif step == "deposit_method":
                if text not in ["bKash", "Nagad", "USDT"]:
                    bot.reply_to(message, "Choose bKash, Nagad or USDT.")
                    return

                states[chat_id]["method"] = text
                states[chat_id]["step"] = "deposit_amount"

                bot.send_message(
    message.chat.id,
    "💰 Send deposit amount:\n\n"
    "💳 bKash Personal: 01644053747\n"
    "💳 Nagad Personal: 01644053747\n\n"
    "📌 Send your deposit amount below."
                )
                return

            elif step == "deposit_amount":
                try:
                    amount = float(text)
                    if amount <= 0:
                        raise ValueError()
                except ValueError:
                    bot.reply_to(message, "Invalid amount.")
                    return

                states[chat_id]["amount"] = amount
                states[chat_id]["step"] = "deposit_reference"

                bot.reply_to(
                    message,
                    "🧾 Send your transaction ID / payment reference:"
                )
                return

            elif step == "deposit_reference":
                if not text or len(text) > 150:
                    bot.reply_to(message, "Invalid reference.")
                    return

                ref = db.collection("deposits").document()

                ref.set({
                    "user_id": str(uid),
                    "amount": state["amount"],
                    "method": state["method"],
                    "transaction_id": text,
                    "status": "pending",
                    "created_at": firestore.SERVER_TIMESTAMP
                })

                cancel_state(chat_id)

                bot.reply_to(
                    message,
                    "✅ Deposit Request Submitted!\n"
                    "⏳ Waiting for Admin Approval.",
                    reply_markup=main_keyboard()
                )

                bot.send_message(
                    OWNER_ID,
                    f"💳 New Deposit Request!\n"
                    f"🆔 ID: {ref.id}\n"
                    f"👤 User: {uid}\n"
                    f"💰 Amount: {state['amount']} BDT\n"
                    f"💳 Method: {state['method']}"
                    f"🔑 TXID: {text}"
                )
                return

            elif step == "broadcast":
                cancel_state(chat_id)

                sent = 0

                for user_doc in db.collection("users").stream():
                    try:
                        bot.send_message(
                            int(user_doc.id),
                            "📢 NEXORA Xe Announcement\n\n" + text
                        )
                        sent += 1
                    except Exception:
                        pass

                bot.reply_to(
                    message,
                    f"✅ Broadcast Completed!\nSent: {sent}",
                    reply_markup=admin_keyboard()
                )
                return

            # ADMIN BUTTONS

    if is_admin(uid):

        if text == "👑 Admin Dashboard":
            show_dashboard(chat_id)
            return

        elif text == "💰 Manage Balance":
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.row("➕ Add Balance", "➖ Remove Balance")
            kb.row("🔙 Main Menu")
            bot.send_message(chat_id, "💰 Choose Balance Action:", reply_markup=kb)
            return

        elif text == "➕ Add Balance":
            states[chat_id] = {"step": "balance_user", "action": "add"}
            bot.send_message(chat_id, "Send User Telegram ID:")
            return

        elif text == "➖ Remove Balance":
            states[chat_id] = {"step": "balance_user", "action": "remove"}
            bot.send_message(chat_id, "Send User Telegram ID:")
            return

        elif text == "💳 Deposits":
            show_deposits(chat_id)
            return

        elif text == "🎁 Gift Codes":
            states[chat_id] = {"step": "gift_code"}
            bot.send_message(chat_id, "Send a new unique Gift Code:")
            return

        elif text == "👥 Users":
            users = list(db.collection("users").limit(200).stream())

            if not users:
                bot.send_message(chat_id, "No users found.")
                return

            for u in users:
                d = u.to_dict()
                bot.send_message(
                    chat_id,
                    f"👤 User ID: {u.id}\n"
                    f"💰 Balance: {d.get('balance', 0)} BDT"
                )
            return

        elif text == "📢 Broadcast":
            states[chat_id] = {"step": "broadcast"}
            bot.send_message(chat_id, "Send your announcement message:")
            return

        elif text == "🎙️ Manage Podcasts":
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.row("➕ Upload Podcast", "📚 Podcast List")
            kb.row("🔙 Main Menu")
            bot.send_message(
                chat_id,
                "🎙️ PODCAST MANAGEMENT",
                reply_markup=kb
            )
            return

        elif text == "➕ Upload Podcast":
            states[chat_id] = {"step": "podcast_title"}
            bot.send_message(chat_id, "📝 Send Podcast Title:")
            return

        elif text == "📚 Podcast List":
            show_admin_podcasts(chat_id)
            return

        elif text == "📋 Service Orders":
            show_service_orders(chat_id)
            return

        # USER BUTTONS

    if text == "💰 Balance":
        data = get_user(message.from_user).to_dict()
        bot.reply_to(
            message,
            f"💰 Your Balance: {data.get('balance', 0)} BDT"
        )
        return

    elif text == "🛍️ Shop":
        bot.send_message(chat_id, "🛍️ Shop Coming Soon!")
        return

    elif text == "💳 Deposit":
        states[chat_id] = {"step": "deposit_method"}
        bot.send_message(chat_id, "💳 Select Deposit Method:")
        return

    elif text == "🎁 Gift Code":
        states[chat_id] = {"step": "redeem"}
        bot.send_message(chat_id, "🎁 Send Your Gift Code:")
        return

    elif text == "📦 Orders":
        orders = list(
            db.collection("service_orders")
            .where("user_id", "==", str(uid))
            .limit(20).stream()
        )

        if not orders:
            bot.send_message(chat_id, "📦 No Orders Found.")
            return

        for order in orders:
            d = order.to_dict()
            bot.send_message(
                chat_id,
                f"📦 Service: {d.get('service')}\n"
                f"🆔 Order ID: {order.id}\n"
                f"📌 Status: {d.get('status')}"
            )
        return

    elif text == "📞 Support":
        bot.send_message(chat_id, "📞 Contact: @NexoraXeBot")
        return

    elif text == "💼 Tasks":
        show_tasks(chat_id)
        return

    elif text in SERVICES:
        states[chat_id] = {
            "step": "task_link",
            "service": SERVICES[text]
        }
        bot.send_message(chat_id, "🌐 Send your Page/Profile Link:")
        return

    elif text == "🎙️ Podcasts":
        show_podcasts(chat_id)
        return

    except Exception as e:
        print("Menu Error:", e)
        bot.reply_to(message, "⚠️ Something went wrong. Try again.")


print("🚀 NEXORA Xe Bot is running...")
bot.infinity_polling()
