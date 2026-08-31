from dataclasses import dataclass, field
from typing import Any

from get_orbit import (
    AmbiguousTargetError,
    JapaneseAliasNotRegisteredError,
    JplApiError,
    TargetNotFoundError,
    TargetResolutionError,
)
from orbit_service import (
    OrbitServiceError,
    TargetNotRegisteredError,
    UnsupportedTargetTypeError,
)
from stellarium_service import StellariumApiError, StellariumError


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


class ApplicationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.info = ErrorInfo(
            code=code,
            message=message,
            details=details or {},
        )
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.info.code

    @property
    def message(self) -> str:
        return self.info.message

    @property
    def details(self) -> dict[str, Any]:
        return self.info.details

    def to_dict(self) -> dict[str, Any]:
        return self.info.to_dict()


def error_info_from_exception(error: BaseException) -> ErrorInfo:
    if isinstance(error, ApplicationError):
        return error.info

    if isinstance(error, AmbiguousTargetError):
        return ErrorInfo(
            code="ambiguous_target",
            message=str(error),
            details={
                "identifier": error.identifier,
                "candidates": list(error.candidates),
            },
        )

    if isinstance(error, JapaneseAliasNotRegisteredError):
        return ErrorInfo(
            code="japanese_alias_not_registered",
            message=str(error),
            details={"identifier": error.identifier},
        )

    if isinstance(error, TargetNotFoundError):
        return ErrorInfo(
            code="target_not_found",
            message=str(error),
            details={"identifier": error.identifier},
        )

    if isinstance(error, UnsupportedTargetTypeError):
        return ErrorInfo(
            code="unsupported_target_type",
            message=str(error),
        )

    if isinstance(error, TargetNotRegisteredError):
        return ErrorInfo(
            code="target_not_registered",
            message=str(error),
        )

    if isinstance(error, TargetResolutionError):
        return ErrorInfo(
            code="target_resolution_failed",
            message=str(error),
        )

    if isinstance(error, JplApiError):
        return ErrorInfo(
            code="jpl_api_error",
            message=str(error),
        )

    if isinstance(error, StellariumApiError):
        return ErrorInfo(
            code="stellarium_api_error",
            message=str(error),
        )

    if isinstance(error, StellariumError):
        return ErrorInfo(
            code="stellarium_error",
            message=str(error),
        )

    if isinstance(error, OrbitServiceError):
        return ErrorInfo(
            code="orbit_service_error",
            message=str(error),
        )

    if isinstance(error, ValueError):
        return ErrorInfo(
            code="invalid_input",
            message=str(error),
        )

    return ErrorInfo(
        code="internal_error",
        message="予期しないエラーが発生しました。",
        details={
            "exception_type": type(error).__name__,
            "technical_message": str(error),
        },
    )


def application_error_from_exception(error: BaseException) -> ApplicationError:
    info = error_info_from_exception(error)
    return ApplicationError(
        code=info.code,
        message=info.message,
        details=info.details,
    )
