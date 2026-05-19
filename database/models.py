from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    first_seen = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
    last_active = Column(DateTime, default=datetime.datetime.now(datetime.UTC), onupdate=datetime.datetime.now(datetime.UTC))

    skin_type = Column(String(50), nullable=True)
    allergens = Column(JSON, default=list)
    preferences = Column(JSON, default=list)
    agreement_accepted = Column(Boolean, default=False)


class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
    user_message = Column(Text, nullable=False)
    llm_response_raw = Column(Text, nullable=True)
    llm_response_parsed = Column(JSON, nullable=True)
    prompt_used = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id           = Column(Integer, primary_key=True)
    timestamp    = Column(DateTime, default=datetime.datetime.now(datetime.UTC), nullable=False, index=True)
    telegram_id  = Column(BigInteger, nullable=True, index=True)
    threat_level = Column(String(10),  nullable=False)
    threat_type  = Column(String(50),  nullable=True)
    source       = Column(String(30),  nullable=True)
    input_fragment = Column(String(200), nullable=True)
    action_taken = Column(String(20),  nullable=False)