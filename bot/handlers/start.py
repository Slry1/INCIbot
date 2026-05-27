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
            "Я помогу персонализированно оценить состав косметических средств.\n\n"
            "📌 <b>Что я умею:</b>\n"
            "• 📷 Распознавать состав с фото этикетки\n"
            "• 🔗 Анализировать по ссылке с Wildberries\n"
            "• 🔍 Находить товар по названию и оценивать его состав\n"
            "• 📋 Принимать состав текстом напрямую\n"
            "• Учитывать тип кожи, аллергены и предпочтения\n\n"
            "📝 Отправь фото этикетки, ссылку, название или состав — и я дам оценку!"
        )
        await message.answer(welcome_text, reply_markup=main_keyboard, parse_mode="HTML")
    else:
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я — <b>INCIbot</b>, чат-бот для персонализированной оценки "
            "косметических средств по INCI-составу.\n\n"
            "📌 <b>Мои возможности:</b>\n"
            "📷 <b>Фото этикетки</b> — сфотографируй состав на упаковке, "
            "бот распознает ингредиенты автоматически\n"
            "🔗 <b>Ссылка с Wildberries</b> — состав загружается автоматически\n"
            "🔍 <b>Поиск по названию</b> — напиши название средства, и я найду его\n"
            "📋 <b>Текстовый состав</b> — отправь список ингредиентов напрямую\n"
            "👤 <b>Персонализация</b> — учёт типа кожи, аллергенов и предпочтений\n"
            "📊 <b>Умный анализ</b> — нейросеть DeepSeek 3.2 и база из 248 ингредиентов\n\n"
            "⚠️ <b>Важно:</b> для работы бота необходимо ознакомиться "
            "и согласиться с условиями обработки персональных данных."
        )
        await message.answer(welcome_text, parse_mode="HTML")
        await show_agreement(message)


async def show_agreement(message: Message):
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
        "• Только для формирования персонализированных оценок "
        "и анонимного агрегированного анализа использования системы\n"
        "• Не передаются третьим лицам\n"
        "• Хранятся на серверах на территории РФ (Yandex Cloud, ЦОД Москва)\n"
        "• Вы можете в любой момент удалить свои данные (/delete_data)\n\n"
        "⚖️ <b>Ваши права:</b>\n"
        "• Отозвать согласие в любой момент (команда /delete_data)\n"
        "• Использовать сервис без персонализации (без указания профиля)\n"
        "• Получить информацию о хранимых данных (команда /my_data)\n\n"
        "🤖 <b>Об использовании ИИ:</b>\n"
        "• Оценки генерируются нейросетью DeepSeek 3.2\n"
        "• Оценка носит <b>исключительно рекомендательный характер</b>\n"
        "• Не является медицинским заключением\n"
        "• Не заменяет консультацию дерматолога или аллерголога\n"
        "• При распознавании состава с фотографии возможны неточности — "
        "рекомендуется проверять полный состав на упаковке\n"
        "• Перед использованием нового средства рекомендуется патч-тест\n\n"
        "Нажимая «✅ Согласен», вы подтверждаете, что ознакомились "
        "с условиями и даёте согласие на обработку указанных данных."
    )
    await message.answer(agreement_text, reply_markup=agree_keyboard, parse_mode="HTML")


@router.message(F.text == "✅ Согласен")
async def on_agreement_accepted(message: Message):
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
        "📷 <b>Сфотографировать этикетку</b> — бот распознает состав\n"
        "📝 <b>Оценить состав</b> — ссылка, название или текст состава\n"
        "⚙️ <b>Настроить профиль</b> — тип кожи и аллергены для точных оценок\n\n"
        "💡 Совет: заполните профиль через «⚙️ Настройки» — "
        "тогда оценки будут учитывать именно ваши особенности.",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )


@router.message(F.text == "❌ Отказаться")
async def on_agreement_declined(message: Message):
    await message.answer(
        "😔 <b>Вы отказались от обработки данных.</b>\n\n"
        "Без согласия персонализированные оценки недоступны — "
        "бот не сможет учитывать ваш тип кожи и аллергены.\n\n"
        "Вы можете использовать бот в <b>базовом режиме</b> "
        "без персонализации — оценки будут общими.\n\n"
        "Если передумаете — нажмите /start для повторного соглашения.",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )


@router.message(Command("agreement"))
async def cmd_agreement(message: Message):
    await show_agreement(message)


@router.message(Command("delete_data"))
async def cmd_delete_data(message: Message):
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
    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(message.from_user.id)
        stats = await repo.get_user_stats(user.id)
        break

    profile_text = (
        "📋 <b>Информация о хранимых данных</b>\n\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"👤 Имя: {user.username or 'не указано'}\n"
        f"📅 Первое обращение: {user.first_seen.strftime('%d.%m.%Y %H:%M') if user.first_seen else 'неизвестно'}\n"
        f"🕐 Последняя активность: {user.last_active.strftime('%d.%m.%Y %H:%M') if user.last_active else 'неизвестно'}\n"
        f"🧴 Тип кожи: {user.skin_type or 'не указан'}\n"
        f"⚠️ Аллергены: {', '.join(user.allergens) if user.allergens else 'не указаны'}\n"
        f"⭐️ Предпочтения: {', '.join(user.preferences) if user.preferences else 'не указаны'}\n"
        f"📝 Соглашение принято: {'✅ Да' if user.agreement_accepted else '❌ Нет'}\n"
        f"📊 Всего запросов: {stats.get('total_queries', 0)}\n"
        f"📈 Средняя оценка: {stats.get('avg_score', 0):.1f}/10\n\n"
        "<i>Для удаления данных: /delete_data</i>\n"
        "<i>Для изменения настроек: /settings</i>"
    )
    await message.answer(profile_text, parse_mode="HTML")


@router.message(F.text == "❓ Помощь")
@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📖 <b>Как пользоваться INCIbot</b>\n\n"
        "Анализирую составы косметики с учётом вашего типа кожи и аллергенов.\n\n"
        "📌 <b>Способы отправить состав:</b>\n\n"
        "1️⃣ <b>Фото этикетки 📷</b>\n"
        "Сфотографируйте упаковку — бот распознает INCI-состав автоматически. "
        "Снимайте чётко, при хорошем освещении, без бликов.\n\n"
        "2️⃣ <b>Ссылка на Wildberries 🔗</b>\n"
        "Вставьте ссылку на товар — состав загрузится автоматически.\n\n"
        "3️⃣ <b>Название средства 🔍</b>\n"
        "Напишите название — бот найдёт товар и предложит выбрать из списка.\n\n"
        "4️⃣ <b>Текст состава 📋</b>\n"
        "Вставьте список ингредиентов через запятую напрямую.\n\n"
        "2️⃣ <b>Настроить профиль</b> (/settings)\n"
        "Укажите тип кожи, аллергены и предпочтения. "
        "Без профиля оценки будут общими.\n\n"
        "📊 <b>Шкала оценок:</b>\n"
        "• 9–10 — отличный состав, подходит идеально\n"
        "• 7–8 — хороший, есть небольшие замечания\n"
        "• 5–6 — удовлетворительно, есть нюансы\n"
        "• 3–4 — проблемный, лучше избегать\n"
        "• 0–2 — опасный или неполные данные\n\n"
        "💡 <b>Советы для точного результата:</b>\n"
        "• Заполните профиль — оценка станет персонализированной\n"
        "• При фото: снимайте крупно, без бликов и расфокуса\n"
        "• Убедитесь что весь состав попал в кадр\n"
        "• При сомнениях — проверяйте состав на упаковке\n\n"
        "⚠️ <b>Ограничения:</b> оценка носит рекомендательный характер "
        "и не является медицинским заключением. "
        "При распознавании состава с фото часть ингредиентов может быть "
        "не распознана — всегда проверяйте полный состав на упаковке. "
        "Перед использованием нового средства рекомендуется патч-тест."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "🔍 Как это работает")
@router.message(Command("how_it_works"))
async def cmd_how_it_works(message: Message):
    how_it_works_text = (
        "🔍 <b>Как работает INCIbot</b>\n\n"
        "Анализирую INCI-состав косметического средства и даю "
        "персонализированную оценку с учётом вашего типа кожи, "
        "аллергенов и предпочтений.\n\n"

        "📥 <b>Источники состава:</b>\n"
        "• 📷 Фото этикетки — OCR распознаёт текст через Yandex Vision, "
        "извлекает INCI-блок и проверяет ингредиенты по базе из 7338 наименований\n"
        "• 🔗 Wildberries — парсинг карточки товара (Success Rate 87%)\n"
        "• 📋 Текст напрямую — любой INCI-список через запятую\n\n"

        "🧠 <b>Как формируется оценка:</b>\n"
        "• Наличие аллергенов из вашего профиля\n"
        "• Комедогенность компонентов\n"
        "• Соответствие типу кожи\n"
        "• Консерванты, отдушки, раздражители\n"
        "• Порядок ингредиентов (первые 3–5 — основа, >1%)\n"
        "• RAG-база знаний: показания и противопоказания ингредиентов\n\n"

        "🔒 <b>Надёжность:</b>\n"
        "• Верификатор LLM-as-a-Judge проверяет каждый ответ "
        "(Hallucination Detection Rate 100%, FP 0%)\n"
        "• Защита от prompt injection (17 паттернов)\n"
        "• При неполном составе оценка снижается с предупреждением\n\n"

        "📜 <b>Важные ограничения:</b>\n"
        "• Оценка носит <b>рекомендательный характер</b>\n"
        "• Не является медицинским заключением\n"
        "• Не заменяет консультацию дерматолога или аллерголога\n"
        "• Точные концентрации ингредиентов — коммерческая тайна, "
        "в анализе не используются\n"
        "• При OCR-распознавании с фото: если этикетка попала в кадр "
        "не полностью, аллергены из хвоста состава могут быть пропущены — "
        "всегда проверяйте полный состав на упаковке\n"
        "• Перед использованием нового средства — патч-тест\n\n"

        "🔐 <b>Ваши права:</b>\n"
        "• Удалить данные: /delete_data\n"
        "• Данные хранятся на серверах в РФ (Yandex Cloud, ЦОД Москва)\n\n"

        "<i>Система соответствует требованиям 152-ФЗ «О персональных данных», "
        "ст. 18.1 ФЗ «О рекламе» и ТР ТС 009/2011. "
        "Не продвигает конкретные товары или бренды. "
        "Оценка формируется исключительно на основе состава.</i>"
    )
    await message.answer(how_it_works_text, parse_mode="HTML")


@router.message(Command("settings"))
async def cmd_settings_alias(message: Message, state: FSMContext):
    from bot.handlers.profile import start_settings
    await start_settings(message, state)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    from config import config

    if message.from_user.id not in config.ADMIN_IDS:
        return

    async for session in get_session():
        repo = DatabaseRepository(session)
        stats = await repo.get_global_stats()
        break

    sec = stats.get("security", {})
    by_level = sec.get("by_level", {})
    by_source = sec.get("by_source", {})
    by_type = sec.get("by_type", [])

    top_types = ""
    for item in by_type[:5]:
        top_types += f"  • {item['type']}: {item['count']}\n"
    if not top_types:
        top_types = "  нет данных\n"

    stats_text = (
        "📊 <b>Статистика системы INCIbot</b>\n\n"

        "👥 <b>Пользователи и запросы:</b>\n"
        f"  Всего пользователей: {stats['total_users']}\n"
        f"  Всего запросов: {stats['total_queries']}\n\n"

        "🔐 <b>Безопасность — события:</b>\n"
        f"  Всего событий: {sec.get('total_events', 0)}\n"
        f"  HIGH (заблокировано): {by_level.get('high', 0)}\n"
        f"  LOW (нейтрализовано): {by_level.get('low', 0)}\n"
        f"  Уникальных нарушителей: {sec.get('unique_attackers', 0)}\n\n"

        "📌 <b>Источник атак:</b>\n"
        f"  От пользователя: {by_source.get('user', 0)}\n"
        f"  Через Wildberries: {by_source.get('wildberries', 0)}\n"
        f"  Через OCR фото: {by_source.get('ocr_photo', 0)}\n\n"

        "🎯 <b>Топ типов атак:</b>\n"
        f"{top_types}"
    )

    await message.answer(stats_text, parse_mode="HTML")