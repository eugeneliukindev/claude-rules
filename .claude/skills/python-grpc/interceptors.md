# The Status Interceptor

The one place a gRPC service maps its errors to status codes, referenced from `SKILL.md`. The
module below ran under grpcio 1.84 and passes `mypy --strict` with `types-grpcio`.

- [The module](#the-module)
- [What it covers, and what it does not](#what-it-covers-and-what-it-does-not)

## The Module

The servicer raises domain errors and never calls `context.abort` itself; this interceptor, passed
to `grpc.aio.server(interceptors=[StatusInterceptor()])`, wraps every unary and server-streaming
handler.

```python
"""Domain errors mapped to gRPC status codes, in one interceptor for every method."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Final, Never, cast, final, override

import grpc

from shop.errors import InvalidRequestError, OrderAlreadyShippedError, OrderNotFoundError

_CODE_BY_ERROR: Final[Mapping[type[Exception], grpc.StatusCode]] = MappingProxyType(
    {
        InvalidRequestError: grpc.StatusCode.INVALID_ARGUMENT,
        OrderNotFoundError: grpc.StatusCode.NOT_FOUND,
        OrderAlreadyShippedError: grpc.StatusCode.FAILED_PRECONDITION,
    }
)
_INTERNAL_DETAILS: Final = "internal error"

type _Context = grpc.aio.ServicerContext[object, object]
type _UnaryBehavior = Callable[[object, _Context], Awaitable[object]]
type _StreamBehavior = Callable[[object, _Context], AsyncIterator[object]]

logger = logging.getLogger(__name__)


@final
class StatusInterceptor(grpc.aio.ServerInterceptor):
    @override
    async def intercept_service[RequestT, ResponseT](
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler[RequestT, ResponseT] | None]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler[RequestT, ResponseT] | None:
        handler = await continuation(handler_call_details)
        if handler is None:
            return None
        if handler.unary_unary is not None:
            return grpc.unary_unary_rpc_method_handler(
                _mapped_unary(cast("_UnaryBehavior", handler.unary_unary)),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.unary_stream is not None:
            return grpc.unary_stream_rpc_method_handler(
                _mapped_stream(cast("_StreamBehavior", handler.unary_stream)),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler


def _mapped_unary(behavior: _UnaryBehavior) -> _UnaryBehavior:
    async def call(request: object, context: _Context) -> object:
        try:
            return await behavior(request, context)
        except grpc.aio.AbortError:
            raise
        except Exception as error:  # noqa: BLE001 — the transport boundary
            await _abort_with_status(context, error)

    return call


def _mapped_stream(behavior: _StreamBehavior) -> _StreamBehavior:
    async def call(request: object, context: _Context) -> AsyncIterator[object]:
        try:
            async for response in behavior(request, context):
                yield response
        except grpc.aio.AbortError:
            raise
        except Exception as error:  # noqa: BLE001 — the transport boundary
            await _abort_with_status(context, error)

    return call


async def _abort_with_status(context: _Context, error: Exception) -> Never:
    for error_type in type(error).__mro__:
        code = _CODE_BY_ERROR.get(error_type)
        if code is not None:
            await context.abort(code, str(error))
    logger.error("rpc failed", exc_info=error)
    await context.abort(grpc.StatusCode.INTERNAL, _INTERNAL_DETAILS)
```

## What It Covers, and What It Does Not

- **`from __future__ import annotations` is load-bearing below Python 3.14.** `types-grpcio` makes
  `RpcMethodHandler` generic and the runtime class is not, so the signature of `intercept_service`
  raises `TypeError` at import without it.
- **The `cast`s are there because the stubs type a handler's behaviour as synchronous**; under
  `grpc.aio` it is a coroutine function, or an async generator function for a streaming response.
- **`AbortError` is re-raised before the `except Exception`.** Without it the client still gets
  the code the handler aborted with, but every deliberate abort is logged at `ERROR` as a failed
  RPC, with its traceback — measured.
- **Client-streaming and bidirectional methods pass through unwrapped** — this service has none. A
  service that does wraps `stream_unary` and `stream_stream` the same way, through
  `stream_unary_rpc_method_handler` and `stream_stream_rpc_method_handler`; unwrapped, their
  unclassified errors reach the client as `UNKNOWN` with the message.
- **A stream is closed at `yield` when the client leaves**, which throws `GeneratorExit` — a
  `BaseException`, so the `except Exception` above lets it through untouched.
