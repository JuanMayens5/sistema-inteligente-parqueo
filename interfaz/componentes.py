"""
Componentes visuales compartidos
================================

Todo lo que define el aspecto de la aplicación y las piezas que se usan en
más de una pantalla:

    Paleta y estados      colores, textos de cada estado, colores de los LEDs
    configurar_estilos()  estilos ttk (botones, tablas, pestañas)
    ToolTip               ayuda que aparece al dejar el mouse sobre un widget
    crear_tabla()         tabla (Treeview) con barra de desplazamiento
    PanelInformacion      panel flotante con la ficha de un espacio o vehículo
    VentanaNotificaciones historial de notificaciones de la sesión

Para cambiar el aspecto general basta con tocar las constantes de este archivo.
"""

import tkinter as tk
from datetime import datetime
from tkinter import ttk

# =============================================================================
#  Paleta y tipografía
# =============================================================================

FUENTE = "Segoe UI"
FUENTE_MONO = "Consolas"

COLOR_FONDO = "#f1f5f9"
COLOR_PANEL = "#ffffff"
COLOR_ENCABEZADO = "#0f172a"
COLOR_CHIP = "#1e293b"
COLOR_TEXTO = "#0f172a"
COLOR_SUAVE = "#64748b"
COLOR_ACENTO = "#2563eb"
COLOR_BORDE = "#cbd5e1"
COLOR_PELIGRO = "#dc2626"
COLOR_CONSOLA_FONDO = "#0b1220"
COLOR_CONSOLA_TEXTO = "#e2e8f0"

# Cómo se ve cada tarjeta del mapa según su estado (ver estado_visual()).
ESTILO_ESTADO = {
    "DISPONIBLE": {"texto": "Disponible", "fondo": "#dcfce7", "borde": "#22c55e", "letra": "#14532d"},
    "ASIGNADA": {"texto": "Asignado", "fondo": "#fef9c3", "borde": "#eab308", "letra": "#713f12"},
    "OCUPADA": {"texto": "Ocupado", "fondo": "#fee2e2", "borde": "#ef4444", "letra": "#7f1d1d"},
    "AUTORIZADA": {"texto": "Saliendo", "fondo": "#dbeafe", "borde": "#3b82f6", "letra": "#1e3a8a"},
    "FUERA_DE_SERVICIO": {"texto": "Fuera de servicio", "fondo": "#e5e7eb", "borde": "#9ca3af",
                          "letra": "#374151"},
}

# Color del "LED virtual" de cada tarjeta = columna espacios.led_estado.
COLOR_LED = {"VERDE": "#22c55e", "AMARILLO": "#eab308", "ROJO": "#ef4444",
             "PARPADEO": "#ef4444", "APAGADO": "#9ca3af"}

# Color e ícono de las notificaciones según su nivel (ver logica/mensajes.py).
COLOR_NIVEL = {"ok": "#15803d", "aviso": "#b45309", "error": "#b91c1c", "info": "#1d4ed8"}
ICONO_NIVEL = {"ok": "✓", "aviso": "⚠", "error": "✕", "info": "ℹ"}

# Orden en que aparecen los tipos en el mapa y en la lista de tipos de vehículo.
ORDEN_TIPOS_ESPACIO = ["COMPACTO", "GRANDE", "MOTOCICLETA", "CARGA_DESCARGA", "RESERVADO"]
ORDEN_TIPOS_VEHICULO = ["COMPACTO", "GRANDE", "MOTOCICLETA", "CARGA", "RESERVADO"]


def estado_visual(fila):
    """Estado que se dibuja para una fila del estado del parqueo.

    Se usa el estado de la OCUPACIÓN porque distingue más casos que el del
    espacio: un espacio OCUPADO puede estar "Ocupado" o ya "Saliendo" (AUTORIZADA).
    """
    if fila["estado"] == "FUERA_DE_SERVICIO":
        return "FUERA_DE_SERVICIO"
    return fila["estado_ocupacion"] or "DISPONIBLE"


def ordenar_segun(valores, preferencia):
    """Ordena `valores` según la lista `preferencia`; lo desconocido va al final."""
    return sorted(valores, key=lambda v: (preferencia.index(v) if v in preferencia else len(preferencia), v))


def formatear(valor):
    """Texto para mostrar un valor de la base en una tabla o ficha."""
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m %H:%M:%S")
    return str(valor)


# =============================================================================
#  Estilos ttk
# =============================================================================

def configurar_estilos(raiz):
    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")

    estilo.configure("TFrame", background=COLOR_FONDO)
    estilo.configure("TLabel", background=COLOR_FONDO, foreground=COLOR_TEXTO, font=(FUENTE, 10))
    estilo.configure("Tenue.TLabel", foreground=COLOR_SUAVE, font=(FUENTE, 9))
    estilo.configure("TLabelframe", background=COLOR_FONDO, bordercolor=COLOR_BORDE)
    estilo.configure("TLabelframe.Label", background=COLOR_FONDO, foreground=COLOR_SUAVE,
                     font=(FUENTE, 9, "bold"))

    estilo.configure("TButton", font=(FUENTE, 9), padding=(6, 7))
    for nombre, color, activo in [("Principal", COLOR_ACENTO, "#1d4ed8"),
                                  ("Alarma", COLOR_PELIGRO, "#b91c1c")]:
        estilo.configure(nombre + ".TButton", font=(FUENTE, 10, "bold"), padding=(10, 9),
                         background=color, foreground="white", borderwidth=0)
        estilo.map(nombre + ".TButton", background=[("disabled", "#94a3b8"), ("active", activo)])

    estilo.configure("TMenubutton", font=(FUENTE, 9), padding=(6, 7))
    estilo.configure("TNotebook", background=COLOR_FONDO, borderwidth=0)
    estilo.configure("TNotebook.Tab", font=(FUENTE, 9, "bold"), padding=(14, 7))
    estilo.configure("Treeview", background="white", fieldbackground="white", rowheight=25,
                     font=(FUENTE, 9))
    estilo.configure("Treeview.Heading", font=(FUENTE, 9, "bold"), padding=(4, 5))


# =============================================================================
#  ToolTip
# =============================================================================

class ToolTip:
    """Muestra un texto de ayuda cuando el mouse se queda medio segundo sobre un widget."""

    def __init__(self, widget, texto, demora_ms=500):
        self.widget = widget
        self.texto = texto
        self.demora_ms = demora_ms
        self._programado = None
        self._ventana = None
        widget.bind("<Enter>", self._programar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")
        widget.bind("<ButtonPress>", self._ocultar, add="+")

    def _programar(self, evento=None):
        self._ocultar()
        self._programado = self.widget.after(self.demora_ms, self._mostrar)

    def _mostrar(self):
        self._programado = None
        if not self.widget.winfo_exists():
            return
        self._ventana = tk.Toplevel(self.widget)
        self._ventana.wm_overrideredirect(True)      # sin barra de título
        self._ventana.attributes("-topmost", True)
        self._ventana.wm_geometry("+{0}+{1}".format(self.widget.winfo_rootx() + 12,
                                                     self.widget.winfo_rooty() + self.widget.winfo_height() + 6))
        tk.Label(self._ventana, text=self.texto, background="#111827", foreground="white",
                 font=(FUENTE, 8), padx=8, pady=4, wraplength=260, justify="left").pack()

    def _ocultar(self, evento=None):
        if self._programado:
            self.widget.after_cancel(self._programado)
            self._programado = None
        if self._ventana is not None:
            self._ventana.destroy()
            self._ventana = None


# =============================================================================
#  Tabla con barra de desplazamiento
# =============================================================================

def crear_tabla(padre, columnas):
    """Crea un Treeview con scroll. columnas = [(clave, título, ancho), ...].

    Devuelve (contenedor, tabla): el contenedor es lo que se coloca en pantalla.
    """
    contenedor = ttk.Frame(padre)
    contenedor.columnconfigure(0, weight=1)
    contenedor.rowconfigure(0, weight=1)

    tabla = ttk.Treeview(contenedor, show="headings", selectmode="browse")
    tabla.grid(row=0, column=0, sticky="nsew")
    barra = ttk.Scrollbar(contenedor, orient="vertical", command=tabla.yview)
    barra.grid(row=0, column=1, sticky="ns")
    tabla.configure(yscrollcommand=barra.set)
    tabla.tag_configure("par", background="#f8fafc")

    configurar_columnas(tabla, columnas)
    return contenedor, tabla


def configurar_columnas(tabla, columnas):
    """Cambia las columnas de una tabla existente (la pestaña Detalle reutiliza una sola)."""
    tabla.configure(columns=[clave for clave, _, _ in columnas])
    for clave, titulo, ancho in columnas:
        tabla.heading(clave, text=titulo)
        tabla.column(clave, width=ancho, anchor="w")


# =============================================================================
#  Panel flotante de información
# =============================================================================

class PanelInformacion(tk.Frame):
    """Ficha de detalle que flota sobre la esquina superior derecha.

    Solo aparece cuando hay algo seleccionado y se cierra con la "×".
    Se coloca con place() para quedar por encima del mapa y de las tablas.
    posicion_y es una función que dice a qué altura colocarlo (así no tapa la
    barra de acción ni el aviso de alarma).
    """

    def __init__(self, padre, al_cerrar, posicion_y=lambda: 0):
        super().__init__(padre, bg=COLOR_PANEL, highlightbackground=COLOR_BORDE, highlightthickness=1)
        self._posicion_y = posicion_y

        encabezado = tk.Frame(self, bg=COLOR_PANEL)
        encabezado.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(encabezado, text="INFORMACIÓN", bg=COLOR_PANEL, fg=COLOR_SUAVE,
                 font=(FUENTE, 9, "bold")).pack(side="left")
        cerrar = tk.Button(encabezado, text="×", bg=COLOR_PANEL, fg=COLOR_SUAVE, bd=0,
                           activebackground=COLOR_PANEL, font=(FUENTE, 12, "bold"),
                           cursor="hand2", command=al_cerrar)
        cerrar.pack(side="right")
        ToolTip(cerrar, "Cerrar este panel.")

        self.texto = tk.Text(self, width=36, height=15, bg=COLOR_PANEL, fg=COLOR_TEXTO,
                             font=(FUENTE_MONO, 9), relief="flat", padx=8, pady=6, wrap="word",
                             state="disabled")
        self.texto.pack(fill="both", expand=True, padx=8, pady=8)
        self.texto.tag_configure("titulo", font=(FUENTE, 11, "bold"), foreground=COLOR_ACENTO)
        self.texto.tag_configure("tenue", foreground=COLOR_SUAVE)
        self.texto.tag_configure("alarma", foreground=COLOR_PELIGRO, font=(FUENTE_MONO, 9, "bold"))

    @property
    def visible(self):
        return bool(self.place_info())

    def mostrar(self, titulo, filas):
        """filas = [(etiqueta, valor), ...]. Un valor que empieza con "⚠" se pinta en rojo."""
        self._empezar()
        self.texto.insert("end", titulo + "\n\n", "titulo")
        for etiqueta, valor in filas:
            estilo = "alarma" if str(valor).startswith("⚠") else ()
            self.texto.insert("end", "{0:<13}{1}\n".format(etiqueta + ":", formatear(valor)), estilo)
        self._terminar()

    def mostrar_texto(self, mensaje):
        self._empezar()
        self.texto.insert("end", mensaje, "tenue")
        self._terminar()

    def ocultar(self):
        self.place_forget()

    def _empezar(self):
        self.texto.config(state="normal")
        self.texto.delete("1.0", "end")

    def _terminar(self):
        self.texto.config(state="disabled")
        self.reubicar()

    def reubicar(self):
        """Coloca el panel en la esquina derecha, a la altura que indique posicion_y()."""
        self.place(relx=1.0, y=self._posicion_y(), anchor="ne", width=320, height=350)
        self.lift()


# =============================================================================
#  Ventana de notificaciones
# =============================================================================

class VentanaNotificaciones(tk.Toplevel):
    """Historial de notificaciones de la sesión (la más reciente arriba)."""

    def __init__(self, padre, al_limpiar):
        super().__init__(padre)
        self.title("Notificaciones de la sesión")
        self.geometry("480x480")
        self.configure(bg=COLOR_FONDO)

        self.texto = tk.Text(self, bg=COLOR_PANEL, font=(FUENTE, 9), relief="flat", padx=10,
                             pady=8, wrap="word", state="disabled")
        self.texto.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        for nivel, color in COLOR_NIVEL.items():
            self.texto.tag_configure(nivel, foreground=color)
        self.texto.tag_configure("hora", foreground=COLOR_SUAVE, font=(FUENTE_MONO, 8))
        ttk.Button(self, text="Limpiar notificaciones", command=al_limpiar).pack(pady=8)

    def actualizar(self, notificaciones):
        """notificaciones = [(hora, nivel, texto), ...]"""
        self.texto.config(state="normal")
        self.texto.delete("1.0", "end")
        if not notificaciones:
            self.texto.insert("end", "Sin notificaciones todavía.")
        for hora, nivel, texto in notificaciones:
            self.texto.insert("end", hora + "  ", "hora")
            self.texto.insert("end", texto + "\n", nivel)
        self.texto.config(state="disabled")
