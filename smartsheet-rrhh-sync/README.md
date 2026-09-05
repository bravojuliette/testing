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
