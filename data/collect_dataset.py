"""Сбор датасета фильмов из Викиданных (SPARQL-запрос к query.wikidata.org).

Берутся фильмы, у которых указаны бюджет и кассовые сборы в долларах США.
Результат: data/films_raw.csv - «сырые» данные, их очистка делается в блокноте.
Запуск: python data/collect_dataset.py   (занимает 1-3 минуты)
"""
import time
from pathlib import Path

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {"Accept": "text/csv", "User-Agent": "lab4-student-dataset/1.0"}
OUT = Path(__file__).parent / "films_raw.csv"

QUERY = """
SELECT ?film (SAMPLE(?ru) AS ?title_ru) (SAMPLE(?en) AS ?title_en)
       (MIN(YEAR(?date)) AS ?year) (MAX(?budget) AS ?budget_usd) (MAX(?box) AS ?box_office_usd)
       (SAMPLE(?duration) AS ?duration_min) (SAMPLE(?countryName) AS ?country)
       (SAMPLE(?genreName) AS ?genre) (SAMPLE(?mc) AS ?metacritic)
WHERE {
  ?film wdt:P31 wd:Q11424 ; wdt:P577 ?date .
  ?film p:P2130/psv:P2130 [ wikibase:quantityAmount ?budget ; wikibase:quantityUnit wd:Q4917 ] .
  ?film p:P2142/psv:P2142 [ wikibase:quantityAmount ?box ; wikibase:quantityUnit wd:Q4917 ] .
  FILTER(YEAR(?date) >= %d && YEAR(?date) <= %d)
  OPTIONAL { ?film rdfs:label ?ru FILTER(LANG(?ru) = "ru") }
  OPTIONAL { ?film rdfs:label ?en FILTER(LANG(?en) = "en") }
  OPTIONAL { ?film wdt:P2047 ?duration }
  OPTIONAL { ?film wdt:P495 ?c . ?c rdfs:label ?countryName FILTER(LANG(?countryName) = "ru") }
  OPTIONAL { ?film wdt:P136 ?g . ?g rdfs:label ?genreName FILTER(LANG(?genreName) = "ru") }
  OPTIONAL { ?film p:P444 ?st . ?st ps:P444 ?mc ; pq:P447 wd:Q150248 }
}
GROUP BY ?film
"""


def fetch(first: int, last: int) -> str:
    for attempt in range(3):
        try:
            response = requests.get(ENDPOINT, params={"query": QUERY % (first, last)},
                                    headers=HEADERS, timeout=90)
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            # сервер иногда просит подождать (код 429) - пробуем ещё раз
            print(f"  {first}-{last}: {type(error).__name__}, повтор через 5 с")
            time.sleep(5)
    raise RuntimeError(f"Не удалось получить данные за {first}-{last}")


def main() -> None:
    header, rows = None, []
    for first in range(1980, 2025, 3):
        text = fetch(first, first + 2)
        lines = text.strip().splitlines()
        header = lines[0]
        rows += lines[1:]
        print(f"{first}-{first + 2}: {len(lines) - 1} фильмов")
        time.sleep(1)   # не нагружаем сервер
    OUT.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"Сохранено {len(rows)} строк в {OUT}")


if __name__ == "__main__":
    main()
