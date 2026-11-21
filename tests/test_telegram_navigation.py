"""Tests for sending navigation destinations from the Telegram bot."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from leapconnect.application.commands import ascii_label, send_vehicle_destination
from leapconnect.infrastructure.geocoding import Place, _place_from_result
from leapconnect.infrastructure.telegram.bot import (
    BOT_COMMANDS,
    Destination,
    TelegramBotHandler,
    parse_coordinates,
)
from leapconnect.infrastructure.telegram.config import TelegramConfig
from leapconnect.infrastructure.telegram.notifier import TelegramNotifier

VIN = "VIN123"


def _vehicle(rights=(180,), abilities=(52,)):
    return SimpleNamespace(vin=VIN, rights=list(rights), abilities=list(abilities))


def _handler(sender=None, search=None, allowed=True):
    cache = SimpleNamespace(_cache={VIN: object()})
    return TelegramBotHandler(
        vehicle_cache=cache,
        command_executor=AsyncMock(),
        rights_checker=lambda vin, cmd: allowed,
        destination_sender=sender or AsyncMock(return_value={"ok": True}),
        place_search=search or AsyncMock(return_value=[]),
    )


class TestHelpers:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("44.4949, 11.3426", (44.4949, 11.3426)),
            ("44.4949 11.3426", (44.4949, 11.3426)),
            ("-33.86;151.2", (-33.86, 151.2)),
            ("Via Roma 1, Bologna", None),
            ("95.0, 10.0", None),
            ("44.49", None),
        ],
    )
    def test_parse_coordinates(self, text, expected):
        assert parse_coordinates(text) == expected

    def test_ascii_label_folds_accents_and_drops_the_rest(self):
        assert ascii_label("Città di Castello – Piazza Matteotti") == (
            "Citta di Castello Piazza Matteotti"
        )
        assert ascii_label("北京") == ""
        assert len(ascii_label("a" * 200)) == 80

    def test_place_from_nominatim_result(self):
        place = _place_from_result(
            {
                "lat": "44.5",
                "lon": "11.3",
                "name": "",
                "display_name": "10, Via Indipendenza, Bologna, Italia",
                "address": {"road": "Via Indipendenza", "house_number": "10"},
            }
        )
        assert place == Place(
            44.5, 11.3, "Via Indipendenza 10", "10, Via Indipendenza, Bologna, Italia"
        )

    def test_navigate_is_in_the_bot_menu(self):
        assert "navigate" in {c["command"] for c in BOT_COMMANDS}


class TestSendVehicleDestination:
    async def test_sends_ascii_name_and_coordinates(self):
        client = AsyncMock()
        await send_vehicle_destination(
            client,
            _vehicle(),
            latitude=44.5,
            longitude=11.3,
            name="Caffè Nerò",
            address="Via Indipendenza 10, Bologna",
        )
        client.send_destination.assert_awaited_once_with(
            VIN,
            address="Via Indipendenza 10, Bologna",
            address_name="Caffe Nero",
            latitude=44.5,
            longitude=11.3,
        )

    async def test_coordinates_label_when_no_name(self):
        client = AsyncMock()
        await send_vehicle_destination(client, _vehicle(), latitude=1.5, longitude=2.5)
        kwargs = client.send_destination.await_args.kwargs
        assert kwargs["address"] == kwargs["address_name"] == "1.500000, 2.500000"

    async def test_missing_right_raises(self):
        with pytest.raises(PermissionError):
            await send_vehicle_destination(
                AsyncMock(), _vehicle(rights=()), latitude=1.0, longitude=2.0
            )


class TestNavigateCommand:
    async def test_coordinates_are_sent_straight_away(self):
        sender = AsyncMock(return_value={"ok": True})
        handler = _handler(sender=sender)
        text, keyboard = await handler.handle_navigate("44.4949, 11.3426")
        sender.assert_awaited_once_with(VIN, 44.4949, 11.3426, "", "")
        assert keyboard is None
        assert "✅" in text

    async def test_address_is_proposed_then_sent_on_confirm(self):
        sender = AsyncMock(return_value={"ok": True})
        search = AsyncMock(
            return_value=[Place(44.5, 11.3, "Piazza Maggiore", "Piazza Maggiore, BO")]
        )
        handler = _handler(sender=sender, search=search)

        text, keyboard = await handler.handle_navigate("piazza maggiore bologna")
        search.assert_awaited_once_with("piazza maggiore bologna")
        sender.assert_not_awaited()
        assert "Piazza Maggiore" in text
        send_cb = keyboard["inline_keyboard"][0][0]["callback_data"]
        assert send_cb.startswith("nav:send:")

        result = await handler.handle_navigation_callback(send_cb)
        sender.assert_awaited_once_with(
            VIN, 44.5, 11.3, "Piazza Maggiore", "Piazza Maggiore, BO"
        )
        assert "Piazza Maggiore" in result
        # The proposal can't be sent twice
        again = await handler.handle_navigation_callback(send_cb)
        assert "expired" in again
        assert sender.await_count == 1

    async def test_cancel_does_not_send(self):
        sender = AsyncMock()
        search = AsyncMock(return_value=[Place(1.0, 2.0, "X", "X")])
        handler = _handler(sender=sender, search=search)
        _, keyboard = await handler.handle_navigate("x")
        cancel_cb = keyboard["inline_keyboard"][0][1]["callback_data"]
        assert "Cancelled" in await handler.handle_navigation_callback(cancel_cb)
        sender.assert_not_awaited()

    async def test_no_match(self):
        handler = _handler(search=AsyncMock(return_value=[]))
        text, keyboard = await handler.handle_navigate("nowhere <b>")
        assert "No place found" in text
        assert "&lt;b&gt;" in text  # user text is escaped (HTML parse mode)
        assert keyboard is None

    async def test_search_error(self):
        handler = _handler(search=AsyncMock(side_effect=RuntimeError("down")))
        text, _ = await handler.handle_navigate("somewhere")
        assert "failed" in text

    async def test_usage_without_arguments(self):
        text, keyboard = await _handler().handle_navigate("  ")
        assert "/navigate" in text
        assert keyboard is None

    async def test_missing_permission(self):
        sender = AsyncMock()
        handler = _handler(sender=sender, allowed=False)
        text, _ = await handler.handle_navigate("1.0, 2.0")
        assert "missing permission" in text
        sender.assert_not_awaited()

    async def test_handle_command_alias(self):
        sender = AsyncMock(return_value={"ok": True})
        handler = _handler(sender=sender)
        text = await handler.handle_command("/naviga@SomeBot 44.5 11.3")
        sender.assert_awaited_once_with(VIN, 44.5, 11.3, "", "")
        assert "✅" in text

    async def test_cloud_error_is_reported(self):
        sender = AsyncMock(side_effect=RuntimeError("boom & co"))
        text = await _handler(sender=sender).send_destination(Destination(1.0, 2.0))
        assert "boom &amp; co" in text


class TestSharedLocation:
    async def _notifier(self, handler):
        notifier = TelegramNotifier(
            TelegramConfig(bot_token="T", chat_id="1", bot_enabled=True)
        )
        notifier._bot_handler = handler
        notifier._update_user_info = AsyncMock()
        return notifier

    async def test_venue_is_sent_with_its_title(self):
        sender = AsyncMock(return_value={"ok": True})
        notifier = await self._notifier(_handler(sender=sender))
        client = AsyncMock()
        msg = {
            "chat": {"id": 42},
            "venue": {
                "location": {"latitude": 44.5, "longitude": 11.3},
                "title": "Bar Centrale",
                "address": "Via Roma 1",
            },
            "location": {"latitude": 44.5, "longitude": 11.3},
        }
        await notifier._handle_location_message(client, msg, "42")
        sender.assert_awaited_once_with(VIN, 44.5, 11.3, "Bar Centrale", "Via Roma 1")
        payload = client.post.await_args.kwargs["json"]
        assert payload["chat_id"] == "42"
        assert "Bar Centrale" in payload["text"]

    async def test_plain_location_is_sent(self):
        sender = AsyncMock(return_value={"ok": True})
        notifier = await self._notifier(_handler(sender=sender))
        msg = {"chat": {"id": 42}, "location": {"latitude": 1.5, "longitude": 2.5}}
        await notifier._handle_location_message(AsyncMock(), msg, "42")
        sender.assert_awaited_once_with(VIN, 1.5, 2.5, "", "")
