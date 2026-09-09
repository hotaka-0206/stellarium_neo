import uvicorn

from api.server import app


def run_backend(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    uvicorn.run(
        app,
        host=host,
        port=port,
    )


def main() -> None:
    run_backend()


if __name__ == "__main__":
    main()