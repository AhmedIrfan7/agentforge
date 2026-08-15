"""Application error types and FastAPI exception handlers.

Every error response uses the same envelope — {"error": {"code", "message"}}
— and unexpected exceptions are logged with full detail server-side but
never leak internals (stack traces, DB errors, provider details) to the
client. See AGENTS.md SECTION 9 "Error Handling."
"""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from logging_config import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class TooManyRequestsError(AppError):
    status_code = 429
    code = "too_many_requests"


class UnsupportedFileTypeError(AppError):
    # Same code as the automatic pydantic/RequestValidationError path
    # below ("validation_error") -- a rejected file type is the same
    # category of problem to a client as a malformed request body, not
    # a distinct error class it needs to special-case.
    status_code = 422
    code = "validation_error"


class FileTooLargeError(AppError):
    # 413, not 422 -- "too large" is a distinct, standard HTTP status
    # (Payload Too Large) from "malformed"/"wrong type", and worth a
    # client being able to tell apart (e.g. to show "compress your file"
    # rather than "pick a different file").
    status_code = 413
    code = "file_too_large"


class InfectedFileError(AppError):
    # 422, like UnsupportedFileTypeError -- still "the file you sent is
    # unprocessable" -- but its own code, not "validation_error": a virus
    # hit is a different problem for a client to surface than "wrong
    # type", the same reasoning that gave FileTooLargeError its own code
    # instead of folding into validation_error.
    status_code = 422
    code = "infected_file"


class InvalidChunkingStrategyError(AppError):
    # Same code as UnsupportedFileTypeError -- an unrecognized strategy
    # name is the same broad category of problem ("the value you sent
    # isn't valid") as a rejected file type, not a distinct one worth
    # its own client-facing code.
    status_code = 422
    code = "validation_error"


def _error_response(
    status_code: int, code: str, message: str, details: object = None
) -> JSONResponse:
    body: dict[str, object] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details  # type: ignore[index]
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # exc.errors() embeds the raw exception object in each error's
        # ctx["error"] for any field_validator that raises ValueError
        # (roadmap step 160 -- agents/configuration.py:AgentConfiguration
        # is this codebase's first field_validator) -- plain json.dumps
        # can't serialize that and turns a real 422 into an unhandled
        # 500. jsonable_encoder recursively converts anything it doesn't
        # recognize (including a bare exception) via str(), the same
        # fallback FastAPI's own default validation-error handler
        # already relies on.
        return _error_response(
            422, "validation_error", "Invalid request.", jsonable_encoder(exc.errors())
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", path=str(request.url.path))
        return _error_response(500, "internal_error", "An unexpected error occurred.")
