from uvicorn import run

from .api import create_app
from .config import load_settings


def main() -> None:
    app = create_app()
    settings = load_settings()
    run(app, host=settings.gateway.host, port=settings.gateway.port)


if __name__ == "__main__":
    main()
