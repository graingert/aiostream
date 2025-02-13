import pytest
import asyncio

from aiostream.test_utils import event_loop
from aiostream.aiter_utils import AsyncIteratorContext, aitercontext, anext

# Pytest fixtures
event_loop


# Some async iterators for testing


async def agen():
    for x in range(5):
        await asyncio.sleep(1)
        yield x


async def silence_agen():
    while True:
        try:
            yield 1
        except BaseException:
            return


async def reraise_agen():
    while True:
        try:
            yield 1
        except BaseException as exc:
            raise RuntimeError from exc


async def stuck_agen():
    try:
        yield 1
    except BaseException:
        yield 2


class not_an_agen(list):
    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return self.pop()
        except IndexError:
            raise StopAsyncIteration


# Tests


@pytest.mark.asyncio
async def test_simple_aitercontext(event_loop):

    async with aitercontext(agen()) as safe_gen:

        # Cannot enter twice
        with pytest.raises(RuntimeError):
            async with safe_gen:
                pass

        it = iter(range(5))
        async for item in safe_gen:
            assert item == next(it)
    assert event_loop.steps == [1] * 5

    # Exiting is idempotent
    await safe_gen.__aexit__(None, None, None)
    await safe_gen.aclose()

    with pytest.raises(RuntimeError):
        await anext(safe_gen)

    with pytest.raises(RuntimeError):
        async with safe_gen:
            pass

    with pytest.raises(RuntimeError):
        await safe_gen.athrow(ValueError())


@pytest.mark.asyncio
async def test_athrow_in_aitercontext(event_loop):
    async with aitercontext(agen()) as safe_gen:
        assert await safe_gen.__anext__() == 0
        with pytest.raises(ZeroDivisionError):
            await safe_gen.athrow(ZeroDivisionError())
        async for _ in safe_gen:
            assert False  # No more items


@pytest.mark.asyncio
async def test_aitercontext_wrong_usage(event_loop):
    safe_gen = aitercontext(agen())
    with pytest.warns(UserWarning):
        await anext(safe_gen)

    with pytest.raises(TypeError):
        AsyncIteratorContext(None)

    with pytest.raises(TypeError):
        AsyncIteratorContext(safe_gen)


@pytest.mark.asyncio
async def test_raise_in_aitercontext(event_loop):
    with pytest.raises(ZeroDivisionError):
        async with aitercontext(agen()) as safe_gen:
            async for _ in safe_gen:
                1 / 0

    with pytest.raises(ZeroDivisionError):
        async with aitercontext(agen()) as safe_gen:
            async for _ in safe_gen:
                pass
            1 / 0

    with pytest.raises(GeneratorExit):
        async with aitercontext(agen()) as safe_gen:
            async for _ in safe_gen:
                raise GeneratorExit

    with pytest.raises(GeneratorExit):
        async with aitercontext(agen()) as safe_gen:
            async for _ in safe_gen:
                pass
            raise GeneratorExit


@pytest.mark.asyncio
async def test_silence_exception_in_aitercontext(event_loop):
    async with aitercontext(silence_agen()) as safe_gen:
        async for item in safe_gen:
            assert item == 1
            1 / 0

    # Silencing a generator exit is forbidden
    with pytest.raises(GeneratorExit):
        async with aitercontext(silence_agen()) as safe_gen:
            async for _ in safe_gen:
                raise GeneratorExit


@pytest.mark.asyncio
async def test_reraise_exception_in_aitercontext(event_loop):
    with pytest.raises(RuntimeError) as info:
        async with aitercontext(reraise_agen()) as safe_gen:
            async for item in safe_gen:
                assert item == 1
                1 / 0
    assert type(info.value.__cause__) is ZeroDivisionError

    with pytest.raises(RuntimeError) as info:
        async with aitercontext(reraise_agen()) as safe_gen:
            async for item in safe_gen:
                assert item == 1
                raise GeneratorExit
    assert type(info.value.__cause__) is GeneratorExit


@pytest.mark.asyncio
async def test_stuck_in_aitercontext(event_loop):
    with pytest.raises(RuntimeError) as info:
        async with aitercontext(stuck_agen()) as safe_gen:
            async for item in safe_gen:
                assert item == 1
                1 / 0
    assert "didn't stop after athrow" in str(info.value)

    with pytest.raises(RuntimeError) as info:
        async with aitercontext(stuck_agen()) as safe_gen:
            async for item in safe_gen:
                assert item == 1
                raise GeneratorExit
    # GeneratorExit relies on aclose, not athrow
    # The message is a bit different
    assert "async generator ignored GeneratorExit" in str(info.value)


@pytest.mark.asyncio
async def test_not_an_agen_in_aitercontext(event_loop):
    async with aitercontext(not_an_agen([1])) as safe_gen:
        async for item in safe_gen:
            assert item == 1

    with pytest.raises(ZeroDivisionError):
        async with aitercontext(not_an_agen([1])) as safe_gen:
            async for item in safe_gen:
                1 / 0
