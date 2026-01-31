# Internacionalização (i18n) para APIs REST

Guia completo para implementar internacionalização em APIs REST, cobrindo mensagens de erro, validação, formatos de data/número e boas práticas.

---

## Visão Geral

### O que internacionalizar em uma API?

| Elemento | Prioridade | Exemplo |
|----------|------------|---------|
| Mensagens de erro | Alta | "Usuário não encontrado" |
| Mensagens de validação | Alta | "Email inválido" |
| Enums/Status legíveis | Média | "Pendente", "Aprovado" |
| Formatos de data | Média | "15/01/2025" vs "01/15/2025" |
| Formatos de número | Média | "1.234,56" vs "1,234.56" |
| Moeda | Baixa | "R$ 100,00" vs "$100.00" |

### O que NÃO internacionalizar

- Códigos de erro (`USER_NOT_FOUND`) - sempre em inglês
- Campos técnicos (`type`, `param`, `field`)
- IDs e identificadores
- Dados do usuário (nome, endereço)
- Logs internos

---

## Negociação de Idioma

### Header Accept-Language

```http
Accept-Language: pt-BR, pt;q=0.9, en;q=0.8, es;q=0.7
```

**Parsing:**
- `pt-BR` - Português Brasil (qualidade 1.0 implícita)
- `pt;q=0.9` - Português genérico (qualidade 0.9)
- `en;q=0.8` - Inglês (qualidade 0.8)
- `es;q=0.7` - Espanhol (qualidade 0.7)

### Algoritmo de Seleção

```
1. Parse Accept-Language e ordena por qualidade
2. Para cada locale do cliente (maior qualidade primeiro):
   a. Se locale exato existe (pt-BR) → usa
   b. Se locale base existe (pt) → usa
   c. Continua para próximo
3. Se nenhum match → usa DEFAULT_LOCALE
```

### Response Header

```http
Content-Language: pt-BR
```

---

## Estrutura de Arquivos de Tradução

### Organização Recomendada

```
locales/
├── en/
│   ├── errors.json
│   ├── validation.json
│   └── enums.json
├── pt-BR/
│   ├── errors.json
│   ├── validation.json
│   └── enums.json
├── es/
│   ├── errors.json
│   ├── validation.json
│   └── enums.json
└── index.py
```

### errors.json

```json
{
  "USER_NOT_FOUND": "Usuário não encontrado",
  "USER_NOT_FOUND_WITH_ID": "Usuário com ID '{id}' não encontrado",
  "EMAIL_EXISTS": "Este email já está cadastrado",
  "INVALID_TOKEN": "Token de acesso inválido ou expirado",
  "FORBIDDEN": "Você não tem permissão para acessar este recurso",
  "RATE_LIMIT_EXCEEDED": "Limite de requisições excedido. Tente novamente em {seconds} segundos",
  "INTERNAL_ERROR": "Ocorreu um erro interno. Nossa equipe foi notificada",
  "MAINTENANCE": "Sistema em manutenção. Previsão de retorno: {time}",
  "VALIDATION_FAILED": "Erros de validação encontrados",
  "CONFLICT": "Conflito ao processar requisição",
  "RESOURCE_NOT_FOUND": "{resource} não encontrado",
  "RESOURCE_NOT_FOUND_WITH_ID": "{resource} com ID '{id}' não encontrado"
}
```

### validation.json

```json
{
  "REQUIRED": "O campo '{field}' é obrigatório",
  "REQUIRED_SIMPLE": "Campo obrigatório",
  "MIN_LENGTH": "O campo '{field}' deve ter no mínimo {min} caracteres",
  "MAX_LENGTH": "O campo '{field}' deve ter no máximo {max} caracteres",
  "MIN_VALUE": "O campo '{field}' deve ser maior ou igual a {min}",
  "MAX_VALUE": "O campo '{field}' deve ser menor ou igual a {max}",
  "INVALID_EMAIL": "Email inválido",
  "INVALID_URL": "URL inválida",
  "INVALID_UUID": "UUID inválido",
  "INVALID_DATE": "Data inválida. Use o formato {format}",
  "DATE_IN_PAST": "A data deve ser no passado",
  "DATE_IN_FUTURE": "A data deve ser no futuro",
  "INVALID_ENUM": "Valor inválido. Valores permitidos: {values}",
  "INVALID_TYPE": "Tipo inválido. Esperado: {expected}, recebido: {received}",
  "INVALID_FORMAT": "Formato inválido",
  "UNIQUE_VIOLATION": "Este valor já está em uso",
  "ARRAY_MIN_ITEMS": "A lista deve ter no mínimo {min} itens",
  "ARRAY_MAX_ITEMS": "A lista deve ter no máximo {max} itens",
  "REGEX_MISMATCH": "Formato inválido para '{field}'",
  "PASSWORD_TOO_WEAK": "Senha muito fraca. Use letras, números e símbolos",
  "PASSWORDS_DONT_MATCH": "As senhas não conferem"
}
```

### enums.json

```json
{
  "order_status": {
    "pending": "Pendente",
    "processing": "Em processamento",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado"
  },
  "user_role": {
    "admin": "Administrador",
    "manager": "Gerente",
    "user": "Usuário",
    "guest": "Visitante"
  },
  "payment_status": {
    "pending": "Aguardando pagamento",
    "paid": "Pago",
    "failed": "Falhou",
    "refunded": "Reembolsado"
  }
}
```

---

## Implementação Python

### Classe I18n

```python
import json
import os
import re
from pathlib import Path
from typing import Optional
from functools import lru_cache


class I18n:
    """Gerenciador de internacionalização."""
    
    SUPPORTED_LOCALES = ["en", "pt-BR", "pt", "es"]
    DEFAULT_LOCALE = "en"
    FALLBACK_CHAIN = {
        "pt-BR": ["pt", "en"],
        "pt": ["en"],
        "es": ["en"],
        "en": []
    }
    
    def __init__(self, locales_dir: str = "locales"):
        self.locales_dir = Path(locales_dir)
        self._cache: dict[str, dict] = {}
        self._load_all()
    
    def _load_all(self):
        """Carrega todos os arquivos de tradução."""
        for locale in self.SUPPORTED_LOCALES:
            locale_dir = self.locales_dir / locale
            if not locale_dir.exists():
                continue
            
            self._cache[locale] = {}
            
            for file in locale_dir.glob("*.json"):
                namespace = file.stem  # errors, validation, enums
                with open(file, "r", encoding="utf-8") as f:
                    self._cache[locale][namespace] = json.load(f)
    
    def _get_fallback_chain(self, locale: str) -> list[str]:
        """Retorna cadeia de fallback para um locale."""
        chain = [locale]
        chain.extend(self.FALLBACK_CHAIN.get(locale, []))
        if self.DEFAULT_LOCALE not in chain:
            chain.append(self.DEFAULT_LOCALE)
        return chain
    
    def get(
        self,
        key: str,
        locale: str,
        namespace: str = "errors",
        params: dict = None
    ) -> str:
        """
        Busca tradução com fallback.
        
        Args:
            key: Chave da tradução (ex: USER_NOT_FOUND)
            locale: Locale desejado (ex: pt-BR)
            namespace: Arquivo de tradução (errors, validation, enums)
            params: Parâmetros para interpolação
        
        Returns:
            Mensagem traduzida ou a própria key se não encontrada
        """
        params = params or {}
        
        # Tenta cada locale na cadeia de fallback
        for fallback_locale in self._get_fallback_chain(locale):
            translations = self._cache.get(fallback_locale, {}).get(namespace, {})
            
            if key in translations:
                message = translations[key]
                return self._interpolate(message, params)
        
        # Não encontrou, retorna a key formatada
        return self._interpolate(key, params)
    
    def get_nested(
        self,
        path: str,
        locale: str,
        namespace: str = "enums",
        params: dict = None
    ) -> str:
        """
        Busca tradução aninhada (ex: order_status.pending).
        """
        params = params or {}
        keys = path.split(".")
        
        for fallback_locale in self._get_fallback_chain(locale):
            translations = self._cache.get(fallback_locale, {}).get(namespace, {})
            
            value = translations
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            
            if value and isinstance(value, str):
                return self._interpolate(value, params)
        
        return path
    
    def _interpolate(self, message: str, params: dict) -> str:
        """Substitui placeholders {key} pelos valores."""
        if not params:
            return message
        
        def replace(match):
            key = match.group(1)
            return str(params.get(key, match.group(0)))
        
        return re.sub(r'\{(\w+)\}', replace, message)
    
    def get_error(self, code: str, locale: str, **params) -> str:
        """Atalho para buscar mensagem de erro."""
        return self.get(code, locale, namespace="errors", params=params)
    
    def get_validation(self, code: str, locale: str, **params) -> str:
        """Atalho para buscar mensagem de validação."""
        return self.get(code, locale, namespace="validation", params=params)
    
    def get_enum(self, enum_type: str, value: str, locale: str) -> str:
        """Atalho para buscar label de enum."""
        return self.get_nested(f"{enum_type}.{value}", locale, namespace="enums")


# Singleton global
i18n = I18n()
```

### Parsing do Accept-Language

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class LocalePreference:
    locale: str
    quality: float


def parse_accept_language(header: str) -> list[LocalePreference]:
    """
    Parse do header Accept-Language.
    
    Exemplo:
        "pt-BR, pt;q=0.9, en;q=0.8" ->
        [LocalePreference("pt-BR", 1.0), LocalePreference("pt", 0.9), ...]
    """
    if not header:
        return []
    
    preferences = []
    
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        
        if ";q=" in part:
            locale, q = part.split(";q=", 1)
            try:
                quality = float(q)
            except ValueError:
                quality = 1.0
        else:
            locale = part
            quality = 1.0
        
        # Normaliza locale (en-us -> en-US)
        locale = normalize_locale(locale.strip())
        
        preferences.append(LocalePreference(locale, quality))
    
    # Ordena por qualidade (maior primeiro)
    preferences.sort(key=lambda x: x.quality, reverse=True)
    
    return preferences


def normalize_locale(locale: str) -> str:
    """Normaliza formato do locale (en-us -> en-US)."""
    if "-" in locale:
        lang, region = locale.split("-", 1)
        return f"{lang.lower()}-{region.upper()}"
    return locale.lower()


def negotiate_locale(
    accept_language: str,
    supported: list[str],
    default: str = "en"
) -> str:
    """
    Negocia o melhor locale baseado no Accept-Language.
    
    Args:
        accept_language: Header Accept-Language
        supported: Lista de locales suportados
        default: Locale padrão
    
    Returns:
        Melhor locale disponível
    """
    preferences = parse_accept_language(accept_language)
    
    for pref in preferences:
        # Match exato
        if pref.locale in supported:
            return pref.locale
        
        # Match parcial (pt-BR -> pt)
        base_locale = pref.locale.split("-")[0]
        if base_locale in supported:
            return base_locale
        
        # Match reverso (pt -> pt-BR se pt-BR está em supported)
        for supported_locale in supported:
            if supported_locale.startswith(f"{pref.locale}-"):
                return supported_locale
    
    return default
```

### Middleware FastAPI

```python
from fastapi import FastAPI, Request
from contextvars import ContextVar

# Context var para acessar locale em qualquer lugar
current_locale: ContextVar[str] = ContextVar("current_locale", default="en")

app = FastAPI()


@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    # Negocia locale
    accept_language = request.headers.get("Accept-Language", "")
    locale = negotiate_locale(
        accept_language,
        supported=I18n.SUPPORTED_LOCALES,
        default=I18n.DEFAULT_LOCALE
    )
    
    # Salva no request state e context var
    request.state.locale = locale
    token = current_locale.set(locale)
    
    try:
        response = await call_next(request)
        response.headers["Content-Language"] = locale
        return response
    finally:
        current_locale.reset(token)


def get_locale() -> str:
    """Retorna locale atual (para uso fora do request context)."""
    return current_locale.get()
```

### Helpers para Erros

```python
from fastapi import HTTPException, Request


def localized_error(
    request: Request,
    error_type: str,
    code: str,
    status_code: int = 400,
    param: str = None,
    details: dict = None,
    **message_params
) -> HTTPException:
    """
    Cria HTTPException com mensagem localizada.
    
    Uso:
        raise localized_error(
            request,
            "not_found_error",
            "USER_NOT_FOUND_WITH_ID",
            404,
            id=user_id
        )
    """
    locale = getattr(request.state, "locale", I18n.DEFAULT_LOCALE)
    message = i18n.get_error(code, locale, **message_params)
    
    error_body = {
        "type": error_type,
        "message": message,
        "code": code
    }
    
    if param:
        error_body["param"] = param
    if details:
        error_body["details"] = details
    
    return HTTPException(status_code=status_code, detail=error_body)


# Helpers específicos
def not_found(request: Request, resource: str, resource_id: str = None):
    if resource_id:
        return localized_error(
            request, "not_found_error", "RESOURCE_NOT_FOUND_WITH_ID",
            404, resource=resource, id=resource_id
        )
    return localized_error(
        request, "not_found_error", "RESOURCE_NOT_FOUND",
        404, resource=resource
    )


def conflict(request: Request, code: str, **params):
    return localized_error(request, "conflict_error", code, 409, **params)


def rate_limited(request: Request, seconds: int):
    return localized_error(
        request, "rate_limit_error", "RATE_LIMIT_EXCEEDED",
        429, seconds=seconds
    )
```

### Validação Localizada

```python
from pydantic import BaseModel, field_validator, ValidationError
from fastapi import Request
from fastapi.exceptions import RequestValidationError


def localize_validation_errors(
    exc: RequestValidationError,
    locale: str
) -> list[dict]:
    """
    Converte erros do Pydantic para formato localizado.
    """
    localized = []
    
    for error in exc.errors():
        # Extrai informações do erro
        field = ".".join(str(x) for x in error["loc"][1:])  # Remove 'body'
        error_type = error["type"]
        ctx = error.get("ctx", {})
        
        # Mapeia tipo do Pydantic para nossa chave
        code_mapping = {
            "missing": "REQUIRED",
            "string_too_short": "MIN_LENGTH",
            "string_too_long": "MAX_LENGTH",
            "greater_than_equal": "MIN_VALUE",
            "less_than_equal": "MAX_VALUE",
            "value_error.email": "INVALID_EMAIL",
            "value_error.url": "INVALID_URL",
            "uuid_parsing": "INVALID_UUID",
            "datetime_parsing": "INVALID_DATE",
            "enum": "INVALID_ENUM",
            "type_error": "INVALID_TYPE",
        }
        
        code = code_mapping.get(error_type, "INVALID_FORMAT")
        
        # Monta parâmetros para interpolação
        params = {"field": field, **ctx}
        
        # Busca mensagem traduzida
        message = i18n.get_validation(code, locale, **params)
        
        localized.append({
            "field": field,
            "message": message,
            "code": code
        })
    
    return localized


# Exception handler
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    locale = getattr(request.state, "locale", I18n.DEFAULT_LOCALE)
    
    errors = localize_validation_errors(exc, locale)
    
    return JSONResponse(
        status_code=422,
        content={
            "type": "validation_error",
            "message": i18n.get_error("VALIDATION_FAILED", locale),
            "code": "VALIDATION_FAILED",
            "details": {"errors": errors}
        }
    )
```

---

## Formatação de Data/Hora

### Biblioteca Babel

```bash
pip install babel
```

### Implementação

```python
from babel import Locale
from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_decimal, format_currency
from datetime import datetime, date
from typing import Union


class Formatter:
    """Formatador localizado para datas, números e moeda."""
    
    # Mapeamento de locale para timezone padrão
    DEFAULT_TIMEZONES = {
        "pt-BR": "America/Sao_Paulo",
        "pt": "Europe/Lisbon",
        "en": "America/New_York",
        "es": "Europe/Madrid"
    }
    
    # Mapeamento de locale para moeda padrão
    DEFAULT_CURRENCIES = {
        "pt-BR": "BRL",
        "pt": "EUR",
        "en": "USD",
        "es": "EUR"
    }
    
    @staticmethod
    def date(
        value: Union[date, datetime],
        locale: str,
        format: str = "medium"
    ) -> str:
        """
        Formata data.
        
        Formats: short, medium, long, full
        
        Exemplos (2025-01-15):
            pt-BR: 15/01/2025 (short), 15 de jan. de 2025 (medium)
            en: 1/15/25 (short), Jan 15, 2025 (medium)
        """
        return format_date(value, format=format, locale=locale)
    
    @staticmethod
    def datetime(
        value: datetime,
        locale: str,
        format: str = "medium"
    ) -> str:
        """
        Formata data e hora.
        
        Exemplos:
            pt-BR: 15/01/2025 14:30:00
            en: Jan 15, 2025, 2:30:00 PM
        """
        return format_datetime(value, format=format, locale=locale)
    
    @staticmethod
    def time(
        value: Union[datetime, time],
        locale: str,
        format: str = "short"
    ) -> str:
        """
        Formata hora.
        
        Exemplos:
            pt-BR: 14:30
            en: 2:30 PM
        """
        return format_time(value, format=format, locale=locale)
    
    @staticmethod
    def number(
        value: float,
        locale: str,
        decimal_places: int = 2
    ) -> str:
        """
        Formata número.
        
        Exemplos (1234.56):
            pt-BR: 1.234,56
            en: 1,234.56
        """
        return format_decimal(value, format=f"#,##0.{'0' * decimal_places}", locale=locale)
    
    @staticmethod
    def currency(
        value: float,
        locale: str,
        currency: str = None
    ) -> str:
        """
        Formata moeda.
        
        Exemplos (100.50):
            pt-BR: R$ 100,50
            en: $100.50
        """
        if currency is None:
            currency = Formatter.DEFAULT_CURRENCIES.get(locale, "USD")
        
        return format_currency(value, currency, locale=locale)
    
    @staticmethod
    def relative_time(
        value: datetime,
        locale: str
    ) -> str:
        """
        Formata tempo relativo (há 5 minutos, em 2 dias).
        """
        from babel.dates import format_timedelta
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        delta = value - now
        
        return format_timedelta(delta, locale=locale, add_direction=True)


# Uso
formatter = Formatter()

# Data
formatter.date(date.today(), "pt-BR")  # "17/01/2025"
formatter.date(date.today(), "en")     # "Jan 17, 2025"

# Número
formatter.number(1234.56, "pt-BR")  # "1.234,56"
formatter.number(1234.56, "en")     # "1,234.56"

# Moeda
formatter.currency(100.50, "pt-BR")  # "R$ 100,50"
formatter.currency(100.50, "en")     # "$100.50"
```

### Incluindo Formatação na Resposta

```python
@app.get("/v1/orders/{order_id}")
async def get_order(order_id: str, request: Request):
    locale = request.state.locale
    order = await find_order(order_id)
    
    # Formata campos para exibição
    order_data = {
        "id": order.id,
        "status": order.status,
        "status_label": i18n.get_enum("order_status", order.status, locale),
        "total": order.total,
        "total_formatted": formatter.currency(order.total, locale),
        "created_at": order.created_at.isoformat(),
        "created_at_formatted": formatter.datetime(order.created_at, locale)
    }
    
    return {"type": "order", "data": order_data}
```

**Response (pt-BR):**
```json
{
  "type": "order",
  "data": {
    "id": "ord_123",
    "status": "shipped",
    "status_label": "Enviado",
    "total": 150.99,
    "total_formatted": "R$ 150,99",
    "created_at": "2025-01-15T10:30:00Z",
    "created_at_formatted": "15 de jan. de 2025 10:30"
  }
}
```

---

## Pluralização

### Arquivo de Traduções

```json
{
  "ITEMS_COUNT": {
    "zero": "Nenhum item",
    "one": "{count} item",
    "other": "{count} itens"
  },
  "DAYS_AGO": {
    "zero": "Hoje",
    "one": "Ontem",
    "other": "Há {count} dias"
  },
  "REMAINING_ATTEMPTS": {
    "zero": "Nenhuma tentativa restante",
    "one": "1 tentativa restante",
    "other": "{count} tentativas restantes"
  }
}
```

### Implementação

```python
def get_plural(
    self,
    key: str,
    count: int,
    locale: str,
    namespace: str = "errors",
    **params
) -> str:
    """
    Busca tradução com pluralização.
    
    Uso:
        i18n.get_plural("ITEMS_COUNT", 5, "pt-BR")
        # "5 itens"
    """
    params["count"] = count
    
    for fallback_locale in self._get_fallback_chain(locale):
        translations = self._cache.get(fallback_locale, {}).get(namespace, {})
        
        if key not in translations:
            continue
        
        plural_forms = translations[key]
        
        if not isinstance(plural_forms, dict):
            # Não é plural, retorna direto
            return self._interpolate(plural_forms, params)
        
        # Seleciona forma correta
        if count == 0 and "zero" in plural_forms:
            form = "zero"
        elif count == 1 and "one" in plural_forms:
            form = "one"
        else:
            form = "other"
        
        message = plural_forms.get(form, plural_forms.get("other", key))
        return self._interpolate(message, params)
    
    return key
```

---

## Cache de Traduções

### Redis Cache

```python
import redis
import json
from functools import wraps

redis_client = redis.Redis()
CACHE_TTL = 3600  # 1 hora


def cached_translation(func):
    """Decorator para cachear traduções."""
    
    @wraps(func)
    def wrapper(self, key: str, locale: str, namespace: str = "errors", **params):
        # Sem params, pode cachear
        if not params:
            cache_key = f"i18n:{locale}:{namespace}:{key}"
            
            cached = redis_client.get(cache_key)
            if cached:
                return cached.decode()
            
            result = func(self, key, locale, namespace, **params)
            redis_client.setex(cache_key, CACHE_TTL, result)
            return result
        
        # Com params, não cacheia (interpolação dinâmica)
        return func(self, key, locale, namespace, **params)
    
    return wrapper


class I18n:
    @cached_translation
    def get(self, key: str, locale: str, namespace: str = "errors", **params) -> str:
        # implementação...
        pass
```

### Invalidação

```python
def invalidate_translations(locale: str = None, namespace: str = None):
    """Invalida cache de traduções."""
    if locale and namespace:
        pattern = f"i18n:{locale}:{namespace}:*"
    elif locale:
        pattern = f"i18n:{locale}:*"
    else:
        pattern = "i18n:*"
    
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)
```

---

## Hot Reload de Traduções

### Watcher de Arquivos

```python
import asyncio
from watchfiles import awatch
from pathlib import Path


async def watch_translations(i18n: I18n):
    """Recarrega traduções quando arquivos mudam."""
    async for changes in awatch(i18n.locales_dir):
        for change_type, path in changes:
            print(f"Translation file changed: {path}")
        
        # Recarrega todas as traduções
        i18n._load_all()
        
        # Invalida cache
        invalidate_translations()
        
        print("Translations reloaded")


# Inicia watcher em background (desenvolvimento)
if settings.ENVIRONMENT == "development":
    asyncio.create_task(watch_translations(i18n))
```

---

## API para Gestão de Traduções

### Endpoints (Admin)

```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/admin/i18n", tags=["i18n"])


@router.get("/locales")
async def list_locales():
    """Lista locales suportados."""
    return {
        "type": "list",
        "data": I18n.SUPPORTED_LOCALES,
        "metadata": {
            "default": I18n.DEFAULT_LOCALE
        }
    }


@router.get("/translations/{locale}")
async def get_translations(locale: str, namespace: str = None):
    """Retorna todas as traduções de um locale."""
    if locale not in i18n._cache:
        raise HTTPException(404, {"type": "not_found_error", "message": "Locale not found"})
    
    data = i18n._cache[locale]
    
    if namespace:
        data = data.get(namespace, {})
    
    return {"type": "translations", "data": data}


@router.get("/missing")
async def find_missing_translations(base_locale: str = "en"):
    """Encontra traduções faltando em outros locales."""
    base = i18n._cache.get(base_locale, {})
    missing = {}
    
    for locale in I18n.SUPPORTED_LOCALES:
        if locale == base_locale:
            continue
        
        locale_translations = i18n._cache.get(locale, {})
        missing[locale] = {}
        
        for namespace, keys in base.items():
            locale_ns = locale_translations.get(namespace, {})
            missing_keys = set(keys.keys()) - set(locale_ns.keys())
            
            if missing_keys:
                missing[locale][namespace] = list(missing_keys)
    
    return {"type": "missing_translations", "data": missing}
```

---

## Testes

### Fixtures

```python
import pytest
from unittest.mock import patch


@pytest.fixture
def i18n_instance():
    """I18n com traduções de teste."""
    return I18n(locales_dir="tests/locales")


@pytest.fixture
def mock_locale():
    """Mock do locale atual."""
    def _mock(locale: str):
        return patch.object(current_locale, "get", return_value=locale)
    return _mock
```

### Testes de Tradução

```python
def test_get_translation_exact_locale(i18n_instance):
    result = i18n_instance.get("USER_NOT_FOUND", "pt-BR")
    assert result == "Usuário não encontrado"


def test_get_translation_fallback_to_base(i18n_instance):
    # pt-BR não tem, mas pt tem
    result = i18n_instance.get("SOME_KEY", "pt-BR")
    # Deve cair no fallback pt ou en


def test_get_translation_with_interpolation(i18n_instance):
    result = i18n_instance.get(
        "USER_NOT_FOUND_WITH_ID",
        "pt-BR",
        id="usr_123"
    )
    assert result == "Usuário com ID 'usr_123' não encontrado"


def test_get_translation_missing_key_returns_key(i18n_instance):
    result = i18n_instance.get("NONEXISTENT_KEY", "pt-BR")
    assert result == "NONEXISTENT_KEY"


def test_plural_zero(i18n_instance):
    result = i18n_instance.get_plural("ITEMS_COUNT", 0, "pt-BR")
    assert result == "Nenhum item"


def test_plural_one(i18n_instance):
    result = i18n_instance.get_plural("ITEMS_COUNT", 1, "pt-BR")
    assert result == "1 item"


def test_plural_many(i18n_instance):
    result = i18n_instance.get_plural("ITEMS_COUNT", 5, "pt-BR")
    assert result == "5 itens"
```

### Testes de Endpoint

```python
from fastapi.testclient import TestClient


def test_error_response_in_portuguese(client: TestClient):
    response = client.get(
        "/v1/users/nonexistent",
        headers={"Accept-Language": "pt-BR"}
    )
    
    assert response.status_code == 404
    assert response.headers["Content-Language"] == "pt-BR"
    assert response.json()["message"] == "Usuário não encontrado"


def test_error_response_in_english(client: TestClient):
    response = client.get(
        "/v1/users/nonexistent",
        headers={"Accept-Language": "en"}
    )
    
    assert response.status_code == 404
    assert response.headers["Content-Language"] == "en"
    assert response.json()["message"] == "User not found"


def test_fallback_to_default_locale(client: TestClient):
    response = client.get(
        "/v1/users/nonexistent",
        headers={"Accept-Language": "ja"}  # Não suportado
    )
    
    assert response.headers["Content-Language"] == "en"
```

---

## Checklist de Implementação

### ✅ Básico

- [ ] Parser de Accept-Language
- [ ] Middleware para setar locale
- [ ] Header Content-Language na resposta
- [ ] Arquivos de tradução organizados
- [ ] Mensagens de erro traduzidas

### ✅ Intermediário

- [ ] Fallback chain configurado
- [ ] Interpolação de parâmetros
- [ ] Mensagens de validação traduzidas
- [ ] Enums/status traduzidos
- [ ] Pluralização

### ✅ Avançado

- [ ] Cache de traduções
- [ ] Hot reload em desenvolvimento
- [ ] Formatação de data/número localizada
- [ ] API de gestão de traduções
- [ ] Detector de traduções faltando

---

## Dicas Finais

1. **Nunca concatene strings** para formar mensagens - use interpolação
2. **Mantenha códigos em inglês** - facilita busca e debugging
3. **Teste com locales diferentes** - alguns textos ficam muito maiores
4. **Documente o contexto** - tradutores precisam saber onde a string aparece
5. **Use ferramentas de tradução** - Crowdin, Lokalise, Phrase

---

*Guia de Internacionalização para APIs REST v1.0*
