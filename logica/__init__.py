"""
Lógica de la aplicación (no depende de Tkinter ni de SQL Server)
================================================================

    mensajes.py          traduce los códigos de resultado a textos en español
    interprete.py        consola del lenguaje: analiza, ejecuta y registra en bitácora
    eventos_hardware.py  traduce eventos de sensores (simulador / ESP32) a procedimientos
                         y calcula los comandos PY:... para los LEDs y la alarma física

Todo lo de este paquete recibe el origen de datos ("db") como parámetro, así
que funciona igual con SQL Server y con el modo demostración.
"""
