import os
import sys
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)
from pymongo import MongoClient
from datetime import datetime
import certifi
from bson.objectid import ObjectId

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
MAIN_MENU, FORM_FILLING, EDIT_FIELD, CONFIRMATION = range(4)

# Environment Variables
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
MONGODB_URI = os.environ.get('MONGODB_URI')

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN environment variable সেট করা হয়নি!")
    sys.exit(1)

if not MONGODB_URI:
    logger.error("❌ MONGODB_URI environment variable সেট করা হয়নি!")
    sys.exit(1)

# MongoDB কানেকশন
try:
    logger.info("MongoDB এ কানেক্ট হচ্ছে...")
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
    db = client["stock_bot_db"]
    collection = db["stock_signals"]
    logger.info("✅ MongoDB কানেক্ট সফল!")
except Exception as e:
    logger.error(f"❌ MongoDB কানেক্ট ত্রুটি: {e}")
    sys.exit(1)

def calculate_position(symbol, total_capital, risk_percent, buy_price, sl_price, tp_price):
    """ট্রেডিং প্যারামিটার ক্যালকুলেট করে"""
    try:
        if buy_price <= sl_price:
            return {"error": "❌ বাই প্রাইস এসএল থেকে বেশি হতে হবে"}
        
        if tp_price <= buy_price:
            return {"error": "❌ টিপি প্রাইস বাই থেকে বেশি হতে হবে"}
        
        risk_per_trade = total_capital * risk_percent
        risk_per_share = buy_price - sl_price
        
        if risk_per_share <= 0:
            return {"error": "❌ ইনভ্যালিড রিস্ক পার শেয়ার ক্যালকুলেশন"}
        
        position_size = int(risk_per_trade / risk_per_share)
        position_size = max(1, position_size)
        
        exposure_bdt = position_size * buy_price
        actual_risk_bdt = position_size * risk_per_share
        diff = round(buy_price - sl_price, 4)
        rrr = round((tp_price - buy_price) / (buy_price - sl_price), 2)
        
        return {
            "symbol": symbol.upper(),
            "buy": round(buy_price, 2),
            "sl": round(sl_price, 2),
            "tp": round(tp_price, 2),
            "position_size": position_size,
            "exposure_bdt": round(exposure_bdt, 2),
            "actual_risk_bdt": round(actual_risk_bdt, 2),
            "diff": diff,
            "rrr": rrr,
            "total_capital": total_capital,
            "risk_percent": risk_percent * 100,
            "created_at": datetime.now()
        }
    except Exception as e:
        return {"error": f"❌ ক্যালকুলেশন এরর: {str(e)}"}

def format_signal_card(data, show_delete_button=False):
    """সিগন্যাল কার্ড ফরম্যাট তৈরি করে"""
    card = (
        f"╔══════════════════════╗\n"
        f"║     📊 {data['symbol']} \n"
        f"╠══════════════════════╣\n"
        f"║ 💰 ক্যাপিটাল: {data['total_capital']:,.0f} BDT\n"
        f"║ ⚠️ রিস্ক: {data['risk_percent']:.1f}%\n"
        f"╠══════════════════════╣\n"
        f"║ 📈 বাই: {data['buy']}\n"
        f"║ 📉 SL: {data['sl']}  |  🎯 TP: {data['tp']}\n"
        f"║ 📊 RRR: {data['rrr']}  |  📏 ডিফ: {data['diff']}\n"
        f"╠══════════════════════╣\n"
        f"║ 📦 পজিশন: {data['position_size']} shares\n"
        f"║ 💵 এক্সপোজার: {data['exposure_bdt']:,.0f} BDT\n"
        f"║ ⚡ রিস্ক: {data['actual_risk_bdt']:,.0f} BDT\n"
        f"╚══════════════════════╝"
    )
    
    if show_delete_button and '_id' in data:
        keyboard = [[InlineKeyboardButton("🗑️ ডিলিট", callback_data=f"delete_{data['_id']}")]]
        return card, InlineKeyboardMarkup(keyboard)
    return card, None

def format_form_display(user_data):
    """HTML ফর্মের মত ডিজাইনে ফর্ম তৈরি করে"""
    
    # ফিল্ডের মান গুলো নেওয়া
    symbol = user_data.get('symbol', '_________')
    
    # ক্যাপিটাল ফরম্যাট
    if user_data.get('capital'):
        capital = f"{user_data['capital']:,.0f} BDT"
    else:
        capital = '_________'
    
    # রিস্ক ফরম্যাট
    if user_data.get('risk'):
        risk = f"{user_data['risk']*100:.1f}%"
    else:
        risk = '_________'
    
    buy = user_data.get('buy', '_________')
    sl = user_data.get('sl', '_________')
    tp = user_data.get('tp', '_________')
    
    form = (
        "╔══════════════════════════════════════╗\n"
        "║     📝 স্টক সিগন্যাল ফর্ম           ║\n"
        "╠══════════════════════════════════════╣\n"
        f"║ 📌 সিম্বল      : {symbol:<15} ║\n"
        f"║ 💰 ক্যাপিটাল   : {capital:<15} ║\n"
        f"║ ⚠️ রিস্ক       : {risk:<15} ║\n"
        f"║ 📈 বাই         : {buy:<15} ║\n"
        f"║ 📉 এসএল        : {sl:<15} ║\n"
        f"║ 🎯 টিপি        : {tp:<15} ║\n"
        "╠══════════════════════════════════════╣\n"
        "║ নিচের বাটন ব্যবহার করে ফর্ম পূরণ করুন ║\n"
        "╚══════════════════════════════════════╝"
    )
    return form

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📝 নতুন সিগন্যাল", callback_data="new_signal")],
        [InlineKeyboardButton("📊 সংরক্ষিত সিগন্যাল", callback_data="view_signals")],
        [InlineKeyboardButton("❓ সাহায্য", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n"
        "আমি **Risk Reward BD Stock Bot**\n"
        "নিচের মেনু থেকে সিলেক্ট করুন:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return MAIN_MENU

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প মেনু দেখায়"""
    query = update.callback_query
    await query.answer()
    
    help_text = (
        "📚 **Risk Reward BD Stock Bot - সাহায্য**\n\n"
        
        "**কমান্ড সমূহ:**\n"
        "/start - বট শুরু করুন\n\n"
        
        "**ফর্ম ইনপুট সিস্টেম:**\n"
        "1️⃣ 'নতুন সিগন্যাল' বাটনে ক্লিক করুন\n"
        "2️⃣ প্রতিটি ফিল্ডের জন্য বাটন থাকবে\n"
        "3️⃣ বাটন ক্লিক করে মান বসান\n"
        "4️⃣ সব ফিল্ড পূরণ হলে Submit বাটনে ক্লিক করুন\n\n"
        
        "**ফিল্ড সমূহ:**\n"
        "• 📌 সিম্বল - স্টক সিম্বল (যেমন: aaa)\n"
        "• 💰 ক্যাপিটাল - মোট ট্রেডিং ক্যাপিটাল (BDT)\n"
        "• ⚠️ রিস্ক - প্রতি ট্রেডে রিস্কের শতাংশ (যেমন: 0.01)\n"
        "• 📈 বাই - ক্রয় মূল্য\n"
        "• 📉 এসএল - স্টপ লস\n"
        "• 🎯 টিপি - টার্গেট প্রাইস\n\n"
        
        "**আউটপুট ফরম্যাট:**\n"
        "📊 সিম্বল\n"
        "📉 SL | 🎯 TP (পাশাপাশি)\n"
        "📊 RRR | 📏 ডিফ (পাশাপাশি)"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]]
    await query.edit_message_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মেইন ফর্ম দেখায়"""
    query = update.callback_query
    await query.answer()
    
    # ফর্ম বাটন তৈরি
    keyboard = [
        [InlineKeyboardButton("📌 সিম্বল সেট করুন", callback_data="set_symbol")],
        [InlineKeyboardButton("💰 ক্যাপিটাল সেট করুন", callback_data="set_capital")],
        [InlineKeyboardButton("⚠️ রিস্ক সেট করুন", callback_data="set_risk")],
        [InlineKeyboardButton("📈 বাই সেট করুন", callback_data="set_buy")],
        [InlineKeyboardButton("📉 এসএল সেট করুন", callback_data="set_sl")],
        [InlineKeyboardButton("🎯 টিপি সেট করুন", callback_data="set_tp")],
        [InlineKeyboardButton("✅ ফর্ম জমা দিন", callback_data="submit_form")],
        [InlineKeyboardButton("🗑️ ফর্ম ক্লিয়ার", callback_data="clear_form")],
        [InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # ফর্ম ডিসপ্লে
    form_display = format_form_display(context.user_data)
    
    await query.edit_message_text(
        f"{form_display}\n\n"
        "বাটন ক্লিক করে ফর্ম পূরণ করুন:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return FORM_FILLING

async def handle_form_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফর্মের ইনপুট হ্যান্ডল করে"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("set_", "")
    context.user_data['current_field'] = field
    
    field_names = {
        'symbol': '📌 সিম্বল',
        'capital': '💰 ক্যাপিটাল',
        'risk': '⚠️ রিস্ক',
        'buy': '📈 বাই',
        'sl': '📉 এসএল',
        'tp': '🎯 টিপি'
    }
    
    examples = {
        'symbol': 'aaa',
        'capital': '500000',
        'risk': '0.01 (1% এর জন্য)',
        'buy': '30',
        'sl': '29',
        'tp': '39'
    }
    
    await query.edit_message_text(
        f"✏️ {field_names[field]} লিখুন:\n\n"
        f"উদাহরণ: {examples[field]}\n\n"
        "মান লিখে পাঠান (/cancel দিয়ে ফর্মে ফিরতে পারেন)"
    )
    return EDIT_FIELD

async def save_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফিল্ডের মান সংরক্ষণ করে"""
    field = context.user_data.get('current_field')
    value = update.message.text.strip()
    
    try:
        # ভ্যালিডেশন
        if field == 'symbol':
            value = value.upper()
            if len(value) > 10:
                await update.message.reply_text("❌ সিম্বল ১০ অক্ষরের বেশি হতে পারবে না। আবার দিন:")
                return EDIT_FIELD
            context.user_data['symbol'] = value
        
        elif field == 'capital':
            capital = float(value.replace(',', ''))
            if capital <= 0:
                await update.message.reply_text("❌ ক্যাপিটাল পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_FIELD
            context.user_data['capital'] = capital
        
        elif field == 'risk':
            risk = float(value)
            if risk <= 0 or risk > 1:
                await update.message.reply_text("❌ রিস্ক ০ থেকে ১ এর মধ্যে হতে হবে। আবার দিন:")
                return EDIT_FIELD
            context.user_data['risk'] = risk
        
        elif field == 'buy':
            buy = float(value)
            if buy <= 0:
                await update.message.reply_text("❌ বাই প্রাইস পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_FIELD
            context.user_data['buy'] = buy
        
        elif field == 'sl':
            sl = float(value)
            if sl <= 0:
                await update.message.reply_text("❌ এসএল প্রাইস পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_FIELD
            if 'buy' in context.user_data and sl >= context.user_data['buy']:
                await update.message.reply_text("❌ এসএল বাই থেকে কম হতে হবে। আবার দিন:")
                return EDIT_FIELD
            context.user_data['sl'] = sl
        
        elif field == 'tp':
            tp = float(value)
            if tp <= 0:
                await update.message.reply_text("❌ টিপি প্রাইস পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_FIELD
            if 'buy' in context.user_data and tp <= context.user_data['buy']:
                await update.message.reply_text("❌ টিপি বাই থেকে বেশি হতে হবে। আবার দিন:")
                return EDIT_FIELD
            context.user_data['tp'] = tp
        
        # ফর্মে ফিরে যান
        keyboard = [
            [InlineKeyboardButton("📌 সিম্বল সেট করুন", callback_data="set_symbol")],
            [InlineKeyboardButton("💰 ক্যাপিটাল সেট করুন", callback_data="set_capital")],
            [InlineKeyboardButton("⚠️ রিস্ক সেট করুন", callback_data="set_risk")],
            [InlineKeyboardButton("📈 বাই সেট করুন", callback_data="set_buy")],
            [InlineKeyboardButton("📉 এসএল সেট করুন", callback_data="set_sl")],
            [InlineKeyboardButton("🎯 টিপি সেট করুন", callback_data="set_tp")],
            [InlineKeyboardButton("✅ ফর্ম জমা দিন", callback_data="submit_form")],
            [InlineKeyboardButton("🗑️ ফর্ম ক্লিয়ার", callback_data="clear_form")],
            [InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        form_display = format_form_display(context.user_data)
        
        await update.message.reply_text(
            f"✅ {field} সেট করা হয়েছে!\n\n"
            f"{form_display}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return FORM_FILLING
        
    except ValueError:
        await update.message.reply_text("❌ সঠিক মান দিন। আবার চেষ্টা করুন:")
        return EDIT_FIELD

async def submit_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফর্ম জমা দেয়"""
    query = update.callback_query
    await query.answer()
    
    # সব ফিল্ড চেক করা
    required_fields = ['symbol', 'capital', 'risk', 'buy', 'sl', 'tp']
    missing = []
    
    for field in required_fields:
        if field not in context.user_data:
            field_names = {
                'symbol': 'সিম্বল',
                'capital': 'ক্যাপিটাল',
                'risk': 'রিস্ক', 
                'buy': 'বাই',
                'sl': 'এসএল',
                'tp': 'টিপি'
            }
            missing.append(field_names[field])
    
    if missing:
        await query.edit_message_text(
            f"❌ নিচের ফিল্ডগুলো পূরণ হয়নি:\n{', '.join(missing)}\n\n"
            "বাটন ক্লিক করে ফিল্ডগুলো পূরণ করুন।"
        )
        return FORM_FILLING
    
    # ক্যালকুলেশন
    result = calculate_position(
        context.user_data['symbol'],
        context.user_data['capital'],
        context.user_data['risk'],
        context.user_data['buy'],
        context.user_data['sl'],
        context.user_data['tp']
    )
    
    if "error" in result:
        await query.edit_message_text(f"❌ {result['error']}")
        return FORM_FILLING
    
    # প্রিভিউ দেখান
    card_text, _ = format_signal_card(result, show_delete_button=False)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ সংরক্ষণ করুন", callback_data="save_signal"),
            InlineKeyboardButton("📝 এডিট করুন", callback_data="back_to_form")
        ],
        [InlineKeyboardButton("❌ বাতিল", callback_data="cancel_form")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['preview_result'] = result
    
    await query.edit_message_text(
        f"{card_text}\n\n"
        "✅ সব ফিল্ড পূরণ হয়েছে। সংরক্ষণ করতে চান?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CONFIRMATION

async def save_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সিগন্যাল সংরক্ষণ করে"""
    query = update.callback_query
    await query.answer()
    
    result = context.user_data['preview_result']
    
    # MongoDB-তে সংরক্ষণ
    result['user_id'] = query.from_user.id
    result['username'] = query.from_user.username or query.from_user.first_name
    
    insert_result = collection.insert_one(result)
    result['_id'] = insert_result.inserted_id
    
    # ফাইনাল কার্ড
    card_text, keyboard = format_signal_card(result, show_delete_button=True)
    
    await query.edit_message_text(
        f"{card_text}\n\n✅ সিগন্যাল সংরক্ষণ করা হয়েছে!",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def clear_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফর্ম ক্লিয়ার করে"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    keyboard = [
        [InlineKeyboardButton("📌 সিম্বল সেট করুন", callback_data="set_symbol")],
        [InlineKeyboardButton("💰 ক্যাপিটাল সেট করুন", callback_data="set_capital")],
        [InlineKeyboardButton("⚠️ রিস্ক সেট করুন", callback_data="set_risk")],
        [InlineKeyboardButton("📈 বাই সেট করুন", callback_data="set_buy")],
        [InlineKeyboardButton("📉 এসএল সেট করুন", callback_data="set_sl")],
        [InlineKeyboardButton("🎯 টিপি সেট করুন", callback_data="set_tp")],
        [InlineKeyboardButton("✅ ফর্ম জমা দিন", callback_data="submit_form")],
        [InlineKeyboardButton("🗑️ ফর্ম ক্লিয়ার", callback_data="clear_form")],
        [InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    form_display = format_form_display({})
    
    await query.edit_message_text(
        f"{form_display}\n\n"
        "🔄 ফর্ম ক্লিয়ার করা হয়েছে। নতুন করে পূরণ করুন:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return FORM_FILLING

async def view_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সংরক্ষিত সিগন্যাল দেখায়"""
    query = update.callback_query
    await query.answer()
    
    signals = list(collection.find({"user_id": query.from_user.id}))
    
    if not signals:
        keyboard = [[InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "📭 আপনার কোনো সিগন্যাল নেই।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU
    
    # RRR অনুযায়ী সাজানো (উচ্চ থেকে নিম্ন) এবং তারপর diff (নিম্ন থেকে উচ্চ)
    sorted_signals = sorted(signals, key=lambda x: (-x['rrr'], x['diff']))
    
    await query.edit_message_text(
        f"📊 **আপনার {len(sorted_signals)}টি সিগন্যাল (RRR বেশি → কম, ডিফ কম → বেশি):**",
        parse_mode='Markdown'
    )
    
    for signal in sorted_signals:
        card_text, keyboard = format_signal_card(signal, show_delete_button=True)
        await query.message.reply_text(card_text, reply_markup=keyboard, parse_mode='Markdown')
        await asyncio.sleep(0.5)
    
    keyboard = [[InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]]
    await query.message.reply_text(
        "মেনুতে ফিরতে বাটন ক্লিক করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মেইন মেনুতে ফিরে যায়"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 নতুন সিগন্যাল", callback_data="new_signal")],
        [InlineKeyboardButton("📊 সংরক্ষিত সিগন্যাল", callback_data="view_signals")],
        [InlineKeyboardButton("❓ সাহায্য", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📌 **মেইন মেনু**\n\n"
        "আপনি কি করতে চান?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return MAIN_MENU

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ডিলিট বাটনের কলব্যাক হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "delete_all":
            result = collection.delete_many({"user_id": query.from_user.id})
            await query.edit_message_text(f"✅ {result.deleted_count}টি সিগন্যাল ডিলিট করা হয়েছে।")
            
        elif query.data.startswith("delete_"):
            signal_id = query.data.replace("delete_", "")
            result = collection.delete_one({"_id": ObjectId(signal_id), "user_id": query.from_user.id})
            
            if result.deleted_count > 0:
                await query.edit_message_text("✅ সিগন্যালটি ডিলিট করা হয়েছে।")
            else:
                await query.edit_message_text("❌ সিগন্যালটি পাওয়া যায়নি।")
                
    except Exception as e:
        await query.edit_message_text(f"❌ একটি ত্রুটি হয়েছে: {str(e)}")
        logger.error(f"Error in button_callback: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কনভারসেশন বাতিল"""
    await update.message.reply_text(
        "🚫 অপারেশন বাতিল করা হয়েছে।\n"
        "/start দিয়ে আবার শুরু করতে পারেন।"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def run_bot():
    """বট চালানোর async ফাংশন"""
    try:
        logger.info("🤖 Risk Reward BD Stock Bot চালু হচ্ছে...")
        
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # কনভারসেশন হ্যান্ডলার
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(show_form, pattern="^new_signal$"),
                    CallbackQueryHandler(view_signals, pattern="^view_signals$"),
                    CallbackQueryHandler(help_menu, pattern="^help$"),
                    CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"),
                ],
                FORM_FILLING: [
                    CallbackQueryHandler(handle_form_input, pattern="^set_"),
                    CallbackQueryHandler(submit_form, pattern="^submit_form$"),
                    CallbackQueryHandler(clear_form, pattern="^clear_form$"),
                    CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"),
                ],
                EDIT_FIELD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_field_value),
                ],
                CONFIRMATION: [
                    CallbackQueryHandler(save_signal, pattern="^save_signal$"),
                    CallbackQueryHandler(show_form, pattern="^back_to_form$"),
                    CallbackQueryHandler(back_to_menu, pattern="^cancel_form$"),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        app.add_handler(conv_handler)
        app.add_handler(CallbackQueryHandler(button_callback, pattern="^(delete_all|delete_.*)$"))
        
        logger.info("✅ বট চালু হয়েছে")
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # বট চলতে থাকবে
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 বট বন্ধ হচ্ছে...")
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            
    except Exception as e:
        logger.error(f"❌ বট চালু ত্রুটি: {e}", exc_info=True)
        raise

def main():
    """মেইন ফাংশন"""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("🛑 বট বন্ধ হচ্ছে...")
    except Exception as e:
        logger.error(f"❌ মেইন ত্রুটি: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
