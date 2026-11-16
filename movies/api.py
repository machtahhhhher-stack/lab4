"""Получение данных о фильмах по API.

Источники (все бесплатные, без ключей):
  * Викиданные (wikidata.org)  - поиск фильма и факты: год, режиссёр, жанр, бюджет, оценки;
  * Википедия (REST API)       - краткое описание и постер;
  * iTunes RSS                 - топ продаж фильмов (рейтинг).
"""
import asyncio
import random
import ssl
from typing import Any
from urllib.parse import quote

import aiohttp
import certifi

from movies.errors import ApiError, NotFoundError
from movies.models import Film, FilmShort, TopItem

WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
ITUNES_TOP = "https://itunes.apple.com/{country}/rss/topmovies/limit={limit}/json"
# правила Википедии: в User-Agent нужно указать, кто делает запросы
HEADERS = {"User-Agent": "EvgrafovMoviesBot/1.0 (https://github.com/machtahhhhher-stack/lab4)"}
TIMEOUT = aiohttp.ClientTimeout(total=15)

# что в Викиданных считается фильмом (свойство P31 «это частный случай»):
# фильм, художественный фильм, мультфильм, телефильм
FILM_TYPES = ("Q11424", "Q24869", "Q202866", "Q506240")
RETRIES = 2   # сколько раз повторять запрос, если сервис просит подождать (код 429)
# у кого оценка (квалификатор P447 «оценено кем»)
RATING_SOURCES = {"Q37312": "IMDb", "Q105584": "Rotten Tomatoes", "Q150248": "Metacritic"}
USD = "http://www.wikidata.org/entity/Q4917"


class MovieApi:
    """Клиент к внешним API. Одна HTTP-сессия на всё время работы бота."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self._session is None or self._session.closed:
            # свой список сертификатов (certifi): на некоторых компьютерах системный
            # устарел, и без этого HTTPS-запросы падают с CERTIFICATE_VERIFY_FAILED
            context = ssl.create_default_context(cafile=certifi.where())
            self._session = aiohttp.ClientSession(headers=HEADERS, timeout=TIMEOUT,
                                                  connector=aiohttp.TCPConnector(ssl=context))
        for attempt in range(RETRIES + 1):
            try:
                async with self._session.get(url, params=params) as response:
                    if response.status == 429 and attempt < RETRIES:
                        # «слишком много запросов» - ждём и пробуем снова
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    if response.status == 404:
                        raise NotFoundError("Страница не найдена")
                    if response.status != 200:
                        raise ApiError(f"Сервис ответил кодом {response.status}")
                    # content_type=None: iTunes отдаёт JSON с типом text/javascript
                    return await response.json(content_type=None)
            except asyncio.TimeoutError:
                raise ApiError("Сервис не ответил вовремя, попробуйте ещё раз") from None
            except aiohttp.ClientError as error:
                raise ApiError(f"Нет связи с сервисом ({type(error).__name__})") from error
            except ValueError as error:   # пришёл не JSON
                raise ApiError("Сервис вернул непонятный ответ") from error
        raise ApiError("Сервис перегружен, попробуйте через минуту")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ---------------------------------------------------------- поиск
    async def search(self, query: str, lang: str = "ru", limit: int = 5) -> list[FilmShort]:
        query = query.strip()
        if len(query) < 2:
            raise NotFoundError("Слишком короткий запрос - нужно хотя бы 2 буквы")
        # полнотекстовый поиск Викиданных; haswbstatement оставляет только фильмы
        only_films = "|".join(f"P31={t}" for t in FILM_TYPES)
        found = await self._get_json(WIKIDATA, {
            "action": "query", "list": "search", "srsearch": f"{query} haswbstatement:{only_films}",
            "srlimit": limit, "srnamespace": 0, "format": "json"})
        ids = [item["title"] for item in found.get("query", {}).get("search", [])]
        if not ids:
            raise NotFoundError(f"По запросу «{query}» фильмов не найдено")
        # названия и короткие описания - одним запросом
        entities = await self._entities(ids, props="labels|descriptions", lang=lang)
        return [FilmShort(i, label(entities.get(i, {}), lang) or i,
                          description(entities.get(i, {}), lang)) for i in ids]

    # ---------------------------------------------------------- карточка
    async def film(self, film_id: str, lang: str = "ru") -> Film:
        data = await self._entities([film_id], props="labels|claims|sitelinks", lang=lang)
        if film_id not in data or "missing" in data[film_id]:
            raise NotFoundError("Фильм не найден")
        entity = data[film_id]
        claims = entity.get("claims", {})

        directors = item_ids(claims, "P57")
        genres = item_ids(claims, "P136")[:4]
        countries = item_ids(claims, "P495")
        # одним запросом получаем названия режиссёров, жанров и стран
        names = await self._labels(directors + genres + countries, lang)

        film = Film(
            id=film_id,
            title=label(entity, lang) or film_id,
            year=earliest_year(claims),
            directors=[names.get(i, i) for i in directors],
            genres=[names.get(i, i) for i in genres],
            countries=[names.get(i, i) for i in countries],
            duration=first_amount(claims, "P2047"),
            budget=usd_amount(claims, "P2130"),
            box_office=usd_amount(claims, "P2142"),
            ratings=ratings(claims, list(RATING_SOURCES)),
            imdb_id=first_string(claims, "P345"),
        )
        sitelink = entity.get("sitelinks", {}).get(f"{lang}wiki")
        if sitelink:
            await self._add_wikipedia(film, lang, sitelink["title"])
        return film

    async def _add_wikipedia(self, film: Film, lang: str, title: str) -> None:
        """Описание и постер из Википедии. Если не получилось - карточка
        всё равно покажется, просто без описания."""
        try:
            page = await self._get_json(WIKIPEDIA_SUMMARY.format(lang=lang, title=quote(title)))
        except (ApiError, NotFoundError):
            return
        film.summary = page.get("extract", "")
        film.poster = page.get("originalimage", page.get("thumbnail", {})).get("source", "")
        film.wiki_url = page.get("content_urls", {}).get("desktop", {}).get("page", "")

    # ---------------------------------------------------------- топ
    async def top(self, country: str = "ru", limit: int = 10) -> list[TopItem]:
        data = await self._get_json(ITUNES_TOP.format(country=country, limit=limit))
        entries = data.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):   # если в топе один фильм, iTunes присылает не список
            entries = [entries]
        if not entries:
            raise NotFoundError("Топ сейчас пуст")
        return [TopItem(place=i,
                        title=e.get("im:name", {}).get("label", "?"),
                        genre=e.get("category", {}).get("attributes", {}).get("label", ""),
                        year=e.get("im:releaseDate", {}).get("label", "")[:4],
                        link=e.get("id", {}).get("label", ""))
                for i, e in enumerate(entries, start=1)]

    async def random_film(self, lang: str = "ru") -> Film:
        """Случайный фильм из топа iTunes - сразу с полной карточкой."""
        items = await self.top(limit=25)
        random.shuffle(items)
        for item in items[:5]:   # не каждый фильм из топа есть в Викиданных
            try:
                found = await self.search(item.title, lang, limit=1)
                return await self.film(found[0].id, lang)
            except NotFoundError:
                continue
        raise NotFoundError("Не удалось подобрать фильм, попробуйте ещё раз")

    # ---------------------------------------------------------- служебное
    async def _entities(self, ids: list[str], props: str, lang: str = "ru") -> dict[str, Any]:
        if not ids:
            return {}
        data = await self._get_json(WIKIDATA, {
            "action": "wbgetentities", "ids": "|".join(ids[:50]), "props": props,
            "languages": "|".join(languages(lang)),
            "sitefilter": f"{lang}wiki", "format": "json"})
        return data.get("entities", {})

    async def _labels(self, ids: list[str], lang: str) -> dict[str, str]:
        entities = await self._entities(list(dict.fromkeys(ids)), props="labels", lang=lang)
        return {i: label(e, lang) or i for i, e in entities.items()}


# ---------------------------------------------------------- разбор ответа Викиданных
# Ответ Викиданных устроен так: claims["P57"] - список утверждений,
# у каждого mainsnak.datavalue.value - само значение.

def values(claims: dict, prop: str) -> list[Any]:
    result = []
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if value is not None:
            result.append(value)
    return result


def item_ids(claims: dict, prop: str) -> list[str]:
    return [v["id"] for v in values(claims, prop) if isinstance(v, dict) and "id" in v]


def languages(lang: str) -> list[str]:
    """Нужный язык + запасные: «mul» (общая подпись для всех языков - так теперь
    хранятся имена людей) и английский. Повторы API не принимает, поэтому убираем."""
    return list(dict.fromkeys([lang, "mul", "en"]))


def label(entity: dict, lang: str) -> str:
    labels = entity.get("labels", {})
    for code in languages(lang):
        if code in labels:
            return labels[code]["value"]
    return ""


def description(entity: dict, lang: str) -> str:
    descriptions = entity.get("descriptions", {})
    for code in languages(lang):
        if code in descriptions:
            return descriptions[code]["value"]
    return ""


def earliest_year(claims: dict) -> int | None:
    # даты выглядят так: "+2014-10-26T00:00:00Z"
    years = [int(v["time"][1:5]) for v in values(claims, "P577") if isinstance(v, dict) and "time" in v]
    return min(years) if years else None


def first_amount(claims: dict, prop: str) -> int | None:
    amounts = [float(v["amount"]) for v in values(claims, prop) if isinstance(v, dict) and "amount" in v]
    return round(amounts[0]) if amounts else None


def usd_amount(claims: dict, prop: str) -> float | None:
    """Бюджет и сборы указаны в разных валютах - берём только доллары, максимум."""
    amounts = [float(v["amount"]) for v in values(claims, prop)
               if isinstance(v, dict) and v.get("unit") == USD]
    return max(amounts) if amounts else None


def first_string(claims: dict, prop: str) -> str:
    strings = [v for v in values(claims, prop) if isinstance(v, str)]
    return strings[0] if strings else ""


def ratings(claims: dict, sources: list[str]) -> dict[str, str]:
    """Оценки (свойство P444) с указанием, кто оценил (квалификатор P447)."""
    result: dict[str, str] = {}
    for claim in claims.get("P444", []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        for qualifier in claim.get("qualifiers", {}).get("P447", []):
            source = qualifier.get("datavalue", {}).get("value", {}).get("id")
            if source in sources and isinstance(value, str):
                result.setdefault(RATING_SOURCES[source], value)   # первая оценка источника
    return result
