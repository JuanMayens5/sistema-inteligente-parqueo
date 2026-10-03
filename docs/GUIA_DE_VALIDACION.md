# Guía de validación — Sistema Inteligente de Parqueo

Pasos para comprobar, de principio a fin, que la aplicación funciona antes de
entregarla. Tiempo estimado: **40 a 50 minutos**. Marca cada casilla al
terminar. Si algo no da lo esperado, anota el paso y revisa
[Solución de problemas](../README.md#solución-de-problemas).

Todos los comandos se ejecutan desde la carpeta principal del proyecto.

---

## Parte 0 · Preparación

### 0.1 Entorno

- [ ] Instalar la dependencia:

  ```bash
  pip install -r requirements.txt
  ```

- [ ] Comprobar la conexión. Todo debe salir `[OK]`:

  ```bash
  python herramientas/verificar_conexion.py
  ```

  Esperado: driver, conexión, 9 espacios, 5 tipos, procedimientos y acentos en `OK`.
  La línea `pa_cancelar_ocupacion ... no existe todavía` es normal.

### 0.2 Pruebas automáticas (5 minutos)

Usan una base aparte (`SistemaInteligenteParqueo_Pruebas`); **no tocan tu base real**.

- [ ] Datos, consola y eventos de sensores:

  ```bash
  python pruebas/prueba_backend.py
  ```

  Esperado al final: `38/38 casos correctos` para memoria y `38/38` para SQL Server.

- [ ] Interfaz completa:

  ```bash
  python pruebas/prueba_interfaz.py --sqlserver
  ```

  Esperado: `10/10 verificaciones correctas, 0 errores inesperados`. Durante la
  prueba se abre y se cierra una ventana sola; no la toques.

### 0.3 Dejar la base limpia para la validación manual

> ⚠️ Borra **todos** los vehículos, ocupaciones, alarmas y la bitácora de tu
> base de desarrollo. Hazlo solo si esos datos no te importan.

- [ ] Reiniciar la base (pide confirmación, escribe `SI`):

  ```bash
  python herramientas/reiniciar_base.py
  ```

- [ ] Abrir la aplicación:

  ```bash
  python main.py
  ```

  Esperado: 9 espacios verdes. Indicadores: **9 Disponibles · 0 Asignados · 0
  Ocupados · 0 Alarmas**. Abajo: `● Conectado · SQL Server · localhost /
  SistemaInteligenteParqueo`.

---

## Parte A · Ciclo normal de un vehículo (modo Operación)

Usa la placa `P123ABC`, tipo `COMPACTO`. Después de cada paso, mira el botón
azul, el mapa y los indicadores.

| # | Acción | Resultado esperado |
|---|---|---|
| A1 | Escribe `p123abc` (en minúsculas) | Se convierte a `P123ABC`. El botón dice **Registrar y asignar espacio** |
| A2 | Clic en el botón azul | Notificación "Espacio C-01 asignado". `C-01` en **amarillo** ("Asignado") con su LED amarillo. Indicadores: 8 disp · 1 asignado. El botón pasa a **Registrar llegada**. Se abre el panel de información |
| A3 | Clic en el botón azul | `C-01` en **rojo** ("Ocupado"), LED rojo. Botón: **Autorizar salida**. En el panel: Seguridad **armada** |
| A4 | Clic en el botón azul | `C-01` en **azul** ("Saliendo"). Botón: **Registrar salida**. Panel: "Autorizada: hora · CONTROL" |
| A5 | Clic en el botón azul | `C-01` vuelve a **verde**. 9 disponibles. El botón regresa a "Asignar espacio" (el vehículo sigue registrado) |

- [ ] A1 a A5 correctos

Pruebas de uso del mapa y la barra:

- [ ] Clic en una tarjeta del mapa: se abre el panel con sector, estado y LED; si
  tiene vehículo, la placa pasa al campo de placa.
- [ ] Pasar el mouse sobre botones, indicadores y tarjetas muestra ayuda (tooltip).
- [ ] `×` del panel lo cierra. `(?)` junto a "Mapa de espacios" muestra la leyenda de colores.
- [ ] **⋯ Más acciones**: *Solo registrar*, *Buscar vehículo*, *Actualizar vista* y *Limpiar campos* funcionan.
- [ ] El botón 🔔 y **Ver todas** abren el historial de notificaciones; ahí se pueden limpiar.

---

## Parte B · Alarmas y seguridad

Con `P123ABC` otra vez: A2 y A3 (asignar y llegada), para que `C-01` quede **Ocupado**.

Ve a **⚙ Modo avanzado → Simulador de sensores**. **Elige `C-01` en el selector
"Espacio"** (por defecto aparece `CD-01`).

| # | Acción | Resultado esperado |
|---|---|---|
| B1 | Botón **Movimiento (PIR)** | Alarma. El registro muestra `ESP:MOVIMIENTO:C-01`, `ALARMA_ACTIVADA` y los comandos `PY:LED:C-01:PARPADEO` y `PY:ALARMA:ON`. Suena la campana del sistema |
| B2 | **← Volver a operación** | Franja **roja** sobre el mapa: "C-01 · Movimiento no autorizado del vehículo P123ABC". Indicador **Alarmas = 1** en rojo. `C-01` con borde rojo parpadeante y ⚠ |
| B3 | Botón azul (ahora **rojo**: "Apagar alarma") | Alarma apagada, franja desaparece, Alarmas = 0. La seguridad **sigue armada**: el botón vuelve a "Autorizar salida" |
| B4 | En el simulador: **Se fue el vehículo** | Alarma por **salida no autorizada**. El espacio sigue ocupado |
| B5 | **Apagar alarma** y luego **Autorizar salida** | Sin alarmas; `C-01` "Saliendo" |
| B6 | En el simulador: **Movimiento (PIR)** | **No** hay alarma ("movimiento registrado sin generar alarma"): la seguridad ya está desarmada |
| B7 | **Registrar salida** | `C-01` libre y verde |

- [ ] B1 a B7 correctos

También prueba el flujo con el botón físico simulado: asigna y registra la
llegada de otro vehículo, y en el simulador usa **Botón físico de salida** →
queda "Saliendo" y en el panel aparece `BOTON_FISICO` como quien autorizó.

- [ ] Botón físico simulado correcto

---

## Parte C · Casos de error (mensajes claros, sin cierres)

| # | Acción | Resultado esperado |
|---|---|---|
| C1 | Placa vacía + botón azul | Aviso "Debes ingresar la placa" |
| C2 | Registrar `P123ABC` otra vez (campo de placa + **Solo registrar**) | Aviso "La placa P123ABC ya estaba registrada" |
| C3 | Placa de 25 caracteres | Aviso de que no puede pasar de 20 |
| C4 | Registrar dos vehículos de tipo **CARGA** y asignar ambos | El primero recibe `CD-01`; el segundo: "No hay espacios disponibles para vehículos tipo CARGA" |
| C5 | **Buscar vehículo** con una placa que no existe | Mensaje de que no existe |

- [ ] C1 a C5 correctos

### Compatibilidad entre tipos (reglas de la base)

Reinicia la base (0.3) y, en **Modo Avanzado → Consola**, ejecuta:

```
REGISTRAR A001AAA COMPACTO
ASIGNAR A001AAA
REGISTRAR A002AAA COMPACTO
ASIGNAR A002AAA
REGISTRAR A003AAA COMPACTO
ASIGNAR A003AAA
REGISTRAR A004AAA COMPACTO
ASIGNAR A004AAA
```

- [ ] Los tres primeros reciben `C-01`, `C-02`, `C-03`; **el cuarto recibe `G-01`** (un compacto cabe en uno grande cuando se acaban los compactos).

Registra y asigna tres motocicletas (`M001AAA`, `M002AAA`, `M003AAA`).

- [ ] Las dos primeras reciben `M-01` y `M-02`; la tercera, un espacio compacto libre si queda alguno.

---

## Parte D · Modo Avanzado

### D1 Detalle

En **Detalle**, recorre las 7 opciones del selector y comprueba que tienen datos coherentes con lo que hiciste:

- [ ] Vehículos en el parqueo
- [ ] Catálogo de espacios (con sector, LED y alarma)
- [ ] Vehículos registrados
- [ ] Alarmas activas
- [ ] Historial de ocupaciones (incluye las `FINALIZADA`)
- [ ] Eventos de sensor (llegadas, salidas y movimientos)
- [ ] Bitácora de comandos
- [ ] Clic en una fila abre su ficha en el panel de información

### D2 Consola y bitácora

Escribe estos comandos y comprueba la respuesta:

| Comando | Esperado |
|---|---|
| `AYUDA` | Lista de comandos |
| `ESTADO` | Resumen por tipo de espacio |
| `CONSULTAR` / `CONSULTAR OCUPADOS` | Tabla de espacios / filtrada |
| `VEHICULOS` y `ALARMAS` | Listas |
| `REGISTRAR P900AAA COMPACTO` | Verde: "registrado" |
| `ASIGNAR` (sin placa) | Rojo: error sintáctico con el uso correcto |
| `REGISTRAR P900AAA #` | Rojo: **error léxico**, indica la columna del carácter |
| `ASIGNAR P999ZZZ` | Error: el vehículo no existe |
| `BORRAR TODO` | Error: comando desconocido |
| `TOKENS ASIGNAR P123ABC` | Lista de tokens |
| `LIMPIAR` | Borra la consola |

- [ ] Todos responden como se espera. Flecha ↑ recupera comandos anteriores.
- [ ] En **Detalle → Bitácora de comandos** aparece cada instrucción con su clasificación: `OK`, `ERROR_LEXICO`, `ERROR_SINTACTICO` o `ERROR_SEMANTICO`.

### D3 Simulador

- [ ] **Llegó un vehículo** en un espacio asignado → registra la llegada (espacio rojo).
- [ ] **Llegó un vehículo** en un espacio sin asignar → aviso "no hay ninguno asignado", sin cambios.
- [ ] Mensaje a mano `ESP:CUALQUIER:COSA` → error de protocolo, la aplicación no se cae.
- [ ] **Reenviar estado completo al ESP32** → el registro lista de nuevo el LED de cada espacio y el estado de la alarma.

---

## Parte E · Comprobar en la base de datos

Compara lo que ve la aplicación con SQL Server (SSMS o `sqlcmd`):

```bash
sqlcmd -S localhost -E -C -d SistemaInteligenteParqueo -Q "EXEC dbo.pa_consultar"
```
```bash
sqlcmd -S localhost -E -C -d SistemaInteligenteParqueo -Q "SELECT TOP 10 placa, estado, fecha_llegada, autorizado_por FROM dbo.ocupaciones o JOIN dbo.vehiculos v ON v.id = o.vehiculo_id ORDER BY o.id DESC"
```
```bash
sqlcmd -S localhost -E -C -d SistemaInteligenteParqueo -Q "SELECT TOP 10 texto_original, resultado FROM dbo.bitacora_comandos ORDER BY id DESC"
```

- [ ] Los estados de `pa_consultar` coinciden con el mapa.
- [ ] `ocupaciones` muestra el ciclo `ASIGNADA → OCUPADA → AUTORIZADA → FINALIZADA`.
- [ ] `bitacora_comandos` coincide con lo escrito en la consola.

---

## Parte F · Robustez

### F1 Dos ventanas a la vez

- [ ] Abre `python main.py` **dos veces**. Registra y asigna un vehículo en la primera: la segunda se actualiza sola en unos 3 segundos.

### F2 Sin conexión con SQL Server

1. Cierra la aplicación. En `config_db.ini` cambia `servidor = servidorquenoexiste`.
2. Ejecuta `python main.py`.

- [ ] Aparece un mensaje claro con la causa y la opción de abrir en **modo demostración**. Al aceptar, abre con datos de ejemplo y el encabezado dice "Modo demostración".
- [ ] **Restaura** `servidor = localhost`.

### F3 Instalación desde cero (lo que hará quien descargue el repositorio)

- [ ] En otra carpeta: `git clone https://github.com/JuanMayens5/sistema-inteligente-parqueo.git`, y seguir **solo** el README: instalar, ejecutar el script, copiar `config_db.ini`, abrir. Si algo no queda claro, corrige el README.

---

## Lista antes de entregar

- [ ] Partes 0 a F en orden, sin fallos sin explicar.
- [ ] `config_db.ini` **no** está en el repositorio y no contiene contraseñas reales.
- [ ] Commit y `git push` hechos (falta subir el último cambio del README). Comprueba en GitHub que el README se ve bien.
- [ ] La base queda limpia para la demostración (0.3) y la aplicación abre sin errores.
- [ ] Ensayo corto de la demostración: Parte A + B (≈5 minutos).

## Qué decir con honestidad en la entrega

Para que nadie lo descubra por sorpresa, menciónalo tú:

1. **El hardware real (ESP32) no está conectado.** El simulador reproduce los mismos mensajes y ejecuta los mismos procedimientos; el puente por puerto serial queda como siguiente fase.
2. **Liberar un espacio a mano** no aparece con SQL Server, porque la base no tiene `pa_cancelar_ocupacion`.
3. **La consola usa un analizador provisional**; la sintaxis oficial del lenguaje está por definirse.
4. **Mejoras propuestas a la base** (expiración de asignaciones, alarma de sensor inconsistente, espacios fuera de servicio): ver `docs/PLAN_INTEGRACION_BASE_DATOS.md`.
