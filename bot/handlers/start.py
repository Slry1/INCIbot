from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters.callback_data import CallbackData
from database.db import get_session
from database.repository import DatabaseRepository

router = Router()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Оценить состав")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="🔍 Как это работает")]
    ],
    resize_keyboard=True
)

agree_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Согласен"), KeyboardButton(text="❌ Отказаться")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


class AgreementCallback(CallbackData, prefix="agree"):
    """Callback для принятия пользовательского соглашения"""
    action: str


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        break

    if user and user.agreement_accepted:
        welcome_text = (
            f"👋 С возвращением, {message.from_user.first_name}!\n\n"
            "Я помогу тебе персонализированно оценить состав косметических средств.\n\n"
            "📌 <b>Что я умею:</b>\n"
            "• Анализировать состав косметики по ссылке, названию или тексту\n"
            "• Учитывать твой тип кожи, аллергены и предпочтения\n"
            "• Находить товары на Wildberries и сразу оценивать их состав\n"
            "• Давать персонализированные рекомендации\n\n"
            "📝 Отправь мне ссылку на товар, название или состав — и я дам оценку!"
        )
        await message.answer(welcome_text, reply_markup=main_keyboard, parse_mode="HTML")
    else:
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я — <b>INCIbot</b>, чат-бот для персонализированной оценки "
            "косметических средств по их составу.\n\n"
            "📌 <b>Мои возможности:</b>\n"
            "🔗 <b>Анализ по ссылке</b> — отправь ссылку на товар с Wildberries, "
            "Ozon или Золотого Яблока\n"
            "🔍 <b>Поиск по названию</b> — напиши название средства, и я найду его\n"
            "📋 <b>Оценка состава</b> — отправь список ингредиентов напрямую\n"
            "👤 <b>Персонализация</b> — учёт твоего типа кожи, аллергенов и предпочтений\n"
            "📊 <b>Умный анализ</b> — использую нейросеть YandexGPT и базу знаний "
            "из 248+ косметических ингредиентов\n\n"
            "⚠️ <b>Важно:</b> перед использованием бота необходимо ознакомиться "
            "и согласиться с условиями обработки персональных данных."
        )
        await message.answer(welcome_text, parse_mode="HTML")
        await show_agreement(message)

async def show_agreement(message: Message):
    """Показывает пользовательское соглашение и запрашивает согласие"""
    agreement_text = (
        "📜 <b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ</b>\n"
        "и согласие на обработку персональных данных\n\n"
        "В соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ "
        "«О персональных данных», для функционирования сервиса "
        "персонализированной оценки косметических средств требуется "
        "обработка следующих данных:\n\n"
        "📋 <b>Обрабатываемые данные:</b>\n"
        "• Идентификатор Telegram (telegram_id)\n"
        "• Имя пользователя (username, first_name)\n"
        "• Тип кожи (опционально, указывается самостоятельно)\n"
        "• Список аллергенов (опционально, указывается самостоятельно)\n"
        "• Предпочтения по косметике (опционально, указывается самостоятельно)\n"
        "• История запросов для персонализации оценок\n\n"
        "🔐 <b>Как используются данные:</b>\n"
        "• Только для формирования персонализированных оценок\n"
        "• Не передаются третьим лицам\n"
        "• Хранятся на серверах на территории РФ (Yandex Cloud)\n"
        "• Вы можете в любой момент удалить свои данные\n\n"
        "⚖️ <b>Ваши права:</b>\n"
        "• Отозвать согласие в любой момент (команда /delete_data)\n"
        "• Использовать сервис без персонализации (без указания типа кожи и аллергенов)\n"
        "• Получить информацию о хранимых данных (команда /my_data)\n\n"
        "🤖 <b>Об использовании ИИ:</b>\n"
        "• Оценки генерируются нейросетью\n"
        "• Оценка носит рекомендательный характер\n"
        "• Не является медицинским заключением\n"
        "• Перед использованием средства рекомендуется патч-тест\n\n"
        "Нажимая «✅ Согласен», вы подтверждаете, что ознакомились "
        "с условиями и даёте согласие на обработку указанных данных."
    )
    await message.answer(agreement_text, reply_markup=agree_keyboard, parse_mode="HTML")


@router.message(F.text == "✅ Согласен")
async def on_agreement_accepted(message: Message):
    """Пользователь принял соглашение"""
    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        await repo.update_agreement(user_id=user.id, accepted=True)
        break

    await message.answer(
        "✅ <b>Спасибо!</b> Соглашение принято.\n\n"
        "Теперь вы можете:\n"
        "📝 <b>Оценить состав</b> — отправьте ссылку, название или состав\n"
        "⚙️ <b>Настроить профиль</b> — укажите тип кожи и аллергены "
        "для персонализированных оценок\n\n"
        "Для настройки профиля нажмите кнопку «⚙️ Настройки» или "
        "сразу отправьте мне состав для оценки!",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )


@router.message(F.text == "❌ Отказаться")
async def on_agreement_declined(message: Message):
    """Пользователь отказался от соглашения"""
    await message.answer(
        "😔 <b>Вы отказались от обработки данных.</b>\n\n"
        "К сожалению, без согласия на обработку персональных данных "
        "функционал бота ограничен — персонализированные оценки "
        "невозможны без информации о типе кожи и аллергенах.\n\n"
        "Вы можете продолжить использование в <b>базовом режиме</b> "
        "без персонализации.\n\n"
        "Если передумаете — нажмите /start для повторного соглашения.",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )

@router.message(Command("agreement"))
async def cmd_agreement(message: Message):
    """Повторный показ пользовательского соглашения"""
    await show_agreement(message)


@router.message(Command("delete_data"))
async def cmd_delete_data(message: Message):
    """Удаление данных пользователя (право на забвение)"""
    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
        )
        if user:
            await repo.delete_user_data(user.id)
        break

    await message.answer(
        "🗑 <b>Ваши данные удалены.</b>\n\n"
        "Удалена следующая информация:\n"
        "• Тип кожи\n"
        "• Список аллергенов\n"
        "• Предпочтения\n"
        "• История запросов\n\n"
        "Ваш идентификатор Telegram сохранён только для учёта отказа от соглашения.\n\n"
        "Чтобы снова использовать персонализацию, нажмите /start.",
        parse_mode="HTML"
    )


@router.message(Command("my_data"))
async def cmd_my_data(message: Message):
    """Показывает данные пользователя, которые хранятся в системе"""
    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(message.from_user.id)
        stats = await repo.get_user_stats(user.id)
        break

    profile_text = (
        "📋 <b>Информация о хранимых данных</b>\n\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"👤 Имя: {user.first_name or 'не указано'}\n"
        f"📅 Первое обращение: {user.first_seen.strftime('%d.%m.%Y %H:%M') if user.first_seen else 'неизвестно'}\n"
        f"🕐 Последняя активность: {user.last_active.strftime('%d.%m.%Y %H:%M') if user.last_active else 'неизвестно'}\n"
        f"🧴 Тип кожи: {user.skin_type or 'не указан'}\n"
        f"⚠️ Аллергены: {', '.join(user.allergens) if user.allergens else 'не указаны'}\n"
        f"⭐️ Предпочтения: {', '.join(user.preferences) if user.preferences else 'не указаны'}\n"
        f"📝 Соглашение принято: {'✅ Да' if user.agreement_accepted else '❌ Нет'}\n"
        f"📊 Всего запросов: {stats.get('total_queries', 0)}\n"
        f"📈 Средняя оценка: {stats.get('avg_score', 0):.1f}/10\n\n"
        "<i>Для удаления данных используйте команду /delete_data</i>\n"
        "<i>Для изменения данных используйте /settings</i>"
    )
    await message.answer(profile_text, parse_mode="HTML")



@router.message(F.text == "❓ Помощь")
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Расширенная справка по использованию бота"""
    help_text = (
        "📖 <b>Как пользоваться INCIbot</b>\n\n"
        "🤖 <b>Я — чат-бот для персонализированной оценки косметики.</b>\n"
        "Анализирую составы с учётом твоего типа кожи и аллергенов.\n\n"
        "📌 <b>Основные действия:</b>\n\n"
        "1️⃣ <b>Оценить состав</b>\n"
        "Отправь мне одно из трёх:\n"
        "• 🔗 <b>Ссылку</b> на товар с Wildberries\n"
        "• 🔍 <b>Название</b> средства — я найду его на Wildberries\n"
        "• 📋 <b>Список ингредиентов</b> через запятую\n\n"
        "2️⃣ <b>Настроить профиль</b> (/settings)\n"
        "Укажи тип кожи, аллергены и предпочтения — это сделает "
        "оценки персонализированными. Если не заполнять профиль, "
        "оценки будут общими.\n\n"
        "3️⃣ <b>Просмотр профиля</b> (/profile)\n"
        "Посмотри свои текущие настройки и статистику.\n\n"
        "📊 <b>Как читать результаты:</b>\n"
        "• 9-10⭐ — отличный состав, подходит идеально\n"
        "• 7-8⭐ — хороший состав с небольшими замечаниями\n"
        "• 5-6⭐ — удовлетворительно, есть нюансы\n"
        "• 3-4⭐ — проблемный состав, лучше избегать\n"
        "• 0-2⭐ — опасный состав или неполные данные\n\n"
        "💡 <b>Советы:</b>\n"
        "• Чем точнее заполнен профиль — тем точнее оценка\n"
        "• Отправляйте полный состав (все ингредиенты через запятую)\n"
        "• Для поиска пишите конкретное название с брендом\n\n"
        "⚠️ <b>Важно:</b> Оценка носит рекомендательный характер "
        "и генерируется нейросетью. Перед использованием нового "
        "средства рекомендуется провести патч-тест."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "🔍 Как это работает")
@router.message(Command("how_it_works"))
async def cmd_how_it_works(message: Message):
    how_it_works_text = (
        "🔍 <b>Как работает INCIbot</b>\n\n"
        "Я анализирую состав косметического средства и даю "
        "персонализированную оценку с учётом вашего типа кожи, "
        "аллергенов и предпочтений.\n\n"

        "📊 <b>Ключевые критерии оценки:</b>\n"
        "• Наличие аллергенов и раздражителей\n"
        "• Комедогенность компонентов (способность забивать поры)\n"
        "• Соответствие вашему типу кожи\n"
        "• Наличие нежелательных консервантов и отдушек\n"
        "• Эффективность увлажняющих и активных компонентов\n"
        "• Порядок ингредиентов (первые 3-5 — основа средства)\n\n"

        "👤 <b>Персонализация:</b>\n"
        "Вы можете настроить профиль через «⚙️ Настройки». "
        "Я буду учитывать ваш тип кожи, аллергены и предпочтения "
        "при каждой оценке. Без заполнения профиля оценка будет "
        "общей, без учёта индивидуальных особенностей.\n\n"

        "📜 <b>Важная информация:</b>\n"
        "• Оценка носит <b>рекомендательный характер</b>\n"
        "• Результат <b>не является медицинским заключением</b>\n"
        "• Точные концентрации компонентов являются коммерческой "
        "тайной производителей и недоступны для анализа\n"
        "• Перед использованием нового средства рекомендуется "
        "провести патч-тест\n\n"

        "🔐 <b>Ваши права:</b>\n"
        "• Вы можете отказаться от персонализации, не заполняя профиль\n"
        "• Вы можете удалить свои данные в любой момент (/delete_data)\n"
        "• Вы можете получить информацию о хранимых данных (/my_data)\n"
        "• Данные хранятся на серверах на территории РФ\n\n"

        "<i>Данная система соответствует требованиям ст. 18.1 ФЗ «О рекламе» "
        "и 152-ФЗ «О персональных данных».\n"
        "Система не продвигает конкретные товары или бренды. "
        "Оценка формируется исключительно на основе состава "
        "без учёта бренда.</i>"
    )
    await message.answer(how_it_works_text, parse_mode="HTML")



@router.message(Command("settings"))
async def cmd_settings_alias(message: Message, state: FSMContext):
    from bot.handlers.profile import start_settings
    await start_settings(message, state)