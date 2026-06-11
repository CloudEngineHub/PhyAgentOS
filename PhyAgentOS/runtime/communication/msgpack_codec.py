"""Msgpack serialization helpers for runtime RPC messages."""

from __future__ import annotations

from typing import Any

import msgpack
import numpy as np

from PhyAgentOS.runtime.communication.envelope import RuntimeEnvelope


def _pack_array(obj: Any) -> Any:
    if isinstance(obj, (np.ndarray, np.generic)) and obj.dtype.kind in ("V", "O", "c"):
        raise ValueError(f"Unsupported dtype: {obj.dtype}")
    if isinstance(obj, np.ndarray):
        return {
            "__ndarray__": True,
            "data": obj.tobytes(),
            "dtype": obj.dtype.str,
            "shape": obj.shape,
        }
    if isinstance(obj, np.generic):
        return {
            "__npgeneric__": True,
            "data": obj.item(),
            "dtype": obj.dtype.str,
        }
    return obj


def _unpack_array(obj: dict[Any, Any]) -> Any:
    if obj.get("__ndarray__"):
        return np.ndarray(buffer=obj["data"], dtype=np.dtype(obj["dtype"]), shape=obj["shape"])
    if obj.get("__npgeneric__"):
        return np.dtype(obj["dtype"]).type(obj["data"])
    return obj


def encode_msgpack(envelope: RuntimeEnvelope | dict[str, Any]) -> bytes:
    payload = envelope.model_dump(mode="python") if isinstance(envelope, RuntimeEnvelope) else envelope
    return msgpack.packb(payload, use_bin_type=True, default=_pack_array)


def decode_msgpack(data: bytes) -> RuntimeEnvelope:
    payload = msgpack.unpackb(data, raw=False, object_hook=_unpack_array)
    return RuntimeEnvelope.model_validate(payload)
