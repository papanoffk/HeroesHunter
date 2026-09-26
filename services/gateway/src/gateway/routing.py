from dataclasses import dataclass

from gateway.config import Settings


@dataclass(frozen=True, slots=True)
class Route:
    prefix: str
    upstream: str
    # Only auth works with tokens; other services get the identity headers instead.
    passes_token: bool = False


def build_routes(settings: Settings) -> list[Route]:
    routes = [
        Route("/auth", settings.auth_url, passes_token=True),
        Route("/v1/heroes", settings.heroes_url),
        Route("/v1/corporations", settings.corporations_url),
        Route("/v1/missions", settings.missions_url),
        Route("/v1/resumes", settings.resumes_url),
        Route("/v1/notifications", settings.notifications_url),
    ]
    return sorted(routes, key=lambda route: len(route.prefix), reverse=True)


def match_route(routes: list[Route], path: str) -> Route | None:
    return next((r for r in routes if path == r.prefix or path.startswith(r.prefix + "/")), None)
