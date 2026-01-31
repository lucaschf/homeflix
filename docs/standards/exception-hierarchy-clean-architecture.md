# Hierarquia de Exceções para Clean Architecture

## Sumário

1. [Visão Geral](#visão-geral)
2. [Princípios de Design](#princípios-de-design)
3. [Hierarquia Completa](#hierarquia-completa)
4. [Implementação](#implementação)
   - [Base (CoreException)](#base-coreexception)
   - [Domínio (DomainException)](#domínio-domainexception)
   - [Aplicação (ApplicationException)](#aplicação-applicationexception)
   - [Infraestrutura (InfrastructureException)](#infraestrutura-infrastructureexception)
   - [Apresentação (PresentationException)](#apresentação-presentationexception)
5. [Handler Global (FastAPI)](#handler-global-fastapi)
6. [Exemplos de Uso](#exemplos-de-uso)
7. [Boas Práticas](#boas-práticas)
8. [HTTP Status Mapper (Abordagem Purista)](#http-status-mapper-abordagem-purista)
9. [Internacionalização (i18n)](#internacionalização-i18n)
10. [Considerações de Performance](#considerações-de-performance)
11. [Testes](#testes)
12. [Inicialização e Registro (FastAPI)](#inicialização-e-registro-fastapi)
13. [Guia de Boas Práticas para Desenvolvedores](#guia-de-boas-práticas-para-desenvolvedores)
14. [Gerenciamento de Regras de Negócio (rule_code)](#gerenciamento-de-regras-de-negócio-rule_code)
15. [Estrutura de Pastas](#estrutura-de-pastas)

---

## Visão Geral

Esta documentação apresenta uma hierarquia de exceções projetada para aplicações que seguem **Clean Architecture** e **Domain-Driven Design (DDD)**. A estrutura foi inspirada no padrão de resposta de erros da API do Claude (Anthropic), adaptada para cobrir todas as camadas de uma aplicação.

### Objetivos

- **Separação clara por camada**: Domain, Application e Infrastructure
- **Serialização padronizada**: Formato consistente para respostas de API
- **Rastreabilidade**: Cada exceção possui um ID único para correlação com logs
- **Observabilidade**: Suporte a severity e tags para ferramentas de monitoramento
- **Segurança**: Mensagens técnicas nunca são expostas ao cliente final

### Formato de Resposta

Todas as exceções são serializadas no seguinte formato:

```json
{
  "type": "error",
  "error": {
    "code": "BUSINESS_RULE_VIOLATION",
    "message": "Documento já foi verificado",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "details": [
      {
        "code": "FIELD_INVALID",
        "message": "CPF inválido",
        "field": "cpf"
      }
    ]
  }
}
```

---

## Princípios de Design

### 1. Separação por Camada

Cada camada da Clean Architecture possui sua própria base de exceções:

| Camada | Base Exception | Responsabilidade |
|--------|----------------|------------------|
| Domain | `DomainException` | Regras de negócio, validação de entidades e value objects |
| Application | `ApplicationException` | Fluxo de use cases, autorização, validação de input |
| Infrastructure | `InfrastructureException` | Comunicação com serviços externos, persistência |

### 2. Idiomático Python

- Utiliza `raise ... from e` para encadeamento de exceções (não um campo `cause` manual)
- Acessa a causa original via `__cause__` nativo do Python
- Usa `dataclasses` para exceções como objetos de dados puros

### 3. Segurança

- Exceções de infraestrutura nunca expõem detalhes técnicos ao cliente
- Campo `internal_message` disponível apenas para logs
- `exception_id` permite correlação sem expor informações sensíveis

### 4. Trade-off Pragmático

O mapeamento `http_status` nas exceções é um trade-off consciente:

- **Purista**: O domínio não deveria conhecer HTTP
- **Pragmático**: Evita criar um mapeador externo cheio de condicionais

Se o projeto crescer muito ou virar uma biblioteca compartilhada, considere extrair para um mapper externo.

---

## Hierarquia Completa

```
CoreException
├── DomainException
│   ├── DomainValidationException
│   ├── BusinessRuleViolationException
│   ├── DomainNotFoundException
│   └── DomainConflictException
│
├── ApplicationException
│   ├── UseCaseValidationException
│   ├── UnauthorizedOperationException
│   ├── ForbiddenOperationException
│   └── ResourceNotFoundException
│
├── InfrastructureException
│   ├── GatewayException
│   │   ├── GatewayTimeoutException
│   │   ├── GatewayUnavailableException
│   │   ├── GatewayRateLimitException
│   │   └── GatewayBadResponseException
│   │
│   └── RepositoryException
│       ├── DatabaseConnectionException
│       └── DataIntegrityException
│
└── PresentationException
    ├── InvalidRequestFormatException
    ├── UnsupportedMediaTypeException
    ├── NotAcceptableException
    ├── MissingHeaderException
    ├── InvalidHeaderException
    ├── APIVersionException
    ├── APIRateLimitException
    └── RequestEntityTooLargeException
```

### Mapeamento HTTP

| Exceção | HTTP Status | Uso |
|---------|-------------|-----|
| **Domain** | | |
| `DomainValidationException` | 422 | Estado inválido de entidade/value object |
| `BusinessRuleViolationException` | 422 | Violação de regra de negócio |
| `DomainNotFoundException` | 404 | Agregado não encontrado |
| `DomainConflictException` | 409 | Conflito de estado no domínio |
| **Application** | | |
| `UseCaseValidationException` | 400 | Input do use case inválido |
| `UnauthorizedOperationException` | 401 | Usuário não autenticado |
| `ForbiddenOperationException` | 403 | Usuário sem permissão |
| `ResourceNotFoundException` | 404 | Recurso do request não encontrado |
| **Infrastructure** | | |
| `GatewayTimeoutException` | 504 | Timeout em serviço externo |
| `GatewayUnavailableException` | 503 | Serviço externo indisponível |
| `GatewayRateLimitException` | 429 | Rate limit de serviço externo |
| `GatewayBadResponseException` | 502 | Resposta inválida de serviço externo |
| `DatabaseConnectionException` | 503 | Falha de conexão com banco |
| `DataIntegrityException` | 409 | Violação de constraint |
| **Presentation** | | |
| `InvalidRequestFormatException` | 400 | JSON malformado, encoding inválido |
| `UnsupportedMediaTypeException` | 415 | Content-Type não suportado |
| `NotAcceptableException` | 406 | Accept header não atendido |
| `MissingHeaderException` | 400 | Header obrigatório ausente |
| `InvalidHeaderException` | 400 | Header com valor inválido |
| `APIVersionException` | 400 | Versão da API não suportada |
| `APIRateLimitException` | 429 | Rate limit da API atingido |
| `RequestEntityTooLargeException` | 413 | Payload muito grande |

---

## Implementação

### Base (CoreException)

```python
# core/exceptions/base.py
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class Severity(str, Enum):
    """Níveis de severidade para observabilidade"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExceptionDetail:
    """
    Detalhe estruturado do erro.
    
    Útil para validações com múltiplos erros, onde cada campo
    pode ter sua própria mensagem de erro.
    
    Attributes:
        code: Código do erro (ex: "FIELD_INVALID", "REQUIRED_FIELD")
        message: Mensagem descritiva do erro
        field: Nome do campo relacionado (opcional)
        metadata: Dados adicionais para contexto (opcional)
    """
    code: str
    message: str
    field: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoreException(Exception):
    """
    Base de todas as exceções da aplicação.
    
    Fornece:
    - Estrutura padronizada e serializável
    - Rastreabilidade via exception_id
    - Suporte a observabilidade via severity e tags
    
    Attributes:
        message: Mensagem principal do erro
        code: Código único do tipo de erro (ex: "DOMAIN_VALIDATION_ERROR")
        details: Lista de detalhes para erros compostos
        exception_id: UUID único para rastreabilidade
        timestamp: Momento em que a exceção foi criada
        severity: Nível de severidade para alertas
        tags: Metadados para observabilidade (não enviados ao cliente)
    
    Example:
        >>> raise CoreException(
        ...     message="Algo deu errado",
        ...     code="GENERIC_ERROR",
        ...     severity=Severity.HIGH,
        ...     tags={"user_id": "123"}
        ... )
    """
    message: str
    code: str = "CORE_ERROR"
    details: list[ExceptionDetail] = field(default_factory=list)
    exception_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: Severity = Severity.MEDIUM
    tags: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        super().__init__(self.message)
    
    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        """
        Serializa a exceção para formato de resposta.
        
        Args:
            include_internal: Se True, inclui dados sensíveis.
                              Use apenas para logs, NUNCA para response HTTP.
        
        Returns:
            Dicionário com estrutura padronizada do erro.
        """
        result = {
            "type": "error",
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": self.exception_id,
                "details": [
                    {k: v for k, v in d.__dict__.items() if v is not None}
                    for d in self.details
                ] if self.details else None,
            }
        }
        
        if include_internal:
            result["_internal"] = {
                "severity": self.severity.value,
                "tags": self.tags,
                "timestamp": self.timestamp.isoformat(),
                "cause": str(self.__cause__) if self.__cause__ else None,
                "cause_type": type(self.__cause__).__name__ if self.__cause__ else None,
            }
        
        return result
    
    @property
    def http_status(self) -> int:
        """
        Código HTTP correspondente ao erro.
        
        Override nas subclasses para mapear corretamente.
        """
        return 500
```

### Domínio (DomainException)

```python
# core/exceptions/domain.py
from dataclasses import dataclass
from typing import Any
from .base import CoreException, ExceptionDetail


@dataclass
class DomainException(CoreException):
    """
    Base para violações de regras de negócio.
    
    Use para erros que representam violações das regras do domínio,
    independente de como a aplicação foi chamada (API, CLI, evento).
    """
    code: str = "DOMAIN_ERROR"
    
    @property
    def http_status(self) -> int:
        return 422


@dataclass
class DomainValidationException(DomainException):
    """
    Estado inválido de objeto do domínio (Entity, Value Object, Aggregate).
    
    Diferente de UseCaseValidationException:
    - DomainValidation: objeto do domínio não pode existir nesse estado
    - UseCaseValidation: input do request está malformado
    
    Attributes:
        object_type: Tipo do objeto sendo validado (ex: "CPF", "Document", "User")
    
    Example:
        >>> raise DomainValidationException(
        ...     message="CPF inválido",
        ...     object_type="CPF"
        ... )
        
        >>> # Ou com múltiplas violações:
        >>> raise DomainValidationException.from_violations(
        ...     object_type="Document",
        ...     violations={
        ...         "cpf": "CPF inválido",
        ...         "document_type": "Tipo não suportado"
        ...     }
        ... )
    """
    code: str = "DOMAIN_VALIDATION_ERROR"
    object_type: str = ""
    
    @classmethod
    def from_violations(
        cls,
        object_type: str,
        violations: dict[str, str],
        **kwargs
    ) -> "DomainValidationException":
        """
        Factory para criar exceção a partir de múltiplas violações.
        
        Args:
            object_type: Nome do tipo sendo validado
            violations: Dicionário campo -> mensagem de erro
            **kwargs: Argumentos adicionais para a exceção
        
        Returns:
            Instância de DomainValidationException com details preenchidos
        """
        details = [
            ExceptionDetail(
                code="FIELD_INVALID",
                message=msg,
                field=field_name
            )
            for field_name, msg in violations.items()
        ]
        return cls(
            message=f"Validation failed for {object_type}",
            object_type=object_type,
            details=details,
            **kwargs
        )
    
    def __post_init__(self):
        super().__post_init__()
        if self.object_type:
            self.tags["object_type"] = self.object_type


@dataclass
class BusinessRuleViolationException(DomainException):
    """
    Violação de regra de negócio.
    
    Use quando uma operação viola uma regra do domínio que não é
    simplesmente validação de dados.
    
    Attributes:
        rule_code: Código identificador da regra violada
    
    Exemplos de rule_code:
    - INSUFFICIENT_BALANCE: Saldo insuficiente
    - DOCUMENT_ALREADY_VERIFIED: Documento já verificado
    - CPF_BLOCKED: CPF bloqueado no sistema
    - DEVICE_NOT_BOUND: Dispositivo não vinculado
    - DAILY_LIMIT_EXCEEDED: Limite diário excedido
    - ACCOUNT_INACTIVE: Conta inativa
    
    Example:
        >>> raise BusinessRuleViolationException(
        ...     message="Documento já foi verificado anteriormente",
        ...     rule_code="DOCUMENT_ALREADY_VERIFIED"
        ... )
    """
    code: str = "BUSINESS_RULE_VIOLATION"
    rule_code: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        if self.rule_code:
            self.tags["rule_code"] = self.rule_code


@dataclass
class DomainNotFoundException(DomainException):
    """
    Agregado ou Entidade não encontrado no domínio.
    
    Lançada tipicamente por repositórios ou domain services quando
    um agregado esperado não existe.
    
    Attributes:
        resource_type: Tipo do recurso (ex: "User", "Document", "Order")
        resource_id: Identificador do recurso não encontrado
    
    .. note:: **DomainNotFoundException vs ResourceNotFoundException**
    
        Existe sobreposição semântica entre estas duas exceções. Ambas indicam
        "algo não existe". A distinção é:
        
        - **DomainNotFoundException**: Lançada pela camada de domínio (repositórios,
          domain services) quando um agregado/entidade não é encontrado.
        
        - **ResourceNotFoundException**: Lançada pela camada de aplicação (use cases)
          quando quer abstrair detalhes do domínio ou quando o "recurso" não é
          necessariamente um agregado (ex: permissão negada mascarada como not found).
        
        **Abordagem simplificada**: Se o time achar confuso manter duas exceções,
        é válido usar apenas ``DomainNotFoundException`` e deixá-la propagar até
        o handler. Ambas mapeiam para HTTP 404.
        
        **Abordagem detalhada**: Manter as duas permite que o use case converta
        ou enriqueça o erro antes de retornar, mantendo a camada de domínio
        desacoplada da apresentação.
    
    Example:
        >>> raise DomainNotFoundException(
        ...     message="Documento não encontrado",
        ...     resource_type="Document",
        ...     resource_id="doc-123"
        ... )
    """
    code: str = "DOMAIN_NOT_FOUND"
    resource_type: str = ""
    resource_id: str = ""
    
    @property
    def http_status(self) -> int:
        return 404
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["resource_type"] = self.resource_type
        self.tags["resource_id"] = self.resource_id


@dataclass
class DomainConflictException(DomainException):
    """
    Conflito de estado no domínio.
    
    Use para situações como:
    - Operações concorrentes no mesmo agregado
    - Tentativa de criar recurso que já existe
    - Conflito de versão (optimistic locking)
    
    Example:
        >>> raise DomainConflictException(
        ...     message="Documento foi modificado por outro processo",
        ...     tags={"expected_version": 1, "actual_version": 2}
        ... )
    """
    code: str = "DOMAIN_CONFLICT"
    
    @property
    def http_status(self) -> int:
        return 409
```

### Aplicação (ApplicationException)

```python
# core/exceptions/application.py
from dataclasses import dataclass
from .base import CoreException, ExceptionDetail


@dataclass
class ApplicationException(CoreException):
    """
    Base para erros de use case / application layer.
    
    Use para erros relacionados ao fluxo da aplicação,
    não às regras de negócio em si.
    """
    code: str = "APPLICATION_ERROR"
    
    @property
    def http_status(self) -> int:
        return 400


@dataclass
class UseCaseValidationException(ApplicationException):
    """
    Input do use case inválido.
    
    Diferente de DomainValidationException:
    - UseCaseValidation: input do request está malformado
    - DomainValidation: objeto do domínio não pode existir nesse estado
    
    Example:
        >>> raise UseCaseValidationException.required_field("document_id")
        
        >>> raise UseCaseValidationException.from_violations({
        ...     "email": "Formato de email inválido",
        ...     "age": "Deve ser maior que 18"
        ... })
    """
    code: str = "USE_CASE_VALIDATION_ERROR"
    
    @classmethod
    def from_violations(
        cls,
        violations: dict[str, str],
        **kwargs
    ) -> "UseCaseValidationException":
        """
        Factory para criar exceção a partir de múltiplas violações de input.
        
        Args:
            violations: Dicionário campo -> mensagem de erro
            **kwargs: Argumentos adicionais para a exceção
        
        Returns:
            Instância de UseCaseValidationException com details preenchidos
        """
        details = [
            ExceptionDetail(
                code="INVALID_INPUT",
                message=msg,
                field=field_name
            )
            for field_name, msg in violations.items()
        ]
        return cls(
            message="Invalid input",
            details=details,
            **kwargs
        )
    
    @classmethod
    def required_field(cls, field_name: str) -> "UseCaseValidationException":
        """
        Factory para campo obrigatório ausente.
        
        Args:
            field_name: Nome do campo obrigatório
        
        Returns:
            Instância de UseCaseValidationException
        """
        return cls(
            message=f"Field '{field_name}' is required",
            details=[
                ExceptionDetail(
                    code="REQUIRED_FIELD",
                    message="Campo obrigatório não informado",
                    field=field_name
                )
            ]
        )


@dataclass
class UnauthorizedOperationException(ApplicationException):
    """
    Usuário não autenticado.
    
    Use quando a operação requer autenticação mas o usuário
    não está autenticado ou o token é inválido.
    
    Example:
        >>> raise UnauthorizedOperationException(
        ...     message="Token expirado"
        ... )
    """
    code: str = "UNAUTHORIZED"
    
    @property
    def http_status(self) -> int:
        return 401


@dataclass
class ForbiddenOperationException(ApplicationException):
    """
    Usuário autenticado mas sem permissão.
    
    Use quando o usuário está autenticado mas não tem
    a permissão necessária para a operação.
    
    Attributes:
        required_permission: Permissão que seria necessária
    
    Example:
        >>> raise ForbiddenOperationException(
        ...     message="Permissão insuficiente para aprovar documentos",
        ...     required_permission="document:approve"
        ... )
    """
    code: str = "FORBIDDEN"
    required_permission: str = ""
    
    @property
    def http_status(self) -> int:
        return 403
    
    def __post_init__(self):
        super().__post_init__()
        if self.required_permission:
            self.tags["required_permission"] = self.required_permission


@dataclass
class ResourceNotFoundException(ApplicationException):
    """
    Recurso do request não encontrado (nível de use case).
    
    Diferente de DomainNotFoundException:
    - DomainNotFound: agregado não existe (lançado pelo repositório/domínio)
    - ResourceNotFound: recurso do request não existe (lançado pelo use case)
    
    Na prática, o use case frequentemente converte DomainNotFoundException
    em ResourceNotFoundException para abstrair detalhes do domínio.
    
    Attributes:
        resource_type: Tipo do recurso
        resource_id: Identificador do recurso
    
    Example:
        >>> raise ResourceNotFoundException(
        ...     message="Documento não encontrado",
        ...     resource_type="Document",
        ...     resource_id="doc-123"
        ... )
    """
    code: str = "RESOURCE_NOT_FOUND"
    resource_type: str = ""
    resource_id: str = ""
    
    @property
    def http_status(self) -> int:
        return 404
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["resource_type"] = self.resource_type
        self.tags["resource_id"] = self.resource_id
```

### Infraestrutura (InfrastructureException)

```python
# core/exceptions/infrastructure.py
from dataclasses import dataclass
from typing import Any
from .base import CoreException, Severity


@dataclass
class InfrastructureException(CoreException):
    """
    Base para erros de infraestrutura.
    
    IMPORTANTE: Mensagens técnicas NUNCA devem ser expostas ao cliente.
    Use internal_message para logs e a message padrão será genérica.
    
    Attributes:
        internal_message: Mensagem técnica detalhada (apenas para logs)
    """
    code: str = "INFRASTRUCTURE_ERROR"
    severity: Severity = Severity.HIGH
    internal_message: str = ""
    
    @property
    def http_status(self) -> int:
        return 502
    
    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        """
        Serializa a exceção.
        
        Para exceções de infraestrutura, a mensagem é sempre
        genérica quando include_internal=False.
        """
        result = super().to_dict(include_internal)
        
        # Mensagem genérica pro cliente - NUNCA expor detalhes técnicos
        if not include_internal:
            result["error"]["message"] = "Erro interno. Tente novamente mais tarde."
        else:
            result["_internal"]["internal_message"] = self.internal_message
        
        return result


# ============================================================================
# Gateway Exceptions (APIs externas)
# ============================================================================

@dataclass
class GatewayException(InfrastructureException):
    """
    Base para erros de comunicação com serviços externos.
    
    Attributes:
        gateway_name: Nome do serviço externo (ex: "OCR", "SMS", "EmailProvider")
    """
    code: str = "GATEWAY_ERROR"
    gateway_name: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["gateway"] = self.gateway_name


@dataclass
class GatewayTimeoutException(GatewayException):
    """
    Timeout ao chamar serviço externo.
    
    Attributes:
        timeout_seconds: Tempo de timeout configurado
    
    Example:
        >>> try:
        ...     response = httpx.get(url, timeout=30)
        ... except httpx.TimeoutException as e:
        ...     raise GatewayTimeoutException(
        ...         message="Timeout ao processar OCR",
        ...         gateway_name="OCR",
        ...         timeout_seconds=30,
        ...         internal_message=str(e)
        ...     ) from e
    """
    code: str = "GATEWAY_TIMEOUT"
    timeout_seconds: float | None = None
    
    @property
    def http_status(self) -> int:
        return 504
    
    def __post_init__(self):
        super().__post_init__()
        if self.timeout_seconds:
            self.tags["timeout_seconds"] = self.timeout_seconds


@dataclass
class GatewayUnavailableException(GatewayException):
    """
    Serviço externo indisponível.
    
    Use quando não é possível estabelecer conexão com o serviço.
    
    Example:
        >>> try:
        ...     response = httpx.get(url)
        ... except httpx.ConnectError as e:
        ...     raise GatewayUnavailableException(
        ...         message="Serviço de OCR indisponível",
        ...         gateway_name="OCR",
        ...         internal_message=str(e)
        ...     ) from e
    """
    code: str = "GATEWAY_UNAVAILABLE"
    
    @property
    def http_status(self) -> int:
        return 503


@dataclass
class GatewayRateLimitException(GatewayException):
    """
    Rate limit do serviço externo atingido.
    
    Attributes:
        retry_after_seconds: Segundos para aguardar antes de retry (se disponível)
    
    Example:
        >>> raise GatewayRateLimitException(
        ...     message="Rate limit do serviço de SMS",
        ...     gateway_name="SMS",
        ...     retry_after_seconds=60
        ... )
    """
    code: str = "GATEWAY_RATE_LIMIT"
    retry_after_seconds: int | None = None
    
    @property
    def http_status(self) -> int:
        return 429
    
    def __post_init__(self):
        super().__post_init__()
        if self.retry_after_seconds:
            self.tags["retry_after"] = self.retry_after_seconds


@dataclass
class GatewayBadResponseException(GatewayException):
    """
    Resposta inesperada ou inválida do serviço externo.
    
    Use quando o serviço responde, mas com dados inválidos
    ou status code inesperado.
    
    Attributes:
        original_status: Status code retornado pelo serviço
    
    Example:
        >>> raise GatewayBadResponseException(
        ...     message="Resposta inválida do serviço de OCR",
        ...     gateway_name="OCR",
        ...     original_status=500,
        ...     internal_message="Response body: {\"error\": \"internal\"}"
        ... )
    """
    code: str = "GATEWAY_BAD_RESPONSE"
    original_status: int | None = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.original_status:
            self.tags["original_status"] = self.original_status


# ============================================================================
# Repository Exceptions (Persistência)
# ============================================================================

@dataclass
class RepositoryException(InfrastructureException):
    """Base para erros de persistência/banco de dados."""
    code: str = "REPOSITORY_ERROR"


@dataclass
class DatabaseConnectionException(RepositoryException):
    """
    Falha de conexão com banco de dados.
    
    Severidade CRITICAL pois afeta toda a aplicação.
    
    Example:
        >>> try:
        ...     connection = pool.acquire()
        ... except ConnectionError as e:
        ...     raise DatabaseConnectionException(
        ...         message="Falha ao conectar no banco",
        ...         internal_message=str(e)
        ...     ) from e
    """
    code: str = "DATABASE_CONNECTION_ERROR"
    severity: Severity = Severity.CRITICAL
    
    @property
    def http_status(self) -> int:
        return 503


@dataclass
class DataIntegrityException(RepositoryException):
    """
    Violação de integridade no banco (unique constraint, FK, etc).
    
    Geralmente indica:
    - Problema de lógica na aplicação
    - Race condition
    - Dados inconsistentes
    
    Attributes:
        constraint_name: Nome da constraint violada (se disponível)
    
    Example:
        >>> try:
        ...     await session.commit()
        ... except IntegrityError as e:
        ...     raise DataIntegrityException(
        ...         message="Violação de integridade",
        ...         constraint_name="uq_user_email",
        ...         internal_message=str(e)
        ...     ) from e
    """
    code: str = "DATA_INTEGRITY_ERROR"
    constraint_name: str = ""
    
    @property
    def http_status(self) -> int:
        return 409
    
    def __post_init__(self):
        super().__post_init__()
        if self.constraint_name:
            self.tags["constraint"] = self.constraint_name
```

### Apresentação (PresentationException)

> **Observação importante**: A camada de apresentação (API REST) geralmente não precisa de exceções próprias porque ela é o **ponto de entrada** - ela recebe erros das outras camadas e os transforma em respostas HTTP. Porém, existem cenários onde exceções específicas da API fazem sentido.

#### Quando usar PresentationException?

| Cenário | Exemplo |
|---------|---------|
| Parsing/deserialização falhou | JSON malformado, content-type inválido |
| Validação de request (antes do use case) | Header obrigatório ausente, query param inválido |
| Negociação de conteúdo | Accept header não suportado |
| Versionamento de API | Versão da API não suportada |
| Rate limiting da própria API | Limite de requests do cliente |

#### Implementação

```python
# api/exceptions.py
from dataclasses import dataclass
from core.exceptions import CoreException, ExceptionDetail, Severity


@dataclass
class PresentationException(CoreException):
    """
    Base para erros da camada de apresentação (API).
    
    Use para erros que ocorrem ANTES de chegar ao use case,
    relacionados ao protocolo HTTP ou parsing do request.
    
    Observação: A maioria dos projetos não precisa dessas exceções,
    pois o FastAPI/Pydantic já tratam muitos desses casos. Use apenas
    quando precisar de controle mais granular sobre o formato de erro
    ou para cenários não cobertos pelo framework.
    """
    code: str = "PRESENTATION_ERROR"
    
    @property
    def http_status(self) -> int:
        return 400


@dataclass
class InvalidRequestFormatException(PresentationException):
    """
    Request com formato inválido (JSON malformado, encoding errado, etc).
    
    Example:
        >>> raise InvalidRequestFormatException(
        ...     message="Invalid JSON",
        ...     details=[ExceptionDetail(
        ...         code="JSON_PARSE_ERROR",
        ...         message="Expecting ',' delimiter: line 1 column 15"
        ...     )]
        ... )
    """
    code: str = "INVALID_REQUEST_FORMAT"


@dataclass
class UnsupportedMediaTypeException(PresentationException):
    """
    Content-Type não suportado.
    
    Attributes:
        received_type: Content-Type recebido
        supported_types: Lista de tipos suportados
    """
    code: str = "UNSUPPORTED_MEDIA_TYPE"
    received_type: str = ""
    supported_types: list[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.supported_types = self.supported_types or ["application/json"]
        self.tags["received_type"] = self.received_type
        self.tags["supported_types"] = self.supported_types
    
    @property
    def http_status(self) -> int:
        return 415


@dataclass
class NotAcceptableException(PresentationException):
    """
    Accept header não pode ser atendido.
    
    Attributes:
        requested_type: Tipo solicitado no Accept header
        available_types: Tipos que a API pode retornar
    """
    code: str = "NOT_ACCEPTABLE"
    requested_type: str = ""
    available_types: list[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.available_types = self.available_types or ["application/json"]
    
    @property
    def http_status(self) -> int:
        return 406


@dataclass
class MissingHeaderException(PresentationException):
    """
    Header obrigatório ausente.
    
    Attributes:
        header_name: Nome do header ausente
    """
    code: str = "MISSING_HEADER"
    header_name: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["header_name"] = self.header_name
        if not self.details:
            self.details = [
                ExceptionDetail(
                    code="REQUIRED_HEADER",
                    message=f"Header '{self.header_name}' is required",
                    field=self.header_name
                )
            ]


@dataclass
class InvalidHeaderException(PresentationException):
    """
    Header com valor inválido.
    
    Attributes:
        header_name: Nome do header
        header_value: Valor recebido
        expected_format: Formato esperado (para mensagem de erro)
    """
    code: str = "INVALID_HEADER"
    header_name: str = ""
    header_value: str = ""
    expected_format: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["header_name"] = self.header_name


@dataclass
class APIVersionException(PresentationException):
    """
    Versão da API não suportada.
    
    Attributes:
        requested_version: Versão solicitada
        supported_versions: Versões disponíveis
    """
    code: str = "API_VERSION_NOT_SUPPORTED"
    requested_version: str = ""
    supported_versions: list[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.supported_versions = self.supported_versions or []
        self.tags["requested_version"] = self.requested_version
        self.tags["supported_versions"] = self.supported_versions


@dataclass
class APIRateLimitException(PresentationException):
    """
    Rate limit da API atingido.
    
    Diferente de GatewayRateLimitException:
    - GatewayRateLimitException: serviço externo limitou nossa aplicação
    - APIRateLimitException: nossa API limitou o cliente
    
    Attributes:
        limit: Limite configurado
        window_seconds: Janela de tempo em segundos
        retry_after_seconds: Quando o cliente pode tentar novamente
    """
    code: str = "API_RATE_LIMIT"
    limit: int = 0
    window_seconds: int = 0
    retry_after_seconds: int | None = None
    severity: Severity = Severity.LOW  # Rate limit não é crítico
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["limit"] = self.limit
        self.tags["window_seconds"] = self.window_seconds
    
    @property
    def http_status(self) -> int:
        return 429


@dataclass
class RequestEntityTooLargeException(PresentationException):
    """
    Payload excede o limite permitido.
    
    Attributes:
        max_size_bytes: Tamanho máximo permitido
        received_size_bytes: Tamanho recebido
    """
    code: str = "REQUEST_ENTITY_TOO_LARGE"
    max_size_bytes: int = 0
    received_size_bytes: int = 0
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["max_size_bytes"] = self.max_size_bytes
        self.tags["received_size_bytes"] = self.received_size_bytes
    
    @property
    def http_status(self) -> int:
        return 413
```

#### Uso com Middlewares e Dependencies

```python
# api/dependencies/content_type.py
from fastapi import Request
from api.exceptions import UnsupportedMediaTypeException


async def validate_content_type(request: Request):
    """Dependency para validar Content-Type."""
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        
        if not content_type.startswith("application/json"):
            raise UnsupportedMediaTypeException(
                message="Content-Type must be application/json",
                received_type=content_type,
                supported_types=["application/json"]
            )
```

```python
# api/dependencies/rate_limit.py
from fastapi import Request
from api.exceptions import APIRateLimitException


class RateLimiter:
    async def check(self, request: Request, client_id: str):
        # ... lógica de rate limiting
        
        if limit_exceeded:
            raise APIRateLimitException(
                message="Rate limit exceeded",
                limit=100,
                window_seconds=60,
                retry_after_seconds=remaining_seconds,
            )
```

```python
# api/dependencies/api_version.py
from fastapi import Request
from api.exceptions import APIVersionException

SUPPORTED_VERSIONS = ["v1", "v2"]


async def validate_api_version(request: Request):
    """Valida header X-API-Version."""
    version = request.headers.get("X-API-Version", "v1")
    
    if version not in SUPPORTED_VERSIONS:
        raise APIVersionException(
            message=f"API version '{version}' is not supported",
            requested_version=version,
            supported_versions=SUPPORTED_VERSIONS,
        )
```

### Módulo de Exportação

```python
# core/exceptions/__init__.py
from .base import CoreException, ExceptionDetail, Severity
from .domain import (
    DomainException,
    DomainValidationException,
    BusinessRuleViolationException,
    DomainNotFoundException,
    DomainConflictException,
)
from .application import (
    ApplicationException,
    UseCaseValidationException,
    UnauthorizedOperationException,
    ForbiddenOperationException,
    ResourceNotFoundException,
)
from .infrastructure import (
    InfrastructureException,
    GatewayException,
    GatewayTimeoutException,
    GatewayUnavailableException,
    GatewayRateLimitException,
    GatewayBadResponseException,
    RepositoryException,
    DatabaseConnectionException,
    DataIntegrityException,
)

__all__ = [
    # Base
    "CoreException",
    "ExceptionDetail",
    "Severity",
    # Domain
    "DomainException",
    "DomainValidationException",
    "BusinessRuleViolationException",
    "DomainNotFoundException",
    "DomainConflictException",
    # Application
    "ApplicationException",
    "UseCaseValidationException",
    "UnauthorizedOperationException",
    "ForbiddenOperationException",
    "ResourceNotFoundException",
    # Infrastructure
    "InfrastructureException",
    "GatewayException",
    "GatewayTimeoutException",
    "GatewayUnavailableException",
    "GatewayRateLimitException",
    "GatewayBadResponseException",
    "RepositoryException",
    "DatabaseConnectionException",
    "DataIntegrityException",
]
```

```python
# api/exceptions/__init__.py
from .presentation import (
    PresentationException,
    InvalidRequestFormatException,
    UnsupportedMediaTypeException,
    NotAcceptableException,
    MissingHeaderException,
    InvalidHeaderException,
    APIVersionException,
    APIRateLimitException,
    RequestEntityTooLargeException,
)

__all__ = [
    "PresentationException",
    "InvalidRequestFormatException",
    "UnsupportedMediaTypeException",
    "NotAcceptableException",
    "MissingHeaderException",
    "InvalidHeaderException",
    "APIVersionException",
    "APIRateLimitException",
    "RequestEntityTooLargeException",
]
```

---

## Handler Global (FastAPI)

```python
# api/exception_handlers.py
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from core.exceptions import CoreException, ExceptionDetail, Severity

logger = structlog.get_logger()


async def core_exception_handler(request: Request, exc: CoreException) -> JSONResponse:
    """
    Handler global para todas as exceções da aplicação.
    
    Inclui CoreException e todas as suas derivadas:
    - DomainException
    - ApplicationException
    - InfrastructureException
    - PresentationException
    
    Responsabilidades:
    1. Logar exceção com detalhes internos
    2. Enviar alertas para exceções críticas
    3. Retornar response limpa ao cliente
    """
    
    # 1. Log completo com detalhes internos
    log_data = exc.to_dict(include_internal=True)
    log_data["path"] = request.url.path
    log_data["method"] = request.method
    log_data["client_ip"] = request.client.host if request.client else None
    
    if exc.severity in (Severity.HIGH, Severity.CRITICAL):
        logger.error("exception_raised", **log_data)
    else:
        logger.warning("exception_raised", **log_data)
    
    # 2. Alertas para monitoramento (implementar conforme necessidade)
    if exc.severity == Severity.CRITICAL:
        # await send_to_pagerduty(exc)
        pass
    
    if exc.tags.get("fraud_signal"):
        # await send_to_fraud_monitoring(exc)
        pass
    
    # 3. Response limpa pro cliente
    response = JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(include_internal=False),
        headers={"X-Request-ID": exc.exception_id}
    )
    
    # Header Retry-After para rate limit
    if hasattr(exc, "retry_after_seconds") and exc.retry_after_seconds:
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
    
    return response


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handler para erros de validação do Pydantic/FastAPI.
    
    Converte o formato do Pydantic para nosso formato padronizado,
    mantendo consistência nas respostas de erro.
    """
    import uuid
    
    exception_id = str(uuid.uuid4())
    
    details = [
        ExceptionDetail(
            code="VALIDATION_ERROR",
            message=error.get("msg", "Invalid value"),
            field=".".join(str(loc) for loc in error.get("loc", [])),
            metadata={"type": error.get("type")}
        )
        for error in exc.errors()
    ]
    
    response_body = {
        "type": "error",
        "error": {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "Request validation failed",
            "request_id": exception_id,
            "details": [
                {k: v for k, v in d.__dict__.items() if v is not None}
                for d in details
            ],
        }
    }
    
    logger.warning(
        "request_validation_error",
        exception_id=exception_id,
        path=request.url.path,
        errors=exc.errors(),
    )
    
    return JSONResponse(
        status_code=422,
        content=response_body,
        headers={"X-Request-ID": exception_id}
    )


async def json_decode_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler para erros de parsing JSON.
    
    Captura JSONDecodeError e retorna erro padronizado.
    """
    import uuid
    
    exception_id = str(uuid.uuid4())
    
    logger.warning(
        "json_decode_error",
        exception_id=exception_id,
        path=request.url.path,
        error=str(exc),
    )
    
    return JSONResponse(
        status_code=400,
        content={
            "type": "error",
            "error": {
                "code": "INVALID_REQUEST_FORMAT",
                "message": "Invalid JSON in request body",
                "request_id": exception_id,
                "details": None,
            }
        },
        headers={"X-Request-ID": exception_id}
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler para exceções não tratadas.
    
    Captura qualquer exceção que não seja CoreException e
    retorna erro genérico ao cliente. Loga o traceback completo
    para debugging.
    """
    import traceback
    import uuid
    
    exception_id = str(uuid.uuid4())
    
    logger.error(
        "unhandled_exception",
        exception_id=exception_id,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        traceback=traceback.format_exc(),
        path=request.url.path,
        method=request.method,
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "type": "error",
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Erro interno. Tente novamente mais tarde.",
                "request_id": exception_id,
                "details": None,
            }
        },
        headers={"X-Request-ID": exception_id}
    )
```

### Registro dos Handlers

```python
# main.py
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from json import JSONDecodeError

from core.exceptions import CoreException
from api.exception_handlers import (
    core_exception_handler,
    request_validation_handler,
    json_decode_handler,
    unhandled_exception_handler,
)

app = FastAPI()

# Ordem importa: mais específico primeiro
app.add_exception_handler(RequestValidationError, request_validation_handler)
app.add_exception_handler(JSONDecodeError, json_decode_handler)
app.add_exception_handler(CoreException, core_exception_handler)  # Inclui todas as derivadas
app.add_exception_handler(Exception, unhandled_exception_handler)
```

---

## Exemplos de Uso

### Value Object

```python
# domain/value_objects/cpf.py
from core.exceptions import DomainValidationException, ExceptionDetail


class CPF:
    """Value Object para CPF."""
    
    def __init__(self, value: str):
        cleaned = self._clean(value)
        
        if not self._is_valid(cleaned):
            raise DomainValidationException(
                message="CPF inválido",
                object_type="CPF",
                details=[
                    ExceptionDetail(
                        code="INVALID_FORMAT",
                        message="CPF deve conter 11 dígitos válidos",
                        field="value"
                    )
                ]
            )
        
        self._value = cleaned
    
    @staticmethod
    def _clean(value: str) -> str:
        return "".join(filter(str.isdigit, value))
    
    @staticmethod
    def _is_valid(value: str) -> bool:
        if len(value) != 11:
            return False
        # ... validação de dígitos verificadores
        return True
    
    @property
    def value(self) -> str:
        return self._value
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CPF):
            return False
        return self._value == other._value
    
    def __hash__(self) -> int:
        return hash(self._value)
```

### Entity

```python
# domain/entities/document.py
from core.exceptions import (
    DomainValidationException,
    BusinessRuleViolationException,
)
from domain.value_objects import CPF


class Document:
    """Entidade de Documento."""
    
    ALLOWED_TYPES = ["RG", "CNH", "PASSPORT"]
    
    def __init__(
        self,
        id: str,
        cpf: CPF,
        document_type: str,
    ):
        violations = {}
        
        if document_type not in self.ALLOWED_TYPES:
            violations["document_type"] = (
                f"Tipo deve ser um de: {', '.join(self.ALLOWED_TYPES)}"
            )
        
        if violations:
            raise DomainValidationException.from_violations(
                object_type="Document",
                violations=violations
            )
        
        self._id = id
        self._cpf = cpf
        self._document_type = document_type
        self._verified = False
        self._verified_at = None
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def is_verified(self) -> bool:
        return self._verified
    
    def mark_as_verified(self) -> None:
        """
        Marca documento como verificado.
        
        Raises:
            BusinessRuleViolationException: Se documento já foi verificado
        """
        if self._verified:
            raise BusinessRuleViolationException(
                message="Documento já foi verificado anteriormente",
                rule_code="DOCUMENT_ALREADY_VERIFIED"
            )
        
        from datetime import datetime, timezone
        self._verified = True
        self._verified_at = datetime.now(timezone.utc)
```

### Use Case

```python
# application/use_cases/verify_document.py
from dataclasses import dataclass
from core.exceptions import (
    UseCaseValidationException,
    ResourceNotFoundException,
)


@dataclass
class VerifyDocumentInput:
    document_id: str
    image_base64: str


@dataclass
class VerifyDocumentOutput:
    verified: bool
    verified_at: str


class VerifyDocumentUseCase:
    """Use case para verificação de documento."""
    
    def __init__(
        self,
        document_repository,
        ocr_gateway,
    ):
        self._document_repository = document_repository
        self._ocr_gateway = ocr_gateway
    
    async def execute(self, input: VerifyDocumentInput) -> VerifyDocumentOutput:
        # 1. Validação de input (Application Layer)
        self._validate_input(input)
        
        # 2. Busca documento
        document = await self._document_repository.find_by_id(input.document_id)
        if not document:
            raise ResourceNotFoundException(
                message=f"Documento {input.document_id} não encontrado",
                resource_type="Document",
                resource_id=input.document_id
            )
        
        # 3. Processa OCR (pode lançar GatewayException)
        ocr_result = await self._ocr_gateway.extract(input.image_base64)
        
        # 4. Regra de domínio (pode lançar BusinessRuleViolationException)
        document.mark_as_verified()
        
        # 5. Persiste
        await self._document_repository.save(document)
        
        return VerifyDocumentOutput(
            verified=True,
            verified_at=document._verified_at.isoformat()
        )
    
    def _validate_input(self, input: VerifyDocumentInput) -> None:
        violations = {}
        
        if not input.document_id:
            violations["document_id"] = "Document ID é obrigatório"
        
        if not input.image_base64:
            violations["image_base64"] = "Imagem é obrigatória"
        
        if violations:
            raise UseCaseValidationException.from_violations(violations)
```

### Gateway

```python
# infrastructure/gateways/ocr_gateway.py
import httpx
from core.exceptions import (
    GatewayTimeoutException,
    GatewayUnavailableException,
    GatewayBadResponseException,
    GatewayRateLimitException,
)


class OCRGateway:
    """Gateway para serviço de OCR externo."""
    
    GATEWAY_NAME = "OCR"
    
    def __init__(self, base_url: str, timeout: int = 30):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout
        )
        self._timeout = timeout
    
    async def extract(self, image_base64: str) -> dict:
        """
        Extrai texto de imagem via OCR.
        
        Raises:
            GatewayTimeoutException: Timeout na requisição
            GatewayUnavailableException: Serviço indisponível
            GatewayRateLimitException: Rate limit atingido
            GatewayBadResponseException: Resposta inválida
        """
        try:
            response = await self._client.post(
                "/extract",
                json={"image": image_base64}
            )
            
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                raise GatewayRateLimitException(
                    message="Rate limit do serviço de OCR",
                    gateway_name=self.GATEWAY_NAME,
                    retry_after_seconds=int(retry_after) if retry_after else None,
                )
            
            if response.status_code >= 400:
                raise GatewayBadResponseException(
                    message="Erro no serviço de OCR",
                    gateway_name=self.GATEWAY_NAME,
                    original_status=response.status_code,
                    internal_message=response.text,
                )
            
            return response.json()
            
        except httpx.TimeoutException as e:
            raise GatewayTimeoutException(
                message="Timeout ao processar OCR",
                gateway_name=self.GATEWAY_NAME,
                timeout_seconds=self._timeout,
                internal_message=str(e),
            ) from e
            
        except httpx.ConnectError as e:
            raise GatewayUnavailableException(
                message="Serviço de OCR indisponível",
                gateway_name=self.GATEWAY_NAME,
                internal_message=str(e),
            ) from e
```

### Repository

```python
# infrastructure/repositories/document_repository.py
from sqlalchemy.exc import IntegrityError, OperationalError
from core.exceptions import (
    DatabaseConnectionException,
    DataIntegrityException,
)


class SQLAlchemyDocumentRepository:
    """Implementação SQLAlchemy do repositório de documentos."""
    
    def __init__(self, session_factory):
        self._session_factory = session_factory
    
    async def save(self, document) -> None:
        """
        Persiste documento no banco.
        
        Raises:
            DatabaseConnectionException: Falha de conexão
            DataIntegrityException: Violação de constraint
        """
        try:
            async with self._session_factory() as session:
                session.add(self._to_model(document))
                await session.commit()
                
        except OperationalError as e:
            raise DatabaseConnectionException(
                message="Falha ao conectar no banco",
                internal_message=str(e),
            ) from e
            
        except IntegrityError as e:
            raise DataIntegrityException(
                message="Violação de integridade",
                constraint_name=self._extract_constraint_name(e),
                internal_message=str(e),
            ) from e
    
    @staticmethod
    def _extract_constraint_name(error: IntegrityError) -> str:
        # Implementação específica do banco
        return str(error.orig) if error.orig else ""
```

---

## Boas Práticas

### 1. Sempre use `raise ... from e`

```python
# ✅ Correto - preserva a causa original
try:
    result = external_service.call()
except ExternalError as e:
    raise GatewayException(...) from e

# ❌ Errado - perde o traceback original
try:
    result = external_service.call()
except ExternalError as e:
    raise GatewayException(...)
```

### 2. Nunca exponha detalhes técnicos ao cliente

```python
# ✅ Correto
raise DatabaseConnectionException(
    message="Falha ao conectar no banco",  # Genérico
    internal_message="Connection refused: localhost:5432"  # Só para logs
)

# ❌ Errado - expõe infraestrutura
raise DatabaseConnectionException(
    message="Connection refused: localhost:5432"
)
```

### 3. Use factories para múltiplas violações

```python
# ✅ Correto - estruturado
raise DomainValidationException.from_violations(
    object_type="User",
    violations={
        "email": "Formato inválido",
        "age": "Deve ser maior que 18"
    }
)

# ❌ Evite - menos estruturado
raise DomainValidationException(
    message="Email inválido e idade deve ser maior que 18"
)
```

### 4. Adicione tags relevantes para observabilidade

```python
raise BusinessRuleViolationException(
    message="Saldo insuficiente",
    rule_code="INSUFFICIENT_BALANCE",
    tags={
        "user_id": user.id,
        "requested_amount": amount,
        "available_balance": balance,
    }
)
```

### 5. Escolha a exceção correta por camada

| Situação | Exceção | Camada |
|----------|---------|--------|
| CPF com formato inválido | `DomainValidationException` | Domain |
| Documento já verificado | `BusinessRuleViolationException` | Domain |
| Campo obrigatório ausente no request | `UseCaseValidationException` | Application |
| Usuário tentando acessar recurso de outro | `ForbiddenOperationException` | Application |
| Timeout em API externa | `GatewayTimeoutException` | Infrastructure |
| Violação de unique constraint | `DataIntegrityException` | Infrastructure |
| JSON malformado no body | `InvalidRequestFormatException` | Presentation |
| Content-Type não é application/json | `UnsupportedMediaTypeException` | Presentation |
| Cliente excedeu rate limit da API | `APIRateLimitException` | Presentation |

---

## HTTP Status Mapper (Abordagem Purista)

Como discutido nos [Princípios de Design](#princípios-de-design), manter `http_status` nas exceções é um trade-off pragmático. Se você preferir uma abordagem purista onde o domínio não conhece HTTP, use um mapper externo.

### Quando usar o Mapper Externo?

| Cenário | Recomendação |
|---------|--------------|
| Projeto pequeno/médio | `http_status` na exceção (pragmático) |
| Biblioteca compartilhada entre projetos | Mapper externo |
| Múltiplos protocolos (HTTP, gRPC, GraphQL) | Mapper externo |
| Domínio precisa ser 100% puro | Mapper externo |

### Implementação

#### 1. Remova `http_status` das Exceções

```python
# core/exceptions/base.py
@dataclass
class CoreException(Exception):
    message: str
    code: str = "CORE_ERROR"
    details: list[ExceptionDetail] = field(default_factory=list)
    exception_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: Severity = Severity.MEDIUM
    tags: dict[str, Any] = field(default_factory=dict)
    
    # Removido: http_status property
    
    def __post_init__(self):
        super().__init__(self.message)
    
    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        # ... mesmo código anterior
        pass
```

#### 2. Crie o Mapper

```python
# api/exception_mapper.py
from typing import Type
from core.exceptions import (
    CoreException,
    # Domain
    DomainException,
    DomainValidationException,
    BusinessRuleViolationException,
    DomainNotFoundException,
    DomainConflictException,
    # Application
    ApplicationException,
    UseCaseValidationException,
    UnauthorizedOperationException,
    ForbiddenOperationException,
    ResourceNotFoundException,
    # Infrastructure
    InfrastructureException,
    GatewayException,
    GatewayTimeoutException,
    GatewayUnavailableException,
    GatewayRateLimitException,
    GatewayBadResponseException,
    RepositoryException,
    DatabaseConnectionException,
    DataIntegrityException,
)


class HTTPStatusMapper:
    """
    Mapeia exceções do domínio para códigos HTTP.
    
    Mantém o domínio puro, sem conhecimento de protocolos de transporte.
    O mapeamento é feito na camada de Interface Adapters (API).
    
    Example:
        >>> mapper = HTTPStatusMapper()
        >>> status = mapper.get_status(some_exception)
        >>> # ou
        >>> status = mapper.get_status_by_type(DomainValidationException)
    """
    
    # Mapeamento de tipo de exceção -> HTTP status
    _STATUS_MAP: dict[Type[CoreException], int] = {
        # Domain
        DomainException: 422,
        DomainValidationException: 422,
        BusinessRuleViolationException: 422,
        DomainNotFoundException: 404,
        DomainConflictException: 409,
        
        # Application
        ApplicationException: 400,
        UseCaseValidationException: 400,
        UnauthorizedOperationException: 401,
        ForbiddenOperationException: 403,
        ResourceNotFoundException: 404,
        
        # Infrastructure
        InfrastructureException: 502,
        GatewayException: 502,
        GatewayTimeoutException: 504,
        GatewayUnavailableException: 503,
        GatewayRateLimitException: 429,
        GatewayBadResponseException: 502,
        RepositoryException: 502,
        DatabaseConnectionException: 503,
        DataIntegrityException: 409,
    }
    
    # Status padrão para exceções não mapeadas
    DEFAULT_STATUS = 500
    
    def get_status(self, exception: CoreException) -> int:
        """
        Obtém o HTTP status para uma instância de exceção.
        
        Percorre a hierarquia de classes (MRO) para encontrar
        o mapeamento mais específico.
        
        Args:
            exception: Instância da exceção
        
        Returns:
            Código HTTP correspondente
        """
        return self.get_status_by_type(type(exception))
    
    def get_status_by_type(self, exception_type: Type[CoreException]) -> int:
        """
        Obtém o HTTP status para um tipo de exceção.
        
        Args:
            exception_type: Classe da exceção
        
        Returns:
            Código HTTP correspondente
        """
        # Busca direta
        if exception_type in self._STATUS_MAP:
            return self._STATUS_MAP[exception_type]
        
        # Busca na hierarquia (MRO - Method Resolution Order)
        for base_class in exception_type.__mro__:
            if base_class in self._STATUS_MAP:
                return self._STATUS_MAP[base_class]
        
        return self.DEFAULT_STATUS
    
    def register(self, exception_type: Type[CoreException], status: int) -> None:
        """
        Registra um novo mapeamento.
        
        Útil para exceções customizadas do projeto.
        
        Args:
            exception_type: Classe da exceção
            status: Código HTTP
        
        Example:
            >>> mapper.register(MyCustomException, 418)
        """
        self._STATUS_MAP[exception_type] = status
    
    def register_many(self, mappings: dict[Type[CoreException], int]) -> None:
        """
        Registra múltiplos mapeamentos de uma vez.
        
        Args:
            mappings: Dicionário tipo -> status
        """
        self._STATUS_MAP.update(mappings)


# Instância singleton para uso global
http_status_mapper = HTTPStatusMapper()
```

#### 3. Atualize o Handler

```python
# api/exception_handlers.py
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from core.exceptions import CoreException, Severity
from api.exception_mapper import http_status_mapper

logger = structlog.get_logger()


async def core_exception_handler(request: Request, exc: CoreException) -> JSONResponse:
    """
    Handler global usando mapper externo.
    """
    # Obtém status via mapper (não da exceção)
    http_status = http_status_mapper.get_status(exc)
    
    # Log completo
    log_data = exc.to_dict(include_internal=True)
    log_data["path"] = request.url.path
    log_data["method"] = request.method
    log_data["http_status"] = http_status
    
    if exc.severity in (Severity.HIGH, Severity.CRITICAL):
        logger.error("exception_raised", **log_data)
    else:
        logger.warning("exception_raised", **log_data)
    
    # Response
    return JSONResponse(
        status_code=http_status,
        content=exc.to_dict(include_internal=False),
        headers={"X-Request-ID": exc.exception_id}
    )
```

#### 4. Registrando Exceções Customizadas

```python
# main.py
from api.exception_mapper import http_status_mapper
from my_project.exceptions import (
    PaymentDeclinedException,
    QuotaExceededException,
)

# Registra exceções específicas do projeto
http_status_mapper.register(PaymentDeclinedException, 402)  # Payment Required
http_status_mapper.register(QuotaExceededException, 429)

# Ou em lote
http_status_mapper.register_many({
    PaymentDeclinedException: 402,
    QuotaExceededException: 429,
})
```

### Mapper para Múltiplos Protocolos

Se você precisa suportar HTTP, gRPC e GraphQL, pode criar mappers específicos:

```python
# api/mappers/__init__.py
from .http_mapper import HTTPStatusMapper
from .grpc_mapper import GRPCStatusMapper
from .graphql_mapper import GraphQLErrorMapper

__all__ = ["HTTPStatusMapper", "GRPCStatusMapper", "GraphQLErrorMapper"]
```

```python
# api/mappers/grpc_mapper.py
from grpc import StatusCode
from typing import Type
from core.exceptions import (
    CoreException,
    DomainNotFoundException,
    UnauthorizedOperationException,
    ForbiddenOperationException,
    GatewayUnavailableException,
    GatewayTimeoutException,
    # ...
)


class GRPCStatusMapper:
    """Mapeia exceções para códigos gRPC."""
    
    _STATUS_MAP: dict[Type[CoreException], StatusCode] = {
        DomainNotFoundException: StatusCode.NOT_FOUND,
        UnauthorizedOperationException: StatusCode.UNAUTHENTICATED,
        ForbiddenOperationException: StatusCode.PERMISSION_DENIED,
        GatewayUnavailableException: StatusCode.UNAVAILABLE,
        GatewayTimeoutException: StatusCode.DEADLINE_EXCEEDED,
        # ...
    }
    
    DEFAULT_STATUS = StatusCode.INTERNAL
    
    def get_status(self, exception: CoreException) -> StatusCode:
        for base_class in type(exception).__mro__:
            if base_class in self._STATUS_MAP:
                return self._STATUS_MAP[base_class]
        return self.DEFAULT_STATUS


grpc_status_mapper = GRPCStatusMapper()
```

```python
# api/mappers/graphql_mapper.py
from typing import Type
from core.exceptions import CoreException, UnauthorizedOperationException, ForbiddenOperationException


class GraphQLErrorMapper:
    """
    Mapeia exceções para extensões GraphQL.
    
    GraphQL sempre retorna 200, mas usa 'extensions' para metadados.
    """
    
    _EXTENSIONS_MAP: dict[Type[CoreException], dict] = {
        UnauthorizedOperationException: {
            "code": "UNAUTHENTICATED",
            "http_status": 401,
        },
        ForbiddenOperationException: {
            "code": "FORBIDDEN", 
            "http_status": 403,
        },
        # ...
    }
    
    def get_extensions(self, exception: CoreException) -> dict:
        for base_class in type(exception).__mro__:
            if base_class in self._EXTENSIONS_MAP:
                return {
                    **self._EXTENSIONS_MAP[base_class],
                    "request_id": exception.exception_id,
                }
        
        return {
            "code": exception.code,
            "request_id": exception.exception_id,
        }


graphql_error_mapper = GraphQLErrorMapper()
```

### Estrutura de Pastas Atualizada

```
project/
├── core/
│   └── exceptions/
│       ├── __init__.py
│       ├── base.py              # SEM http_status
│       ├── domain.py
│       ├── application.py
│       └── infrastructure.py
│
├── api/
│   ├── mappers/
│   │   ├── __init__.py
│   │   ├── http_mapper.py       # HTTPStatusMapper
│   │   ├── grpc_mapper.py       # GRPCStatusMapper (opcional)
│   │   └── graphql_mapper.py    # GraphQLErrorMapper (opcional)
│   ├── exception_handlers.py
│   └── main.py
│
└── ...
```

### Trade-offs

| Abordagem | Prós | Contras |
|-----------|------|---------|
| `http_status` na exceção | Simples, menos código, fácil manutenção | Domínio conhece HTTP |
| Mapper externo | Domínio puro, suporta múltiplos protocolos | Mais arquivos, mapeamento pode ficar dessincronizado |

**Recomendação**: Comece com `http_status` na exceção. Migre para mapper externo apenas se precisar de múltiplos protocolos ou se o projeto crescer a ponto de virar uma biblioteca compartilhada.

---

## Inicialização e Registro (FastAPI)

Esta seção mostra como registrar os handlers e mappers de forma limpa e organizada na aplicação FastAPI.

### Diagrama de Sequência de Inicialização

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INICIALIZAÇÃO DA APLICAÇÃO                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CONFIGURAÇÃO DE MENSAGENS (i18n)                                         │
│    - Registrar mensagens customizadas do projeto                            │
│    - Registrar regras de negócio específicas                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. CONFIGURAÇÃO DO HTTP STATUS MAPPER (se usar abordagem purista)           │
│    - Registrar mapeamentos de exceções customizadas                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. CRIAÇÃO DA APLICAÇÃO FASTAPI                                             │
│    - Instanciar FastAPI()                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. REGISTRO DOS EXCEPTION HANDLERS (ordem importa!)                         │
│    - RequestValidationError  (mais específico)                              │
│    - JSONDecodeError                                                        │
│    - CoreException           (captura toda a hierarquia)                    │
│    - Exception               (fallback - menos específico)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. REGISTRO DE MIDDLEWARES                                                  │
│    - Correlation ID middleware (PRIMEIRO - mais externo)                    │
│    - Logging middleware                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. REGISTRO DE ROTAS                                                        │
│    - Incluir routers                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Padronização de IDs

O sistema usa três tipos de identificadores que podem causar confusão:

| ID | Escopo | Propósito |
|----|--------|-----------|
| `correlation_id` | Request (cross-service) | Rastrear um request através de múltiplos serviços |
| `request_id` | Response (cliente) | ID retornado ao cliente para suporte |
| `exception_id` | Exceção (interno) | Identificar uma exceção específica (útil em batch) |

**Regra de ouro**: O `request_id` retornado ao cliente **deve ser o `correlation_id`** do request. Isso permite que o cliente reporte um ID que pode ser rastreado em toda a infraestrutura.

```python
# api/exceptions/handlers.py
from api.middlewares.correlation_id import get_correlation_id

async def core_exception_handler(request: Request, exc: CoreException) -> JSONResponse:
    # Usa correlation_id como request_id na resposta
    # O exception_id fica apenas para logs internos (útil se houver múltiplos erros)
    correlation_id = get_correlation_id()
    
    # ... logging com ambos os IDs
    log_data["correlation_id"] = correlation_id
    log_data["exception_id"] = exc.exception_id  # Interno apenas
    
    # Response usa correlation_id como request_id
    response_body = exc.to_dict(include_internal=False, locale=locale)
    response_body["error"]["request_id"] = correlation_id  # Sobrescreve
    
    return JSONResponse(
        status_code=exc.http_status,
        content=response_body,
        headers={
            "X-Request-ID": correlation_id,
            "X-Correlation-ID": correlation_id,
        }
    )
```

### Sanitização de Tags (Segurança)

As `tags` das exceções são logadas para observabilidade, mas podem conter dados sensíveis se um desenvolvedor não tiver cuidado. Implemente sanitização antes de logar:

```python
# api/utils/sanitization.py
"""
Utilitários para sanitização de dados antes de logging.
Evita vazamento de informações sensíveis.
"""
from typing import Any
import re


# Padrões de campos sensíveis (case-insensitive)
SENSITIVE_PATTERNS = [
    r"password",
    r"passwd",
    r"secret",
    r"token",
    r"api_key",
    r"apikey",
    r"auth",
    r"credential",
    r"credit_card",
    r"card_number",
    r"cvv",
    r"ssn",
    r"cpf",
    r"private_key",
]

SENSITIVE_REGEX = re.compile(
    "|".join(SENSITIVE_PATTERNS),
    re.IGNORECASE
)

# Valor de substituição
REDACTED = "[REDACTED]"


def is_sensitive_key(key: str) -> bool:
    """Verifica se uma chave parece conter dados sensíveis."""
    return bool(SENSITIVE_REGEX.search(key))


def sanitize_value(value: Any, max_depth: int = 3) -> Any:
    """
    Sanitiza um valor para logging seguro.
    
    - Strings longas são truncadas
    - Objetos complexos são convertidos para representação segura
    - Limita profundidade de recursão
    """
    if max_depth <= 0:
        return "[MAX_DEPTH_EXCEEDED]"
    
    if value is None:
        return None
    
    if isinstance(value, (bool, int, float)):
        return value
    
    if isinstance(value, str):
        # Trunca strings muito longas
        if len(value) > 200:
            return value[:200] + "...[TRUNCATED]"
        return value
    
    if isinstance(value, (list, tuple)):
        if len(value) > 10:
            return [sanitize_value(v, max_depth - 1) for v in value[:10]] + ["...[TRUNCATED]"]
        return [sanitize_value(v, max_depth - 1) for v in value]
    
    if isinstance(value, dict):
        return sanitize_dict(value, max_depth - 1)
    
    # Objetos complexos: só o tipo e repr truncado
    type_name = type(value).__name__
    try:
        repr_str = repr(value)[:50]
    except Exception:
        repr_str = "[REPR_FAILED]"
    
    return f"<{type_name}: {repr_str}>"


def sanitize_dict(data: dict[str, Any], max_depth: int = 3) -> dict[str, Any]:
    """
    Sanitiza um dicionário para logging seguro.
    
    - Remove/mascara campos sensíveis
    - Trunca valores longos
    - Limita profundidade
    """
    if not isinstance(data, dict):
        return {"_sanitized": str(data)[:100]}
    
    result = {}
    for key, value in data.items():
        str_key = str(key)
        
        if is_sensitive_key(str_key):
            result[str_key] = REDACTED
        else:
            result[str_key] = sanitize_value(value, max_depth)
    
    return result


def sanitize_tags(tags: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitiza tags de exceção para logging.
    
    Entry point principal para usar no exception handler.
    """
    return sanitize_dict(tags, max_depth=3)
```

#### Handler Atualizado com Sanitização

```python
# api/exceptions/handlers.py
from api.utils.sanitization import sanitize_tags, sanitize_dict
from api.dependencies.auth import get_current_user_id  # Sua implementação de auth

async def core_exception_handler(request: Request, exc: CoreException) -> JSONResponse:
    locale = get_locale_from_request(request)
    correlation_id = get_correlation_id()
    
    # Sanitiza dados antes de logar
    safe_tags = sanitize_tags(exc.tags)
    
    # Enriquece tags com contexto do request (apenas para logs, nunca na resposta)
    log_tags = {
        **safe_tags,
        "path": request.url.path,
        "method": request.method,
    }
    
    # Adiciona user_id se autenticado (enriquece observabilidade)
    # IMPORTANTE: Nunca incluir no JSON de resposta
    try:
        user_id = get_current_user_id(request)
        if user_id:
            log_tags["user_id"] = user_id
    except Exception:
        # Usuário não autenticado ou erro ao extrair - ignora silenciosamente
        pass
    
    log_data = {
        "event": "exception_raised",
        "correlation_id": correlation_id,
        "exception_id": exc.exception_id,
        "code": exc.code,
        "message": exc.message,  # Mensagem original, não traduzida
        "severity": exc.severity.value,
        "tags": log_tags,  # Tags enriquecidas e sanitizadas
        "client_ip": request.client.host if request.client else None,
        "locale": locale.value,
    }
    
    # Adiciona causa se existir (sanitizada)
    if exc.__cause__:
        log_data["cause"] = {
            "type": type(exc.__cause__).__name__,
            "message": str(exc.__cause__)[:500],  # Trunca mensagens longas
        }
    
    # Log com nível apropriado
    if exc.severity in (Severity.HIGH, Severity.CRITICAL):
        logger.error(**log_data)
    else:
        logger.warning(**log_data)
    
    # Response para o cliente (sem dados internos, sem user_id)
    response_body = exc.to_dict(include_internal=False, locale=locale)
    response_body["error"]["request_id"] = correlation_id
    
    return JSONResponse(
        status_code=exc.http_status,
        content=response_body,
        headers={
            "X-Request-ID": correlation_id,
            "X-Correlation-ID": correlation_id,
            "Content-Language": locale.value,
        }
    )
```

---

## Guia de Boas Práticas para Desenvolvedores

Este guia serve como onboarding para desenvolvedores que vão utilizar o framework de exceções no dia a dia.

### Princípios Fundamentais

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REGRAS DE OURO                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. SEMPRE use exceções da hierarquia - nunca lance Exception genérica       │
│ 2. SEMPRE use `raise ... from e` para preservar a causa original            │
│ 3. NUNCA exponha detalhes técnicos em mensagens para o cliente              │
│ 4. NUNCA coloque dados sensíveis (senhas, tokens, CPF) nas tags             │
│ 5. SEMPRE escolha a exceção correta pela camada onde o erro ocorre          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Árvore de Decisão: Qual Exceção Usar?

```
                              ┌─────────────────┐
                              │ Onde ocorreu o  │
                              │     erro?       │
                              └────────┬────────┘
                                       │
          ┌────────────────┬───────────┼───────────┬────────────────┐
          ▼                ▼           ▼           ▼                ▼
    ┌──────────┐    ┌───────────┐ ┌─────────┐ ┌──────────┐    ┌──────────┐
    │  Domain  │    │Application│ │  Infra  │ │   API    │    │ Não sei  │
    │ (Entity, │    │(Use Case) │ │(Gateway,│ │(Parsing, │    │          │
    │   VO)    │    │           │ │  Repo)  │ │ Headers) │    │          │
    └────┬─────┘    └─────┬─────┘ └────┬────┘ └────┬─────┘    └────┬─────┘
         │                │            │           │               │
         ▼                ▼            ▼           ▼               ▼
   Domain         Application    Infra       Presentation    Pergunte ao
   Exception      Exception      Exception   Exception       Tech Lead!
```

### Cheat Sheet: Exceções por Situação

| Situação | Exceção | Exemplo |
|----------|---------|---------|
| CPF com formato inválido | `DomainValidationException` | Value Object rejeitando input |
| Email duplicado no banco | `DataIntegrityException` | Constraint violation |
| Usuário não encontrado | `DomainNotFoundException` | Repository.get_by_id() |
| Usuário sem permissão | `ForbiddenOperationException` | Use case verificando ACL |
| Token JWT expirado | `UnauthorizedOperationException` | Middleware de auth |
| Documento já verificado | `BusinessRuleViolationException` | Regra de negócio |
| API externa timeout | `GatewayTimeoutException` | Gateway chamando serviço |
| API externa retornou 500 | `GatewayUnavailableException` | Serviço fora do ar |
| JSON malformado no body | `InvalidRequestFormatException` | Parsing falhou |
| Content-Type errado | `UnsupportedMediaTypeException` | Header inválido |
| Rate limit do cliente | `APIRateLimitException` | Muitas requisições |
| Campo obrigatório ausente | `UseCaseValidationException` | Input do use case |

### Padrões de Código

#### ✅ CERTO: Value Object com Validação

```python
# domain/value_objects/email.py
from dataclasses import dataclass
import re
from core.exceptions import DomainValidationException, ExceptionDetail

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


@dataclass(frozen=True)
class Email:
    value: str
    
    def __post_init__(self):
        if not self.value:
            raise DomainValidationException(
                message="Email is required",
                object_type="Email",
                details=[
                    ExceptionDetail(
                        code="REQUIRED_FIELD",
                        message="Email cannot be empty",
                        field="email"
                    )
                ]
            )
        
        if not EMAIL_REGEX.match(self.value):
            raise DomainValidationException(
                message="Invalid email format",
                object_type="Email",
                details=[
                    ExceptionDetail(
                        code="FIELD_INVALID",
                        message=f"'{self.value}' is not a valid email",
                        field="email"
                    )
                ]
            )
```

#### ✅ CERTO: Repository com Exceção Encadeada

```python
# infrastructure/repositories/user_repository.py
from sqlalchemy.exc import IntegrityError, OperationalError
from core.exceptions import (
    DomainNotFoundException,
    DataIntegrityException,
    DatabaseConnectionException,
    Severity,
)


class SQLAlchemyUserRepository:
    def get_by_id(self, user_id: str) -> User:
        user = self._session.get(User, user_id)
        if not user:
            raise DomainNotFoundException(
                message="User not found",
                resource_type="User",
                resource_id=user_id
            )
        return user
    
    def save(self, user: User) -> None:
        try:
            self._session.add(user)
            self._session.commit()
        except IntegrityError as e:
            self._session.rollback()
            raise DataIntegrityException(
                message="User already exists",
                constraint_name="users_email_unique",
                tags={"user_id": user.id}
            ) from e  # ⬅️ SEMPRE preserve a causa!
        except OperationalError as e:
            self._session.rollback()
            raise DatabaseConnectionException(
                message="Database connection failed",
                internal_message=str(e),  # ⬅️ Detalhes só no internal
                severity=Severity.CRITICAL,
            ) from e
```

#### ✅ CERTO: Use Case com Tratamento de Erros

```python
# application/use_cases/create_user.py
from dataclasses import dataclass
from core.exceptions import (
    UseCaseValidationException,
    ResourceNotFoundException,
    ExceptionDetail,
)


@dataclass
class CreateUserInput:
    email: str
    name: str
    organization_id: str


class CreateUserUseCase:
    def execute(self, input: CreateUserInput) -> UserDTO:
        # 1. Validação de input (Application Layer)
        errors = []
        if not input.email:
            errors.append(ExceptionDetail(
                code="REQUIRED_FIELD",
                message="Email is required",
                field="email"
            ))
        if not input.name:
            errors.append(ExceptionDetail(
                code="REQUIRED_FIELD", 
                message="Name is required",
                field="name"
            ))
        
        if errors:
            raise UseCaseValidationException(
                message="Invalid input",
                details=errors
            )
        
        # 2. Busca dependências (pode lançar DomainNotFoundException)
        try:
            org = self._org_repo.get_by_id(input.organization_id)
        except DomainNotFoundException:
            # Converte para ResourceNotFound (abstrai o domínio)
            raise ResourceNotFoundException(
                message="Organization not found",
                resource_type="Organization",
                resource_id=input.organization_id
            )
        
        # 3. Cria o usuário (Domain Layer pode validar)
        email = Email(input.email)  # Pode lançar DomainValidationException
        user = User.create(email=email, name=input.name, organization=org)
        
        # 4. Persiste (pode lançar DataIntegrityException)
        self._user_repo.save(user)
        
        return UserDTO.from_entity(user)
```

#### ✅ CERTO: Gateway com Retry e Exceções Específicas

```python
# infrastructure/gateways/payment_gateway.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from core.exceptions import (
    GatewayTimeoutException,
    GatewayUnavailableException,
    GatewayRateLimitException,
    GatewayBadResponseException,
    Severity,
)


class StripeGateway:
    GATEWAY_NAME = "Stripe"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    def charge(self, amount: int, currency: str, token: str) -> PaymentResult:
        try:
            response = self._client.post(
                "/v1/charges",
                json={"amount": amount, "currency": currency, "source": token},
                timeout=30.0
            )
            
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise GatewayRateLimitException(
                    message="Stripe rate limit exceeded",
                    gateway_name=self.GATEWAY_NAME,
                    retry_after_seconds=int(retry_after),
                )
            
            if response.status_code >= 500:
                raise GatewayUnavailableException(
                    message="Stripe is unavailable",
                    gateway_name=self.GATEWAY_NAME,
                    internal_message=f"HTTP {response.status_code}: {response.text[:200]}",
                    severity=Severity.HIGH,
                )
            
            if response.status_code >= 400:
                raise GatewayBadResponseException(
                    message="Invalid request to Stripe",
                    gateway_name=self.GATEWAY_NAME,
                    internal_message=response.text[:500],
                )
            
            return PaymentResult.from_response(response.json())
            
        except httpx.TimeoutException as e:
            raise GatewayTimeoutException(
                message="Stripe request timed out",
                gateway_name=self.GATEWAY_NAME,
                timeout_seconds=30,
                internal_message=str(e),
            ) from e
        except httpx.ConnectError as e:
            raise GatewayUnavailableException(
                message="Cannot connect to Stripe",
                gateway_name=self.GATEWAY_NAME,
                internal_message=str(e),
                severity=Severity.CRITICAL,
            ) from e
```

### Anti-Padrões: O Que NÃO Fazer

#### ❌ ERRADO: Exception genérica

```python
# ❌ NUNCA faça isso
def get_user(user_id: str) -> User:
    user = db.get(user_id)
    if not user:
        raise Exception("User not found")  # ❌ Genérico demais!
```

#### ❌ ERRADO: Perder a causa original

```python
# ❌ NUNCA faça isso
try:
    external_api.call()
except RequestException as e:
    raise GatewayException(message="API failed")  # ❌ Perdeu o 'from e'!
```

#### ❌ ERRADO: Expor detalhes técnicos

```python
# ❌ NUNCA faça isso
raise DatabaseConnectionException(
    message=f"Connection to 10.0.0.5:5432 failed: {str(e)}"  # ❌ IP exposto!
)
```

#### ❌ ERRADO: Dados sensíveis nas tags

```python
# ❌ NUNCA faça isso
raise BusinessRuleViolationException(
    message="Payment failed",
    tags={
        "credit_card": "4111-1111-1111-1111",  # ❌ PCI violation!
        "user_password": user.password,         # ❌ LGPD violation!
    }
)
```

#### ❌ ERRADO: Exceção da camada errada

```python
# ❌ NUNCA faça isso no Domain Layer
class User:
    def change_email(self, new_email: str):
        if not new_email:
            # ❌ UseCaseValidationException é da Application Layer!
            raise UseCaseValidationException(message="Email required")
```

### Checklist de Code Review

Use este checklist ao revisar código que envolve exceções:

```markdown
## Checklist de Exceções

### Tipo de Exceção
- [ ] A exceção é da camada correta? (Domain/Application/Infrastructure/Presentation)
- [ ] O código da exceção é descritivo e único?
- [ ] A severidade está apropriada para o tipo de erro?

### Mensagens
- [ ] A mensagem é clara para o usuário final?
- [ ] Não há detalhes técnicos (IPs, queries, stack traces) na mensagem?
- [ ] A mensagem está no catálogo de i18n?

### Encadeamento
- [ ] Usa `raise ... from e` quando há exceção original?
- [ ] A causa original está preservada para debugging?

### Tags e Observabilidade
- [ ] As tags são úteis para debugging?
- [ ] Não há dados sensíveis (senhas, tokens, PII) nas tags?
- [ ] Os campos relevantes estão nas tags para filtros no Datadog/Grafana?

### Tratamento
- [ ] O erro é tratado no nível apropriado?
- [ ] Há fallback ou retry quando faz sentido?
- [ ] Erros de infraestrutura têm tratamento de resiliência?
```

### FAQ - Perguntas Frequentes

**P: Quando devo criar uma nova exceção customizada?**

R: Quase nunca. Use as exceções existentes com `code` e `tags` customizados. Crie nova exceção apenas se precisar de atributos específicos ou comportamento diferente.

```python
# ✅ Prefira isso:
raise BusinessRuleViolationException(
    message="Insufficient balance",
    rule_code="INSUFFICIENT_BALANCE",
    tags={"required": 100, "available": 50}
)

# ❌ Em vez de criar:
class InsufficientBalanceException(DomainException): ...
```

**P: Devo logar a exceção antes de lançar?**

R: Não. O handler global já faz isso. Logar antes cria duplicação.

```python
# ❌ ERRADO - duplica logs
logger.error("User not found", user_id=user_id)
raise DomainNotFoundException(...)

# ✅ CERTO - handler loga automaticamente
raise DomainNotFoundException(
    message="User not found",
    resource_type="User",
    resource_id=user_id
)
```

**P: Como adicionar contexto extra para debugging?**

R: Use as `tags`. Elas aparecem nos logs mas não na resposta ao cliente.

```python
raise GatewayTimeoutException(
    message="Payment provider timeout",
    gateway_name="Stripe",
    tags={
        "attempt": 3,
        "endpoint": "/v1/charges",
        "amount": 1000,
        "currency": "BRL",
    }
)
```

**P: E se eu precisar de uma mensagem de erro customizada para o cliente?**

R: Adicione ao catálogo de i18n e use o `code` correspondente.

```python
# 1. Adicione ao catálogo (i18n_config.py)
register_business_rules({
    "CARD_EXPIRED": {
        Locale.PT_BR: "Cartão expirado. Use outro método de pagamento.",
        Locale.EN_US: "Card expired. Please use another payment method.",
    }
})

# 2. Use o code
raise BusinessRuleViolationException(
    message="Card expired",  # Fallback
    code="CARD_EXPIRED",     # Usado para tradução
    rule_code="CARD_EXPIRED"
)
```

**P: Como testar exceções?**

R: Use pytest.raises com verificação de atributos.

```python
def test_user_not_found_raises_exception():
    repo = UserRepository()
    
    with pytest.raises(DomainNotFoundException) as exc_info:
        repo.get_by_id("nonexistent-id")
    
    exc = exc_info.value
    assert exc.code == "DOMAIN_NOT_FOUND"
    assert exc.resource_type == "User"
    assert exc.resource_id == "nonexistent-id"
    assert exc.http_status == 404
```

---

## Gerenciamento de Regras de Negócio (rule_code)

Esta seção define como gerenciar os códigos de regras de negócio (`rule_code`) usados em `BusinessRuleViolationException`.

### Princípios

1. **Códigos são identificadores únicos** - Usados para i18n, logs e debugging
2. **Metadados fixos no Enum** - Severidade, se é retentável, se o usuário pode corrigir
3. **Configurações variáveis externas** - Limites de tentativas, features habilitadas (vêm do tenant)
4. **Type-safety** - Usar Enum evita typos e permite autocomplete

### Estrutura Recomendada

```
domain/
├── rules/
│   ├── __init__.py              # Exporta BusinessRule
│   └── business_rules.py        # Enum com metadados fixos
│
├── config/
│   ├── __init__.py
│   └── tenant_config.py         # Configurações variáveis por tenant
│
└── ...
```

### Implementação do Enum de Regras

```python
# domain/rules/business_rules.py
from dataclasses import dataclass
from enum import Enum
from core.exceptions import Severity


@dataclass(frozen=True)
class RuleMetadata:
    """
    Metadados FIXOS de uma regra de negócio.
    
    Não inclui valores que variam por tenant (como max_attempts).
    
    Attributes:
        code: Código único para i18n e logs
        default_message: Mensagem fallback (inglês)
        severity: Nível de severidade para alertas
        retryable: Se o usuário pode tentar novamente
        user_actionable: Se o usuário pode corrigir o problema
    """
    code: str
    default_message: str
    severity: Severity = Severity.MEDIUM
    retryable: bool = False
    user_actionable: bool = True


class BusinessRule(Enum):
    """
    Regras de negócio do sistema de onboarding.
    
    Convenção de nomenclatura:
    - Prefixo indica o contexto/domínio
    - Sufixo indica a natureza da violação
    
    Exemplo: LIVENESS_MAX_ATTEMPTS_EXCEEDED
             ^^^^^^^^ ^^^^^^^^^^^^^^^^^^^
             contexto natureza
    
    Nota: Valores que variam por tenant (max_attempts, thresholds)
    devem vir de TenantConfig, não deste Enum.
    """
    
    # =========================================================================
    # CPF / Validação Inicial
    # =========================================================================
    CPF_BLOCKED = RuleMetadata(
        code="CPF_BLOCKED",
        default_message="CPF is blocked in the system",
        severity=Severity.HIGH,
        retryable=False,
        user_actionable=False,
    )
    CPF_INVALID_FORMAT = RuleMetadata(
        code="CPF_INVALID_FORMAT",
        default_message="Invalid CPF format",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    CPF_ALREADY_REGISTERED = RuleMetadata(
        code="CPF_ALREADY_REGISTERED",
        default_message="CPF is already registered",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    
    # =========================================================================
    # Enriquecimento de Dados (BigData / Receita Federal)
    # =========================================================================
    DATA_DIVERGENCE_CRITICAL = RuleMetadata(
        code="DATA_DIVERGENCE_CRITICAL",
        default_message="Critical data divergence detected",
        severity=Severity.HIGH,
        retryable=False,
        user_actionable=False,
    )
    DATA_DIVERGENCE_NAME = RuleMetadata(
        code="DATA_DIVERGENCE_NAME",
        default_message="Name does not match records",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    DATA_DIVERGENCE_BIRTHDATE = RuleMetadata(
        code="DATA_DIVERGENCE_BIRTHDATE",
        default_message="Birthdate does not match records",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    
    # =========================================================================
    # OCR / Documento
    # =========================================================================
    DOCUMENT_TYPE_INVALID = RuleMetadata(
        code="DOCUMENT_TYPE_INVALID",
        default_message="Document type not recognized",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    DOCUMENT_TYPE_NOT_SUPPORTED = RuleMetadata(
        code="DOCUMENT_TYPE_NOT_SUPPORTED",
        default_message="Document type is not supported",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    DOCUMENT_EXPIRED = RuleMetadata(
        code="DOCUMENT_EXPIRED",
        default_message="Document has expired",
        severity=Severity.MEDIUM,
        retryable=True,
        user_actionable=True,
    )
    DOCUMENT_INCOMPLETE = RuleMetadata(
        code="DOCUMENT_INCOMPLETE",
        default_message="Document is incomplete (missing back side)",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    DOCUMENT_UNREADABLE = RuleMetadata(
        code="DOCUMENT_UNREADABLE",
        default_message="Document is not readable",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    OCR_SIMILARITY_NAME_FAILED = RuleMetadata(
        code="OCR_SIMILARITY_NAME_FAILED",
        default_message="Name on document does not match registration",
        severity=Severity.MEDIUM,
        retryable=True,
        user_actionable=True,
    )
    OCR_SIMILARITY_CPF_FAILED = RuleMetadata(
        code="OCR_SIMILARITY_CPF_FAILED",
        default_message="CPF on document does not match registration",
        severity=Severity.MEDIUM,
        retryable=True,
        user_actionable=True,
    )
    OCR_SIMILARITY_BIRTHDATE_FAILED = RuleMetadata(
        code="OCR_SIMILARITY_BIRTHDATE_FAILED",
        default_message="Birthdate on document does not match registration",
        severity=Severity.MEDIUM,
        retryable=True,
        user_actionable=True,
    )
    OCR_MAX_ATTEMPTS_EXCEEDED = RuleMetadata(
        code="OCR_MAX_ATTEMPTS_EXCEEDED",
        default_message="Maximum document upload attempts exceeded",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    
    # =========================================================================
    # Liveness / Selfie
    # =========================================================================
    LIVENESS_FAILED = RuleMetadata(
        code="LIVENESS_FAILED",
        default_message="Liveness check failed",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    LIVENESS_GLASSES_DETECTED = RuleMetadata(
        code="LIVENESS_GLASSES_DETECTED",
        default_message="Please remove glasses and try again",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    LIVENESS_EYES_CLOSED = RuleMetadata(
        code="LIVENESS_EYES_CLOSED",
        default_message="Eyes appear closed, please try again",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    LIVENESS_FACE_OBSTRUCTED = RuleMetadata(
        code="LIVENESS_FACE_OBSTRUCTED",
        default_message="Face is obstructed, please try again",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    LIVENESS_MULTIPLE_FACES = RuleMetadata(
        code="LIVENESS_MULTIPLE_FACES",
        default_message="Multiple faces detected, only one face allowed",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    LIVENESS_NO_FACE_DETECTED = RuleMetadata(
        code="LIVENESS_NO_FACE_DETECTED",
        default_message="No face detected in image",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    LIVENESS_MAX_ATTEMPTS_EXCEEDED = RuleMetadata(
        code="LIVENESS_MAX_ATTEMPTS_EXCEEDED",
        default_message="Maximum liveness attempts exceeded",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    
    # =========================================================================
    # Face Match
    # =========================================================================
    FACEMATCH_FAILED = RuleMetadata(
        code="FACEMATCH_FAILED",
        default_message="Face does not match document photo",
        severity=Severity.MEDIUM,
        retryable=True,
        user_actionable=True,
    )
    FACEMATCH_LOW_CONFIDENCE = RuleMetadata(
        code="FACEMATCH_LOW_CONFIDENCE",
        default_message="Face match confidence is too low",
        severity=Severity.MEDIUM,
        retryable=True,
        user_actionable=True,
    )
    
    # =========================================================================
    # Deepfake Detection
    # =========================================================================
    DEEPFAKE_DETECTED = RuleMetadata(
        code="DEEPFAKE_DETECTED",
        default_message="Suspicious image detected",
        severity=Severity.HIGH,
        retryable=True,
        user_actionable=False,
    )
    DEEPFAKE_BLOCK = RuleMetadata(
        code="DEEPFAKE_BLOCK",
        default_message="Access blocked due to security concerns",
        severity=Severity.CRITICAL,
        retryable=False,
        user_actionable=False,
    )
    DEEPFAKE_HIGH_RISK = RuleMetadata(
        code="DEEPFAKE_HIGH_RISK",
        default_message="High risk image detected",
        severity=Severity.HIGH,
        retryable=True,
        user_actionable=False,
    )
    
    # =========================================================================
    # Quiz
    # =========================================================================
    QUIZ_INCORRECT_ANSWERS = RuleMetadata(
        code="QUIZ_INCORRECT_ANSWERS",
        default_message="Quiz answers are incorrect",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    QUIZ_TIMEOUT = RuleMetadata(
        code="QUIZ_TIMEOUT",
        default_message="Quiz time expired",
        severity=Severity.LOW,
        retryable=True,
        user_actionable=True,
    )
    QUIZ_MAX_ATTEMPTS_EXCEEDED = RuleMetadata(
        code="QUIZ_MAX_ATTEMPTS_EXCEEDED",
        default_message="Maximum quiz attempts exceeded",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    
    # =========================================================================
    # Jornada / Sessão
    # =========================================================================
    JOURNEY_EXPIRED = RuleMetadata(
        code="JOURNEY_EXPIRED",
        default_message="Onboarding session has expired",
        severity=Severity.LOW,
        retryable=False,
        user_actionable=False,
    )
    JOURNEY_ALREADY_COMPLETED = RuleMetadata(
        code="JOURNEY_ALREADY_COMPLETED",
        default_message="Onboarding already completed",
        severity=Severity.LOW,
        retryable=False,
        user_actionable=False,
    )
    JOURNEY_INVALID_STATE = RuleMetadata(
        code="JOURNEY_INVALID_STATE",
        default_message="Invalid journey state for this operation",
        severity=Severity.MEDIUM,
        retryable=False,
        user_actionable=False,
    )
    
    # =========================================================================
    # Properties para acesso aos metadados
    # =========================================================================
    @property
    def code(self) -> str:
        return self.value.code
    
    @property
    def default_message(self) -> str:
        return self.value.default_message
    
    @property
    def severity(self) -> Severity:
        return self.value.severity
    
    @property
    def retryable(self) -> bool:
        return self.value.retryable
    
    @property
    def user_actionable(self) -> bool:
        return self.value.user_actionable
```

### Configurações por Tenant

Valores que variam por tenant (limites de tentativas, features habilitadas) ficam em uma estrutura separada:

```python
# domain/config/tenant_config.py
from dataclasses import dataclass, field


@dataclass
class RetryLimits:
    """
    Limites de tentativas configuráveis por tenant.
    
    Cada tenant pode definir seus próprios limites.
    """
    ocr: int = 3
    liveness: int = 3
    quiz: int = 3
    deepfake: int = 3


@dataclass
class SimilarityThresholds:
    """
    Thresholds de similaridade configuráveis por tenant.
    """
    name: float = 0.85
    cpf: float = 1.0  # Deve ser exato
    birthdate: float = 1.0  # Deve ser exato
    facematch: float = 0.90


@dataclass
class TenantFeatures:
    """Features habilitadas por tenant."""
    quiz_enabled: bool = True
    quiz_mode: str = "MANDATORY"  # DISABLED, MANDATORY, FALLBACK
    deepfake_enabled: bool = True
    manual_review_enabled: bool = True
    liveness_provider: str = "default"  # default, facetec, iproov


@dataclass
class TenantConfig:
    """
    Configurações completas de um tenant.
    
    Carregadas do banco/cache no início de cada request
    e injetadas nos use cases.
    """
    tenant_id: str
    tenant_name: str
    retry_limits: RetryLimits = field(default_factory=RetryLimits)
    similarity_thresholds: SimilarityThresholds = field(default_factory=SimilarityThresholds)
    features: TenantFeatures = field(default_factory=TenantFeatures)
    
    # Configurações de callback
    callback_url: str | None = None
    callback_auth_header: str | None = None
    
    @classmethod
    def default(cls, tenant_id: str) -> "TenantConfig":
        """Cria configuração com valores padrão."""
        return cls(
            tenant_id=tenant_id,
            tenant_name=f"Tenant {tenant_id}",
        )
```

### Repository de Configuração

```python
# infrastructure/repositories/tenant_config_repository.py
from domain.config import TenantConfig, RetryLimits, SimilarityThresholds, TenantFeatures


class TenantConfigRepository:
    """
    Busca configuração do tenant.
    
    Implementa cache para evitar queries repetidas.
    """
    
    def __init__(self, db_session, cache_client):
        self._db = db_session
        self._cache = cache_client
        self._cache_ttl = 300  # 5 minutos
    
    def get_by_tenant_id(self, tenant_id: str) -> TenantConfig:
        """
        Busca configuração do tenant.
        
        Ordem: Cache -> Banco -> Default
        """
        cache_key = f"tenant:{tenant_id}:config"
        
        # Tenta cache
        cached = self._cache.get(cache_key)
        if cached:
            return self._deserialize(cached)
        
        # Busca do banco
        model = (
            self._db.query(TenantConfigModel)
            .filter_by(tenant_id=tenant_id)
            .first()
        )
        
        if not model:
            # Retorna default se tenant não configurado
            return TenantConfig.default(tenant_id)
        
        config = TenantConfig(
            tenant_id=model.tenant_id,
            tenant_name=model.tenant_name,
            retry_limits=RetryLimits(
                ocr=model.ocr_max_attempts,
                liveness=model.liveness_max_attempts,
                quiz=model.quiz_max_attempts,
                deepfake=model.deepfake_max_attempts,
            ),
            similarity_thresholds=SimilarityThresholds(
                name=model.similarity_name_threshold,
                cpf=model.similarity_cpf_threshold,
                birthdate=model.similarity_birthdate_threshold,
                facematch=model.facematch_threshold,
            ),
            features=TenantFeatures(
                quiz_enabled=model.quiz_enabled,
                quiz_mode=model.quiz_mode,
                deepfake_enabled=model.deepfake_enabled,
                manual_review_enabled=model.manual_review_enabled,
            ),
            callback_url=model.callback_url,
        )
        
        # Salva no cache
        self._cache.set(cache_key, self._serialize(config), ttl=self._cache_ttl)
        
        return config
    
    def invalidate_cache(self, tenant_id: str) -> None:
        """Invalida cache quando config é atualizada."""
        self._cache.delete(f"tenant:{tenant_id}:config")
```

### Atualização do BusinessRuleViolationException

```python
# core/exceptions/domain.py (atualizado)
from domain.rules import BusinessRule


@dataclass
class BusinessRuleViolationException(DomainException):
    """
    Violação de regra de negócio.
    
    Pode ser criada de duas formas:
    1. Com BusinessRule enum (recomendado): herda metadados automaticamente
    2. Com rule_code string (fallback): para casos dinâmicos
    
    Example com Enum:
        >>> raise BusinessRuleViolationException(
        ...     rule=BusinessRule.CPF_BLOCKED,
        ...     tags={"cpf_suffix": "***789"}
        ... )
    
    Example com string:
        >>> raise BusinessRuleViolationException(
        ...     message="Custom rule violated",
        ...     rule_code="CUSTOM_RULE"
        ... )
    """
    code: str = "BUSINESS_RULE_VIOLATION"
    rule: BusinessRule | None = None
    rule_code: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        
        if self.rule:
            # Herda metadados do enum
            self.rule_code = self.rule.code
            self.severity = self.rule.severity
            self.tags["rule_code"] = self.rule.code
            self.tags["retryable"] = self.rule.retryable
            self.tags["user_actionable"] = self.rule.user_actionable
            
            # Usa mensagem padrão do enum se não fornecida
            if not self.message or self.message == "Business rule violation":
                self.message = self.rule.default_message
                self.message_params["rule_code"] = self.rule.code
        
        elif self.rule_code:
            self.tags["rule_code"] = self.rule_code
```

### Uso nos Use Cases

```python
# application/use_cases/process_quiz.py
from dataclasses import dataclass
from domain.rules import BusinessRule
from domain.config import TenantConfig
from core.exceptions import BusinessRuleViolationException


@dataclass
class QuizAnswerInput:
    journey_id: str
    answers: list[dict]


class ProcessQuizUseCase:
    """
    Processa respostas do quiz.
    
    O limite de tentativas vem do TenantConfig, não do Enum.
    """
    
    def __init__(
        self,
        journey_repo: JourneyRepository,
        tenant_config_repo: TenantConfigRepository,
        quiz_gateway: QuizGateway,
    ):
        self._journey_repo = journey_repo
        self._tenant_config_repo = tenant_config_repo
        self._quiz_gateway = quiz_gateway
    
    def execute(self, input: QuizAnswerInput) -> QuizResult:
        # Carrega jornada e configuração do tenant
        journey = self._journey_repo.get_by_id(input.journey_id)
        tenant_config = self._tenant_config_repo.get_by_tenant_id(journey.tenant_id)
        
        # Limite vem do tenant, não do enum
        max_attempts = tenant_config.retry_limits.quiz
        
        # Verifica se excedeu tentativas
        if journey.quiz_attempts >= max_attempts:
            raise BusinessRuleViolationException(
                rule=BusinessRule.QUIZ_MAX_ATTEMPTS_EXCEEDED,
                tags={
                    "journey_id": journey.id,
                    "tenant_id": journey.tenant_id,
                    "attempts": journey.quiz_attempts,
                    "max_attempts": max_attempts,
                }
            )
        
        # Verifica se quiz está habilitado para o tenant
        if not tenant_config.features.quiz_enabled:
            # Quiz desabilitado - pula etapa
            return QuizResult(success=True, skipped=True)
        
        # Valida respostas com serviço externo
        try:
            result = self._quiz_gateway.verify(
                journey_id=journey.id,
                answers=input.answers,
            )
        except GatewayTimeoutException:
            # Não conta como tentativa - erro de infra
            raise
        
        if result.status == "TIMEOUT":
            journey.increment_quiz_attempt()
            self._journey_repo.save(journey)
            
            raise BusinessRuleViolationException(
                rule=BusinessRule.QUIZ_TIMEOUT,
                tags={
                    "journey_id": journey.id,
                    "attempt": journey.quiz_attempts,
                    "max_attempts": max_attempts,
                    "remaining": max_attempts - journey.quiz_attempts,
                }
            )
        
        if result.status == "INCORRECT":
            journey.increment_quiz_attempt()
            self._journey_repo.save(journey)
            
            raise BusinessRuleViolationException(
                rule=BusinessRule.QUIZ_INCORRECT_ANSWERS,
                tags={
                    "journey_id": journey.id,
                    "attempt": journey.quiz_attempts,
                    "max_attempts": max_attempts,
                    "remaining": max_attempts - journey.quiz_attempts,
                    "has_bonus_question": result.bonus_question_available,
                }
            )
        
        # Sucesso
        journey.complete_quiz()
        self._journey_repo.save(journey)
        
        return QuizResult(success=True)
```

```python
# application/use_cases/process_liveness.py
class ProcessLivenessUseCase:
    """Processa verificação de liveness."""
    
    def execute(self, input: LivenessInput) -> LivenessResult:
        journey = self._journey_repo.get_by_id(input.journey_id)
        tenant_config = self._tenant_config_repo.get_by_tenant_id(journey.tenant_id)
        
        max_attempts = tenant_config.retry_limits.liveness
        facematch_threshold = tenant_config.similarity_thresholds.facematch
        
        # Verifica tentativas
        if journey.liveness_attempts >= max_attempts:
            raise BusinessRuleViolationException(
                rule=BusinessRule.LIVENESS_MAX_ATTEMPTS_EXCEEDED,
                tags={
                    "journey_id": journey.id,
                    "attempts": journey.liveness_attempts,
                    "max_attempts": max_attempts,
                }
            )
        
        # Liveness check
        try:
            liveness_result = self._liveness_gateway.check(input.selfie)
        except GatewayTimeoutException:
            raise
        
        if not liveness_result.is_live:
            journey.increment_liveness_attempt()
            self._journey_repo.save(journey)
            
            # Mapeia razão para regra específica
            rule = self._map_liveness_failure_to_rule(liveness_result.failure_reason)
            
            raise BusinessRuleViolationException(
                rule=rule,
                tags={
                    "journey_id": journey.id,
                    "reason": liveness_result.failure_reason,
                    "attempt": journey.liveness_attempts,
                    "max_attempts": max_attempts,
                    "remaining": max_attempts - journey.liveness_attempts,
                }
            )
        
        # Face match com threshold do tenant
        match_result = self._rekognition_gateway.compare_faces(
            journey.document_photo,
            input.selfie
        )
        
        if match_result.similarity < facematch_threshold:
            journey.increment_liveness_attempt()
            self._journey_repo.save(journey)
            
            raise BusinessRuleViolationException(
                rule=BusinessRule.FACEMATCH_FAILED,
                tags={
                    "similarity": match_result.similarity,
                    "threshold": facematch_threshold,
                    "attempt": journey.liveness_attempts,
                    "max_attempts": max_attempts,
                }
            )
        
        # Deepfake check (se habilitado)
        if tenant_config.features.deepfake_enabled:
            self._check_deepfake(journey, input.selfie, tenant_config)
        
        return LivenessResult(success=True)
    
    def _map_liveness_failure_to_rule(self, reason: str) -> BusinessRule:
        """Mapeia razão de falha do liveness para regra específica."""
        mapping = {
            "glasses": BusinessRule.LIVENESS_GLASSES_DETECTED,
            "eyes_closed": BusinessRule.LIVENESS_EYES_CLOSED,
            "face_obstructed": BusinessRule.LIVENESS_FACE_OBSTRUCTED,
            "multiple_faces": BusinessRule.LIVENESS_MULTIPLE_FACES,
            "no_face": BusinessRule.LIVENESS_NO_FACE_DETECTED,
        }
        return mapping.get(reason, BusinessRule.LIVENESS_FAILED)
```

### Helper para Validação de Tentativas

Para evitar repetição de código:

```python
# application/helpers/retry_validator.py
from domain.rules import BusinessRule
from core.exceptions import BusinessRuleViolationException


class RetryValidator:
    """Helper para validação de tentativas."""
    
    @staticmethod
    def validate(
        current_attempts: int,
        max_attempts: int,
        exceeded_rule: BusinessRule,
        tags: dict | None = None,
    ) -> dict:
        """
        Valida tentativas e retorna info de remaining.
        
        Args:
            current_attempts: Tentativas atuais
            max_attempts: Limite do tenant
            exceeded_rule: Regra a lançar se excedido
            tags: Tags adicionais para a exceção
        
        Returns:
            Dict com attempt info para uso nas tags
        
        Raises:
            BusinessRuleViolationException: Se tentativas >= max
        """
        if current_attempts >= max_attempts:
            raise BusinessRuleViolationException(
                rule=exceeded_rule,
                tags={
                    **(tags or {}),
                    "attempts": current_attempts,
                    "max_attempts": max_attempts,
                }
            )
        
        return {
            "attempt": current_attempts + 1,  # Próxima tentativa
            "max_attempts": max_attempts,
            "remaining": max_attempts - current_attempts - 1,
        }


# Uso
retry_info = RetryValidator.validate(
    current_attempts=journey.liveness_attempts,
    max_attempts=tenant_config.retry_limits.liveness,
    exceeded_rule=BusinessRule.LIVENESS_MAX_ATTEMPTS_EXCEEDED,
    tags={"journey_id": journey.id}
)

# Se não lançou exceção, podemos usar retry_info
raise BusinessRuleViolationException(
    rule=BusinessRule.LIVENESS_FAILED,
    tags={**retry_info, "reason": "glasses"}
)
```

### Integração com i18n

Adicione as mensagens de regras de negócio ao catálogo:

```python
# core/exceptions/messages.py (adicionar ao BUSINESS_RULE_MESSAGES)

BUSINESS_RULE_MESSAGES: dict[str, dict[Locale, str]] = {
    # === CPF ===
    "CPF_BLOCKED": {
        Locale.PT_BR: "CPF bloqueado no sistema. Entre em contato com o suporte.",
        Locale.EN_US: "CPF is blocked. Please contact support.",
        Locale.ES: "CPF bloqueado en el sistema. Contacte con soporte.",
    },
    "CPF_INVALID_FORMAT": {
        Locale.PT_BR: "Formato de CPF inválido.",
        Locale.EN_US: "Invalid CPF format.",
        Locale.ES: "Formato de CPF inválido.",
    },
    
    # === OCR ===
    "DOCUMENT_TYPE_INVALID": {
        Locale.PT_BR: "Tipo de documento não reconhecido. Use CNH, RG ou RNE.",
        Locale.EN_US: "Document type not recognized. Please use CNH, RG or RNE.",
        Locale.ES: "Tipo de documento no reconocido. Use CNH, RG o RNE.",
    },
    "DOCUMENT_EXPIRED": {
        Locale.PT_BR: "Documento expirado. Envie um documento válido.",
        Locale.EN_US: "Document has expired. Please submit a valid document.",
        Locale.ES: "Documento vencido. Envíe un documento válido.",
    },
    "OCR_MAX_ATTEMPTS_EXCEEDED": {
        Locale.PT_BR: "Número máximo de tentativas de envio de documento excedido.",
        Locale.EN_US: "Maximum document upload attempts exceeded.",
        Locale.ES: "Número máximo de intentos de carga de documento excedido.",
    },
    "OCR_SIMILARITY_NAME_FAILED": {
        Locale.PT_BR: "O nome no documento não corresponde ao cadastro.",
        Locale.EN_US: "Name on document does not match registration.",
        Locale.ES: "El nombre en el documento no coincide con el registro.",
    },
    
    # === Liveness ===
    "LIVENESS_FAILED": {
        Locale.PT_BR: "Não foi possível validar sua selfie. Tente novamente.",
        Locale.EN_US: "Could not validate your selfie. Please try again.",
        Locale.ES: "No se pudo validar tu selfie. Inténtalo de nuevo.",
    },
    "LIVENESS_GLASSES_DETECTED": {
        Locale.PT_BR: "Remova os óculos e tente novamente.",
        Locale.EN_US: "Please remove your glasses and try again.",
        Locale.ES: "Quítese las gafas e inténtelo de nuevo.",
    },
    "LIVENESS_EYES_CLOSED": {
        Locale.PT_BR: "Seus olhos parecem fechados. Tente novamente.",
        Locale.EN_US: "Your eyes appear closed. Please try again.",
        Locale.ES: "Tus ojos parecen cerrados. Inténtalo de nuevo.",
    },
    "LIVENESS_FACE_OBSTRUCTED": {
        Locale.PT_BR: "Seu rosto está obstruído. Remova qualquer obstáculo.",
        Locale.EN_US: "Your face is obstructed. Please remove any obstruction.",
        Locale.ES: "Tu rostro está obstruido. Elimina cualquier obstrucción.",
    },
    "LIVENESS_MAX_ATTEMPTS_EXCEEDED": {
        Locale.PT_BR: "Número máximo de tentativas de selfie excedido.",
        Locale.EN_US: "Maximum selfie attempts exceeded.",
        Locale.ES: "Número máximo de intentos de selfie excedido.",
    },
    "FACEMATCH_FAILED": {
        Locale.PT_BR: "O rosto na selfie não corresponde ao documento.",
        Locale.EN_US: "Face in selfie does not match document photo.",
        Locale.ES: "El rostro en la selfie no coincide con el documento.",
    },
    
    # === Deepfake ===
    "DEEPFAKE_DETECTED": {
        Locale.PT_BR: "Imagem suspeita detectada. Use uma foto real.",
        Locale.EN_US: "Suspicious image detected. Please use a real photo.",
        Locale.ES: "Imagen sospechosa detectada. Use una foto real.",
    },
    "DEEPFAKE_BLOCK": {
        Locale.PT_BR: "Acesso bloqueado por motivos de segurança.",
        Locale.EN_US: "Access blocked for security reasons.",
        Locale.ES: "Acceso bloqueado por motivos de seguridad.",
    },
    
    # === Quiz ===
    "QUIZ_INCORRECT_ANSWERS": {
        Locale.PT_BR: "Respostas incorretas. Tente novamente.",
        Locale.EN_US: "Incorrect answers. Please try again.",
        Locale.ES: "Respuestas incorrectas. Inténtalo de nuevo.",
    },
    "QUIZ_TIMEOUT": {
        Locale.PT_BR: "Tempo esgotado. Tente novamente.",
        Locale.EN_US: "Time expired. Please try again.",
        Locale.ES: "Tiempo agotado. Inténtalo de nuevo.",
    },
    "QUIZ_MAX_ATTEMPTS_EXCEEDED": {
        Locale.PT_BR: "Número máximo de tentativas do quiz excedido.",
        Locale.EN_US: "Maximum quiz attempts exceeded.",
        Locale.ES: "Número máximo de intentos del quiz excedido.",
    },
    
    # === Jornada ===
    "JOURNEY_EXPIRED": {
        Locale.PT_BR: "Sessão expirada. Inicie o processo novamente.",
        Locale.EN_US: "Session expired. Please start the process again.",
        Locale.ES: "Sesión expirada. Inicie el proceso de nuevo.",
    },
    "JOURNEY_ALREADY_COMPLETED": {
        Locale.PT_BR: "Este processo já foi concluído.",
        Locale.EN_US: "This process has already been completed.",
        Locale.ES: "Este proceso ya ha sido completado.",
    },
}
```

### Diagrama de Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GERENCIAMENTO DE REGRAS DE NEGÓCIO                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐         ┌─────────────────────┐                    │
│  │   BusinessRule      │         │   TenantConfig      │                    │
│  │   (Enum)            │         │   (Por Tenant)      │                    │
│  ├─────────────────────┤         ├─────────────────────┤                    │
│  │ • code              │         │ • retry_limits      │                    │
│  │ • default_message   │         │   - ocr: 3          │                    │
│  │ • severity (FIXO)   │         │   - liveness: 5     │                    │
│  │ • retryable (FIXO)  │         │   - quiz: 3         │                    │
│  │ • user_actionable   │         │ • thresholds        │                    │
│  └──────────┬──────────┘         │ • features          │                    │
│             │                    └──────────┬──────────┘                    │
│             │                               │                               │
│             └───────────┬───────────────────┘                               │
│                         │                                                   │
│                         ▼                                                   │
│             ┌─────────────────────┐                                         │
│             │      Use Case       │                                         │
│             ├─────────────────────┤                                         │
│             │ max = tenant_config │                                         │
│             │     .retry_limits   │                                         │
│             │     .quiz           │                                         │
│             │                     │                                         │
│             │ if attempts >= max: │                                         │
│             │   raise Business... │                                         │
│             │     rule=QUIZ_MAX.. │                                         │
│             │     tags={          │                                         │
│             │       max_attempts, │◄──── Valor do tenant                    │
│             │       attempts      │                                         │
│             │     }               │                                         │
│             └─────────────────────┘                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Resumo

| O que | Onde fica | Exemplo |
|-------|-----------|---------|
| Código da regra | `BusinessRule` enum | `QUIZ_MAX_ATTEMPTS_EXCEEDED` |
| Mensagem padrão | `BusinessRule` enum | `"Maximum quiz attempts exceeded"` |
| Severidade | `BusinessRule` enum | `Severity.MEDIUM` |
| Se permite retry | `BusinessRule` enum | `retryable=False` |
| Limite de tentativas | `TenantConfig` | `retry_limits.quiz=3` |
| Threshold de similaridade | `TenantConfig` | `similarity_thresholds.facematch=0.90` |
| Feature habilitada | `TenantConfig` | `features.quiz_enabled=True` |
| Mensagem traduzida | `BUSINESS_RULE_MESSAGES` | `"Número máximo de tentativas..."` |

### Implementação Modular

#### Estrutura de Arquivos

```
api/
├── __init__.py
├── main.py                    # Entry point
├── app_factory.py             # Factory para criar a aplicação
├── config/
│   ├── __init__.py
│   ├── exception_config.py    # Configuração de exceções
│   └── i18n_config.py         # Configuração de i18n
├── exceptions/
│   ├── __init__.py
│   ├── presentation.py
│   └── handlers.py
├── middlewares/
│   ├── __init__.py
│   ├── logging.py
│   └── correlation_id.py
└── routers/
    ├── __init__.py
    ├── documents.py
    └── health.py
```

#### Configuração de i18n

```python
# api/config/i18n_config.py
"""
Configuração de internacionalização.
Registra mensagens específicas do projeto.
"""
from core.exceptions.messages import (
    Locale,
    register_messages,
    register_business_rules,
)


def configure_i18n() -> None:
    """
    Registra todas as mensagens customizadas do projeto.
    
    Deve ser chamado antes de qualquer uso das exceções.
    """
    
    # Mensagens gerais do projeto
    register_messages({
        "DOCUMENT_PROCESSING_ERROR": {
            Locale.PT_BR: "Erro ao processar documento",
            Locale.EN_US: "Error processing document",
            Locale.ES: "Error al procesar documento",
        },
        "OCR_EXTRACTION_FAILED": {
            Locale.PT_BR: "Falha na extração de texto do documento",
            Locale.EN_US: "Failed to extract text from document",
            Locale.ES: "Error al extraer texto del documento",
        },
    })
    
    # Regras de negócio específicas do domínio
    register_business_rules({
        "SELFIE_MISMATCH": {
            Locale.PT_BR: "Selfie não corresponde ao documento",
            Locale.EN_US: "Selfie does not match the document",
            Locale.ES: "Selfie no coincide con el documento",
        },
        "DOCUMENT_EXPIRED": {
            Locale.PT_BR: "Documento expirado",
            Locale.EN_US: "Document expired",
            Locale.ES: "Documento vencido",
        },
        "LIVENESS_CHECK_FAILED": {
            Locale.PT_BR: "Verificação de prova de vida falhou",
            Locale.EN_US: "Liveness check failed",
            Locale.ES: "Verificación de prueba de vida falló",
        },
        "FACE_NOT_DETECTED": {
            Locale.PT_BR: "Rosto não detectado na imagem",
            Locale.EN_US: "Face not detected in image",
            Locale.ES: "Rostro no detectado en la imagen",
        },
    })
```

#### Configuração de Exceções

```python
# api/config/exception_config.py
"""
Configuração dos exception handlers.
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from json import JSONDecodeError

from core.exceptions import CoreException
from api.exceptions.handlers import (
    core_exception_handler,
    request_validation_handler,
    json_decode_handler,
    unhandled_exception_handler,
)


def configure_exception_handlers(app: FastAPI) -> None:
    """
    Registra todos os exception handlers na aplicação.
    
    A ORDEM É IMPORTANTE:
    - Handlers mais específicos primeiro
    - Handler genérico (Exception) por último
    
    Args:
        app: Instância do FastAPI
    """
    
    # 1. Erros de validação do Pydantic (mais específico)
    app.add_exception_handler(
        RequestValidationError,
        request_validation_handler
    )
    
    # 2. Erros de parsing JSON
    app.add_exception_handler(
        JSONDecodeError,
        json_decode_handler
    )
    
    # 3. Todas as exceções da aplicação (CoreException e derivadas)
    #    Isso inclui: Domain, Application, Infrastructure, Presentation
    app.add_exception_handler(
        CoreException,
        core_exception_handler
    )
    
    # 4. Fallback para exceções não tratadas (menos específico)
    app.add_exception_handler(
        Exception,
        unhandled_exception_handler
    )
```

#### Configuração do HTTP Status Mapper (Abordagem Purista)

```python
# api/config/mapper_config.py
"""
Configuração do HTTP Status Mapper.
Usar apenas se optar pela abordagem purista.
"""
from api.mappers.http_mapper import http_status_mapper
from my_project.exceptions import (
    PaymentDeclinedException,
    QuotaExceededException,
    BiometricValidationException,
)


def configure_http_mapper() -> None:
    """
    Registra mapeamentos customizados de exceção -> HTTP status.
    
    Usar apenas se optar por remover http_status das exceções.
    """
    http_status_mapper.register_many({
        PaymentDeclinedException: 402,      # Payment Required
        QuotaExceededException: 429,        # Too Many Requests
        BiometricValidationException: 422,  # Unprocessable Entity
    })
```

#### Middleware de Correlation ID

```python
# api/middlewares/correlation_id.py
"""
Middleware para propagação de Correlation ID.
Permite rastrear requests através de múltiplos serviços.
"""
import uuid
from contextvars import ContextVar
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Context var para acesso global ao correlation ID
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware que extrai ou gera Correlation ID para cada request.
    
    O Correlation ID é usado para:
    - Rastrear requests em logs
    - Correlacionar erros entre serviços
    - Debugging distribuído
    """
    
    HEADER_NAME = "X-Correlation-ID"
    
    async def dispatch(self, request: Request, call_next):
        # Extrai do header ou gera novo
        correlation_id = request.headers.get(
            self.HEADER_NAME,
            str(uuid.uuid4())
        )
        
        # Armazena no context var para acesso global
        correlation_id_ctx.set(correlation_id)
        
        # Processa request
        response = await call_next(request)
        
        # Adiciona ao response
        response.headers[self.HEADER_NAME] = correlation_id
        
        return response


def get_correlation_id() -> str:
    """Retorna o Correlation ID do request atual."""
    return correlation_id_ctx.get()
```

#### Factory da Aplicação

```python
# api/app_factory.py
"""
Factory para criação da aplicação FastAPI.
Centraliza toda a configuração.
"""
from fastapi import FastAPI
from contextlib import asynccontextmanager

from api.config.i18n_config import configure_i18n
from api.config.exception_config import configure_exception_handlers
from api.middlewares.correlation_id import CorrelationIdMiddleware
from api.routers import documents, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.
    
    Startup:
    - Configurar conexões de banco
    - Inicializar caches
    - Healthcheck de dependências
    
    Shutdown:
    - Fechar conexões
    - Flush de logs/métricas
    """
    # Startup
    print("🚀 Iniciando aplicação...")
    yield
    # Shutdown
    print("👋 Encerrando aplicação...")


def create_app() -> FastAPI:
    """
    Factory que cria e configura a aplicação FastAPI.
    
    Ordem de configuração:
    1. i18n (mensagens devem estar disponíveis antes de qualquer erro)
    2. Criar app
    3. Exception handlers
    4. Middlewares
    5. Routers
    
    Returns:
        Aplicação FastAPI configurada
    """
    
    # 1. Configurar i18n ANTES de criar a app
    #    Isso garante que mensagens estejam disponíveis para qualquer erro
    configure_i18n()
    
    # 2. Criar aplicação
    app = FastAPI(
        title="Document Verification API",
        description="API para verificação de documentos e identidade",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # 3. Configurar exception handlers
    #    DEVE vir antes dos middlewares para capturar erros corretamente
    configure_exception_handlers(app)
    
    # 4. Adicionar middlewares
    #    IMPORTANTE: Middlewares funcionam como "cebola" (onion model):
    #    - Na ida (request): primeiro adicionado = primeiro a processar
    #    - Na volta (response): primeiro adicionado = último a processar
    #    
    #    O CorrelationIdMiddleware DEVE ser adicionado PRIMEIRO para que
    #    o correlation_id esteja disponível em todos os logs subsequentes.
    app.add_middleware(CorrelationIdMiddleware)  # PRIMEIRO - mais externo
    # app.add_middleware(LoggingMiddleware)      # SEGUNDO - mais interno
    
    # 5. Registrar routers
    app.include_router(health.router, prefix="/health", tags=["Health"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
    
    return app
```

#### Entry Point

```python
# api/main.py
"""
Entry point da aplicação.
"""
from api.app_factory import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
```

### Integração com Observabilidade

#### Configuração de Logs Estruturados

```python
# api/config/logging_config.py
"""
Configuração de logging estruturado.
Integra com ferramentas de observabilidade (Datadog, ELK, etc).
"""
import structlog
from api.middlewares.correlation_id import get_correlation_id


def add_correlation_id(logger, method_name, event_dict):
    """Processor que adiciona correlation_id a todos os logs."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_service_info(logger, method_name, event_dict):
    """Processor que adiciona informações do serviço."""
    event_dict["service"] = "document-verification-api"
    event_dict["environment"] = "production"  # Usar env var
    return event_dict


def configure_logging() -> None:
    """Configura structlog para logs estruturados."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            add_service_info,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

#### Exemplo de Log de Exceção

Quando uma exceção é capturada, o log estruturado fica assim:

```json
{
  "event": "exception_raised",
  "level": "error",
  "timestamp": "2024-01-15T10:30:00.000000+00:00",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "service": "document-verification-api",
  "environment": "production",
  "error": {
    "code": "GATEWAY_TIMEOUT",
    "message": "Timeout ao processar OCR",
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
  },
  "_internal": {
    "severity": "high",
    "tags": {
      "gateway": "OCR",
      "timeout_seconds": 30
    },
    "internal_message": "Connection to 10.0.0.1:8080 timed out after 30s",
    "cause": "httpx.TimeoutException",
    "cause_type": "TimeoutException"
  },
  "path": "/api/v1/documents/verify",
  "method": "POST",
  "client_ip": "192.168.1.100"
}
```

Este formato permite:
- **Filtragem por severity** no Datadog/Grafana
- **Alertas automáticos** para `severity: critical`
- **Correlação de requests** através de múltiplos serviços
- **Debugging** com informações internas detalhadas

---

## Estrutura de Pastas

```
project/
├── core/
│   └── exceptions/
│       ├── __init__.py              # Exporta exceções do core
│       ├── base.py                  # CoreException, ExceptionDetail, Severity
│       ├── messages.py              # Catálogo i18n, get_message(), Locale
│       ├── domain.py                # DomainException e derivadas
│       ├── application.py           # ApplicationException e derivadas
│       └── infrastructure.py        # InfrastructureException e derivadas
│
├── domain/
│   ├── rules/
│   │   ├── __init__.py              # Exporta BusinessRule
│   │   └── business_rules.py        # Enum com metadados fixos
│   │
│   ├── config/
│   │   ├── __init__.py              # Exporta TenantConfig
│   │   └── tenant_config.py         # Configurações variáveis por tenant
│   │
│   ├── entities/
│   │   ├── journey.py               # Entidade de jornada de onboarding
│   │   └── document.py              # Entidade de documento
│   │
│   ├── value_objects/
│   │   ├── cpf.py                   # Value Object de CPF
│   │   └── email.py                 # Value Object de Email
│   │
│   └── services/
│       └── cpf_block_service.py     # Serviço de bloqueio de CPF
│
├── application/
│   ├── use_cases/
│   │   ├── start_onboarding.py      # Inicia jornada
│   │   ├── process_ocr.py           # Processa documento
│   │   ├── process_liveness.py      # Processa selfie
│   │   ├── process_quiz.py          # Processa quiz
│   │   └── finish_onboarding.py     # Finaliza jornada
│   │
│   └── helpers/
│       └── retry_validator.py       # Helper para validação de tentativas
│
├── infrastructure/
│   ├── gateways/
│   │   ├── ocr_gateway.py           # Gateway para serviço de OCR
│   │   ├── liveness_gateway.py      # Gateway para serviço de liveness
│   │   ├── rekognition_gateway.py   # Gateway para AWS Rekognition
│   │   ├── deepfake_gateway.py      # Gateway para AIOrNot
│   │   └── quiz_gateway.py          # Gateway para serviço de quiz
│   │
│   └── repositories/
│       ├── journey_repository.py    # Repositório de jornadas
│       ├── document_repository.py   # Repositório de documentos
│       └── tenant_config_repository.py  # Repositório de config de tenant
│
├── api/
│   ├── __init__.py
│   ├── main.py                      # Entry point
│   ├── app_factory.py               # Factory da aplicação
│   ├── config/
│   │   ├── __init__.py
│   │   ├── exception_config.py      # Registro de handlers
│   │   ├── i18n_config.py           # Mensagens customizadas
│   │   ├── mapper_config.py         # HTTP Status Mapper (opcional)
│   │   └── logging_config.py        # Configuração de logs
│   ├── exceptions/
│   │   ├── __init__.py
│   │   ├── presentation.py          # PresentationException e derivadas
│   │   └── handlers.py              # Exception handlers
│   ├── utils/
│   │   ├── __init__.py
│   │   └── sanitization.py          # Sanitização de dados para logs
│   ├── mappers/                     # (Opcional - abordagem purista)
│   │   ├── __init__.py
│   │   ├── http_mapper.py
│   │   ├── grpc_mapper.py
│   │   └── graphql_mapper.py
│   ├── middlewares/
│   │   ├── __init__.py
│   │   ├── correlation_id.py        # Propagação de correlation ID
│   │   └── logging.py               # Request/Response logging
│   ├── dependencies/
│   │   ├── auth.py                  # Autenticação e extração de user_id
│   │   ├── tenant.py                # Extração de tenant_id
│   │   ├── content_type.py          # Validação de Content-Type
│   │   ├── rate_limit.py            # Rate limiting
│   │   └── api_version.py           # Validação de versão
│   └── routers/
│       ├── __init__.py
│       ├── onboarding.py            # Rotas de onboarding
│       ├── ocr.py                   # Rotas de OCR
│       ├── liveness.py              # Rotas de liveness
│       ├── quiz.py                  # Rotas de quiz
│       └── health.py                # Health check
│
└── tests/
    ├── conftest.py                  # Fixtures compartilhadas
    ├── unit/
    │   ├── core/
    │   │   └── exceptions/
    │   │       ├── test_base.py
    │   │       ├── test_domain.py
    │   │       ├── test_application.py
    │   │       ├── test_infrastructure.py
    │   │       └── test_messages.py  # Inclui testes de consistência
    │   ├── domain/
    │   │   ├── rules/
    │   │   │   └── test_business_rules.py
    │   │   └── config/
    │   │       └── test_tenant_config.py
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── test_process_ocr.py
    │   │       ├── test_process_liveness.py
    │   │       └── test_process_quiz.py
    │   └── api/
    │       ├── test_exception_handlers.py
    │       ├── test_exception_mapper.py
    │       └── test_sanitization.py
    │
    └── integration/
        └── test_onboarding_flow.py  # Teste do fluxo completo
```

---

## Internacionalização (i18n)

Por padrão, as exceções não estão preparadas para internacionalização - as mensagens estão hardcoded. Esta seção apresenta como adicionar suporte a múltiplos idiomas.

### Abordagens Possíveis

| Abordagem | Descrição | Prós | Contras |
|-----------|-----------|------|---------|
| Códigos apenas | API retorna só códigos, frontend traduz | Simples no backend | Cliente mantém catálogo |
| Catálogo no backend | Backend traduz baseado no locale | Centralizado, consistente | Mais código no backend |
| Híbrido | Backend traduz, cliente pode sobrescrever | Flexível | Mais complexo |

### Implementação Recomendada: Catálogo no Backend

#### 1. Catálogo de Mensagens

```python
# core/exceptions/messages.py
from enum import Enum
from typing import Any


class Locale(str, Enum):
    PT_BR = "pt-BR"
    EN_US = "en-US"
    ES = "es"


MESSAGE_CATALOG: dict[str, dict[Locale, str]] = {
    # =========================================================================
    # Base
    # =========================================================================
    "CORE_ERROR": {
        Locale.PT_BR: "Erro interno",
        Locale.EN_US: "Internal error",
        Locale.ES: "Error interno",
    },
    
    # =========================================================================
    # Domain
    # =========================================================================
    "DOMAIN_ERROR": {
        Locale.PT_BR: "Erro de domínio",
        Locale.EN_US: "Domain error",
        Locale.ES: "Error de dominio",
    },
    "DOMAIN_VALIDATION_ERROR": {
        Locale.PT_BR: "Validação falhou para {object_type}",
        Locale.EN_US: "Validation failed for {object_type}",
        Locale.ES: "Validación fallida para {object_type}",
    },
    "BUSINESS_RULE_VIOLATION": {
        Locale.PT_BR: "Violação de regra de negócio",
        Locale.EN_US: "Business rule violation",
        Locale.ES: "Violación de regla de negocio",
    },
    "DOMAIN_NOT_FOUND": {
        Locale.PT_BR: "{resource_type} não encontrado",
        Locale.EN_US: "{resource_type} not found",
        Locale.ES: "{resource_type} no encontrado",
    },
    "DOMAIN_CONFLICT": {
        Locale.PT_BR: "Conflito de estado",
        Locale.EN_US: "State conflict",
        Locale.ES: "Conflicto de estado",
    },
    
    # =========================================================================
    # Application
    # =========================================================================
    "APPLICATION_ERROR": {
        Locale.PT_BR: "Erro de aplicação",
        Locale.EN_US: "Application error",
        Locale.ES: "Error de aplicación",
    },
    "USE_CASE_VALIDATION_ERROR": {
        Locale.PT_BR: "Entrada inválida",
        Locale.EN_US: "Invalid input",
        Locale.ES: "Entrada inválida",
    },
    "UNAUTHORIZED": {
        Locale.PT_BR: "Não autenticado",
        Locale.EN_US: "Unauthorized",
        Locale.ES: "No autenticado",
    },
    "FORBIDDEN": {
        Locale.PT_BR: "Sem permissão para esta operação",
        Locale.EN_US: "Permission denied",
        Locale.ES: "Permiso denegado",
    },
    "RESOURCE_NOT_FOUND": {
        Locale.PT_BR: "{resource_type} não encontrado",
        Locale.EN_US: "{resource_type} not found",
        Locale.ES: "{resource_type} no encontrado",
    },
    
    # =========================================================================
    # Infrastructure
    # =========================================================================
    "INFRASTRUCTURE_ERROR": {
        Locale.PT_BR: "Erro interno. Tente novamente mais tarde.",
        Locale.EN_US: "Internal error. Please try again later.",
        Locale.ES: "Error interno. Inténtelo de nuevo más tarde.",
    },
    "GATEWAY_ERROR": {
        Locale.PT_BR: "Erro ao acessar serviço externo",
        Locale.EN_US: "External service error",
        Locale.ES: "Error del servicio externo",
    },
    "GATEWAY_TIMEOUT": {
        Locale.PT_BR: "Tempo esgotado ao acessar serviço externo",
        Locale.EN_US: "External service timeout",
        Locale.ES: "Tiempo de espera agotado del servicio externo",
    },
    "GATEWAY_UNAVAILABLE": {
        Locale.PT_BR: "Serviço externo indisponível",
        Locale.EN_US: "External service unavailable",
        Locale.ES: "Servicio externo no disponible",
    },
    "GATEWAY_RATE_LIMIT": {
        Locale.PT_BR: "Limite de requisições do serviço externo excedido",
        Locale.EN_US: "External service rate limit exceeded",
        Locale.ES: "Límite de solicitudes del servicio externo excedido",
    },
    "GATEWAY_BAD_RESPONSE": {
        Locale.PT_BR: "Resposta inválida do serviço externo",
        Locale.EN_US: "Invalid response from external service",
        Locale.ES: "Respuesta inválida del servicio externo",
    },
    "REPOSITORY_ERROR": {
        Locale.PT_BR: "Erro de persistência",
        Locale.EN_US: "Persistence error",
        Locale.ES: "Error de persistencia",
    },
    "DATABASE_CONNECTION_ERROR": {
        Locale.PT_BR: "Erro interno. Tente novamente mais tarde.",
        Locale.EN_US: "Internal error. Please try again later.",
        Locale.ES: "Error interno. Inténtelo de nuevo más tarde.",
    },
    "DATA_INTEGRITY_ERROR": {
        Locale.PT_BR: "Conflito de dados",
        Locale.EN_US: "Data conflict",
        Locale.ES: "Conflicto de datos",
    },
    
    # =========================================================================
    # Presentation
    # =========================================================================
    "PRESENTATION_ERROR": {
        Locale.PT_BR: "Erro na requisição",
        Locale.EN_US: "Request error",
        Locale.ES: "Error en la solicitud",
    },
    "INVALID_REQUEST_FORMAT": {
        Locale.PT_BR: "Formato de requisição inválido",
        Locale.EN_US: "Invalid request format",
        Locale.ES: "Formato de solicitud inválido",
    },
    "UNSUPPORTED_MEDIA_TYPE": {
        Locale.PT_BR: "Tipo de conteúdo não suportado",
        Locale.EN_US: "Unsupported media type",
        Locale.ES: "Tipo de contenido no soportado",
    },
    "NOT_ACCEPTABLE": {
        Locale.PT_BR: "Formato de resposta não suportado",
        Locale.EN_US: "Not acceptable response format",
        Locale.ES: "Formato de respuesta no aceptable",
    },
    "MISSING_HEADER": {
        Locale.PT_BR: "Header obrigatório ausente: {header_name}",
        Locale.EN_US: "Missing required header: {header_name}",
        Locale.ES: "Encabezado requerido faltante: {header_name}",
    },
    "INVALID_HEADER": {
        Locale.PT_BR: "Header inválido: {header_name}",
        Locale.EN_US: "Invalid header: {header_name}",
        Locale.ES: "Encabezado inválido: {header_name}",
    },
    "API_VERSION_NOT_SUPPORTED": {
        Locale.PT_BR: "Versão da API não suportada: {requested_version}",
        Locale.EN_US: "API version not supported: {requested_version}",
        Locale.ES: "Versión de API no soportada: {requested_version}",
    },
    "API_RATE_LIMIT": {
        Locale.PT_BR: "Limite de requisições excedido. Tente novamente em {retry_after_seconds} segundos.",
        Locale.EN_US: "Rate limit exceeded. Try again in {retry_after_seconds} seconds.",
        Locale.ES: "Límite de solicitudes excedido. Intente de nuevo en {retry_after_seconds} segundos.",
    },
    "REQUEST_ENTITY_TOO_LARGE": {
        Locale.PT_BR: "Requisição muito grande. Tamanho máximo: {max_size_bytes} bytes",
        Locale.EN_US: "Request too large. Maximum size: {max_size_bytes} bytes",
        Locale.ES: "Solicitud demasiado grande. Tamaño máximo: {max_size_bytes} bytes",
    },
    
    # =========================================================================
    # Detail Codes
    # =========================================================================
    "FIELD_INVALID": {
        Locale.PT_BR: "Campo inválido",
        Locale.EN_US: "Invalid field",
        Locale.ES: "Campo inválido",
    },
    "REQUIRED_FIELD": {
        Locale.PT_BR: "Campo obrigatório",
        Locale.EN_US: "Required field",
        Locale.ES: "Campo obligatorio",
    },
    "INVALID_INPUT": {
        Locale.PT_BR: "Entrada inválida",
        Locale.EN_US: "Invalid input",
        Locale.ES: "Entrada inválida",
    },
    "REQUIRED_HEADER": {
        Locale.PT_BR: "Header obrigatório",
        Locale.EN_US: "Required header",
        Locale.ES: "Encabezado obligatorio",
    },
    "VALIDATION_ERROR": {
        Locale.PT_BR: "Erro de validação",
        Locale.EN_US: "Validation error",
        Locale.ES: "Error de validación",
    },
}


# Mensagens específicas de regras de negócio (separadas para organização)
BUSINESS_RULE_MESSAGES: dict[str, dict[Locale, str]] = {
    "DOCUMENT_ALREADY_VERIFIED": {
        Locale.PT_BR: "Documento já foi verificado anteriormente",
        Locale.EN_US: "Document has already been verified",
        Locale.ES: "El documento ya ha sido verificado",
    },
    "CPF_BLOCKED": {
        Locale.PT_BR: "CPF bloqueado no sistema",
        Locale.EN_US: "CPF is blocked in the system",
        Locale.ES: "CPF bloqueado en el sistema",
    },
    "INSUFFICIENT_BALANCE": {
        Locale.PT_BR: "Saldo insuficiente",
        Locale.EN_US: "Insufficient balance",
        Locale.ES: "Saldo insuficiente",
    },
    "DAILY_LIMIT_EXCEEDED": {
        Locale.PT_BR: "Limite diário excedido",
        Locale.EN_US: "Daily limit exceeded",
        Locale.ES: "Límite diario excedido",
    },
    "DEVICE_NOT_BOUND": {
        Locale.PT_BR: "Dispositivo não vinculado",
        Locale.EN_US: "Device not bound",
        Locale.ES: "Dispositivo no vinculado",
    },
    "ACCOUNT_INACTIVE": {
        Locale.PT_BR: "Conta inativa",
        Locale.EN_US: "Inactive account",
        Locale.ES: "Cuenta inactiva",
    },
}


DEFAULT_LOCALE = Locale.PT_BR


def get_message(
    code: str,
    locale: Locale = DEFAULT_LOCALE,
    **kwargs
) -> str | None:
    """
    Obtém mensagem traduzida para um código de erro.
    
    Usa interpolação segura - placeholders faltantes não quebram a execução,
    apenas logam um warning e retornam a mensagem com placeholders visíveis.
    
    Args:
        code: Código do erro
        locale: Idioma desejado
        **kwargs: Variáveis para interpolação na mensagem
    
    Returns:
        Mensagem traduzida e interpolada, ou None se não encontrada
    
    Example:
        >>> get_message("DOMAIN_NOT_FOUND", Locale.PT_BR, resource_type="Documento")
        "Documento não encontrado"
    """
    import structlog
    logger = structlog.get_logger()
    
    # Busca no catálogo principal
    messages = MESSAGE_CATALOG.get(code)
    
    # Se não encontrou, busca em regras de negócio
    if not messages:
        messages = BUSINESS_RULE_MESSAGES.get(code)
    
    if not messages:
        return None
    
    # Tenta o locale solicitado, depois o padrão, depois qualquer um
    message = (
        messages.get(locale) or 
        messages.get(DEFAULT_LOCALE) or 
        next(iter(messages.values()), None)
    )
    
    if not message:
        return None
    
    # Interpolação segura - não quebra se faltar parâmetro
    try:
        return message.format(**kwargs)
    except KeyError as e:
        logger.warning(
            "i18n_interpolation_failed",
            code=code,
            locale=locale.value,
            missing_key=str(e),
            available_keys=list(kwargs.keys()),
            message_template=message,
        )
        # Retorna mensagem com placeholders visíveis para debug
        return message


def register_messages(messages: dict[str, dict[Locale, str]]) -> None:
    """
    Registra novas mensagens no catálogo.
    
    Útil para adicionar mensagens específicas do projeto.
    
    Args:
        messages: Dicionário de código -> {locale -> mensagem}
    
    Example:
        >>> register_messages({
        ...     "CUSTOM_ERROR": {
        ...         Locale.PT_BR: "Erro customizado",
        ...         Locale.EN_US: "Custom error",
        ...     }
        ... })
    """
    MESSAGE_CATALOG.update(messages)


def register_business_rules(messages: dict[str, dict[Locale, str]]) -> None:
    """
    Registra novas mensagens de regras de negócio.
    
    Args:
        messages: Dicionário de rule_code -> {locale -> mensagem}
    """
    BUSINESS_RULE_MESSAGES.update(messages)
```

#### 2. ExceptionDetail com i18n

```python
# core/exceptions/base.py (atualizado)
from dataclasses import dataclass, field
from typing import Any

from .messages import Locale, get_message, DEFAULT_LOCALE


@dataclass
class ExceptionDetail:
    """
    Detalhe estruturado do erro com suporte a i18n.
    
    Attributes:
        code: Código do erro (usado para tradução)
        message: Mensagem original (fallback se tradução não existir)
        field: Nome do campo relacionado (opcional)
        metadata: Dados adicionais para contexto (opcional)
    """
    code: str
    message: str
    field: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_message(self, locale: Locale = DEFAULT_LOCALE) -> str:
        """Obtém mensagem traduzida."""
        translated = get_message(self.code, locale, **self.metadata)
        return translated if translated else self.message
    
    def to_dict(self, locale: Locale = DEFAULT_LOCALE) -> dict[str, Any]:
        """Serializa com mensagem traduzida."""
        result = {
            "code": self.code,
            "message": self.get_message(locale),
        }
        
        if self.field:
            result["field"] = self.field
        
        return result
```

#### 3. CoreException com i18n

```python
# core/exceptions/base.py (atualizado)
@dataclass
class CoreException(Exception):
    """
    Base de todas as exceções da aplicação com suporte a i18n.
    
    Attributes:
        message: Mensagem original (fallback)
        code: Código do erro (usado para tradução)
        message_params: Parâmetros para interpolação na mensagem traduzida
    """
    message: str
    code: str = "CORE_ERROR"
    details: list[ExceptionDetail] = field(default_factory=list)
    exception_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: Severity = Severity.MEDIUM
    tags: dict[str, Any] = field(default_factory=dict)
    
    # Parâmetros para interpolação da mensagem traduzida
    message_params: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        super().__init__(self.message)
    
    def get_message(self, locale: Locale = DEFAULT_LOCALE) -> str:
        """
        Obtém mensagem traduzida.
        
        Args:
            locale: Idioma desejado
        
        Returns:
            Mensagem traduzida ou mensagem original como fallback
        """
        translated = get_message(self.code, locale, **self.message_params)
        return translated if translated else self.message
    
    def to_dict(
        self, 
        include_internal: bool = False,
        locale: Locale = DEFAULT_LOCALE
    ) -> dict[str, Any]:
        """
        Serializa a exceção com mensagens traduzidas.
        
        Args:
            include_internal: Se True, inclui dados sensíveis (apenas para logs)
            locale: Idioma para as mensagens
        
        Returns:
            Dicionário com estrutura padronizada do erro
        """
        result = {
            "type": "error",
            "error": {
                "code": self.code,
                "message": self.get_message(locale),
                "request_id": self.exception_id,
                "details": [
                    d.to_dict(locale) for d in self.details
                ] if self.details else None,
            }
        }
        
        if include_internal:
            result["_internal"] = {
                "severity": self.severity.value,
                "tags": self.tags,
                "timestamp": self.timestamp.isoformat(),
                "cause": str(self.__cause__) if self.__cause__ else None,
                "cause_type": type(self.__cause__).__name__ if self.__cause__ else None,
                "original_message": self.message,
                "locale": locale.value,
            }
        
        return result
    
    @property
    def http_status(self) -> int:
        return 500
```

#### 4. Exceções com message_params automático

```python
# core/exceptions/domain.py (atualizado)
@dataclass
class DomainValidationException(DomainException):
    code: str = "DOMAIN_VALIDATION_ERROR"
    object_type: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        if self.object_type:
            self.tags["object_type"] = self.object_type
            # Adiciona automaticamente aos params de interpolação
            self.message_params["object_type"] = self.object_type


@dataclass
class DomainNotFoundException(DomainException):
    code: str = "DOMAIN_NOT_FOUND"
    resource_type: str = ""
    resource_id: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.tags["resource_type"] = self.resource_type
        self.tags["resource_id"] = self.resource_id
        # Adiciona automaticamente aos params de interpolação
        self.message_params["resource_type"] = self.resource_type
        self.message_params["resource_id"] = self.resource_id
```

#### 5. Handler com Detecção de Locale

```python
# api/exception_handlers.py (atualizado)
from fastapi import Request
from fastapi.responses import JSONResponse
from core.exceptions import CoreException, Severity
from core.exceptions.messages import Locale, DEFAULT_LOCALE


def get_locale_from_request(request: Request) -> Locale:
    """
    Extrai locale do request.
    
    Ordem de prioridade:
    1. Query param: ?lang=pt-BR
    2. Header: Accept-Language
    3. Header customizado: X-Locale
    4. Default (PT_BR)
    
    Args:
        request: Request do FastAPI
    
    Returns:
        Locale detectado
    """
    # 1. Query param
    lang = request.query_params.get("lang")
    if lang:
        try:
            return Locale(lang)
        except ValueError:
            pass
    
    # 2. Header customizado (mais preciso)
    x_locale = request.headers.get("X-Locale")
    if x_locale:
        try:
            return Locale(x_locale)
        except ValueError:
            pass
    
    # 3. Accept-Language header
    accept_language = request.headers.get("Accept-Language", "")
    
    # Parse simples do Accept-Language
    # Formato: pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7
    for part in accept_language.split(","):
        lang_tag = part.split(";")[0].strip()
        
        # Tenta match exato
        try:
            return Locale(lang_tag)
        except ValueError:
            pass
        
        # Tenta match parcial (pt -> pt-BR)
        for locale in Locale:
            if locale.value.lower().startswith(lang_tag.lower()):
                return locale
    
    return DEFAULT_LOCALE


async def core_exception_handler(request: Request, exc: CoreException) -> JSONResponse:
    """
    Handler global com suporte a i18n.
    """
    # Detecta locale do request
    locale = get_locale_from_request(request)
    
    # Log sempre no locale padrão para consistência nos logs
    log_data = exc.to_dict(include_internal=True, locale=DEFAULT_LOCALE)
    log_data["path"] = request.url.path
    log_data["method"] = request.method
    log_data["client_ip"] = request.client.host if request.client else None
    log_data["requested_locale"] = locale.value
    
    if exc.severity in (Severity.HIGH, Severity.CRITICAL):
        logger.error("exception_raised", **log_data)
    else:
        logger.warning("exception_raised", **log_data)
    
    # Response no locale do cliente
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(include_internal=False, locale=locale),
        headers={
            "X-Request-ID": exc.exception_id,
            "Content-Language": locale.value,
        }
    )
```

### Exemplo de Uso

```python
# Lançando exceção - mensagem é fallback
raise DomainNotFoundException(
    message="Document not found",  # Fallback
    resource_type="Document",
    resource_id="doc-123",
)

# Request com Accept-Language: pt-BR
# Response:
{
    "type": "error",
    "error": {
        "code": "DOMAIN_NOT_FOUND",
        "message": "Document não encontrado",
        "request_id": "550e8400-e29b-41d4-a716-446655440000",
        "details": null
    }
}

# Request com Accept-Language: en-US
# Response:
{
    "type": "error",
    "error": {
        "code": "DOMAIN_NOT_FOUND",
        "message": "Document not found",
        "request_id": "550e8400-e29b-41d4-a716-446655440000",
        "details": null
    }
}
```

### Registrando Mensagens do Projeto

```python
# main.py ou config
from core.exceptions.messages import register_messages, register_business_rules, Locale

# Mensagens específicas do projeto
register_messages({
    "CUSTOM_VALIDATION_ERROR": {
        Locale.PT_BR: "Erro de validação customizado",
        Locale.EN_US: "Custom validation error",
        Locale.ES: "Error de validación personalizado",
    },
})

# Regras de negócio específicas
register_business_rules({
    "SELFIE_MISMATCH": {
        Locale.PT_BR: "Selfie não corresponde ao documento",
        Locale.EN_US: "Selfie does not match the document",
        Locale.ES: "Selfie no coincide con el documento",
    },
    "DOCUMENT_EXPIRED": {
        Locale.PT_BR: "Documento expirado",
        Locale.EN_US: "Document expired",
        Locale.ES: "Documento vencido",
    },
})
```

### Estrutura de Pastas com i18n

```
project/
├── core/
│   └── exceptions/
│       ├── __init__.py
│       ├── base.py              # CoreException com i18n
│       ├── messages.py          # Catálogo de mensagens
│       ├── domain.py
│       ├── application.py
│       └── infrastructure.py
│
└── api/
    ├── exceptions/
    │   └── presentation.py
    └── exception_handlers.py    # Handler com detecção de locale
```

---

## Considerações de Performance

### UUID e Timestamp em Alta Escala

Por padrão, cada instância de `CoreException` gera um `uuid4()` e `datetime.now(timezone.utc)`. Em sistemas de altíssima performance (dezenas de milhares de exceções por segundo), isso pode aparecer no profiler.

> **Nota sobre timezone**: Usamos `datetime.now(timezone.utc)` em vez de `datetime.utcnow()`. O Python 3.12+ desencoraja `utcnow()` pois retorna um datetime "naive" (sem timezone), o que pode causar ambiguidades em cálculos de data. Usar `timezone.utc` explicita o fuso horário.

> **Na prática**: `uuid4()` e `datetime.now()` são extremamente rápidos (microsegundos). Só se torna problema em volumes muito altos, o que geralmente indica um problema maior na aplicação (ex: validação deveria ocorrer antes).

### Lazy Evaluation (Opcional)

Se o profiler indicar problema real, use lazy evaluation:

```python
# core/exceptions/base.py (versão otimizada)
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
import uuid


@dataclass
class CoreException(Exception):
    message: str
    code: str = "CORE_ERROR"
    details: list[ExceptionDetail] = field(default_factory=list)
    severity: Severity = Severity.MEDIUM
    tags: dict[str, Any] = field(default_factory=dict)
    message_params: dict[str, Any] = field(default_factory=dict)
    
    # Lazy - só gerados quando acessados
    _exception_id: str | None = field(default=None, repr=False)
    _timestamp: datetime | None = field(default=None, repr=False)
    
    def __post_init__(self):
        super().__init__(self.message)
    
    @property
    def exception_id(self) -> str:
        """Gera UUID apenas quando acessado pela primeira vez."""
        if self._exception_id is None:
            self._exception_id = str(uuid.uuid4())
        return self._exception_id
    
    @property
    def timestamp(self) -> datetime:
        """Gera timestamp apenas quando acessado pela primeira vez."""
        if self._timestamp is None:
            self._timestamp = datetime.now(timezone.utc)
        return self._timestamp
    
    def to_dict(
        self, 
        include_internal: bool = False,
        locale: Locale = DEFAULT_LOCALE
    ) -> dict[str, Any]:
        # Acessa as properties apenas aqui, quando realmente necessário
        result = {
            "type": "error",
            "error": {
                "code": self.code,
                "message": self.get_message(locale),
                "request_id": self.exception_id,  # Gera UUID aqui
                "details": [
                    d.to_dict(locale) for d in self.details
                ] if self.details else None,
            }
        }
        
        if include_internal:
            result["_internal"] = {
                "severity": self.severity.value,
                "tags": self.tags,
                "timestamp": self.timestamp.isoformat(),  # Gera timestamp aqui
                # ...
            }
        
        return result
```

### Quando Usar Lazy Evaluation

| Cenário | Recomendação |
|---------|--------------|
| Aplicação típica (< 1000 req/s) | Manter simples (eager) |
| Alta escala com muitas validações | Considerar lazy |
| Exceções raramente serializadas | Lazy pode ajudar |
| Profiler indicou gargalo | Implementar lazy |

**Recomendação**: Comece com a versão simples. Otimize apenas se houver evidência de problema real.

---

## Testes

### Estrutura de Testes

```
tests/
├── unit/
│   ├── core/
│   │   └── exceptions/
│   │       ├── test_base.py
│   │       ├── test_domain.py
│   │       ├── test_application.py
│   │       ├── test_infrastructure.py
│   │       └── test_messages.py
│   └── api/
│       ├── test_exception_handlers.py
│       └── test_exception_mapper.py
└── conftest.py
```

### Fixtures Compartilhadas

```python
# tests/conftest.py
import pytest
from datetime import datetime, timezone
from unittest.mock import patch


@pytest.fixture
def fixed_uuid():
    """UUID fixo para testes determinísticos."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def fixed_timestamp():
    """Timestamp fixo para testes determinísticos (timezone-aware)."""
    return datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def mock_uuid_and_time(fixed_uuid, fixed_timestamp):
    """Mock de UUID e timestamp para testes."""
    with patch("uuid.uuid4", return_value=type("UUID", (), {"__str__": lambda s: fixed_uuid})()), \
         patch("core.exceptions.base.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_timestamp
        mock_dt.timezone = timezone
        yield
```

### Testes da Base (CoreException)

```python
# tests/unit/core/exceptions/test_base.py
import pytest
from core.exceptions import CoreException, ExceptionDetail, Severity
from core.exceptions.messages import Locale


class TestExceptionDetail:
    def test_to_dict_minimal(self):
        detail = ExceptionDetail(code="FIELD_INVALID", message="Invalid value")
        
        result = detail.to_dict()
        
        assert result == {
            "code": "FIELD_INVALID",
            "message": "Campo inválido",  # Traduzido
        }
    
    def test_to_dict_with_field(self):
        detail = ExceptionDetail(
            code="FIELD_INVALID",
            message="Invalid value",
            field="email"
        )
        
        result = detail.to_dict()
        
        assert result["field"] == "email"
    
    def test_to_dict_respects_locale(self):
        detail = ExceptionDetail(code="REQUIRED_FIELD", message="Required")
        
        result_pt = detail.to_dict(Locale.PT_BR)
        result_en = detail.to_dict(Locale.EN_US)
        
        assert result_pt["message"] == "Campo obrigatório"
        assert result_en["message"] == "Required field"
    
    def test_fallback_to_original_message_when_code_not_found(self):
        detail = ExceptionDetail(
            code="UNKNOWN_CODE",
            message="Original message"
        )
        
        result = detail.to_dict()
        
        assert result["message"] == "Original message"


class TestCoreException:
    def test_creates_with_required_fields(self):
        exc = CoreException(message="Test error")
        
        assert exc.message == "Test error"
        assert exc.code == "CORE_ERROR"
        assert exc.severity == Severity.MEDIUM
    
    def test_exception_id_is_generated(self):
        exc = CoreException(message="Test error")
        
        assert exc.exception_id is not None
        assert len(exc.exception_id) == 36  # UUID format
    
    def test_timestamp_is_generated(self):
        exc = CoreException(message="Test error")
        
        assert exc.timestamp is not None
    
    def test_is_python_exception(self):
        exc = CoreException(message="Test error")
        
        assert isinstance(exc, Exception)
        assert str(exc) == "Test error"
    
    def test_to_dict_without_internal(self):
        exc = CoreException(
            message="Test error",
            code="TEST_CODE",
        )
        
        result = exc.to_dict(include_internal=False)
        
        assert result["type"] == "error"
        assert result["error"]["code"] == "TEST_CODE"
        assert result["error"]["request_id"] == exc.exception_id
        assert "_internal" not in result
    
    def test_to_dict_with_internal(self):
        exc = CoreException(
            message="Test error",
            severity=Severity.HIGH,
            tags={"user_id": "123"},
        )
        
        result = exc.to_dict(include_internal=True)
        
        assert "_internal" in result
        assert result["_internal"]["severity"] == "high"
        assert result["_internal"]["tags"]["user_id"] == "123"
    
    def test_to_dict_includes_details(self):
        exc = CoreException(
            message="Validation failed",
            details=[
                ExceptionDetail(code="FIELD_INVALID", message="Invalid", field="email"),
                ExceptionDetail(code="REQUIRED_FIELD", message="Required", field="name"),
            ]
        )
        
        result = exc.to_dict()
        
        assert len(result["error"]["details"]) == 2
        assert result["error"]["details"][0]["field"] == "email"
    
    def test_to_dict_with_locale(self):
        exc = CoreException(
            message="Fallback message",
            code="UNAUTHORIZED",
        )
        
        result_pt = exc.to_dict(locale=Locale.PT_BR)
        result_en = exc.to_dict(locale=Locale.EN_US)
        
        assert result_pt["error"]["message"] == "Não autenticado"
        assert result_en["error"]["message"] == "Unauthorized"
    
    def test_cause_is_captured(self):
        original = ValueError("Original error")
        
        try:
            raise CoreException(message="Wrapped") from original
        except CoreException as exc:
            result = exc.to_dict(include_internal=True)
            
            assert result["_internal"]["cause"] == "Original error"
            assert result["_internal"]["cause_type"] == "ValueError"
    
    def test_http_status_default(self):
        exc = CoreException(message="Test")
        
        assert exc.http_status == 500


class TestSeverity:
    def test_severity_values(self):
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"
```

### Testes de Domínio

```python
# tests/unit/core/exceptions/test_domain.py
import pytest
from core.exceptions import (
    DomainException,
    DomainValidationException,
    BusinessRuleViolationException,
    DomainNotFoundException,
    DomainConflictException,
)
from core.exceptions.messages import Locale


class TestDomainValidationException:
    def test_http_status(self):
        exc = DomainValidationException(message="Invalid")
        
        assert exc.http_status == 422
    
    def test_from_violations_factory(self):
        exc = DomainValidationException.from_violations(
            object_type="User",
            violations={
                "email": "Invalid email format",
                "age": "Must be over 18",
            }
        )
        
        assert exc.object_type == "User"
        assert len(exc.details) == 2
        assert exc.tags["object_type"] == "User"
    
    def test_from_violations_sets_message_params(self):
        exc = DomainValidationException.from_violations(
            object_type="Document",
            violations={"type": "Invalid"}
        )
        
        result = exc.to_dict(locale=Locale.PT_BR)
        
        assert "Document" in result["error"]["message"]
    
    def test_details_have_field_names(self):
        exc = DomainValidationException.from_violations(
            object_type="User",
            violations={"email": "Invalid"}
        )
        
        assert exc.details[0].field == "email"


class TestBusinessRuleViolationException:
    def test_http_status(self):
        exc = BusinessRuleViolationException(message="Rule violated")
        
        assert exc.http_status == 422
    
    def test_rule_code_in_tags(self):
        exc = BusinessRuleViolationException(
            message="Document already verified",
            rule_code="DOCUMENT_ALREADY_VERIFIED"
        )
        
        assert exc.tags["rule_code"] == "DOCUMENT_ALREADY_VERIFIED"
    
    def test_translated_message_for_known_rule(self):
        exc = BusinessRuleViolationException(
            message="Fallback",
            code="BUSINESS_RULE_VIOLATION",
            rule_code="DOCUMENT_ALREADY_VERIFIED"
        )
        
        # Note: rule_code translation requires custom handling
        result = exc.to_dict(locale=Locale.PT_BR)
        
        assert result["error"]["code"] == "BUSINESS_RULE_VIOLATION"


class TestDomainNotFoundException:
    def test_http_status(self):
        exc = DomainNotFoundException(message="Not found")
        
        assert exc.http_status == 404
    
    def test_resource_info_in_tags(self):
        exc = DomainNotFoundException(
            message="Document not found",
            resource_type="Document",
            resource_id="doc-123"
        )
        
        assert exc.tags["resource_type"] == "Document"
        assert exc.tags["resource_id"] == "doc-123"
    
    def test_message_interpolation(self):
        exc = DomainNotFoundException(
            message="Not found",
            resource_type="Documento",
            resource_id="123"
        )
        
        result = exc.to_dict(locale=Locale.PT_BR)
        
        assert "Documento" in result["error"]["message"]


class TestDomainConflictException:
    def test_http_status(self):
        exc = DomainConflictException(message="Conflict")
        
        assert exc.http_status == 409
```

### Testes de i18n

```python
# tests/unit/core/exceptions/test_messages.py
import pytest
from unittest.mock import patch
from core.exceptions.messages import (
    Locale,
    get_message,
    register_messages,
    register_business_rules,
    MESSAGE_CATALOG,
    BUSINESS_RULE_MESSAGES,
)


class TestGetMessage:
    def test_returns_translated_message(self):
        result = get_message("UNAUTHORIZED", Locale.PT_BR)
        
        assert result == "Não autenticado"
    
    def test_returns_different_locale(self):
        result_pt = get_message("UNAUTHORIZED", Locale.PT_BR)
        result_en = get_message("UNAUTHORIZED", Locale.EN_US)
        
        assert result_pt != result_en
    
    def test_returns_none_for_unknown_code(self):
        result = get_message("UNKNOWN_CODE_12345", Locale.PT_BR)
        
        assert result is None
    
    def test_interpolates_parameters(self):
        result = get_message(
            "DOMAIN_NOT_FOUND",
            Locale.PT_BR,
            resource_type="Documento"
        )
        
        assert result == "Documento não encontrado"
    
    def test_falls_back_to_default_locale(self):
        # Simula um locale que não existe para o código
        # Deve retornar o default (PT_BR)
        result = get_message("UNAUTHORIZED", Locale.ES)
        
        assert result is not None
    
    def test_handles_missing_interpolation_key_gracefully(self):
        """Deve logar warning mas não quebrar."""
        with patch("core.exceptions.messages.structlog.get_logger") as mock_logger:
            mock_log = mock_logger.return_value
            
            result = get_message(
                "DOMAIN_NOT_FOUND",
                Locale.PT_BR,
                # Falta resource_type
            )
            
            # Retorna mensagem com placeholder visível
            assert "{resource_type}" in result
            mock_log.warning.assert_called_once()
    
    def test_searches_business_rules_catalog(self):
        result = get_message("DOCUMENT_ALREADY_VERIFIED", Locale.PT_BR)
        
        assert result == "Documento já foi verificado anteriormente"


class TestRegisterMessages:
    def test_adds_new_messages(self):
        register_messages({
            "CUSTOM_TEST_CODE": {
                Locale.PT_BR: "Mensagem customizada",
                Locale.EN_US: "Custom message",
            }
        })
        
        result = get_message("CUSTOM_TEST_CODE", Locale.PT_BR)
        
        assert result == "Mensagem customizada"
        
        # Cleanup
        del MESSAGE_CATALOG["CUSTOM_TEST_CODE"]


class TestRegisterBusinessRules:
    def test_adds_new_business_rules(self):
        register_business_rules({
            "CUSTOM_RULE_TEST": {
                Locale.PT_BR: "Regra customizada",
                Locale.EN_US: "Custom rule",
            }
        })
        
        result = get_message("CUSTOM_RULE_TEST", Locale.PT_BR)
        
        assert result == "Regra customizada"
        
        # Cleanup
        del BUSINESS_RULE_MESSAGES["CUSTOM_RULE_TEST"]


class TestCatalogConsistency:
    """
    Testes de consistência do catálogo de mensagens.
    
    Garantem que todas as traduções existam para todos os locales,
    evitando que mensagens faltantes cheguem à produção.
    """
    
    def test_all_message_codes_have_all_locales(self):
        """Verifica se todos os códigos têm tradução para todos os locales."""
        missing = []
        
        for code, translations in MESSAGE_CATALOG.items():
            for locale in Locale:
                if locale not in translations:
                    missing.append(f"{code} -> {locale.value}")
        
        assert not missing, (
            f"Traduções faltando no MESSAGE_CATALOG:\n" + 
            "\n".join(f"  - {m}" for m in missing)
        )
    
    def test_all_business_rules_have_all_locales(self):
        """Verifica se todas as regras de negócio têm tradução para todos os locales."""
        missing = []
        
        for code, translations in BUSINESS_RULE_MESSAGES.items():
            for locale in Locale:
                if locale not in translations:
                    missing.append(f"{code} -> {locale.value}")
        
        assert not missing, (
            f"Traduções faltando no BUSINESS_RULE_MESSAGES:\n" + 
            "\n".join(f"  - {m}" for m in missing)
        )
    
    def test_no_empty_translations(self):
        """Verifica se não há traduções vazias."""
        empty = []
        
        for catalog_name, catalog in [
            ("MESSAGE_CATALOG", MESSAGE_CATALOG),
            ("BUSINESS_RULE_MESSAGES", BUSINESS_RULE_MESSAGES),
        ]:
            for code, translations in catalog.items():
                for locale, message in translations.items():
                    if not message or not message.strip():
                        empty.append(f"{catalog_name}.{code}.{locale.value}")
        
        assert not empty, (
            f"Traduções vazias encontradas:\n" + 
            "\n".join(f"  - {e}" for e in empty)
        )
    
    def test_interpolation_placeholders_are_consistent(self):
        """
        Verifica se os placeholders de interpolação são consistentes
        entre os diferentes locales de um mesmo código.
        """
        import re
        placeholder_pattern = re.compile(r'\{(\w+)\}')
        inconsistent = []
        
        for catalog_name, catalog in [
            ("MESSAGE_CATALOG", MESSAGE_CATALOG),
            ("BUSINESS_RULE_MESSAGES", BUSINESS_RULE_MESSAGES),
        ]:
            for code, translations in catalog.items():
                placeholders_by_locale = {}
                
                for locale, message in translations.items():
                    placeholders = set(placeholder_pattern.findall(message))
                    placeholders_by_locale[locale] = placeholders
                
                # Compara todos os locales com o primeiro
                locales = list(placeholders_by_locale.keys())
                if len(locales) > 1:
                    reference = placeholders_by_locale[locales[0]]
                    for locale in locales[1:]:
                        if placeholders_by_locale[locale] != reference:
                            inconsistent.append(
                                f"{catalog_name}.{code}: "
                                f"{locales[0].value}={reference} vs "
                                f"{locale.value}={placeholders_by_locale[locale]}"
                            )
        
        assert not inconsistent, (
            f"Placeholders inconsistentes entre locales:\n" + 
            "\n".join(f"  - {i}" for i in inconsistent)
        )
```

### Testes do Handler

```python
# tests/unit/api/test_exception_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.testclient import TestClient
from fastapi import FastAPI

from core.exceptions import (
    CoreException,
    DomainValidationException,
    BusinessRuleViolationException,
    GatewayTimeoutException,
    Severity,
)
from core.exceptions.messages import Locale
from api.exception_handlers import (
    core_exception_handler,
    get_locale_from_request,
)


class TestGetLocaleFromRequest:
    def test_extracts_from_query_param(self):
        request = MagicMock(spec=Request)
        request.query_params = {"lang": "en-US"}
        request.headers = {}
        
        result = get_locale_from_request(request)
        
        assert result == Locale.EN_US
    
    def test_extracts_from_x_locale_header(self):
        request = MagicMock(spec=Request)
        request.query_params = {}
        request.headers = {"X-Locale": "es"}
        
        result = get_locale_from_request(request)
        
        assert result == Locale.ES
    
    def test_extracts_from_accept_language(self):
        request = MagicMock(spec=Request)
        request.query_params = {}
        request.headers = {"Accept-Language": "en-US,en;q=0.9,pt;q=0.8"}
        
        result = get_locale_from_request(request)
        
        assert result == Locale.EN_US
    
    def test_returns_default_when_no_locale_info(self):
        request = MagicMock(spec=Request)
        request.query_params = {}
        request.headers = {}
        
        result = get_locale_from_request(request)
        
        assert result == Locale.PT_BR
    
    def test_query_param_takes_precedence(self):
        request = MagicMock(spec=Request)
        request.query_params = {"lang": "en-US"}
        request.headers = {"Accept-Language": "pt-BR"}
        
        result = get_locale_from_request(request)
        
        assert result == Locale.EN_US


class TestCoreExceptionHandler:
    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/documents"
        request.method = "POST"
        request.query_params = {}
        request.headers = {}
        request.client.host = "127.0.0.1"
        return request
    
    @pytest.mark.asyncio
    async def test_returns_correct_status_code(self, mock_request):
        exc = DomainValidationException(message="Invalid")
        
        with patch("api.exception_handlers.logger"):
            response = await core_exception_handler(mock_request, exc)
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_returns_exception_id_in_header(self, mock_request):
        exc = CoreException(message="Test")
        
        with patch("api.exception_handlers.logger"):
            response = await core_exception_handler(mock_request, exc)
        
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] == exc.exception_id
    
    @pytest.mark.asyncio
    async def test_respects_locale_from_request(self, mock_request):
        mock_request.headers = {"Accept-Language": "en-US"}
        exc = CoreException(message="Fallback", code="UNAUTHORIZED")
        
        with patch("api.exception_handlers.logger"):
            response = await core_exception_handler(mock_request, exc)
        
        import json
        body = json.loads(response.body)
        
        assert body["error"]["message"] == "Unauthorized"
        assert response.headers["Content-Language"] == "en-US"
    
    @pytest.mark.asyncio
    async def test_logs_with_appropriate_level(self, mock_request):
        exc_medium = CoreException(message="Test", severity=Severity.MEDIUM)
        exc_critical = CoreException(message="Test", severity=Severity.CRITICAL)
        
        with patch("api.exception_handlers.logger") as mock_logger:
            await core_exception_handler(mock_request, exc_medium)
            mock_logger.warning.assert_called()
            
            mock_logger.reset_mock()
            
            await core_exception_handler(mock_request, exc_critical)
            mock_logger.error.assert_called()
    
    @pytest.mark.asyncio
    async def test_does_not_expose_internal_details(self, mock_request):
        exc = GatewayTimeoutException(
            message="Timeout",
            gateway_name="OCR",
            internal_message="Connection to 10.0.0.1:8080 timed out"
        )
        
        with patch("api.exception_handlers.logger"):
            response = await core_exception_handler(mock_request, exc)
        
        import json
        body = json.loads(response.body)
        
        assert "10.0.0.1" not in str(body)
        assert "_internal" not in body


class TestIntegration:
    """Testes de integração com FastAPI."""
    
    @pytest.fixture
    def app(self):
        from api.exception_handlers import core_exception_handler
        
        app = FastAPI()
        app.add_exception_handler(CoreException, core_exception_handler)
        
        @app.get("/test-validation")
        async def test_validation():
            raise DomainValidationException.from_violations(
                object_type="User",
                violations={"email": "Invalid email"}
            )
        
        @app.get("/test-business-rule")
        async def test_business_rule():
            raise BusinessRuleViolationException(
                message="Document already verified",
                rule_code="DOCUMENT_ALREADY_VERIFIED"
            )
        
        return app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app, raise_server_exceptions=False)
    
    def test_validation_error_response(self, client):
        response = client.get("/test-validation")
        
        assert response.status_code == 422
        body = response.json()
        assert body["type"] == "error"
        assert body["error"]["code"] == "DOMAIN_VALIDATION_ERROR"
        assert len(body["error"]["details"]) == 1
    
    def test_business_rule_error_response(self, client):
        response = client.get("/test-business-rule")
        
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "BUSINESS_RULE_VIOLATION"
    
    def test_request_id_header_present(self, client):
        response = client.get("/test-validation")
        
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36  # UUID
    
    def test_locale_affects_message(self, client):
        response_pt = client.get(
            "/test-validation",
            headers={"Accept-Language": "pt-BR"}
        )
        response_en = client.get(
            "/test-validation",
            headers={"Accept-Language": "en-US"}
        )
        
        body_pt = response_pt.json()
        body_en = response_en.json()
        
        assert body_pt["error"]["message"] != body_en["error"]["message"]
```

### Testes do HTTP Status Mapper

```python
# tests/unit/api/test_exception_mapper.py
import pytest
from core.exceptions import (
    CoreException,
    DomainException,
    DomainValidationException,
    BusinessRuleViolationException,
    DomainNotFoundException,
    ApplicationException,
    UseCaseValidationException,
    UnauthorizedOperationException,
    InfrastructureException,
    GatewayTimeoutException,
    DatabaseConnectionException,
)
from api.exception_mapper import HTTPStatusMapper, http_status_mapper


class TestHTTPStatusMapper:
    def test_maps_domain_validation_to_422(self):
        exc = DomainValidationException(message="Invalid")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 422
    
    def test_maps_not_found_to_404(self):
        exc = DomainNotFoundException(message="Not found")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 404
    
    def test_maps_unauthorized_to_401(self):
        exc = UnauthorizedOperationException(message="Unauthorized")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 401
    
    def test_maps_gateway_timeout_to_504(self):
        exc = GatewayTimeoutException(message="Timeout", gateway_name="OCR")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 504
    
    def test_maps_db_connection_to_503(self):
        exc = DatabaseConnectionException(message="Connection failed")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 503
    
    def test_falls_back_to_parent_class_mapping(self):
        """Exceção customizada deve usar mapeamento da classe pai."""
        
        @dataclass
        class CustomDomainException(DomainException):
            pass
        
        exc = CustomDomainException(message="Custom")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 422  # DomainException default
    
    def test_returns_500_for_unknown_exception(self):
        exc = CoreException(message="Unknown")
        
        status = http_status_mapper.get_status(exc)
        
        assert status == 500
    
    def test_register_custom_mapping(self):
        mapper = HTTPStatusMapper()
        
        @dataclass
        class PaymentDeclinedException(ApplicationException):
            pass
        
        mapper.register(PaymentDeclinedException, 402)
        
        exc = PaymentDeclinedException(message="Payment declined")
        status = mapper.get_status(exc)
        
        assert status == 402
    
    def test_register_many(self):
        mapper = HTTPStatusMapper()
        
        @dataclass
        class ExceptionA(CoreException):
            pass
        
        @dataclass
        class ExceptionB(CoreException):
            pass
        
        mapper.register_many({
            ExceptionA: 418,
            ExceptionB: 451,
        })
        
        assert mapper.get_status(ExceptionA(message="A")) == 418
        assert mapper.get_status(ExceptionB(message="B")) == 451
```

### Executando os Testes

```bash
# Todos os testes
pytest tests/ -v

# Com cobertura
pytest tests/ --cov=core --cov=api --cov-report=html

# Apenas testes de exceção
pytest tests/unit/core/exceptions/ -v

# Apenas testes de i18n
pytest tests/unit/core/exceptions/test_messages.py -v

# Testes de integração
pytest tests/unit/api/test_exception_handlers.py::TestIntegration -v
```

---

## Referências

- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Domain-Driven Design - Eric Evans](https://www.domainlanguage.com/ddd/)
- [Anthropic API Error Handling](https://docs.anthropic.com/en/api/errors)
- [Python Exception Chaining (PEP 3134)](https://peps.python.org/pep-3134/)
