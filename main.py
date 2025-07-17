from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
# import yfinance as yf
from moexalgo import Ticker
from datetime import date, datetime, timedelta
# import matplotlib.dates as mdates
from io import BytesIO
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os
import locale
import pandas as pd
from mplfinance.original_flavor import candlestick_ohlc
import numpy as np

locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')

def clear_cache(context, pattern='chart_'):
    """Удаляет все ключи, начинающиеся с pattern"""
    keys = [k for k in context.user_data if k.startswith(pattern)]
    for k in keys:
        context.user_data.pop(k, None)

def times_line_message(start, end, delta):
    if delta >= 1:
        return f'{start.strftime('%d.%m.%y')} - {end.strftime('%d.%m.%y')}'
    else:
        return f'{start.strftime('%d.%m.%y')}'

def get_available_frequencies(n_days: int) -> list[str]:
    if n_days == 0:
        n_days = 1
    frequency_rules = [
        ("1 min", 1, 3),
        ("10 min", 1, 30),
        ("1 hour", 1, 180),
        ("1 day", 30, 4000),
        ("1 week", 210, 8400),
        ("1 month", 672, 8400)
    ]
    return [code for code, min_d, max_d in frequency_rules if min_d <= n_days <= max_d]

def plural_day_ru(n):
    n = abs(n) % 100
    n1 = n % 10

    if 11 <= n <= 19:
        return "дней"
    elif n1 == 1:
        return "день"
    elif 2 <= n1 <= 4:
        return "дня"
    else:
        return "дней"

def type_gap_to_ru(s):
    dict_type_to_rus = {
        '1min': 'минутный',
        '10min': '10-минутный',
        '1h': 'часовой',
        '1d': 'дневной',
        '1w': 'недельный',
        '1m': 'месячный',
    }
    return dict_type_to_rus[s]

def format_days_human(n_days):
    if n_days >= 365 * 2:
        years = n_days // 365
        return f"{years} {'года' if 2 <= years <= 4 else 'лет'}"
    elif n_days >= 60:
        months = n_days // 30
        return f"{months} {'месяца' if 2 <= months <= 4 else 'месяцев'}"
    elif n_days >= 7:
        weeks = n_days // 7
        return f"{weeks} {'недели' if 2 <= weeks <= 4 else 'недель'}"
    elif n_days == 0:
        return "1 день"
    else:
        return f"{n_days} {'день' if n_days == 1 else 'дня' if 2 <= n_days <= 4 else 'дней'}"

def converter_to_heikin_ashi_dataframe(df):
    open_, high, low, close = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    n = len(df)
    ha_open = np.empty(n)
    ha_close = (open_ + high + low + close) / 4

    ha_open[0] = (open_[0] + close[0]) / 2
    for i in range(1, n):
        ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2

    ha_high = np.maximum.reduce([high, ha_open, ha_close])
    ha_low = np.minimum.reduce([low, ha_open, ha_close])

    ha_df = pd.DataFrame({
        'begin': df['begin'],
        'open': ha_open,
        'high': ha_high,
        'low': ha_low,
        'close': ha_close
    })
    return ha_df

def paint_plot(df, ticker, start_date, end_date, date_type, date_delta, chart_type='line'):
    # плавающие гиперпараметры
    len_x = 15
    days = plural_day_ru(date_delta)
    gap_type = type_gap_to_ru(date_type)
    if date_delta >= 1:
        part_header_time_gap = f'{start_date.strftime('%d.%m.%y')} - {end_date.strftime('%d.%m.%y')}'
    else:
        part_header_time_gap = f'{start_date.strftime('%d.%m.%y')}'

    if date_delta <= 3:
        x_date_format = '%d.%m %H:%M'
    elif date_delta <= 90:
        x_date_format = '%d.%m.%y'
    else:
        x_date_format = '%b %Y'

    df['begin'] = pd.to_datetime(df['begin'])

    df['x'] = range(len(df))

    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['font.family'] = 'Times New Roman'
    fig, ax = plt.subplots(figsize=(len_x, 7))


    if chart_type == 'line':
        # плавающие гиперпараметры (line)
        if len(df) >= 500:
            linewidth = 1.7
        elif len(df) >= 1000:
            linewidth = 1.3
        elif len(df) >= 2000:
            linewidth = 1.1
        elif len(df) >= 4000:
            linewidth = 0.9
        else:
            linewidth = 2

        # x = list(range(len(df)))
        x = df['x'].values
        y = df['open'].values

        # Основной график
        ax.plot(x, y,
                linewidth=linewidth,
                color="#3d69b7",
                label='Цена открытия')
        ax.legend(fontsize=12)

    elif chart_type == 'candles':
        quotes = df[['x', 'open', 'high', 'low', 'close']].astype(float).values
        candlestick_ohlc(ax, quotes, width=0.6,
                        colorup='green', colordown='red', alpha=0.8)
    
    elif chart_type == 'heiken-ashi':
        ha_df = converter_to_heikin_ashi_dataframe(df)
        ha_df['x'] = range(len(ha_df))
        quotes = ha_df[['x', 'open', 'high', 'low', 'close']].astype(float).values
        candlestick_ohlc(ax, quotes, width=0.6,
                         colorup='green', colordown='red', alpha=0.8)


    ax.set_title(f'{ticker} | {part_header_time_gap} | {format_days_human(date_delta)} ({len(df)} точек) | Последняя цена: {df.iloc[-1]["close"]:.1f}₽',
                fontsize=20, pad=20, fontweight='bold')
    ax.set_xlabel('Дата', fontsize=16)
    ax.set_ylabel('Цена (₽)', fontsize=16)

    # Отображаем подписи дат на оси X с шагом
    step_x = max(len(df) // 10, 1)
    xticks = df['x'][::step_x]
    xticklabels = df['begin'].dt.strftime(x_date_format)[::step_x]

    ax.grid(True, alpha=0.4)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=45)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    buf.seek(0)
    plt.close()


    return buf

def get_chart_type_keyboard(current_type):
    types = {
        'line': '📈 Линия',
        'candles': '🕯 Свечи'
    }

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✅ ' if t == current_type else ''}{label}",
                callback_data=f'set_chart_type:{t}'
            )
            for t, label in types.items()
        ],
        [InlineKeyboardButton(f"{'✅ ' if 'heiken-ashi' == current_type else ''}🌀 Хейкен-Аши", callback_data='set_chart_type:heiken-ashi')]
        # [InlineKeyboardButton('✅ 🌀 Хейкен-Аши' if current_type=='heiken_ashi' else '🌀 Хейкен-Аши', callback_data='set_chart_type:heiken-ashi')]
        # [InlineKeyboardButton("🔙 Назад", callback_data='go_back')]
    ]
    return InlineKeyboardMarkup(keyboard)



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
        [InlineKeyboardButton('📝 Ввести тикер вручную', callback_data='manual_ticker_input')],
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
    
async def handle_text(update, context):
    input_query = context.user_data.get('awaiting_input_type')

    if input_query == 'ticker':
        ticker = update.message.text.strip().upper()
        try:
            Ticker(ticker)
            context.user_data['ticker'] = ticker
            context.user_data.pop("awaiting_input_type", None)
            await period_menu(update, context)
        except Exception as e:
            await update.message.reply_text(f'❌ Ошибка: {str(e)}.\nПроверьте тикер и попробуйте ещё раз')
    
    elif input_query == 'date_range':
        text = update.message.text.strip()
        try:
            if len(text.split('-')) == 2:
                start_str, end_str = text.split('-')
            else:
                start_str, end_str = text, text
            start_date = datetime.strptime(start_str.strip(), '%d.%m.%Y').date()
            end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").date()

            if start_date > end_date:
                await update.message.reply_text("❌ Начальная дата позже конечной.")
                return
            
            context.user_data["start_end_dates"] = (start_date, end_date)
            context.user_data.pop("awaiting_input_type", None)

            await time_gap_menu(update, context, get_available_frequencies((end_date - start_date).days))

        except Exception as e:
            await update.message.reply_text(f'❌ Ошибка: {str(e)}.\nНеверный формат. Попробуй: 01.01.2024 - 10.01.2024')
    else:
        await update.message.reply_text("🤔 Не понимаю. Нажмите кнопку для ввода.")

# Обработчики для ручного ввода
async def manual_ticker_input(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text('✏️ Введите тикер (например: LKOH, TATN):',
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton('🔙 Назад', callback_data='go_back')]]
                                  ))
    
    context.user_data["awaiting_input_type"] = "ticker"

    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'manual_ticker_input':
        stack.append('manual_ticker_input')

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
    query = update.callback_query
    await query.answer()
    ticker = query.data.replace('ticker_', '')
    context.user_data['ticker'] = ticker
    await period_menu(update, context)

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
        [InlineKeyboardButton('📊 5 лет', callback_data='period_5years')],
        [InlineKeyboardButton('📝 Ввести произвольный период', callback_data='manual_dates_input')]
    ]

    keyboard_period.append([InlineKeyboardButton('🔙 Назад', callback_data='go_back')])
    await edit_message(
        f"⏳ Выберите период для {context.user_data.get('ticker', '')}:",
        reply_markup=InlineKeyboardMarkup(keyboard_period)
    )
    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'period_menu':
        stack.append('period_menu')

async def manual_dates_input(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text('✏️ Введите даты (дату) в формате: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ (ДД.ММ.ГГГГ)',
                                reply_markup=InlineKeyboardMarkup(
                                    [[InlineKeyboardButton('🔙 Назад', callback_data='go_back')]]
                                ))
    context.user_data["awaiting_input_type"] = "date_range"

    stack = context.user_data.setdefault('history_steps', [])
    if not stack or stack[-1] != 'manual_dates_input':
        stack.append('manual_dates_input')

async def handle_period(update, context):
    query = update.callback_query
    await query.answer()
    period = query.data.replace('period_', '')

    end_date = date.today()
    if period == '1day':
        start_date = end_date - timedelta(days=1)
        time_gap_correct_buttons = ['1 min', '10 min', '1 hour']
    elif period == '1month':
        start_date = end_date - timedelta(days=30)
        time_gap_correct_buttons = ['10 min', '1 hour', '1 day']
    elif period == '1year':
        start_date = end_date - timedelta(days=365)
        time_gap_correct_buttons = ['1 hour', '1 day', '1 week']
    elif period == '5years':
        start_date = end_date - timedelta(days=5*365)
        time_gap_correct_buttons = ['1 day', '1 week', '1 month']

    
    context.user_data['start_end_dates'] = (start_date, end_date)
    context.user_data['period'] = period
    
    await time_gap_menu(update, context, time_gap_correct_buttons)

async def time_gap_menu(update, context, list_of_buttons=None):
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        edit_message = query.edit_message_text
    else:
        edit_message = update.message.reply_text

    time_gap_buttons = {'1 min': [InlineKeyboardButton('📅 1 минута', callback_data='time_gap:1min')],
                        '10 min': [InlineKeyboardButton('📅 10 минут', callback_data='time_gap:10min')],
                        '1 hour': [InlineKeyboardButton('📅 1 час', callback_data='time_gap:1h')],
                        '1 day': [InlineKeyboardButton('📅 1 день', callback_data='time_gap:1d')],
                        '1 week': [InlineKeyboardButton('📅 1 неделя', callback_data='time_gap:1w')],
                        '1 month': [InlineKeyboardButton('📅 1 месяц', callback_data='time_gap:1m')]
                        }

    keyboard_time_gap = [time_gap_buttons[time_gap] for time_gap in list_of_buttons] if list_of_buttons else list(time_gap_buttons.values())
    keyboard_time_gap.append([InlineKeyboardButton('🔙 Назад', callback_data='go_back')])

    await edit_message(
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

async def handler_chart_type_change(update, context):
    query = update.callback_query
    await query.answer()

    chart_type = query.data.replace("set_chart_type:", "")
    context.user_data["chart_type"] = chart_type

    params = context.user_data.get('plot_params')
    # Проверяем кеш
    cache_key = f'chart_{chart_type}'
    if cache_key in context.user_data:
        buf = BytesIO(context.user_data[cache_key])

    else:
        data = context.user_data.get('data')
        buf = paint_plot(
            data,
            ticker=params['ticker'],
            start_date=params['start_date'],
            end_date=params['end_date'],
            date_type=params['date_type'],
            date_delta=params['date_delta'],
            chart_type=chart_type
        )
        context.user_data[cache_key] = buf.getvalue()  # Сохраняем в кеш

    await query.message.edit_media(
        media=InputMediaPhoto(
            media=buf,
            caption=params['caption']
        ),
        reply_markup=get_chart_type_keyboard(chart_type)
    )
    buf.close()

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
    
    date_delta = (end_date - start_date).days
    
    message_line = times_line_message(start_date, end_date, date_delta)
        
    if data.empty:
        await query.message.reply_text(
            f"⚠️ По тикеру {ticker} нет данных в период {message_line}.\n"
            f"Предположительно в данный период биржа не работала. Попробуйте изменить период."
        )
        # stack = context.user_data.get('history_steps', [])
        # if stack:
        #     stack.pop()
        await handle_back(update, context)
        return
    
    # Фактические доступные даты
    actual_start = data['begin'].min().date()
    actual_end = data['begin'].max().date()

    # Уведомление, если вводимый период ≠ фактический
    warning = ""
    if start_date < actual_start - timedelta(30) or actual_end + timedelta(30) < end_date:
        warning = (
            f"⚠️ Данные доступны только за период: {actual_start.strftime('%d.%m.%y')} - {actual_end.strftime('%d.%m.%y')}.\n"
            f"(Вы указали: {message_line})\n\n"
        )
        start_date, end_date = actual_start, actual_end
        date_delta = (actual_end - actual_start).days
        message_line = times_line_message(start_date, end_date, date_delta)

    # Чистим кеш
    clear_cache(context)

    buf = paint_plot(data, ticker, start_date, end_date, time_gap, date_delta)

    date_delta = date_delta or 1

    caption = warning + (
                f"📊 График {ticker} за {message_line} ({date_delta} {plural_day_ru(date_delta)})\n"
                f"📏 Частота данных: {type_gap_to_ru(time_gap)} формат\n"
                f"🔄 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    context.user_data['data'] = data
    context.user_data['plot_params'] = {
    'ticker': ticker,
    'start_date': start_date,
    'end_date': end_date,
    'date_type': time_gap,
    'date_delta': date_delta,
    'caption': caption
    }
    context.user_data['chart_type'] = 'line'


    if len(data) <= 220:
        await query.message.reply_photo(
            photo=buf,
            caption=caption,
            reply_markup=get_chart_type_keyboard(context.user_data['chart_type'])
        )
    else:
        await query.message.reply_photo(
            photo=buf,
            caption=caption
        )
    buf.close()

def main():
    load_dotenv()
    FINANCE_BOT_TOKEN = os.getenv("FINANCE_BOT_TOKEN")
    
    application = Application.builder().token(FINANCE_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_back, pattern='^go_back$'))
    application.add_handler(CallbackQueryHandler(manual_ticker_input, pattern='^manual_ticker_input$'))
    application.add_handler(CallbackQueryHandler(company_list, pattern='^company_list$'))
    application.add_handler(CallbackQueryHandler(manual_dates_input, pattern='^manual_dates_input$'))
    application.add_handler(CallbackQueryHandler(handle_ticker, pattern='^ticker_'))
    application.add_handler(CallbackQueryHandler(handle_period, pattern='^period_'))
    application.add_handler(CallbackQueryHandler(handle_time_gap, pattern='^time_gap:'))
    application.add_handler(CallbackQueryHandler(handler_chart_type_change, pattern='^set_chart_type:'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    application.run_polling()

if __name__ == "__main__":
    main()

