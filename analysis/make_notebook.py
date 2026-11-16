"""Собирает блокнот films_analysis.ipynb (его можно открыть в Google Colab).

Запуск: python analysis/make_notebook.py  - создаёт блокнот и выполняет его,
чтобы в нём сразу были результаты и графики.
"""
from pathlib import Path

import nbformat
from nbclient import NotebookClient

HERE = Path(__file__).parent
NB = HERE / "films_analysis.ipynb"

cells = []


def md(text: str) -> None:
    cells.append(nbformat.v4.new_markdown_cell(text.strip()))


def code(text: str) -> None:
    cells.append(nbformat.v4.new_code_cell(text.strip()))


md("""
# Анализ данных: бюджет, сборы и длительность фильмов

Лабораторная работа №4, часть «Анализ данных». Евграфов Р. А., ИДБ-25-11, вариант 7 (фильмы).

[![Открыть в Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/machtahhhhher-stack/lab4/blob/main/analysis/films_analysis.ipynb)

## 1. Постановка задачи

Тема бота — фильмы, поэтому и для анализа взяты данные о фильмах. Вопросы исследования:

1. Связаны ли **бюджет** фильма и его **кассовые сборы**? Окупаются ли дорогие фильмы лучше?
2. Как распределена **длительность** фильмов — можно ли считать распределение нормальным?
3. Связана ли **оценка критиков** (Metacritic) с коммерческим успехом фильма?

Инструменты: NumPy, Pandas, Matplotlib.
""")

md("""
## 2. Поиск данных

Набор данных собран самостоятельно из открытой базы знаний **Викиданные** (Wikidata) SPARQL-запросом
(скрипт `data/collect_dataset.py` в репозитории). Взяты фильмы 1980–2024 годов, у которых указаны
и бюджет, и кассовые сборы **в долларах США**.

| Столбец | Что означает |
|---|---|
| `film` | ссылка на фильм в Викиданных |
| `title_ru`, `title_en` | название на русском и английском |
| `year` | год выхода |
| `budget_usd` | бюджет, $ |
| `box_office_usd` | кассовые сборы, $ |
| `duration_min` | длительность, минут |
| `country`, `genre` | одна из стран производства и один из жанров |
| `metacritic` | оценка критиков Metacritic в виде строки «73/100» |
""")

code("""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams["figure.figsize"] = (9, 4.5)
plt.rcParams["axes.grid"] = True
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

URL = "https://raw.githubusercontent.com/machtahhhhher-stack/lab4/main/data/films_raw.csv"
try:
    raw = pd.read_csv("../data/films_raw.csv")   # блокнот открыт из папки проекта
except FileNotFoundError:
    raw = pd.read_csv(URL)                       # Google Colab: берём файл прямо с GitHub
print(raw.shape)
raw.head()
""")

code("""
raw.info()
""")

md("""
## 3. Подготовка данных

«Сырые» данные нужно очистить:

* **дубликаты** — фильм с несколькими датами выхода попадал в запрос несколько раз;
* **пропуски** — у части фильмов нет длительности или оценки;
* **типы** — оценка записана строкой «73/100», нужно число;
* **выбросы и ошибки** — в Викиданных встречаются опечатки (длительность 10 809 минут, бюджет 6 000 $).
""")

code("""
print("Пропуски по столбцам:")
print(raw.isna().sum())
print("\\nСтрок:", len(raw), " уникальных фильмов:", raw["film"].nunique())
""")

code("""
df = (raw.sort_values("year")
         .drop_duplicates("film", keep="first")       # оставляем самый ранний год выхода
         .copy())

# оценка "73/100" -> 73.0 (регулярное выражение достаёт число)
df["metacritic_score"] = df["metacritic"].str.extract(r"(\\d+)/100", expand=False).astype(float)

# название: русское, а если его нет - английское
df["title"] = df["title_ru"].fillna(df["title_en"]).fillna("без названия")

print("После удаления дубликатов:", len(df))
df[["budget_usd", "box_office_usd", "duration_min", "metacritic_score"]].describe()
""")

code("""
# Явные ошибки: бюджет меньше 100 тысяч $ и сборы меньше 1000 $ для фильмов с полноценным
# прокатом неправдоподобны; длительность меньше 40 минут - уже короткометражка,
# больше 5 часов - ошибка ввода (минуты перепутаны с секундами и т.п.)
before = len(df)
df = df[(df["budget_usd"] >= 1e5) & (df["box_office_usd"] >= 1e3)]
df.loc[~df["duration_min"].between(40, 300), "duration_min"] = np.nan
print("Удалено строк с ошибочными деньгами:", before - len(df))
print("Длительностей признано ошибочными:", df["duration_min"].isna().sum())
""")

code("""
# Новые признаки
df["roi"] = df["box_office_usd"] / df["budget_usd"]              # во сколько раз сборы больше бюджета
df["profitable"] = np.where(df["roi"] > 1, "окупился", "не окупился")
df["decade"] = (df["year"] // 10 * 10).astype(int).astype(str) + "-е"
df["log_budget"] = np.log10(df["budget_usd"])                     # деньги - на логарифмической шкале
df["log_box"] = np.log10(df["box_office_usd"])

clean = df[["title", "year", "decade", "country", "genre", "budget_usd", "box_office_usd",
            "roi", "profitable", "duration_min", "metacritic_score", "log_budget", "log_box"]]
print("Итоговый набор:", clean.shape)
clean.head()
""")

md("""
## 4. Исследование данных
""")

code("""
clean[["budget_usd", "box_office_usd", "roi", "duration_min", "metacritic_score"]].describe(
    percentiles=[0.1, 0.5, 0.9])
""")

code("""
print("Медианная окупаемость:", round(clean["roi"].median(), 2), "раза")
print(clean["profitable"].value_counts(normalize=True).round(3))
print("\\nСамые окупаемые фильмы:")
clean.nlargest(5, "roi")[["title", "year", "budget_usd", "box_office_usd", "roi"]]
""")

code("""
by_decade = clean.groupby("decade").agg(
    фильмов=("title", "count"),
    медиана_бюджета=("budget_usd", "median"),
    медиана_сборов=("box_office_usd", "median"),
    медиана_окупаемости=("roi", "median"),
)
by_decade
""")

code("""
top_genres = clean["genre"].value_counts().head(8)
genre_stats = (clean[clean["genre"].isin(top_genres.index)]
               .groupby("genre")["roi"].median().sort_values(ascending=False))
print(top_genres)
genre_stats
""")

code("""
corr = clean[["log_budget", "log_box", "roi", "duration_min", "metacritic_score", "year"]].corr()
corr.round(2)
""")

md("""
## 5. Визуализация
""")

code("""
fig, ax = plt.subplots(figsize=(7, 6))
colors = np.where(clean["roi"] > 1, "tab:green", "tab:red")
ax.scatter(clean["budget_usd"], clean["box_office_usd"], s=8, alpha=0.4, c=colors)
lim = [1e5, 4e9]
ax.plot(lim, lim, "k--", lw=1, label="сборы = бюджет")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("Бюджет, $"); ax.set_ylabel("Сборы, $")
ax.set_title("Бюджет и кассовые сборы (зелёные - окупились)")
ax.legend()
plt.show()
""")

code("""
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
ax1.hist(clean["duration_min"].dropna(), bins=40, color="tab:blue", edgecolor="white")
ax1.axvline(clean["duration_min"].mean(), color="red", label="среднее")
ax1.axvline(clean["duration_min"].median(), color="orange", ls="--", label="медиана")
ax1.set_xlabel("Длительность, мин"); ax1.set_ylabel("Число фильмов")
ax1.set_title("Гистограмма длительности"); ax1.legend()
ax2.hist(clean["log_box"], bins=40, color="tab:purple", edgecolor="white")
ax2.set_xlabel("log10(сборы, $)"); ax2.set_title("Гистограмма сборов (логарифм)")
plt.show()
""")

code("""
decades = sorted(clean["decade"].unique())
data = [clean.loc[clean["decade"] == d, "budget_usd"] / 1e6 for d in decades]
plt.boxplot(data, showfliers=False)
plt.xticks(range(1, len(decades) + 1), decades)   # подписи - так работает в любой версии
plt.ylabel("Бюджет, млн $"); plt.title("Диаграмма размаха: бюджет по десятилетиям")
plt.show()
""")

code("""
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
genre_stats.sort_values().plot.barh(ax=ax1, color="tab:orange")
ax1.axvline(1, color="k", ls="--", lw=1)
ax1.set_xlabel("Медианная окупаемость, раз"); ax1.set_title("Окупаемость по жанрам")
countries = clean["country"].value_counts()
share = pd.concat([countries.head(5), pd.Series({"другие": countries.iloc[5:].sum()})])
ax2.pie(share, labels=share.index, autopct="%1.0f%%", startangle=90)
ax2.set_title("Страны производства")
plt.show()
""")

code("""
yearly = clean.groupby("year")["budget_usd"].median() / 1e6
plt.plot(yearly.index, yearly.values, marker="o", ms=3)
plt.plot(yearly.index, yearly.rolling(5, center=True).mean(), lw=3, label="скользящее среднее (5 лет)")
plt.xlabel("Год"); plt.ylabel("Медианный бюджет, млн $")
plt.title("Как менялся типичный бюджет фильма"); plt.legend()
plt.show()
""")

code("""
fig, ax = plt.subplots(figsize=(6.5, 5))
im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
ax.set_xticks(range(len(corr)), corr.columns, rotation=45, ha="right")
ax.set_yticks(range(len(corr)), corr.columns)
for i in range(len(corr)):
    for j in range(len(corr)):
        ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=9)
fig.colorbar(im); ax.set_title("Матрица корреляций"); ax.grid(False)
plt.show()
""")

md("""
## 6. Проверка статистических гипотез

### Гипотеза 1. Между бюджетом и сборами существует сильная положительная корреляция

Считаем коэффициенты корреляции **Пирсона** (линейная связь) и **Спирмена** (монотонная связь,
устойчива к выбросам; вычисляется как корреляция Пирсона между рангами значений).
По шкале Чеддока связь сильная при |r| ≥ 0,7.
""")

code("""
pearson = clean["budget_usd"].corr(clean["box_office_usd"])
spearman = clean["budget_usd"].rank().corr(clean["box_office_usd"].rank())
pearson_log = clean["log_budget"].corr(clean["log_box"])

def strength(r):
    r = abs(r)
    return ("очень слабая" if r < 0.1 else "слабая" if r < 0.3 else "умеренная" if r < 0.5
            else "заметная" if r < 0.7 else "сильная")

print(f"Пирсон:              r = {pearson:.3f} ({strength(pearson)})")
print(f"Спирмен:             r = {spearman:.3f} ({strength(spearman)})")
print(f"Пирсон (логарифмы):  r = {pearson_log:.3f}")
print("Гипотеза 1", "ПОДТВЕРЖДАЕТСЯ" if min(pearson, spearman) >= 0.7 else "НЕ подтверждается")
""")

md("""
### Гипотеза 2. Длительность фильмов распределена нормально

Для нормального распределения коэффициент асимметрии и эксцесс близки к нулю,
а по правилу трёх сигм в интервалы ±1σ, ±2σ, ±3σ попадает 68,3 %, 95,4 % и 99,7 % значений.
""")

code("""
d = clean["duration_min"].dropna()
mean, std = d.mean(), d.std()
print(f"Среднее {mean:.1f} мин, медиана {d.median():.0f} мин, σ = {std:.1f}")
print(f"Асимметрия (skew): {d.skew():.2f}   эксцесс (kurt): {d.kurt():.2f}")

rule = pd.DataFrame({
    "интервал": ["±1σ", "±2σ", "±3σ"],
    "норма, %": [68.3, 95.4, 99.7],
    "факт, %": [((d - mean).abs() <= k * std).mean() * 100 for k in (1, 2, 3)],
})
print(rule.round(1).to_string(index=False))
normal = abs(d.skew()) < 0.5 and abs(d.kurt()) < 1
print("Гипотеза 2", "ПОДТВЕРЖДАЕТСЯ" if normal else "ОТВЕРГАЕТСЯ")
""")

md("""
### Гипотеза 3. Высокие оценки критиков связаны с лучшей окупаемостью
""")

code("""
m = clean.dropna(subset=["metacritic_score"])
r_roi = m["metacritic_score"].rank().corr(m["roi"].rank())
r_box = m["metacritic_score"].corr(m["log_box"])
print(f"Фильмов с оценкой Metacritic: {len(m)}")
print(f"Оценка и окупаемость (Спирмен): r = {r_roi:.3f} ({strength(r_roi)})")
print(f"Оценка и сборы (Пирсон, логарифм): r = {r_box:.3f} ({strength(r_box)})")

m = m.assign(группа=pd.cut(m["metacritic_score"], [0, 40, 60, 80, 100],
                           labels=["0-40", "41-60", "61-80", "81-100"]))
m.groupby("группа", observed=True)["roi"].agg(["count", "median"])
""")

md("""
## 7. Выводы

* Собран и очищен уникальный набор данных о ~2400 фильмах из Викиданных: удалены дубликаты,
  ошибочные значения, оценки приведены к числу, добавлены признаки окупаемости и десятилетия.
* **Гипотеза 1 подтверждается:** бюджет и сборы связаны сильной положительной корреляцией
  (Пирсон ≈ 0,75, Спирмен ≈ 0,78). Дорогие фильмы в среднем собирают больше, но не всегда окупаются лучше.
* **Гипотеза 2 отвергается:** распределение длительности имеет правостороннюю асимметрию (skew ≈ 1,3)
  и «тяжёлые хвосты» (эксцесс ≈ 3,8) — типичный фильм идёт около 1 ч 50 мин, но длинных фильмов
  заметно больше, чем было бы при нормальном распределении.
* **Гипотеза 3 подтверждается частично:** оценка критиков слабо положительно связана с окупаемостью
  (r ≈ 0,24), но почти не связана с абсолютными сборами — хорошие фильмы не обязательно кассовые.
* Около 76 % фильмов выборки окупились в прокате, медианная окупаемость — примерно 2,4 раза.
""")

nb = nbformat.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
    "colab": {"provenance": []},
})
NotebookClient(nb, timeout=300, kernel_name="python3",
               resources={"metadata": {"path": str(HERE)}}).execute()
nbformat.write(nb, NB)
print("Готово:", NB)
