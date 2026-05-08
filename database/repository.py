from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, History
from datetime import datetime


class DatabaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, telegram_id: int, username: str = None,
                                 first_name: str = None, last_name: str = None) -> User:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            self.session.add(user)
            await self.session.commit()

        return user

    async def update_user_profile(self, user_id: int, skin_type: str = None,
                                  allergens: list = None, preferences: list = None) -> User:
        update_data = {}
        if skin_type is not None:
            update_data["skin_type"] = skin_type
        if allergens is not None:
            update_data["allergens"] = allergens
        if preferences is not None:
            update_data["preferences"] = preferences

        if update_data:
            await self.session.execute(
                update(User)
                .where(User.id == user_id)
                .values(**update_data)
            )
            await self.session.commit()

        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()

    async def update_agreement(self, user_id: int, accepted: bool) -> None:
        """Обновление статуса пользовательского соглашения"""
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(agreement_accepted=accepted)
        )
        await self.session.commit()

    async def delete_user_data(self, user_id: int) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                skin_type=None,
                allergens=None,
                preferences=None,
                agreement_accepted=False
            )
        )
        await self.session.execute(
            delete(History).where(History.user_id == user_id)
        )
        await self.session.commit()

    async def save_history(self, user_id: int, user_message: str,
                           llm_response_raw: str = None,
                           llm_response_parsed: dict = None,
                           prompt_used: str = None,
                           processing_time_ms: int = None) -> History:
        history = History(
            user_id=user_id,
            user_message=user_message,
            llm_response_raw=llm_response_raw,
            llm_response_parsed=llm_response_parsed,
            prompt_used=prompt_used,
            processing_time_ms=processing_time_ms
        )
        self.session.add(history)
        await self.session.commit()
        return history

    async def get_user_history(self, user_id: int, limit: int = 5) -> list:
        result = await self.session.execute(
            select(History)
            .where(History.user_id == user_id)
            .order_by(History.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_user_stats(self, user_id: int) -> dict:
        result = await self.session.execute(
            select(
                func.count(History.id).label("total_queries"),
                func.avg(
                    func.cast(
                        func.json_extract_path_text(History.llm_response_parsed, "score"),
                        Integer
                    )
                ).label("avg_score")
            )
            .where(History.user_id == user_id)
        )
        row = result.one()
        return {
            "total_queries": row.total_queries or 0,
            "avg_score": round(float(row.avg_score or 0), 1),
        }