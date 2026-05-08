from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import get_session
from database.repository import DatabaseRepository
from bot.handlers.start import main_keyboard

router = Router()

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)


class ProfileSettings(StatesGroup):
    waiting_for_skin_type = State()
    waiting_for_allergens = State()
    waiting_for_preferences = State()


@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(message.from_user.id)

        profile_text = (
            f"📋 <b>Ваш профиль</b>\n\n"
            f"🆔 ID: {user.telegram_id}\n"
            f"👤 Имя: {user.first_name or 'не указано'}\n"
            f"🧴 Тип кожи: {user.skin_type or 'не указан'}\n"
            f"⚠️ Аллергены: {', '.join(user.allergens) if user.allergens else 'не указаны'}\n"
            f"⭐️ Предпочтения: {', '.join(user.preferences) if user.preferences else 'не указаны'}\n\n"
            f"Используйте /settings для изменения параметров"
        )
        break

    await message.answer(profile_text, parse_mode="HTML")


@router.message(F.text == "⚙️ Настройки")
async def start_settings(message: Message, state: FSMContext):
    await state.set_state(ProfileSettings.waiting_for_skin_type)
    await message.answer(
        "👤 <b>Настройка профиля</b>\n\n"
        "Выберите ваш тип кожи:\n"
        "• Сухая\n"
        "• Жирная\n"
        "• Комбинированная\n"
        "• Нормальная\n"
        "• Чувствительная\n\n"
        "Или напишите свой вариант.",
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )


@router.message(ProfileSettings.waiting_for_skin_type)
async def process_skin_type(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Настройка отменена", reply_markup=main_keyboard)
        return

    await state.update_data(skin_type=message.text)
    await state.set_state(ProfileSettings.waiting_for_allergens)
    await message.answer(
        "Укажите аллергены (через запятую), на которые у вас есть реакция.\n"
        "Пример: отдушка, лаванда, орехи\n\n"
        "Если аллергенов нет, напишите 'нет'."
    )


@router.message(ProfileSettings.waiting_for_allergens)
async def process_allergens(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Настройка отменена", reply_markup=main_keyboard)
        return

    allergens = []
    if message.text.lower() != "нет":
        allergens = [a.strip() for a in message.text.split(",")]

    await state.update_data(allergens=allergens)
    await state.set_state(ProfileSettings.waiting_for_preferences)
    await message.answer(
        "Укажите ваши предпочтения (через запятую).\n"
        "Пример: натуральные компоненты, без спирта, веган\n\n"
        "Если предпочтений нет, напишите 'нет'."
    )


@router.message(ProfileSettings.waiting_for_preferences)
async def process_preferences(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Настройка отменена", reply_markup=main_keyboard)
        return

    preferences = []
    if message.text.lower() != "нет":
        preferences = [p.strip() for p in message.text.split(",")]

    user_data = await state.get_data()
    skin_type = user_data.get("skin_type")
    allergens = user_data.get("allergens", [])

    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(message.from_user.id)
        await repo.update_user_profile(
            user_id=user.id,
            skin_type=skin_type,
            allergens=allergens,
            preferences=preferences
        )
        break

    await state.clear()
    await message.answer(
        "✅ Профиль успешно обновлён!\n\n"
        f"Тип кожи: {skin_type}\n"
        f"Аллергены: {', '.join(allergens) if allergens else 'нет'}\n"
        f"Предпочтения: {', '.join(preferences) if preferences else 'нет'}",
        reply_markup=main_keyboard
    )