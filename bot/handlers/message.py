import time
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters.callback_data import CallbackData
from database.db import get_session
from database.repository import DatabaseRepository
from llm.yandex_client import YandexGPTClient
from llm.prompt_builder import PromptBuilder
from llm.rag_module import IngredientRAG
from bot.cosmetic_parser import CosmeticParser, ProductInfo
import asyncio

router = Router()
_cosmetic_parser = CosmeticParser()
_rag = IngredientRAG()

user_search_cache = {}


class ProductSelectCallback(CallbackData, prefix="prod"):
    nm_id: int


class SearchCancelCallback(CallbackData, prefix="cancel_search"):
    pass


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _is_url(text: str) -> bool:
    lower = text.lower()
    return any(domain in lower for domain in (
        "wildberries.ru", "wb.ru", "ozon.ru", "goldapple.ru"
    ))


def _is_product_name(text: str) -> bool:
    return CosmeticParser.looks_like_search_query(text)


def build_search_results_keyboard(products: list[dict]) -> InlineKeyboardMarkup:
    buttons = []

    for i, p in enumerate(products, 1):
        name = p['name'][:40] + "..." if len(p['name']) > 40 else p['name']
        text = f"{i}. {name} | {p['brand']} | {p['price']}₽"
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=ProductSelectCallback(nm_id=p['id']).pack()
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=SearchCancelCallback().pack()
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def process_product(
        message: Message,
        nm_id: int,
        user,
        llm_client: YandexGPTClient,
        status_msg: Message
):
    import aiohttp

    start_time = time.time()

    await status_msg.delete()
    loading_msg = await message.answer("🔗 Загружаю состав товара...")

    composition = None
    product_info = None

    async with aiohttp.ClientSession() as session:
        product_info = await _cosmetic_parser.wb.fetch_by_article(session, str(nm_id))
        if product_info:
            composition = product_info.ingredients

    await loading_msg.delete()

    if not composition or composition == "Состав не найден":
        await message.answer(
            "😔 Не удалось получить состав для этого товара.\n"
            "Попробуйте другой товар или вставьте состав вручную."
        )
        return

    analyzing_msg = await message.answer("🤖 Анализирую состав...")

    prompt = PromptBuilder.build_prompt(
        skin_type=user.skin_type,
        allergens=user.allergens or [],
        preferences=user.preferences or [],
        name=product_info.name if product_info else "",
        ingredients=composition,
        history=[],
        rag=_rag
    )

    response = await llm_client.generate_response(prompt)
    processing_time = int((time.time() - start_time) * 1000)

    await analyzing_msg.delete()

    if response and response.get("score") is not None:
        score = response.get("score", 0)
        explanation = response.get("explanation", "Оценка сформирована")
        warnings = response.get("warnings", [])
        recommendations = response.get("recommendations", [])

        stars = "⭐️" * (score // 2) + "☆" * (5 - (score // 2))

        if product_info:
            title_line = (
                    f"📊 <b>Оценка: {score}/10</b> — "
                    f"{product_info.name}"
                    + (f" ({product_info.brand})" if product_info.brand else "")
            )
        else:
            title_line = f"📊 <b>Оценка состава: {score}/10</b>"

        answer_text = (
            f"{title_line}\n"
            f"{stars}\n\n"
            f"📝 <b>Пояснение:</b>\n{explanation}\n\n"
        )

        if warnings:
            answer_text += "⚠️ <b>Предупреждения:</b>\n"
            for w in warnings:
                answer_text += f"• {w}\n"
            answer_text += "\n"

        if recommendations:
            answer_text += "💡 <b>Рекомендации:</b>\n"
            for r in recommendations:
                answer_text += f"• {r}\n"

        if product_info:
            answer_text += f"\n🔗 <a href='{product_info.source_url}'>Ссылка на товар</a>\n"

        answer_text += "\n<i>⚠️ Оценка носит рекомендательный характер и сгенерирована при помощи ИИ.</i>"

        await message.answer(answer_text, parse_mode="HTML")

        async for session in get_session():
            repo = DatabaseRepository(session)
            await repo.save_history(
                user_id=user.id,
                user_message=product_info.name if product_info else f"Товар {nm_id}",
                llm_response_raw=str(response),
                llm_response_parsed=response,
                prompt_used=prompt,
                processing_time_ms=processing_time
            )
            break
    else:
        await message.answer(
            "😔 Извините, не удалось обработать запрос.\n"
            "Пожалуйста, попробуйте позже."
        )


@router.message(F.text == "📝 Оценить состав")
async def prompt_ingredients(message: Message):
    await message.answer(
        "📝 Отправьте состав косметического средства для оценки.\n\n"
        "Вы можете:\n"
        "• Вставить <b>ссылку</b> на товар с Wildberries\n"
        "• Написать <b>название</b> продукта — бот найдёт его сам\n"
        "• Вставить <b>состав</b> напрямую (Aqua, Glycerin, ...)\n\n"
        "Пример ссылки: https://www.wildberries.ru/catalog/12345678/detail.aspx\n"
        "Пример названия: <i>Крем для лица Cerave увлажняющий</i>",
        parse_mode="HTML"
    )


@router.message(F.text)
async def handle_message(message: Message, state: FSMContext, llm_client: YandexGPTClient):
    start_time = time.time()
    text = message.text.strip()

    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(message.from_user.id)
        history = await repo.get_user_history(user.id, limit=5)
        break

    ingredients_text = text
    product_info: ProductInfo | None = None

    if _is_url(text):
        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = await message.answer("🔗 Загружаю состав со страницы товара...")

        try:
            product_info = await _cosmetic_parser.parse(text)
        except Exception:
            product_info = None

        if product_info and product_info.ingredients != "Состав не найден":
            ingredients_text = product_info.ingredients
            await status_msg.edit_text(
                f"✅ Нашёл продукт: <b>{product_info.name}</b>"
                + (f" ({product_info.brand})" if product_info.brand else ""),
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text(
                "😔 Не удалось получить состав автоматически.\n\n"
                "Попробуйте:\n"
                "• Проверить ссылку (откройте её в браузере)\n"
                "• Скопировать состав вручную со страницы товара и отправить его"
            )
            return

    elif _is_product_name(text):
        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = await message.answer(f"🔍 Ищу: <b>{text}</b>...", parse_mode="HTML")

        products = await asyncio.to_thread(
            _cosmetic_parser.wb.search_sync_multiple, text, 5
        )

        if not products:
            await status_msg.edit_text(
                f"❌ По запросу <b>{text}</b> ничего не найдено.\n"
                "Попробуйте уточнить название или вставьте состав вручную.",
                parse_mode="HTML"
            )
            return

        user_search_cache[message.from_user.id] = products

        response_text = f"🔍 <b>Найдено {len(products)} товаров:</b>\n\n"
        for i, p in enumerate(products, 1):
            response_text += f"{i}. <b>{p['name'][:60]}</b>\n"
            response_text += f"   🏷 {p['brand']} | ⭐ {p['rating']} | 💬 {p['feedbacks']}\n"
            response_text += f"   💰 {p['price']}₽\n\n"
        response_text += "👇 <b>Выберите товар для оценки состава:</b>"

        keyboard = build_search_results_keyboard(products)
        await status_msg.edit_text(
            response_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    else:
        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = None

    if not _is_product_name(text) or (_is_url(text) and product_info):
        if not status_msg:
            analyzing_msg = await message.answer("🤖 Анализирую состав...")
        else:
            analyzing_msg = await message.answer("🤖 Анализирую состав...")

        prompt = PromptBuilder.build_prompt(
            skin_type=user.skin_type,
            allergens=user.allergens or [],
            preferences=user.preferences or [],
            name=product_info.name if product_info else "",
            ingredients=ingredients_text,
            history=history,
            rag=_rag
        )

        response = await llm_client.generate_response(prompt)
        processing_time = int((time.time() - start_time) * 1000)

        if response and response.get("score") is not None:
            score = response.get("score", 0)
            explanation = response.get("explanation", "Оценка сформирована")
            warnings = response.get("warnings", [])
            recommendations = response.get("recommendations", [])

            stars = "⭐️" * (score // 2) + "☆" * (5 - (score // 2))

            if product_info:
                title_line = (
                        f"📊 <b>Оценка: {score}/10</b> — "
                        f"{product_info.name}"
                        + (f" ({product_info.brand})" if product_info.brand else "")
                )
            else:
                title_line = f"📊 <b>Оценка состава: {score}/10</b>"

            answer_text = (
                f"{title_line}\n"
                f"{stars}\n\n"
                f"📝 <b>Пояснение:</b>\n{explanation}\n\n"
            )

            if warnings:
                answer_text += "⚠️ <b>Предупреждения:</b>\n"
                for w in warnings:
                    answer_text += f"• {w}\n"
                answer_text += "\n"

            if recommendations:
                answer_text += "💡 <b>Рекомендации:</b>\n"
                for r in recommendations:
                    answer_text += f"• {r}\n"

            if product_info:
                answer_text += f"\n🔗 <a href='{product_info.source_url}'>Ссылка на товар</a>\n"

            answer_text += "\n<i>⚠️ Оценка носит рекомендательный характер и сгенерирована при помощи ИИ. Перед использованием проведите патч-тест.</i>"

            await analyzing_msg.delete()
            await message.answer(answer_text, parse_mode="HTML")

            async for session in get_session():
                repo = DatabaseRepository(session)
                await repo.save_history(
                    user_id=user.id,
                    user_message=text,
                    llm_response_raw=str(response),
                    llm_response_parsed=response,
                    prompt_used=prompt,
                    processing_time_ms=processing_time
                )
                break
        else:
            await analyzing_msg.delete()
            await message.answer(
                "😔 Извините, не удалось обработать запрос.\n"
                "Пожалуйста, попробуйте позже или уточните состав."
            )



@router.callback_query(ProductSelectCallback.filter())
async def on_product_select(
        callback: CallbackQuery,
        callback_data: ProductSelectCallback,
        llm_client: YandexGPTClient
):
    nm_id = callback_data.nm_id

    await callback.answer("Загружаю состав...")

    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(callback.from_user.id)
        break

    status_msg = await callback.message.edit_text("🔗 Загружаю состав товара...")

    # Обрабатываем товар
    await process_product(callback.message, nm_id, user, llm_client, status_msg)


@router.callback_query(SearchCancelCallback.filter())
async def on_search_cancel(callback: CallbackQuery):
    await callback.answer("Поиск отменен")
    await callback.message.edit_text("❌ Поиск отменен")

    user_search_cache.pop(callback.from_user.id, None)