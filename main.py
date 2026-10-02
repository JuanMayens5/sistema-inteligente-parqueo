"""
Sistema Inteligente de Parqueo — punto de entrada
=================================================

    python main.py

Flujo de arranque
-----------------
    1. Lee config_db.ini                       datos.cargar_configuracion()
    2. Elige el origen de datos                datos.obtener_backend()
         sqlserver -> datos/sqlserver.py (base real)
         mock      -> datos/memoria.py   (modo demostración)
    3. Abre la conexión                        db.conectar_db()
         si falla, ofrece abrir en modo demostración
    4. Crea la ventana y entra al ciclo de Tkinter   interfaz.app.AppParqueo

Estructura del proyecto: ver README.md.
"""

import tkinter as tk
from tkinter import messagebox

from datos import cargar_configuracion, obtener_backend
from datos.contrato import ErrorConexion
from interfaz.app import AppParqueo


def conectar(configuracion):
    """Devuelve (db, conexion). Si SQL Server no responde, pregunta si usar el modo demostración."""
    try:
        db = obtener_backend(configuracion.origen)
        return db, db.conectar_db(configuracion)
    except ErrorConexion as error:
        ventana = tk.Tk()
        ventana.withdraw()          # ventana oculta: solo sirve de "dueña" del cuadro de diálogo
        usar_demostracion = messagebox.askyesno(
            "No se pudo conectar a la base de datos",
            "{0}\n\nRevisa config_db.ini o ejecuta:\n    python herramientas/verificar_conexion.py\n\n"
            "¿Abrir la aplicación en modo demostración (datos en memoria)?".format(error))
        ventana.destroy()
        if not usar_demostracion:
            return None, None
        db = obtener_backend("mock")
        return db, db.conectar_db(configuracion)


def main():
    configuracion = cargar_configuracion()
    db, conexion = conectar(configuracion)
    if db is None:
        return
    AppParqueo(db, conexion, configuracion).mainloop()


if __name__ == "__main__":
    main()
