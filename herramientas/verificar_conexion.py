"""
Diagnóstico de la conexión con SQL Server
=========================================

    python herramientas/verificar_conexion.py

Revisa, en orden, todo lo que la aplicación necesita y dice exactamente qué
falla. Solo LEE la base: no modifica nada.

    1. pyodbc instalado
    2. driver ODBC de config_db.ini instalado
    3. conexión a la base
    4. catálogos y espacios cargados
    5. procedimientos almacenados presentes
    6. acentos correctos (collation)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar "datos"

from datos import cargar_configuracion
from datos.contrato import ErrorConexion

PROCEDIMIENTOS = ["pa_registrar_vehiculo", "pa_asignar_espacio", "pa_llegada",
                  "pa_registrar_movimiento", "pa_apagar_alarma", "pa_autorizar_salida",
                  "pa_salida", "pa_consultar"]


def comprobar(correcto, texto):
    print("  [{0}] {1}".format("OK" if correcto else "X ", texto))
    return correcto


def main():
    config = cargar_configuracion()
    print("Configuración: servidor={0}  base={1}  autenticación={2}  driver={3}".format(
        config.servidor, config.base_datos, config.autenticacion, config.driver))

    try:
        import pyodbc
    except ImportError:
        comprobar(False, "pyodbc no está instalado -> pip install -r requirements.txt")
        return 1
    comprobar(True, "pyodbc {0}".format(pyodbc.version))

    if not comprobar(config.driver in pyodbc.drivers(), "driver '{0}' instalado".format(config.driver)):
        print("      Drivers disponibles:", ", ".join(pyodbc.drivers()))
        return 1

    from datos import sqlserver
    try:
        conexion = sqlserver.conectar_db(config)
    except ErrorConexion as error:
        comprobar(False, "conexión: {0}".format(error))
        return 1
    comprobar(True, "conexión a {0}".format(conexion.descripcion))

    espacios = sqlserver.obtener_estado_parqueo(conexion)
    tipos = sqlserver.listar_tipos_vehiculo(conexion)
    todo_bien = comprobar(len(espacios) > 0, "{0} espacios cargados".format(len(espacios)))
    todo_bien &= comprobar(len(tipos) > 0, "tipos de vehículo: {0}".format(", ".join(tipos)))

    existentes = {fila["name"] for fila in conexion.ejecutar(
        "SELECT name FROM sys.procedures WHERE name LIKE 'pa[_]%'")}
    faltantes = [nombre for nombre in PROCEDIMIENTOS if nombre not in existentes]
    todo_bien &= comprobar(not faltantes, "procedimientos almacenados" +
                           (" (faltan: {0})".format(", ".join(faltantes)) if faltantes else ""))
    print("  [i ] pa_cancelar_ocupacion (propuesto): {0}".format(
        "presente" if conexion.cancelacion_disponible else "no existe todavía"))

    descripcion = conexion.ejecutar(
        "SELECT descripcion FROM dbo.tipos_vehiculo WHERE codigo = 'COMPACTO'")[0]["descripcion"]
    todo_bien &= comprobar(descripcion == "Vehículo compacto",
                           "acentos correctos ('{0}')".format(descripcion))

    conexion.close()
    print("\nTodo listo." if todo_bien else "\nHay problemas: revisa las líneas marcadas con X.")
    return 0 if todo_bien else 1


if __name__ == "__main__":
    sys.exit(main())
