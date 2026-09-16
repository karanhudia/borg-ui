import asyncio

import pytest

from app.services.agent_artifact_relay import AgentArtifactRelay


@pytest.mark.unit
async def test_relay_streams_chunks_then_unregisters():
    relay = AgentArtifactRelay()
    relay.register(1)

    async def produce():
        await relay.push(1, b"hello ")
        await relay.push(1, b"world")
        await relay.close(1)

    task = asyncio.create_task(produce())
    chunks = [
        chunk async for chunk in relay.stream(1, first_byte_timeout=1, idle_timeout=1)
    ]
    await task

    assert b"".join(chunks) == b"hello world"
    assert not relay.is_registered(1)


@pytest.mark.unit
async def test_relay_first_byte_timeout():
    relay = AgentArtifactRelay()
    relay.register(2)

    with pytest.raises(TimeoutError):
        async for _ in relay.stream(2, first_byte_timeout=0.05, idle_timeout=0.05):
            pass

    assert not relay.is_registered(2)


@pytest.mark.unit
async def test_relay_error_close_raises_after_first_chunk():
    relay = AgentArtifactRelay()
    relay.register(3)
    await relay.push(3, b"partial")
    await relay.close(3, error="boom")

    gen = relay.stream(3, first_byte_timeout=1, idle_timeout=1)
    assert await gen.__anext__() == b"partial"
    with pytest.raises(RuntimeError, match="boom"):
        await gen.__anext__()
    assert not relay.is_registered(3)


@pytest.mark.unit
async def test_relay_close_reports_whether_a_consumer_was_listening():
    relay = AgentArtifactRelay()
    # Never registered: nobody to tell.
    assert await relay.close(7) is False

    relay.register(8)
    gen = relay.stream(8, first_byte_timeout=1, idle_timeout=1)
    consumer = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0)
    # The consumer is waiting; an empty stream's close is its only event.
    assert await relay.close(8, confirm_timeout=1) is True
    with pytest.raises(StopAsyncIteration):
        await consumer
    assert not relay.is_registered(8)

    # The consumer times out in the same tick the marker is queued: with a
    # confirmation asked for, the enqueue alone is not a delivery.
    relay.register(12)
    gen = relay.stream(12, first_byte_timeout=0.05, idle_timeout=1)
    consumer = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0.06)  # past the timeout, before the task ran on
    assert await relay.close(12, confirm_timeout=1) is False
    with pytest.raises(TimeoutError):
        await consumer

    # A failure claims no delivery.
    relay.register(11)
    gen = relay.stream(11, first_byte_timeout=1, idle_timeout=1)
    consumer = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0)
    assert await relay.close(11, error="boom") is False
    with pytest.raises(RuntimeError, match="boom"):
        await consumer

    # The consumer left (timed out) before the producer closed.
    relay.register(9)
    with pytest.raises(TimeoutError):
        async for _ in relay.stream(9, first_byte_timeout=0.01, idle_timeout=1):
            pass
    assert await relay.close(9) is False


@pytest.mark.unit
async def test_relay_close_woken_by_a_leaving_consumer_reports_no_delivery():
    # close() blocks on a full queue like push() does; when the consumer
    # leaves, its exit drains the queue and wakes the put. That wake-up is
    # not a delivery.
    relay = AgentArtifactRelay()
    relay.register(10)
    for _ in range(16):
        assert await relay.push(10, b"x") is True

    closing = asyncio.create_task(relay.close(10))
    await asyncio.sleep(0.01)
    assert not closing.done()

    # What the consumer's exit does, in this order and without a get in
    # between: a get would free a slot and wake the put on its own, and
    # whether that wake-up or the departure lands first depends on the
    # Python version's wait_for.
    channel = relay._channels[10]
    channel.consumer_gone = True
    channel.drain()
    relay.unregister(10)

    assert await asyncio.wait_for(closing, timeout=1) is False
    assert not relay.is_registered(10)


@pytest.mark.unit
async def test_relay_close_answers_within_its_bound_for_a_stalled_consumer():
    # A consumer that stalls: the marker sits behind chunks it has not
    # taken. With a confirmation asked for, the close answers no within
    # its bound (nothing was confirmed) rather than holding the agent's
    # upload request.
    relay = AgentArtifactRelay()
    relay.register(13)
    await relay.push(13, b"chunk")
    gen = relay.stream(13, first_byte_timeout=1, idle_timeout=1)
    assert await gen.__anext__() == b"chunk"  # then the consumer stalls

    started = asyncio.get_running_loop().time()
    assert await relay.close(13, confirm_timeout=0.05) is False
    # It waited the bound out, and no longer.
    assert 0.04 <= asyncio.get_running_loop().time() - started < 1

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert not relay.is_registered(13)

    # The put itself is bounded too: a full queue nobody drains answers
    # within the bound, and the marker is not queued.
    relay.register(14)
    for _ in range(16):
        assert await relay.push(14, b"x") is True
    started = asyncio.get_running_loop().time()
    assert await relay.close(14, confirm_timeout=0.05) is False
    assert asyncio.get_running_loop().time() - started < 1
    assert relay.is_registered(14)

    # One bound for the whole confirmation: a consumer that frees a slot
    # late and then stalls does not buy the wait a second bound.
    relay.register(16)
    for _ in range(16):
        assert await relay.push(16, b"x") is True
    started = asyncio.get_running_loop().time()
    closing = asyncio.create_task(relay.close(16, confirm_timeout=0.4))
    await asyncio.sleep(0.3)
    gen16 = relay.stream(16, first_byte_timeout=1, idle_timeout=5)
    assert await gen16.__anext__() == b"x"  # frees the slot, then stalls
    assert await closing is False
    assert asyncio.get_running_loop().time() - started < 0.6
    await gen16.aclose()

    # A download's close waits for its reader as push() does, and answers
    # from the consumer's presence once the marker is queued.
    relay.register(15)
    await relay.push(15, b"chunk")
    gen = relay.stream(15, first_byte_timeout=1, idle_timeout=1)
    assert await gen.__anext__() == b"chunk"
    assert await relay.close(15) is True
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


@pytest.mark.unit
async def test_relay_push_without_consumer_returns_false():
    relay = AgentArtifactRelay()
    assert await relay.push(99, b"x") is False


@pytest.mark.unit
async def test_relay_push_after_consumer_leaves_returns_false():
    relay = AgentArtifactRelay()
    relay.register(4)

    push_task = asyncio.create_task(relay.push(4, b"data"))
    gen = relay.stream(4, first_byte_timeout=1, idle_timeout=1)
    assert await gen.__anext__() == b"data"
    await push_task
    await gen.aclose()  # consumer leaves

    # Channel is dead now — further pushes report it and do not hang.
    assert await relay.push(4, b"more") is False
    assert not relay.is_registered(4)


@pytest.mark.unit
async def test_relay_unblocks_producer_when_consumer_leaves():
    relay = AgentArtifactRelay()
    relay.register(5)
    for _ in range(16):  # fill the queue to maxsize
        assert await relay.push(5, b"x") is True

    blocked = asyncio.create_task(relay.push(5, b"y"))  # blocks on a full queue
    await asyncio.sleep(0.01)
    assert not blocked.done()

    gen = relay.stream(5, first_byte_timeout=1, idle_timeout=1)
    await gen.__anext__()
    await gen.aclose()  # consumer leaves -> drains + marks the channel dead

    # The blocked producer must wake up rather than hang forever.
    result = await asyncio.wait_for(blocked, timeout=1)
    assert result in (True, False)
    assert not relay.is_registered(5)
