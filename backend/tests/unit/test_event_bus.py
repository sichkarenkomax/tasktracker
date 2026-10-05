from __future__ import annotations

import pytest

from app.core.events import DomainEvent, EventBus, InvalidEventName


def make_event(name: str = "task.created") -> DomainEvent:
    return DomainEvent(name=name, payload={"task_id": "42"})


class TestDomainEvent:
    def test_payload_is_immutable(self) -> None:
        event = make_event()
        with pytest.raises(TypeError):
            event.payload["task_id"] = "43"  # type: ignore[index]

    def test_event_name_must_be_dotted(self) -> None:
        with pytest.raises(InvalidEventName):
            DomainEvent(name="TaskCreated")

    def test_to_dict_is_serialisable(self) -> None:
        assert make_event().to_dict()["name"] == "task.created"


class TestEventBus:
    async def test_dispatches_to_named_handler(self) -> None:
        bus = EventBus()
        received: list[DomainEvent] = []

        async def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("task.created", handler)
        failures = await bus.publish(make_event())

        assert failures == []
        assert [event.name for event in received] == ["task.created"]

    async def test_wildcard_receives_everything(self) -> None:
        bus = EventBus()
        received: list[str] = []
        bus.subscribe_all(lambda event: received.append(event.name))

        await bus.publish(make_event("task.created"))
        await bus.publish(make_event("crm.deal.created"))

        assert received == ["task.created", "crm.deal.created"]

    async def test_unrelated_handler_is_not_called(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        bus.subscribe("task.created", lambda event: calls.append(event.name))

        await bus.publish(make_event("task.deleted"))

        assert calls == []

    async def test_sync_handlers_are_supported(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        bus.subscribe("task.created", lambda event: calls.append(event.name))

        await bus.publish(make_event())

        assert calls == ["task.created"]

    async def test_failing_handler_is_isolated(self) -> None:
        bus = EventBus()
        calls: list[str] = []

        async def broken(event: DomainEvent) -> None:
            raise RuntimeError("boom")

        bus.subscribe("task.created", broken)
        bus.subscribe("task.created", lambda event: calls.append(event.name))

        failures = await bus.publish(make_event())

        assert len(failures) == 1
        assert isinstance(failures[0][1], RuntimeError)
        assert calls == ["task.created"]

    async def test_publish_without_subscribers_is_noop(self) -> None:
        bus = EventBus()
        assert await bus.publish(make_event()) == []

    async def test_unsubscribe(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        subscription = bus.subscribe("task.created", lambda event: calls.append(event.name))

        assert bus.unsubscribe(subscription) is True
        await bus.publish(make_event())

        assert calls == []
        assert bus.unsubscribe(subscription) is False

    async def test_subscription_count(self) -> None:
        bus = EventBus()
        bus.subscribe("task.created", lambda event: None)
        bus.subscribe("task.updated", lambda event: None)
        bus.subscribe_all(lambda event: None)

        assert bus.subscription_count == 3
        assert bus.event_names == ["task.created", "task.updated"]

        bus.clear()
        assert bus.subscription_count == 0
