"""In-process relay that streams an agent-uploaded artifact straight to a
waiting client — a proxy pipe from the agent's HTTP upload to the browser's
download, with no disk buffering.

The download request registers a bounded queue for its agent job id and returns
a StreamingResponse that drains it. The agent's `POST /jobs/{id}/artifact`
handler pushes body chunks into that same queue. A bounded queue gives
backpressure: if the browser is slow, the queue fills and the agent upload
blocks, which in turn throttles `borg extract`.

If the download consumer goes away (client disconnect, timeout, error), the
channel is marked dead and drained so a producer blocked in `queue.put()` wakes
up immediately; `push()`/`close()` then report the consumer is gone so the
upload handler stops relaying instead of hanging forever.

Single-worker only (gunicorn --workers 1), which is how the server runs; both
sides share one event loop. With multiple workers the two requests could land
in different processes and would need a shared medium instead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

# Bytes chunk marker for a clean end-of-stream; an error carries a message.
_EOF = object()


@dataclass
class _Channel:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=16))
    error: Optional[str] = None
    consumer_gone: bool = False

    def drain(self) -> None:
        """Empty the queue so a producer blocked in put() wakes up."""
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class AgentArtifactRelay:
    def __init__(self) -> None:
        self._channels: dict[int, _Channel] = {}

    def register(self, job_id: int) -> None:
        """Open a channel a download consumer will drain for this job."""
        self._channels[job_id] = _Channel()

    def is_registered(self, job_id: int) -> bool:
        return job_id in self._channels

    def unregister(self, job_id: int) -> None:
        self._channels.pop(job_id, None)

    async def push(self, job_id: int, chunk: bytes) -> bool:
        """Feed one chunk to the consumer.

        Returns False if nobody is listening — either the channel was never
        registered or the consumer left (possibly while we were blocked waiting
        for queue space, which the consumer's exit drains to wake us).
        """
        channel = self._channels.get(job_id)
        if channel is None or channel.consumer_gone:
            return False
        await channel.queue.put(chunk)
        return not channel.consumer_gone

    async def close(self, job_id: int, *, error: Optional[str] = None) -> None:
        """Signal end-of-stream (or failure) to the consumer."""
        channel = self._channels.get(job_id)
        if channel is None or channel.consumer_gone:
            return
        channel.error = error
        await channel.queue.put(_EOF)

    async def stream(
        self,
        job_id: int,
        *,
        first_byte_timeout: float,
        idle_timeout: float,
    ):
        """Yield chunks for the download consumer.

        Raises TimeoutError if the first chunk does not arrive within
        `first_byte_timeout`, or if the stream stalls for `idle_timeout` between
        chunks. Raises RuntimeError if the producer closed with an error.
        """
        channel = self._channels.get(job_id)
        if channel is None:
            raise RuntimeError("artifact channel not registered")
        try:
            timeout = first_byte_timeout
            while True:
                try:
                    item = await asyncio.wait_for(channel.queue.get(), timeout=timeout)
                except asyncio.TimeoutError as exc:
                    raise TimeoutError("artifact stream timed out") from exc
                if item is _EOF:
                    if channel.error:
                        raise RuntimeError(channel.error)
                    return
                yield item
                timeout = idle_timeout
        finally:
            # The consumer is leaving (EOF, timeout, error, or client disconnect).
            # Mark the channel dead and drain it so a producer blocked in put()
            # wakes up and stops relaying instead of hanging indefinitely.
            channel.consumer_gone = True
            channel.drain()
            self.unregister(job_id)


# Module-level singleton shared by the /artifact endpoint and the download route.
agent_artifact_relay = AgentArtifactRelay()
