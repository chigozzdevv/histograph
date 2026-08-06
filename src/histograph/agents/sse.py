from collections.abc import AsyncIterator

import httpx


async def iter_sse_data(response: httpx.Response) -> AsyncIterator[str]:
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines.clear()
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if field == "data":
            data_lines.append(value[1:] if separator and value.startswith(" ") else value)
    if data_lines:
        yield "\n".join(data_lines)
