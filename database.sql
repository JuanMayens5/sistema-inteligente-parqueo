/* =============================================================================
   SISTEMA INTELIGENTE DE PARQUEO
   Universidad Mariano Gálvez - Ingeniería en Sistemas - Sexto Semestre
   Motor: SQL Server (probado con SQL Server 2019+)

   Este script crea:
     1. Catálogos (tipos de vehículo, tipos de espacio, compatibilidad)
     2. Tablas principales (espacios, vehiculos, ocupaciones)
     3. Tablas de seguridad y electrónica (alarmas, eventos_sensor)
     4. Bitácora de comandos (integración con el lenguaje formal)
     5. Vistas de consulta
     6. Procedimientos almacenados, uno por cada comando del lenguaje
============================================================================= */

IF DB_ID('SistemaInteligenteParqueo') IS NULL
    CREATE DATABASE SistemaInteligenteParqueo;
GO

USE SistemaInteligenteParqueo;
GO

/* -----------------------------------------------------------------------------
   0. LIMPIEZA (permite volver a ejecutar el script desde cero)
----------------------------------------------------------------------------- */
DROP TABLE IF EXISTS dbo.bitacora_comandos;
DROP TABLE IF EXISTS dbo.eventos_sensor;
DROP TABLE IF EXISTS dbo.alarmas;
DROP TABLE IF EXISTS dbo.ocupaciones;
DROP TABLE IF EXISTS dbo.vehiculos;
DROP TABLE IF EXISTS dbo.espacios;
DROP TABLE IF EXISTS dbo.compatibilidad;
DROP TABLE IF EXISTS dbo.tipos_espacio;
DROP TABLE IF EXISTS dbo.tipos_vehiculo;
GO


/* =============================================================================
   1. CATÁLOGOS
============================================================================= */

CREATE TABLE dbo.tipos_vehiculo (
    codigo      VARCHAR(20) NOT NULL CONSTRAINT PK_tipos_vehiculo PRIMARY KEY,
    descripcion VARCHAR(60) NOT NULL
);

CREATE TABLE dbo.tipos_espacio (
    codigo      VARCHAR(20) NOT NULL CONSTRAINT PK_tipos_espacio PRIMARY KEY,
    descripcion VARCHAR(60) NOT NULL
);

/* Regla de negocio como DATOS, no quemada en el código Python:
   qué tipo de vehículo puede ocupar qué tipo de espacio y con qué prioridad.
   prioridad 1 = opción ideal, 2 = alternativa, etc.                          */
CREATE TABLE dbo.compatibilidad (
    tipo_vehiculo VARCHAR(20) NOT NULL,
    tipo_espacio  VARCHAR(20) NOT NULL,
    prioridad     TINYINT     NOT NULL CONSTRAINT DF_comp_prioridad DEFAULT 1,
    CONSTRAINT PK_compatibilidad PRIMARY KEY (tipo_vehiculo, tipo_espacio),
    CONSTRAINT FK_comp_vehiculo FOREIGN KEY (tipo_vehiculo)
        REFERENCES dbo.tipos_vehiculo(codigo),
    CONSTRAINT FK_comp_espacio  FOREIGN KEY (tipo_espacio)
        REFERENCES dbo.tipos_espacio(codigo)
);
GO


/* =============================================================================
   2. TABLAS PRINCIPALES
============================================================================= */

CREATE TABLE dbo.espacios (
    id                INT IDENTITY(1,1) CONSTRAINT PK_espacios PRIMARY KEY,
    codigo            VARCHAR(10) NOT NULL CONSTRAINT UQ_espacios_codigo UNIQUE,
    tipo_espacio      VARCHAR(20) NOT NULL,
    sector            VARCHAR(20) NULL,

    /* DISPONIBLE  -> libre
       ASIGNADO    -> el sistema lo reservó, el vehículo aún no llega
       OCUPADO     -> el sensor confirmó la llegada (LLEGADA)
       FUERA_DE_SERVICIO -> mantenimiento                                     */
    estado            VARCHAR(20) NOT NULL CONSTRAINT DF_espacios_estado DEFAULT 'DISPONIBLE',

    /* --- Electrónica Digital: estado del hardware de cada espacio --- */
    direccion_hw      VARCHAR(20) NULL,   -- pin / dirección del nodo o Arduino
    led_estado        VARCHAR(10) NOT NULL CONSTRAINT DF_espacios_led DEFAULT 'VERDE',
    sensor_ocupacion  BIT NOT NULL CONSTRAINT DF_espacios_socup DEFAULT 0,
    sensor_movimiento BIT NOT NULL CONSTRAINT DF_espacios_smov  DEFAULT 0,

    activo            BIT NOT NULL CONSTRAINT DF_espacios_activo DEFAULT 1,

    CONSTRAINT FK_espacios_tipo FOREIGN KEY (tipo_espacio)
        REFERENCES dbo.tipos_espacio(codigo),
    CONSTRAINT CK_espacios_estado CHECK
        (estado IN ('DISPONIBLE','ASIGNADO','OCUPADO','FUERA_DE_SERVICIO')),
    CONSTRAINT CK_espacios_led CHECK
        (led_estado IN ('VERDE','AMARILLO','ROJO','PARPADEO','APAGADO'))
);

CREATE TABLE dbo.vehiculos (
    id             INT IDENTITY(1,1) CONSTRAINT PK_vehiculos PRIMARY KEY,
    placa          VARCHAR(20) NOT NULL CONSTRAINT UQ_vehiculos_placa UNIQUE,
    tipo_vehiculo  VARCHAR(20) NOT NULL,
    fecha_registro DATETIME2 NOT NULL CONSTRAINT DF_vehiculos_fecha DEFAULT SYSDATETIME(),
    CONSTRAINT FK_vehiculos_tipo FOREIGN KEY (tipo_vehiculo)
        REFERENCES dbo.tipos_vehiculo(codigo)
);

CREATE TABLE dbo.ocupaciones (
    id                 INT IDENTITY(1,1) CONSTRAINT PK_ocupaciones PRIMARY KEY,
    vehiculo_id        INT NOT NULL,
    espacio_id         INT NOT NULL,

    /* Ciclo de vida completo del comando:
       ASIGNADA -> OCUPADA -> AUTORIZADA -> FINALIZADA (o CANCELADA)          */
    estado             VARCHAR(15) NOT NULL CONSTRAINT DF_ocup_estado DEFAULT 'ASIGNADA',

    fecha_asignacion   DATETIME2 NOT NULL CONSTRAINT DF_ocup_fasig DEFAULT SYSDATETIME(),
    fecha_llegada      DATETIME2 NULL,
    fecha_autorizacion DATETIME2 NULL,
    fecha_salida       DATETIME2 NULL,

    seguridad_activa   BIT NOT NULL CONSTRAINT DF_ocup_seg DEFAULT 0,
    autorizado_por     VARCHAR(40) NULL,

    CONSTRAINT FK_ocup_vehiculo FOREIGN KEY (vehiculo_id) REFERENCES dbo.vehiculos(id),
    CONSTRAINT FK_ocup_espacio  FOREIGN KEY (espacio_id)  REFERENCES dbo.espacios(id),
    CONSTRAINT CK_ocup_estado CHECK
        (estado IN ('ASIGNADA','OCUPADA','AUTORIZADA','FINALIZADA','CANCELADA')),
    CONSTRAINT CK_ocup_fechas CHECK
        (fecha_salida IS NULL OR fecha_salida >= fecha_asignacion)
);

/* Un espacio NO puede tener dos ocupaciones vivas al mismo tiempo.
   Un vehículo NO puede estar en dos espacios al mismo tiempo.
   Los índices filtrados hacen que el motor lo garantice, no el código Python. */
CREATE UNIQUE INDEX UX_ocupaciones_espacio_activo
    ON dbo.ocupaciones(espacio_id)
    WHERE estado IN ('ASIGNADA','OCUPADA','AUTORIZADA');

CREATE UNIQUE INDEX UX_ocupaciones_vehiculo_activo
    ON dbo.ocupaciones(vehiculo_id)
    WHERE estado IN ('ASIGNADA','OCUPADA','AUTORIZADA');
GO


/* =============================================================================
   3. SEGURIDAD Y ELECTRÓNICA
============================================================================= */

/* La alarma se liga a la OCUPACIÓN, y por eso la aplicación siempre puede
   decir QUÉ VEHÍCULO la está generando (requerimiento del enunciado).        */
CREATE TABLE dbo.alarmas (
    id            INT IDENTITY(1,1) CONSTRAINT PK_alarmas PRIMARY KEY,
    espacio_id    INT NOT NULL,
    ocupacion_id  INT NULL,
    tipo          VARCHAR(30) NOT NULL CONSTRAINT DF_alarmas_tipo DEFAULT 'MOVIMIENTO_NO_AUTORIZADO',
    estado        VARCHAR(10) NOT NULL CONSTRAINT DF_alarmas_estado DEFAULT 'ACTIVA',
    fecha_inicio  DATETIME2 NOT NULL CONSTRAINT DF_alarmas_ini DEFAULT SYSDATETIME(),
    fecha_fin     DATETIME2 NULL,
    apagada_por   VARCHAR(40) NULL,
    descripcion   VARCHAR(200) NULL,

    CONSTRAINT FK_alarmas_espacio   FOREIGN KEY (espacio_id)   REFERENCES dbo.espacios(id),
    CONSTRAINT FK_alarmas_ocupacion FOREIGN KEY (ocupacion_id) REFERENCES dbo.ocupaciones(id),
    CONSTRAINT CK_alarmas_estado CHECK (estado IN ('ACTIVA','APAGADA')),
    CONSTRAINT CK_alarmas_tipo   CHECK (tipo IN
        ('MOVIMIENTO_NO_AUTORIZADO','SALIDA_NO_AUTORIZADA','SENSOR_INCONSISTENTE'))
);

/* Solo una alarma activa por espacio */
CREATE UNIQUE INDEX UX_alarmas_espacio_activa
    ON dbo.alarmas(espacio_id)
    WHERE estado = 'ACTIVA';

/* Historial crudo de lo que reportan los sensores (evidencia para la demo) */
CREATE TABLE dbo.eventos_sensor (
    id          BIGINT IDENTITY(1,1) CONSTRAINT PK_eventos_sensor PRIMARY KEY,
    espacio_id  INT NOT NULL,
    tipo_sensor VARCHAR(15) NOT NULL,
    valor       BIT NOT NULL,
    fecha       DATETIME2 NOT NULL CONSTRAINT DF_eventos_fecha DEFAULT SYSDATETIME(),
    CONSTRAINT FK_eventos_espacio FOREIGN KEY (espacio_id) REFERENCES dbo.espacios(id),
    CONSTRAINT CK_eventos_tipo CHECK (tipo_sensor IN ('OCUPACION','MOVIMIENTO'))
);

CREATE INDEX IX_eventos_espacio_fecha ON dbo.eventos_sensor(espacio_id, fecha DESC);
GO


/* =============================================================================
   4. BITÁCORA DE COMANDOS (curso de Autómatas y Lenguajes Formales)
   Guarda cada instrucción que entra al intérprete y en qué fase falló.
============================================================================= */

CREATE TABLE dbo.bitacora_comandos (
    id             BIGINT IDENTITY(1,1) CONSTRAINT PK_bitacora PRIMARY KEY,
    texto_original VARCHAR(300) NOT NULL,
    comando        VARCHAR(30) NULL,          -- REGISTRAR, ASIGNAR, ...
    parametros     VARCHAR(200) NULL,
    resultado      VARCHAR(25) NOT NULL,
    mensaje        VARCHAR(300) NULL,
    usuario        VARCHAR(40) NULL,
    fecha          DATETIME2 NOT NULL CONSTRAINT DF_bitacora_fecha DEFAULT SYSDATETIME(),
    CONSTRAINT CK_bitacora_resultado CHECK (resultado IN
        ('OK','ERROR_LEXICO','ERROR_SINTACTICO','ERROR_SEMANTICO','ERROR_EJECUCION'))
);
GO


/* =============================================================================
   5. DATOS INICIALES
============================================================================= */

INSERT INTO dbo.tipos_vehiculo (codigo, descripcion) VALUES
    ('COMPACTO',    'Vehículo compacto'),
    ('GRANDE',      'Vehículo grande / SUV / pick-up'),
    ('MOTOCICLETA', 'Motocicleta'),
    ('CARGA',       'Vehículo de carga y descarga'),
    ('RESERVADO',   'Vehículo con espacio reservado');

INSERT INTO dbo.tipos_espacio (codigo, descripcion) VALUES
    ('COMPACTO',       'Espacio para vehículo compacto'),
    ('GRANDE',         'Espacio para vehículo grande'),
    ('MOTOCICLETA',    'Espacio para motocicleta'),
    ('CARGA_DESCARGA', 'Espacio de carga y descarga'),
    ('RESERVADO',      'Espacio reservado');

INSERT INTO dbo.compatibilidad (tipo_vehiculo, tipo_espacio, prioridad) VALUES
    ('COMPACTO',    'COMPACTO',       1),
    ('COMPACTO',    'GRANDE',         2),   -- si no hay compactos, cabe en uno grande
    ('GRANDE',      'GRANDE',         1),
    ('MOTOCICLETA', 'MOTOCICLETA',    1),
    ('MOTOCICLETA', 'COMPACTO',       2),
    ('CARGA',       'CARGA_DESCARGA', 1),
    ('RESERVADO',   'RESERVADO',      1);

INSERT INTO dbo.espacios (codigo, tipo_espacio, sector, direccion_hw) VALUES
    ('C-01', 'COMPACTO',       'A', 'PIN-02'),
    ('C-02', 'COMPACTO',       'A', 'PIN-03'),
    ('C-03', 'COMPACTO',       'A', 'PIN-04'),
    ('G-01', 'GRANDE',         'B', 'PIN-05'),
    ('G-02', 'GRANDE',         'B', 'PIN-06'),
    ('M-01', 'MOTOCICLETA',    'C', 'PIN-07'),
    ('M-02', 'MOTOCICLETA',    'C', 'PIN-08'),
    ('CD-01','CARGA_DESCARGA', 'D', 'PIN-09'),
    ('R-01', 'RESERVADO',      'D', 'PIN-10');
GO


/* =============================================================================
   6. VISTAS
============================================================================= */

/* Respuesta directa del comando CONSULTAR() */
CREATE OR ALTER VIEW dbo.vw_estado_parqueo AS
SELECT
    e.codigo            AS espacio,
    e.tipo_espacio      AS tipo,
    e.sector,
    e.estado,
    e.led_estado,
    v.placa             AS placa_vehiculo,
    v.tipo_vehiculo,
    o.estado            AS estado_ocupacion,
    o.fecha_asignacion,
    o.fecha_llegada,
    CASE WHEN a.id IS NULL THEN 'NO' ELSE 'SI' END AS alarma_activa
FROM dbo.espacios e
LEFT JOIN dbo.ocupaciones o
       ON o.espacio_id = e.id
      AND o.estado IN ('ASIGNADA','OCUPADA','AUTORIZADA')
LEFT JOIN dbo.vehiculos v ON v.id = o.vehiculo_id
LEFT JOIN dbo.alarmas   a ON a.espacio_id = e.id AND a.estado = 'ACTIVA';
GO

/* Qué vehículo está generando cada alarma */
CREATE OR ALTER VIEW dbo.vw_alarmas_activas AS
SELECT
    a.id AS alarma_id,
    e.codigo AS espacio,
    v.placa,
    v.tipo_vehiculo,
    a.tipo,
    a.fecha_inicio,
    a.descripcion
FROM dbo.alarmas a
JOIN dbo.espacios e ON e.id = a.espacio_id
LEFT JOIN dbo.ocupaciones o ON o.id = a.ocupacion_id
LEFT JOIN dbo.vehiculos   v ON v.id = o.vehiculo_id
WHERE a.estado = 'ACTIVA';
GO


/* =============================================================================
   7. PROCEDIMIENTOS = COMANDOS DEL LENGUAJE FORMAL
   Todos devuelven una sola fila: resultado, mensaje (+ dato extra si aplica),
   para que el intérprete en Python solo lea cursor.fetchone().
============================================================================= */

/* ---------- REGISTRAR(tipo, placa) ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_registrar_vehiculo
    @placa VARCHAR(20),
    @tipo  VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SET @placa = UPPER(LTRIM(RTRIM(@placa)));
    SET @tipo  = UPPER(LTRIM(RTRIM(@tipo)));

    IF NOT EXISTS (SELECT 1 FROM dbo.tipos_vehiculo WHERE codigo = @tipo)
    BEGIN
        SELECT 'TIPO_INVALIDO' AS resultado,
               'El tipo de vehículo no existe en el catálogo.' AS mensaje;
        RETURN;
    END

    IF EXISTS (SELECT 1 FROM dbo.vehiculos WHERE placa = @placa)
    BEGIN
        SELECT 'YA_REGISTRADO' AS resultado,
               'La placa ya se encontraba registrada.' AS mensaje;
        RETURN;
    END

    INSERT INTO dbo.vehiculos (placa, tipo_vehiculo) VALUES (@placa, @tipo);

    SELECT 'OK' AS resultado, 'Vehículo registrado correctamente.' AS mensaje;
END
GO


/* ---------- ASIGNAR(placa) ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_asignar_espacio
    @placa VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET @placa = UPPER(LTRIM(RTRIM(@placa)));

    DECLARE @vehiculo_id INT, @tipo VARCHAR(20), @espacio_id INT, @codigo VARCHAR(10);

    SELECT @vehiculo_id = id, @tipo = tipo_vehiculo
    FROM dbo.vehiculos WHERE placa = @placa;

    IF @vehiculo_id IS NULL
    BEGIN
        SELECT 'VEHICULO_NO_ENCONTRADO' AS resultado,
               'El vehículo no está registrado.' AS mensaje,
               CAST(NULL AS VARCHAR(10)) AS codigo_espacio;
        RETURN;
    END

    IF EXISTS (SELECT 1 FROM dbo.ocupaciones
               WHERE vehiculo_id = @vehiculo_id
                 AND estado IN ('ASIGNADA','OCUPADA','AUTORIZADA'))
    BEGIN
        SELECT 'YA_TIENE_ESPACIO' AS resultado,
               'El vehículo ya tiene un espacio asignado.' AS mensaje,
               CAST(NULL AS VARCHAR(10)) AS codigo_espacio;
        RETURN;
    END

    BEGIN TRANSACTION;

        /* UPDLOCK evita que dos operadores tomen el mismo espacio a la vez */
        SELECT TOP 1 @espacio_id = e.id, @codigo = e.codigo
        FROM dbo.espacios e WITH (UPDLOCK, ROWLOCK)
        JOIN dbo.compatibilidad c ON c.tipo_espacio = e.tipo_espacio
        WHERE c.tipo_vehiculo = @tipo
          AND e.estado = 'DISPONIBLE'
          AND e.activo = 1
        ORDER BY c.prioridad, e.id;

        IF @espacio_id IS NULL
        BEGIN
            ROLLBACK TRANSACTION;
            SELECT 'SIN_ESPACIO' AS resultado,
                   'No hay espacios disponibles para este tipo de vehículo.' AS mensaje,
                   CAST(NULL AS VARCHAR(10)) AS codigo_espacio;
            RETURN;
        END

        INSERT INTO dbo.ocupaciones (vehiculo_id, espacio_id, estado)
        VALUES (@vehiculo_id, @espacio_id, 'ASIGNADA');

        UPDATE dbo.espacios
        SET estado = 'ASIGNADO', led_estado = 'AMARILLO'
        WHERE id = @espacio_id;

    COMMIT TRANSACTION;

    SELECT 'OK' AS resultado,
           'Espacio asignado. Esperando la llegada del vehículo.' AS mensaje,
           @codigo AS codigo_espacio;
END
GO


/* ---------- LLEGADA(placa) : confirma ocupación y ARMA la seguridad ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_llegada
    @placa VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET @placa = UPPER(LTRIM(RTRIM(@placa)));

    DECLARE @ocupacion_id INT, @espacio_id INT, @codigo VARCHAR(10);

    SELECT @ocupacion_id = o.id, @espacio_id = e.id, @codigo = e.codigo
    FROM dbo.ocupaciones o
    JOIN dbo.vehiculos v ON v.id = o.vehiculo_id
    JOIN dbo.espacios  e ON e.id = o.espacio_id
    WHERE v.placa = @placa AND o.estado = 'ASIGNADA';

    IF @ocupacion_id IS NULL
    BEGIN
        SELECT 'SIN_ASIGNACION' AS resultado,
               'El vehículo no tiene una asignación pendiente de llegada.' AS mensaje,
               CAST(NULL AS VARCHAR(10)) AS codigo_espacio;
        RETURN;
    END

    BEGIN TRANSACTION;

        UPDATE dbo.ocupaciones
        SET estado = 'OCUPADA',
            fecha_llegada = SYSDATETIME(),
            seguridad_activa = 1            -- activación automática de seguridad
        WHERE id = @ocupacion_id;

        UPDATE dbo.espacios
        SET estado = 'OCUPADO', led_estado = 'ROJO', sensor_ocupacion = 1
        WHERE id = @espacio_id;

        INSERT INTO dbo.eventos_sensor (espacio_id, tipo_sensor, valor)
        VALUES (@espacio_id, 'OCUPACION', 1);

    COMMIT TRANSACTION;

    SELECT 'OK' AS resultado,
           'Llegada confirmada. Sistema de seguridad activado.' AS mensaje,
           @codigo AS codigo_espacio;
END
GO


/* ---------- Reporte de movimiento desde el sensor ----------
   Si hay un vehículo con seguridad activa y sin autorización -> ALARMA.       */
CREATE OR ALTER PROCEDURE dbo.pa_registrar_movimiento
    @codigo_espacio VARCHAR(10)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @espacio_id INT, @ocupacion_id INT, @placa VARCHAR(20), @seguridad BIT;

    SELECT @espacio_id = id FROM dbo.espacios WHERE codigo = @codigo_espacio;

    IF @espacio_id IS NULL
    BEGIN
        SELECT 'ESPACIO_NO_ENCONTRADO' AS resultado,
               'El código de espacio no existe.' AS mensaje,
               CAST(NULL AS VARCHAR(20)) AS placa;
        RETURN;
    END

    INSERT INTO dbo.eventos_sensor (espacio_id, tipo_sensor, valor)
    VALUES (@espacio_id, 'MOVIMIENTO', 1);

    SELECT @ocupacion_id = o.id, @placa = v.placa, @seguridad = o.seguridad_activa
    FROM dbo.ocupaciones o
    JOIN dbo.vehiculos v ON v.id = o.vehiculo_id
    WHERE o.espacio_id = @espacio_id AND o.estado IN ('OCUPADA','AUTORIZADA');

    IF @ocupacion_id IS NULL OR @seguridad = 0
    BEGIN
        SELECT 'MOVIMIENTO_AUTORIZADO' AS resultado,
               'Movimiento registrado sin generar alarma.' AS mensaje,
               @placa AS placa;
        RETURN;
    END

    IF EXISTS (SELECT 1 FROM dbo.alarmas WHERE espacio_id = @espacio_id AND estado = 'ACTIVA')
    BEGIN
        SELECT 'ALARMA_YA_ACTIVA' AS resultado,
               'Ya existe una alarma activa en este espacio.' AS mensaje,
               @placa AS placa;
        RETURN;
    END

    BEGIN TRANSACTION;

        INSERT INTO dbo.alarmas (espacio_id, ocupacion_id, tipo, descripcion)
        VALUES (@espacio_id, @ocupacion_id, 'MOVIMIENTO_NO_AUTORIZADO',
                CONCAT('Movimiento no autorizado del vehículo ', @placa));

        UPDATE dbo.espacios SET led_estado = 'PARPADEO', sensor_movimiento = 1
        WHERE id = @espacio_id;

    COMMIT TRANSACTION;

    SELECT 'ALARMA_ACTIVADA' AS resultado,
           CONCAT('¡ALARMA! Movimiento no autorizado en ', @codigo_espacio) AS mensaje,
           @placa AS placa;
END
GO


/* ---------- APAGAR_ALARMA(placa) ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_apagar_alarma
    @placa   VARCHAR(20),
    @usuario VARCHAR(40) = 'OPERADOR'
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET @placa = UPPER(LTRIM(RTRIM(@placa)));

    DECLARE @alarma_id INT, @espacio_id INT;

    SELECT @alarma_id = a.id, @espacio_id = a.espacio_id
    FROM dbo.alarmas a
    JOIN dbo.ocupaciones o ON o.id = a.ocupacion_id
    JOIN dbo.vehiculos   v ON v.id = o.vehiculo_id
    WHERE v.placa = @placa AND a.estado = 'ACTIVA';

    IF @alarma_id IS NULL
    BEGIN
        SELECT 'SIN_ALARMA' AS resultado,
               'No hay una alarma activa para ese vehículo.' AS mensaje;
        RETURN;
    END

    BEGIN TRANSACTION;

        UPDATE dbo.alarmas
        SET estado = 'APAGADA', fecha_fin = SYSDATETIME(), apagada_por = @usuario
        WHERE id = @alarma_id;

        UPDATE dbo.espacios SET led_estado = 'ROJO', sensor_movimiento = 0
        WHERE id = @espacio_id;

    COMMIT TRANSACTION;

    SELECT 'OK' AS resultado, 'Alarma desactivada.' AS mensaje;
END
GO


/* ---------- AUTORIZAR_SALIDA(placa) ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_autorizar_salida
    @placa    VARCHAR(20),
    @operador VARCHAR(40) = 'OPERADOR'
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET @placa = UPPER(LTRIM(RTRIM(@placa)));

    DECLARE @ocupacion_id INT, @espacio_id INT;

    SELECT @ocupacion_id = o.id, @espacio_id = o.espacio_id
    FROM dbo.ocupaciones o
    JOIN dbo.vehiculos v ON v.id = o.vehiculo_id
    WHERE v.placa = @placa AND o.estado = 'OCUPADA';

    IF @ocupacion_id IS NULL
    BEGIN
        SELECT 'SIN_OCUPACION' AS resultado,
               'El vehículo no tiene una ocupación activa que autorizar.' AS mensaje;
        RETURN;
    END

    BEGIN TRANSACTION;

        UPDATE dbo.ocupaciones
        SET estado = 'AUTORIZADA',
            fecha_autorizacion = SYSDATETIME(),
            seguridad_activa = 0,           -- se desarma para que no suene la alarma
            autorizado_por = @operador
        WHERE id = @ocupacion_id;

        /* Si quedaba una alarma sonando, la autorización la cierra */
        UPDATE dbo.alarmas
        SET estado = 'APAGADA', fecha_fin = SYSDATETIME(), apagada_por = @operador
        WHERE espacio_id = @espacio_id AND estado = 'ACTIVA';

        UPDATE dbo.espacios SET led_estado = 'AMARILLO', sensor_movimiento = 0
        WHERE id = @espacio_id;

    COMMIT TRANSACTION;

    SELECT 'OK' AS resultado, 'Salida autorizada.' AS mensaje;
END
GO


/* ---------- SALIDA(placa) : libera el espacio ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_salida
    @placa VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET @placa = UPPER(LTRIM(RTRIM(@placa)));

    DECLARE @ocupacion_id INT, @espacio_id INT, @estado VARCHAR(15), @codigo VARCHAR(10);

    SELECT @ocupacion_id = o.id, @espacio_id = e.id, @estado = o.estado, @codigo = e.codigo
    FROM dbo.ocupaciones o
    JOIN dbo.vehiculos v ON v.id = o.vehiculo_id
    JOIN dbo.espacios  e ON e.id = o.espacio_id
    WHERE v.placa = @placa AND o.estado IN ('OCUPADA','AUTORIZADA');

    IF @ocupacion_id IS NULL
    BEGIN
        SELECT 'SIN_OCUPACION' AS resultado,
               'El vehículo no se encuentra dentro del parqueo.' AS mensaje,
               CAST(NULL AS VARCHAR(10)) AS codigo_espacio;
        RETURN;
    END

    /* Intento de salida sin autorización -> se genera alarma */
    IF @estado <> 'AUTORIZADA'
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM dbo.alarmas WHERE espacio_id = @espacio_id AND estado = 'ACTIVA')
        BEGIN
            INSERT INTO dbo.alarmas (espacio_id, ocupacion_id, tipo, descripcion)
            VALUES (@espacio_id, @ocupacion_id, 'SALIDA_NO_AUTORIZADA',
                    CONCAT('Intento de salida sin autorización del vehículo ', @placa));

            UPDATE dbo.espacios SET led_estado = 'PARPADEO' WHERE id = @espacio_id;
        END

        SELECT 'SALIDA_NO_AUTORIZADA' AS resultado,
               'La salida no ha sido autorizada por el operador. Alarma activada.' AS mensaje,
               @codigo AS codigo_espacio;
        RETURN;
    END

    BEGIN TRANSACTION;

        UPDATE dbo.ocupaciones
        SET estado = 'FINALIZADA', fecha_salida = SYSDATETIME(), seguridad_activa = 0
        WHERE id = @ocupacion_id;

        UPDATE dbo.espacios
        SET estado = 'DISPONIBLE',
            led_estado = 'VERDE',
            sensor_ocupacion = 0,
            sensor_movimiento = 0
        WHERE id = @espacio_id;

        INSERT INTO dbo.eventos_sensor (espacio_id, tipo_sensor, valor)
        VALUES (@espacio_id, 'OCUPACION', 0);

    COMMIT TRANSACTION;

    SELECT 'OK' AS resultado,
           'Salida registrada. El espacio quedó disponible.' AS mensaje,
           @codigo AS codigo_espacio;
END
GO


/* ---------- CONSULTAR() ---------- */
CREATE OR ALTER PROCEDURE dbo.pa_consultar
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM dbo.vw_estado_parqueo ORDER BY tipo, espacio;
END
GO


/* =============================================================================
   8. PRUEBA RÁPIDA (descomentar para probar el flujo completo)
============================================================================= */
/*
EXEC dbo.pa_registrar_vehiculo @placa = 'P123ABC', @tipo = 'COMPACTO';
EXEC dbo.pa_asignar_espacio    @placa = 'P123ABC';
EXEC dbo.pa_llegada            @placa = 'P123ABC';
EXEC dbo.pa_registrar_movimiento @codigo_espacio = 'C-01';   -- dispara alarma
SELECT * FROM dbo.vw_alarmas_activas;
EXEC dbo.pa_apagar_alarma      @placa = 'P123ABC', @usuario = 'CONTROL';
EXEC dbo.pa_salida             @placa = 'P123ABC';           -- rechazada
EXEC dbo.pa_autorizar_salida   @placa = 'P123ABC', @operador = 'CONTROL';
EXEC dbo.pa_salida             @placa = 'P123ABC';           -- ahora sí libera
EXEC dbo.pa_consultar;
*/
