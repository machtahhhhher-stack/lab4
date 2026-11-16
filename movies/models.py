"""Классы данных: фильм из поиска, полная карточка фильма, место в топе."""
from dataclasses import dataclass, field


@dataclass
class FilmShort:
    """Строчка в результатах поиска."""
    id: str            # идентификатор в Викиданных, например Q13417189
    title: str
    description: str = ""

    def __str__(self) -> str:
        return f"{self.title} — {self.description}" if self.description else self.title


@dataclass
class Film:
    """Полная информация о фильме."""
    id: str
    title: str
    year: int | None = None
    directors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    duration: int | None = None          # минуты
    budget: float | None = None          # доллары США
    box_office: float | None = None      # доллары США
    ratings: dict[str, str] = field(default_factory=dict)   # {"IMDb": "8,7/10"}
    imdb_id: str = ""
    summary: str = ""                    # краткое описание из Википедии
    poster: str = ""                     # ссылка на картинку
    wiki_url: str = ""

    @property
    def imdb_url(self) -> str:
        return f"https://www.imdb.com/title/{self.imdb_id}/" if self.imdb_id else ""

    @property
    def wikidata_url(self) -> str:
        return f"https://www.wikidata.org/wiki/{self.id}"


@dataclass
class TopItem:
    """Позиция в топе продаж iTunes."""
    place: int
    title: str
    genre: str = ""
    year: str = ""
    link: str = ""
