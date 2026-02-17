import os
import sys
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import re
from datetime import datetime

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 🔴 আপনার বট টোকেন এখানে সেট করুন
TELEGRAM_TOKEN = "8597965743:AAEV7NlAKH5VJZIXgqJ8iO02GoWKJHMIafc"

def calculate_position(symbol, total_capital, risk_percent, buy_price, sl_price, tp_price):
    """
    ট্রেডিং প্যারামিটার ক্যালকুলেট করে
    """
    try:
        # ইনপুট ভ্যালিডেশন
        if buy_price <= sl_price:
            return {"error": "❌ buy price must be greater than SL price"}
        
        if tp_price <= buy_price:
            return {"error": "❌ TP price must be greater than buy price"}
        
        # ক্যালকুলেশন
        risk_per_trade = total_capital * risk_percent
        risk_per_share = buy_price - sl_price
        
        if risk_per_share <= 0:
            return {"error": "❌ Invalid risk per share calculation"}
        
        position_size = int(risk_per_trade / risk_per_share)
        position_size = max(1, position_size)  # minimum 1 share
        
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
            "risk_percent": risk_percent * 100
        }
        
    except Exception as e:
        return {"error": f"❌ Calculation error: {str(e)}"}

def format_output(data):
    """ফরম্যাটেড আউটপুট তৈরি করে"""
    if "error" in data:
        return data["error"]
    
    return (
        f"📊 **ট্রেড ক্যালকুলেশন**\n\n"
        f"📌 **সিম্বল:** {data['symbol']}\n"
        f"💰 **ক্যাপিটাল:** {data['total_capital']:,.0f} BDT\n"
        f"⚠️ **রিস্ক:** {data['risk_percent']:.1f}%\n\n"
        f"📈 **বাই:** {data['buy']}\n"
        f"📉 **SL:** {data['sl']}\n"
        f"🎯 **TP:** {data['tp']}\n"
        f"📊 **RRR:** {data['rrr']}\n"
        f"📏 **ডিফারেন্স:** {data['diff']}\n\n"
        f"📦 **পজিশন সাইজ:** {data['position_size']} shares\n"
        f"💵 **এক্সপোজার:** {data['exposure_bdt']:,.0f} BDT\n"
        f"⚡ **একচুয়াল রিস্ক:** {data['actual_risk_bdt']:,.0f} BDT\n\n"
        f"✅ **রিস্ক টার্গেট:** {data['total_capital'] * (data['risk_percent']/100):,.0f} BDT"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n"
        "আমি **Risk Reward BD Stock Bot** - আপনার ট্রেড ক্যালকুলেশন সহায়ক।\n\n"
        "📌 **উপলব্ধ কমান্ড:**\n"
        "/stock [সিম্বল] [টোটাল_ক্যাপিটাল] [রিস্ক_পার্সেন্ট] [বাই] [এসএল] [টিপি]\n"
        "/help - সাহায্য দেখুন\n\n"
        "📝 **উদাহরণ:**\n"
        "`/stock aaa 500000 0.01 30 29 39`\n\n"
        "আমি ক্যালকুলেট করব:\n"
        "✅ পজিশন সাইজ\n"
        "✅ এক্সপোজার\n"
        "✅ একচুয়াল রিস্ক\n"
        "✅ RRR\n"
        "✅ ডিফারেন্স"
    )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stock সিম্বল টোটাল_ক্যাপিটাল রিস্ক_পার্সেন্ট বাই এসএল টিপি
    উদাহরণ: /stock aaa 500000 0.01 30 29 39
    """
    try:
        # আর্গুমেন্ট চেক
        if len(context.args) != 6:
            await update.message.reply_text(
                "❌ **ভুল ফরম্যাট!**\n\n"
                "সঠিক ব্যবহার:\n"
                "`/stock [সিম্বল] [টোটাল_ক্যাপিটাল] [রিস্ক_পার্সেন্ট] [বাই] [এসএল] [টিপি]`\n\n"
                "উদাহরণ:\n"
                "`/stock aaa 500000 0.01 30 29 39`"
            )
            return
        
        # আর্গুমেন্ট পার্স করুন
        symbol = context.args[0].strip().upper()
        total_capital = float(context.args[1].replace(',', ''))
        risk_percent = float(context.args[2])
        buy_price = float(context.args[3])
        sl_price = float(context.args[4])
        tp_price = float(context.args[5])
        
        # সিম্বল ভ্যালিডেশন
        if not symbol or len(symbol) > 10:
            await update.message.reply_text("❌ সিম্বল নাম সঠিক নয় (১-১০ অক্ষর)")
            return
        
        # ভ্যালিডেশন
        if total_capital <= 0:
            await update.message.reply_text("❌ টোটাল ক্যাপিটাল পজিটিভ হতে হবে")
            return
        
        if risk_percent <= 0 or risk_percent > 1:
            await update.message.reply_text("❌ রিস্ক পার্সেন্ট ০ থেকে ১ এর মধ্যে হতে হবে (যেমন: 0.01 = 1%)")
            return
        
        if buy_price <= 0 or sl_price <= 0 or tp_price <= 0:
            await update.message.reply_text("❌ সব প্রাইস পজিটিভ হতে হবে")
            return
        
        # ক্যালকুলেশন
        result = calculate_position(
            symbol=symbol,
            total_capital=total_capital,
            risk_percent=risk_percent,
            buy_price=buy_price,
            sl_price=sl_price,
            tp_price=tp_price
        )
        
        # রেজাল্ট পাঠান
        await update.message.reply_text(format_output(result))
        
        # লগ করুন
        logger.info(f"Stock calculation by {update.effective_user.username or update.effective_user.first_name}: {context.args}")
        
    except ValueError as e:
        await update.message.reply_text(
            "❌ **ভ্যালু এরর!**\n\n"
            "দয়া করে সঠিক নাম্বার দিন।\n"
            "উদাহরণ: `/stock aaa 500000 0.01 30 29 39`"
        )
        logger.error(f"ValueError in stock_command: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ একটি ত্রুটি হয়েছে: {str(e)}")
        logger.error(f"Error in stock_command: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প কমান্ড"""
    help_text = (
        "📚 **Risk Reward BD Stock Bot - সাহায্য**\n\n"
        "**কমান্ড সমূহ:**\n"
        "/start - বট শুরু করুন\n"
        "/help - এই হেল্প মেসেজ দেখুন\n"
        "/stock - ট্রেড ক্যালকুলেট করুন\n\n"
        
        "**স্টক ক্যালকুলেশন ফরম্যাট:**\n"
        "`/stock [সিম্বল] [টোটাল_ক্যাপিটাল] [রিস্ক_পার্সেন্ট] [বাই] [এসএল] [টিপি]`\n\n"
        
        "**প্যারামিটার বিবরণ:**\n"
        "• **সিম্বল:** স্টক সিম্বল (যেমন: aaa, bbc, etc.)\n"
        "• **টোটাল_ক্যাপিটাল:** মোট ট্রেডিং ক্যাপিটাল (BDT)\n"
        "• **রিস্ক_পার্সেন্ট:** প্রতি ট্রেডে রিস্কের শতাংশ (যেমন: 0.01 = 1%)\n"
        "• **বাই:** ক্রয় মূল্য\n"
        "• **এসএল:** স্টপ লস\n"
        "• **টিপি:** টার্গেট প্রাইস\n\n"
        
        "**উদাহরণ:**\n"
        "`/stock aaa 500000 0.01 30 29 39`\n"
        "`/stock bbc 1000000 0.02 45 43 52`\n\n"
        
        "**আউটপুট:**\n"
        "• স্টক সিম্বল\n"
        "• পজিশন সাইজ (শেয়ার সংখ্যা)\n"
        "• এক্সপোজার (মোট বিনিয়োগ)\n"
        "• একচুয়াল রিস্ক (BDT)\n"
        "• RRR (Risk-Reward Ratio)\n"
        "• ডিফারেন্স (বাই - এসএল)\n\n"
        
        "📢 **ডেভেলপার:** @MuktarHosen"
    )
    await update.message.reply_text(help_text)

async def run_bot():
    """বট চালু করার জন্য async ফাংশন"""
    try:
        logger.info("🤖 Risk Reward BD Stock Bot চালু হচ্ছে...")
        
        # Application তৈরি
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # হ্যান্ডলার যোগ করুন
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("stock", stock_command))
        
        logger.info("✅ বট চালু হয়েছে")
        logger.info("🤖 বট ইউজারনেম: @riskrewardbdstock_bot")
        
        # বট চালান
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # বট চলতে থাকবে
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ বট চালু ত্রুটি: {e}", exc_info=True)
        raise

def main():
    """মেইন ফাংশন - Event Loop সেটআপ"""
    try:
        # Python 3.14+ এর জন্য Event Loop সেটআপ
        if sys.version_info >= (3, 14):
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        
        # Event Loop তৈরি
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # বট চালান
        loop.run_until_complete(run_bot())
        loop.run_forever()
        
    except KeyboardInterrupt:
        logger.info("🛑 বট বন্ধ হচ্ছে...")
    except Exception as e:
        logger.error(f"❌ মেইন ত্রুটি: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
