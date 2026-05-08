from uvicorn import run

from ..config import load_settings
from .service import create_agent_app


def main() -> None:
    app = create_agent_app()
    settings = load_settings()
    run(app, host=settings.agent.host, port=settings.agent.port)


if __name__ == "__main__":
    main()
