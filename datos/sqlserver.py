"""
Origen de datos: SQL Server
===========================

Implementa el contrato de datos/contrato.py con pyodbc, contra la base
SistemaInteligenteParqueo que crea database.sql.

Reglas que sigue este módulo
----------------------------
* ESCRITURAS -> siempre por procedimiento almacenado (pa_*). Las reglas de
  negocio (qué espacio asignar, cuándo sonar una alarma, qué color lleva el
  LED...) viven en la base; aquí solo se llama al procedimiento y se empaqueta
  su respuesta en un Resultado. Única excepción: la bitácora, que es un
  INSERT directo porque es una tabla de solo inserción.
* LECTURAS -> vistas (vw_*) o SELECT con parámetros "?". Nunca se arma el SQL
  pegando el texto que escribe el usuario (eso permitiría inyección SQL).
* La conexión se abre con autocommit=True porque cada procedimiento maneja su
  propia transacción. Con autocommit=False, pyodbc dejaría una transacción
  abierta reteniendo los bloqueos (el UPDLOCK de pa_asignar_espacio) hasta un
  commit() que nadie haría.
* Si se cae la comunicación con el servidor se lanza ErrorConexion; los demás
  errores (por ejemplo, SQL mal escrito) NO se ocultan, para que fallen en las
  pruebas.

Flujo de una operación
----------------------
    asignar_espacio(conexion, "P123ABC")
      -> _procedimiento("EXEC dbo.pa_asignar_espacio @placa = ?", "P123ABC")
      -> ConexionSQL.ejecutar(...)            # devuelve [{'resultado': 'OK', ...}]
      -> Resultado("OK", "Espacio asignado...", "C-01")
"""

import re

import pyodbc

from datos.contrato import ErrorConexion, Resultado, normalizar

SEGUNDOS_PARA_CONECTAR = 3
SEGUNDOS_POR_CONSULTA = 10


# =============================================================================
#  Conexión
# =============================================================================

def cadena_conexion(config, base_datos=None):
    """Arma la cadena ODBC a partir de config_db.ini.

    base_datos permite apuntar a otra base (por ejemplo "master" o la base de
    pruebas) sin cambiar la configuración.
    """
    partes = [
        "DRIVER={%s}" % config.driver,
        "SERVER=%s" % config.servidor,
        "DATABASE=%s" % (base_datos or config.base_datos),
        # El Driver 18 cifra la conexión por defecto y el certificado de un
        # SQL Server local es autofirmado: sin esto la conexión se rechaza.
        "TrustServerCertificate=yes",
    ]
    if config.autenticacion == "windows":
        partes.append("Trusted_Connection=yes")
    else:
        partes += ["UID=" + _valor_odbc(config.usuario), "PWD=" + _valor_odbc(config.contrasena)]
    return ";".join(partes) + ";"


def _valor_odbc(texto):
    """Encierra un valor entre llaves para que un ';' en la contraseña no rompa la cadena."""
    return "{" + texto.replace("}", "}}") + "}"


class ConexionSQL:
    """Conexión a SQL Server con lo que la interfaz necesita saber de ella.

    Envuelve la conexión de pyodbc para poder reconectar sin crear un objeto
    nuevo (la interfaz guarda siempre la misma referencia) y para convertir
    los errores de comunicación en ErrorConexion.
    """

    def __init__(self, cadena, descripcion):
        self._cadena = cadena
        self._cnx = None
        self.descripcion = descripcion
        self.cancelacion_disponible = False
        self.reconectar()

    def reconectar(self):
        """Abre (o vuelve a abrir) la conexión. Lanza ErrorConexion si no puede."""
        self.close()
        try:
            self._cnx = pyodbc.connect(self._cadena, autocommit=True,
                                       timeout=SEGUNDOS_PARA_CONECTAR)
        except pyodbc.Error as error:
            raise ErrorConexion(_texto_de_error(error)) from error
        self._cnx.timeout = SEGUNDOS_POR_CONSULTA

        # pa_cancelar_ocupacion es una propuesta (Anexo A del plan): si el
        # encargado de la base ya lo creó, la interfaz muestra "Liberar espacio".
        fila = self.ejecutar("SELECT OBJECT_ID('dbo.pa_cancelar_ocupacion') AS id")[0]
        self.cancelacion_disponible = fila["id"] is not None

    def ejecutar(self, sql, *parametros):
        """Ejecuta una instrucción y devuelve sus filas como lista de diccionarios.

        Las instrucciones que no devuelven filas (INSERT) devuelven [].
        El cursor se libera solo al salir de la función; como todos los
        procedimientos usan SET NOCOUNT ON y devuelven un único resultado,
        fetchall() lo consume completo y la conexión queda libre.
        """
        if self._cnx is None:
            raise ErrorConexion("No hay conexión abierta con SQL Server.")
        try:
            cursor = self._cnx.execute(sql, *parametros)
            if cursor.description is None:
                return []
            columnas = [columna[0] for columna in cursor.description]
            return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        except pyodbc.Error as error:
            if not _es_error_de_conexion(error):
                raise
            self.close()
            raise ErrorConexion(_texto_de_error(error)) from error

    def close(self):
        if self._cnx is not None:
            try:
                self._cnx.close()
            except pyodbc.Error:
                pass    # la conexión ya estaba rota; no hay nada más que cerrar
            self._cnx = None


def _es_error_de_conexion(error):
    """True si el error indica que se perdió la comunicación con el servidor.

    Códigos SQLSTATE: 08xxx = conexión, HYT00/HYT01 = tiempo de espera agotado.
    """
    estado = str(error.args[0]) if error.args else ""
    return (isinstance(error, (pyodbc.OperationalError, pyodbc.InterfaceError))
            or estado.startswith(("08", "HYT")))


def _texto_de_error(error):
    """Mensaje de pyodbc sin los prefijos técnicos del driver ([Microsoft][ODBC...])."""
    texto = error.args[1] if len(error.args) > 1 else str(error)
    texto = re.sub(r"\[[^\]]*\]", "", texto).split("(SQL")[0]
    return texto.strip() or str(error)


def conectar_db(config):
    """Abre la conexión con los datos de config_db.ini. Lanza ErrorConexion si falla."""
    descripcion = "SQL Server · {0} / {1}".format(config.servidor, config.base_datos)
    return ConexionSQL(cadena_conexion(config), descripcion)


# =============================================================================
#  Escrituras (una función por procedimiento almacenado)
# =============================================================================

def _procedimiento(conexion, sql, *parametros):
    """Ejecuta un pa_* y convierte su única fila (resultado, mensaje[, dato]) en Resultado."""
    fila = conexion.ejecutar(sql, *parametros)[0]
    valores = list(fila.values())
    dato = valores[2] if len(valores) > 2 else None
    return Resultado(fila["resultado"], fila["mensaje"], dato)


def registrar_vehiculo(conexion, placa, tipo):
    """REGISTRAR -> OK | TIPO_INVALIDO | YA_REGISTRADO"""
    return _procedimiento(conexion, "EXEC dbo.pa_registrar_vehiculo @placa = ?, @tipo = ?",
                          placa, tipo)


def asignar_espacio(conexion, placa):
    """ASIGNAR -> OK (dato = espacio) | VEHICULO_NO_ENCONTRADO | YA_TIENE_ESPACIO | SIN_ESPACIO"""
    return _procedimiento(conexion, "EXEC dbo.pa_asignar_espacio @placa = ?", placa)


def registrar_llegada(conexion, placa):
    """LLEGADA -> OK (dato = espacio, arma la seguridad) | SIN_ASIGNACION"""
    return _procedimiento(conexion, "EXEC dbo.pa_llegada @placa = ?", placa)


def registrar_movimiento(conexion, codigo_espacio):
    """Sensor PIR -> ALARMA_ACTIVADA | ALARMA_YA_ACTIVA | MOVIMIENTO_AUTORIZADO |
    ESPACIO_NO_ENCONTRADO  (dato = placa del vehículo en ese espacio)"""
    return _procedimiento(conexion, "EXEC dbo.pa_registrar_movimiento @codigo_espacio = ?",
                          codigo_espacio)


def apagar_alarma(conexion, placa, usuario):
    """APAGAR_ALARMA -> OK | SIN_ALARMA  (la seguridad sigue armada)"""
    return _procedimiento(conexion, "EXEC dbo.pa_apagar_alarma @placa = ?, @usuario = ?",
                          placa, usuario)


def autorizar_salida(conexion, placa, operador):
    """AUTORIZAR_SALIDA -> OK (desarma la seguridad y cierra alarmas) | SIN_OCUPACION"""
    return _procedimiento(conexion, "EXEC dbo.pa_autorizar_salida @placa = ?, @operador = ?",
                          placa, operador)


def registrar_salida(conexion, placa):
    """SALIDA -> OK (dato = espacio liberado) | SIN_OCUPACION |
    SALIDA_NO_AUTORIZADA (genera alarma)"""
    return _procedimiento(conexion, "EXEC dbo.pa_salida @placa = ?", placa)


def soporta_cancelacion(conexion):
    """¿La base tiene pa_cancelar_ocupacion? Se revisa al conectar."""
    return conexion.cancelacion_disponible


def cancelar_ocupacion(conexion, codigo_espacio, usuario):
    """Liberación manual -> OK (dato = placa) | ESPACIO_YA_LIBRE | ESPACIO_NO_ENCONTRADO"""
    if not conexion.cancelacion_disponible:
        return Resultado("CANCELACION_NO_DISPONIBLE",
                         "La base de datos todavía no tiene pa_cancelar_ocupacion.", None)
    return _procedimiento(conexion,
                          "EXEC dbo.pa_cancelar_ocupacion @codigo_espacio = ?, @usuario = ?",
                          codigo_espacio, usuario)


def registrar_bitacora(conexion, texto, comando, parametros, resultado, mensaje, usuario):
    """Guarda una instrucción de la consola en bitacora_comandos.

    Los textos se recortan al tamaño de cada columna para que un comando muy
    largo no provoque el error "String or binary data would be truncated".
    """
    conexion.ejecutar(
        "INSERT INTO dbo.bitacora_comandos "
        "(texto_original, comando, parametros, resultado, mensaje, usuario) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        texto[:300], _recortar(comando, 30), _recortar(parametros, 200),
        resultado, _recortar(mensaje, 300), _recortar(usuario, 40))


def _recortar(texto, largo):
    return texto[:largo] if texto else None


# =============================================================================
#  Lecturas
# =============================================================================

def obtener_estado_parqueo(conexion):
    """Una fila por espacio (vista vw_estado_parqueo, vía el comando CONSULTAR)."""
    return conexion.ejecutar("EXEC dbo.pa_consultar")


def listar_tipos_vehiculo(conexion):
    filas = conexion.ejecutar("SELECT codigo FROM dbo.tipos_vehiculo ORDER BY codigo")
    return [fila["codigo"] for fila in filas]


def listar_vehiculos(conexion):
    """Todos los vehículos registrados y, si tienen, su espacio actual."""
    return conexion.ejecutar("""
        SELECT v.placa, v.tipo_vehiculo, v.fecha_registro,
               e.codigo AS espacio, o.estado AS estado_ocupacion
        FROM dbo.vehiculos v
        LEFT JOIN dbo.ocupaciones o
               ON o.vehiculo_id = v.id AND o.estado IN ('ASIGNADA','OCUPADA','AUTORIZADA')
        LEFT JOIN dbo.espacios e ON e.id = o.espacio_id
        ORDER BY v.id DESC""")


def listar_ocupaciones(conexion, solo_activas=True):
    """Ocupaciones activas (ASIGNADA/OCUPADA/AUTORIZADA) o el historial completo."""
    return conexion.ejecutar("""
        SELECT o.id, v.placa, v.tipo_vehiculo, e.codigo AS espacio, o.estado,
               o.fecha_asignacion, o.fecha_llegada, o.fecha_autorizacion,
               o.fecha_salida, o.autorizado_por
        FROM dbo.ocupaciones o
        JOIN dbo.vehiculos v ON v.id = o.vehiculo_id
        JOIN dbo.espacios  e ON e.id = o.espacio_id
        WHERE ? = 0 OR o.estado IN ('ASIGNADA','OCUPADA','AUTORIZADA')
        ORDER BY o.id DESC""", 1 if solo_activas else 0)


def listar_alarmas_activas(conexion):
    """Alarmas sonando y qué vehículo las genera (vista vw_alarmas_activas)."""
    return conexion.ejecutar("""
        SELECT alarma_id, espacio, placa, tipo_vehiculo, tipo, fecha_inicio, descripcion
        FROM dbo.vw_alarmas_activas
        ORDER BY alarma_id DESC""")


def listar_eventos_sensor(conexion, limite=100):
    """Últimos eventos reportados por los sensores (el más reciente primero)."""
    return conexion.ejecutar("""
        SELECT TOP (?) ev.id, e.codigo AS espacio, ev.tipo_sensor, ev.valor, ev.fecha
        FROM dbo.eventos_sensor ev
        JOIN dbo.espacios e ON e.id = ev.espacio_id
        ORDER BY ev.id DESC""", limite)


def listar_bitacora(conexion, limite=100):
    """Últimas instrucciones de la consola (la más reciente primero)."""
    return conexion.ejecutar("""
        SELECT TOP (?) id, fecha, texto_original, comando, parametros,
               resultado, mensaje, usuario
        FROM dbo.bitacora_comandos
        ORDER BY id DESC""", limite)


def buscar_vehiculo(conexion, placa):
    """Ficha completa de un vehículo: datos, ocupación activa y alarma. None si no existe."""
    filas = conexion.ejecutar("""
        SELECT v.placa, v.tipo_vehiculo, v.fecha_registro,
               e.codigo AS espacio, e.tipo_espacio, o.estado AS estado_ocupacion,
               o.fecha_asignacion, o.fecha_llegada, o.fecha_autorizacion,
               o.autorizado_por, o.seguridad_activa,
               CASE WHEN a.id IS NULL THEN 'NO' ELSE 'SI' END AS alarma_activa,
               a.tipo AS tipo_alarma
        FROM dbo.vehiculos v
        LEFT JOIN dbo.ocupaciones o
               ON o.vehiculo_id = v.id AND o.estado IN ('ASIGNADA','OCUPADA','AUTORIZADA')
        LEFT JOIN dbo.espacios e ON e.id = o.espacio_id
        LEFT JOIN dbo.alarmas  a ON a.ocupacion_id = o.id AND a.estado = 'ACTIVA'
        WHERE v.placa = ?""", normalizar(placa))
    return filas[0] if filas else None
