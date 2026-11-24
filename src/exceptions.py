"""Исключения конвейера."""


class ExtractionError(RuntimeError):
    """Источник недоступен или вернул некорректные данные."""


class InsecureFeedError(ExtractionError):
    """RSS-лента отдаётся не по HTTPS (REQUIRE_TLS=true)."""


class DataQualityError(RuntimeError):
    """Не пройдены критические проверки качества данных."""
