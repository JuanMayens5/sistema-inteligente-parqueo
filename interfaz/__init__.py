"""
Interfaz gráfica (Tkinter)
==========================

    app.py              AppParqueo: la ventana principal y el "controlador".
                        Habla con la base, guarda el estado y reparte los datos
                        a las vistas. Todas las acciones (registrar, asignar...)
                        están aquí.
    vista_operacion.py  Modo Operación: barra de acción rápida, aviso de alarma,
                        mapa de espacios y última notificación.
    vista_avanzada.py   Modo Avanzado: tablas de detalle, consola del lenguaje y
                        simulador de sensores.
    componentes.py      Colores, estilos y piezas reutilizables (tooltip, tabla,
                        panel de información, ventana de notificaciones).

Regla de diseño: las vistas NUNCA hablan con la base de datos. Reciben los
datos ya leídos por AppParqueo y, cuando el usuario hace algo, llaman a un
método de AppParqueo (self.app.accion_...).
"""
