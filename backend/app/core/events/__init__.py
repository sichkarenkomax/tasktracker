"""In-process event bus.

Rationale (docs/architecture.md, sections 20-21):

* the platform ships its own automation foundation, so events are a first-class
  concept from the very first release;
* an in-process bus is enough for the MVP - Redis/Kafka/queues are deliberately
  postponed (section 39);
* handlers must be isolated: a failing subscriber must never break the
  publisher that produced the event.
"""

from app.core.events.bus import WILDCARD, EventBus, EventHandler, Subscription
from app.core.events.types import DomainEvent, InvalidEventName

__all__ = [
    "WILDCARD",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "InvalidEventName",
    "Subscription",
]
