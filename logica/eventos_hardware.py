"""
Eventos de hardware (simulador hoy, ESP32 después)
==================================================

Este módulo es el "puente" entre los sensores y la base de datos. Hoy lo usa
el Simulador de sensores de la interfaz; cuando exista hardware_serial.py,
el puerto serial le mandará exactamente los mismos mensajes.

Dos responsabilidades
---------------------
1. ESP32 -> base:  procesar_evento() decide qué procedimiento llamar según
   el sensor y el estado actual del espacio.

       Mensaje del ESP32              Estado del espacio   Procedimiento
       ESP:ESPACIO:C-01:OCUPADO       ASIGNADA             pa_llegada
       ESP:ESPACIO:C-01:LIBRE         OCUPADA/AUTORIZADA   pa_salida
       ESP:MOVIMIENTO:C-01            (cualquiera)         pa_registrar_movimiento
       ESP:BOTON:SALIDA:C-01          OCUPADA              pa_autorizar_salida
       ESP:HEARTBEAT                  -                    (solo confirma conexión)

2. base -> ESP32:  SincronizadorEsp32 calcula los comandos PY:... para que los
   LEDs y la alarma física coincidan con la base. La base es la ÚNICA fuente
   de verdad: se compara el estado nuevo con lo último enviado y solo se
   mandan las diferencias.

       PY:LED:C-01:ROJO      (VERDE, AMARILLO, ROJO, PARPADEO, APAGADO)
       PY:ALARMA:ON / OFF    (buzzer + LED de alarma)

Los sensores detectan PRESENCIA, no placas: por eso la placa se busca en el
estado del parqueo según el espacio donde ocurrió el evento.
"""

from datos.contrato import ASIGNADA, AUTORIZADA, OCUPADA, Resultado, fila_de_espacio

OPERADOR_BOTON_FISICO = "BOTON_FISICO"   # se guarda en ocupaciones.autorizado_por

# Plantillas para construir los mensajes del ESP32 (las usa el simulador).
PLANTILLAS_ESP32 = {
    "OCUPADO": "ESP:ESPACIO:{0}:OCUPADO",
    "LIBRE": "ESP:ESPACIO:{0}:LIBRE",
    "MOVIMIENTO": "ESP:MOVIMIENTO:{0}",
    "BOTON_SALIDA": "ESP:BOTON:SALIDA:{0}",
}


def interpretar_mensaje(linea):
    """Convierte un mensaje del ESP32 en (evento, espacio).

    Ejemplo: "ESP:ESPACIO:C-01:OCUPADO" -> ("OCUPADO", "C-01")
    Lanza ValueError si el mensaje no sigue el protocolo.
    """
    partes = [parte.strip().upper() for parte in linea.strip().split(":")]
    if partes[0] != "ESP":
        raise ValueError("El mensaje debe empezar con 'ESP:'.")

    match partes[1:]:
        case ["ESPACIO", espacio, "OCUPADO"]:
            return "OCUPADO", espacio
        case ["ESPACIO", espacio, "LIBRE"]:
            return "LIBRE", espacio
        case ["MOVIMIENTO", espacio]:
            return "MOVIMIENTO", espacio
        case ["BOTON", "SALIDA", espacio]:
            return "BOTON_SALIDA", espacio
        case ["HEARTBEAT"]:
            return "HEARTBEAT", None
    raise ValueError("Mensaje no reconocido por el protocolo: " + linea.strip())


def procesar_evento(db, conexion, evento, espacio):
    """Ejecuta en la base lo que corresponde a un evento de sensor. Devuelve un Resultado."""
    if evento == "HEARTBEAT":
        return Resultado("OK", "El ESP32 sigue conectado.", None)
    if evento == "MOVIMIENTO":
        return db.registrar_movimiento(conexion, espacio)

    fila = fila_de_espacio(db.obtener_estado_parqueo(conexion), espacio)
    if fila is None:
        return Resultado("ESPACIO_NO_ENCONTRADO", "El código de espacio no existe.", None)
    placa, estado = fila["placa_vehiculo"], fila["estado_ocupacion"]

    if evento == "OCUPADO":
        if estado == ASIGNADA:
            return db.registrar_llegada(conexion, placa)
        if estado in (OCUPADA, AUTORIZADA):
            return Resultado("SIN_CAMBIOS", "{0} ya estaba ocupado por {1}.".format(espacio, placa), placa)
        # Pendiente en la base: pa_evento_ocupacion con alarma SENSOR_INCONSISTENTE.
        return Resultado("OCUPACION_NO_ESPERADA",
                         "El sensor detectó un vehículo en {0}, pero no hay ninguno asignado.".format(espacio),
                         None)

    if evento == "LIBRE":
        if estado in (OCUPADA, AUTORIZADA):
            return db.registrar_salida(conexion, placa)
        return Resultado("SIN_CAMBIOS", "{0} no tenía un vehículo dentro.".format(espacio), placa)

    if evento == "BOTON_SALIDA":
        if estado == OCUPADA:
            return db.autorizar_salida(conexion, placa, OPERADOR_BOTON_FISICO)
        return Resultado("SIN_OCUPACION",
                         "No hay un vehículo esperando autorización en {0}.".format(espacio), placa)

    raise ValueError("Evento desconocido: " + evento)


class SincronizadorEsp32:
    """Calcula qué comandos hay que mandar al ESP32 para que coincida con la base."""

    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        """Olvida lo enviado: la próxima vez se manda todo (por ejemplo, si el ESP32 se reinició)."""
        self._leds_enviados = {}
        self._alarma_enviada = None

    def comandos_pendientes(self, estado_parqueo):
        """Devuelve los comandos PY:... necesarios según el estado actual del parqueo."""
        comandos = []
        for fila in estado_parqueo:
            if self._leds_enviados.get(fila["espacio"]) != fila["led_estado"]:
                comandos.append("PY:LED:{0}:{1}".format(fila["espacio"], fila["led_estado"]))
                self._leds_enviados[fila["espacio"]] = fila["led_estado"]

        hay_alarma = any(fila["alarma_activa"] == "SI" for fila in estado_parqueo)
        if hay_alarma != self._alarma_enviada:
            comandos.append("PY:ALARMA:ON" if hay_alarma else "PY:ALARMA:OFF")
            self._alarma_enviada = hay_alarma
        return comandos
