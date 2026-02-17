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
import re

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_FORM, CONFIRMATION = range(2)

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

def create_form_template():
    """HTML ফর্মের টেমপ্লেট তৈরি করে"""
    form = (
        "╔══════════════════════════════════════════════╗\n"
        "║           📝 স্টক সিগন্যাল ফর্ম             ║\n"
        "╠══════════════════════════════════════════════╣\n"
        "║                                              ║\n"
        "║  📌 সিম্বল        : [   আপনার সিম্বল দিন   ] ║\n"
        "║                                              ║\n"
        "║  💰 ক্যাপিটাল     : [   আপনার ক্যাপিটাল    ] ║\n"
        "║                                              ║\n"
        "║  ⚠️ রিস্ক %       : [   আপনার রিস্ক %      ] ║\n"
        "║                                              ║\n"
        "║  📈 বাই প্রাইস    : [   আপনার বাই প্রাইস   ] ║\n"
        "║                                              ║\n"
        "║  📉 এসএল প্রাইস   : [   আপনার এসএল প্রাইস  ] ║\n"
        "║                                              ║\n"
        "║  🎯 টিপি প্রাইস   : [   আপনার টিপি প্রাইস  ] ║\n"
        "║                                              ║\n"
        "╠══════════════════════════════════════════════╣\n"
        "║                                              ║\n"
        "║  একসাথে সব তথ্য দিন নিচের ফরম্যাটে:          ║\n"
        "║                                              ║\n"
        "║  সিম্বল, ক্যাপিটাল, রিস্ক%, বাই, এসএল, টিপি  ║\n"
        "║                                              ║\n"
        "║  📝 উদাহরণ:                                 ║\n"
        "║  aaa, 500000, 0.01, 30, 29, 39              ║\n"
        "║                                              ║\n"
        "╚══════════════════════════════════════════════╝"
    )
    return form

def parse_form_input(text):
    """ইউজারের ইনপুট পার্স করে"""
    try:
        # কমা দিয়ে আলাদা করা
        parts = [part.strip() for part in text.split(',')]
        
        if len(parts) != 6:
            return None, "❌ ৬টি মান দিন (কমা দিয়ে আলাদা করে)"
        
        symbol = parts[0].upper()
        
        # ক্যাপিটাল থেকে কমা ও বিডিটি বাদ
        capital_str = re.sub(r'[^\d.]', '', parts[1])
        capital = float(capital_str)
        
        risk = float(parts[2])
        buy = float(parts[3])
        sl = float(parts[4])
        tp = float(parts[5])
        
        # ভ্যালিডেশন
        if len(symbol) > 10:
            return None, "❌ সিম্বল ১০ অক্ষরের বেশি হতে পারবে না"
        
        if capital <= 0:
            return None, "❌ ক্যাপিটাল পজিটিভ হতে হবে"
        
        if risk <= 0 or risk > 1:
            return None, "❌ রিস্ক ০ থেকে ১ এর মধ্যে হতে হবে"
        
        if buy <= 0:
            return None, "❌ বাই প্রাইস পজিটিভ হতে হবে"
        
        if sl <= 0:
            return None, "❌ এসএল প্রাইস পজিটিভ হতে হবে"
        
        if tp <= 0:
            return None, "❌ টিপি প্রাইস পজিটিভ হতে হবে"
        
        if sl >= buy:
            return None, "❌ এসএল বাই থেকে কম হতে হবে"
        
        if tp <= buy:
            return None, "❌ টিপি বাই থেকে বেশি হতে হবে"
        
        return {
            'symbol': symbol,
            'capital': capital,
            'risk': risk,
            'buy': buy,
            'sl': sl,
            'tp': tp
        }, None
        
    except ValueError as e:
        return None, f"❌ সঠিক সংখ্যা দিন: {str(e)}"
    except Exception as e:
        return None, f"❌ ফরম্যাট ঠিক নয়: {str(e)}"

def format_form_preview(data):
    """ফর্ম প্রিভিউ দেখায়"""
    preview = (
        "╔════════════════════════════════╗\n"
        "║     📝 আপনার দেওয়া তথ্য       ║\n"
        "╠════════════════════════════════╣\n"
        f"║ 📌 সিম্বল      : {data['symbol']:<12} ║\n"
        f"║ 💰 ক্যাপিটাল   : {data['capital']:,.0f} BDT      ║\n"
        f"║ ⚠️ রিস্ক       : {data['risk']*100:.1f}%          ║\n"
        f"║ 📈 বাই         : {data['buy']:<12} ║\n"
        f"║ 📉 এসএল        : {data['sl']:<12} ║\n"
        f"║ 🎯 টিপি        : {data['tp']:<12} ║\n"
        "╚════════════════════════════════╝"
    )
    return preview

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📝 ফর্ম পূরণ করুন", callback_data="fill_form")],
        [InlineKeyboardButton("📊 সংরক্ষিত সিগন্যাল", callback_data="view_signals")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n"
        "আমি **Risk Reward BD Stock Bot**\n"
        "নিচের মেনু থেকে সিলেক্ট করুন:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফর্ম দেখায়"""
    query = update.callback_query
    await query.answer()
    
    form_template = create_form_template()
    
    keyboard = [[InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{form_template}\n\n"
        "👉 একসাথে সব তথ্য কমা দিয়ে লিখুন:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return WAITING_FOR_FORM

async def handle_form_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ফর্মের ইনপুট হ্যান্ডল করে"""
    user_input = update.message.text
    
    # ইনপুট পার্স করা
    data, error = parse_form_input(user_input)
    
    if error:
        keyboard = [[InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]]
        await update.message.reply_text(
            f"{error}\n\n"
            "আবার চেষ্টা করুন অথবা মেনুতে ফিরুন:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_FORM
    
    # ডাটা টেম্পোরারি স্টোর
    context.user_data['form_data'] = data
    
    # প্রিভিউ দেখান
    preview = format_form_preview(data)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ সংরক্ষণ করুন", callback_data="confirm_save"),
            InlineKeyboardButton("❌ বাতিল", callback_data="cancel_save")
        ],
        [InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{preview}\n\n"
        "আপনার তথ্য যাচাই করুন। সংরক্ষণ করতে চান?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CONFIRMATION

async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সংরক্ষণ নিশ্চিত করা"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_save":
        data = context.user_data.get('form_data')
        
        if not data:
            await query.edit_message_text("❌ কোনো ডাটা পাওয়া যায়নি!")
            return ConversationHandler.END
        
        # ক্যালকুলেশন
        result = calculate_position(
            data['symbol'],
            data['capital'],
            data['risk'],
            data['buy'],
            data['sl'],
            data['tp']
        )
        
        if "error" in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return ConversationHandler.END
        
        # MongoDB-তে সংরক্ষণ
        result['user_id'] = query.from_user.id
        result['username'] = query.from_user.username or query.from_user.first_name
        
        insert_result = collection.insert_one(result)
        result['_id'] = insert_result.inserted_id
        
        # ফাইনাল কার্ড দেখান
        card_text, keyboard = format_signal_card(result, show_delete_button=True)
        
        await query.edit_message_text(
            f"{card_text}\n\n✅ সিগন্যাল সংরক্ষণ করা হয়েছে!",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        logger.info(f"Signal saved for {result['symbol']} by {query.from_user.username}")
        
    else:
        await query.edit_message_text("❌ সংরক্ষণ বাতিল করা হয়েছে।")
    
    context.user_data.clear()
    return ConversationHandler.END

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
        return
    
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

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মেইন মেনুতে ফিরে যায়"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 ফর্ম পূরণ করুন", callback_data="fill_form")],
        [InlineKeyboardButton("📊 সংরক্ষিত সিগন্যাল", callback_data="view_signals")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📌 **মেইন মেনু**\n\n"
        "আপনি কি করতে চান?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

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
        
        # ফর্ম কনভারসেশন হ্যান্ডলার
        form_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(show_form, pattern="^fill_form$")],
            states={
                WAITING_FOR_FORM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_form_input),
                    CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$")
                ],
                CONFIRMATION: [
                    CallbackQueryHandler(confirm_save, pattern="^(confirm_save|cancel_save)$"),
                    CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$")
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # হ্যান্ডলার যোগ
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(view_signals, pattern="^view_signals$"))
        app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
        app.add_handler(form_handler)
        app.add_handler(CallbackQueryHandler(button_callback, pattern="^(delete_all|delete_.*)$"))
        
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
