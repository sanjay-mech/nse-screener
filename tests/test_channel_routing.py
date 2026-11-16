"""
Unit tests for Dual Telegram Channel Alert Routing.
- 52-Week High/Low and ATH/ATL -> Channel 1 (-1004490443970)
- Donchian Channels (DC) and Supertrend (ST) -> Channel 2 (-1004314287084)
"""
import pytest
from alerts.telegram_bot import TelegramBot
from config.settings import settings


@pytest.mark.asyncio
async def test_telegram_channel_routing(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "mock_token")
    monkeypatch.setattr(settings, "TELEGRAM_CHANNEL_ATH_52W", "-1004490443970")
    monkeypatch.setattr(settings, "TELEGRAM_CHANNEL_DC_ST", "-1004314287084")
    monkeypatch.setattr(settings, "ADMIN_CHAT_ID", "1016641982")

    bot = TelegramBot(repository=None)
    bot.token = "mock_token"

    # 1. ATH alert -> should route to Channel 1 (-1004490443970) + Admin
    await bot.broadcast_alert("ATH msg", trigger="ATH")
    enqueued_chats = []
    while not bot._outbound_queue.empty():
        chat_id, text, _ = await bot._outbound_queue.get()
        enqueued_chats.append(chat_id)

    assert "-1004490443970" in enqueued_chats
    assert "-1004314287084" not in enqueued_chats
    assert "1016641982" in enqueued_chats

    # 2. 52W High alert -> should route to Channel 1 (-1004490443970) + Admin
    await bot.broadcast_alert("52W msg", trigger="52W_HIGH")
    enqueued_chats = []
    while not bot._outbound_queue.empty():
        chat_id, text, _ = await bot._outbound_queue.get()
        enqueued_chats.append(chat_id)

    assert "-1004490443970" in enqueued_chats
    assert "-1004314287084" not in enqueued_chats

    # 3. Donchian alert -> should route to Channel 2 (-1004314287084) + Admin
    await bot.broadcast_alert("DC msg", trigger="DC50_HIGH")
    enqueued_chats = []
    while not bot._outbound_queue.empty():
        chat_id, text, _ = await bot._outbound_queue.get()
        enqueued_chats.append(chat_id)

    assert "-1004314287084" in enqueued_chats
    assert "-1004490443970" not in enqueued_chats

    # 4. Supertrend alert -> should route to Channel 2 (-1004314287084) + Admin
    await bot.broadcast_alert("ST msg", trigger="ST_DAILY_10_1_BUY")
    enqueued_chats = []
    while not bot._outbound_queue.empty():
        chat_id, text, _ = await bot._outbound_queue.get()
        enqueued_chats.append(chat_id)

    assert "-1004314287084" in enqueued_chats
    assert "-1004490443970" not in enqueued_chats

    # 5. General broadcast (trigger is None) -> should go to both channels + Admin
    await bot.broadcast_alert("General msg", trigger=None)
    enqueued_chats = []
    while not bot._outbound_queue.empty():
        chat_id, text, _ = await bot._outbound_queue.get()
        enqueued_chats.append(chat_id)

    assert "-1004490443970" in enqueued_chats
    assert "-1004314287084" in enqueued_chats
    assert "1016641982" in enqueued_chats
