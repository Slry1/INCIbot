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
from llm.verifier import ResponseVerifier
from llm.sanitizer import InputSanitizer, ThreatLevel
from llm.rate_limiter import RateLimiter
from bot.cosmetic_parser import CosmeticParser, ProductInfo
from config import config
import asyncio

router = Router()
_cosmetic_parser = CosmeticParser()
_rag = IngredientRAG(kb_path=config.RAG_DATA_PATH)
_verifier = ResponseVerifier()
_rate_limiter = RateLimiter()

_SEARCH_CACHE_TTL = 300  # секунд (5 минут)

class _TTLCache:
    """Кэш результатов поиска с автоматическим истечением записей."""

    def __init__(self, ttl: int):
        self._ttl = ttl
        self._data: dict[int, tuple[list, float]] = {}

    def set(self, user_id: int, products: list) -> None:
        self._evict()
        self._data[user_id] = (products, time.time())

    def get(self, user_id: int) -> list | None:
        entry = self._data.get(user_id)
        if entry is None:
            return None
        products, ts = entry
        if time.time() - ts > self._ttl:
            del self._data[user_id]
            return None
        return products

    def pop(self, user_id: int) -> None:
        self._data.pop(user_id, None)

    def _evict(self) -> None:
        """Удаляет все просроченные записи."""
        now = time.time()
        expired = [uid for uid, (_, ts) in self._data.items() if now - ts > self._ttl]
        for uid in expired:
            del self._data[uid]


user_search_cache = _TTLCache(ttl=_SEARCH_CACHE_TTL)


async def safe_edit(msg: Message, text: str, **kwargs) -> None:
    try:
        await msg.edit_text(text, **kwargs)
    except Exception as e:
        if "message is not modified" not in str(e):
            raise


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


def _format_answer(
    response: dict,
    product_info: ProductInfo | None,
    was_corrected: bool,
) -> str:
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

    verifier_note = (
        "\n🔍 <i>Ответ прошёл верификацию. Обнаружены неточности — оценка скорректирована.</i>\n"
        if was_corrected else ""
    )

    text = (
        f"{title_line}\n"
        f"{stars}"
        f"{verifier_note}\n"
        f"📝 <b>Пояснение:</b>\n{explanation}\n\n"
    )

    if warnings:
        text += "⚠️ <b>Предупреждения:</b>\n"
        for w in warnings:
            text += f"• {w}\n"
        text += "\n"

    if recommendations:
        text += "💡 <b>Рекомендации:</b>\n"
        for r in recommendations:
            text += f"• {r}\n"

    if product_info:
        text += f"\n🔗 <a href='{product_info.source_url}'>Ссылка на товар</a>\n"

    text += "\n<i>⚠️ Оценка носит рекомендательный характер и сгенерирована при помощи ИИ. Перед использованием проведите патч-тест.</i>"

    return text


async def _evaluate_and_verify(
    llm_client: YandexGPTClient,
    prompt: str,
    ingredients: str,
    skin_type: str,
    allergens: list,
    status_message: Message,
    source: str = "user",
    telegram_id: int = None,
) -> tuple[dict, bool]:
    san = InputSanitizer.check(ingredients, source=source)

    if not san.is_safe:
        async for session in get_session():
            repo = DatabaseRepository(session)
            await repo.log_security_event(
                telegram_id=telegram_id,
                threat_level=san.threat_level.value,
                threat_type=san.threat_type,
                source=source,
                input_text=ingredients,
                action_taken="blocked" if san.threat_level.value == "high" else "neutralized",
            )
            break

        if san.threat_level.value == "high":
            await safe_edit(status_message, "⚠️ Обнаружена попытка манипуляции с данными.")
            return {
                "score": 0,
                "explanation": "Входные данные содержат недопустимые инструкции. Пожалуйста, отправьте только состав косметического средства в формате INCI.",
                "warnings": [],
                "recommendations": [],
                "_injection_blocked": True,
            }, False
        else:
            ingredients = InputSanitizer.neutralize(ingredients)

    response = await llm_client.generate_response(prompt)

    if not response or response.get("score") is None:
        return response, False

    if _verifier.enabled:
        await safe_edit(status_message, "🔍 Проверяю ответ на точность...")

        verification = await _verifier.verify(
            ingredients=ingredients,
            llm_response=response,
            skin_type=skin_type,
            allergens=allergens,
        )

        corrected = _verifier.apply_corrections(response, verification)
        was_corrected = not verification.verified and not verification.verifier_failed

        return corrected, was_corrected

    return response, False


async def process_product(
    message: Message,
    nm_id: int,
    user,
    llm_client: YandexGPTClient,
    status_msg: Message,
):
    import aiohttp

    start_time = time.time()

    await safe_edit(status_msg, "🔗 Загружаю состав товара...")

    composition = None
    product_info = None

    async with aiohttp.ClientSession() as session:
        product_info = await _cosmetic_parser.wb.fetch_by_article(session, str(nm_id))
        if product_info:
            composition = product_info.ingredients

    if not composition or composition == "Состав не найден":
        await safe_edit(status_msg,
            "😔 Не удалось получить состав для этого товара.\n"
            "Попробуйте другой товар или вставьте состав вручную."
        )
        return

    await safe_edit(status_msg, "🤖 Анализирую состав...")

    prompt = PromptBuilder.build_prompt(
        skin_type=user.skin_type,
        allergens=user.allergens or [],
        preferences=user.preferences or [],
        name=product_info.name if product_info else "",
        ingredients=composition,
        history=[],
        rag=_rag,
    )

    response, was_corrected = await _evaluate_and_verify(
        llm_client=llm_client,
        prompt=prompt,
        ingredients=composition,
        skin_type=user.skin_type or "",
        allergens=user.allergens or [],
        status_message=status_msg,
        source="wildberries",
        telegram_id=message.from_user.id,
    )

    processing_time = int((time.time() - start_time) * 1000)
    await status_msg.delete()

    if response and response.get("score") is not None:
        answer_text = _format_answer(response, product_info, was_corrected)
        await message.answer(answer_text, parse_mode="HTML")

        async for session in get_session():
            repo = DatabaseRepository(session)
            await repo.save_history(
                user_id=user.id,
                user_message=product_info.name if product_info else f"Товар {nm_id}",
                llm_response_raw=str(response),
                llm_response_parsed=response,   # содержит _verified и _corrections
                prompt_used=prompt,
                processing_time_ms=processing_time,
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
        parse_mode="HTML",
    )


@router.message(F.text)
async def handle_message(message: Message, state: FSMContext, llm_client: YandexGPTClient):
    start_time = time.time()
    text = message.text.strip()

    rl = await _rate_limiter.acquire(message.from_user.id)
    if not rl.allowed:
        limit_labels = {
            "burst": "слишком много запросов подряд",
            "rpm":   "превышен лимит запросов в минуту",
            "rph":   "превышен лимит запросов в час",
        }
        reason = limit_labels.get(rl.limit_type, "превышен лимит запросов")
        minutes = (rl.retry_after_seconds or 60) // 60
        seconds = (rl.retry_after_seconds or 60) % 60
        wait_str = f"{minutes} мин {seconds} сек" if minutes else f"{seconds} сек"
        await message.answer(
            f"⏳ {reason.capitalize()}.\n"
            f"Пожалуйста, подождите {wait_str} перед следующим запросом."
        )
        return

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
            await safe_edit(status_msg,
                f"✅ Нашёл продукт: <b>{product_info.name}</b>"
                + (f" ({product_info.brand})" if product_info.brand else ""),
                parse_mode="HTML",
            )
        else:
            await safe_edit(status_msg,
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
            await safe_edit(status_msg,
                f"❌ По запросу <b>{text}</b> ничего не найдено.\n"
                "Попробуйте уточнить название или вставьте состав вручную.",
                parse_mode="HTML",
            )
            return

        user_search_cache.set(message.from_user.id, products)

        response_text = f"🔍 <b>Найдено {len(products)} товаров:</b>\n\n"
        for i, p in enumerate(products, 1):
            response_text += f"{i}. <b>{p['name'][:60]}</b>\n"
            response_text += f"   🏷 {p['brand']} | ⭐ {p['rating']} | 💬 {p['feedbacks']}\n"
            response_text += f"   💰 {p['price']}₽\n\n"
        response_text += "👇 <b>Выберите товар для оценки состава:</b>"

        keyboard = build_search_results_keyboard(products)
        await safe_edit(status_msg, response_text, reply_markup=keyboard, parse_mode="HTML")
        return

    else:
        await message.bot.send_chat_action(message.chat.id, "typing")
        status_msg = None

    if not _is_product_name(text) or (_is_url(text) and product_info):
        analyzing_msg = await message.answer("🤖 Анализирую состав...")

        prompt = PromptBuilder.build_prompt(
            skin_type=user.skin_type,
            allergens=user.allergens or [],
            preferences=user.preferences or [],
            name=product_info.name if product_info else "",
            ingredients=ingredients_text,
            history=history,
            rag=_rag,
        )

        response, was_corrected = await _evaluate_and_verify(
            llm_client=llm_client,
            prompt=prompt,
            ingredients=ingredients_text,
            skin_type=user.skin_type or "",
            allergens=user.allergens or [],
            status_message=analyzing_msg,
            source="user",
            telegram_id=message.from_user.id,
        )

        processing_time = int((time.time() - start_time) * 1000)

        if response and response.get("score") is not None:
            answer_text = _format_answer(response, product_info, was_corrected)

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
                    processing_time_ms=processing_time,
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
    llm_client: YandexGPTClient,
):
    nm_id = callback_data.nm_id
    await callback.answer("Загружаю состав...")

    async for session in get_session():
        repo = DatabaseRepository(session)
        user = await repo.get_or_create_user(callback.from_user.id)
        break

    try:
        status_msg = await callback.message.edit_text("🔗 Загружаю состав товара...")
    except Exception as e:
        if "message is not modified" in str(e):
            status_msg = callback.message
        else:
            raise
    await process_product(callback.message, nm_id, user, llm_client, status_msg)


@router.callback_query(SearchCancelCallback.filter())
async def on_search_cancel(callback: CallbackQuery):
    await callback.answer("Поиск отменен")
    await safe_edit(callback.message, "❌ Поиск отменен")
    user_search_cache.pop(callback.from_user.id)