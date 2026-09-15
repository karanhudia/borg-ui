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

# How long `close(confirm_timeout=...)` waits for the consumer to take the
# end marker before it answers no. The in-process consumer of a listing
# takes it at once, and the agent's upload request, whose own read timeout
# is far longer than this, must not be held for a consumer that stalled.
CLOSE_ACK_TIMEOUT_SECONDS = 5.0


@dataclass
class _Channel:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=16))
    error: Optional[str] = None
    consumer_gone: bool = False
    # Set once the producer called close(): what is still queued is the
    # tail of the upload, the end marker behind it.
    closing: bool = False
    # Set once the consumer took the end marker; `settled` fires when the
    # consumer is done with the channel either way.
    eof_taken: bool = False
    settled: asyncio.Event = field(default_factory=asyncio.Event)

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

    def is_closing(self, job_id: int) -> bool:
        """Whether the producer has ended the upload: the queue holds at
        most its tail and the end marker, so a consumer that paces its
        intake can take the rest at once and confirm the marker in time."""
        channel = self._channels.get(job_id)
        return channel is not None and channel.closing

    def unregister(self, job_id: int) -> None:
        channel = self._channels.pop(job_id, None)
        if channel is not None:
            channel.settled.set()

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

    async def close(
        self,
        job_id: int,
        *,
        error: Optional[str] = None,
        confirm_timeout: Optional[float] = None,
    ) -> bool:
        """Signal end-of-stream (or failure) to the consumer.

        Returns False if nobody is listening any more, like `push()`: an
        upload with no chunks (an empty output) reaches only this call, and
        its answer is the only sign the consumer was still there. The
        answer is read after the put, since a put that waited on a full
        queue may have been woken by the consumer leaving (its exit drains
        the queue) rather than by space. A failure claims no delivery.

        With `confirm_timeout` the answer is whether the consumer took the
        marker, for an upload that is worthless unless consumed: a consumer
        whose timeout expired in the same tick has taken nothing, so the
        enqueue alone is not the answer. Both the put and the wait for the
        consumer are bounded by it, and past the bound the answer is no:
        a consumer that has not taken the marker by then has confirmed
        nothing, and the agent's upload request must not be held for it.
        Without it (a download), the put waits as `push()` does, for a
        consumer that reads at its own pace.
        """
        channel = self._channels.get(job_id)
        if channel is None or channel.consumer_gone:
            return False
        channel.closing = True
        channel.error = error
        if confirm_timeout is None:
            await channel.queue.put(_EOF)
            return error is None and not channel.consumer_gone
        # One deadline for both steps: a consumer that frees a slot just
        # before it and then stalls must not buy the wait a second bound.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + confirm_timeout
        try:
            await asyncio.wait_for(channel.queue.put(_EOF), timeout=confirm_timeout)
        except asyncio.TimeoutError:
            return False
        if error is not None:
            return False
        if channel.settled.is_set():
            return channel.eof_taken
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        try:
            await asyncio.wait_for(channel.settled.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            return False
        return channel.eof_taken

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
                    channel.eof_taken = True
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
