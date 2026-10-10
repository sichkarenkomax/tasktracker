"""When a person was last here (stage 2.9).

Presence is written from ordinary API traffic: a separate heartbeat endpoint
would be one more call from every client, and a client that forgets it loses
presence silently, which is worse than a presence that is a minute stale.

The throttle is the point of this module. Writing on every request turns every
read into a write, and the roster is read far more often than it changes. So the
time is kept in memory and the database is touched at most once a minute per
person - which also means one stale answer is not a lie, it is what "last seen"
has always meant.

Two consequences worth stating plainly:

* **Per process.** Two workers behind a load balancer can each write once a
  minute, so a busy deployment sees up to one write per worker per minute. That
  is the price of not adding a heartbeat endpoint, and it is cheaper than the
  database traffic it replaces.
* **Best effort by design.** A write that fails (a closed connection, a read
  replica being restarted) is not retried and does not fail the request. Presence
  is the least important thing the request was doing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.users.models import User

#: How long a "last seen" is good enough not to write a new one. One minute is
#: short enough that the roster is honest and long enough that browsing the task
#: list does not turn into a write per row rendered.
THROTTLE_SECONDS = 60.0

#: Being seen within this window means "here now" (stage 2.9). Five minutes is
#: the usual answer and it is deliberately longer than the throttle: a person who
#: is working in one tab and reading in another should not flicker offline
#: between the two.
ONLINE_WINDOW = timedelta(minutes=5)


class PresenceTracker:
    """Remembers who was written recently enough to skip.

    A plain dict, not a cache with an eviction policy: it holds one float per
    person who made a request in the last minute, so it is bounded by the number
    of active users and empties itself between bursts. Entries for people who
    stop being active expire by being ignored, which costs one stale key each.
    """

    def __init__(self) -> None:
        self._written: dict[UUID, float] = {}

    def due(self, user_id: UUID) -> bool:
        """Whether this person is due a write right now."""
        last = self._written.get(user_id)
        return last is None or monotonic() - last >= THROTTLE_SECONDS

    def mark_written(self, user_id: UUID) -> None:
        self._written[user_id] = monotonic()

    def forget(self, user_id: UUID) -> None:
        """Drop the mark, so the next request writes again.

        For the tests, which need to start from "due" rather than from whatever
        the previous test left behind, and for a caller that has just written a
        corrected timestamp by hand.
        """
        self._written.pop(user_id, None)


#: One tracker for the process. The alternative - a new one per request - would
#: throttle nothing at all.
tracker = PresenceTracker()


def is_online(last_seen: datetime | None, *, now: datetime | None = None) -> bool:
    """Whether a person counts as here now.

    A person who has never been seen is not online, and neither is one seen just
    before the clock moved: the comparison is against an aware UTC timestamp, and
    a naive one would raise here instead of quietly answering.
    """
    if last_seen is None:
        return False
    moment = now or datetime.now(UTC)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    return moment - last_seen <= ONLINE_WINDOW


async def record(user: User, session: AsyncSession) -> None:
    """Note that this person is here, at most once a minute.

    Takes the ``User`` and the request's session rather than the pieces it needs,
    so the caller stays one line and this module owns the whole policy. The write
    is a plain attribute assignment followed by a commit: the column is one
    timestamp on a row the request already holds, and an UPDATE that re-reads it
    would buy nothing but a chance to disagree with itself.

    The tracker is marked *before* the commit rather than after it, so a failure
    leaves the person due again instead of being marked as seen for a timestamp
    that was never written.
    """
    if not tracker.due(user.id):
        return
    user.last_seen = datetime.now(UTC)
    await session.commit()
    tracker.mark_written(user.id)
