import os
import sys
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
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
            return {"error": "❌ buy price must be greater than SL price"}
        
        if tp_price <= buy_price:
            return {"error": "❌ TP price must be greater than buy price"}
        
        risk_per_trade = total_capital * risk_percent
        risk_per_share = buy_price - sl_price
        
        if risk_per_share <= 0:
            return {"error": "❌ Invalid risk per share calculation"}
        
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
        return {"error": f"❌ Calculation error: {str(e)}"}

def format_signal_card(data, show_delete_button=False):
    """সিগন্যাল কার্ড ফরম্যাট তৈরি করে - SL/TP পাশাপাশি এবং RRR/ডিফ পাশাপাশি"""
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
        "/stock [সিম্বল] [ক্যাপিটাল] [রিস্ক%] [বাই] [এসএল] [টিপি] - নতুন সিগন্যাল যোগ করুন\n"
        "/ok - MongoDB থেকে সাজানো সিগন্যাল দেখুন\n"
        "/clear - সব সিগন্যাল ডিলিট করুন\n"
        "/help - সাহায্য দেখুন\n\n"
        "📝 **উদাহরণ:**\n"
        "/stock aaa 500000 0.01 30 29 39"
    )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """নতুন স্টক সিগন্যাল যোগ করে এবং MongoDB-তে সংরক্ষণ করে"""
    try:
        if len(context.args) != 6:
            await update.message.reply_text(
                "❌ **ভুল ফরম্যাট!**\n\n"
                "সঠিক ব্যবহার:\n"
                "/stock [সিম্বল] [ক্যাপিটাল] [রিস্ক%] [বাই] [এসএল] [টিপি]\n\n"
                "উদাহরণ:\n"
                "/stock aaa 500000 0.01 30 29 39"
            )
            return
        
        symbol = context.args[0].upper()
        total_capital = float(context.args[1])
        risk_percent = float(context.args[2])
        buy_price = float(context.args[3])
        sl_price = float(context.args[4])
        tp_price = float(context.args[5])
        
        # ভ্যালিডেশন
        if total_capital <= 0:
            await update.message.reply_text("❌ টোটাল ক্যাপিটাল পজিটিভ হতে হবে")
            return
        
        if risk_percent <= 0 or risk_percent > 1:
            await update.message.reply_text("❌ রিস্ক পার্সেন্ট ০ থেকে ১ এর মধ্যে হতে হবে (যেমন: 0.01 = 1%)")
            return
        
        # ক্যালকুলেশন
        result = calculate_position(symbol, total_capital, risk_percent, buy_price, sl_price, tp_price)
        
        if "error" in result:
            await update.message.reply_text(result["error"])
            return
        
        # MongoDB-তে সংরক্ষণ
        result['user_id'] = update.effective_user.id
        result['username'] = update.effective_user.username or update.effective_user.first_name
        
        insert_result = collection.insert_one(result)
        result['_id'] = insert_result.inserted_id
        
        # কার্ড দেখান (ডিলিট বাটন সহ)
        card_text, keyboard = format_signal_card(result, show_delete_button=True)
        await update.message.reply_text(card_text, reply_markup=keyboard, parse_mode='Markdown')
        
        logger.info(f"Signal saved for {symbol} by {update.effective_user.username}")
        
    except ValueError as e:
        await update.message.reply_text("❌ ভ্যালু ঠিক নয়। দয়া করে সঠিক নাম্বার দিন।")
        logger.error(f"ValueError: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ একটি ত্রুটি হয়েছে: {str(e)}")
        logger.error(f"Error in stock_command: {e}")

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
            await asyncio.sleep(0.5)  # রেট লিমিট এড়াতে সামান্য বিরতি
        
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প কমান্ড"""
    help_text = (
        "📚 **Risk Reward BD Stock Bot - সাহায্য**\n\n"
        
        "**কমান্ড সমূহ:**\n"
        "/start - বট শুরু করুন\n"
        "/help - এই হেল্প মেসেজ দেখুন\n"
        "/stock - নতুন সিগন্যাল যোগ করুন\n"
        "/ok - সংরক্ষিত সিগন্যাল দেখুন\n"
        "/clear - সব সিগন্যাল ডিলিট করুন\n\n"
        
        "**স্টক ক্যালকুলেশন ফরম্যাট:**\n"
        "`/stock [সিম্বল] [ক্যাপিটাল] [রিস্ক%] [বাই] [এসএল] [টিপি]`\n\n"
        
        "**প্যারামিটার বিবরণ:**\n"
        "• **সিম্বল:** স্টক সিম্বল (যেমন: aaa)\n"
        "• **ক্যাপিটাল:** মোট ট্রেডিং ক্যাপিটাল (BDT)\n"
        "• **রিস্ক%:** প্রতি ট্রেডে রিস্কের শতাংশ (যেমন: 0.01 = 1%)\n"
        "• **বাই:** ক্রয় মূল্য\n"
        "• **এসএল:** স্টপ লস\n"
        "• **টিপি:** টার্গেট প্রাইস\n\n"
        
        "**উদাহরণ:**\n"
        "`/stock aaa 500000 0.01 30 29 39`\n"
        "`/stock bbc 1000000 0.02 45 43 52`\n\n"
        
        "**আউটপুট ফরম্যাট:**\n"
        "📊 সিম্বল\n"
        "💰 ক্যাপিটাল\n"
        "⚠️ রিস্ক%\n"
        "📈 বাই\n"
        "📉 SL | 🎯 TP (পাশাপাশি)\n"
        "📊 RRR | 📏 ডিফ (পাশাপাশি)\n"
        "📦 পজিশন সাইজ\n"
        "💵 এক্সপোজার\n"
        "⚡ একচুয়াল রিস্ক\n\n"
        
        "**ফিচার:**\n"
        "✅ সিগন্যাল MongoDB-তে সংরক্ষিত হয়\n"
        "✅ /ok কমান্ডে RRR ও diff অনুযায়ী সাজানো দেখায়\n"
        "✅ ইনলাইন বাটন দিয়ে ডিলিট করার সুবিধা\n"
        "✅ ইউজার-ভিত্তিক ডাটা সেপারেশন"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনলাইন বাটনের কলব্যাক হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "delete_all":
            # সব সিগন্যাল ডিলিট
            result = collection.delete_many({"user_id": query.from_user.id})
            await query.edit_message_text(f"✅ {result.deleted_count}টি সিগন্যাল ডিলিট করা হয়েছে।")
            
        elif query.data == "cancel_delete":
            await query.edit_message_text("❌ ডিলিট বাতিল করা হয়েছে।")
            
        elif query.data.startswith("delete_"):
            # নির্দিষ্ট সিগন্যাল ডিলিট
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
        
        # হ্যান্ডলার যোগ
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("stock", stock_command))
        app.add_handler(CommandHandler("ok", ok_command))
        app.add_handler(CommandHandler("clear", clear_command))
        
        # ইনলাইন বাটন হ্যান্ডলার
        app.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("✅ বট চালু হয়েছে")
        logger.info(f"বট ইউজারনেম: @riskrewardbdstock_bot")
        
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
