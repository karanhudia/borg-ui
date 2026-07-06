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
