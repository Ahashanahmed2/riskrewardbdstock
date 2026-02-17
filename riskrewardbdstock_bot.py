import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# টোকেন সেট করুন (সরাসরি)
TELEGRAM_TOKEN = "8597965743:AAEV7NlAKH5VJZIXgqJ8iO02GoWKJHMIafc"

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
            "risk_percent": risk_percent * 100
        }
    except Exception as e:
        return {"error": f"❌ Calculation error: {str(e)}"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n"
        "আমি Risk Reward BD Stock Bot\n\n"
        "/stock [সিম্বল] [ক্যাপিটাল] [রিস্ক%] [বাই] [এসএল] [টিপি]\n"
        "উদাহরণ: /stock aaa 500000 0.01 30 29 39"
    )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 6:
            await update.message.reply_text("❌ ফরম্যাট: /stock [সিম্বল] [ক্যাপিটাল] [রিস্ক%] [বাই] [এসএল] [টিপি]")
            return
        
        symbol = context.args[0].upper()
        total_capital = float(context.args[1])
        risk_percent = float(context.args[2])
        buy_price = float(context.args[3])
        sl_price = float(context.args[4])
        tp_price = float(context.args[5])
        
        result = calculate_position(symbol, total_capital, risk_percent, buy_price, sl_price, tp_price)
        
        if "error" in result:
            await update.message.reply_text(result["error"])
            return
        
        reply = (
            f"📊 {result['symbol']}\n"
            f"💰 ক্যাপিটাল: {result['total_capital']:,.0f} BDT\n"
            f"⚠️ রিস্ক: {result['risk_percent']:.1f}%\n"
            f"📈 বাই: {result['buy']} | 📉 SL: {result['sl']} | 🎯 TP: {result['tp']}\n"
            f"📊 RRR: {result['rrr']} | 📏 ডিফ: {result['diff']}\n"
            f"📦 পজিশন: {result['position_size']} shares\n"
            f"💵 এক্সপোজার: {result['exposure_bdt']:,.0f} BDT\n"
            f"⚡ রিস্ক: {result['actual_risk_bdt']:,.0f} BDT"
        )
        
        await update.message.reply_text(reply)
        
    except ValueError:
        await update.message.reply_text("❌ ভ্যালু ঠিক নয়")
    except Exception as e:
        await update.message.reply_text(f"❌ এরর: {str(e)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/stock [সিম্বল] [ক্যাপিটাল] [রিস্ক%] [বাই] [এসএল] [টিপি]\n"
        "উদাহরণ: /stock aaa 500000 0.01 30 29 39"
    )

def main():
    """মেইন ফাংশন"""
    try:
        print("🤖 বট চালু হচ্ছে...")
        
        # Application তৈরি
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # হ্যান্ডলার যোগ
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("stock", stock_command))
        
        print("✅ বট চালু হয়েছে")
        
        # Polling শুরু
        app.run_polling()
        
    except Exception as e:
        print(f"❌ এরর: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
