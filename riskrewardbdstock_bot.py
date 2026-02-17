import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import json
from datetime import datetime
import re

# লগিং সক্রিয় করা
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# আপনার দেওয়া বট টোকেন
BOT_TOKEN = "8597965743:AAEV7NlAKH5VJZIXgqJ8iO02GoWKJHMIafc"

# ডাটা সংরক্ষণের ফাইল
DATA_FILE = "stock_signals.json"

def load_data():
    """JSON ফাইল থেকে ডাটা লোড করা"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data(data):
    """JSON ফাইলে ডাটা সংরক্ষণ করা"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def parse_data_format(text):
    """ডাটা ফরম্যাট পার্স করা: aaa 500000 0.01 30 29 39"""
    pattern = r'^([a-zA-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$'
    match = re.match(pattern, text.strip())
    
    if match:
        return {
            'symbol': match.group(1).upper(),
            'capital': float(match.group(2)),
            'risk': float(match.group(3)),
            'buy': float(match.group(4)),
            'sl': float(match.group(5)),
            'tp': float(match.group(6)),
            'timestamp': datetime.now().isoformat()
        }
    return None

def calculate_rrr(item):
    """RRR ক্যালকুলেশন"""
    try:
        buy = item['buy']
        sl = item['sl']
        tp = item['tp']
        
        risk = buy - sl
        reward = tp - buy
        
        if risk > 0:
            rrr = reward / risk
        else:
            rrr = 0
            
        return round(rrr, 2)
    except:
        return 0

def calculate_diff(item):
    """Buy - SL ক্যালকুলেশন"""
    return round(item['buy'] - item['sl'], 2)

def calculate_position(item):
    """পজিশন সাইজ ক্যালকুলেশন"""
    try:
        risk_amount = item['capital'] * item['risk']
        diff = item['buy'] - item['sl']
        if diff > 0:
            position = risk_amount / diff
            return int(round(position))
        return 0
    except:
        return 0

def calculate_exposure(item):
    """এক্সপোজার ক্যালকুলেশন"""
    position = calculate_position(item)
    return int(round(position * item['buy']))

def calculate_risk_amount(item):
    """রিস্ক অ্যামাউন্ট ক্যালকুলেশন"""
    return int(round(item['capital'] * item['risk']))

def format_signal(item, index=None):
    """সিগন্যাল ফরম্যাট করা"""
    rrr = calculate_rrr(item)
    diff = calculate_diff(item)
    position = calculate_position(item)
    exposure = calculate_exposure(item)
    risk_amount = calculate_risk_amount(item)
    
    if index is not None:
        header = f"🔴 #{index} {item['symbol']}"
    else:
        header = f"📊 {item['symbol']}"
    
    box = f"""
╔════════════════════════════════════╗
║  {header:<32}║
╠════════════════════════════════════╣
║  💰 ক্যাপিটাল: {item['capital']:>12,.0f} BDT  ║
║  ⚠️ রিস্ক: {item['risk']*100:>15.1f}%        ║
╠════════════════════════════════════╣
║  📈 বাই: {item['buy']:>8.1f}                  ║
║  🛑 SL: {item['sl']:>9.1f}                    ║
║  🎯 TP: {item['tp']:>9.1f}                    ║
║  📊 RRR: {rrr:>8.1f}                          ║
║  📏 ডিফ: {diff:>8.1f}                         ║
╠════════════════════════════════════╣
║  📦 পজিশন: {position:>11,} shares    ║
║  💵 এক্সপোজার: {exposure:>9,} BDT      ║
║  ⚡ রিস্ক: {risk_amount:>9,} BDT        ║
╚════════════════════════════════════╝
"""
    return box

def create_table_view(data_list):
    """টেবুলার ভিউ তৈরি করা - row ও column আকারে"""
    if not data_list:
        return "📭 কোন ডাটা নেই।"
    
    # হেডার তৈরি
    table = "```\n"
    table += "=" * 80 + "\n"
    table += f"{'#':<3} {'Symbol':<8} {'Capital':>12} {'Risk%':>6} {'Buy':>6} {'SL':>6} {'TP':>6} {'RRR':>6} {'Diff':>6} {'Position':>10}\n"
    table += "=" * 80 + "\n"
    
    # প্রতিটি এন্ট্রি যোগ করা
    for i, item in enumerate(data_list, 1):
        rrr = calculate_rrr(item)
        diff = calculate_diff(item)
        position = calculate_position(item)
        
        table += f"{i:<3} {item['symbol']:<8} {item['capital']:>12,.0f} {item['risk']*100:>5.1f}% {item['buy']:>6.1f} {item['sl']:>6.1f} {item['tp']:>6.1f} {rrr:>6.1f} {diff:>6.1f} {position:>10,}\n"
    
    table += "=" * 80 + "\n"
    table += "```"
    
    return table

def create_compact_table(data_list):
    """কম্প্যাক্ট টেবিল ভিউ (ছোট)"""
    if not data_list:
        return "📭 কোন ডাটা নেই।"
    
    # হেডার
    table = "```\n"
    table += "=" * 60 + "\n"
    table += f"{'#':<3} {'Symbol':<6} {'RRR':>5} {'Buy':>5} {'SL':>5} {'TP':>5} {'Diff':>5}\n"
    table += "=" * 60 + "\n"
    
    # ডাটা
    for i, item in enumerate(data_list, 1):
        rrr = calculate_rrr(item)
        diff = calculate_diff(item)
        table += f"{i:<3} {item['symbol']:<6} {rrr:>5.1f} {item['buy']:>5.1f} {item['sl']:>5.1f} {item['tp']:>5.1f} {diff:>5.1f}\n"
    
    table += "=" * 60 + "\n"
    table += "```"
    
    return table

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড হ্যান্ডলার"""
    user = update.effective_user
    
    text = f"""হ্যালো {user.first_name}! 👋

╔════════════════════════════╗
║   📈 স্টক সিগন্যাল বট     ║
╠════════════════════════════╣
║ ফরম্যাট:                  ║
║ সিম্বল ক্যাপিটাল রিস্ক    ║
║ বাই এসএল টিপি            ║
║                          ║
║ যেমন:                    ║
║ aaa 500000 0.01 30 29 39 ║
║                          ║
╠════════════════════════════╣
║ 📋 কমান্ড:                ║
║ /list - সব সিগন্যাল (টেবিল)║
║ /listall - বিস্তারিত তালিকা║
║ /delete - সব মুছুন        ║
║ /help - সাহায্য           ║
╚════════════════════════════╝
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help কমান্ড হ্যান্ডলার"""
    text = """📝 **ব্যবহার বিধি**

╔════════════════════════════╗
║    ফরম্যাট ব্যাখ্যা        ║
╠════════════════════════════╣
║ <code>aaa 500000 0.01 30 29 39</code> ║
║                          ║
║ • aaa = স্টক সিম্বল      ║
║ • 500000 = মূলধন (টাকা)  ║
║ • 0.01 = রিস্ক (1%)      ║
║ • 30 = বাই প্রাইস        ║
║ • 29 = স্টপ লস (SL)     ║
║ • 39 = টার্গেট (TP)      ║
╚════════════════════════════╝

**ক্যালকুলেশন:**
• RRR = (TP - Buy) / (Buy - SL)
• পজিশন = (ক্যাপিটাল × রিস্ক) / (Buy - SL)
• এক্সপোজার = পজিশন × Buy

**কমান্ড:**
• /list - কম্প্যাক্ট টেবিল ভিউ
• /listall - বিস্তারিত টেবিল
• /delete - সব ডাটা মুছুন
"""
    
    await update.message.reply_text(text, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনকামিং মেসেজ হ্যান্ডলার"""
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    
    data_item = parse_data_format(text)
    
    if data_item:
        all_data = load_data()
        
        if user_id not in all_data:
            all_data[user_id] = []
        
        all_data[user_id].append(data_item)
        save_data(all_data)
        
        signal_box = format_signal(data_item)
        
        await update.message.reply_text(
            f"✅ **সিগন্যাল সংরক্ষিত!**\n{signal_box}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            """❌ **ভুল ফরম্যাট!**

সঠিক ফরম্যাট:
`aaa 500000 0.01 30 29 39`

উদাহরণ:
`aaa 500000 0.01 30 29 39`
`bbb 1000000 0.02 45 44 55`

সাহায্যের জন্য /help ব্যবহার করুন""",
            parse_mode='Markdown'
        )

async def list_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কম্প্যাক্ট টেবিল ভিউ দেখানো"""
    user_id = str(update.effective_user.id)
    all_data = load_data()
    
    if user_id not in all_data or not all_data[user_id]:
        await update.message.reply_text('📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।')
        return
    
    # RRR অনুযায়ী সাজানো
    sorted_data = sorted(
        all_data[user_id], 
        key=lambda x: calculate_rrr(x), 
        reverse=True
    )
    
    # কম্প্যাক্ট টেবিল তৈরি
    table = create_compact_table(sorted_data)
    
    # মেসেজ পাঠানো
    await update.message.reply_text(
        f"📋 **কম্প্যাক্ট ভিউ (RRR বেশি আগে):**\n\n{table}",
        parse_mode='Markdown'
    )
    
    # বিস্তারিত দেখার বাটন
    keyboard = [[
        InlineKeyboardButton("📊 বিস্তারিত দেখুন", callback_data="show_detailed")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "বিস্তারিত তথ্যের জন্য নিচের বাটনে ক্লিক করুন:",
        reply_markup=reply_markup
    )

async def list_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বিস্তারিত টেবিল ভিউ দেখানো"""
    user_id = str(update.effective_user.id)
    all_data = load_data()
    
    if user_id not in all_data or not all_data[user_id]:
        await update.message.reply_text('📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।')
        return
    
    # RRR অনুযায়ী সাজানো
    sorted_data = sorted(
        all_data[user_id], 
        key=lambda x: calculate_rrr(x), 
        reverse=True
    )
    
    # বিস্তারিত টেবিল তৈরি
    table = create_table_view(sorted_data)
    
    # মেসেজ পাঠানো
    await update.message.reply_text(
        f"📋 **বিস্তারিত ভিউ (RRR বেশি আগে):**\n\n{table}",
        parse_mode='Markdown'
    )

async def delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সব ইউজার ডাটা মুছে ফেলা"""
    user_id = str(update.effective_user.id)
    all_data = load_data()
    
    if user_id in all_data:
        del all_data[user_id]
        save_data(all_data)
        await update.message.reply_text("✅ সব ডাটা মুছে ফেলা হয়েছে।")
    else:
        await update.message.reply_text('📭 আপনার মুছে ফেলার মতো কোনো ডাটা নেই।')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাটন ক্লিক হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    all_data = load_data()
    
    if user_id not in all_data or not all_data[user_id]:
        await query.edit_message_text("📭 কোনো ডাটা পাওয়া যায়নি।")
        return
    
    if query.data == "show_detailed":
        # বিস্তারিত টেবিল দেখানো
        sorted_data = sorted(
            all_data[user_id], 
            key=lambda x: calculate_rrr(x), 
            reverse=True
        )
        
        table = create_table_view(sorted_data)
        
        await query.edit_message_text(
            f"📋 **বিস্তারিত ভিউ:**\n\n{table}",
            parse_mode='Markdown'
        )
        return
    
    # অন্যান্য কলব্যাক হ্যান্ডলিং
    callback_data = query.data
    action, index_str = callback_data.split('_')
    index = int(index_str)
    
    sorted_data = sorted(
        all_data[user_id], 
        key=lambda x: calculate_rrr(x), 
        reverse=True
    )
    
    if index >= len(sorted_data):
        await query.edit_message_text("❌ এন্ট্রি পাওয়া যায়নি।")
        return
    
    if action == "delete":
        actual_item = sorted_data[index]
        
        user_data = all_data[user_id]
        for i, item in enumerate(user_data):
            if (item['symbol'] == actual_item['symbol'] and 
                item['capital'] == actual_item['capital'] and
                item['risk'] == actual_item['risk'] and
                item['buy'] == actual_item['buy'] and
                item['sl'] == actual_item['sl'] and
                item['tp'] == actual_item['tp']):
                user_data.pop(i)
                break
        
        if not user_data:
            del all_data[user_id]
        
        save_data(all_data)
        
        await query.edit_message_text(f"✅ এন্ট্রি #{index+1} মুছে ফেলা হয়েছে।")
    
    elif action == "edit":
        await query.edit_message_text(
            f"""✏️ **এন্ট্রি #{index+1} সম্পাদনা করুন**

নতুন ডাটা এই ফরম্যাটে পাঠান:
`সিম্বল ক্যাপিটাল রিস্ক বাই এসএল টিপি`

উদাহরণ:
`aaa 500000 0.01 30 29 39`""",
            parse_mode='Markdown'
        )
        context.user_data['editing_index'] = index

async def main():
    """মেইন ফাংশন"""
    logger.info("🤖 বট চালু হচ্ছে...")
    logger.info(f"বট টোকেন: {BOT_TOKEN[:10]}...")
    
    try:
        # অ্যাপ্লিকেশন তৈরি
        application = Application.builder().token(BOT_TOKEN).build()

        # কমান্ড হ্যান্ডলার
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("list", list_data))
        application.add_handler(CommandHandler("listall", list_all_data))
        application.add_handler(CommandHandler("delete", delete_all))
        
        # মেসেজ হ্যান্ডলার
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # কলব্যাক হ্যান্ডলার
        application.add_handler(CallbackQueryHandler(button_callback))

        logger.info("✅ বট সফলভাবে চালু হয়েছে!")
        logger.info("📱 আপনার বট এখন অ্যাকটিভ: @riskrewardbd_bot")
        
        # বট চালু করা
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # বট চালু রাখা
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ বট চালু করতে সমস্যা: {e}")
        
    finally:
        logger.info("🛑 বট বন্ধ হচ্ছে...")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 ইউজার বট বন্ধ করেছেন।")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        except KeyboardInterrupt:
            logger.info("🛑 ইউজার বট বন্ধ করেছেন।")
