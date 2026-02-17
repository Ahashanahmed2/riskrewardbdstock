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
SYMBOL, CAPITAL, RISK, BUY, SL, TP, CONFIRM = range(7)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n"
        "আমি **Risk Reward BD Stock Bot**\n\n"
        "📌 **কমান্ড সমূহ:**\n"
        "/stock - নতুন সিগন্যাল যোগ করুন (স্টেপ বাই স্টেপ)\n"
        "/ok - MongoDB থেকে সাজানো সিগন্যাল দেখুন\n"
        "/clear - সব সিগن্যাল ডিলিট করুন\n"
        "/cancel - কোন অপারেশন বাতিল করুন\n"
        "/help - সাহায্য দেখুন\n\n"
        "📝 **উদাহরণ:**\n"
        "/stock - তারপর ধাপে ধাপে তথ্য দিন"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প কমান্ড"""
    help_text = (
        "📚 **Risk Reward BD Stock Bot - সাহায্য**\n\n"
        
        "**কমান্ড সমূহ:**\n"
        "/start - বট শুরু করুন\n"
        "/help - এই হেল্প মেসেজ দেখুন\n"
        "/stock - নতুন সিগন্যাল যোগ করুন (স্টেপ বাই স্টেপ)\n"
        "/ok - সংরক্ষিত সিগন্যাল দেখুন\n"
        "/clear - সব সিগন্যাল ডিলিট করুন\n"
        "/cancel - কোন অপারেশন বাতিল করুন\n\n"
        
        "**স্টক ক্যালকুলেশন স্টেপ বাই স্টেপ:**\n"
        "1️⃣ /stock কমান্ড দিন\n"
        "2️⃣ সিম্বল দিন (যেমন: aaa)\n"
        "3️⃣ টোটাল ক্যাপিটাল দিন (যেমন: 500000)\n"
        "4️⃣ রিস্ক পার্সেন্ট দিন (যেমন: 0.01)\n"
        "5️⃣ বাই প্রাইস দিন (যেমন: 30)\n"
        "6️⃣ এসএল প্রাইস দিন (যেমন: 29)\n"
        "7️⃣ টিপি প্রাইস দিন (যেমন: 39)\n"
        "8️⃣ কনফার্ম করুন\n\n"
        
        "**আউটপুট ফরম্যাট:**\n"
        "📊 সিম্বল\n"
        "💰 ক্যাপিটাল\n"
        "⚠️ রিস্ক%\n"
        "📈 বাই\n"
        "📉 SL | 🎯 TP (পাশাপাশি)\n"
        "📊 RRR | 📏 ডিফ (পাশাপাশি)\n"
        "📦 পজিশন সাইজ\n"
        "💵 এক্সপোজার\n"
        "⚡ একচুয়াল রিস্ক"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stock_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টক কনভারসেশন শুরু"""
    await update.message.reply_text(
        "📝 **নতুন স্টক সিগন্যাল তৈরি**\n\n"
        "প্রথমে **সিম্বল** দিন (যেমন: aaa):\n"
        "👉 /cancel দিয়ে বাতিল করতে পারেন"
    )
    return SYMBOL

async def get_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সিম্বল ইনপুট নেওয়া"""
    symbol = update.message.text.strip().upper()
    
    if len(symbol) > 10:
        await update.message.reply_text("❌ সিম্বল ১০ অক্ষরের বেশি হতে পারবে না। আবার দিন:")
        return SYMBOL
    
    context.user_data['symbol'] = symbol
    await update.message.reply_text(
        f"✅ সিম্বল: {symbol}\n\n"
        "এখন **টোটাল ক্যাপিটাল** দিন (যেমন: 500000):\n"
        "👉 শুধু সংখ্যা দিন, কমা বা বিডিটি লেখার দরকার নেই"
    )
    return CAPITAL

async def get_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ক্যাপিটাল ইনপুট নেওয়া"""
    try:
        capital = float(update.message.text.replace(',', ''))
        if capital <= 0:
            await update.message.reply_text("❌ ক্যাপিটাল পজিটিভ হতে হবে। আবার দিন:")
            return CAPITAL
        
        context.user_data['capital'] = capital
        await update.message.reply_text(
            f"✅ ক্যাপিটাল: {capital:,.0f} BDT\n\n"
            "এখন **রিস্ক পার্সেন্ট** দিন (যেমন: 0.01 = 1%):\n"
            "👉 ০ থেকে ১ এর মধ্যে সংখ্যা দিন"
        )
        return RISK
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা দিন। আবার চেষ্টা করুন:")
        return CAPITAL

async def get_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """রিস্ক পার্সেন্ট ইনপুট নেওয়া"""
    try:
        risk = float(update.message.text)
        if risk <= 0 or risk > 1:
            await update.message.reply_text("❌ রিস্ক ০ থেকে ১ এর মধ্যে হতে হবে। আবার দিন:")
            return RISK
        
        context.user_data['risk'] = risk
        await update.message.reply_text(
            f"✅ রিস্ক: {risk*100:.1f}%\n\n"
            "এখন **বাই প্রাইস** দিন (যেমন: 30):"
        )
        return BUY
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা দিন। আবার চেষ্টা করুন:")
        return RISK

async def get_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাই প্রাইস ইনপুট নেওয়া"""
    try:
        buy = float(update.message.text)
        if buy <= 0:
            await update.message.reply_text("❌ বাই প্রাইস পজিটিভ হতে হবে। আবার দিন:")
            return BUY
        
        context.user_data['buy'] = buy
        await update.message.reply_text(
            f"✅ বাই: {buy}\n\n"
            "এখন **এসএল প্রাইস** দিন (যেমন: 29):"
        )
        return SL
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা দিন। আবার চেষ্টা করুন:")
        return BUY

async def get_sl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এসএল প্রাইস ইনপুট নেওয়া"""
    try:
        sl = float(update.message.text)
        if sl <= 0:
            await update.message.reply_text("❌ এসএল প্রাইস পজিটিভ হতে হবে। আবার দিন:")
            return SL
        
        if sl >= context.user_data['buy']:
            await update.message.reply_text("❌ এসএল বাই থেকে কম হতে হবে। আবার দিন:")
            return SL
        
        context.user_data['sl'] = sl
        await update.message.reply_text(
            f"✅ SL: {sl}\n\n"
            "এখন **টিপি প্রাইস** দিন (যেমন: 39):"
        )
        return TP
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা দিন। আবার চেষ্টা করুন:")
        return SL

async def get_tp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """টিপি প্রাইস ইনপুট নেওয়া"""
    try:
        tp = float(update.message.text)
        if tp <= 0:
            await update.message.reply_text("❌ টিপি প্রাইস পজিটিভ হতে হবে। আবার দিন:")
            return TP
        
        if tp <= context.user_data['buy']:
            await update.message.reply_text("❌ টিপি বাই থেকে বেশি হতে হবে। আবার দিন:")
            return TP
        
        context.user_data['tp'] = tp
        
        # সব ডাটা নিয়ে ক্যালকুলেশন
        result = calculate_position(
            context.user_data['symbol'],
            context.user_data['capital'],
            context.user_data['risk'],
            context.user_data['buy'],
            context.user_data['sl'],
            tp
        )
        
        if "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
            return ConversationHandler.END
        
        context.user_data['result'] = result
        
        # কনফার্মেশন কার্ড দেখান
        card_text, _ = format_signal_card(result, show_delete_button=False)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ সংরক্ষণ করুন", callback_data="confirm_save"),
                InlineKeyboardButton("❌ বাতিল", callback_data="confirm_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{card_text}\n\n"
            "আপনার তথ্য যাচাই করুন। সংরক্ষণ করতে চান?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return CONFIRM
        
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা দিন। আবার চেষ্টা করুন:")
        return TP

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
        
    else:
        await query.edit_message_text("❌ অপারেশন বাতিল করা হয়েছে।")
    
    # ক্লিনআপ
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

async def ok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """RRR বেশি এবং diff কম অনুযায়ী সাজানো সিগন্যাল দেখায়"""
    try:
        # ইউজারের সব সিগন্যাল সংগ্রহ করুন
        signals = list(collection.find({"user_id": update.effective_user.id}))
        
        if not signals:
            await update.message.reply_text("📭 আপনার কোনো সিগন্যাল নেই। /stock দিয়ে নতুন সিগন্যাল যোগ করুন।")
            return
        
        # RRR অনুযায়ী সাজানো (উচ্চ থেকে নিম্ন) এবং তারপর diff (নিম্ন থেকে উচ্চ)
        sorted_signals = sorted(signals, key=lambda x: (-x['rrr'], x['diff']))
        
        # হেডার মেসেজ
        header = f"📊 **আপনার {len(sorted_signals)}টি সিগন্যাল (RRR বেশি → কম, ডিফ কম → বেশি):**\n\n"
        await update.message.reply_text(header, parse_mode='Markdown')
        
        # প্রতিটি সিগন্যাল আলাদা কার্ডে দেখান
        for signal in sorted_signals:
            card_text, _ = format_signal_card(signal, show_delete_button=False)
            await update.message.reply_text(card_text, parse_mode='Markdown')
            await asyncio.sleep(0.5)
        
        # ডিলিট কনফার্মেশন বাটন
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
        
        # Application তৈরি
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # কনভারসেশন হ্যান্ডলার তৈরি
        stock_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('stock', stock_start)],
            states={
                SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_symbol)],
                CAPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_capital)],
                RISK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_risk)],
                BUY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_buy)],
                SL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sl)],
                TP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tp)],
                CONFIRM: [CallbackQueryHandler(confirm_save, pattern="^(confirm_save|confirm_cancel)$")],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # হ্যান্ডলার যোগ
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(stock_conv_handler)
        app.add_handler(CommandHandler("ok", ok_command))
        app.add_handler(CommandHandler("clear", clear_command))
        app.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("✅ বট চালু হয়েছে")
        
        # বট চালান
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
