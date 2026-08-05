from fastapi import Request


def request_id(request: Request) -> str:
    return request.state.request_id


def source_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else None
