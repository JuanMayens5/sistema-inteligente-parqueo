"""
Textos para el usuario
======================

Las funciones de datos devuelven CÓDIGOS (por ejemplo "SIN_ESPACIO"), no
frases. Aquí se traduce cada código a un texto en español (con una pista del
siguiente paso cuando ayuda) y se le asigna un NIVEL, que define el color con
que se muestra:

    ok -> verde     aviso -> ámbar     error -> rojo     info -> azul

Si llega un código que no está en MENSAJES, se muestra el mensaje que
devolvió la propia base. Así, un código nuevo que agregue el encargado de la
base se ve bien aunque este archivo todavía no lo conozca.

Uso:
    mensajes.describir(resultado, placa="P123ABC", tipo="COMPACTO", espacio="C-01")
    mensajes.nivel(resultado.codigo)
"""

# Los {placa}, {tipo} y {espacio} se rellenan con los datos que pase quien llama.
MENSAJES = {
    # --- Códigos que devuelven los procedimientos de la base ---
    "TIPO_INVALIDO": "El tipo de vehículo '{tipo}' no existe en el catálogo.",
    "YA_REGISTRADO": "La placa {placa} ya estaba registrada. El botón principal te ofrece su siguiente paso.",
    "VEHICULO_NO_ENCONTRADO": "No existe un vehículo registrado con la placa {placa}.",
    "YA_TIENE_ESPACIO": "El vehículo {placa} ya tiene un espacio asignado.",
    "SIN_ESPACIO": "No hay espacios disponibles para vehículos tipo {tipo}.",
    "SIN_ASIGNACION": "El vehículo {placa} no tiene una asignación pendiente de llegada.",
    "SALIDA_NO_AUTORIZADA": "La salida de {placa} no estaba autorizada: se activó una alarma en {espacio}.",
    "ALARMA_ACTIVADA": "¡ALARMA! Movimiento no autorizado en {espacio} (vehículo {placa}).",
    "ALARMA_YA_ACTIVA": "Ya hay una alarma activa en {espacio}.",
    "MOVIMIENTO_AUTORIZADO": "Movimiento registrado en {espacio} sin generar alarma.",
    "SIN_ALARMA": "No hay una alarma activa para el vehículo {placa}.",
    "ESPACIO_NO_ENCONTRADO": "No existe el espacio {espacio}.",
    "ESPACIO_YA_LIBRE": "El espacio {espacio} no tiene una ocupación activa.",
    # SIN_OCUPACION no está aquí a propósito: significa cosas distintas según el
    # procedimiento, así que se muestra el mensaje que devuelve la base.

    # --- Códigos propios de la aplicación ---
    "PLACA_VACIA": "Debes ingresar la placa del vehículo.",
    "PLACA_LARGA": "La placa no puede tener más de 20 caracteres.",
    "ERROR_CONEXION": "Se perdió la conexión con la base de datos.",
    "CANCELACION_NO_DISPONIBLE": "La base de datos todavía no permite liberar espacios manualmente.",
}

NIVELES = {
    "OK": "ok",
    "TIPO_INVALIDO": "error",
    "YA_REGISTRADO": "aviso",
    "VEHICULO_NO_ENCONTRADO": "error",
    "YA_TIENE_ESPACIO": "aviso",
    "SIN_ESPACIO": "error",
    "SIN_ASIGNACION": "aviso",
    "SIN_OCUPACION": "aviso",
    "SALIDA_NO_AUTORIZADA": "error",
    "ALARMA_ACTIVADA": "error",
    "ALARMA_YA_ACTIVA": "aviso",
    "MOVIMIENTO_AUTORIZADO": "info",
    "SIN_ALARMA": "aviso",
    "ESPACIO_NO_ENCONTRADO": "error",
    "ESPACIO_YA_LIBRE": "aviso",
    "PLACA_VACIA": "aviso",
    "PLACA_LARGA": "aviso",
    "ERROR_CONEXION": "error",
    "CANCELACION_NO_DISPONIBLE": "aviso",
    # Resultados del simulador de sensores (logica/eventos_hardware.py)
    "SIN_CAMBIOS": "info",
    "OCUPACION_NO_ESPERADA": "aviso",
}

# Códigos que significan "la instrucción se procesó bien", aunque no sean "OK":
# el sensor de movimiento funcionó correctamente aunque haya disparado una alarma.
# La consola los usa para clasificar la instrucción en la bitácora.
CODIGOS_PROCESADOS = {"OK", "ALARMA_ACTIVADA", "ALARMA_YA_ACTIVA", "MOVIMIENTO_AUTORIZADO"}


class _DatosTolerantes(dict):
    """Si falta un dato para rellenar el texto, se escribe '?' en vez de fallar."""

    def __missing__(self, clave):
        return "?"


def describir(resultado, **datos):
    """Texto para mostrar. `resultado` puede ser un Resultado o solo un código."""
    codigo = getattr(resultado, "codigo", resultado)
    if codigo in MENSAJES:
        return MENSAJES[codigo].format_map(_DatosTolerantes(datos))
    return getattr(resultado, "mensaje", None) or "Resultado no reconocido: {0}".format(codigo)


def nivel(codigo):
    return NIVELES.get(codigo, "info")


def fue_procesado(codigo):
    return codigo in CODIGOS_PROCESADOS
