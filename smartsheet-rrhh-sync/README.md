# Sincronización Google Sheets → 3 maestros de Smartsheet (RRHH)

Script de Google Apps Script que reparte los empleados de un Google Sheet
entre tres maestros de Smartsheet según la columna **Centro Emplazamiento (DR)**:

| Maestro | Sheet ID | Criterio |
|---|---|---|
| Maestro de Empleados - E&R | `5049183181426564` | El centro **comienza por** `E&R` (sin distinguir mayúsculas) |
| Maestro de Empleados - WTS | `4408773492821892` | El centro es **exactamente** `WTS` |
| Maestro de Empleados - Agua | `4550142341369732` | Cualquier otro valor (incluido vacío) |

Cada maestro se sincroniza igual que el antiguo maestro único: bajas,
duplicados, actualizaciones y altas por `ID RRHH`, con control de tiempo,
reintentos y capacidad máxima. Si un empleado cambia de centro, se elimina
del maestro antiguo y se crea en el nuevo automáticamente.

## Instalación

1. Abre el proyecto de Apps Script y **sustituye todo el código** por el
   contenido de `Code.gs`.
2. En *Configuración del proyecto → Propiedades del script*, comprueba que
   existe la propiedad `SMARTSHEET_TOKEN` con el token de la API de
   Smartsheet (es la misma propiedad que usaba el script anterior).
3. Comprueba que los tres Smartsheets tienen exactamente las mismas
   columnas que el maestro antiguo (las de `COLUMN_MAP`).
4. Ejecuta `previewRouting()` y revisa en el registro cuántos empleados
   van a cada maestro y con qué valores de centro. **No toca Smartsheet ni
   necesita token.**
5. Ejecuta `previewSync()` para ver el plan (altas, bajas, actualizaciones)
   de cada maestro. **No modifica nada.**
6. Ejecuta `setupSync()` **una sola vez**. Elimina los activadores antiguos
   e instala los nuevos. La primera sincronización se lanza sola en el
   siguiente minuto.

## Funciones útiles

| Función | Qué hace |
|---|---|
| `previewRouting()` | Recuento por maestro y valores de centro. No usa Smartsheet. |
| `previewSync()` | Plan completo de cada maestro sin modificar nada. |
| `auditMissingFields()` | Campos con valor en Google pero vacíos en Smartsheet, por maestro. |
| `forceSyncNow()` | Fuerza una sincronización inmediata. |
| `setupSync()` | Instala los activadores (ejecutar una vez). |
| `removeSyncTriggers()` | Desinstala los activadores. |

## Cómo funciona el reparto de tiempo

Apps Script limita cada ejecución a 6 minutos. El script se detiene a los
4 minutos (`MAX_EXECUTION_MS`) y guarda en `RRHH_TARGET_CURSOR` por qué
maestro iba, de modo que la siguiente ejecución del worker (cada minuto)
continúa por ese maestro y no vuelve a empezar por el primero.

## Seguridad

- Si Google no tiene ningún `ID RRHH` válido y un maestro sí tiene
  registros, se cancela (protección contra borrado masivo).
- Si **ningún** empleado se enruta a un maestro pero ese maestro tiene
  registros, no se vacía (`ALLOW_EMPTY_TARGET_WIPE: false`). Ponlo a
  `true` solo si es intencionado.
- Un error en un maestro no bloquea a los demás: se procesan el resto y se
  reintenta en la siguiente ejecución.

## Cambiar los filtros

Los criterios están en `TARGETS`, en la parte superior de `Code.gs`. Se
evalúan de arriba abajo y el empleado va al primero que devuelve `true`;
el último debe ser siempre el comodín (`() => true`). La función `matches`
recibe el centro ya limpio y en MAYÚSCULAS.

## Nota sobre el maestro antiguo

El Smartsheet antiguo (`3382072258285444`) deja de sincronizarse. No se
modifica ni se borra: puedes conservarlo como histórico o eliminarlo cuando
hayas comprobado que los tres nuevos maestros están correctos.

---

# Migración de fórmulas: maestro único → 3 maestros

`MigrateFormulas.gs` reescribe automáticamente las fórmulas de **otras
hojas de Smartsheet** que consultaban el maestro antiguo, para que busquen
en cascada en los tres maestros nuevos (E&R → WTS → Agua).

Se añade como **archivo nuevo** en el mismo proyecto de Apps Script
(Archivo → Nuevo → Script), junto a `Code.gs`. Usa el mismo token.

## Flujo

| Paso | Función | Qué hace |
|---|---|---|
| 0 | `migrationDebugSheet()` | Opcional. Pon en `MIG_CFG.DEBUG_SHEET_ID` el ID de una hoja que sepas que consulta el maestro antiguo y muestra sus referencias, para comprobar que la detección funciona. |
| 1 | `migrationDiscover()` | Recorre todas las hojas a las que tienes acceso y guarda las que tienen referencias al maestro antiguo. Si no termina en una ejecución, instala un activador por minuto que continúa solo y se elimina al acabar. `migrationDiscoverReset()` borra la lista para empezar de cero. |
| 2 | `migrationStartPreview()` | **Simulación.** Escribe en un Google Sheet (se crea solo en tu Drive) qué referencias se crearían y cómo quedaría cada fórmula. No toca Smartsheet. |
| 3 | Revisa el informe | Filtra por Estado = `REVISAR`: son fórmulas que hay que adaptar a mano. |
| 4 | `migrationStartApply()` | Crea las referencias nuevas y reescribe las fórmulas. |
| 5 | `migrationStatus()` | Progreso, errores y enlace al informe. |
| — | `migrationStop()` | Para el worker sin perder progreso. |
| — | `migrationReset()` | Borra el progreso para volver a empezar un modo. |
| — | `migrationStartRollback()` | Restaura las fórmulas originales usando el informe. |

Los modos Preview, Apply y Rollback instalan un activador por minuto
(`migrationWorker`) que procesa hojas hasta agotar 4 minutos y **se elimina
solo al terminar**.

## Qué se reescribe

Solo las fórmulas que usan referencias al maestro antiguo. El resto de
la fórmula queda intacto.

| Patrón original | Resultado |
|---|---|
| `INDEX(...)`, `VLOOKUP(...)`, `MATCH(...)` | `IFERROR(v_ER, IFERROR(v_WTS, v_AGUA))` |
| `COUNTIF`, `COUNTIFS`, `SUMIF`, `SUMIFS`, `COUNT`, `SUM` | `(v_ER + v_WTS + v_AGUA)` |
| `MAX(...)` | `MAX(v_ER, v_WTS, v_AGUA)` |
| `JOIN(COLLECT(...), sep)` | `(JOIN_ER + JOIN_WTS + JOIN_AGUA)` |
| `IF`, `IFERROR`, `AND`, `OR`, `ISERROR`... | Se entra en sus argumentos y se aplica lo anterior dentro. |
| `AVG`, `MIN`, `COLLECT` suelto, otros | `REVISAR` (no se modifica) |

La última variante de la cascada **no** va envuelta en `IFERROR`: si el
empleado no está en ningún maestro, la fórmula da el mismo error que
antes, así los `IFERROR(..., "")` o `ISERROR(...)` que ya tuvieras
siguen funcionando igual.

Ejemplo:

```
=IFERROR(INDEX({Maestro Nombre}, MATCH([ID RRHH]@row, {Maestro ID}, 0)), "")
```
pasa a
```
=IFERROR(IFERROR(INDEX({ER NOMBRE Y APELLIDOS}, MATCH([ID RRHH]@row, {ER ID RRHH}, 0)),
 IFERROR(INDEX({WTS NOMBRE Y APELLIDOS}, MATCH([ID RRHH]@row, {WTS ID RRHH}, 0)),
 INDEX({AGUA NOMBRE Y APELLIDOS}, MATCH([ID RRHH]@row, {AGUA ID RRHH}, 0)))), "")
```

## Referencias nuevas

Por cada referencia antigua se crean tres, una por maestro, con el nombre
`<PREFIJO> <TÍTULO DE COLUMNA>` (por ejemplo `{ER NOMBRE Y APELLIDOS}`).
Si la referencia antigua abarcaba varias columnas, el nombre es
`<PREFIJO> <PRIMERA> a <ÚLTIMA>`. Si en la hoja ya existe una referencia
equivalente, se reutiliza. Las referencias antiguas **no se borran**;
Smartsheet las elimina solo cuando ninguna fórmula las usa.

## Límites a tener en cuenta

- Cada campo consultado pasa a usar **3 referencias en lugar de 1**.
  Smartsheet permite 100 referencias distintas por hoja. El informe indica
  cuántas se crean en cada hoja.
- El total de celdas referenciadas no crece: los tres maestros suman las
  mismas filas que el antiguo.
- Se referencian siempre **columnas completas**. Si alguna referencia
  antigua estaba limitada a un rango de filas, se indica en el informe.
- Los **enlaces de celda** (cell links) y los **informes** de Smartsheet no
  son fórmulas y no se migran.
