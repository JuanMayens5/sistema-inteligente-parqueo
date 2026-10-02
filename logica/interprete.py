"""
Consola del lenguaje (intérprete PROVISIONAL)
=============================================

Recibe una línea de texto, la analiza y la ejecuta contra la base:

    texto ──► tokenizar() ──► ¿comando y argumentos válidos? ──► función de datos ──► respuesta
              (fase léxica)    (fase sintáctica)                  (fase semántica: la base decide)

Cada instrucción queda guardada en la tabla bitacora_comandos con la fase en
la que terminó:

    OK                la instrucción se ejecutó
    ERROR_LEXICO      hay un carácter que el tokenizador no reconoce
    ERROR_SINTACTICO  comando desconocido o cantidad de argumentos incorrecta
    ERROR_SEMANTICO   la sintaxis es correcta, pero la base la rechazó (ej. SIN_ESPACIO)
    ERROR_EJECUCION   falló algo inesperado al ejecutarla

Es PROVISIONAL: cuando el analizador léxico/sintáctico definitivo del curso
esté listo, reemplazará a este archivo conservando la función ejecutar(),
que es lo único que usa la interfaz.

Sintaxis actual:  COMANDO arg1 arg2 ...   (ej. REGISTRAR P123ABC COMPACTO)
La sintaxis oficial está pendiente de definir con el equipo del lenguaje.
"""

import re
from collections import namedtuple

from datos.contrato import (
    ASIGNADO, DISPONIBLE, FUERA_DE_SERVICIO, OCUPADO, ErrorConexion, normalizar, resumir,
)
from logica import mensajes

# =============================================================================
#  Fase léxica: tokenizador
# =============================================================================

PALABRAS_RESERVADAS = {
    "AYUDA", "ESTADO", "CONSULTAR", "VEHICULOS", "ALARMAS", "BUSCAR", "TOKENS",
    "REGISTRAR", "ASIGNAR", "LLEGADA", "MOVIMIENTO", "APAGAR_ALARMA",
    "AUTORIZAR_SALIDA", "SALIDA", "LIBERAR",
}

# Cada token se reconoce con una expresión regular. El orden importa: se
# prueba de arriba hacia abajo, así que lo más específico va primero.
_ESPECIFICACION_TOKENS = [
    ("ESPACIO_BLANCO", r"[ \t]+"),
    ("FIN_INSTRUCCION", r";"),
    ("CADENA", r'"[^"]*"'),
    ("CODIGO_ESPACIO", r"[A-Za-z]{1,2}-[0-9]{2}\b"),        # C-01, CD-01
    ("PLACA", r"[A-Za-z][0-9]{3}[A-Za-z]{3}\b"),            # P123ABC
    ("PALABRA", r"[A-Za-zÁÉÍÓÚÑáéíóúñ_][A-Za-zÁÉÍÓÚÑáéíóúñ_0-9]*"),
    ("NUMERO", r"[0-9]+"),
    ("DESCONOCIDO", r"."),
]
_PATRON = re.compile("|".join("(?P<{0}>{1})".format(nombre, patron)
                              for nombre, patron in _ESPECIFICACION_TOKENS))

Token = namedtuple("Token", ["tipo", "lexema", "columna"])


def tokenizar(texto):
    """Parte el texto en tokens. Las palabras reservadas se marcan como RESERVADA."""
    tokens = []
    for coincidencia in _PATRON.finditer(texto):
        tipo, lexema = coincidencia.lastgroup, coincidencia.group()
        if tipo == "ESPACIO_BLANCO":
            continue
        if tipo == "PALABRA" and lexema.upper() in PALABRAS_RESERVADAS:
            tipo = "RESERVADA"
        tokens.append(Token(tipo, lexema, coincidencia.start() + 1))
    return tokens


# =============================================================================
#  Punto de entrada
# =============================================================================

# nivel -> color en la consola; clasificacion -> columna "resultado" de la bitácora
Respuesta = namedtuple("Respuesta", ["nivel", "mensaje", "clasificacion"])


def ejecutar(texto, db, conexion, usuario):
    """Analiza, ejecuta y registra en la bitácora una instrucción. Devuelve (nivel, mensaje).

    Si se pierde la conexión, se deja pasar el ErrorConexion para que la
    interfaz lo maneje (sin conexión tampoco se puede escribir la bitácora).
    """
    texto = texto.strip().rstrip(";").strip()
    if not texto:
        return "info", ""

    try:
        respuesta = _interpretar(texto, db, conexion, usuario)
    except ErrorConexion:
        raise
    except Exception as error:
        respuesta = Respuesta("error", "Error al ejecutar: {0}".format(error), "ERROR_EJECUCION")

    palabras = texto.split(None, 1)
    db.registrar_bitacora(conexion, texto, palabras[0].upper(),
                          palabras[1] if len(palabras) > 1 else None,
                          respuesta.clasificacion, respuesta.mensaje.splitlines()[0], usuario)
    return respuesta.nivel, respuesta.mensaje


def _interpretar(texto, db, conexion, usuario):
    """Pasa por las tres fases y devuelve la Respuesta."""
    tokens = tokenizar(texto)

    invalido = next((t for t in tokens if t.tipo == "DESCONOCIDO"), None)
    if invalido:
        return Respuesta("error", "Error léxico: carácter no válido '{0}' en la columna {1}."
                         .format(invalido.lexema, invalido.columna), "ERROR_LEXICO")

    comando = tokens[0].lexema.upper()
    argumentos = [normalizar(t.lexema.strip('"')) for t in tokens[1:] if t.tipo != "FIN_INSTRUCCION"]

    if comando in ACCIONES:
        return _ejecutar_accion(comando, argumentos, db, conexion, usuario)
    if comando in CONSULTAS:
        return CONSULTAS[comando](db, conexion, argumentos, texto)
    return Respuesta("error", "Error sintáctico: '{0}' no es un comando conocido. Escribe AYUDA."
                     .format(tokens[0].lexema), "ERROR_SINTACTICO")


# =============================================================================
#  Comandos que modifican la base (cada uno llama a un procedimiento)
# =============================================================================

# comando -> (argumentos que espera, llamada a la base, texto si sale "OK")
ACCIONES = {
    "REGISTRAR": (("placa", "tipo"),
                  lambda db, c, a, u: db.registrar_vehiculo(c, a["placa"], a["tipo"]),
                  "Vehículo {placa} ({tipo}) registrado."),
    "ASIGNAR": (("placa",),
                lambda db, c, a, u: db.asignar_espacio(c, a["placa"]),
                "Espacio {espacio} asignado al vehículo {placa}."),
    "LLEGADA": (("placa",),
                lambda db, c, a, u: db.registrar_llegada(c, a["placa"]),
                "Llegada de {placa} confirmada en {espacio}. Seguridad activada."),
    "MOVIMIENTO": (("espacio",),
                   lambda db, c, a, u: db.registrar_movimiento(c, a["espacio"]),
                   "Movimiento registrado en {espacio}."),
    "APAGAR_ALARMA": (("placa",),
                      lambda db, c, a, u: db.apagar_alarma(c, a["placa"], u),
                      "Alarma del vehículo {placa} desactivada. La seguridad sigue armada."),
    "AUTORIZAR_SALIDA": (("placa",),
                         lambda db, c, a, u: db.autorizar_salida(c, a["placa"], u),
                         "Salida del vehículo {placa} autorizada."),
    "SALIDA": (("placa",),
               lambda db, c, a, u: db.registrar_salida(c, a["placa"]),
               "Salida de {placa} registrada. {espacio} quedó disponible."),
    "LIBERAR": (("espacio",),
                lambda db, c, a, u: db.cancelar_ocupacion(c, a["espacio"], u),
                "Espacio {espacio} liberado (ocupación de {placa} cancelada)."),
}


def _ejecutar_accion(comando, argumentos, db, conexion, usuario):
    nombres, llamar, texto_exito = ACCIONES[comando]
    if len(argumentos) != len(nombres):
        uso = " ".join([comando] + ["<{0}>".format(nombre) for nombre in nombres])
        return Respuesta("error", "Error sintáctico. Uso: " + uso, "ERROR_SINTACTICO")

    datos = dict(zip(nombres, argumentos))
    resultado = llamar(db, conexion, datos, usuario)
    # "dato" es el espacio (ASIGNAR, LLEGADA, SALIDA) o la placa (MOVIMIENTO, LIBERAR):
    # completa el que no vino como argumento.
    datos.setdefault("placa", resultado.dato)
    datos.setdefault("espacio", resultado.dato)

    if resultado.codigo == "OK":
        return Respuesta("ok", texto_exito.format_map(datos), "OK")

    if "tipo" not in datos and datos.get("placa"):
        ficha = db.buscar_vehiculo(conexion, datos["placa"])
        datos["tipo"] = ficha["tipo_vehiculo"] if ficha else "?"
    clasificacion = "OK" if mensajes.fue_procesado(resultado.codigo) else "ERROR_SEMANTICO"
    return Respuesta(mensajes.nivel(resultado.codigo), mensajes.describir(resultado, **datos),
                     clasificacion)


# =============================================================================
#  Comandos de consulta (solo leen)
# =============================================================================

AYUDA = """Comandos disponibles (versión provisional):

  AYUDA                        muestra esta lista
  ESTADO                       resumen de ocupación del parqueo
  CONSULTAR [estado]           tabla de espacios (filtro opcional: DISPONIBLE, ASIGNADO, OCUPADO)
  VEHICULOS                    vehículos registrados
  ALARMAS                      alarmas activas y qué vehículo las genera
  BUSCAR <placa>               ficha de un vehículo
  REGISTRAR <placa> <tipo>     registra un vehículo (COMPACTO, GRANDE, MOTOCICLETA, CARGA, RESERVADO)
  ASIGNAR <placa>              le asigna un espacio compatible
  LLEGADA <placa>              confirma que llegó (activa la seguridad)
  MOVIMIENTO <espacio>         simula el sensor de movimiento (PIR)
  APAGAR_ALARMA <placa>        apaga la alarma del vehículo
  AUTORIZAR_SALIDA <placa>     autoriza la salida (desactiva la seguridad)
  SALIDA <placa>               registra la salida y libera el espacio
  LIBERAR <espacio>            cancela la ocupación (si la base lo permite)
  TOKENS <texto>               muestra cómo se tokeniza un texto
  LIMPIAR                      borra la consola

Ejemplo:  REGISTRAR P123ABC COMPACTO;"""


def _ayuda(db, conexion, argumentos, texto):
    return Respuesta("info", AYUDA, "OK")


def _estado(db, conexion, argumentos, texto):
    estado = db.obtener_estado_parqueo(conexion)
    conteo = resumir(estado)
    lineas = ["Parqueo: {total} espacios · {disponibles} disponibles · {asignados} asignados · "
              "{ocupados} ocupados · {alarmas} alarma(s)".format(**conteo)]
    for tipo in sorted({fila["tipo"] for fila in estado}):
        del_tipo = [fila for fila in estado if fila["tipo"] == tipo]
        libres = sum(1 for fila in del_tipo if fila["estado"] == DISPONIBLE)
        lineas.append("  {0:<16} {1}/{2} disponibles".format(tipo, libres, len(del_tipo)))
    return Respuesta("info", "\n".join(lineas), "OK")


def _consultar(db, conexion, argumentos, texto):
    estado = db.obtener_estado_parqueo(conexion)
    if argumentos:
        filtro = argumentos[0].rstrip("S")          # acepta DISPONIBLES, OCUPADOS...
        if filtro not in (DISPONIBLE, ASIGNADO, OCUPADO, FUERA_DE_SERVICIO):
            return Respuesta("error", "Error sintáctico. Filtro no válido: " + argumentos[0],
                             "ERROR_SINTACTICO")
        estado = [fila for fila in estado if fila["estado"] == filtro]
    columnas = [("espacio", "Espacio"), ("tipo", "Tipo"), ("estado", "Estado"),
                ("led_estado", "LED"), ("placa_vehiculo", "Placa"),
                ("estado_ocupacion", "Ocupación"), ("alarma_activa", "Alarma")]
    return Respuesta("info", _tabla("{0} espacio(s)".format(len(estado)), estado, columnas), "OK")


def _vehiculos(db, conexion, argumentos, texto):
    filas = db.listar_vehiculos(conexion)
    columnas = [("placa", "Placa"), ("tipo_vehiculo", "Tipo"), ("espacio", "Espacio"),
                ("estado_ocupacion", "Ocupación")]
    return Respuesta("info", _tabla("{0} vehículo(s) registrado(s)".format(len(filas)),
                                    filas, columnas), "OK")


def _alarmas(db, conexion, argumentos, texto):
    filas = db.listar_alarmas_activas(conexion)
    columnas = [("espacio", "Espacio"), ("placa", "Placa"), ("tipo", "Tipo"),
                ("descripcion", "Descripción")]
    return Respuesta("aviso" if filas else "info",
                     _tabla("{0} alarma(s) activa(s)".format(len(filas)), filas, columnas), "OK")


def _buscar(db, conexion, argumentos, texto):
    if len(argumentos) != 1:
        return Respuesta("error", "Error sintáctico. Uso: BUSCAR <placa>", "ERROR_SINTACTICO")
    ficha = db.buscar_vehiculo(conexion, argumentos[0])
    if ficha is None:
        return Respuesta("error", mensajes.describir("VEHICULO_NO_ENCONTRADO", placa=argumentos[0]),
                         "ERROR_SEMANTICO")
    campos = [("Placa", "placa"), ("Tipo", "tipo_vehiculo"), ("Espacio", "espacio"),
              ("Ocupación", "estado_ocupacion"), ("Seguridad armada", "seguridad_activa"),
              ("Alarma", "alarma_activa")]
    lineas = ["{0:<17} {1}".format(etiqueta + ":", _texto(ficha[clave])) for etiqueta, clave in campos]
    return Respuesta("info", "\n".join(lineas), "OK")


def _tokens(db, conexion, argumentos, texto):
    resto = texto.split(None, 1)[1] if " " in texto.strip() else ""
    if not resto:
        return Respuesta("error", "Error sintáctico. Uso: TOKENS <texto>", "ERROR_SINTACTICO")
    lineas = ["{0:<16} {1:<20} columna {2}".format(t.tipo, t.lexema, t.columna)
              for t in tokenizar(resto)]
    return Respuesta("info", "{0} token(s)\n".format(len(lineas)) + "\n".join(lineas), "OK")


CONSULTAS = {
    "AYUDA": _ayuda, "ESTADO": _estado, "CONSULTAR": _consultar, "VEHICULOS": _vehiculos,
    "ALARMAS": _alarmas, "BUSCAR": _buscar, "TOKENS": _tokens,
}


def _texto(valor):
    if valor is None:
        return "-"
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    return str(valor)


def _tabla(titulo, filas, columnas):
    """Tabla de texto alineada. La primera línea es el título (es lo que queda en la bitácora)."""
    if not filas:
        return titulo
    anchos = [max(len(encabezado), *(len(_texto(fila[clave])) for fila in filas))
              for clave, encabezado in columnas]
    lineas = [titulo, "  ".join(encabezado.ljust(ancho)
                                for (_, encabezado), ancho in zip(columnas, anchos))]
    for fila in filas:
        lineas.append("  ".join(_texto(fila[clave]).ljust(ancho)
                                for (clave, _), ancho in zip(columnas, anchos)))
    return "\n".join(lineas)
