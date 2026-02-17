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
(FORM_START, SYMBOL, CAPITAL, RISK, BUY, SL, TP, CONFIRM, 
 EDIT_FIELD, EDIT_VALUE) = range(9)

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
        f"📊 **{data['symbol']}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 ক্যাপিটাল: {data['total_capital']:,.0f} BDT\n"
        f"⚠️ রিস্ক: {data['risk_percent']:.1f}%\n"
        f"━━━━━━━━━━━━━━\n"
        f"📈 বাই: {data['buy']}\n"
        f"📉 SL: {data['sl']}  |  🎯 TP: {data['tp']}\n"
        f"📊 RRR: {data['rrr']}  |  📏 ডিফ: {data['diff']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📦 পজিশন: {data['position_size']} shares\n"
        f"💵 এক্সপোজার: {data['exposure_bdt']:,.0f} BDT\n"
        f"⚡ রিস্ক: {data['actual_risk_bdt']:,.0f} BDT\n"
        f"━━━━━━━━━━━━━━"
    )
    
    if show_delete_button and '_id' in data:
        keyboard = [[InlineKeyboardButton("🗑️ ডিলিট", callback_data=f"delete_{data['_id']}")]]
        return card, InlineKeyboardMarkup(keyboard)
    return card, None

def format_form_preview(user_data):
    """ফর্ম প্রিভিউ দেখায়"""
    preview = (
        "📝 **আপনার তথ্য:**\n"
        "━━━━━━━━━━━━━━\n"
        f"📌 সিম্বল: {user_data.get('symbol', '❌ দেওয়া হয়নি')}\n"
        f"💰 ক্যাপিটাল: {user_data.get('capital', '❌ দেওয়া হয়নি'):,.0f if user_data.get('capital') else '❌ দেওয়া হয়নি'} BDT\n"
        f"⚠️ রিস্ক: {user_data.get('risk', '❌ দেওয়া হয়নি')*100:.1f}% if user_data.get('risk') else '❌ দেওয়া হয়নি'}\n"
        f"📈 বাই: {user_data.get('buy', '❌ দেওয়া হয়নি')}\n"
        f"📉 এসএল: {user_data.get('sl', '❌ দেওয়া হয়নি')}\n"
        f"🎯 টিপি: {user_data.get('tp', '❌ দেওয়া হয়নি')}\n"
        "━━━━━━━━━━━━━━"
    )
    return preview

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n"
        "আমি **Risk Reward BD Stock Bot**\n\n"
        "📌 **কমান্ড সমূহ:**\n"
        "/stock - ফর্ম আকারে নতুন সিগন্যাল যোগ করুন\n"
        "/ok - সংরক্ষিত সিগন্যাল দেখুন\n"
        "/clear - সব সিগন্যাল ডিলিট করুন\n"
        "/cancel - ফর্ম বাতিল করুন\n"
        "/help - সাহায্য দেখুন"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প কমান্ড"""
    help_text = (
        "📚 **Risk Reward BD Stock Bot - সাহায্য**\n\n"
        
        "**কমান্ড সমূহ:**\n"
        "/start - বট শুরু করুন\n"
        "/help - এই হেল্প মেসেজ দেখুন\n"
        "/stock - ফর্ম আকারে নতুন সিগন্যাল যোগ করুন\n"
        "/ok - সংরক্ষিত সিগন্যাল দেখুন\n"
        "/clear - সব সিগন্যাল ডিলিট করুন\n"
        "/cancel - ফর্ম বাতিল করুন\n\n"
        
        "**ফর্ম ইনপুট সিস্টেম:**\n"
        "1️⃣ /stock দিন - একটি ফর্ম দেখাবে\n"
        "2️⃣ প্রতিটি ফিল্ডের জন্য বাটন থাকবে\n"
        "3️⃣ বাটন ক্লিক করে মান বসান\n"
        "4️⃣ সব ফিল্ড পূরণ হলে Submit বাটন দেখাবে\n\n"
        
        "**ফিল্ড সমূহ:**\n"
        "• 📌 সিম্বল - স্টক সিম্বল (যেমন: aaa)\n"
        "• 💰 ক্যাপিটাল - মোট ট্রেডিং ক্যাপিটাল (BDT)\n"
        "• ⚠️ রিস্ক% - প্রতি ট্রেডে রিস্কের শতাংশ (যেমন: 0.01)\n"
        "• 📈 বাই - ক্রয় মূল্য\n"
        "• 📉 এসএল - স্টপ লস\n"
        "• 🎯 টিপি - টার্গেট প্রাইস\n\n"
        
        "**আউটপুট ফরম্যাট:**\n"
        "📊 সিম্বল\n"
        "📉 SL | 🎯 TP (পাশাপাশি)\n"
        "📊 RRR | 📏 ডিফ (পাশাপাশি)"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stock_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টক ফর্ম শুরু"""
    context.user_data.clear()
    
    keyboard = [
        [InlineKeyboardButton("📌 সিম্বল বসান", callback_data="edit_symbol")],
        [InlineKeyboardButton("💰 ক্যাপিটাল বসান", callback_data="edit_capital")],
        [InlineKeyboardButton("⚠️ রিস্ক বসান", callback_data="edit_risk")],
        [InlineKeyboardButton("📈 বাই বসান", callback_data="edit_buy")],
        [InlineKeyboardButton("📉 এসএল বসান", callback_data="edit_sl")],
        [InlineKeyboardButton("🎯 টিপি বসান", callback_data="edit_tp")],
        [InlineKeyboardButton("✅ সাবমিট", callback_data="submit_form")],
        [InlineKeyboardButton("❌ ফর্ম বাতিল", callback_data="cancel_form")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📝 **নতুন স্টক সিগন্যাল ফর্ম**\n\n"
        "নিচের বাটনগুলো ক্লিক করে প্রতিটি ফিল্ড পূরণ করুন:\n\n"
        f"{format_form_preview(context.user_data)}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return FORM_START

async def form_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফর্মের বাটন হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_form":
        await query.edit_message_text("❌ ফর্ম বাতিল করা হয়েছে।")
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == "submit_form":
        # চেক করা সব ফিল্ড পূরণ হয়েছে কিনা
        required_fields = ['symbol', 'capital', 'risk', 'buy', 'sl', 'tp']
        missing_fields = []
        
        for field in required_fields:
            if field not in context.user_data:
                field_names = {
                    'symbol': '📌 সিম্বল',
                    'capital': '💰 ক্যাপিটাল', 
                    'risk': '⚠️ রিস্ক',
                    'buy': '📈 বাই',
                    'sl': '📉 এসএল',
                    'tp': '🎯 টিপি'
                }
                missing_fields.append(field_names[field])
        
        if missing_fields:
            await query.edit_message_text(
                f"❌ নিচের ফিল্ডগুলো পূরণ হয়নি:\n{', '.join(missing_fields)}\n\n"
                "বাটন ক্লিক করে ফিল্ডগুলো পূরণ করুন।"
            )
            return FORM_START
        
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
            return FORM_START
        
        context.user_data['result'] = result
        
        # প্রিভিউ দেখান
        card_text, _ = format_signal_card(result, show_delete_button=False)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ সংরক্ষণ করুন", callback_data="confirm_save"),
                InlineKeyboardButton("📝 এডিট করুন", callback_data="back_to_form"),
                InlineKeyboardButton("❌ বাতিল", callback_data="cancel_form")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{card_text}\n\n"
            "✅ সব ফিল্ড পূরণ হয়েছে। সংরক্ষণ করতে চান?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return CONFIRM
    
    elif query.data.startswith("edit_"):
        field = query.data.replace("edit_", "")
        context.user_data['editing_field'] = field
        
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
            'risk': '0.01',
            'buy': '30',
            'sl': '29',
            'tp': '39'
        }
        
        await query.edit_message_text(
            f"{field_names[field]} বসান:\n\n"
            f"উদাহরণ: {examples[field]}\n\n"
            "মান টাইপ করে পাঠান (শুধু সংখ্যা/টেক্সট):\n"
            "👉 /cancel দিয়ে ফর্মে ফিরতে পারেন"
        )
        return EDIT_VALUE

async def get_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফিল্ডের মান ইনপুট নেওয়া"""
    field = context.user_data.get('editing_field')
    value = update.message.text.strip()
    
    try:
        if field == 'symbol':
            value = value.upper()
            if len(value) > 10:
                await update.message.reply_text("❌ সিম্বল ১০ অক্ষরের বেশি হতে পারবে না। আবার দিন:")
                return EDIT_VALUE
            context.user_data['symbol'] = value
        
        elif field == 'capital':
            capital = float(value.replace(',', ''))
            if capital <= 0:
                await update.message.reply_text("❌ ক্যাপিটাল পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_VALUE
            context.user_data['capital'] = capital
        
        elif field == 'risk':
            risk = float(value)
            if risk <= 0 or risk > 1:
                await update.message.reply_text("❌ রিস্ক ০ থেকে ১ এর মধ্যে হতে হবে। আবার দিন:")
                return EDIT_VALUE
            context.user_data['risk'] = risk
        
        elif field == 'buy':
            buy = float(value)
            if buy <= 0:
                await update.message.reply_text("❌ বাই প্রাইস পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_VALUE
            context.user_data['buy'] = buy
        
        elif field == 'sl':
            sl = float(value)
            if sl <= 0:
                await update.message.reply_text("❌ এসএল প্রাইস পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_VALUE
            if 'buy' in context.user_data and sl >= context.user_data['buy']:
                await update.message.reply_text("❌ এসএল বাই থেকে কম হতে হবে। আবার দিন:")
                return EDIT_VALUE
            context.user_data['sl'] = sl
        
        elif field == 'tp':
            tp = float(value)
            if tp <= 0:
                await update.message.reply_text("❌ টিপি প্রাইস পজিটিভ হতে হবে। আবার দিন:")
                return EDIT_VALUE
            if 'buy' in context.user_data and tp <= context.user_data['buy']:
                await update.message.reply_text("❌ টিপি বাই থেকে বেশি হতে হবে। আবার দিন:")
                return EDIT_VALUE
            context.user_data['tp'] = tp
        
        # ফর্মে ফিরে যান
        keyboard = [
            [InlineKeyboardButton("📌 সিম্বল বসান", callback_data="edit_symbol")],
            [InlineKeyboardButton("💰 ক্যাপিটাল বসান", callback_data="edit_capital")],
            [InlineKeyboardButton("⚠️ রিস্ক বসান", callback_data="edit_risk")],
            [InlineKeyboardButton("📈 বাই বসান", callback_data="edit_buy")],
            [InlineKeyboardButton("📉 এসএল বসান", callback_data="edit_sl")],
            [InlineKeyboardButton("🎯 টিপি বসান", callback_data="edit_tp")],
            [InlineKeyboardButton("✅ সাবমিট", callback_data="submit_form")],
            [InlineKeyboardButton("❌ ফর্ম বাতিল", callback_data="cancel_form")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ {field} সেট করা হয়েছে!\n\n"
            f"{format_form_preview(context.user_data)}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return FORM_START
        
    except ValueError:
        await update.message.reply_text("❌ সঠিক মান দিন। আবার চেষ্টা করুন:")
        return EDIT_VALUE

async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কনফার্মেশন হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_save":
        result = context.user_data['result']
        
        # MongoDB-তে সংরক্ষণ
        result['user_id'] = query.from_user.id
        result['username'] = query.from_user.username or query.from_user.first_name
        
        insert_result = collection.insert_one(result)
        result['_id'] = insert_result.inserted_id
        
        # ফাইনাল কার্ড দেখান (ডিলিট বাটন সহ)
        card_text, keyboard = format_signal_card(result, show_delete_button=True)
        await query.edit_message_text(
            card_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        logger.info(f"Signal saved for {result['symbol']} by {query.from_user.username}")
        
    elif query.data == "back_to_form":
        keyboard = [
            [InlineKeyboardButton("📌 সিম্বল বসান", callback_data="edit_symbol")],
            [InlineKeyboardButton("💰 ক্যাপিটাল বসান", callback_data="edit_capital")],
            [InlineKeyboardButton("⚠️ রিস্ক বসান", callback_data="edit_risk")],
            [InlineKeyboardButton("📈 বাই বসান", callback_data="edit_buy")],
            [InlineKeyboardButton("📉 এসএল বসান", callback_data="edit_sl")],
            [InlineKeyboardButton("🎯 টিপি বসান", callback_data="edit_tp")],
            [InlineKeyboardButton("✅ সাবমিট", callback_data="submit_form")],
            [InlineKeyboardButton("❌ ফর্ম বাতিল", callback_data="cancel_form")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📝 **ফর্ম এডিট করুন**\n\n"
            f"{format_form_preview(context.user_data)}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return FORM_START
    
    else:
        await query.edit_message_text("❌ অপারেশন বাতিল করা হয়েছে।")
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কনভারসেশন বাতিল"""
    await update.message.reply_text(
        "🚫 অপারেশন বাতিল করা হয়েছে।\n"
        "/stock দিয়ে আবার শুরু করতে পারেন।"
    )
    context.user_data.clear()
    return ConversationHandler.END

# অন্যান্য কমান্ড (ok, clear, button_callback) আগের মতই থাকবে
async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """RRR বেশি এবং diff কম অনুযায়ী সাজানো সিগন্যাল দেখায়"""
    try:
        signals = list(collection.find({"user_id": update.effective_user.id}))
        
        if not signals:
            await update.message.reply_text("📭 আপনার কোনো সিগন্যাল নেই। /stock দিয়ে নতুন সিগন্যাল যোগ করুন।")
            return
        
        sorted_signals = sorted(signals, key=lambda x: (-x['rrr'], x['diff']))
        
        header = f"📊 **আপনার {len(sorted_signals)}টি সিগন্যাল (RRR বেশি → কম, ডিফ কম → বেশি):**\n\n"
        await update.message.reply_text(header, parse_mode='Markdown')
        
        for signal in sorted_signals:
            card_text, _ = format_signal_card(signal, show_delete_button=False)
            await update.message.reply_text(card_text, parse_mode='Markdown')
            await asyncio.sleep(0.5)
        
        keyboard = [
            [InlineKeyboardButton("🗑️ সব ডিলিট করুন", callback_data="delete_all")],
            [InlineKeyboardButton("❌ বাতিল", callback_data="cancel_delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "সব সিগন্যাল দেখানো হয়েছে। আপনি কি এই সিগন্যালগুলো ডিলিট করতে চান?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ একটি ত্রুটি হয়েছে: {str(e)}")
        logger.error(f"Error in ok_command: {e}")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সব সিগন্যাল ডিলিট করে"""
    try:
        result = collection.delete_many({"user_id": update.effective_user.id})
        
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ {result.deleted_count}টি সিগন্যাল ডিলিট করা হয়েছে।")
        else:
            await update.message.reply_text("📭 আপনার কোনো সিগন্যাল নেই।")
            
    except Exception as e:
        await update.message.reply_text(f"❌ একটি ত্রুটি হয়েছে: {str(e)}")
        logger.error(f"Error in clear_command: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনলাইন বাটনের কলব্যাক হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "delete_all":
            result = collection.delete_many({"user_id": query.from_user.id})
            await query.edit_message_text(f"✅ {result.deleted_count}টি সিগন্যাল ডিলিট করা হয়েছে।")
            
        elif query.data == "cancel_delete":
            await query.edit_message_text("❌ ডিলিট বাতিল করা হয়েছে।")
            
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

async def run_bot():
    """বট চালানোর async ফাংশন"""
    try:
        logger.info("🤖 Risk Reward BD Stock Bot চালু হচ্ছে...")
        
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # কনভারসেশন হ্যান্ডলার তৈরি
        stock_form_handler = ConversationHandler(
            entry_points=[CommandHandler('stock', stock_start)],
            states={
                FORM_START: [CallbackQueryHandler(form_button_handler)],
                EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_field_value)],
                CONFIRM: [CallbackQueryHandler(confirm_save, pattern="^(confirm_save|back_to_form|cancel_form)$")],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # হ্যান্ডলার যোগ
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(stock_form_handler)
        app.add_handler(CommandHandler("ok", ok_command))
        app.add_handler(CommandHandler("clear", clear_command))
        app.add_handler(CallbackQueryHandler(button_callback, pattern="^(delete_all|cancel_delete|delete_.*)$"))
        
        logger.info("✅ বট চালু হয়েছে")
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
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
