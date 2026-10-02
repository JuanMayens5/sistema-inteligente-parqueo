"""
Modo Avanzado
=============

Herramientas técnicas, separadas del modo Operación para no saturar al operador:

    Detalle               una sola tabla con un selector: vehículos en el parqueo,
                          catálogo de espacios, vehículos registrados, alarmas,
                          historial de ocupaciones, eventos de sensor y bitácora.
    Consola del lenguaje  escribe comandos (REGISTRAR, ASIGNAR...) que ejecuta
                          logica/interprete.py y quedan en la bitácora.
    Simulador de sensores dispara los mismos mensajes que mandará el ESP32 y muestra
                          los comandos PY:... que se le responderían.

Igual que la vista de operación, esta vista no habla con la base: le pide los
datos a AppParqueo (app.leer_datos, app.ejecutar_comando, app.procesar_mensaje_esp32).
"""

import tkinter as tk
from tkinter import ttk

from interfaz.componentes import (
    COLOR_CONSOLA_FONDO, COLOR_CONSOLA_TEXTO, FUENTE, FUENTE_MONO, ToolTip, configurar_columnas,
    crear_tabla, formatear,
)
from logica.eventos_hardware import PLANTILLAS_ESP32

# Cada vista de la pestaña Detalle:
#   nombre -> (de dónde salen las filas, columnas [(clave, título, ancho)], qué se abre al elegir una fila)
# "de dónde salen" es (función de datos, argumentos), o None para usar el estado ya leído del parqueo.
VISTAS_DETALLE = {
    "Vehículos en el parqueo": (
        ("listar_ocupaciones", {"solo_activas": True}),
        [("placa", "Placa", 100), ("tipo_vehiculo", "Tipo", 110), ("espacio", "Espacio", 70),
         ("estado", "Ocupación", 100), ("fecha_asignacion", "Asignado", 120),
         ("fecha_llegada", "Llegada", 120), ("fecha_autorizacion", "Autorizada", 120)],
        "placa"),
    "Catálogo de espacios": (
        None,
        [("espacio", "Espacio", 70), ("tipo", "Tipo", 130), ("sector", "Sector", 60),
         ("estado", "Estado", 120), ("led_estado", "LED", 80), ("placa_vehiculo", "Placa", 100),
         ("estado_ocupacion", "Ocupación", 100), ("alarma_activa", "Alarma", 60)],
        "espacio"),
    "Vehículos registrados": (
        ("listar_vehiculos", {}),
        [("placa", "Placa", 100), ("tipo_vehiculo", "Tipo", 110), ("fecha_registro", "Registrado", 130),
         ("espacio", "Espacio", 70), ("estado_ocupacion", "Ocupación", 100)],
        "placa"),
    "Alarmas activas": (
        ("listar_alarmas_activas", {}),
        [("espacio", "Espacio", 70), ("placa", "Placa", 100), ("tipo", "Tipo", 190),
         ("fecha_inicio", "Desde", 130), ("descripcion", "Descripción", 320)],
        "placa"),
    "Historial de ocupaciones": (
        ("listar_ocupaciones", {"solo_activas": False}),
        [("placa", "Placa", 100), ("espacio", "Espacio", 70), ("estado", "Estado", 100),
         ("fecha_asignacion", "Asignado", 120), ("fecha_llegada", "Llegada", 120),
         ("fecha_autorizacion", "Autorizada", 120), ("fecha_salida", "Salida", 120),
         ("autorizado_por", "Autorizó", 100)],
        "placa"),
    "Eventos de sensor": (
        ("listar_eventos_sensor", {}),
        [("fecha", "Fecha", 130), ("espacio", "Espacio", 70), ("tipo_sensor", "Sensor", 110),
         ("valor", "Detecta", 70)],
        "espacio"),
    "Bitácora de comandos": (
        ("listar_bitacora", {}),
        [("fecha", "Fecha", 130), ("texto_original", "Instrucción", 250),
         ("resultado", "Resultado", 140), ("mensaje", "Mensaje", 330), ("usuario", "Usuario", 90)],
        None),
}

BIENVENIDA_CONSOLA = ("Consola del lenguaje del proyecto (intérprete provisional).\n"
                      "Escribe AYUDA para ver los comandos o LIMPIAR para borrar la consola.\n"
                      "Flechas Arriba/Abajo: comandos anteriores. Cada instrucción queda en la bitácora.\n")

# Colores de las líneas de la consola y del registro del simulador.
COLORES_TERMINAL = {"comando": "#38bdf8", "ok": "#4ade80", "error": "#f87171", "aviso": "#fbbf24",
                    "info": "#cbd5e1", "entrada": "#38bdf8", "salida": "#c084fc"}

# Botones del simulador: (texto, evento del protocolo, explicación)
BOTONES_SIMULADOR = [
    ("🚗  Llegó un vehículo", "OCUPADO", "El sensor ultrasónico detecta un vehículo en el espacio."),
    ("↩  Se fue el vehículo", "LIBRE", "El sensor ultrasónico deja de detectar el vehículo."),
    ("👁  Movimiento (PIR)", "MOVIMIENTO", "El sensor de movimiento detecta actividad en el espacio."),
    ("🔘  Botón físico de salida", "BOTON_SALIDA", "El operador presiona el botón de autorización."),
]


class VistaAvanzada(ttk.Frame):

    def __init__(self, padre, app):
        super().__init__(padre)
        self.app = app
        self._filas_detalle = {}          # id de fila en la tabla -> diccionario de datos
        self._historial_comandos = []
        self._posicion_historial = 0

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        cuaderno = ttk.Notebook(self)
        cuaderno.grid(row=0, column=0, sticky="nsew")
        cuaderno.add(self._crear_pestana_detalle(cuaderno), text="Detalle")
        cuaderno.add(self._crear_pestana_consola(cuaderno), text="Consola del lenguaje")
        cuaderno.add(self._crear_pestana_simulador(cuaderno), text="Simulador de sensores")

    # =========================================================================
    #  Pestaña Detalle
    # =========================================================================

    def _crear_pestana_detalle(self, padre):
        pestana = ttk.Frame(padre, padding=10)
        pestana.columnconfigure(0, weight=1)
        pestana.rowconfigure(1, weight=1)

        selector = ttk.Frame(pestana)
        selector.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(selector, text="Mostrar:").pack(side="left", padx=(0, 6))
        self.combo_detalle = ttk.Combobox(selector, state="readonly", width=28,
                                          values=list(VISTAS_DETALLE))
        self.combo_detalle.pack(side="left")
        self.combo_detalle.current(0)
        self.combo_detalle.bind("<<ComboboxSelected>>", lambda evento: self.actualizar_detalle())
        ttk.Label(selector, text="Clic en una fila para ver su ficha.", style="Tenue.TLabel").pack(
            side="left", padx=12)

        _, columnas, _ = VISTAS_DETALLE[self.combo_detalle.get()]
        contenedor, self.tabla = crear_tabla(pestana, columnas)
        contenedor.grid(row=1, column=0, sticky="nsew")
        self.tabla.bind("<<TreeviewSelect>>", self._al_elegir_fila)
        return pestana

    def actualizar_detalle(self):
        """Vuelve a llenar la tabla con la vista elegida en el selector."""
        fuente, columnas, _ = VISTAS_DETALLE[self.combo_detalle.get()]
        filas = self.app.estado_parqueo if fuente is None else self.app.leer_datos(*fuente)

        configurar_columnas(self.tabla, columnas)
        self.tabla.delete(*self.tabla.get_children())
        self._filas_detalle = {}
        for indice, fila in enumerate(filas):
            identificador = str(indice)
            self._filas_detalle[identificador] = fila
            self.tabla.insert("", "end", iid=identificador,
                              values=[formatear(fila[clave]) for clave, _, _ in columnas],
                              tags=("par",) if indice % 2 else ())

    def _al_elegir_fila(self, evento=None):
        seleccion = self.tabla.selection()
        _, _, abre = VISTAS_DETALLE[self.combo_detalle.get()]
        if not seleccion or abre is None:
            return
        fila = self._filas_detalle[seleccion[0]]
        if abre == "espacio":
            self.app.seleccionar_espacio(fila["espacio"])
        else:
            self.app.mostrar_vehiculo(fila["placa"], llenar_formulario=True)

    # =========================================================================
    #  Pestaña Consola
    # =========================================================================

    def _crear_pestana_consola(self, padre):
        pestana = ttk.Frame(padre, padding=10)
        pestana.columnconfigure(0, weight=1)
        pestana.rowconfigure(0, weight=1)

        self.consola = self._crear_terminal(pestana)
        self.consola.master.grid(row=0, column=0, sticky="nsew")
        self.escribir_consola(BIENVENIDA_CONSOLA, "info")

        entrada = ttk.Frame(pestana)
        entrada.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        entrada.columnconfigure(1, weight=1)
        ttk.Label(entrada, text="›", font=(FUENTE_MONO, 12, "bold")).grid(row=0, column=0, padx=(2, 6))
        self.entrada_comando = ttk.Entry(entrada, font=(FUENTE_MONO, 10))
        self.entrada_comando.grid(row=0, column=1, sticky="ew")
        self.entrada_comando.bind("<Return>", lambda evento: self._ejecutar_comando())
        self.entrada_comando.bind("<Up>", lambda evento: self._navegar_historial(-1))
        self.entrada_comando.bind("<Down>", lambda evento: self._navegar_historial(1))
        ttk.Button(entrada, text="Ejecutar", style="Principal.TButton",
                   command=self._ejecutar_comando).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(entrada, text="Limpiar", command=self.limpiar_consola).grid(row=0, column=3, padx=(6, 0))
        return pestana

    def _ejecutar_comando(self):
        texto = self.entrada_comando.get().strip()
        if not texto:
            return
        self._historial_comandos.append(texto)
        self._posicion_historial = len(self._historial_comandos)
        self.entrada_comando.delete(0, "end")
        self.escribir_consola("› " + texto, "comando")

        if texto.upper().rstrip(";").strip() == "LIMPIAR":
            self.limpiar_consola()
            return
        nivel, mensaje = self.app.ejecutar_comando(texto)
        if mensaje:
            self.escribir_consola(mensaje, nivel)

    def _navegar_historial(self, paso):
        if self._historial_comandos:
            self._posicion_historial = max(0, min(len(self._historial_comandos),
                                                  self._posicion_historial + paso))
            texto = (self._historial_comandos[self._posicion_historial]
                     if self._posicion_historial < len(self._historial_comandos) else "")
            self.entrada_comando.delete(0, "end")
            self.entrada_comando.insert(0, texto)
        return "break"      # evita que Tkinter mueva el cursor

    def escribir_consola(self, texto, nivel):
        self._escribir_terminal(self.consola, texto, nivel)

    def limpiar_consola(self):
        self.consola.config(state="normal")
        self.consola.delete("1.0", "end")
        self.consola.config(state="disabled")
        self.escribir_consola(BIENVENIDA_CONSOLA, "info")

    # =========================================================================
    #  Pestaña Simulador de sensores
    # =========================================================================

    def _crear_pestana_simulador(self, padre):
        pestana = ttk.Frame(padre, padding=10)
        pestana.columnconfigure(1, weight=1)
        pestana.rowconfigure(1, weight=1)

        ttk.Label(pestana, style="Tenue.TLabel", wraplength=900, justify="left",
                  text="Simula lo que enviará el ESP32. Cada evento pasa por el mismo código que usará "
                       "el hardware real (logica/eventos_hardware.py) y ejecuta los procedimientos de la base. "
                       "A la derecha se ven los mensajes recibidos (→) y los comandos que se le "
                       "responderían al ESP32 (←)."
                  ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        controles = ttk.Frame(pestana)
        controles.grid(row=1, column=0, sticky="n", padx=(0, 12))
        ttk.Label(controles, text="Espacio").pack(anchor="w")
        self.combo_espacio = ttk.Combobox(controles, state="readonly", width=12)
        self.combo_espacio.pack(anchor="w", pady=(2, 10))

        for texto, evento, explicacion in BOTONES_SIMULADOR:
            boton = ttk.Button(controles, text=texto, width=28,
                               command=lambda e=evento: self._simular(e))
            boton.pack(fill="x", pady=2)
            ToolTip(boton, "{0}\nMensaje: {1}".format(explicacion, PLANTILLAS_ESP32[evento].format("C-01")))

        ttk.Separator(controles).pack(fill="x", pady=10)
        ttk.Label(controles, text="Mensaje del ESP32 escrito a mano").pack(anchor="w")
        self.entrada_esp32 = ttk.Entry(controles, font=(FUENTE_MONO, 9), width=30)
        self.entrada_esp32.pack(fill="x", pady=(2, 2))
        self.entrada_esp32.insert(0, "ESP:HEARTBEAT")
        self.entrada_esp32.bind("<Return>", lambda evento: self._enviar_mensaje_escrito())
        ttk.Button(controles, text="Enviar mensaje", command=self._enviar_mensaje_escrito).pack(fill="x")

        ttk.Separator(controles).pack(fill="x", pady=10)
        reenviar = ttk.Button(controles, text="Reenviar estado completo al ESP32",
                              command=self.app.reenviar_estado_esp32)
        reenviar.pack(fill="x")
        ToolTip(reenviar, "Lo que haría la aplicación si el ESP32 se reinicia: vuelve a mandar "
                          "el color de todos los LEDs y el estado de la alarma.")

        self.registro_esp32 = self._crear_terminal(pestana)
        self.registro_esp32.master.grid(row=1, column=1, sticky="nsew")
        return pestana

    def fijar_espacios(self, codigos):
        """Lista de espacios del simulador (se actualiza con el estado del parqueo)."""
        actual = self.combo_espacio.get()
        self.combo_espacio.config(values=codigos)
        if actual not in codigos and codigos:
            self.combo_espacio.current(0)

    def _simular(self, evento):
        self.app.procesar_mensaje_esp32(PLANTILLAS_ESP32[evento].format(self.combo_espacio.get()))

    def _enviar_mensaje_escrito(self):
        if self.entrada_esp32.get().strip():
            self.app.procesar_mensaje_esp32(self.entrada_esp32.get())

    def registrar_trafico(self, texto, nivel):
        """Agrega una línea al registro del simulador (nivel: entrada, salida, ok, error...)."""
        self._escribir_terminal(self.registro_esp32, texto, nivel)

    # =========================================================================
    #  Terminal de texto (compartida por la consola y el simulador)
    # =========================================================================

    def _crear_terminal(self, padre):
        """Caja de texto oscura de solo lectura con scroll. Devuelve el widget Text."""
        marco = ttk.Frame(padre)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)
        texto = tk.Text(marco, bg=COLOR_CONSOLA_FONDO, fg=COLOR_CONSOLA_TEXTO, font=(FUENTE_MONO, 9),
                        relief="flat", padx=10, pady=8, wrap="none", state="disabled")
        texto.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(marco, orient="vertical", command=texto.yview)
        barra.grid(row=0, column=1, sticky="ns")
        texto.configure(yscrollcommand=barra.set)
        for nivel, color in COLORES_TERMINAL.items():
            texto.tag_configure(nivel, foreground=color)
        texto.tag_configure("comando", font=(FUENTE_MONO, 9, "bold"))
        return texto

    @staticmethod
    def _escribir_terminal(texto, contenido, nivel):
        texto.config(state="normal")
        texto.insert("end", contenido.rstrip("\n") + "\n", nivel)
        texto.see("end")
        texto.config(state="disabled")
