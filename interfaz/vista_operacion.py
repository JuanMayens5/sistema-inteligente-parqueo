"""
Modo Operación
==============

La pantalla que usa el operador del parqueo en el día a día:

    ┌──────────────────────────────────────────────────────────────┐
    │ Placa [____]  Tipo [____▾]  [Botón contextual]  [Liberar]  [⋯] │  barra de acción rápida
    ├──────────────────────────────────────────────────────────────┤
    │ ⚠ C-01 · Movimiento no autorizado...   [Ver] [Apagar alarma]  │  aviso (solo si hay alarmas)
    ├──────────────────────────────────────────────────────────────┤
    │  COMPACTO · 2 de 3 disponibles                                │
    │  [C-01 ●] [C-02 ●] [C-03 ●]      ← tarjetas: color = estado,  │  mapa de espacios
    │                                     punto = LED físico         │
    ├──────────────────────────────────────────────────────────────┤
    │ ✓ Última notificación                          [Ver todas ▾]  │  barra de notificaciones
    └──────────────────────────────────────────────────────────────┘

Esta vista NO habla con la base de datos. AppParqueo le pasa los datos
(dibujar_mapa, mostrar_alarmas...) y ella le avisa a AppParqueo cuando el
usuario hace algo (self.app.accion_...).
"""

import tkinter as tk
from tkinter import ttk

from interfaz.componentes import (
    COLOR_ACENTO, COLOR_BORDE, COLOR_FONDO, COLOR_LED, COLOR_NIVEL, COLOR_PANEL, COLOR_PELIGRO,
    COLOR_SUAVE, ESTILO_ESTADO, FUENTE, FUENTE_MONO, ICONO_NIVEL, ORDEN_TIPOS_ESPACIO, ToolTip,
    estado_visual, ordenar_segun,
)

GRUPOS_POR_FILA = 2        # tipos de espacio lado a lado en el mapa
TARJETAS_POR_FILA = 3      # tarjetas por fila dentro de cada tipo
MILISEGUNDOS_PARPADEO = 500


class VistaOperacion(ttk.Frame):

    def __init__(self, padre, app, tipos_vehiculo, permite_liberar, permite_reinicio):
        super().__init__(padre)
        self.app = app
        # Funciones que se llaman cada medio segundo para hacer parpadear la
        # tarjeta y el LED de los espacios con alarma. Se rehace en cada dibujo del mapa.
        self._efectos_parpadeo = []
        self._encendido = True
        self._alarma_del_aviso = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._construir_barra_accion(tipos_vehiculo, permite_liberar, permite_reinicio)
        self._construir_aviso_alarma()
        self._construir_mapa()
        self._construir_barra_notificaciones()
        self._parpadear()

    # =========================================================================
    #  Construcción
    # =========================================================================

    def _construir_barra_accion(self, tipos_vehiculo, permite_liberar, permite_reinicio):
        barra = ttk.Frame(self, padding=(2, 4))
        barra.grid(row=0, column=0, sticky="ew")

        ttk.Label(barra, text="Placa").grid(row=0, column=0, padx=(0, 6))
        self.var_placa = tk.StringVar()
        self.var_placa.trace_add("write", self._al_escribir_placa)
        self.entrada_placa = ttk.Entry(barra, textvariable=self.var_placa, font=(FUENTE_MONO, 13), width=13)
        self.entrada_placa.grid(row=0, column=1, padx=(0, 16))
        self.entrada_placa.bind("<Return>", lambda evento: self.app.ejecutar_accion_contextual())
        ToolTip(self.entrada_placa, "Placa del vehículo (se convierte a mayúsculas). "
                                    "Enter ejecuta el botón azul.")

        ttk.Label(barra, text="Tipo").grid(row=0, column=2, padx=(0, 6))
        self.combo_tipo = ttk.Combobox(barra, values=tipos_vehiculo, state="readonly", width=14)
        self.combo_tipo.grid(row=0, column=3, padx=(0, 16))
        self.combo_tipo.current(0)
        ToolTip(self.combo_tipo, "Tipo del vehículo. La base decide qué espacio le toca según la "
                                 "tabla de compatibilidad (ej. un compacto puede usar un espacio grande).")

        self.boton_principal = ttk.Button(barra, text="Registrar y asignar espacio",
                                          style="Principal.TButton",
                                          command=self.app.ejecutar_accion_contextual)
        self.boton_principal.grid(row=0, column=4, padx=(0, 8))
        ToolTip(self.boton_principal, "Ofrece el siguiente paso según el estado del vehículo: "
                                      "registrar → llegada → autorizar salida → salida.")

        self.boton_liberar = None
        if permite_liberar:
            self.boton_liberar = ttk.Button(barra, text="Liberar espacio", state="disabled",
                                            command=self.app.accion_liberar)
            self.boton_liberar.grid(row=0, column=5, padx=(0, 8))
            ToolTip(self.boton_liberar, "Cancela la ocupación del espacio seleccionado sin "
                                        "registrar salida (uso excepcional).")

        self.menu_acciones = ttk.Menubutton(barra, text="⋯ Más acciones")
        menu = tk.Menu(self.menu_acciones, tearoff=False)
        menu.add_command(label="Solo registrar (sin asignar espacio)",
                         command=lambda: self.app.accion_registrar(asignar=False))
        menu.add_command(label="Buscar vehículo por placa", command=self.app.accion_buscar)
        menu.add_separator()
        menu.add_command(label="Actualizar vista", command=lambda: self.app.refrescar(forzar=True))
        menu.add_command(label="Limpiar campos", command=self.app.accion_limpiar)
        if permite_reinicio:
            menu.add_separator()
            menu.add_command(label="Reiniciar datos de demostración",
                             command=self.app.accion_reiniciar_demo)
        self.menu_acciones["menu"] = menu
        self.menu_acciones.grid(row=0, column=6)

    def _construir_aviso_alarma(self):
        """Franja roja sobre el mapa; se oculta con grid_remove() cuando no hay alarmas."""
        self.aviso = tk.Frame(self, bg="#fee2e2", highlightbackground=COLOR_PELIGRO, highlightthickness=1)
        self.aviso.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.aviso.columnconfigure(0, weight=1)
        self.texto_aviso = tk.Label(self.aviso, bg="#fee2e2", fg="#7f1d1d", anchor="w",
                                    font=(FUENTE, 10, "bold"), padx=10, pady=8)
        self.texto_aviso.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.aviso, text="Ver",
                   command=lambda: self.app.seleccionar_espacio(self._alarma_del_aviso["espacio"])
                   ).grid(row=0, column=1, padx=4)
        ttk.Button(self.aviso, text="Apagar alarma", style="Alarma.TButton",
                   command=lambda: self.app.accion_apagar_alarma(self._alarma_del_aviso["placa"])
                   ).grid(row=0, column=2, padx=(4, 8), pady=4)
        self.aviso.grid_remove()

    def _construir_mapa(self):
        self.contenedor_mapa = contenedor = ttk.Frame(self)
        contenedor.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(1, weight=1)

        titulo = ttk.Frame(contenedor)
        titulo.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(titulo, text="Mapa de espacios", font=(FUENTE, 10, "bold")).pack(side="left")
        ayuda = ttk.Label(titulo, text=" (?)", font=(FUENTE, 9, "bold"), foreground=COLOR_ACENTO,
                          cursor="question_arrow")
        ayuda.pack(side="left", padx=(4, 0))
        ToolTip(ayuda, "Verde = disponible · Amarillo = asignado (esperando al vehículo) · "
                       "Rojo = ocupado · Azul = saliendo (salida autorizada) · Gris = fuera de servicio.\n"
                       "El punto de cada tarjeta muestra el LED físico. Borde rojo parpadeante = alarma.\n"
                       "Clic en una tarjeta para ver y operar ese espacio.")

        # El mapa va dentro de un Canvas para poder desplazarlo si hay muchos espacios.
        self.lienzo = tk.Canvas(contenedor, bg=COLOR_FONDO, highlightthickness=0)
        self.lienzo.grid(row=1, column=0, sticky="nsew")
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=self.lienzo.yview)
        barra.grid(row=1, column=1, sticky="ns")
        self.lienzo.configure(yscrollcommand=barra.set)

        self.marco_mapa = tk.Frame(self.lienzo, bg=COLOR_FONDO)
        ventana = self.lienzo.create_window((0, 0), window=self.marco_mapa, anchor="nw")
        self.marco_mapa.bind("<Configure>",
                             lambda evento: self.lienzo.configure(scrollregion=self.lienzo.bbox("all")))
        self.lienzo.bind("<Configure>", lambda evento: self.lienzo.itemconfigure(ventana, width=evento.width))
        # La rueda del mouse solo desplaza el mapa mientras el puntero está encima.
        self.lienzo.bind("<Enter>", lambda evento: self.lienzo.bind_all("<MouseWheel>", self._rueda))
        self.lienzo.bind("<Leave>", lambda evento: self.lienzo.unbind_all("<MouseWheel>"))

    def _construir_barra_notificaciones(self):
        barra = tk.Frame(self, bg=COLOR_PANEL, highlightbackground=COLOR_BORDE, highlightthickness=1)
        barra.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        barra.columnconfigure(0, weight=1)
        self.texto_notificacion = tk.Label(barra, text="Sin notificaciones todavía.", bg=COLOR_PANEL,
                                           fg=COLOR_SUAVE, anchor="w", font=(FUENTE, 9), padx=10, pady=6)
        self.texto_notificacion.grid(row=0, column=0, sticky="ew")
        ttk.Button(barra, text="Ver todas ▾", command=self.app.abrir_notificaciones).grid(
            row=0, column=1, padx=8, pady=4)

    # =========================================================================
    #  Formulario (lo que AppParqueo lee o cambia)
    # =========================================================================

    def placa(self):
        return self.var_placa.get().strip().upper()

    def fijar_placa(self, placa):
        self.var_placa.set(placa)

    def tipo(self):
        return self.combo_tipo.get()

    def limpiar_formulario(self):
        self.var_placa.set("")
        self.combo_tipo.current(0)
        self.entrada_placa.focus_set()

    def enfocar_placa(self):
        self.entrada_placa.focus_set()

    def _al_escribir_placa(self, *args):
        texto = self.var_placa.get()
        if texto != texto.upper():
            self.var_placa.set(texto.upper())   # esto vuelve a disparar este mismo método
            return
        self.app.al_cambiar_placa()

    def mostrar_accion(self, texto, es_alarma=False):
        """Cambia el texto del botón contextual (rojo cuando la acción es apagar una alarma)."""
        self.boton_principal.config(text=texto, style="Alarma.TButton" if es_alarma else "Principal.TButton")

    def habilitar_escritura(self, activo):
        """Sin conexión con la base se deshabilitan los controles que escriben."""
        estado = "normal" if activo else "disabled"
        self.entrada_placa.config(state=estado)
        self.combo_tipo.config(state="readonly" if activo else "disabled")
        self.boton_principal.config(state=estado)
        self.menu_acciones.config(state=estado)
        if not activo:
            self.habilitar_liberar(False)

    def habilitar_liberar(self, activo):
        if self.boton_liberar is not None:
            self.boton_liberar.config(state="normal" if activo else "disabled")

    # =========================================================================
    #  Mapa de espacios
    # =========================================================================

    def dibujar_mapa(self, estado_parqueo, seleccionado):
        """Vuelve a crear las tarjetas. estado_parqueo = filas de obtener_estado_parqueo()."""
        self._efectos_parpadeo = []
        for hijo in self.marco_mapa.winfo_children():
            hijo.destroy()

        por_tipo = {}
        for fila in estado_parqueo:
            por_tipo.setdefault(fila["tipo"], []).append(fila)

        # Cada tipo de espacio es un "grupo" (título + sus tarjetas); los grupos
        # se acomodan de GRUPOS_POR_FILA en GRUPOS_POR_FILA.
        for numero_grupo, tipo in enumerate(ordenar_segun(por_tipo, ORDEN_TIPOS_ESPACIO)):
            grupo = por_tipo[tipo]
            marco_grupo = tk.Frame(self.marco_mapa, bg=COLOR_FONDO)
            marco_grupo.grid(row=numero_grupo // GRUPOS_POR_FILA, column=numero_grupo % GRUPOS_POR_FILA,
                             sticky="nw", padx=(0, 28))

            libres = sum(1 for fila in grupo if fila["estado"] == "DISPONIBLE")
            tk.Label(marco_grupo, text="{0}   ·   {1} de {2} disponibles".format(tipo, libres, len(grupo)),
                     bg=COLOR_FONDO, fg=COLOR_SUAVE, font=(FUENTE, 9, "bold")
                     ).grid(row=0, column=0, columnspan=TARJETAS_POR_FILA, sticky="w", padx=6, pady=(10, 2))
            for indice, fila in enumerate(grupo):
                tarjeta = self._crear_tarjeta(marco_grupo, fila, fila["espacio"] == seleccionado)
                tarjeta.grid(row=1 + indice // TARJETAS_POR_FILA, column=indice % TARJETAS_POR_FILA,
                             padx=6, pady=5)

    def inicio_del_mapa(self):
        """Altura (en píxeles, dentro de la ventana) donde empieza el mapa. La usa el panel flotante."""
        return self.winfo_y() + self.contenedor_mapa.winfo_y()

    def _crear_tarjeta(self, padre, fila, seleccionada):
        estilo = ESTILO_ESTADO[estado_visual(fila)]
        en_alarma = fila["alarma_activa"] == "SI"
        borde = COLOR_ACENTO if seleccionada else (COLOR_PELIGRO if en_alarma else estilo["borde"])

        tarjeta = tk.Frame(padre, bg=estilo["fondo"], width=136, height=92, cursor="hand2",
                           highlightbackground=borde, highlightcolor=borde,
                           highlightthickness=3 if (seleccionada or en_alarma) else 2)
        tarjeta.pack_propagate(False)       # tamaño fijo aunque el texto sea más corto

        codigo = ("⚠ " if en_alarma else "") + fila["espacio"]
        tk.Label(tarjeta, text=codigo, bg=estilo["fondo"], fg=estilo["letra"],
                 font=(FUENTE, 13, "bold")).pack(pady=(11, 0))
        tk.Label(tarjeta, text=estilo["texto"], bg=estilo["fondo"], fg=estilo["letra"],
                 font=(FUENTE, 8)).pack()
        tk.Label(tarjeta, text=fila["placa_vehiculo"] or "— libre —", bg=estilo["fondo"],
                 fg=estilo["letra"], font=(FUENTE_MONO, 9, "bold" if fila["placa_vehiculo"] else "normal")
                 ).pack(pady=(4, 0))

        led = self._crear_led(tarjeta, fila["led_estado"], estilo["fondo"])
        led.place(relx=1.0, x=-8, y=8, anchor="ne")

        if en_alarma and not seleccionada:
            self._efectos_parpadeo.append(
                lambda encendido: tarjeta.config(highlightbackground=COLOR_PELIGRO if encendido else estilo["fondo"]))

        ayuda = "{0} · {1}\nLED físico: {2}{3}".format(fila["espacio"], estilo["texto"], fila["led_estado"],
                                                        "\n⚠ Alarma activa" if en_alarma else "")
        # Las etiquetas tapan casi toda la tarjeta: el clic y la ayuda van en cada pieza.
        for widget in [tarjeta, led] + list(tarjeta.pack_slaves()):
            widget.bind("<Button-1>", lambda evento, e=fila["espacio"]: self.app.seleccionar_espacio(e))
            ToolTip(widget, ayuda)
        return tarjeta

    def _crear_led(self, padre, led_estado, fondo):
        """Punto de color que imita al LED físico del espacio (columna led_estado)."""
        lienzo = tk.Canvas(padre, width=12, height=12, bg=fondo, highlightthickness=0)
        color = COLOR_LED.get(led_estado, COLOR_LED["APAGADO"])
        punto = lienzo.create_oval(1, 1, 11, 11, fill=color if led_estado != "APAGADO" else fondo,
                                   outline=color)
        if led_estado == "PARPADEO":
            self._efectos_parpadeo.append(
                lambda encendido: lienzo.itemconfig(punto, fill=color if encendido else fondo))
        return lienzo

    def _parpadear(self):
        """Ciclo permanente: enciende/apaga lo que tenga que parpadear."""
        self._encendido = not self._encendido
        for efecto in self._efectos_parpadeo:
            efecto(self._encendido)
        self.after(MILISEGUNDOS_PARPADEO, self._parpadear)

    def _rueda(self, evento):
        self.lienzo.yview_scroll(int(-evento.delta / 120), "units")

    # =========================================================================
    #  Aviso de alarma y notificaciones
    # =========================================================================

    def mostrar_alarmas(self, alarmas):
        """alarmas = filas de listar_alarmas_activas(). Muestra la más reciente."""
        if not alarmas:
            self.aviso.grid_remove()
            return
        self._alarma_del_aviso = alarmas[0]
        texto = "⚠  {0} · {1}".format(alarmas[0]["espacio"], alarmas[0]["descripcion"])
        if len(alarmas) > 1:
            texto += "   (+{0} más)".format(len(alarmas) - 1)
        self.texto_aviso.config(text=texto)
        self.aviso.grid()

    def mostrar_notificacion(self, nivel, texto, hora):
        self.texto_notificacion.config(text="{0} {1}   ·   {2}".format(ICONO_NIVEL.get(nivel, "•"), texto, hora),
                                       fg=COLOR_NIVEL.get(nivel, COLOR_SUAVE))
