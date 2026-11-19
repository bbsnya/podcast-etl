# Podcast Data ETL Pipeline

ETL-пайплайн для сбора, обработки и загрузки данных о подкастах и их выпусках из Apple iTunes Search API и RSS-лент в PostgreSQL.

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)
![Airflow](https://img.shields.io/badge/Airflow-2.7.3-017CEE?style=flat&logo=apache-airflow&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Metabase](https://img.shields.io/badge/Metabase-BI-509EE3?style=flat&logo=metabase&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Описание

Проект автоматически собирает метаданные о подкастах и информацию о выпусках, преобразует данные и загружает их в реляционное хранилище. Пайплайн работает по классической ETL-схеме: Extract → Transform → Quality Check → Load.

Цель проекта: автоматизировать сбор и подготовку данных о подкастах для последующего анализа публикационной активности, длительности выпусков и качества источников.

---

## Функциональность

- **Extract**: получение данных из Apple iTunes Search API и RSS-лент.
- **Transform**: очистка, нормализация дат и длительности, удаление дубликатов.
- **Quality Check**: проверка обязательных полей, выявление дубликатов.
- **Load**: загрузка данных в PostgreSQL с идемпотентной вставкой (ON CONFLICT).

---

## Метрики

- **Всего подкастов** — общее число уникальных подкастов в базе.
- **Всего выпусков** — общее число загруженных выпусков.
- **Средняя длительность** — среднее значение `duration_seconds` по всем выпускам.
- **Выпусков за последние 30 дней** — количество выпусков, опубликованных за последний месяц (актуальность данных).

---

## Аналитические срезы

- **Топ-10 подкастов по выпускам** — подкасты с наибольшим количеством выпусков.
- **Динамика публикаций по месяцам (2021–2026)** — распределение выпусков по месяцам за последние 5 лет.
- **Распределение длительности выпусков** — группировка выпусков по диапазонам длительности (< 10 мин, 10–30 мин, 30–60 мин, 60–120 мин, > 2 часов).
- **Матрица активности** — зависимость между количеством выпусков подкаста и их средней длительностью (сегментация подкастов).

---

## Технологический стек

| Компонент | Технология |
| :--- | :--- |
| Язык | Python 3.8+ |
| HTTP-запросы | requests |
| Обработка данных | Pandas |
| Оркестрация | Apache Airflow 2.7.3 |
| База данных | PostgreSQL 15 |
| Визуализация | Metabase |
| Тестирование | Pytest |
| Контейнеризация | Docker + Docker Compose |
| Источник данных | Apple iTunes Search API, RSS |

---

## Структура проекта
podcast-etl/
├── dags/
│ └── podcast_etl_dag.py
├── src/
│ ├── init.py
│ ├── config.py
│ ├── extract.py
│ ├── transform.py
│ ├── load.py
│ └── quality.py
├── sql/
│ └── init.sql
├── tests/
│ ├── init.py
│ ├── test_transform.py
│ └── test_load.py
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md

---

## Описание модулей

| Модуль | Назначение |
| :--- | :--- |
| `config.py` | Конфигурация (переменные окружения, параметры API) |
| `extract.py` | Запрос к iTunes API и парсинг RSS |
| `transform.py` | Очистка, нормализация, расчёт длительности |
| `load.py` | Загрузка в PostgreSQL |
| `quality.py` | Проверки качества данных |
| `podcast_etl_dag.py` | Оркестрация в Airflow |

---

## Установка и запуск

**Требования:** Docker Desktop.

1. Запустить все сервисы (PostgreSQL, Airflow, Metabase):
   ```bash
   docker compose up -d
Создать файл .env на основе шаблона:

bash
cp .env.example .env
Открыть Airflow и запустить DAG: http://localhost:8080 (admin / admin).
Доступ к сервисам:

Сервис	URL	Логин / Пароль
Airflow	http://localhost:8080	admin / admin
Metabase	http://localhost:3000	настраивается при первом входе
PostgreSQL	localhost:5432	podcast_user / podcast_pass
Тестирование

bash
docker compose exec airflow-webserver pytest /opt/airflow/tests/ -v
Источник данных

Apple iTunes Search API — метаданные подкастов.
RSS-ленты — информация о выпусках.
Автор

bbsnya
