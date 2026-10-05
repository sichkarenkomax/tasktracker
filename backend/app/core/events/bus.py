"""Async-first in-process event bus."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from app.core.events.types import DomainEvent

logger = logging.getLogger(__name__)

#: Subscribes to every event; used by Core (Activity, Notifications).
WILDCARD = "*"

type EventHandler = Callable[[DomainEvent], Any | Awaitable[Any]]
type HandlerFailure = tuple[str, BaseException]


@dataclass(frozen=True, slots=True)
class Subscription:
    event_name: str
    handler: EventHandler
    owner: str | None = None

    @property
    def label(self) -> str:
        if self.owner:
            return self.owner
        name = getattr(self.handler, "__qualname__", None)
        return str(name) if name else type(self.handler).__name__


class EventBus:
    def __init__(self) -> None:
        self._by_name: dict[str, list[Subscription]] = {}
        self._wildcard: list[Subscription] = []

    # -- registration ------------------------------------------------------
    def subscribe(
        self,
        event_name: str,
        handler: EventHandler,
        *,
        owner: str | None = None,
    ) -> Subscription:
        subscription = Subscription(event_name=event_name, handler=handler, owner=owner)
        self._by_name.setdefault(event_name, []).append(subscription)
        logger.debug("event.subscribe event=%s handler=%s", event_name, subscription.label)
        return subscription

    def subscribe_all(self, handler: EventHandler, *, owner: str | None = None) -> Subscription:
        subscription = Subscription(event_name=WILDCARD, handler=handler, owner=owner)
        self._wildcard.append(subscription)
        logger.debug("event.subscribe event=%s handler=%s", WILDCARD, subscription.label)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> bool:
        if subscription.event_name == WILDCARD:
            if subscription in self._wildcard:
                self._wildcard.remove(subscription)
                return True
            return False
        bucket = self._by_name.get(subscription.event_name)
        if bucket and subscription in bucket:
            bucket.remove(subscription)
            if not bucket:
                del self._by_name[subscription.event_name]
            return True
        return False

    # -- inspection --------------------------------------------------------
    def subscribers(self, event_name: str) -> list[Subscription]:
        return [*self._wildcard, *self._by_name.get(event_name, ())]

    @property
    def event_names(self) -> list[str]:
        return sorted(self._by_name)

    @property
    def subscription_count(self) -> int:
        return len(self._wildcard) + sum(len(bucket) for bucket in self._by_name.values())

    # -- dispatch ----------------------------------------------------------
    async def publish(self, event: DomainEvent) -> list[HandlerFailure]:
        """Deliver `event` to all matching handlers.

        Returns the list of failures instead of raising, so that publishing is
        never able to break the business transaction that produced the event.
        """
        targets = self.subscribers(event.name)
        if not targets:
            logger.debug("event.dropped name=%s reason=no_subscribers", event.name)
            return []

        logger.debug("event.dispatch name=%s subscribers=%d", event.name, len(targets))
        results = await asyncio.gather(
            *(self._invoke(subscription, event) for subscription in targets),
            return_exceptions=True,
        )

        failures: list[HandlerFailure] = []
        for subscription, result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                failures.append((subscription.label, result))
                logger.error(
                    "event.handler_failed event=%s handler=%s",
                    event.name,
                    subscription.label,
                    exc_info=result,
                )
        return failures

    def clear(self) -> None:
        self._by_name.clear()
        self._wildcard.clear()

    @staticmethod
    async def _invoke(subscription: Subscription, event: DomainEvent) -> None:
        result = subscription.handler(event)
        if inspect.isawaitable(result):
            await result


def subscribe_many(
    bus: EventBus,
    pairs: Iterable[tuple[str, EventHandler]],
    *,
    owner: str | None = None,
) -> list[Subscription]:
    return [bus.subscribe(name, handler, owner=owner) for name, handler in pairs]
