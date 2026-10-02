"""
Contrato de la capa de datos
============================

Define la "forma" de lo que viaja entre la base de datos y el resto del
programa. Los dos orígenes de datos lo cumplen:

    datos/sqlserver.py  -> SQL Server real (database.sql)
    datos/memoria.py    -> modo demostración, todo en memoria

Por eso la interfaz, la consola y el simulador de sensores funcionan igual
con cualquiera de los dos: solo conocen lo que está descrito aquí.

Funciones que TODO origen de datos implementa
---------------------------------------------
Conexión
    conectar_db(config)                                   -> conexión

Escrituras: cada una llama a un procedimiento almacenado y devuelve un Resultado
    registrar_vehiculo(conexion, placa, tipo)             pa_registrar_vehiculo
    asignar_espacio(conexion, placa)                      pa_asignar_espacio       dato = espacio
    registrar_llegada(conexion, placa)                    pa_llegada               dato = espacio
    registrar_movimiento(conexion, codigo_espacio)        pa_registrar_movimiento  dato = placa
    apagar_alarma(conexion, placa, usuario)               pa_apagar_alarma
    autorizar_salida(conexion, placa, operador)           pa_autorizar_salida
    registrar_salida(conexion, placa)                     pa_salida                dato = espacio
    cancelar_ocupacion(conexion, codigo_espacio, usuario) pa_cancelar_ocupacion    dato = placa
    soporta_cancelacion(conexion)                         -> bool (¿existe ese procedimiento?)
    registrar_bitacora(conexion, texto, comando, parametros, resultado, mensaje, usuario)

Lecturas
    obtener_estado_parqueo(conexion)          -> list[dict]  una fila por espacio (ver abajo)
    listar_tipos_vehiculo(conexion)           -> list[str]
    listar_vehiculos(conexion)                -> list[dict]
    listar_ocupaciones(conexion, solo_activas=True) -> list[dict]
    listar_alarmas_activas(conexion)          -> list[dict]
    listar_eventos_sensor(conexion, limite=100) -> list[dict]
    listar_bitacora(conexion, limite=100)     -> list[dict]
    buscar_vehiculo(conexion, placa)          -> dict o None

El objeto conexión además tiene:
    .descripcion    texto para el indicador inferior de la interfaz
    .reconectar()   vuelve a abrir la conexión (lanza ErrorConexion si no puede)
    .close()

Fila del estado del parqueo (columnas de la vista vw_estado_parqueo)
---------------------------------------------------------------------
    espacio, tipo, sector, estado, led_estado, placa_vehiculo, tipo_vehiculo,
    estado_ocupacion, fecha_asignacion, fecha_llegada, alarma_activa ('SI'/'NO')
"""

from collections import namedtuple

# Respuesta de toda operación de escritura, igual a la fila que devuelven los
# procedimientos almacenados:
#   codigo  -> "OK", "SIN_ESPACIO", "ALARMA_ACTIVADA", ...
#   mensaje -> texto que devolvió la base (se usa si mensajes.py no conoce el código)
#   dato    -> código de espacio, placa o None, según la operación
Resultado = namedtuple("Resultado", ["codigo", "mensaje", "dato"])


class ErrorConexion(Exception):
    """Se perdió (o no se pudo abrir) la conexión con la base de datos.

    La capa de datos traduce los errores de pyodbc a esta excepción para que
    la interfaz no tenga que conocer pyodbc.
    """


# --- Estados de un espacio (columna espacios.estado) -------------------------
DISPONIBLE = "DISPONIBLE"
ASIGNADO = "ASIGNADO"                # reservado, el vehículo todavía no llega
OCUPADO = "OCUPADO"                  # el sensor confirmó la llegada
FUERA_DE_SERVICIO = "FUERA_DE_SERVICIO"

# --- Ciclo de vida de una ocupación (columna ocupaciones.estado) -------------
#   ASIGNADA -> OCUPADA -> AUTORIZADA -> FINALIZADA   (o CANCELADA)
ASIGNADA = "ASIGNADA"
OCUPADA = "OCUPADA"
AUTORIZADA = "AUTORIZADA"
FINALIZADA = "FINALIZADA"
CANCELADA = "CANCELADA"
OCUPACION_ACTIVA = (ASIGNADA, OCUPADA, AUTORIZADA)

LONGITUD_MAXIMA_PLACA = 20           # vehiculos.placa es VARCHAR(20)


def normalizar(texto):
    """Quita espacios y pasa a mayúsculas, igual que hacen los procedimientos."""
    return (texto or "").strip().upper()


def resumir(estado_parqueo):
    """Cuenta los espacios por estado y las alarmas activas.

    Recibe la lista de obtener_estado_parqueo() para no volver a consultar
    la base (se usa en los indicadores del encabezado).
    """
    conteo = {"total": len(estado_parqueo), "disponibles": 0, "asignados": 0,
              "ocupados": 0, "fuera_de_servicio": 0, "alarmas": 0}
    clave_por_estado = {DISPONIBLE: "disponibles", ASIGNADO: "asignados",
                        OCUPADO: "ocupados", FUERA_DE_SERVICIO: "fuera_de_servicio"}
    for fila in estado_parqueo:
        conteo[clave_por_estado[fila["estado"]]] += 1
        if fila["alarma_activa"] == "SI":
            conteo["alarmas"] += 1
    return conteo


def fila_de_espacio(estado_parqueo, codigo):
    """Fila del estado del parqueo que corresponde a un espacio, o None."""
    codigo = normalizar(codigo)
    return next((f for f in estado_parqueo if f["espacio"] == codigo), None)


def fila_de_placa(estado_parqueo, placa):
    """Fila del espacio donde está (o está asignado) un vehículo, o None."""
    placa = normalizar(placa)
    return next((f for f in estado_parqueo if f["placa_vehiculo"] == placa), None)
