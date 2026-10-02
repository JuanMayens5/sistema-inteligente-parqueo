"""
Reiniciar una base de datos a partir de database.sql
====================================================

Ejecuta database.sql completo, dejando la base como recién creada (con los
datos iniciales). Sirve para empezar las pruebas siempre desde el mismo punto.

    python herramientas/reiniciar_base.py                       # base de config_db.ini (pide confirmación)
    python herramientas/reiniciar_base.py --base MiBasePruebas  # otra base (se crea si no existe)

⚠ BORRA todos los vehículos, ocupaciones, alarmas, eventos y la bitácora.

Cómo funciona
-------------
database.sql tiene el nombre de la base escrito adentro; aquí se reemplaza
por el que se pida, así las pruebas usan una base separada
(SistemaInteligenteParqueo_Pruebas) y nunca tocan la de desarrollo.
El script se parte en los bloques separados por "GO" (igual que hace sqlcmd)
y cada bloque se ejecuta con pyodbc. Como pyodbc manda el texto en Unicode,
los acentos no se corrompen (con sqlcmd habría que usar -f 65001).
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar "datos"

import pyodbc

from datos import RUTA_PROYECTO, cargar_configuracion
from datos.sqlserver import cadena_conexion

RUTA_SCRIPT = RUTA_PROYECTO / "database.sql"
NOMBRE_EN_SCRIPT = "SistemaInteligenteParqueo"


def reiniciar_base(config, base_datos):
    """Crea (si hace falta) y reinicia `base_datos` ejecutando database.sql."""
    script = RUTA_SCRIPT.read_text(encoding="utf-8")
    script = re.sub(r"\b{0}\b".format(NOMBRE_EN_SCRIPT), base_datos, script)
    bloques = re.split(r"^\s*GO\s*;?\s*$", script, flags=re.MULTILINE | re.IGNORECASE)

    # Se conecta a "master" porque la base puede no existir todavía.
    conexion = pyodbc.connect(cadena_conexion(config, "master"), autocommit=True, timeout=5)
    try:
        for bloque in bloques:
            if bloque.strip():
                conexion.execute(bloque)
    finally:
        conexion.close()


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    argumentos.add_argument("--base", help="nombre de la base a reiniciar")
    argumentos.add_argument("--si", action="store_true", help="no pedir confirmación")
    opciones = argumentos.parse_args()

    config = cargar_configuracion()
    base_datos = opciones.base or config.base_datos
    if not opciones.si:
        respuesta = input("Se borrarán TODOS los datos de '{0}'. Escribe SI para continuar: "
                          .format(base_datos))
        if respuesta.strip() != "SI":
            print("Cancelado.")
            return
    reiniciar_base(config, base_datos)
    print("Base '{0}' reiniciada desde database.sql.".format(base_datos))


if __name__ == "__main__":
    main()
