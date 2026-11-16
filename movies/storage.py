"""Настройки пользователей бота: язык, число результатов, постеры,
избранное и история поиска. Хранятся в JSON-файле users.json."""
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from movies.errors import StorageError

LANGUAGES = {"ru": "Русский", "en": "English"}
RESULT_COUNTS = (3, 5, 10)
HISTORY_LIMIT = 10
FAVORITES_LIMIT = 30


@dataclass
class UserSettings:
    lang: str = "ru"
    results: int = 5                 # сколько фильмов показывать в поиске
    posters: bool = True             # присылать постер вместе с карточкой
    favorites: dict[str, str] = field(default_factory=dict)   # {id фильма: название}
    history: list[str] = field(default_factory=list)          # последние запросы

    def remember_query(self, query: str) -> None:
        if query in self.history:
            self.history.remove(query)
        self.history.insert(0, query)
        del self.history[HISTORY_LIMIT:]

    def toggle_favorite(self, film_id: str, title: str) -> bool:
        """Добавляет или убирает фильм. Возвращает True, если фильм теперь в избранном."""
        if film_id in self.favorites:
            del self.favorites[film_id]
            return False
        if len(self.favorites) >= FAVORITES_LIMIT:
            raise StorageError(f"В избранном уже {FAVORITES_LIMIT} фильмов - сначала удалите что-нибудь")
        self.favorites[film_id] = title
        return True

    def next_lang(self) -> str:
        """Переключение языка по кругу ru -> en -> ru."""
        codes = list(LANGUAGES)
        self.lang = codes[(codes.index(self.lang) + 1) % len(codes)] if self.lang in codes else "ru"
        return self.lang

    def next_results(self) -> int:
        self.results = next((n for n in RESULT_COUNTS if n > self.results), RESULT_COUNTS[0])
        return self.results


class UserStore:
    """Все пользователи: {telegram id: UserSettings}. Сохраняется после каждого изменения."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.users: dict[int, UserSettings] = {}
        self.warning = self._load()

    def _load(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(UserSettings)}
            for user_id, data in raw.items():
                self.users[int(user_id)] = UserSettings(**{k: v for k, v in data.items() if k in known})
            return None
        except (OSError, ValueError, TypeError, AttributeError) as error:
            # файл испорчен - не падаем: сохраняем копию и начинаем с чистого листа
            self.users.clear()
            backup = self.path.with_suffix(".broken.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return f"Файл {self.path.name} повреждён ({error}), начат новый (копия: {backup.name})"

    def get(self, user_id: int) -> UserSettings:
        # setdefault: если пользователя ещё нет - создаём с настройками по умолчанию
        return self.users.setdefault(user_id, UserSettings())

    def save(self) -> None:
        data = {str(uid): asdict(settings) for uid, settings in self.users.items()}
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            raise StorageError(f"Не удалось сохранить настройки: {error}") from error
