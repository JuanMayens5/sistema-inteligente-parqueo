"""
Prueba automática de la interfaz
================================

    python pruebas/prueba_interfaz.py              # modo demostración (memoria)
    python pruebas/prueba_interfaz.py --sqlserver  # base de pruebas de SQL Server

Abre la ventana real y la maneja por código (sin clics): recorre el ciclo
completo con el botón contextual, el escenario de alarma con el simulador de
sensores, la consola, todas las vistas de detalle, la pérdida y recuperación
de la conexión, etc. Los cuadros de diálogo se contestan solos con "Sí".

Los IDs UI-xx coinciden con el plan de integración (docs/PLAN_INTEGRACION_BASE_DATOS.md).
"""

import argparse
import sys
import traceback
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar los paquetes

from datos import cargar_configuracion, obtener_backend
from datos.contrato import ErrorConexion, fila_de_espacio
from interfaz.app import AppParqueo
from interfaz.vista_avanzada import VISTAS_DETALLE

BASE_PRUEBAS = "SistemaInteligenteParqueo_Pruebas"
resultados = []            # (caso, correcto, detalle)
errores_inesperados = []


def verificar(caso, condicion, detalle=""):
    resultados.append((caso, bool(condicion), detalle))
    print("  [{0}] {1} {2}".format("OK" if condicion else "FALLA", caso, "" if condicion else detalle))


def paso(app, descripcion, accion):
    """Ejecuta una acción y procesa los eventos pendientes de Tkinter; registra cualquier excepción."""
    try:
        accion()
        app.update()
    except Exception:
        errores_inesperados.append(descripcion + "\n" + traceback.format_exc())
        print("  [ERROR] " + descripcion)
        traceback.print_exc()


def preparar(usar_sqlserver):
    configuracion = cargar_configuracion()
    if usar_sqlserver:
        from herramientas.reiniciar_base import reiniciar_base
        configuracion = replace(configuracion, base_datos=BASE_PRUEBAS)
        reiniciar_base(configuracion, BASE_PRUEBAS)
        db = obtener_backend("sqlserver")
        return db, db.conectar_db(configuracion), configuracion
    db = obtener_backend("mock")
    return db, db.conectar_db(con_ejemplos=False), configuracion


def main():
    opciones = argparse.ArgumentParser()
    opciones.add_argument("--sqlserver", action="store_true")
    usar_sqlserver = opciones.parse_args().sqlserver

    # Los diálogos se contestan solos y los errores inesperados se anotan.
    messagebox.askyesno = lambda *a, **k: True
    messagebox.showerror = lambda titulo, texto, **k: errores_inesperados.append(titulo + ": " + texto)

    db, conexion, configuracion = preparar(usar_sqlserver)
    app = AppParqueo(db, conexion, configuracion)
    app.update()
    vista = app.vista_operacion
    boton = lambda: vista.boton_principal.cget("text")
    estado_de = lambda espacio: fila_de_espacio(app.estado_parqueo, espacio)
    print("\n=== Interfaz contra: {0} ===".format(conexion.descripcion))

    # --- UI-01: arranque ---------------------------------------------------------
    verificar("UI-01 arranque", len(app.estado_parqueo) == 9
              and app.chips["disponibles"][1].cget("text") == "9" and "Conectado" in app.indicador.cget("text"))

    # --- UI-02: ciclo completo con el botón contextual -------------------------
    vista.fijar_placa("P123ABC")
    vista.combo_tipo.set("COMPACTO")
    esperados = [("Registrar llegada", "ASIGNADA"), ("Autorizar salida", "OCUPADA"),
                 ("Registrar salida", "AUTORIZADA"), ("Asignar espacio", None)]
    textos, estados = [], []
    for _ in esperados:
        paso(app, "botón contextual", app.ejecutar_accion_contextual)
        textos.append(boton())
        estados.append(estado_de("C-01")["estado_ocupacion"])
    verificar("UI-02 ciclo con botón contextual",
              list(zip(textos, estados)) == esperados, list(zip(textos, estados)))

    # --- UI-03: vehículo de carga (antes "no asignable") -----------------------
    vista.fijar_placa("C700AAA")
    vista.combo_tipo.set("CARGA")
    paso(app, "registrar carga", app.ejecutar_accion_contextual)
    verificar("UI-03 vehículo de carga recibe CD-01", estado_de("CD-01")["placa_vehiculo"] == "C700AAA")

    # --- UI-04 y UI-08: escenario de alarma con el simulador de sensores -------
    vista.fijar_placa("P555AAA")
    vista.combo_tipo.set("COMPACTO")
    paso(app, "registrar P555AAA", app.ejecutar_accion_contextual)
    asignado_en_c01 = estado_de("C-01")["placa_vehiculo"] == "P555AAA"
    paso(app, "sensor ocupado", lambda: app.procesar_mensaje_esp32("ESP:ESPACIO:C-01:OCUPADO"))
    paso(app, "sensor PIR", lambda: app.procesar_mensaje_esp32("ESP:MOVIMIENTO:C-01"))
    registro = app.vista_avanzada.registro_esp32.get("1.0", "end")
    verificar("UI-04 alarma visible", asignado_en_c01 and app.chips["alarmas"][1].cget("text") == "1"
              and vista.aviso.winfo_manager() == "grid" and boton() == "Apagar alarma"
              and "PY:ALARMA:ON" in registro and "PY:LED:C-01:PARPADEO" in registro, boton())

    paso(app, "apagar desde el aviso", lambda: app.accion_apagar_alarma("P555AAA"))
    verificar("UI-04b apagar alarma", app.chips["alarmas"][1].cget("text") == "0"
              and vista.aviso.winfo_manager() == "" and boton() == "Autorizar salida", boton())

    paso(app, "salida sin autorizar", lambda: app.procesar_mensaje_esp32("ESP:ESPACIO:C-01:LIBRE"))
    salida_rechazada = estado_de("C-01")["alarma_activa"] == "SI"
    paso(app, "botón físico", lambda: app.procesar_mensaje_esp32("ESP:BOTON:SALIDA:C-01"))
    paso(app, "sensor libre", lambda: app.procesar_mensaje_esp32("ESP:ESPACIO:C-01:LIBRE"))
    paso(app, "mensaje inválido", lambda: app.procesar_mensaje_esp32("ESP:CUALQUIER:COSA"))
    verificar("UI-08 eventos del simulador", salida_rechazada and estado_de("C-01")["estado"] == "DISPONIBLE"
              and "PY:LED:C-01:VERDE" in app.vista_avanzada.registro_esp32.get("1.0", "end"))

    # --- UI-07: consola y bitácora -----------------------------------------------
    antes = len(db.listar_bitacora(conexion))
    comandos = ["AYUDA", "ESTADO", "CONSULTAR", "CONSULTAR OCUPADOS", "VEHICULOS", "ALARMAS",
                "REGISTRAR P777XXX MOTOCICLETA;", "ASIGNAR P777XXX", "LLEGADA P777XXX",
                "MOVIMIENTO M-01", "APAGAR_ALARMA P777XXX", "AUTORIZAR_SALIDA P777XXX", "SALIDA P777XXX",
                "BUSCAR P777XXX", "BUSCAR NADIE", "LIBERAR G-02", "TOKENS REGISTRAR P1 X", "BORRAR", "ASIGNAR #"]
    for comando in comandos:
        def ejecutar(texto=comando):
            app.vista_avanzada.entrada_comando.delete(0, "end")
            app.vista_avanzada.entrada_comando.insert(0, texto)
            app.vista_avanzada._ejecutar_comando()
        paso(app, "consola: " + comando, ejecutar)
    paso(app, "consola: LIMPIAR", lambda: (app.vista_avanzada.entrada_comando.insert(0, "LIMPIAR"),
                                          app.vista_avanzada._ejecutar_comando()))
    paso(app, "historial", lambda: app.vista_avanzada._navegar_historial(-1))
    verificar("UI-07 bitácora", len(db.listar_bitacora(conexion)) - antes == len(comandos))

    # --- Modo avanzado: todas las vistas de detalle -----------------------------
    paso(app, "modo avanzado", app.alternar_modo)
    for nombre in VISTAS_DETALLE:
        def elegir(nombre=nombre):
            app.vista_avanzada.combo_detalle.set(nombre)
            app.vista_avanzada.actualizar_detalle()
            filas = app.vista_avanzada.tabla.get_children()
            if filas:
                app.vista_avanzada.tabla.selection_set(filas[0])
        paso(app, "detalle: " + nombre, elegir)
    paso(app, "reenviar estado al ESP32", app.reenviar_estado_esp32)
    paso(app, "modo operación", app.alternar_modo)
    verificar("UI-09 vistas de detalle y modos", app.modo == "operacion")

    # --- Otras acciones del modo operación --------------------------------------
    paso(app, "seleccionar espacio", lambda: app.seleccionar_espacio("G-01"))
    paso(app, "buscar existente", lambda: (vista.fijar_placa("P123ABC"), app.accion_buscar()))
    paso(app, "buscar inexistente", lambda: (vista.fijar_placa("NOEXISTE"), app.accion_buscar()))
    paso(app, "placa vacía", lambda: (vista.fijar_placa(""), app.ejecutar_accion_contextual()))
    paso(app, "solo registrar", lambda: (vista.fijar_placa("P321CBA"), app.accion_registrar(asignar=False)))
    if vista.boton_liberar is not None:
        vista.fijar_placa("P321CBA")
        paso(app, "asignar para liberar", app.ejecutar_accion_contextual)
        paso(app, "seleccionar asignado", lambda: app.seleccionar_espacio(app.espacio_seleccionado))
        paso(app, "liberar espacio", app.accion_liberar)
        verificar("UI-10 liberar espacio", app.db.buscar_vehiculo(conexion, "P321CBA")["espacio"] is None)
    paso(app, "notificaciones", app.abrir_notificaciones)
    paso(app, "limpiar notificaciones", app.limpiar_notificaciones)
    paso(app, "limpiar campos", app.accion_limpiar)
    if hasattr(db, "reiniciar_datos_demo"):
        paso(app, "reiniciar demostración", app.accion_reiniciar_demo)

    # --- UI-05: cambios hechos desde otra conexión (solo SQL Server) -----------
    if usar_sqlserver:
        otra = db.conectar_db(configuracion)
        db.registrar_vehiculo(otra, "P888OTR", "GRANDE")
        db.asignar_espacio(otra, "P888OTR")
        otra.close()
        paso(app, "refresco periódico", app._refresco_periodico)
        verificar("UI-05 cambios de otra ventana", any(f["placa_vehiculo"] == "P888OTR" for f in app.estado_parqueo))

    # --- UI-06: pérdida y recuperación de la conexión ---------------------------
    if usar_sqlserver:
        app.conexion.close()                              # conexión cortada de verdad
    else:
        def conexion_caida(conexion):
            raise ErrorConexion("desconexión simulada")
        original = db.obtener_estado_parqueo
        db.obtener_estado_parqueo = conexion_caida
    app.after(0, app.refrescar)       # por after() para que pase por report_callback_exception
    app.update()
    desconectado = (not app.conectado and "Sin conexión" in app.indicador.cget("text")
                    and str(vista.boton_principal.cget("state")) == "disabled")
    if not usar_sqlserver:
        db.obtener_estado_parqueo = original
    paso(app, "reconexión", app._refresco_periodico)
    verificar("UI-06 pérdida y recuperación de conexión", desconectado and app.conectado
              and str(vista.boton_principal.cget("state")) == "normal")

    app.destroy()

    correctos = sum(1 for _, correcto, _ in resultados if correcto)
    print("\n=== Resumen: {0}/{1} verificaciones correctas, {2} errores inesperados ===".format(
        correctos, len(resultados), len(errores_inesperados)))
    for error in errores_inesperados:
        print("-" * 60 + "\n" + error)
    return 0 if correctos == len(resultados) and not errores_inesperados else 1


if __name__ == "__main__":
    sys.exit(main())
