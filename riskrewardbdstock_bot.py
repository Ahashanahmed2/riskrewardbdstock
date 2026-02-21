import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import json
from datetime import datetime
import re
import csv
import io
import threading

# Flask HTTP সার্ভার for UptimeRobot
from flask import Flask, jsonify
import requests

# লগিং সক্রিয় করা
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# আপনার দেওয়া বট টোকেন
BOT_TOKEN = "8597965743:AAEV7NlAKH5VJZIXgqJ8iO02GoWKJHMIafc"

# Flask অ্যাপ তৈরি
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        'status': 'active',
        'message': 'Stock Signal Bot is running!',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/ping')
def ping():
    return jsonify({'status': 'pong'}), 200

def run_flask():
    """Flask সার্ভার চালানোর ফাংশন"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    logger.info(f"🌐 HTTP সার্ভার চালু হয়েছে (পোর্ট: {port})")

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

def calculate_profit_loss(item):
    """একটি স্টক থেকে কত টাকা profit/loss হবে তা ক্যালকুলেশন"""
    try:
        position = calculate_position(item)
        buy = item['buy']
        tp = item['tp']
        sl = item['sl']
        
        profit_amount = (tp - buy) * position
        loss_amount = (buy - sl) * position
        
        return {
            'profit': int(round(profit_amount)),
            'loss': int(round(loss_amount))
        }
    except:
        return {'profit': 0, 'loss': 0}

def calculate_profit_percentage(item):
    """প্রফিট পার্সেন্টেজ ক্যালকুলেশন"""
    try:
        buy = item['buy']
        tp = item['tp']
        profit_percent = ((tp - buy) / buy) * 100
        return round(profit_percent, 2)
    except:
        return 0

def calculate_loss_percentage(item):
    """লস পার্সেন্টেজ ক্যালকুলেশন"""
    try:
        buy = item['buy']
        sl = item['sl']
        loss_percent = ((buy - sl) / buy) * 100
        return round(loss_percent, 2)
    except:
        return 0

def format_signal(item, index=None):
    """সিগন্যাল ফরম্যাট করা - আপডেটেড ভার্সন"""
    rrr = calculate_rrr(item)
    diff = calculate_diff(item)
    position = calculate_position(item)
    exposure = calculate_exposure(item)
    risk_amount = calculate_risk_amount(item)
    pl = calculate_profit_loss(item)
    profit_percent = calculate_profit_percentage(item)
    loss_percent = calculate_loss_percentage(item)

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
║  📈 বাই: {item['buy']:>8.1f}                   ║
║  🛑 SL:  {item['sl']:>8.1f}                   ║
║  🎯 TP:  {item['tp']:>8.1f}                   ║
╠════════════════════════════════════╣
║  💰 প্রফিট: {pl['profit']:>9,} BDT ({profit_percent:>5.1f}%)  ║
║  📉 লস:    {pl['loss']:>9,} BDT ({loss_percent:>5.1f}%)    ║
╠════════════════════════════════════╣
║  📊 RRR:   {rrr:>5.1f}              ডিফ: {diff:>5.1f}   ║
╠════════════════════════════════════╣
║  📦 পজিশন: {position:>11,} shares    ║
║  💵 এক্সপোজার: {exposure:>9,} BDT      ║
║  ⚡ রিস্ক অ্যামাউন্ট: {risk_amount:>5,} BDT        ║
╚════════════════════════════════════╝
"""
    return box

def create_table_view(data_list):
    """বিস্তারিত টেবিল ভিউ - আপডেটেড"""
    if not data_list:
        return "📭 কোন ডাটা নেই।"

    table = "```\n"
    table += "=" * 120 + "\n"
    table += f"{'#':<3} {'Symbol':<8} {'Capital':>10} {'Risk%':>5} {'Buy':>6} {'SL':>6} {'TP':>6} {'RRR':>5} {'Diff':>5} {'Profit%':>6} {'Position':>8} {'Exposure':>9}\n"
    table += "=" * 120 + "\n"

    for i, item in enumerate(data_list, 1):
        rrr = calculate_rrr(item)
        diff = calculate_diff(item)
        position = calculate_position(item)
        exposure = calculate_exposure(item)
        profit_percent = calculate_profit_percentage(item)

        table += f"{i:<3} {item['symbol']:<8} {item['capital']:>10,.0f} {item['risk']*100:>4.1f}% {item['buy']:>6.1f} {item['sl']:>6.1f} {item['tp']:>6.1f} {rrr:>5.1f} {diff:>5.1f} {profit_percent:>6.1f}% {position:>8,} {exposure:>9,}\n"

    table += "=" * 120 + "\n"
    table += "```"

    return table

def create_compact_table(data_list):
    """কম্প্যাক্ট টেবিল ভিউ - আপডেটেড"""
    if not data_list:
        return "📭 কোন ডাটা নেই।"

    table = "```\n"
    table += "=" * 70 + "\n"
    table += f"{'#':<3} {'Symbol':<6} {'Buy':>6} {'SL':>6} {'TP':>6} {'RRR':>5} {'Diff':>5} {'Profit%':>6}\n"
    table += "=" * 70 + "\n"

    for i, item in enumerate(data_list, 1):
        rrr = calculate_rrr(item)
        diff = calculate_diff(item)
        profit_percent = calculate_profit_percentage(item)
        table += f"{i:<3} {item['symbol']:<6} {item['buy']:>6.1f} {item['sl']:>6.1f} {item['tp']:>6.1f} {rrr:>5.1f} {diff:>5.1f} {profit_percent:>6.1f}%\n"

    table += "=" * 70 + "\n"
    table += "```"

    return table

def get_statistics(data_list):
    """পরিসংখ্যান বের করা"""
    if not data_list:
        return None

    total_signals = len(data_list)
    total_capital = sum(item['capital'] for item in data_list)
    total_risk = sum(item['capital'] * item['risk'] for item in data_list)
    avg_rrr = sum(calculate_rrr(item) for item in data_list) / total_signals
    avg_profit_percent = sum(calculate_profit_percentage(item) for item in data_list) / total_signals

    # সিম্বল অনুযায়ী গ্রুপিং
    symbols = {}
    for item in data_list:
        sym = item['symbol']
        if sym not in symbols:
            symbols[sym] = {'count': 0, 'total_capital': 0, 'total_profit_percent': 0}
        symbols[sym]['count'] += 1
        symbols[sym]['total_capital'] += item['capital']
        symbols[sym]['total_profit_percent'] += calculate_profit_percentage(item)

    return {
        'total_signals': total_signals,
        'total_capital': total_capital,
        'total_risk': total_risk,
        'avg_rrr': avg_rrr,
        'avg_profit_percent': avg_profit_percent,
        'symbols': symbols
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড হ্যান্ডলার"""
    user = update.effective_user

    # মূল মেনুর বাটন
    keyboard = [
        [
            InlineKeyboardButton("📋 লিস্ট দেখুন", callback_data="menu_list"),
            InlineKeyboardButton("📊 পরিসংখ্যান", callback_data="menu_stats")
        ],
        [
            InlineKeyboardButton("📥 এক্সপোর্ট", callback_data="menu_export"),
            InlineKeyboardButton("❓ সাহায্য", callback_data="menu_help")
        ],
        [
            InlineKeyboardButton("🗑 সব মুছুন", callback_data="menu_delete_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

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
╚════════════════════════════╝

নিচের বাটন ব্যবহার করুন:"""

    await update.message.reply_text(text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help কমান্ড হ্যান্ডলার"""
    keyboard = [
        [
            InlineKeyboardButton("📋 ফরম্যাট", callback_data="help_format"),
            InlineKeyboardButton("📊 ক্যালকুলেশন", callback_data="help_calc")
        ],
        [
            InlineKeyboardButton("🎯 কমান্ড", callback_data="help_commands"),
            InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """📝 **সাহায্য ও নির্দেশিকা**

নিচের বিষয়গুলো সম্পর্কে জানতে বাটনে ক্লিক করুন:"""

    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

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

        # অ্যাকশন বাটন
        keyboard = [[
            InlineKeyboardButton("📋 সব লিস্ট", callback_data="menu_list"),
            InlineKeyboardButton("➕ আরো যোগ", callback_data="add_more")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ **সিগন্যাল সংরক্ষিত!**\n{signal_box}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            """❌ **ভুল ফরম্যাট!**

সঠিক ফরম্যাট:
`aaa 500000 0.01 30 29 39`

সাহায্যের জন্য /help ব্যবহার করুন""",
            parse_mode='Markdown'
        )

async def list_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কম্প্যাক্ট টেবিল ভিউ"""
    user_id = str(update.effective_user.id)
    all_data = load_data()

    if user_id not in all_data or not all_data[user_id]:
        await update.message.reply_text('📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।')
        return

    sorted_data = sorted(
        all_data[user_id], 
        key=lambda x: calculate_rrr(x), 
        reverse=True
    )

    table = create_compact_table(sorted_data)

    keyboard = [
        [
            InlineKeyboardButton("📊 বিস্তারিত", callback_data="show_detailed"),
            InlineKeyboardButton("📥 এক্সপোর্ট", callback_data="menu_export")
        ],
        [
            InlineKeyboardButton("📈 পরিসংখ্যান", callback_data="menu_stats"),
            InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📋 **কম্প্যাক্ট ভিউ (RRR বেশি আগে):**\n\n{table}",
        parse_mode='Markdown',
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

    keyboard = [[InlineKeyboardButton("🔙 কম্প্যাক্ট ভিউ", callback_data="menu_list")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📊 **বিস্তারিত ভিউ:**\n\n{table}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """পরিসংখ্যান দেখানো"""
    user_id = str(update.effective_user.id)
    all_data = load_data()

    if user_id not in all_data or not all_data[user_id]:
        await update.message.reply_text('📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।')
        return

    stats = get_statistics(all_data[user_id])

    text = f"""📊 **আপনার পরিসংখ্যান**

╔════════════════════════════════╗
║ মোট সিগন্যাল: {stats['total_signals']:<18} ║
║ মোট ক্যাপিটাল: {stats['total_capital']:>12,.0f} BDT   ║
║ মোট রিস্ক: {stats['total_risk']:>12,.0f} BDT      ║
║ গড় RRR: {stats['avg_rrr']:>14.2f}            ║
║ গড় প্রফিট%: {stats['avg_profit_percent']:>11.2f}%         ║
╚════════════════════════════════╝

**সিম্বল অনুযায়ী:**
"""

    for sym, data in stats['symbols'].items():
        avg_profit = data['total_profit_percent'] / data['count']
        text += f"• {sym}: {data['count']} টি (টোটাল {data['total_capital']:,.0f} BDT, গড় প্রফিট {avg_profit:.1f}%)\n"

    keyboard = [[
        InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup)

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ডাটা CSV ফরম্যাটে এক্সপোর্ট"""
    user_id = str(update.effective_user.id)
    all_data = load_data()

    if user_id not in all_data or not all_data[user_id]:
        await update.message.reply_text('📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।')
        return

    # CSV ফাইল তৈরি
    output = io.StringIO()
    writer = csv.writer(output)

    # হেডার
    writer.writerow(['Symbol', 'Capital', 'Risk%', 'Buy', 'SL', 'TP', 'RRR', 'Diff', 'Profit%', 'Loss%', 'Position', 'Exposure', 'Risk Amount', 'Profit Amount', 'Loss Amount', 'Timestamp'])

    # ডাটা
    for item in all_data[user_id]:
        pl = calculate_profit_loss(item)
        writer.writerow([
            item['symbol'],
            item['capital'],
            item['risk']*100,
            item['buy'],
            item['sl'],
            item['tp'],
            calculate_rrr(item),
            calculate_diff(item),
            calculate_profit_percentage(item),
            calculate_loss_percentage(item),
            calculate_position(item),
            calculate_exposure(item),
            calculate_risk_amount(item),
            pl['profit'],
            pl['loss'],
            item['timestamp'][:10]
        ])

    csv_data = output.getvalue()
    output.close()

    # ফাইল হিসেবে পাঠানো
    await update.message.reply_document(
        document=io.BytesIO(csv_data.encode()),
        filename=f"signals_{datetime.now().strftime('%Y%m%d')}.csv",
        caption="📥 আপনার সিগন্যাল এক্সপোর্ট করা হলো"
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

    # মেনু হ্যান্ডলিং
    if query.data == "back_to_main":
        keyboard = [
            [
                InlineKeyboardButton("📋 লিস্ট দেখুন", callback_data="menu_list"),
                InlineKeyboardButton("📊 পরিসংখ্যান", callback_data="menu_stats")
            ],
            [
                InlineKeyboardButton("📥 এক্সপোর্ট", callback_data="menu_export"),
                InlineKeyboardButton("❓ সাহায্য", callback_data="menu_help")
            ],
            [
                InlineKeyboardButton("🗑 সব মুছুন", callback_data="menu_delete_all")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔙 **মূল মেনুতে ফিরে আসুন**\n\nনিচের বাটন ব্যবহার করুন:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return

    elif query.data == "menu_list":
        if user_id not in all_data or not all_data[user_id]:
            await query.edit_message_text("📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।")
            return

        sorted_data = sorted(
            all_data[user_id], 
            key=lambda x: calculate_rrr(x), 
            reverse=True
        )

        table = create_compact_table(sorted_data)

        keyboard = [
            [
                InlineKeyboardButton("📊 বিস্তারিত", callback_data="show_detailed"),
                InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"📋 **কম্প্যাক্ট ভিউ:**\n\n{table}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return

    elif query.data == "menu_stats":
        if user_id not in all_data or not all_data[user_id]:
            await query.edit_message_text("📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।")
            return

        stats = get_statistics(all_data[user_id])

        text = f"""📊 **আপনার পরিসংখ্যান**

╔════════════════════════════════╗
║ মোট সিগন্যাল: {stats['total_signals']:<18} ║
║ মোট ক্যাপিটাল: {stats['total_capital']:>12,.0f} BDT   ║
║ মোট রিস্ক: {stats['total_risk']:>12,.0f} BDT      ║
║ গড় RRR: {stats['avg_rrr']:>14.2f}            ║
║ গড় প্রফিট%: {stats['avg_profit_percent']:>11.2f}%         ║
╚════════════════════════════════╝

**সিম্বল অনুযায়ী:**\n"""

        for sym, data in stats['symbols'].items():
            avg_profit = data['total_profit_percent'] / data['count']
            text += f"• {sym}: {data['count']} টি (টোটাল {data['total_capital']:,.0f} BDT, গড় প্রফিট {avg_profit:.1f}%)\n"

        keyboard = [[InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup)
        return

    elif query.data == "menu_export":
        # এক্সপোর্ট অপশন
        keyboard = [
            [
                InlineKeyboardButton("📥 CSV ফাইল", callback_data="export_csv"),
            ],
            [InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📥 **এক্সপোর্ট ফরম্যাট নির্বাচন করুন:**",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return

    elif query.data == "export_csv":
        await query.edit_message_text("📥 CSV ফাইল তৈরি হচ্ছে... এক মুহূর্ত অপেক্ষা করুন।")

        if user_id in all_data and all_data[user_id]:
            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow(['Symbol', 'Capital', 'Risk%', 'Buy', 'SL', 'TP', 'RRR', 'Diff', 'Profit%', 'Loss%', 'Position', 'Exposure', 'Risk Amount', 'Profit Amount', 'Loss Amount'])

            for item in all_data[user_id]:
                pl = calculate_profit_loss(item)
                writer.writerow([
                    item['symbol'],
                    item['capital'],
                    item['risk']*100,
                    item['buy'],
                    item['sl'],
                    item['tp'],
                    calculate_rrr(item),
                    calculate_diff(item),
                    calculate_profit_percentage(item),
                    calculate_loss_percentage(item),
                    calculate_position(item),
                    calculate_exposure(item),
                    calculate_risk_amount(item),
                    pl['profit'],
                    pl['loss']
                ])

            csv_data = output.getvalue()
            output.close()

            await context.bot.send_document(
                chat_id=user_id,
                document=io.BytesIO(csv_data.encode()),
                filename=f"signals_{datetime.now().strftime('%Y%m%d')}.csv",
                caption="📥 আপনার সিগন্যাল এক্সপোর্ট করা হলো"
            )
        return

    elif query.data == "menu_help":
        keyboard = [
            [
                InlineKeyboardButton("📋 ফরম্যাট", callback_data="help_format"),
                InlineKeyboardButton("📊 ক্যালকুলেশন", callback_data="help_calc")
            ],
            [
                InlineKeyboardButton("🎯 কমান্ড", callback_data="help_commands"),
                InlineKeyboardButton("🔙 মূল মেনু", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📝 **সাহায্য ও নির্দেশিকা**\n\nনিচের বিষয়গুলো সম্পর্কে জানতে বাটনে ক্লিক করুন:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return

    elif query.data == "menu_delete_all":
        # কনফার্মেশন বাটন
        keyboard = [
            [
                InlineKeyboardButton("✅ হ্যাঁ, মুছুন", callback_data="confirm_delete"),
                InlineKeyboardButton("❌ না, বাতিল", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⚠️ **আপনি কি নিশ্চিত?**\n\nআপনার সব ডাটা চিরতরে মুছে যাবে!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return

    elif query.data == "confirm_delete":
        if user_id in all_data:
            del all_data[user_id]
            save_data(all_data)
            await query.edit_message_text("✅ সব ডাটা মুছে ফেলা হয়েছে।")
        return

    elif query.data == "show_detailed":
        if user_id not in all_data or not all_data[user_id]:
            await query.edit_message_text("📭 আপনার কোনো সংরক্ষিত সিগন্যাল নেই।")
            return

        sorted_data = sorted(
            all_data[user_id], 
            key=lambda x: calculate_rrr(x), 
            reverse=True
        )

        table = create_table_view(sorted_data)

        keyboard = [[InlineKeyboardButton("🔙 কম্প্যাক্ট ভিউ", callback_data="menu_list")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"📊 **বিস্তারিত ভিউ:**\n\n{table}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return

    elif query.data == "add_more":
        await query.edit_message_text(
            "➕ নতুন সিগন্যাল পাঠান:\n\nফরম্যাট: `সিম্বল ক্যাপিটাল রিস্ক বাই এসএল টিপি`\nযেমন: `aaa 500000 0.01 30 29 39`",
            parse_mode='Markdown'
        )
        return

    # হেল্প সাব-মেনু
    elif query.data == "help_format":
        await query.edit_message_text(
            """📋 **ফরম্যাট ব্যাখ্যা**

`aaa 500000 0.01 30 29 39`

• **aaa** - স্টক সিম্বল (যেকোনো নাম)
• **500000** - মূলধন (টাকায়)
• **0.01** - রিস্ক পার্সেন্টেজ (1%)
• **30** - বাই প্রাইস
• **29** - স্টপ লস (SL)
• **39** - টার্গেট প্রাইস (TP)

**আউটপুটে দেখাবে:**
• প্রফিট/লস অ্যামাউন্ট (টাকায়)
• প্রফিট/লস পার্সেন্টেজ
• RRR, ডিফ, পজিশন, এক্সপোজার""",
            parse_mode='Markdown'
        )
        return

    elif query.data == "help_calc":
        await query.edit_message_text(
            """📊 **ক্যালকুলেশন ফর্মুলা**

• **RRR** = (TP - Buy) / (Buy - SL)
• **পজিশন** = (ক্যাপিটাল × রিস্ক) / (Buy - SL)
• **এক্সপোজার** = পজিশন × Buy
• **রিস্ক অ্যামাউন্ট** = ক্যাপিটাল × রিস্ক
• **প্রফিট অ্যামাউন্ট** = (TP - Buy) × পজিশন
• **লস অ্যামাউন্ট** = (Buy - SL) × পজিশন
• **প্রফিট%** = ((TP - Buy) / Buy) × 100
• **লস%** = ((Buy - SL) / Buy) × 100""",
            parse_mode='Markdown'
        )
        return

    elif query.data == "help_commands":
        await query.edit_message_text(
            """🎯 **কমান্ড লিস্ট**

/start - বট শুরু করুন
/help - সাহায্য দেখুন
/list - কম্প্যাক্ট ভিউ দেখুন
/listall - বিস্তারিত ভিউ দেখুন
/stats - পরিসংখ্যান দেখুন
/export - ডাটা এক্সপোর্ট করুন
/delete - সব ডাটা মুছুন""",
            parse_mode='Markdown'
        )
        return

async def post_init(application: Application):
    """বট চালু হওয়ার পর কমান্ড সেট করা"""
    commands = [
        BotCommand("start", "বট শুরু করুন"),
        BotCommand("help", "সাহায্য দেখুন"),
        BotCommand("list", "কম্প্যাক্ট ভিউ দেখুন"),
        BotCommand("listall", "বিস্তারিত ভিউ দেখুন"),
        BotCommand("stats", "পরিসংখ্যান দেখুন"),
        BotCommand("export", "ডাটা এক্সপোর্ট করুন"),
        BotCommand("delete", "সব ডাটা মুছুন")
    ]
    await application.bot.set_my_commands(commands)

async def main():
    """মেইন ফাংশন"""
    logger.info("🤖 বট চালু হচ্ছে...")

    try:
        # Flask সার্ভার আলাদা থ্রেডে চালু করুন
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("🌐 HTTP সার্ভার থ্রেড চালু হয়েছে")

        # অ্যাপ্লিকেশন তৈরি
        application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

        # কমান্ড হ্যান্ডলার
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("list", list_data))
        application.add_handler(CommandHandler("listall", list_all_data))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("export", export_data))
        application.add_handler(CommandHandler("delete", delete_all))

        # মেসেজ হ্যান্ডলার
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # কলব্যাক হ্যান্ডলার
        application.add_handler(CallbackQueryHandler(button_callback))

        logger.info("✅ বট সফলভাবে চালু হয়েছে!")

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