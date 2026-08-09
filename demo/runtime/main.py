import uvicorn

from demo.runtime.app import create_runtime_app
from demo.runtime.settings import ReferenceRuntimeSettings


def main() -> None:
    settings = ReferenceRuntimeSettings()
    uvicorn.run(
        create_runtime_app(settings),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
