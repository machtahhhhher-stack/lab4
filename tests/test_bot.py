"""Тесты бота без интернета и без Telegram: API и сообщения подменяются заглушками."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from movies import handlers, keyboards, texts
from movies.api import earliest_year, label, languages, ratings, usd_amount
from movies.errors import ApiError, NotFoundError, StorageError
from movies.models import Film, FilmShort, TopItem
from movies.storage import FAVORITES_LIMIT, UserSettings, UserStore

MATRIX = Film(id="Q83495", title="Матрица", year=1999, directors=["Лана Вачовски", "Лилли Вачовски"],
              genres=["киберпанк"], countries=["США"], duration=136, budget=63e6, box_office=467_222_728,
              ratings={"IMDb": "8.7/10"}, imdb_id="tt0133093", summary="Фильм о <хакере> & машинах.",
              poster="https://example.com/p.jpg", wiki_url="https://ru.wikipedia.org/wiki/Матрица")


def fake_message(text: str = "", user_id: int = 1) -> MagicMock:
    """Сообщение-заглушка: answer и answer_photo запоминают, как их вызвали."""
    message = MagicMock()
    message.text = text
    message.from_user.id = user_id
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock()
    return message


def fake_api() -> MagicMock:
    api = MagicMock()
    api.search = AsyncMock(return_value=[FilmShort("Q83495", "Матрица", "фильм 1999"),
                                         FilmShort("Q207536", "Матрица: Революция", "фильм 2003")])
    api.film = AsyncMock(return_value=MATRIX)
    api.top = AsyncMock(return_value=[TopItem(1, "Крёстный отец", "Драма", "1972")])
    api.random_film = AsyncMock(return_value=MATRIX)
    return api


class TestWikidataParsing(unittest.TestCase):
    """Разбор ответа Викиданных на маленьких примерах в его формате."""

    def test_earliest_year(self):
        claims = {"P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2014-11-06T00:00:00Z"}}}},
                           {"mainsnak": {"datavalue": {"value": {"time": "+2014-10-26T00:00:00Z"}}}}]}
        self.assertEqual(earliest_year(claims), 2014)
        self.assertIsNone(earliest_year({}))

    def test_usd_only(self):
        usd = "http://www.wikidata.org/entity/Q4917"
        claims = {"P2142": [{"mainsnak": {"datavalue": {"value": {"amount": "+100", "unit": usd}}}},
                            {"mainsnak": {"datavalue": {"value": {"amount": "+999", "unit": "rub"}}}},
                            {"mainsnak": {"datavalue": {"value": {"amount": "+300", "unit": usd}}}}]}
        self.assertEqual(usd_amount(claims, "P2142"), 300)

    def test_ratings(self):
        claims = {"P444": [
            {"mainsnak": {"datavalue": {"value": "8.7/10"}},
             "qualifiers": {"P447": [{"datavalue": {"value": {"id": "Q37312"}}}]}},
            {"mainsnak": {"datavalue": {"value": "73/100"}},
             "qualifiers": {"P447": [{"datavalue": {"value": {"id": "Q150248"}}}]}}]}
        self.assertEqual(ratings(claims, ["Q37312", "Q150248"]), {"IMDb": "8.7/10", "Metacritic": "73/100"})

    def test_label_fallback(self):
        entity = {"labels": {"mul": {"value": "Christopher Nolan"}}}
        self.assertEqual(label(entity, "ru"), "Christopher Nolan")
        self.assertEqual(label({}, "ru"), "")
        self.assertEqual(languages("en"), ["en", "mul"])


class TestTexts(unittest.TestCase):

    def test_money_and_duration(self):
        self.assertEqual(texts.money(63e6), "$63 млн")
        self.assertEqual(texts.money(1.5e9), "$1,50 млрд")
        self.assertEqual(texts.money(None), "—")
        self.assertEqual(texts.duration(136), "2 ч 16 мин")
        self.assertEqual(texts.duration(45), "45 мин")

    def test_card_escapes_html(self):
        card = texts.film_card(MATRIX)
        self.assertIn("<b>Матрица</b> (1999)", card)
        self.assertIn("&lt;хакере&gt; &amp;", card)   # спецсимволы экранированы
        self.assertIn("IMDb 8.7/10", card)

    def test_card_fits_caption_limit(self):
        long_film = Film(id="Q1", title="Длинный", summary="слово " * 1000)
        self.assertLessEqual(len(texts.film_card(long_film, texts.CAPTION_LIMIT)), texts.CAPTION_LIMIT)


class TestStorage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "users.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_settings_survive_restart(self):
        store = UserStore(self.path)
        user = store.get(42)
        user.lang, user.results = "en", 10
        user.toggle_favorite("Q83495", "Матрица")
        store.save()
        again = UserStore(self.path).get(42)   # «перезапуск» бота
        self.assertEqual((again.lang, again.results), ("en", 10))
        self.assertIn("Q83495", again.favorites)

    def test_broken_file(self):
        self.path.write_text("{ сломано", encoding="utf-8")
        store = UserStore(self.path)
        self.assertIsNotNone(store.warning)
        self.assertEqual(store.users, {})
        self.assertTrue(self.path.with_suffix(".broken.json").exists())

    def test_history_without_repeats(self):
        user = UserSettings()
        for query in ["матрица", "аватар", "матрица"]:
            user.remember_query(query)
        self.assertEqual(user.history, ["матрица", "аватар"])

    def test_favorites_limit(self):
        user = UserSettings(favorites={f"Q{i}": "x" for i in range(FAVORITES_LIMIT)})
        with self.assertRaises(StorageError):
            user.toggle_favorite("Q999", "лишний")

    def test_cycles(self):
        user = UserSettings()
        self.assertEqual(user.next_lang(), "en")
        self.assertEqual(user.next_lang(), "ru")
        self.assertEqual([user.next_results() for _ in range(3)], [10, 3, 5])


class TestKeyboards(unittest.TestCase):

    def test_callback_data_fits_telegram_limit(self):
        long_title = "Очень длинное название фильма " * 5
        markup = keyboards.top_buttons([TopItem(1, long_title)])
        data = markup.inline_keyboard[0][0].callback_data
        self.assertLessEqual(len(data.encode("utf-8")), 64)

    def test_film_buttons(self):
        markup = keyboards.film_buttons(MATRIX, is_favorite=True)
        self.assertIn("Убрать", markup.inline_keyboard[0][0].text)
        urls = [b.url for b in markup.inline_keyboard[1]]
        self.assertIn("https://www.imdb.com/title/tt0133093/", urls)


class TestHandlers(unittest.IsolatedAsyncioTestCase):
    """Обработчики - обычные async-функции, вызываем их напрямую."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = UserStore(Path(self.tmp.name) / "users.json")
        self.api = fake_api()

    def tearDown(self):
        self.tmp.cleanup()

    async def test_search_shows_list(self):
        message = fake_message("матрица")
        await handlers.text_search(message, self.api, self.store)
        self.api.search.assert_awaited_once_with("матрица", "ru", limit=5)
        self.assertIn("Нашлось фильмов: 2", message.answer.await_args.args[0])
        self.assertEqual(self.store.get(1).history, ["матрица"])   # запрос запомнился

    async def test_single_result_opens_card_with_poster(self):
        self.api.search.return_value = [FilmShort("Q83495", "Матрица")]
        message = fake_message("матрица 1999")
        await handlers.text_search(message, self.api, self.store)
        message.answer_photo.assert_awaited_once()
        self.assertIn("Матрица", message.answer_photo.await_args.kwargs["caption"])

    async def test_card_without_posters_setting(self):
        self.store.get(1).posters = False
        self.api.search.return_value = [FilmShort("Q83495", "Матрица")]
        message = fake_message("матрица")
        await handlers.text_search(message, self.api, self.store)
        message.answer_photo.assert_not_awaited()
        message.answer.assert_awaited_once()

    async def test_user_language_is_used(self):
        self.store.get(1).lang = "en"
        await handlers.text_search(fake_message("matrix"), self.api, self.store)
        self.assertEqual(self.api.search.await_args.args[1], "en")

    async def test_search_command_without_args(self):
        message = fake_message("/search")
        await handlers.cmd_search(message, MagicMock(args=None), self.api, self.store)
        self.assertIn("Напишите название", message.answer.await_args.args[0])
        self.api.search.assert_not_awaited()

    async def test_top(self):
        message = fake_message()
        await handlers.cmd_top(message, self.api)
        self.assertIn("Крёстный отец", message.answer.await_args.args[0])

    async def test_favorite_button(self):
        callback = MagicMock(data="fav:Q83495", answer=AsyncMock())
        callback.from_user.id = 7
        callback.message.edit_reply_markup = AsyncMock()
        await handlers.cb_favorite(callback, self.api, self.store)
        self.assertIn("Q83495", self.store.get(7).favorites)
        self.assertIn("Добавлено", callback.answer.await_args.args[0])

    async def test_settings_button(self):
        callback = MagicMock(data="set:results", answer=AsyncMock())
        callback.from_user.id = 7
        callback.message.edit_text = AsyncMock()
        await handlers.cb_settings(callback, self.store)
        self.assertEqual(self.store.get(7).results, 10)
        saved = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["7"]["results"], 10)   # настройка сохранилась в файл

    async def test_error_handler(self):
        for error, expected in [(NotFoundError("ничего нет"), "ничего нет"),
                                (ApiError("таймаут"), "недоступен"),
                                (ZeroDivisionError(), "что-то пошло не так")]:
            with self.subTest(error=type(error).__name__):
                message = fake_message()
                event = MagicMock(exception=error)
                event.update.message = message
                event.update.callback_query = None
                with self.assertLogs(level="ERROR") if isinstance(error, ZeroDivisionError) else _nothing():
                    self.assertTrue(await handlers.on_error(event))
                self.assertIn(expected, message.answer.await_args.args[0].lower())


class _nothing:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    unittest.main()
