"""
Pruebas del backend: capa de datos, consola y eventos de hardware
=================================================================

    python pruebas/prueba_backend.py                 # SQL Server (base de pruebas) y memoria
    python pruebas/prueba_backend.py --solo-memoria  # sin SQL Server

Corre LOS MISMOS casos contra los dos orígenes de datos. Si ambos pasan, el
modo demostración se comporta igual que la base real (prueba de paridad).

SQL Server se prueba en una base SEPARADA (SistemaInteligenteParqueo_Pruebas),
que se crea y se reinicia desde database.sql antes de cada grupo de casos.
La base de desarrollo nunca se toca.

Grupos de casos (los IDs coinciden con el plan de integración)
--------------------------------------------------------------
    BD-01..BD-23  procedimientos almacenados, uno por uno
    CO-01..CO-07  consola: ejecución y clasificación en la bitácora
    EV-01..EV-07  eventos de sensores y comandos para el ESP32
    CA-01..CA-02  liberación manual (solo si existe pa_cancelar_ocupacion)
"""

import argparse
import sys
import threading
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar los paquetes

from datos import cargar_configuracion, obtener_backend
from datos.contrato import fila_de_espacio
from logica import eventos_hardware, interprete

BASE_PRUEBAS = "SistemaInteligenteParqueo_Pruebas"
OPERADOR = "PRUEBAS"


class Probador:
    """Lleva la cuenta de los casos de un origen de datos y da atajos para verificar."""

    def __init__(self, nombre, db, abrir_base_limpia, abrir_conexion_extra=None):
        self.nombre = nombre
        self.db = db
        self._abrir_base_limpia = abrir_base_limpia        # reinicia la base y devuelve una conexión
        self._abrir_conexion_extra = abrir_conexion_extra  # otra conexión a la misma base (o None)
        self.conexion = None
        self.total = 0
        self.fallos = []

    def base_limpia(self):
        if self.conexion is not None:
            self.conexion.close()
        self.conexion = self._abrir_base_limpia()
        return self.conexion

    def verificar(self, caso, condicion, detalle=""):
        self.total += 1
        if not condicion:
            self.fallos.append("{0} {1}".format(caso, detalle))
        print("  [{0}] {1} {2}".format("OK" if condicion else "FALLA", caso,
                                       "" if condicion else detalle))

    def espacio(self, codigo):
        return fila_de_espacio(self.db.obtener_estado_parqueo(self.conexion), codigo)

    def ficha(self, placa):
        return self.db.buscar_vehiculo(self.conexion, placa)


# =============================================================================
#  BD: procedimientos almacenados
# =============================================================================

def casos_ciclo_completo(p):
    """BD-01..BD-18, BD-21 y BD-23 en orden sobre una base limpia."""
    db, c = p.db, p.base_limpia()

    r = db.registrar_vehiculo(c, "P123ABC", "COMPACTO")
    p.verificar("BD-01 registrar", r.codigo == "OK", r)
    r = db.registrar_vehiculo(c, "p123abc ", "COMPACTO")
    p.verificar("BD-02 registrar repetido", r.codigo == "YA_REGISTRADO", r)
    r = db.registrar_vehiculo(c, "P999XXX", "CAMION")
    p.verificar("BD-03 tipo inválido", r.codigo == "TIPO_INVALIDO", r)

    r = db.asignar_espacio(c, "P123ABC")
    fila = p.espacio("C-01")
    p.verificar("BD-04 asignar", r == ("OK", r.mensaje, "C-01") and fila["estado"] == "ASIGNADO"
                and fila["led_estado"] == "AMARILLO", (r, fila))
    r = db.asignar_espacio(c, "P123ABC")
    p.verificar("BD-05 asignar repetido", r.codigo == "YA_TIENE_ESPACIO", r)
    r = db.asignar_espacio(c, "P000NOP")
    p.verificar("BD-06 asignar no registrado", r.codigo == "VEHICULO_NO_ENCONTRADO", r)
    r = db.autorizar_salida(c, "P123ABC", OPERADOR)
    p.verificar("BD-07 autorizar sin llegada", r.codigo == "SIN_OCUPACION", r)

    r = db.registrar_llegada(c, "P123ABC")
    fila, ficha = p.espacio("C-01"), p.ficha("P123ABC")
    evento = db.listar_eventos_sensor(c, 1)[0]
    p.verificar("BD-08 llegada", r.codigo == "OK" and fila["estado"] == "OCUPADO"
                and fila["led_estado"] == "ROJO" and ficha["seguridad_activa"]
                and (evento["espacio"], evento["tipo_sensor"], bool(evento["valor"])) == ("C-01", "OCUPACION", True),
                (r, fila, ficha, evento))
    r = db.registrar_llegada(c, "P123ABC")
    p.verificar("BD-09 llegada repetida", r.codigo == "SIN_ASIGNACION", r)

    r = db.registrar_movimiento(c, "C-01")
    alarmas = db.listar_alarmas_activas(c)
    p.verificar("BD-10 movimiento -> alarma", r.codigo == "ALARMA_ACTIVADA" and r.dato == "P123ABC"
                and p.espacio("C-01")["led_estado"] == "PARPADEO"
                and [(a["espacio"], a["placa"]) for a in alarmas] == [("C-01", "P123ABC")], (r, alarmas))
    r = db.registrar_movimiento(c, "C-01")
    p.verificar("BD-11 movimiento con alarma activa", r.codigo == "ALARMA_YA_ACTIVA", r)

    r = db.apagar_alarma(c, "P123ABC", OPERADOR)
    p.verificar("BD-12 apagar alarma", r.codigo == "OK" and p.espacio("C-01")["led_estado"] == "ROJO"
                and p.ficha("P123ABC")["seguridad_activa"], r)
    r = db.apagar_alarma(c, "P123ABC", OPERADOR)
    p.verificar("BD-13 apagar sin alarma", r.codigo == "SIN_ALARMA", r)

    r = db.registrar_salida(c, "P123ABC")
    alarmas = db.listar_alarmas_activas(c)
    p.verificar("BD-14 salida sin autorizar", r.codigo == "SALIDA_NO_AUTORIZADA" and r.dato == "C-01"
                and [a["tipo"] for a in alarmas] == ["SALIDA_NO_AUTORIZADA"], (r, alarmas))

    r = db.autorizar_salida(c, "P123ABC", OPERADOR)
    ficha = p.ficha("P123ABC")
    p.verificar("BD-15 autorizar", r.codigo == "OK" and not db.listar_alarmas_activas(c)
                and p.espacio("C-01")["led_estado"] == "AMARILLO" and not ficha["seguridad_activa"]
                and ficha["autorizado_por"] == OPERADOR, (r, ficha))
    r = db.registrar_movimiento(c, "C-01")
    p.verificar("BD-16 movimiento ya autorizado", r.codigo == "MOVIMIENTO_AUTORIZADO"
                and not db.listar_alarmas_activas(c), r)

    r = db.registrar_salida(c, "P123ABC")
    fila = p.espacio("C-01")
    historial = db.listar_ocupaciones(c, solo_activas=False)
    p.verificar("BD-17 salida", r.codigo == "OK" and fila["estado"] == "DISPONIBLE"
                and fila["led_estado"] == "VERDE" and historial[0]["estado"] == "FINALIZADA",
                (r, fila, historial[:1]))
    r = db.asignar_espacio(c, "P123ABC")
    p.verificar("BD-18 volver a asignar", r.codigo == "OK" and r.dato == "C-01", r)

    for placa in ("C100AAA", "C200AAA"):
        db.registrar_vehiculo(c, placa, "CARGA")
    primero, segundo = db.asignar_espacio(c, "C100AAA"), db.asignar_espacio(c, "C200AAA")
    p.verificar("BD-21 segundo vehículo de carga", primero.dato == "CD-01"
                and segundo.codigo == "SIN_ESPACIO", (primero, segundo))

    r = db.registrar_movimiento(c, "Z-99")
    p.verificar("BD-23 espacio inexistente", r.codigo == "ESPACIO_NO_ENCONTRADO", r)


def casos_compatibilidad(p):
    """BD-19 y BD-20: cuando se acaba el tipo ideal, se usa la alternativa de la tabla compatibilidad."""
    for caso, tipo, esperado in [("BD-19 cuarto compacto", "COMPACTO", ["C-01", "C-02", "C-03", "G-01"]),
                                 ("BD-20 tercera moto", "MOTOCICLETA", ["M-01", "M-02", "C-01"])]:
        db, c = p.db, p.base_limpia()
        obtenidos = []
        for numero in range(len(esperado)):
            placa = "{0}{1:03d}ABC".format(tipo[0], numero)
            db.registrar_vehiculo(c, placa, tipo)
            obtenidos.append(db.asignar_espacio(c, placa).dato)
        p.verificar(caso, obtenidos == esperado, obtenidos)


def caso_concurrencia(p):
    """BD-22: dos conexiones asignan al mismo tiempo; el UPDLOCK evita que tomen el mismo espacio."""
    if p._abrir_conexion_extra is None:
        print("  [--] BD-22 concurrencia: no aplica (solo SQL Server)")
        return
    db, c = p.db, p.base_limpia()
    placas = ["P701AAA", "P702AAA"]
    for placa in placas:
        db.registrar_vehiculo(c, placa, "COMPACTO")

    conexiones = [p._abrir_conexion_extra() for _ in placas]
    barrera = threading.Barrier(len(placas))
    resultados = [None] * len(placas)

    def asignar(indice):
        barrera.wait()                  # los dos hilos arrancan a la vez
        resultados[indice] = db.asignar_espacio(conexiones[indice], placas[indice])

    hilos = [threading.Thread(target=asignar, args=(i,)) for i in range(len(placas))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    for conexion in conexiones:
        conexion.close()
    espacios = [r.dato for r in resultados]
    p.verificar("BD-22 concurrencia", all(r.codigo == "OK" for r in resultados)
                and len(set(espacios)) == 2, resultados)


# =============================================================================
#  CO: consola y bitácora
# =============================================================================

def casos_consola(p):
    db, c = p.db, p.base_limpia()

    def ejecutar(texto):
        nivel, _ = interprete.ejecutar(texto, db, c, OPERADOR)
        return nivel, db.listar_bitacora(c, 1)[0]["resultado"]

    p.verificar("CO-01 comando válido", ejecutar("REGISTRAR P900AAA COMPACTO;") == ("ok", "OK"))
    p.verificar("CO-02 faltan argumentos", ejecutar("ASIGNAR")[1] == "ERROR_SINTACTICO")
    p.verificar("CO-03 carácter inválido", ejecutar("REGISTRAR P900AAA #")[1] == "ERROR_LEXICO")
    p.verificar("CO-04 rechazado por la base", ejecutar("ASIGNAR P999ZZZ")[1] == "ERROR_SEMANTICO")
    p.verificar("CO-05 comando desconocido", ejecutar("BORRAR TODO")[1] == "ERROR_SINTACTICO")
    p.verificar("CO-06 movimiento sin alarma", ejecutar("MOVIMIENTO C-01")[1] == "OK")
    p.verificar("CO-07 consultas", all(ejecutar(t)[1] == "OK"
                                       for t in ("ESTADO", "CONSULTAR OCUPADOS", "VEHICULOS",
                                                 "ALARMAS", "BUSCAR P900AAA", "TOKENS ASIGNAR P1")))


# =============================================================================
#  EV: eventos de sensores (simulador / ESP32)
# =============================================================================

def casos_eventos(p):
    db, c = p.db, p.base_limpia()

    formato_ok = eventos_hardware.interpretar_mensaje("esp:espacio:c-01:ocupado") == ("OCUPADO", "C-01")
    try:
        eventos_hardware.interpretar_mensaje("ESP:NADA")
        rechaza_invalido = False
    except ValueError:
        rechaza_invalido = True
    p.verificar("EV-01 protocolo", formato_ok and rechaza_invalido)

    def evento(nombre, espacio):
        return eventos_hardware.procesar_evento(db, c, nombre, espacio)

    sincronizador = eventos_hardware.SincronizadorEsp32()
    inicial = sincronizador.comandos_pendientes(db.obtener_estado_parqueo(c))
    db.registrar_vehiculo(c, "P800AAA", "COMPACTO")
    db.asignar_espacio(c, "P800AAA")
    cambios = sincronizador.comandos_pendientes(db.obtener_estado_parqueo(c))
    sin_cambios = sincronizador.comandos_pendientes(db.obtener_estado_parqueo(c))
    p.verificar("EV-02 sincronización de LEDs", len(inicial) == 10 and inicial[-1] == "PY:ALARMA:OFF"
                and cambios == ["PY:LED:C-01:AMARILLO"] and sin_cambios == [], (inicial, cambios))

    r = evento("OCUPADO", "C-01")
    p.verificar("EV-03 sensor ocupado -> llegada", r.codigo == "OK"
                and p.espacio("C-01")["estado_ocupacion"] == "OCUPADA", r)
    r = evento("MOVIMIENTO", "C-01")
    comandos = sincronizador.comandos_pendientes(db.obtener_estado_parqueo(c))
    p.verificar("EV-04 PIR -> alarma", r.codigo == "ALARMA_ACTIVADA"
                and comandos == ["PY:LED:C-01:PARPADEO", "PY:ALARMA:ON"], (r, comandos))
    r = evento("BOTON_SALIDA", "C-01")
    p.verificar("EV-05 botón -> autorizar", r.codigo == "OK"
                and p.ficha("P800AAA")["autorizado_por"] == eventos_hardware.OPERADOR_BOTON_FISICO, r)
    r = evento("LIBRE", "C-01")
    p.verificar("EV-06 sensor libre -> salida", r.codigo == "OK"
                and p.espacio("C-01")["estado"] == "DISPONIBLE", r)
    r = evento("OCUPADO", "C-02")
    p.verificar("EV-07 ocupación no esperada", r.codigo == "OCUPACION_NO_ESPERADA", r)


# =============================================================================
#  CA: liberación manual (pa_cancelar_ocupacion, propuesto)
# =============================================================================

def casos_cancelacion(p):
    db, c = p.db, p.base_limpia()
    if not db.soporta_cancelacion(c):
        r = db.cancelar_ocupacion(c, "C-01", OPERADOR)
        p.verificar("CA-00 sin procedimiento", r.codigo == "CANCELACION_NO_DISPONIBLE", r)
        return
    db.registrar_vehiculo(c, "P600AAA", "COMPACTO")
    db.asignar_espacio(c, "P600AAA")
    r = db.cancelar_ocupacion(c, "C-01", OPERADOR)
    p.verificar("CA-01 cancelar", r.codigo == "OK" and r.dato == "P600AAA"
                and p.espacio("C-01")["estado"] == "DISPONIBLE"
                and db.listar_ocupaciones(c, solo_activas=False)[0]["estado"] == "CANCELADA", r)
    r = db.cancelar_ocupacion(c, "C-01", OPERADOR)
    p.verificar("CA-02 cancelar espacio libre", r.codigo == "ESPACIO_YA_LIBRE", r)


# =============================================================================
#  Ejecución
# =============================================================================

GRUPOS = [casos_ciclo_completo, casos_compatibilidad, caso_concurrencia,
          casos_consola, casos_eventos, casos_cancelacion]


def probador_memoria():
    memoria = obtener_backend("mock")
    return Probador("memoria (modo demostración)", memoria,
                    lambda: memoria.conectar_db(con_ejemplos=False))


def probador_sqlserver():
    from herramientas.reiniciar_base import reiniciar_base
    sqlserver = obtener_backend("sqlserver")
    config = replace(cargar_configuracion(), base_datos=BASE_PRUEBAS)

    def abrir_base_limpia():
        reiniciar_base(config, BASE_PRUEBAS)
        return sqlserver.conectar_db(config)

    return Probador("SQL Server ({0})".format(BASE_PRUEBAS), sqlserver, abrir_base_limpia,
                    lambda: sqlserver.conectar_db(config))


def main():
    opciones = argparse.ArgumentParser()
    opciones.add_argument("--solo-memoria", action="store_true")
    solo_memoria = opciones.parse_args().solo_memoria

    probadores = [probador_memoria()] + ([] if solo_memoria else [probador_sqlserver()])
    for probador in probadores:
        print("\n=== {0} ===".format(probador.nombre))
        for grupo in GRUPOS:
            grupo(probador)
        if probador.conexion is not None:
            probador.conexion.close()

    print("\n=== Resumen ===")
    for probador in probadores:
        print("  {0}: {1}/{2} casos correctos".format(
            probador.nombre, probador.total - len(probador.fallos), probador.total))
        for fallo in probador.fallos:
            print("     FALLA", fallo)
    return 1 if any(probador.fallos for probador in probadores) else 0


if __name__ == "__main__":
    sys.exit(main())
