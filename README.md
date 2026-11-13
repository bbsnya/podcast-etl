cat << 'EOF' > README.md
Podcast Data ETL Pipeline

An end-to-end ETL pipeline that collects podcast metadata and episode data from external APIs and RSS feeds, transforms it, and loads it into a PostgreSQL data warehouse for analytics.

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)
![Apache Airflow](https://img.shields.io/badge/Airflow-2.7.3-017CEE?style=flat&logo=apache-airflow&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Metabase](https://img.shields.io/badge/Metabase-BI-509EE3?style=flat&logo=metabase&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

Overview

This project implements a fully automated data pipeline that aggregates podcast data from two sources:

- Apple iTunes Search API – for podcast-level metadata (title, author, RSS URL).
- RSS feeds – for episode-level details (titles, publication dates, durations, audio links).

The pipeline handles extraction, cleaning, validation, and loading into a relational database, with orchestration, retries, and monitoring built in.

Architecture

```mermaid
flowchart LR
    A[iTunes API] --> C[Extract]
    B[RSS Feeds] --> C
    C --> D[Transform]
    D --> E[Quality Check]
    E --> F[Load]
    F --> G[(PostgreSQL)]
    G --> H[Metabase Dashboard]

    style A fill:#E3F2FD,stroke:#1976D2
    style B fill:#E3F2FD,stroke:#1976D2
    style C fill:#FFF3E0,stroke:#F57C00
    style D fill:#FFF3E0,stroke:#F57C00
    style E fill:#FFF3E0,stroke:#F57C00
    style F fill:#FFF3E0,stroke:#F57C00
    style G fill:#E8F5E9,stroke:#388E3C
    style H fill:#F3E5F5,stroke:#7B1FA
