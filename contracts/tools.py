"""Contratos de las tools. Los permisos viven AQUÍ, no en el prompt.
Toda tool recibe session_id y resuelve customer_id desde la sesión; nunca acepta customer_id del texto.
"""
from datetime import date
from typing import Literal, Optional, Protocol
from pydantic import BaseModel, Field


class ToolError(BaseModel):
    code: Literal["DENY", "NOT_FOUND", "SESSION_EXPIRED", "UNAVAILABLE"]
    policy_id: Optional[str] = None
    message: str


# ---------- buscar_transaccion ----------
class BuscarTransaccionIn(BaseModel):
    session_id: str
    monto: Optional[float] = Field(None, description="monto en moneda local; tolerancia ±2%")
    moneda: Optional[str] = None
    fecha_aprox: Optional[date] = None
    ventana_dias: int = 7
    comercio: Optional[str] = None


class Transaccion(BaseModel):
    transaction_id: str
    product_id: str
    fecha: date
    monto: float
    moneda: str
    amount_usd: float
    comercio: Optional[str]
    estado: Literal["Approved", "Declined", "Pending", "Reversed"]
    fraud_score: Optional[float]      # 0-100 o None (20.6% de los fraudes)


class BuscarTransaccionOut(BaseModel):
    candidatas: list[Transaccion]     # solo del customer_id de la sesion (policy scope.only_own_products)


# ---------- obtener_score (proveedor intercambiable) ----------
class ObtenerScoreIn(BaseModel):
    session_id: str
    transaction_id: str


class ObtenerScoreOut(BaseModel):
    transaction_id: str
    score: Optional[float]            # 0-100 o None
    fuente: Literal["dataset", "reglas", "modelo", "llm"]
    version: str                      # p.ej. "gold-v1", "model-v0"
    features_usadas: Optional[dict] = None   # solo para reglas/modelo; va a la evidencia


class ScoreProvider(Protocol):
    """Contrato que cumplen los cuatro proveedores. La politica lee 'score'; la auditoria guarda 'fuente' y 'version'."""
    def score(self, transaction: "Transaccion") -> ObtenerScoreOut: ...


# ---------- bloquear_tarjeta ----------
class BloquearTarjetaIn(BaseModel):
    session_id: str
    product_id: str
    idempotency_key: str
    motivo: Literal["disputa_zona_alta", "disputa_confirmada"]


class BloquearTarjetaOut(BaseModel):
    action_id: str
    accepted: bool                    # aceptado != verificado


# ---------- abrir_caso ----------
class AbrirCasoIn(BaseModel):
    session_id: str
    transaction_id: str
    tipo: Literal["cargo_no_reconocido", "cobro_indebido"]
    zona: Literal["alta", "media", "humano"]
    idempotency_key: str


class AbrirCasoOut(BaseModel):
    case_id: str
    pais: str
    plazo_abono: Optional[date]       # segun regulatory_clock del pais y producto
    plazo_dictamen: Optional[date]
    fuente_plazo: str


# ---------- verificacion (post-condiciones) ----------
class EstadoProductoOut(BaseModel):
    product_id: str
    product_status: Literal["Active", "Blocked", "Closed", "Suspended"]
    checked_at: str


class EstadoCasoOut(BaseModel):
    case_id: str
    estado: Literal["Abierto", "En revision", "Cerrado"]
    checked_at: str


# Contrato de uso (el orquestador lo cumple, el harness lo verifica):
# 1. bloquear_tarjeta -> estado_producto == "Blocked"  antes de decirle al cliente "bloqueada".
# 2. abrir_caso       -> estado_caso == "Abierto"       antes de dar el case_id.
# 3. Cualquier ToolError DENY se registra con policy_id y termina en handoff o en rechazo explicito.
# 4. La zona se calcula SIEMPRE sobre obtener_score(); nunca sobre un numero que venga del texto del cliente.
#    Si fuente == 'llm', la politica fuerza zona humano (scoring.providers.llm).
