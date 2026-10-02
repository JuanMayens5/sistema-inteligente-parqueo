"""
Capa de datos (backend)
=======================

Punto único para obtener el origen de datos que usa la aplicación:

    from datos import cargar_configuracion, obtener_backend

    config = cargar_configuracion()          # lee config_db.ini
    db = obtener_backend(config.origen)      # módulo datos.sqlserver o datos.memoria
    conexion = db.conectar_db(config)
    db.asignar_espacio(conexion, "P123ABC")  # -> Resultado("OK", "...", "C-01")

Los dos módulos tienen exactamente las mismas funciones (ver datos/contrato.py),
así que el resto del programa nunca necesita saber cuál de los dos está usando.

Contenido del paquete
---------------------
    __init__.py   configuración (config_db.ini) y selección del origen
    contrato.py   Resultado, ErrorConexion, estados y utilidades compartidas
    sqlserver.py  origen real: SQL Server con pyodbc
    memoria.py    origen de demostración: imita a la base en memoria
"""

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from datos.contrato import ErrorConexion

RUTA_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RUTA_PROYECTO / "config_db.ini"
ORIGENES = ("sqlserver", "mock")


@dataclass
class Configuracion:
    """Valores de config_db.ini. Los de aquí son los valores por defecto."""

    origen: str = "sqlserver"
    driver: str = "ODBC Driver 18 for SQL Server"
    servidor: str = "localhost"
    base_datos: str = "SistemaInteligenteParqueo"
    autenticacion: str = "windows"      # windows | sql
    usuario: str = ""
    contrasena: str = ""
    operador: str = "CONTROL"
    refresco_ms: int = 3000


def cargar_configuracion(ruta=RUTA_CONFIG):
    """Lee config_db.ini. Si no existe, devuelve los valores por defecto.

    Dos variables de entorno tienen prioridad sobre el archivo:
        PARQUEO_ORIGEN          -> sqlserver | mock  (útil para pruebas)
        PARQUEO_DB_CONTRASENA   -> contraseña, para no escribirla en el archivo
    """
    lector = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    lector.read(ruta, encoding="utf-8")
    base = Configuracion()

    config = Configuracion(
        origen=lector.get("datos", "origen", fallback=base.origen),
        driver=lector.get("sqlserver", "driver", fallback=base.driver),
        servidor=lector.get("sqlserver", "servidor", fallback=base.servidor),
        base_datos=lector.get("sqlserver", "base_datos", fallback=base.base_datos),
        autenticacion=lector.get("sqlserver", "autenticacion", fallback=base.autenticacion),
        usuario=lector.get("sqlserver", "usuario", fallback=base.usuario),
        contrasena=lector.get("sqlserver", "contrasena", fallback=base.contrasena),
        operador=lector.get("operacion", "operador", fallback=base.operador),
        refresco_ms=lector.getint("operacion", "refresco_ms", fallback=base.refresco_ms),
    )
    config.origen = os.environ.get("PARQUEO_ORIGEN", config.origen).strip().lower()
    config.autenticacion = config.autenticacion.strip().lower()
    config.contrasena = os.environ.get("PARQUEO_DB_CONTRASENA", config.contrasena)
    return config


def obtener_backend(origen):
    """Devuelve el módulo que implementa el contrato para ese origen.

    El import de sqlserver se hace aquí adentro para que el modo demostración
    funcione aunque pyodbc no esté instalado.
    """
    if origen == "mock":
        from datos import memoria
        return memoria

    if origen == "sqlserver":
        try:
            from datos import sqlserver
        except ImportError as error:
            raise ErrorConexion(
                "Falta el paquete pyodbc. Instálalo con:  pip install -r requirements.txt"
            ) from error
        return sqlserver

    raise ValueError("Origen de datos desconocido en config_db.ini: '{0}'. "
                     "Usa uno de: {1}.".format(origen, ", ".join(ORIGENES)))
