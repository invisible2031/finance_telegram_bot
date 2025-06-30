from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import yfinance as yf
from moexalgo import Ticker
from datetime import date, time, datetime, timedelta
import matplotlib.dates as mdates
from io import BytesIO
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os


def paint_plot(df, ticker, date_delta=30):

    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['font.family'] = 'Times New Roman'

    fig, ax = plt.subplots(figsize=(15, 7))
    ax.plot(
        df['begin'], 
        df['open'], 
        marker='o', 
        markersize=5,
        linewidth=2,
        color="#49ac72",
        label='Цена открытия'
    )

    # Настройки
    ax.set_title(f'{ticker} | {date_delta} дней ({len(df)} рабочих дней) | Последняя цена: {df.iloc[-1, 2]:.2f}₽',
                    fontsize=14, pad=20, fontweight='bold')
    ax.set_xlabel('Дата', fontsize=14)
    ax.set_ylabel('Цена (₽)', fontsize=14)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.4)

    # Форматирование дат
    ax.xaxis.set_major_formatter(
        plt.matplotlib.dates.DateFormatter('%d.%m.%Y')
    )
    plt.xticks(rotation=45)

    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    return buf

# Функция для обработки кнопки "Назад"
async def handle_back(update, context):
    query = update.callback_query
    await query.answer()

    stack = context.user_data.get('history_steps', [])

    if stack:
        stack.pop()
        previous_step = stack[-1] if stack else 'start'
        
    target_func = globals().get(previous_step)
    await target_func(update, context)

# Главное меню бота
async def start(update, context):
    keyboard_menu = [
        [InlineKeyboardButton('📝 Ввести тикер вручную', callback_data='manual_input')],
        [InlineKeyboardButton('🏦 Выбрать из списка', callback_data='company_list')]
    ]

    if hasattr(update, 'message') and update.message:
        message = update.message
        await message.reply_text("📊 Выберите способ:",
                                 reply_markup=InlineKeyboardMarkup(keyboard_menu)
                                 )
    else:
        query = update.callback_query
        await query.edit_message_text("📊 Выберите способ:",
                                 reply_markup=InlineKeyboardMarkup(keyboard_menu)
                                 )
    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'start':
        stack.append('start')
    

# Обработчик для ручного ввода тикера
async def manual_input(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text('✏️ Введите тикер (например: LKOH, TATN):',
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton('🔙 Назад', callback_data='go_back')]]
                                  ))
    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'manual_input':
        stack.append('manual_input')

# Меню компаний (3 кнопки)
async def company_list(update, context):
    query = update.callback_query
    await query.answer()

    companies = [
        ['Сбербанк', 'SBER'],
        ['Газпром', 'GAZP'],
        ['Новатэк', 'NVTK']
    ]

    keyboard_select_companies = [[InlineKeyboardButton(name, callback_data=f'ticker_{ticker}')] for name, ticker in companies]
    keyboard_select_companies.append([InlineKeyboardButton('🔙 Назад', callback_data='go_back')])  # Добавляем кнопку "Назад"
    await query.edit_message_text(
        '🔍 Выберите компанию:',
        reply_markup=InlineKeyboardMarkup(keyboard_select_companies)
    )
    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'company_list':
        stack.append('company_list')

async def handle_ticker(update, context):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        ticker = query.data.replace('ticker_', '')
        message = query.message
    else:
        ticker = update.message.text.strip().upper()
        message = update.message

    try:
        Ticker(ticker)
        context.user_data['ticker'] = ticker
        await period_menu(update, context)

    except Exception as e:
        await message.reply_text(f'❌ Ошибка: {str(e)}.\nПроверьте тикер и попробуйте ещё раз')


async def period_menu(update, context):
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        edit_message = query.edit_message_text
    else:
        edit_message = update.message.reply_text

    keyboard_period = [
        [InlineKeyboardButton('📅 1 день', callback_data='period_1day')],
        [InlineKeyboardButton('📆 1 месяц', callback_data='period_1month')],
        [InlineKeyboardButton('📅 1 год', callback_data='period_1year')],
        [InlineKeyboardButton('📊 5 лет', callback_data='period_5years')]
    ]

    keyboard_period.append([InlineKeyboardButton('🔙 Назад', callback_data='go_back')])
    await edit_message(
        f"⏳ Выберите период для {context.user_data.get('ticker', '')}:",
        reply_markup=InlineKeyboardMarkup(keyboard_period)
    )
    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'period_menu':
        stack.append('period_menu')


async def handle_period(update, context):
    query = update.callback_query
    await query.answer()
    period = query.data.replace('period_', '')

    end_date = date.today()
    if period == '1day':
        start_date = end_date - timedelta(days=1)
        time_gap_correct_buttons = ['10 min', '1 hour']
    elif period == '1month':
        start_date = end_date - timedelta(days=30)
        time_gap_correct_buttons = ['1 day']
    elif period == '1year':
        start_date = end_date - timedelta(days=365)
        time_gap_correct_buttons = ['1 day', '1 week']
    elif period == '5years':
        start_date = end_date - timedelta(days=5*365)
        time_gap_correct_buttons = ['1 week', '1 month']

    
    context.user_data['start_end_dates'] = (start_date, end_date)
    context.user_data['period'] = period
    
    await time_gap_menu(update, context, time_gap_correct_buttons)


async def time_gap_menu(update, context, list_of_buttons=None):
    query = update.callback_query
    await query.answer()

    time_gap_buttons = {'1 min': [InlineKeyboardButton('📅 1 минута', callback_data='time_gap:1min')],
                        '10 min': [InlineKeyboardButton('📅 10 минут', callback_data='time_gap:10min')],
                        '1 hour': [InlineKeyboardButton('📅 1 час', callback_data='time_gap:1h')],
                        '1 day': [InlineKeyboardButton('📅 1 день', callback_data='time_gap:1d')],
                        '1 week': [InlineKeyboardButton('📅 1 неделя', callback_data='time_gap:1w')],
                        '1 month': [InlineKeyboardButton('📅 1 месяц', callback_data='time_gap:1m')]
                        }

    keyboard_time_gap = [time_gap_buttons[time_gap] for time_gap in list_of_buttons] if list_of_buttons else list(time_gap_buttons.values())
    keyboard_time_gap.append([InlineKeyboardButton('🔙 Назад', callback_data='go_back')])

    await query.edit_message_text(
        '⏳ Выберите временной интервал:',
        reply_markup=InlineKeyboardMarkup(keyboard_time_gap)
    )
    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'time_gap_menu':
        stack.append('time_gap_menu')

async def handle_time_gap(update, context):
    query = update.callback_query
    await query.answer()

    time_gap = query.data.replace('time_gap:', '')
    context.user_data['time_gap'] = time_gap

    await ticker_plot(update, context)


async def ticker_plot(update, context):
    query = update.callback_query
    await query.answer()

    ticker = context.user_data.get('ticker', '')
    start_date, end_date = context.user_data.get('start_end_dates', (date.today() - timedelta(days=30), date.today()))
    time_gap = context.user_data.get('time_gap', '1d')

    # data = Ticker(ticker).candles(start = '2025-06-01', end = date.today())
    # price = data.iloc[-1, 0]
    # await message.reply_text(f"Цена открытия {ticker} ({data.iloc[-1, 7].strftime('%Y-%m-%d')}): {price:.2f} RUB")

    data = Ticker(ticker).candles(start = start_date, end = end_date, period=time_gap)
    buf = paint_plot(data, ticker, (end_date - start_date).days)
    
    await query.message.reply_photo(
        photo=buf,
        caption=f"📊 График {ticker} за {len(data)} дней\n"
                f"🔄 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    buf.close()


def main():
    load_dotenv()
    FINANCE_BOT_TOKEN = os.getenv("FINANCE_BOT_TOKEN")
    
    application = Application.builder().token(FINANCE_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_back, pattern='^go_back$'))
    application.add_handler(CallbackQueryHandler(manual_input, pattern='^manual_input$'))
    application.add_handler(CallbackQueryHandler(company_list, pattern='^company_list$'))
    application.add_handler(CallbackQueryHandler(handle_ticker, pattern='^ticker_'))
    application.add_handler(CallbackQueryHandler(handle_period, pattern='^period_'))
    application.add_handler(CallbackQueryHandler(handle_time_gap, pattern='^time_gap:'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))
    
    application.run_polling()

if __name__ == "__main__":
    main()

