"""
Origen de datos: memoria (modo demostración)
============================================

Imita a la base de datos real sin necesitar SQL Server: las mismas tablas
(como listas de diccionarios), los mismos catálogos, las mismas reglas y los
MISMOS códigos y mensajes que devuelven los procedimientos de database.sql.

Para qué sirve
--------------
* Abrir la aplicación en una computadora sin SQL Server (modo demostración).
* Desarrollar la interfaz sin depender de la base.
* Comprobar que nada depende de detalles de SQL Server: pruebas/prueba_backend.py
  corre los mismos casos contra este módulo y contra la base real, y ambos
  tienen que dar lo mismo.

Cómo está organizado
--------------------
* BaseEnMemoria hace el papel de la "conexión": guarda todas las tablas.
  Cada conectar_db() crea una base nueva e independiente.
* Cada función pública lleva el nombre del procedimiento que imita. Si se
  cambia un procedimiento en database.sql, hay que reflejar el cambio aquí.

Diferencia deliberada con la base real: implementa pa_cancelar_ocupacion
(propuesta del Anexo A del plan) aunque la base todavía no lo tenga.
"""

from datetime import datetime

from datos.contrato import (
    ASIGNADA, ASIGNADO, AUTORIZADA, CANCELADA, DISPONIBLE, FINALIZADA, OCUPACION_ACTIVA,
    OCUPADA, OCUPADO, Resultado, normalizar,
)

# =============================================================================
#  Datos iniciales (copia de la sección 5 de database.sql)
# =============================================================================

TIPOS_VEHICULO = ["CARGA", "COMPACTO", "GRANDE", "MOTOCICLETA", "RESERVADO"]

# (tipo de vehículo, tipo de espacio) -> prioridad. 1 = ideal, 2 = alternativa.
COMPATIBILIDAD = {
    ("COMPACTO", "COMPACTO"): 1,
    ("COMPACTO", "GRANDE"): 2,
    ("GRANDE", "GRANDE"): 1,
    ("MOTOCICLETA", "MOTOCICLETA"): 1,
    ("MOTOCICLETA", "COMPACTO"): 2,
    ("CARGA", "CARGA_DESCARGA"): 1,
    ("RESERVADO", "RESERVADO"): 1,
}

# (código, tipo de espacio, sector, pin del hardware)
ESPACIOS_INICIALES = [
    ("C-01", "COMPACTO", "A", "PIN-02"),
    ("C-02", "COMPACTO", "A", "PIN-03"),
    ("C-03", "COMPACTO", "A", "PIN-04"),
    ("G-01", "GRANDE", "B", "PIN-05"),
    ("G-02", "GRANDE", "B", "PIN-06"),
    ("M-01", "MOTOCICLETA", "C", "PIN-07"),
    ("M-02", "MOTOCICLETA", "C", "PIN-08"),
    ("CD-01", "CARGA_DESCARGA", "D", "PIN-09"),
    ("R-01", "RESERVADO", "D", "PIN-10"),
]


class BaseEnMemoria:
    """Hace de "conexión": contiene todas las tablas de la base simulada."""

    descripcion = "Modo demostración · datos en memoria"
    cancelacion_disponible = True

    def __init__(self, con_ejemplos=True):
        self.reiniciar(con_ejemplos)

    def reiniciar(self, con_ejemplos=True):
        """Deja las tablas como recién creadas por database.sql."""
        self.espacios = [
            {"id": numero, "codigo": codigo, "tipo_espacio": tipo, "sector": sector,
             "estado": DISPONIBLE, "direccion_hw": pin, "led_estado": "VERDE",
             "sensor_ocupacion": False, "sensor_movimiento": False, "activo": True}
            for numero, (codigo, tipo, sector, pin) in enumerate(ESPACIOS_INICIALES, start=1)
        ]
        self.vehiculos = []
        self.ocupaciones = []
        self.alarmas = []
        self.eventos_sensor = []
        self.bitacora = []
        if con_ejemplos:
            _cargar_ejemplos(self)

    def reconectar(self):
        pass    # en memoria la "conexión" nunca se pierde

    def close(self):
        pass


def conectar_db(config=None, con_ejemplos=True):
    """Crea una base en memoria. Con con_ejemplos=True trae vehículos de muestra."""
    return BaseEnMemoria(con_ejemplos)


def reiniciar_datos_demo(conexion):
    """Solo existe en el modo demostración (la interfaz lo usa si está disponible)."""
    conexion.reiniciar(con_ejemplos=True)


# =============================================================================
#  Utilidades internas (equivalen a los SELECT/INSERT dentro de los procedimientos)
# =============================================================================

def _siguiente_id(tabla):
    return max((fila["id"] for fila in tabla), default=0) + 1


def _insertar(tabla, **fila):
    fila["id"] = _siguiente_id(tabla)
    tabla.append(fila)
    return fila


def _espacio_por_codigo(base, codigo):
    return next((e for e in base.espacios if e["codigo"] == normalizar(codigo)), None)


def _espacio_por_id(base, espacio_id):
    return next(e for e in base.espacios if e["id"] == espacio_id)


def _vehiculo_por_placa(base, placa):
    return next((v for v in base.vehiculos if v["placa"] == normalizar(placa)), None)


def _vehiculo_por_id(base, vehiculo_id):
    return next(v for v in base.vehiculos if v["id"] == vehiculo_id)


def _ocupacion(base, estados, placa=None, espacio_id=None):
    """Ocupación de un vehículo (por placa) o de un espacio, en alguno de los estados dados."""
    vehiculo = _vehiculo_por_placa(base, placa) if placa is not None else None
    if placa is not None and vehiculo is None:
        return None
    for ocupacion in base.ocupaciones:
        if ocupacion["estado"] not in estados:
            continue
        if vehiculo is not None and ocupacion["vehiculo_id"] != vehiculo["id"]:
            continue
        if espacio_id is not None and ocupacion["espacio_id"] != espacio_id:
            continue
        return ocupacion
    return None


def _alarma_activa(base, espacio_id):
    return next((a for a in base.alarmas
                 if a["espacio_id"] == espacio_id and a["estado"] == "ACTIVA"), None)


def _crear_alarma(base, espacio, ocupacion, tipo, descripcion):
    _insertar(base.alarmas, espacio_id=espacio["id"], ocupacion_id=ocupacion["id"], tipo=tipo,
              estado="ACTIVA", fecha_inicio=datetime.now(), fecha_fin=None,
              apagada_por=None, descripcion=descripcion)


def _apagar_alarma(alarma, usuario):
    alarma.update(estado="APAGADA", fecha_fin=datetime.now(), apagada_por=usuario)


def _registrar_evento(base, espacio, tipo_sensor, valor):
    _insertar(base.eventos_sensor, espacio_id=espacio["id"], tipo_sensor=tipo_sensor,
              valor=valor, fecha=datetime.now())


# =============================================================================
#  Escrituras (imitan a los procedimientos almacenados)
# =============================================================================

def registrar_vehiculo(conexion, placa, tipo):
    """pa_registrar_vehiculo"""
    placa, tipo = normalizar(placa), normalizar(tipo)
    if tipo not in TIPOS_VEHICULO:
        return Resultado("TIPO_INVALIDO", "El tipo de vehículo no existe en el catálogo.", None)
    if _vehiculo_por_placa(conexion, placa):
        return Resultado("YA_REGISTRADO", "La placa ya se encontraba registrada.", None)
    _insertar(conexion.vehiculos, placa=placa, tipo_vehiculo=tipo, fecha_registro=datetime.now())
    return Resultado("OK", "Vehículo registrado correctamente.", None)


def asignar_espacio(conexion, placa):
    """pa_asignar_espacio: primer espacio libre compatible, por prioridad y luego por id."""
    vehiculo = _vehiculo_por_placa(conexion, placa)
    if vehiculo is None:
        return Resultado("VEHICULO_NO_ENCONTRADO", "El vehículo no está registrado.", None)
    if _ocupacion(conexion, OCUPACION_ACTIVA, placa=placa):
        return Resultado("YA_TIENE_ESPACIO", "El vehículo ya tiene un espacio asignado.", None)

    candidatos = [
        (COMPATIBILIDAD[(vehiculo["tipo_vehiculo"], e["tipo_espacio"])], e["id"], e)
        for e in conexion.espacios
        if (vehiculo["tipo_vehiculo"], e["tipo_espacio"]) in COMPATIBILIDAD
        and e["estado"] == DISPONIBLE and e["activo"]
    ]
    if not candidatos:
        return Resultado("SIN_ESPACIO",
                         "No hay espacios disponibles para este tipo de vehículo.", None)

    espacio = min(candidatos, key=lambda candidato: candidato[:2])[2]
    _insertar(conexion.ocupaciones, vehiculo_id=vehiculo["id"], espacio_id=espacio["id"],
              estado=ASIGNADA, fecha_asignacion=datetime.now(), fecha_llegada=None,
              fecha_autorizacion=None, fecha_salida=None, seguridad_activa=False,
              autorizado_por=None)
    espacio.update(estado=ASIGNADO, led_estado="AMARILLO")
    return Resultado("OK", "Espacio asignado. Esperando la llegada del vehículo.",
                     espacio["codigo"])


def registrar_llegada(conexion, placa):
    """pa_llegada: confirma la ocupación y arma la seguridad."""
    ocupacion = _ocupacion(conexion, (ASIGNADA,), placa=placa)
    if ocupacion is None:
        return Resultado("SIN_ASIGNACION",
                         "El vehículo no tiene una asignación pendiente de llegada.", None)
    espacio = _espacio_por_id(conexion, ocupacion["espacio_id"])
    ocupacion.update(estado=OCUPADA, fecha_llegada=datetime.now(), seguridad_activa=True)
    espacio.update(estado=OCUPADO, led_estado="ROJO", sensor_ocupacion=True)
    _registrar_evento(conexion, espacio, "OCUPACION", True)
    return Resultado("OK", "Llegada confirmada. Sistema de seguridad activado.",
                     espacio["codigo"])


def registrar_movimiento(conexion, codigo_espacio):
    """pa_registrar_movimiento: alarma si hay un vehículo con seguridad armada."""
    espacio = _espacio_por_codigo(conexion, codigo_espacio)
    if espacio is None:
        return Resultado("ESPACIO_NO_ENCONTRADO", "El código de espacio no existe.", None)
    _registrar_evento(conexion, espacio, "MOVIMIENTO", True)

    ocupacion = _ocupacion(conexion, (OCUPADA, AUTORIZADA), espacio_id=espacio["id"])
    placa = _vehiculo_por_id(conexion, ocupacion["vehiculo_id"])["placa"] if ocupacion else None
    if ocupacion is None or not ocupacion["seguridad_activa"]:
        return Resultado("MOVIMIENTO_AUTORIZADO", "Movimiento registrado sin generar alarma.", placa)
    if _alarma_activa(conexion, espacio["id"]):
        return Resultado("ALARMA_YA_ACTIVA", "Ya existe una alarma activa en este espacio.", placa)

    _crear_alarma(conexion, espacio, ocupacion, "MOVIMIENTO_NO_AUTORIZADO",
                  "Movimiento no autorizado del vehículo " + placa)
    espacio.update(led_estado="PARPADEO", sensor_movimiento=True)
    return Resultado("ALARMA_ACTIVADA",
                     "¡ALARMA! Movimiento no autorizado en " + espacio["codigo"], placa)


def apagar_alarma(conexion, placa, usuario="OPERADOR"):
    """pa_apagar_alarma: apaga la alarma, pero la seguridad sigue armada."""
    ocupacion = _ocupacion(conexion, OCUPACION_ACTIVA, placa=placa)
    alarma = _alarma_activa(conexion, ocupacion["espacio_id"]) if ocupacion else None
    if alarma is None:
        return Resultado("SIN_ALARMA", "No hay una alarma activa para ese vehículo.", None)
    _apagar_alarma(alarma, usuario)
    _espacio_por_id(conexion, alarma["espacio_id"]).update(led_estado="ROJO",
                                                            sensor_movimiento=False)
    return Resultado("OK", "Alarma desactivada.", None)


def autorizar_salida(conexion, placa, operador="OPERADOR"):
    """pa_autorizar_salida: desarma la seguridad y cierra las alarmas del espacio."""
    ocupacion = _ocupacion(conexion, (OCUPADA,), placa=placa)
    if ocupacion is None:
        return Resultado("SIN_OCUPACION",
                         "El vehículo no tiene una ocupación activa que autorizar.", None)
    ocupacion.update(estado=AUTORIZADA, fecha_autorizacion=datetime.now(),
                     seguridad_activa=False, autorizado_por=operador)
    alarma = _alarma_activa(conexion, ocupacion["espacio_id"])
    if alarma:
        _apagar_alarma(alarma, operador)
    _espacio_por_id(conexion, ocupacion["espacio_id"]).update(led_estado="AMARILLO",
                                                               sensor_movimiento=False)
    return Resultado("OK", "Salida autorizada.", None)


def registrar_salida(conexion, placa):
    """pa_salida: libera el espacio, o genera alarma si la salida no fue autorizada."""
    ocupacion = _ocupacion(conexion, (OCUPADA, AUTORIZADA), placa=placa)
    if ocupacion is None:
        return Resultado("SIN_OCUPACION", "El vehículo no se encuentra dentro del parqueo.", None)
    espacio = _espacio_por_id(conexion, ocupacion["espacio_id"])

    if ocupacion["estado"] != AUTORIZADA:
        if not _alarma_activa(conexion, espacio["id"]):
            _crear_alarma(conexion, espacio, ocupacion, "SALIDA_NO_AUTORIZADA",
                          "Intento de salida sin autorización del vehículo " + normalizar(placa))
            espacio.update(led_estado="PARPADEO")
        return Resultado("SALIDA_NO_AUTORIZADA",
                         "La salida no ha sido autorizada por el operador. Alarma activada.",
                         espacio["codigo"])

    ocupacion.update(estado=FINALIZADA, fecha_salida=datetime.now(), seguridad_activa=False)
    espacio.update(estado=DISPONIBLE, led_estado="VERDE", sensor_ocupacion=False,
                   sensor_movimiento=False)
    _registrar_evento(conexion, espacio, "OCUPACION", False)
    return Resultado("OK", "Salida registrada. El espacio quedó disponible.", espacio["codigo"])


def soporta_cancelacion(conexion):
    return True


def cancelar_ocupacion(conexion, codigo_espacio, usuario="OPERADOR"):
    """pa_cancelar_ocupacion (PROPUESTO, ver Anexo A del plan): liberación manual."""
    espacio = _espacio_por_codigo(conexion, codigo_espacio)
    if espacio is None:
        return Resultado("ESPACIO_NO_ENCONTRADO", "El código de espacio no existe.", None)
    ocupacion = _ocupacion(conexion, OCUPACION_ACTIVA, espacio_id=espacio["id"])
    if ocupacion is None:
        return Resultado("ESPACIO_YA_LIBRE", "El espacio no tiene una ocupación activa.", None)

    ocupacion.update(estado=CANCELADA, fecha_salida=datetime.now(), seguridad_activa=False)
    alarma = _alarma_activa(conexion, espacio["id"])
    if alarma:
        _apagar_alarma(alarma, usuario)
    espacio.update(estado=DISPONIBLE, led_estado="VERDE", sensor_ocupacion=False,
                   sensor_movimiento=False)
    placa = _vehiculo_por_id(conexion, ocupacion["vehiculo_id"])["placa"]
    return Resultado("OK", "Ocupación cancelada y espacio liberado.", placa)


def registrar_bitacora(conexion, texto, comando, parametros, resultado, mensaje, usuario):
    _insertar(conexion.bitacora, fecha=datetime.now(), texto_original=texto[:300],
              comando=comando, parametros=parametros, resultado=resultado,
              mensaje=mensaje, usuario=usuario)


# =============================================================================
#  Lecturas (mismas columnas que las consultas de datos/sqlserver.py)
# =============================================================================

def obtener_estado_parqueo(conexion):
    """Imita a pa_consultar / vw_estado_parqueo: una fila por espacio."""
    filas = []
    for espacio in conexion.espacios:
        ocupacion = _ocupacion(conexion, OCUPACION_ACTIVA, espacio_id=espacio["id"])
        vehiculo = _vehiculo_por_id(conexion, ocupacion["vehiculo_id"]) if ocupacion else None
        filas.append({
            "espacio": espacio["codigo"],
            "tipo": espacio["tipo_espacio"],
            "sector": espacio["sector"],
            "estado": espacio["estado"],
            "led_estado": espacio["led_estado"],
            "placa_vehiculo": vehiculo["placa"] if vehiculo else None,
            "tipo_vehiculo": vehiculo["tipo_vehiculo"] if vehiculo else None,
            "estado_ocupacion": ocupacion["estado"] if ocupacion else None,
            "fecha_asignacion": ocupacion["fecha_asignacion"] if ocupacion else None,
            "fecha_llegada": ocupacion["fecha_llegada"] if ocupacion else None,
            "alarma_activa": "SI" if _alarma_activa(conexion, espacio["id"]) else "NO",
        })
    return sorted(filas, key=lambda fila: (fila["tipo"], fila["espacio"]))


def listar_tipos_vehiculo(conexion):
    return list(TIPOS_VEHICULO)


def listar_vehiculos(conexion):
    filas = []
    for vehiculo in reversed(conexion.vehiculos):
        ocupacion = _ocupacion(conexion, OCUPACION_ACTIVA, placa=vehiculo["placa"])
        espacio = _espacio_por_id(conexion, ocupacion["espacio_id"]) if ocupacion else None
        filas.append({"placa": vehiculo["placa"], "tipo_vehiculo": vehiculo["tipo_vehiculo"],
                      "fecha_registro": vehiculo["fecha_registro"],
                      "espacio": espacio["codigo"] if espacio else None,
                      "estado_ocupacion": ocupacion["estado"] if ocupacion else None})
    return filas


def listar_ocupaciones(conexion, solo_activas=True):
    filas = []
    for ocupacion in reversed(conexion.ocupaciones):
        if solo_activas and ocupacion["estado"] not in OCUPACION_ACTIVA:
            continue
        vehiculo = _vehiculo_por_id(conexion, ocupacion["vehiculo_id"])
        filas.append({
            "id": ocupacion["id"], "placa": vehiculo["placa"],
            "tipo_vehiculo": vehiculo["tipo_vehiculo"],
            "espacio": _espacio_por_id(conexion, ocupacion["espacio_id"])["codigo"],
            "estado": ocupacion["estado"],
            "fecha_asignacion": ocupacion["fecha_asignacion"],
            "fecha_llegada": ocupacion["fecha_llegada"],
            "fecha_autorizacion": ocupacion["fecha_autorizacion"],
            "fecha_salida": ocupacion["fecha_salida"],
            "autorizado_por": ocupacion["autorizado_por"],
        })
    return filas


def listar_alarmas_activas(conexion):
    filas = []
    for alarma in reversed(conexion.alarmas):
        if alarma["estado"] != "ACTIVA":
            continue
        ocupacion = next(o for o in conexion.ocupaciones if o["id"] == alarma["ocupacion_id"])
        vehiculo = _vehiculo_por_id(conexion, ocupacion["vehiculo_id"])
        filas.append({"alarma_id": alarma["id"],
                      "espacio": _espacio_por_id(conexion, alarma["espacio_id"])["codigo"],
                      "placa": vehiculo["placa"], "tipo_vehiculo": vehiculo["tipo_vehiculo"],
                      "tipo": alarma["tipo"], "fecha_inicio": alarma["fecha_inicio"],
                      "descripcion": alarma["descripcion"]})
    return filas


def listar_eventos_sensor(conexion, limite=100):
    return [{"id": evento["id"],
             "espacio": _espacio_por_id(conexion, evento["espacio_id"])["codigo"],
             "tipo_sensor": evento["tipo_sensor"], "valor": evento["valor"],
             "fecha": evento["fecha"]}
            for evento in reversed(conexion.eventos_sensor[-limite:])]


def listar_bitacora(conexion, limite=100):
    return [dict(fila) for fila in reversed(conexion.bitacora[-limite:])]


def buscar_vehiculo(conexion, placa):
    vehiculo = _vehiculo_por_placa(conexion, placa)
    if vehiculo is None:
        return None
    ocupacion = _ocupacion(conexion, OCUPACION_ACTIVA, placa=placa)
    espacio = _espacio_por_id(conexion, ocupacion["espacio_id"]) if ocupacion else None
    alarma = _alarma_activa(conexion, espacio["id"]) if espacio else None
    return {
        "placa": vehiculo["placa"], "tipo_vehiculo": vehiculo["tipo_vehiculo"],
        "fecha_registro": vehiculo["fecha_registro"],
        "espacio": espacio["codigo"] if espacio else None,
        "tipo_espacio": espacio["tipo_espacio"] if espacio else None,
        "estado_ocupacion": ocupacion["estado"] if ocupacion else None,
        "fecha_asignacion": ocupacion["fecha_asignacion"] if ocupacion else None,
        "fecha_llegada": ocupacion["fecha_llegada"] if ocupacion else None,
        "fecha_autorizacion": ocupacion["fecha_autorizacion"] if ocupacion else None,
        "autorizado_por": ocupacion["autorizado_por"] if ocupacion else None,
        "seguridad_activa": ocupacion["seguridad_activa"] if ocupacion else None,
        "alarma_activa": "SI" if alarma else "NO",
        "tipo_alarma": alarma["tipo"] if alarma else None,
    }


# =============================================================================
#  Datos de ejemplo del modo demostración
# =============================================================================

def _cargar_ejemplos(base):
    """Deja un vehículo en cada etapa del ciclo para que se vean todos los estados."""
    ejemplos = [("P111AAA", "COMPACTO"), ("P222BBB", "GRANDE"), ("M333CCC", "MOTOCICLETA"),
                ("C444DDD", "CARGA"), ("P555EEE", "COMPACTO")]
    for placa, tipo in ejemplos:
        registrar_vehiculo(base, placa, tipo)

    for placa in ("P111AAA", "P222BBB", "M333CCC", "C444DDD"):
        asignar_espacio(base, placa)          # P222BBB se queda en ASIGNADA
    for placa in ("P111AAA", "M333CCC", "C444DDD"):
        registrar_llegada(base, placa)        # P111AAA se queda en OCUPADA
    autorizar_salida(base, "M333CCC", "DEMO")     # M333CCC en AUTORIZADA
    registrar_movimiento(base, "CD-01")           # C444DDD con alarma activa
    # P555EEE queda registrado sin espacio.
