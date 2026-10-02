"""
Ventana principal y controlador de la aplicación
================================================

AppParqueo es el centro de la interfaz. Es el ÚNICO lugar que habla con la
base de datos (a través de `self.db`, que es datos.sqlserver o datos.memoria).

    ┌──────────────── AppParqueo (esta clase) ────────────────┐
    │  encabezado: indicadores · modo · notificaciones         │
    │  ┌ VistaOperacion ┐ ┌ VistaAvanzada ┐  (una a la vez)     │
    │  PanelInformacion (flota encima de las dos)              │
    │  indicador de conexión                                   │
    └──────────────────────────────────────────────────────────┘

Flujo de una acción (ej. clic en "Registrar llegada")
-----------------------------------------------------
    VistaOperacion ──► app.accion_llegada()
                        ├─► db.registrar_llegada(conexion, placa)   # procedimiento pa_llegada
                        ├─► notificar(...)                          # texto de logica/mensajes.py
                        └─► refrescar()
                             ├─► db.obtener_estado_parqueo()        # UNA consulta por refresco
                             └─► reparte esa copia a: encabezado, mapa, aviso de alarma,
                                 botón contextual, panel, detalle y comandos del ESP32

Refresco periódico
------------------
Cada `refresco_ms` (config_db.ini) se vuelve a leer el estado, para ver lo que
cambió desde otra ventana, la consola o el hardware. El mapa solo se redibuja
si algo cambió, para que no parpadee.

Errores de conexión
-------------------
Ninguna acción tiene try/except propio: si se pierde la conexión, la capa de
datos lanza ErrorConexion, Tkinter la entrega a report_callback_exception() y
ahí se pasa al estado "sin conexión" (controles deshabilitados). El refresco
periódico intenta reconectar solo.
"""

import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, ttk

from datos.contrato import (
    ASIGNADA, AUTORIZADA, LONGITUD_MAXIMA_PLACA, OCUPADA, ErrorConexion, fila_de_espacio,
    fila_de_placa, resumir,
)
from interfaz.componentes import (
    COLOR_CHIP, COLOR_ENCABEZADO, COLOR_FONDO, COLOR_PELIGRO, COLOR_SUAVE, FUENTE,
    ORDEN_TIPOS_VEHICULO, PanelInformacion, ToolTip, VentanaNotificaciones, configurar_estilos,
    ordenar_segun,
)
from interfaz.vista_avanzada import VistaAvanzada
from interfaz.vista_operacion import VistaOperacion
from logica import eventos_hardware, interprete, mensajes

MILISEGUNDOS_ESPERA_PLACA = 300     # espera tras la última tecla antes de consultar la placa


class AppParqueo(tk.Tk):

    def __init__(self, db, conexion, configuracion):
        super().__init__()
        self.db = db                    # módulo de datos (sqlserver o memoria)
        self.conexion = conexion
        # datos.Configuracion (config_db.ini). No se llama "config" porque
        # Tkinter ya usa ese nombre para un método de la ventana.
        self.configuracion = configuracion

        self.estado_parqueo = []        # última lectura de pa_consultar: una fila por espacio
        self.espacio_seleccionado = None
        self.conectado = True
        self.modo = "operacion"
        self.notificaciones = []        # [(hora, nivel, texto)] más reciente primero
        self.ventana_notificaciones = None
        self.sincronizador = eventos_hardware.SincronizadorEsp32()
        self._accion_contextual = None  # función que ejecuta el botón azul
        self._contenido_panel = None    # ("espacio", "C-01") o ("vehiculo", "P123ABC")
        self._espacios_en_alarma = set()
        self._aviso_capacidad = None
        self._espera_placa = None

        self.title("Sistema Inteligente de Parqueo")
        self.configure(bg=COLOR_FONDO)
        self.geometry("{0}x{1}".format(min(1220, self.winfo_screenwidth() - 80),
                                       min(820, self.winfo_screenheight() - 100)))
        self.minsize(960, 620)
        self.protocol("WM_DELETE_WINDOW", self.al_cerrar)
        configurar_estilos(self)

        self._construir_encabezado()
        self._construir_cuerpo()
        self._construir_indicador_conexion()

        self.refrescar(forzar=True)
        self.notificar("info", "Aplicación iniciada · " + self.conexion.descripcion)
        self.vista_operacion.enfocar_placa()
        self.after(self.configuracion.refresco_ms, self._refresco_periodico)

    # =========================================================================
    #  Construcción de la ventana
    # =========================================================================

    def _construir_encabezado(self):
        cabecera = tk.Frame(self, bg=COLOR_ENCABEZADO, height=82)
        cabecera.pack(fill="x")
        cabecera.pack_propagate(False)

        titulos = tk.Frame(cabecera, bg=COLOR_ENCABEZADO)
        titulos.pack(side="left", padx=20)
        tk.Label(titulos, text="Sistema Inteligente de Parqueo", bg=COLOR_ENCABEZADO, fg="white",
                 font=(FUENTE, 17, "bold")).pack(anchor="w", pady=(16, 0))
        modo_datos = ("Modo demostración · datos en memoria" if self._es_demostracion()
                      else "Operación en tiempo real · SQL Server")
        tk.Label(titulos, text=modo_datos, bg=COLOR_ENCABEZADO, fg="#94a3b8",
                 font=(FUENTE, 9)).pack(anchor="w")

        # pack(side="right") coloca de derecha a izquierda: la lista va al revés.
        self.chips = {}
        for clave, etiqueta, ayuda in [
            ("alarmas", "Alarmas", "Alarmas de seguridad activas."),
            ("ocupados", "Ocupados", "Espacios con un vehículo dentro (incluye los que están saliendo)."),
            ("asignados", "Asignados", "Espacios reservados esperando a que llegue el vehículo."),
            ("disponibles", "Disponibles", "Espacios libres."),
        ]:
            self.chips[clave] = self._crear_chip(cabecera, etiqueta, ayuda)

        boton = tk.Button(cabecera, text="🔔", bg=COLOR_ENCABEZADO, fg="#94a3b8", bd=0,
                          activebackground=COLOR_ENCABEZADO, activeforeground="white",
                          font=(FUENTE, 13), cursor="hand2", command=self.abrir_notificaciones)
        boton.pack(side="right", padx=(6, 4), pady=14)
        ToolTip(boton, "Historial de notificaciones de esta sesión.")

        self.boton_modo = tk.Button(cabecera, text="⚙ Modo avanzado", bg=COLOR_ENCABEZADO, fg="#94a3b8",
                                    bd=0, activebackground=COLOR_ENCABEZADO, activeforeground="white",
                                    font=(FUENTE, 9, "bold"), cursor="hand2", command=self.alternar_modo)
        self.boton_modo.pack(side="right", padx=(10, 4), pady=14)
        ToolTip(self.boton_modo, "Cambia entre el modo Operación (mapa) y el modo Avanzado "
                                 "(tablas, consola y simulador de sensores).")

    def _crear_chip(self, padre, etiqueta, ayuda):
        """Indicador numérico del encabezado. Devuelve (marco, etiqueta del número)."""
        chip = tk.Frame(padre, bg=COLOR_CHIP, width=92, height=60)
        chip.pack(side="right", padx=(0, 10), pady=11)
        chip.pack_propagate(False)
        numero = tk.Label(chip, text="0", bg=COLOR_CHIP, fg="white", font=(FUENTE, 18, "bold"))
        numero.pack(pady=(4, 0))
        texto = tk.Label(chip, text=etiqueta, bg=COLOR_CHIP, fg="#94a3b8", font=(FUENTE, 8))
        texto.pack()
        for widget in (numero, texto):     # las etiquetas tapan al marco: la ayuda va en ellas
            ToolTip(widget, ayuda)
        return chip, numero, texto

    def _construir_cuerpo(self):
        cuerpo = ttk.Frame(self, padding=(14, 10))
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure(0, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        tipos = ordenar_segun(self.db.listar_tipos_vehiculo(self.conexion), ORDEN_TIPOS_VEHICULO)
        self.vista_operacion = VistaOperacion(
            cuerpo, self, tipos,
            permite_liberar=self.db.soporta_cancelacion(self.conexion),
            permite_reinicio=hasattr(self.db, "reiniciar_datos_demo"))
        self.vista_avanzada = VistaAvanzada(cuerpo, self)
        # Las dos vistas ocupan la misma celda; tkraise() decide cuál se ve.
        self.vista_operacion.grid(row=0, column=0, sticky="nsew")
        self.vista_avanzada.grid(row=0, column=0, sticky="nsew")
        self.vista_operacion.tkraise()

        self.panel = PanelInformacion(cuerpo, al_cerrar=self.ocultar_panel,
                                      posicion_y=self._altura_para_panel)
        # Cuando el mapa se mueve (aparece o desaparece el aviso de alarma, cambia
        # el tamaño de la ventana) el panel se acomoda a la nueva altura.
        self.vista_operacion.contenedor_mapa.bind(
            "<Configure>", lambda evento: self.panel.visible and self.panel.reubicar(), add="+")

    def _construir_indicador_conexion(self):
        self.indicador = tk.Label(self, bg="#e2e8f0", fg=COLOR_SUAVE, anchor="w", padx=14, pady=5,
                                  font=(FUENTE, 9))
        self.indicador.pack(fill="x", side="bottom")
        self._actualizar_indicador()

    def _es_demostracion(self):
        return hasattr(self.db, "reiniciar_datos_demo")

    # =========================================================================
    #  Refresco: leer el estado una vez y repartirlo
    # =========================================================================

    def refrescar(self, forzar=False):
        """Lee el estado del parqueo y actualiza toda la pantalla.

        Con forzar=False solo se redibuja si el estado cambió desde la última lectura.
        """
        estado = self.db.obtener_estado_parqueo(self.conexion)
        cambio = forzar or estado != self.estado_parqueo
        self.estado_parqueo = estado
        conteo = resumir(estado)
        self._actualizar_chips(conteo)

        if cambio:
            alarmas = self.db.listar_alarmas_activas(self.conexion) if conteo["alarmas"] else []
            self.vista_operacion.dibujar_mapa(estado, self.espacio_seleccionado)
            self.vista_operacion.mostrar_alarmas(alarmas)
            self.vista_avanzada.fijar_espacios([fila["espacio"] for fila in estado])
            if self.modo == "avanzado":
                self.vista_avanzada.actualizar_detalle()
            self._actualizar_panel()
            self._avisar_alarmas_nuevas(estado)
            self._revisar_capacidad(conteo)
            for comando in self.sincronizador.comandos_pendientes(estado):
                self.vista_avanzada.registrar_trafico("← " + comando, "salida")

        self._actualizar_boton_contextual()
        self._actualizar_boton_liberar()

    def _refresco_periodico(self):
        """Se llama sola cada refresco_ms. Si no hay conexión, intenta reconectar."""
        try:
            if self.conectado:
                self.refrescar()
            else:
                self._intentar_reconectar()
        finally:
            self.after(self.configuracion.refresco_ms, self._refresco_periodico)

    def _actualizar_chips(self, conteo):
        for clave, (chip, numero, texto) in self.chips.items():
            numero.config(text=str(conteo[clave]))
        # El indicador de alarmas se pone rojo cuando hay alguna.
        chip, numero, texto = self.chips["alarmas"]
        color = COLOR_PELIGRO if conteo["alarmas"] else COLOR_CHIP
        for widget in (chip, numero, texto):
            widget.config(bg=color)

    def _avisar_alarmas_nuevas(self, estado):
        """Notifica y hace sonar la campana cuando aparece una alarma que no estaba antes."""
        en_alarma = {fila["espacio"] for fila in estado if fila["alarma_activa"] == "SI"}
        for espacio in sorted(en_alarma - self._espacios_en_alarma):
            self.notificar("error", "⚠ Alarma activa en {0}. Revisa el aviso rojo sobre el mapa.".format(espacio))
            self.bell()
        self._espacios_en_alarma = en_alarma

    def _revisar_capacidad(self, conteo):
        """Avisa cuando el parqueo se llena, solo cuando cambia la situación."""
        libres = conteo["disponibles"]
        situacion = "lleno" if libres == 0 else ("casi_lleno" if libres <= 2 else "normal")
        if situacion != self._aviso_capacidad and situacion != "normal":
            self.notificar("aviso" if libres else "error",
                           "Parqueo lleno: no quedan espacios disponibles." if libres == 0
                           else "Quedan solo {0} espacios disponibles.".format(libres))
        self._aviso_capacidad = situacion

    # =========================================================================
    #  Conexión con la base
    # =========================================================================

    def report_callback_exception(self, tipo, error, rastro):
        """Tkinter llama aquí cuando un botón o un after() lanza una excepción."""
        if isinstance(error, ErrorConexion):
            if self.conectado:
                self.conectado = False
                self.vista_operacion.habilitar_escritura(False)
                self._actualizar_indicador(str(error))
            self.notificar("error", mensajes.describir("ERROR_CONEXION") + " " + str(error))
            return
        traceback.print_exception(tipo, error, rastro)
        self.notificar("error", "Error inesperado: {0}".format(error))
        messagebox.showerror("Error inesperado", str(error), parent=self)

    def _intentar_reconectar(self):
        try:
            self.conexion.reconectar()
        except ErrorConexion:
            return      # se vuelve a intentar en el próximo refresco
        self.conectado = True
        self.vista_operacion.habilitar_escritura(True)
        self._actualizar_indicador()
        self.sincronizador.reiniciar()
        self.notificar("ok", "Conexión recuperada.")
        self.refrescar(forzar=True)

    def _actualizar_indicador(self, detalle_error=None):
        if self.conectado:
            texto = "●  Conectado · {0} · Operador: {1}".format(self.conexion.descripcion, self.configuracion.operador)
            self.indicador.config(text=texto, fg="#15803d")
        else:
            texto = "●  Sin conexión con la base de datos · reintentando cada {0} s".format(
                self.configuracion.refresco_ms // 1000)
            self.indicador.config(text=texto + (" · " + detalle_error if detalle_error else ""),
                                  fg=COLOR_PELIGRO)

    # =========================================================================
    #  Modo Operación / Avanzado
    # =========================================================================

    def alternar_modo(self):
        if self.modo == "operacion":
            self.modo = "avanzado"
            self.vista_avanzada.tkraise()
            self.vista_avanzada.actualizar_detalle()
            self.boton_modo.config(text="← Volver a operación")
        else:
            self.modo = "operacion"
            self.vista_operacion.tkraise()
            self.boton_modo.config(text="⚙ Modo avanzado")
        if self.panel.visible:
            self.panel.reubicar()   # encima de la vista elegida y a la altura que le toca

    # =========================================================================
    #  Selección y panel de información
    # =========================================================================

    def seleccionar_espacio(self, codigo):
        """Clic en una tarjeta del mapa o en una fila de espacio."""
        self.espacio_seleccionado = codigo
        fila = fila_de_espacio(self.estado_parqueo, codigo)
        if fila and fila["placa_vehiculo"]:
            self.vista_operacion.fijar_placa(fila["placa_vehiculo"])   # para encadenar la siguiente acción
        self.mostrar_espacio(codigo)
        self.vista_operacion.dibujar_mapa(self.estado_parqueo, codigo)
        self._actualizar_boton_liberar()

    def mostrar_espacio(self, codigo):
        fila = fila_de_espacio(self.estado_parqueo, codigo)
        if fila is None:
            return
        filas = [("Código", fila["espacio"]), ("Tipo", fila["tipo"]), ("Sector", fila["sector"]),
                 ("Estado", fila["estado"]), ("LED físico", fila["led_estado"])]
        if fila["placa_vehiculo"]:
            ficha = self.db.buscar_vehiculo(self.conexion, fila["placa_vehiculo"])
            filas += [("Vehículo", ficha["placa"]), ("Tipo veh.", ficha["tipo_vehiculo"])]
            filas += self._filas_de_ocupacion(ficha)
        else:
            filas.append(("Vehículo", "ninguno"))
        self.panel.mostrar("Espacio " + codigo, filas)
        self._contenido_panel = ("espacio", codigo)

    def mostrar_vehiculo(self, placa, llenar_formulario=False):
        """Muestra la ficha de un vehículo. Devuelve la ficha o None si no existe."""
        if llenar_formulario:
            self.vista_operacion.fijar_placa(placa)
        ficha = self.db.buscar_vehiculo(self.conexion, placa)
        if ficha is None:
            self.panel.mostrar_texto("No hay un vehículo registrado con la placa {0}.".format(placa))
            self._contenido_panel = None
            return None
        filas = [("Placa", ficha["placa"]), ("Tipo", ficha["tipo_vehiculo"]),
                 ("Registrado", ficha["fecha_registro"])]
        if ficha["espacio"]:
            filas += [("Espacio", ficha["espacio"])] + self._filas_de_ocupacion(ficha)
        else:
            filas.append(("Espacio", "sin asignar"))
        self.panel.mostrar("Vehículo " + ficha["placa"], filas)
        self._contenido_panel = ("vehiculo", ficha["placa"])
        return ficha

    @staticmethod
    def _filas_de_ocupacion(ficha):
        """Datos de la ocupación activa de un vehículo, para el panel de información."""
        autorizada = ficha["fecha_autorizacion"]
        return [
            ("Ocupación", ficha["estado_ocupacion"]),
            ("Asignado", ficha["fecha_asignacion"]),
            ("Llegada", ficha["fecha_llegada"] or "pendiente"),
            ("Autorizada", "{0} · {1}".format(autorizada.strftime("%H:%M:%S"), ficha["autorizado_por"])
             if autorizada else "no"),
            ("Seguridad", "armada" if ficha["seguridad_activa"] else "desarmada"),
            ("Alarma", "⚠ " + ficha["tipo_alarma"] if ficha["alarma_activa"] == "SI" else "no"),
        ]

    def _altura_para_panel(self):
        """En modo operación el panel va a la altura del mapa, para no tapar los
        botones de la barra de acción ni los del aviso de alarma."""
        if self.modo != "operacion":
            return 0
        return self.vista_operacion.inicio_del_mapa()

    def _actualizar_panel(self):
        """Si el panel está abierto, lo vuelve a llenar con los datos nuevos."""
        if not self.panel.visible or self._contenido_panel is None:
            return
        tipo, clave = self._contenido_panel
        if tipo == "espacio":
            self.mostrar_espacio(clave)
        else:
            self.mostrar_vehiculo(clave)

    def ocultar_panel(self):
        self.panel.ocultar()
        self._contenido_panel = None

    def _actualizar_boton_liberar(self):
        fila = fila_de_espacio(self.estado_parqueo, self.espacio_seleccionado or "")
        self.vista_operacion.habilitar_liberar(
            self.conectado and fila is not None and fila["estado_ocupacion"] is not None)

    # =========================================================================
    #  Botón contextual: ofrece el siguiente paso del ciclo de vida
    # =========================================================================

    def al_cambiar_placa(self):
        """Se llama en cada tecla; espera a que el usuario deje de escribir para consultar."""
        if self._espera_placa is not None:
            self.after_cancel(self._espera_placa)
        self._espera_placa = self.after(MILISEGUNDOS_ESPERA_PLACA, self._actualizar_boton_contextual)

    def _actualizar_boton_contextual(self):
        self._espera_placa = None
        texto, accion, es_alarma = self._calcular_accion_contextual(self.vista_operacion.placa())
        self.vista_operacion.mostrar_accion(texto, es_alarma)
        self._accion_contextual = accion

    def _calcular_accion_contextual(self, placa):
        """Devuelve (texto del botón, función a ejecutar, ¿es una alarma?).

            sin placa o no registrada  -> Registrar y asignar espacio
            registrada sin ocupación   -> Asignar espacio
            ASIGNADA                   -> Registrar llegada
            OCUPADA con alarma         -> Apagar alarma (botón rojo)
            OCUPADA                    -> Autorizar salida
            AUTORIZADA                 -> Registrar salida
        """
        registrar = ("Registrar y asignar espacio", self.accion_registrar, False)
        if not placa:
            return registrar
        fila = fila_de_placa(self.estado_parqueo, placa)
        if fila is None:
            # No está en el mapa: o no existe, o existe pero no tiene espacio.
            if self.db.buscar_vehiculo(self.conexion, placa) is None:
                return registrar
            return "Asignar espacio", self.accion_asignar, False

        estado, en_alarma = fila["estado_ocupacion"], fila["alarma_activa"] == "SI"
        if estado == ASIGNADA:
            return "Registrar llegada", self.accion_llegada, False
        if estado == OCUPADA and en_alarma:
            return "Apagar alarma", self.accion_apagar_alarma, True
        if estado == OCUPADA:
            return "Autorizar salida", self.accion_autorizar, False
        if estado == AUTORIZADA:
            return "Registrar salida", self.accion_salida, False
        return registrar

    def ejecutar_accion_contextual(self):
        """Clic en el botón azul o Enter en la placa. Recalcula por si la placa cambió hace poco."""
        if not self.conectado:
            self.notificar("error", mensajes.describir("ERROR_CONEXION"))
            return
        self._actualizar_boton_contextual()
        self._accion_contextual()

    # =========================================================================
    #  Acciones del operador (cada una llama a un procedimiento de la base)
    # =========================================================================

    def _placa_del_formulario(self):
        """Placa escrita, o None (con aviso) si está vacía o es demasiado larga."""
        placa = self.vista_operacion.placa()
        if not placa or len(placa) > LONGITUD_MAXIMA_PLACA:
            self.notificar("aviso", mensajes.describir("PLACA_VACIA" if not placa else "PLACA_LARGA"))
            self.vista_operacion.enfocar_placa()
            return None
        return placa

    def _reportar(self, resultado, **datos):
        """Muestra un resultado que no fue "OK" con el texto y color de logica/mensajes.py."""
        self.notificar(mensajes.nivel(resultado.codigo), mensajes.describir(resultado, **datos))

    def accion_registrar(self, asignar=True):
        """REGISTRAR y, si asignar=True, también ASIGNAR."""
        placa = self._placa_del_formulario()
        if placa is None:
            return
        tipo = self.vista_operacion.tipo()
        resultado = self.db.registrar_vehiculo(self.conexion, placa, tipo)
        if resultado.codigo != "OK":
            self._reportar(resultado, placa=placa, tipo=tipo)
            self.refrescar()
            return

        siguiente = "" if asignar else " El botón azul ahora ofrece 'Asignar espacio'."
        self.notificar("ok", "Vehículo {0} ({1}) registrado.{2}".format(placa, tipo, siguiente))
        if asignar:
            self.accion_asignar()
        else:
            self.refrescar()
            self.mostrar_vehiculo(placa)

    def accion_asignar(self):
        """ASIGNAR: la base elige el espacio según la tabla de compatibilidad."""
        placa = self._placa_del_formulario()
        if placa is None:
            return
        resultado = self.db.asignar_espacio(self.conexion, placa)
        if resultado.codigo == "OK":
            self.espacio_seleccionado = resultado.dato
            self.notificar("ok", "Espacio {0} asignado a {1}. Cuando llegue, registra su llegada."
                           .format(resultado.dato, placa))
        else:
            ficha = self.db.buscar_vehiculo(self.conexion, placa)
            self._reportar(resultado, placa=placa, tipo=ficha["tipo_vehiculo"] if ficha else "?")
        self.refrescar(forzar=True)
        self.mostrar_vehiculo(placa)

    def _accion_con_placa(self, operacion, texto_exito, placa=None):
        """Plantilla común de LLEGADA, AUTORIZAR_SALIDA, SALIDA y APAGAR_ALARMA."""
        placa = placa or self._placa_del_formulario()
        if placa is None:
            return
        fila = fila_de_placa(self.estado_parqueo, placa)
        resultado = operacion(placa)
        espacio = resultado.dato or (fila["espacio"] if fila else "?")
        if resultado.codigo == "OK":
            self.notificar("ok", texto_exito.format(placa=placa, espacio=espacio))
        else:
            self._reportar(resultado, placa=placa, espacio=espacio)
        self.refrescar()
        self.mostrar_vehiculo(placa)

    def accion_llegada(self):
        self._accion_con_placa(lambda placa: self.db.registrar_llegada(self.conexion, placa),
                               "Llegada de {placa} confirmada en {espacio}. Seguridad activada.")

    def accion_autorizar(self):
        self._accion_con_placa(lambda placa: self.db.autorizar_salida(self.conexion, placa, self.configuracion.operador),
                               "Salida de {placa} autorizada. Ya puede retirarse de {espacio}.")

    def accion_salida(self):
        self._accion_con_placa(lambda placa: self.db.registrar_salida(self.conexion, placa),
                               "Salida de {placa} registrada. {espacio} quedó disponible.")

    def accion_apagar_alarma(self, placa=None):
        """Desde el botón contextual (placa escrita) o desde el aviso rojo (placa de la alarma)."""
        self._accion_con_placa(lambda p: self.db.apagar_alarma(self.conexion, p, self.configuracion.operador),
                               "Alarma de {placa} apagada. La seguridad sigue armada hasta autorizar la salida.",
                               placa)

    def accion_liberar(self):
        """Liberación manual (pa_cancelar_ocupacion). Pide confirmación porque no registra salida."""
        codigo = self.espacio_seleccionado
        fila = fila_de_espacio(self.estado_parqueo, codigo or "")
        if fila is None or fila["estado_ocupacion"] is None:
            self.notificar("aviso", "Selecciona en el mapa un espacio que tenga un vehículo.")
            return
        if not messagebox.askyesno(
                "Liberar espacio",
                "{0} tiene al vehículo {1} (ocupación {2}).\n\nLiberarlo cancelará su ocupación sin "
                "registrar la salida. ¿Continuar?".format(codigo, fila["placa_vehiculo"],
                                                          fila["estado_ocupacion"]), parent=self):
            return
        resultado = self.db.cancelar_ocupacion(self.conexion, codigo, self.configuracion.operador)
        if resultado.codigo == "OK":
            self.notificar("ok", "Espacio {0} liberado (ocupación de {1} cancelada).".format(codigo, resultado.dato))
        else:
            self._reportar(resultado, espacio=codigo)
        self.refrescar()
        self.mostrar_espacio(codigo)

    def accion_buscar(self):
        placa = self._placa_del_formulario()
        if placa is None:
            return
        ficha = self.mostrar_vehiculo(placa)
        if ficha is None:
            self.notificar("error", mensajes.describir("VEHICULO_NO_ENCONTRADO", placa=placa))
            return
        if ficha["espacio"]:
            self.espacio_seleccionado = ficha["espacio"]
            self.vista_operacion.dibujar_mapa(self.estado_parqueo, ficha["espacio"])
        self.notificar("info", "Ficha del vehículo {0} cargada.".format(placa))

    def accion_limpiar(self):
        self.vista_operacion.limpiar_formulario()
        self.espacio_seleccionado = None
        self.ocultar_panel()
        self.vista_operacion.dibujar_mapa(self.estado_parqueo, None)
        self._actualizar_boton_liberar()

    def accion_reiniciar_demo(self):
        """Solo en modo demostración: vuelve a los datos de ejemplo."""
        if not messagebox.askyesno("Reiniciar datos de demostración",
                                   "Se perderán los cambios de esta sesión. ¿Continuar?", parent=self):
            return
        self.db.reiniciar_datos_demo(self.conexion)
        self.sincronizador.reiniciar()
        self.accion_limpiar()
        self.refrescar(forzar=True)
        self.notificar("info", "Datos de demostración reiniciados.")

    # =========================================================================
    #  Modo Avanzado: consola, simulador y tablas de detalle
    # =========================================================================

    def leer_datos(self, nombre_funcion, argumentos):
        """Lecturas de la pestaña Detalle: llama a db.<nombre_funcion>(conexion, **argumentos)."""
        return getattr(self.db, nombre_funcion)(self.conexion, **argumentos)

    def ejecutar_comando(self, texto):
        """Consola: ejecuta una instrucción con logica/interprete.py. Devuelve (nivel, mensaje)."""
        nivel, mensaje = interprete.ejecutar(texto, self.db, self.conexion, self.configuracion.operador)
        if nivel in ("ok", "error", "aviso") and mensaje:
            self.notificar(nivel, "Consola: " + mensaje.splitlines()[0])
        self.refrescar(forzar=True)
        return nivel, mensaje

    def procesar_mensaje_esp32(self, linea):
        """Mensaje del ESP32 (hoy del simulador). El futuro hardware_serial.py llamará aquí también."""
        self.vista_avanzada.registrar_trafico("→ " + linea.strip(), "entrada")
        try:
            evento, espacio = eventos_hardware.interpretar_mensaje(linea)
        except ValueError as error:
            self.vista_avanzada.registrar_trafico("   " + str(error), "error")
            return

        fila = fila_de_espacio(self.estado_parqueo, espacio) if espacio else None
        resultado = eventos_hardware.procesar_evento(self.db, self.conexion, evento, espacio)
        placa = resultado.dato if evento == "MOVIMIENTO" else (fila["placa_vehiculo"] if fila else None)
        texto = mensajes.describir(resultado, placa=placa or "?", espacio=espacio)
        nivel = mensajes.nivel(resultado.codigo)
        self.vista_avanzada.registrar_trafico("   {0}: {1}".format(resultado.codigo, texto), nivel)

        if evento != "HEARTBEAT" and resultado.codigo != "SIN_CAMBIOS":
            self.notificar(nivel, "Sensor {0}: {1}".format(espacio, texto))
        self.refrescar(forzar=True)   # aquí el sincronizador registra los comandos PY:...

    def reenviar_estado_esp32(self):
        self.sincronizador.reiniciar()
        self.vista_avanzada.registrar_trafico("   (reenvío completo del estado)", "info")
        self.refrescar(forzar=True)

    # =========================================================================
    #  Notificaciones
    # =========================================================================

    def notificar(self, nivel, texto):
        """Agrega una notificación al historial y la muestra en la barra inferior."""
        hora = datetime.now().strftime("%H:%M:%S")
        self.notificaciones.insert(0, (hora, nivel, texto))
        del self.notificaciones[200:]      # tope para que no crezca sin límite
        self.vista_operacion.mostrar_notificacion(nivel, texto, hora)
        if self.ventana_notificaciones is not None and self.ventana_notificaciones.winfo_exists():
            self.ventana_notificaciones.actualizar(self.notificaciones)

    def abrir_notificaciones(self):
        if self.ventana_notificaciones is None or not self.ventana_notificaciones.winfo_exists():
            self.ventana_notificaciones = VentanaNotificaciones(self, al_limpiar=self.limpiar_notificaciones)
        self.ventana_notificaciones.actualizar(self.notificaciones)
        self.ventana_notificaciones.lift()

    def limpiar_notificaciones(self):
        self.notificaciones = []
        self.vista_operacion.mostrar_notificacion("info", "Sin notificaciones.", datetime.now().strftime("%H:%M:%S"))
        if self.ventana_notificaciones is not None and self.ventana_notificaciones.winfo_exists():
            self.ventana_notificaciones.actualizar(self.notificaciones)

    def al_cerrar(self):
        self.conexion.close()
        self.destroy()
