/**
 * Sincronización Google Sheets -> 3 maestros de Smartsheet.
 *
 * Google Sheets se lee UNA sola vez por ejecución. Cada empleado se
 * enruta a un único maestro según el valor de la columna
 * "Centro Emplazamiento (DR)":
 *
 *   1. E&R  -> el valor comienza por "E&R".
 *   2. WTS  -> el valor es exactamente "WTS".
 *   3. Agua -> cualquier otro valor (incluido vacío).
 *
 * Cada maestro se comporta exactamente igual que el antiguo maestro
 * único: bajas, duplicados, actualizaciones y altas por ID RRHH,
 * con control de tiempo, reintentos y capacidad máxima.
 *
 * Si un empleado cambia de centro, desaparece de su partición antigua
 * (y por tanto se elimina de ese maestro) y aparece en la nueva (se crea
 * en el otro maestro). No hace falta ninguna lógica adicional.
 */

const CFG = Object.freeze({
  GOOGLE_FILE_ID: '1sPTQfnWtgbB_I27wTN6mTewhWA064ZFHNbvQxCRqUg0',
  GOOGLE_TAB_GID: 0,

  SMARTSHEET_API: 'https://api.smartsheet.com/2.0',
  TOKEN_PROPERTY: 'SMARTSHEET_TOKEN',

  KEY_GOOGLE: 'ID RRHH',
  KEY_SMARTSHEET: 'ID RRHH',

  // Columna (título de Smartsheet, según COLUMN_MAP) que decide a qué
  // maestro va cada empleado. Corresponde a la columna de Google
  // "Centro Emplazamiento (DR)".
  ROUTING_SMARTSHEET_COLUMN: 'CENTRO DE EMPLAZAMIENTO (DR)',

  PREFERRED_CENTER_VALUE: 'SSCC Iberia',
  PREFERRED_CENTER_SMARTSHEET_COLUMN: 'CENTRO DE EMPLAZAMIENTO (DR)',

  DELETE_MISSING_ROWS: true,

  // Seguridad: si para un maestro no hay NINGÚN empleado en Google pero
  // el maestro sí tiene filas con ID, no se vacía ese maestro salvo que
  // este valor sea true.
  ALLOW_EMPTY_TARGET_WIPE: false,

  // Límite habitual por hoja. Se puede sobrescribir por maestro con
  // la propiedad "maxRows" en TARGETS.
  SMARTSHEET_MAX_ROWS: 20000,

  SMARTSHEET_PAGE_SIZE: 5000,

  WRITE_BATCH: 200,
  DELETE_BATCH: 100,
  RETRIES: 5,

  // Apps Script corta cada ejecución a los 6 minutos. El script se detiene
  // antes y continúa en la siguiente ejecución si quedan maestros o
  // acciones pendientes.
  MAX_EXECUTION_MS: 240000,
  MIN_TIME_FOR_API_CALL_MS: 15000,

  FORCE_FULL_SYNC_EVERY_MINUTES: 10,
  FOLLOW_UP_SYNCS_AFTER_CHANGE: 2,

  SYNC_PENDING_PROPERTY: 'RRHH_SYNC_PENDING',
  SYNC_REASON_PROPERTY: 'RRHH_SYNC_REASON',
  LAST_SUCCESS_PROPERTY: 'RRHH_LAST_SUCCESS_MS',
  FOLLOW_UP_PROPERTY: 'RRHH_FOLLOW_UP_SYNCS',

  // Índice del maestro por el que debe continuar la siguiente ejecución
  // cuando la anterior se detuvo por tiempo. Evita que un maestro grande
  // acapare siempre el tiempo y los demás nunca se procesen.
  TARGET_CURSOR_PROPERTY: 'RRHH_TARGET_CURSOR',

  DUPLICATE_LOG_LIMIT: 20,
  AUDIT_LOG_LIMIT: 200
});


/**
 * Maestros de destino. El ORDEN importa: se evalúan de arriba abajo y
 * el empleado va al primero cuyo "matches" devuelve true. El último debe
 * ser el comodín.
 *
 * "matches" recibe el valor de la columna de enrutado ya limpiado
 * (sin espacios sobrantes) y en MAYÚSCULAS.
 */
const TARGETS = Object.freeze([
  {
    key: 'ER',
    name: 'Maestro de Empleados - E&R',
    sheetId: '5049183181426564',
    matches: center => center.startsWith('E&R')
  },
  {
    key: 'WTS',
    name: 'Maestro de Empleados - WTS',
    sheetId: '4408773492821892',
    matches: center => center === 'WTS'
  },
  {
    key: 'AGUA',
    name: 'Maestro de Empleados - Agua',
    sheetId: '4550142341369732',
    matches: () => true
  }
]);


const COLUMN_MAP = Object.freeze([
  ['Centro de coste',             'CENTRO DE COSTE'],
  ['Centro Emplazamiento (DR)',   'CENTRO DE EMPLAZAMIENTO (DR)'],
  ['Sociedad / CIF',              'CIF'],
  ['Mail',                        'CORREO'],
  ['Director de Operaciones',     'D. OPERACIONES'],
  ['DNI',                         'DNI EMPLEADO'],
  ['Mail Responsable jerárquico', 'EMAIL RESP. JERÁRQUICO'],
  ['Mail Responsable RRHH',       'EMAIL RESP. RRHH'],
  ['Email Responsable Compras',   'EMAIL RESPONSABLE COMPRAS'],
  ['ID RRHH',                     'ID RRHH'],
  ['Empresa',                     'NOMBRE EMPRESA'],
  ['Nombre y Apellidos',          'NOMBRE Y APELLIDOS'],
  ['Responsable Jerárquico',      'RESP. JERÁRQUICO'],
  ['Responsable RRHH',            'RESP. RRHH'],
  ['Responsable Compras',         'RESPONSABLE COMPRAS']
]);


/* ========================================================================
 * ACTIVADORES
 * ====================================================================== */

/**
 * Ejecutar una sola vez después de sustituir el código.
 */
function setupSync() {
  removeSyncTriggers();

  const spreadsheet = SpreadsheetApp.openById(CFG.GOOGLE_FILE_ID);

  ScriptApp.newTrigger('queueSyncFromEdit')
    .forSpreadsheet(spreadsheet)
    .onEdit()
    .create();

  ScriptApp.newTrigger('queueSyncFromChange')
    .forSpreadsheet(spreadsheet)
    .onChange()
    .create();

  ScriptApp.newTrigger('runScheduledSync')
    .timeBased()
    .everyMinutes(1)
    .create();

  PropertiesService
    .getScriptProperties()
    .deleteProperty(CFG.TARGET_CURSOR_PROPERTY);

  markSyncPending_('Instalación o reinstalación del script');

  console.log(
    'Activadores instalados. La sincronización se ejecutará ' +
    'automáticamente en el siguiente ciclo del worker.'
  );
}


function removeSyncTriggers() {
  const handlerNames = new Set([
    'syncGoogleToSmartsheet',
    'queueSyncFromEdit',
    'queueSyncFromChange',
    'runScheduledSync'
  ]);

  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (handlerNames.has(trigger.getHandlerFunction())) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}


function queueSyncFromEdit(e) {
  markSyncPending_('Edición en Google Sheets');
  scheduleFollowUpSyncs_();
}


function queueSyncFromChange(e) {
  markSyncPending_('Cambio estructural en Google Sheets');
  scheduleFollowUpSyncs_();
}


function runScheduledSync() {
  const properties = PropertiesService.getScriptProperties();
  const pending =
    properties.getProperty(CFG.SYNC_PENDING_PROPERTY) === '1';

  const lastSuccess = Number(
    properties.getProperty(CFG.LAST_SUCCESS_PROPERTY) || 0
  );

  const fullSyncIsDue =
    !lastSuccess ||
    Date.now() - lastSuccess >=
      CFG.FORCE_FULL_SYNC_EVERY_MINUTES * 60 * 1000;

  if (!pending && !fullSyncIsDue) {
    return;
  }

  syncGoogleToSmartsheet();
}


function forceSyncNow() {
  markSyncPending_('Ejecución manual');
  scheduleFollowUpSyncs_();
  syncGoogleToSmartsheet();
}


/* ========================================================================
 * DIAGNÓSTICO (no modifican Smartsheet)
 * ====================================================================== */

/**
 * Muestra cuántos empleados irían a cada maestro y ejemplos de valores
 * de "Centro Emplazamiento (DR)" por maestro. No toca Smartsheet ni
 * necesita token. Úsala para validar los filtros antes de sincronizar.
 */
function previewRouting() {
  const source = readGoogle_();
  const partitions = partitionByTarget_(source);

  const report = TARGETS.map(target => {
    const rows = partitions.get(target.key);
    const centerCounts = {};

    rows.forEach(row => {
      const center = routingValue_(row) || '(vacío)';
      centerCounts[center] = (centerCounts[center] || 0) + 1;
    });

    return {
      target: target.name,
      sheetId: target.sheetId,
      employees: rows.size,
      centers: centerCounts
    };
  });

  console.log(JSON.stringify({
    googleRowsWithId: source.rows.size,
    googleRowsWithoutId: source.rowsWithoutId,
    targets: report
  }, null, 2));
}


/**
 * Vista previa del plan de cada maestro: no modifica Smartsheet.
 */
function previewSync() {
  const startedAt = Date.now();
  requireToken_();

  const source = readGoogle_();
  const partitions = partitionByTarget_(source);

  const targets = TARGETS.map(target => {
    const plan = buildPlan_(
      target,
      partitions.get(target.key),
      source
    );

    return {
      target: target.name,
      sheetId: target.sheetId,

      googleRowsRouted:
        plan.stats.googleRows,

      smartsheetRowsActuallyRead:
        plan.stats.smartsheetRowsRead,

      smartsheetTotalRows:
        plan.stats.smartsheetTotalRows,

      smartsheetPagesRead:
        plan.stats.smartsheetPagesRead,

      smartsheetRowsWithId:
        plan.stats.smartsheetRowsWithId,

      smartsheetRowsWithoutId:
        plan.stats.smartsheetRowsWithoutId,

      deleteCount:
        plan.remove.length,

      updateCount:
        plan.update.length,

      addRequestedCount:
        plan.add.length,

      addExecutableCount:
        plan.addExecutable.length,

      addSkippedByCapacityCount:
        plan.addSkippedCapacity.length,

      firstDeletes:
        plan.remove.slice(0, 25).map(item => ({
          idRrhh: item.key,
          reason: item.reason
        })),

      firstUpdates:
        plan.update.slice(0, 25).map(item => item.key),

      firstAdds:
        plan.addExecutable.slice(0, 25).map(item => item.key),

      firstAddsSkippedByCapacity:
        plan.addSkippedCapacity.slice(0, 25).map(item => item.key)
    };
  });

  console.log(JSON.stringify({
    durationSeconds:
      Math.round((Date.now() - startedAt) / 1000),

    googleRowsWithId:
      source.rows.size,

    duplicateGoogleOccurrencesResolved:
      source.duplicateRowsResolved,

    duplicatesOverriddenBySsccIberia:
      source.duplicatesOverriddenByPreferredCenter,

    duplicateBlankFieldsRecovered:
      source.duplicateBlankFieldsRecovered,

    targets
  }, null, 2));
}


/**
 * Diagnóstico de campos ausentes por maestro.
 */
function auditMissingFields() {
  const startedAt = Date.now();
  requireToken_();

  const source = readGoogle_();
  const partitions = partitionByTarget_(source);

  const targets = TARGETS.map(target => {
    const sourceRows = partitions.get(target.key);
    const smartSheet = readCompleteSmartsheet_(target.sheetId);

    const smartColumns = smartSheet.smartColumns;
    const keyColumn = smartColumns.get(canonical_(CFG.KEY_SMARTSHEET));

    const indexed = indexSmartRows_(
      smartSheet.rows,
      keyColumn.id,
      smartSheet.totalRowCount
    );

    const missing = [];
    const rowsMissingCompletely = [];
    const countsByColumn = {};

    sourceRows.forEach((sourceRow, normalizedId) => {
      const matches = indexed.byId.get(normalizedId) || [];

      if (!matches.length) {
        rowsMissingCompletely.push({
          idRrhh: sourceRow.id,
          googleRow: sourceRow.rowNumber
        });
        return;
      }

      const targetRow = matches[0];

      COLUMN_MAP.forEach(([googleTitle, smartTitle]) => {
        const columnName = canonical_(smartTitle);
        const column = smartColumns.get(columnName);

        const sourceValue = clean_(
          sourceRow.values.get(columnName) || ''
        );

        const targetValue = clean_(
          targetRow._values.get(String(column.id)) || ''
        );

        if (sourceValue !== '' && targetValue === '') {
          countsByColumn[smartTitle] =
            (countsByColumn[smartTitle] || 0) + 1;

          if (missing.length < CFG.AUDIT_LOG_LIMIT) {
            missing.push({
              idRrhh: sourceRow.id,
              googleRow: sourceRow.rowNumber,
              smartsheetRow: targetRow.rowNumber,
              googleColumn: googleTitle,
              smartsheetColumn: smartTitle,
              googleValue: sourceValue
            });
          }
        }
      });
    });

    return {
      target: target.name,
      sheetId: target.sheetId,
      missingFieldCount:
        Object.values(countsByColumn)
          .reduce((sum, value) => sum + value, 0),
      missingRowsCount:
        rowsMissingCompletely.length,
      countsByColumn,
      firstMissingFields:
        missing,
      firstRowsMissingCompletely:
        rowsMissingCompletely.slice(0, CFG.AUDIT_LOG_LIMIT)
    };
  });

  console.log(JSON.stringify({
    durationSeconds:
      Math.round((Date.now() - startedAt) / 1000),
    targets
  }, null, 2));
}


/* ========================================================================
 * SINCRONIZACIÓN
 * ====================================================================== */

/**
 * Sincronización Google Sheets -> maestros de Smartsheet.
 *
 * Por cada maestro, en orden:
 * 1. Eliminar bajas y duplicados.
 * 2. Actualizar registros existentes.
 * 3. Crear nuevas filas que quepan.
 *
 * Si se aproxima al límite de ejecución, termina de forma controlada,
 * recuerda por qué maestro iba y continúa en el siguiente minuto.
 */
function syncGoogleToSmartsheet() {
  const lock = LockService.getScriptLock();

  if (!lock.tryLock(3000)) {
    console.log(
      'Se omite esta ejecución porque ya hay otra sincronización activa.'
    );
    return;
  }

  const startedAt = Date.now();
  const deadline = startedAt + CFG.MAX_EXECUTION_MS;
  const properties = PropertiesService.getScriptProperties();

  try {
    requireToken_();

    const source = readGoogle_();
    const partitions = partitionByTarget_(source);

    let cursor = Number(
      properties.getProperty(CFG.TARGET_CURSOR_PROPERTY) || 0
    );

    if (!(cursor >= 0 && cursor < TARGETS.length)) {
      cursor = 0;
    }

    const results = [];
    const errors = [];
    let completedAll = true;

    for (let index = cursor; index < TARGETS.length; index++) {
      const target = TARGETS[index];

      if (!hasTimeForAnotherRequest_(deadline)) {
        completedAll = false;
        break;
      }

      properties.setProperty(
        CFG.TARGET_CURSOR_PROPERTY,
        String(index)
      );

      try {
        const result = syncTarget_(
          target,
          partitions.get(target.key),
          source,
          deadline
        );

        results.push(result);

        if (!result.completed) {
          completedAll = false;
          break;
        }

      } catch (error) {
        // Un maestro con error no debe bloquear a los demás.
        errors.push({
          target: target.name,
          sheetId: target.sheetId,
          message: clean_(error.message)
        });

        console.error(
          `Error en ${target.name} (${target.sheetId}): ` +
          error.message
        );
      }
    }

    if (errors.length) {
      // Se reintentan todos los maestros en la siguiente ejecución.
      properties.deleteProperty(CFG.TARGET_CURSOR_PROPERTY);

      markSyncPending_(
        'Reintento tras error en ' +
        errors.map(item => item.target).join(', ') +
        ': ' + errors[0].message
      );

    } else if (completedAll) {
      properties.deleteProperty(CFG.TARGET_CURSOR_PROPERTY);

      properties.setProperty(
        CFG.LAST_SUCCESS_PROPERTY,
        String(Date.now())
      );

      const followUpsRemaining = Number(
        properties.getProperty(CFG.FOLLOW_UP_PROPERTY) || 0
      );

      if (followUpsRemaining > 0) {
        properties.setProperty(
          CFG.FOLLOW_UP_PROPERTY,
          String(followUpsRemaining - 1)
        );

        markSyncPending_(
          'Revisión posterior para capturar fórmulas o importaciones tardías'
        );
      } else {
        properties.deleteProperty(CFG.SYNC_PENDING_PROPERTY);
        properties.deleteProperty(CFG.SYNC_REASON_PROPERTY);
      }

    } else {
      // El cursor ya apunta al maestro que quedó a medias.
      markSyncPending_(
        'Continuación automática por límite preventivo de tiempo'
      );
    }

    console.log(JSON.stringify({
      completedAll,
      durationSeconds:
        Math.round((Date.now() - startedAt) / 1000),
      googleRowsWithId:
        source.rows.size,
      remainingWorkWillContinueNextMinute:
        !completedAll || errors.length > 0,
      targets: results,
      errors
    }, null, 2));

    if (errors.length) {
      throw new Error(
        'Fallo en ' + errors.length + ' maestro(s): ' +
        errors.map(item => `${item.target}: ${item.message}`).join(' | ')
      );
    }

  } catch (error) {
    markSyncPending_(
      'Reintento tras error: ' + clean_(error.message)
    );

    throw error;

  } finally {
    lock.releaseLock();
  }
}


/**
 * Ejecuta el plan de un maestro respetando el límite de tiempo.
 */
function syncTarget_(target, sourceRows, source, deadline) {
  const plan = buildPlan_(target, sourceRows, source);
  const sheetPath = `/sheets/${target.sheetId}/rows`;

  let completed = true;
  let deleted = 0;
  let updated = 0;
  let added = 0;
  let sheetFull = false;

  // 1. Bajas y duplicados.
  for (
    let start = 0;
    start < plan.remove.length;
    start += CFG.DELETE_BATCH
  ) {
    if (!hasTimeForAnotherRequest_(deadline)) {
      completed = false;
      break;
    }

    const batch = plan.remove.slice(start, start + CFG.DELETE_BATCH);
    const rowIds = batch.map(item => item.rowId).join(',');

    smartRequest_(
      'delete',
      `${sheetPath}?ids=${rowIds}&ignoreRowsNotFound=true`
    );

    deleted += batch.length;
  }

  // 2. Actualizaciones.
  if (completed) {
    for (
      let start = 0;
      start < plan.update.length;
      start += CFG.WRITE_BATCH
    ) {
      if (!hasTimeForAnotherRequest_(deadline)) {
        completed = false;
        break;
      }

      const batch = plan.update.slice(start, start + CFG.WRITE_BATCH);

      smartRequest_(
        'put',
        `${sheetPath}?allowPartialSuccess=false`,
        batch.map(item => item.payload)
      );

      updated += batch.length;
    }
  }

  // 3. Altas.
  if (completed) {
    for (
      let start = 0;
      start < plan.addExecutable.length;
      start += CFG.WRITE_BATCH
    ) {
      if (!hasTimeForAnotherRequest_(deadline)) {
        completed = false;
        break;
      }

      const batch = plan.addExecutable.slice(
        start,
        start + CFG.WRITE_BATCH
      );

      try {
        smartRequest_(
          'post',
          `${sheetPath}?allowPartialSuccess=false`,
          batch.map(item => item.payload)
        );

        added += batch.length;

      } catch (error) {
        if (Number(error.smartsheetErrorCode) === 5634) {
          sheetFull = true;

          console.warn(
            `${target.name} ha alcanzado su capacidad máxima. ` +
            'Las actualizaciones y bajas sí se han procesado, ' +
            'pero se detienen las altas.'
          );

          break;
        }

        throw error;
      }
    }
  }

  return {
    target: target.name,
    sheetId: target.sheetId,
    completed,
    sheetFull,
    deleted,
    updated,
    added,
    additionsSkippedByConfiguredCapacity:
      plan.addSkippedCapacity.length,
    googleRowsRouted:
      plan.stats.googleRows,
    smartsheetRowsRead:
      plan.stats.smartsheetRowsRead,
    smartsheetTotalRows:
      plan.stats.smartsheetTotalRows,
    smartsheetPagesRead:
      plan.stats.smartsheetPagesRead
  };
}


/**
 * Construye el plan de un maestro a partir de su partición de Google.
 */
function buildPlan_(target, sourceRows, source) {
  const smartSheet = readCompleteSmartsheet_(target.sheetId);

  const smartColumns = smartSheet.smartColumns;
  const keyColumn = smartColumns.get(canonical_(CFG.KEY_SMARTSHEET));

  const indexed = indexSmartRows_(
    smartSheet.rows,
    keyColumn.id,
    smartSheet.totalRowCount
  );

  if (
    CFG.DELETE_MISSING_ROWS &&
    source.rows.size === 0 &&
    indexed.rowsWithId > 0
  ) {
    throw new Error(
      'SEGURIDAD: Google Sheets no contiene ningún ID RRHH válido ' +
      `y ${target.name} sí tiene registros. Se cancela para evitar ` +
      'un borrado masivo.'
    );
  }

  if (
    CFG.DELETE_MISSING_ROWS &&
    !CFG.ALLOW_EMPTY_TARGET_WIPE &&
    sourceRows.size === 0 &&
    indexed.rowsWithId > 0
  ) {
    throw new Error(
      `SEGURIDAD: ningún empleado de Google Sheets se enruta a ` +
      `${target.name}, pero ese maestro tiene ${indexed.rowsWithId} ` +
      'registros. Se cancela para evitar vaciarlo. Revisa el filtro ' +
      'o activa CFG.ALLOW_EMPTY_TARGET_WIPE si es intencionado.'
    );
  }

  const add = [];
  const update = [];
  const remove = [];

  sourceRows.forEach((sourceRow, normalizedId) => {
    const matches = indexed.byId.get(normalizedId) || [];

    if (!matches.length) {
      add.push({
        key: sourceRow.id,
        payload: {
          toBottom: true,
          cells: cellsToWrite_(sourceRow, smartColumns)
        }
      });

      return;
    }

    const keptRow = matches[0];
    const changedCells = changedCells_(sourceRow, keptRow, smartColumns);

    if (changedCells.length) {
      update.push({
        key: sourceRow.id,
        payload: {
          id: keptRow.id,
          cells: changedCells
        }
      });
    }

    matches.slice(1).forEach(row => {
      remove.push({
        key: sourceRow.id,
        rowId: row.id,
        reason: 'ID RRHH duplicado en Smartsheet'
      });
    });
  });

  if (CFG.DELETE_MISSING_ROWS) {
    indexed.byId.forEach((rows, normalizedId) => {
      if (sourceRows.has(normalizedId)) {
        return;
      }

      const reason = source.rows.has(normalizedId)
        ? 'El empleado pertenece ahora a otro maestro'
        : 'ID RRHH ya no existe en Google Sheets';

      rows.forEach(row => {
        remove.push({
          key: indexed.rawIds.get(normalizedId),
          rowId: row.id,
          reason
        });
      });
    });
  }

  const uniqueRemove = uniqueBy_(remove, item => String(item.rowId));

  const maxRows = Number(target.maxRows || CFG.SMARTSHEET_MAX_ROWS);

  const rowsAfterDeletes = Math.max(
    0,
    indexed.totalRows - uniqueRemove.length
  );

  const availableSlotsAfterDeletes = Math.max(
    0,
    maxRows - rowsAfterDeletes
  );

  return {
    add,
    addExecutable: add.slice(0, availableSlotsAfterDeletes),
    addSkippedCapacity: add.slice(availableSlotsAfterDeletes),
    update,
    remove: uniqueRemove,

    stats: {
      googleRows: sourceRows.size,
      smartsheetRowsRead: smartSheet.rows.length,
      smartsheetTotalRows: indexed.totalRows,
      smartsheetPagesRead: smartSheet.pagesRead,
      smartsheetRowsWithId: indexed.rowsWithId,
      smartsheetRowsWithoutId: indexed.rowsWithoutId,
      rowsAfterDeletes,
      availableSlotsAfterDeletes
    }
  };
}


/* ========================================================================
 * ENRUTADO
 * ====================================================================== */

/**
 * Reparte las filas de Google (ya deduplicadas) entre los maestros.
 * Devuelve Map<targetKey, Map<normalizedId, row>>.
 */
function partitionByTarget_(source) {
  const partitions = new Map();

  TARGETS.forEach(target => {
    partitions.set(target.key, new Map());
  });

  source.rows.forEach((row, normalizedId) => {
    const target = routeTarget_(row);
    partitions.get(target.key).set(normalizedId, row);
  });

  return partitions;
}


function routeTarget_(row) {
  const center = routingValue_(row).toUpperCase();

  const target = TARGETS.find(item => item.matches(center));

  if (!target) {
    throw new Error(
      `Ningún maestro acepta el centro "${center}" ` +
      `(ID RRHH ${row.id}). El último elemento de TARGETS ` +
      'debe ser el comodín.'
    );
  }

  return target;
}


/**
 * Valor de la columna de enrutado, limpio y con espacios colapsados.
 * No se usa canonical_() porque eliminaría el "&" de "E&R".
 */
function routingValue_(row) {
  const columnName = canonical_(CFG.ROUTING_SMARTSHEET_COLUMN);

  return clean_(row.values.get(columnName) || '')
    .replace(/\s+/g, ' ');
}


/* ========================================================================
 * LECTURA DE GOOGLE SHEETS
 * ====================================================================== */

/**
 * Lee únicamente el rango de columnas de Google que contiene las columnas
 * sincronizadas.
 *
 * Duplicados:
 * 1. SSCC Iberia prevalece sobre cualquier otro centro.
 * 2. Si ninguna fila es SSCC Iberia, se conserva la primera.
 * 3. Si hay varias SSCC Iberia, se conserva la primera de ellas.
 *
 * La deduplicación se hace ANTES del enrutado, de modo que un ID RRHH
 * solo existe en un único maestro.
 */
function readGoogle_() {
  const spreadsheet = SpreadsheetApp.openById(CFG.GOOGLE_FILE_ID);

  const sheet = spreadsheet.getSheets().find(item =>
    item.getSheetId() === CFG.GOOGLE_TAB_GID
  );

  if (!sheet) {
    throw new Error(
      `No existe la pestaña con gid=${CFG.GOOGLE_TAB_GID}.`
    );
  }

  const lastRow = sheet.getLastRow();
  const lastColumn = sheet.getLastColumn();

  if (lastRow < 1 || lastColumn < 1) {
    return emptyGoogleResult_();
  }

  const headers = sheet
    .getRange(1, 1, 1, lastColumn)
    .getDisplayValues()[0];

  const headerIndex = new Map();

  headers.forEach((header, zeroBasedIndex) => {
    const normalized = canonical_(header);

    if (normalized && !headerIndex.has(normalized)) {
      headerIndex.set(normalized, zeroBasedIndex + 1);
    }
  });

  const descriptors = COLUMN_MAP.map(([googleTitle, smartTitle]) => {
    const sheetColumn = headerIndex.get(canonical_(googleTitle));

    if (!sheetColumn) {
      throw new Error(
        `Falta la columna de Google Sheets: "${googleTitle}".`
      );
    }

    return {
      googleTitle,
      smartTitle,
      smartKey: canonical_(smartTitle),
      sheetColumn
    };
  });

  const routingKey = canonical_(CFG.ROUTING_SMARTSHEET_COLUMN);

  if (!descriptors.some(item => item.smartKey === routingKey)) {
    throw new Error(
      `La columna de enrutado "${CFG.ROUTING_SMARTSHEET_COLUMN}" ` +
      'no está en COLUMN_MAP.'
    );
  }

  const minimumColumn = Math.min(
    ...descriptors.map(item => item.sheetColumn)
  );

  const maximumColumn = Math.max(
    ...descriptors.map(item => item.sheetColumn)
  );

  descriptors.forEach(item => {
    item.rangeOffset = item.sheetColumn - minimumColumn;
  });

  const values = lastRow > 1
    ? sheet
        .getRange(
          2,
          minimumColumn,
          lastRow - 1,
          maximumColumn - minimumColumn + 1
        )
        .getDisplayValues()
    : [];

  const keySmartName = canonical_(CFG.KEY_SMARTSHEET);
  const preferredCenterName = canonical_(
    CFG.PREFERRED_CENTER_SMARTSHEET_COLUMN
  );
  const preferredCenterValue = canonical_(CFG.PREFERRED_CENTER_VALUE);

  const rows = new Map();
  const duplicateSamples = [];

  let rowsWithoutId = 0;
  let duplicateRowsResolved = 0;
  let duplicatesOverriddenByPreferredCenter = 0;
  let duplicateBlankFieldsRecovered = 0;

  values.forEach((sheetRow, zeroBasedIndex) => {
    const rowNumber = zeroBasedIndex + 2;
    const mappedValues = new Map();
    let hasAnyMappedValue = false;

    descriptors.forEach(descriptor => {
      const value = clean_(sheetRow[descriptor.rangeOffset]);

      mappedValues.set(descriptor.smartKey, value);

      if (value !== '') {
        hasAnyMappedValue = true;
      }
    });

    if (!hasAnyMappedValue) {
      return;
    }

    const rawId = clean_(mappedValues.get(keySmartName) || '');

    if (!rawId) {
      rowsWithoutId++;
      return;
    }

    const normalizedId = normalizeId_(rawId);
    const candidate = {
      id: rawId,
      rowNumber,
      values: mappedValues
    };

    if (!rows.has(normalizedId)) {
      rows.set(normalizedId, candidate);
      return;
    }

    duplicateRowsResolved++;

    const selected = rows.get(normalizedId);

    const selectedIsPreferred =
      canonical_(selected.values.get(preferredCenterName) || '') ===
      preferredCenterValue;

    const candidateIsPreferred =
      canonical_(candidate.values.get(preferredCenterName) || '') ===
      preferredCenterValue;

    let chosen = selected;
    let discarded = candidate;
    let reason = 'Se conserva la primera aparición';

    if (!selectedIsPreferred && candidateIsPreferred) {
      chosen = candidate;
      discarded = selected;
      reason = 'Prevalece SSCC Iberia';
      duplicatesOverriddenByPreferredCenter++;
    } else if (selectedIsPreferred) {
      reason = 'La primera fila seleccionada ya es SSCC Iberia';
    }

    const mergedResult = mergeRowsKeepingPriority_(chosen, discarded);

    rows.set(normalizedId, mergedResult.row);
    duplicateBlankFieldsRecovered += mergedResult.fieldsRecovered;

    if (duplicateSamples.length < CFG.DUPLICATE_LOG_LIMIT) {
      duplicateSamples.push({
        idRrhh: rawId,
        chosenRow: chosen.rowNumber,
        discardedRow: discarded.rowNumber,
        reason,
        blankFieldsRecovered: mergedResult.fieldsRecovered
      });
    }
  });

  if (duplicateRowsResolved) {
    console.log(JSON.stringify({
      duplicateGoogleOccurrencesResolved:
        duplicateRowsResolved,
      overriddenBySsccIberia:
        duplicatesOverriddenByPreferredCenter,
      blankFieldsRecovered:
        duplicateBlankFieldsRecovered,
      samples: duplicateSamples
    }, null, 2));
  }

  return {
    rows,
    rowsWithoutId,
    duplicateRowsResolved,
    duplicatesOverriddenByPreferredCenter,
    duplicateBlankFieldsRecovered
  };
}


function mergeRowsKeepingPriority_(priorityRow, fallbackRow) {
  const mergedValues = new Map(priorityRow.values);
  let fieldsRecovered = 0;

  fallbackRow.values.forEach((fallbackValue, columnName) => {
    const priorityValue = clean_(mergedValues.get(columnName) || '');
    const cleanFallbackValue = clean_(fallbackValue);

    if (priorityValue === '' && cleanFallbackValue !== '') {
      mergedValues.set(columnName, cleanFallbackValue);
      fieldsRecovered++;
    }
  });

  return {
    row: {
      id: priorityRow.id,
      rowNumber: priorityRow.rowNumber,
      values: mergedValues
    },
    fieldsRecovered
  };
}


function emptyGoogleResult_() {
  return {
    rows: new Map(),
    rowsWithoutId: 0,
    duplicateRowsResolved: 0,
    duplicatesOverriddenByPreferredCenter: 0,
    duplicateBlankFieldsRecovered: 0
  };
}


/* ========================================================================
 * LECTURA DE SMARTSHEET
 * ====================================================================== */

/**
 * Lee un Smartsheet completo mediante paginación, limitando la respuesta
 * a las columnas realmente utilizadas.
 */
function readCompleteSmartsheet_(sheetId) {
  const metadata = smartRequest_(
    'get',
    `/sheets/${sheetId}?page=1&pageSize=1&exclude=nonexistentCells`
  );

  const smartColumns = requiredSmartColumns_(
    metadata.columns || [],
    sheetId
  );

  const relevantColumnIds = Array.from(smartColumns.values())
    .map(column => String(column.id))
    .join(',');

  const totalRowCount = Number(metadata.totalRowCount || 0);

  if (totalRowCount === 0) {
    return {
      columns: metadata.columns || [],
      smartColumns,
      rows: [],
      totalRowCount: 0,
      pagesRead: 0,
      version: metadata.version
    };
  }

  const rows = [];
  const seenRowIds = new Set();
  let page = 1;
  let pagesRead = 0;

  while (rows.length < totalRowCount) {
    const response = smartRequest_(
      'get',
      `/sheets/${sheetId}` +
      `?page=${page}` +
      `&pageSize=${CFG.SMARTSHEET_PAGE_SIZE}` +
      `&columnIds=${relevantColumnIds}` +
      '&exclude=nonexistentCells'
    );

    const pageRows = response.rows || [];
    let newRowsInPage = 0;

    pageRows.forEach(row => {
      const rowId = String(row.id);

      if (!seenRowIds.has(rowId)) {
        seenRowIds.add(rowId);
        rows.push(row);
        newRowsInPage++;
      }
    });

    pagesRead++;

    if (newRowsInPage === 0) {
      break;
    }

    page++;

    if (page > 1000) {
      throw new Error(
        'SEGURIDAD: la paginación de Smartsheet superó 1.000 páginas.'
      );
    }
  }

  if (rows.length !== totalRowCount) {
    throw new Error(
      `Lectura incompleta de Smartsheet ${sheetId}: se esperaban ` +
      `${totalRowCount} filas y se han leído ${rows.length}. ` +
      'Se cancela la sincronización para no crear duplicados.'
    );
  }

  return {
    columns: metadata.columns || [],
    smartColumns,
    rows,
    totalRowCount,
    pagesRead,
    version: metadata.version
  };
}


function requiredSmartColumns_(columns, sheetId) {
  const requiredNames = new Set(
    COLUMN_MAP.map(([, title]) => canonical_(title))
  );

  const result = new Map();

  columns.forEach(column => {
    const normalizedTitle = canonical_(column.title);

    if (!requiredNames.has(normalizedTitle)) {
      return;
    }

    if (result.has(normalizedTitle)) {
      throw new Error(
        `Hay más de una columna equivalente a "${column.title}" ` +
        `en Smartsheet ${sheetId}.`
      );
    }

    if (column.systemColumnType) {
      throw new Error(
        `La columna "${column.title}" de Smartsheet ${sheetId} ` +
        'es de sistema y no se puede actualizar.'
      );
    }

    result.set(normalizedTitle, column);
  });

  COLUMN_MAP.forEach(([, smartTitle]) => {
    if (!result.has(canonical_(smartTitle))) {
      throw new Error(
        `Falta la columna "${smartTitle}" en Smartsheet ${sheetId}.`
      );
    }
  });

  return result;
}


function indexSmartRows_(rows, keyColumnId, totalRowCount) {
  const byId = new Map();
  const rawIds = new Map();

  let rowsWithId = 0;
  let rowsWithoutId = 0;

  rows.forEach(row => {
    row._values = new Map();

    (row.cells || []).forEach(cell => {
      row._values.set(String(cell.columnId), cellText_(cell));
    });

    const rawId = clean_(row._values.get(String(keyColumnId)) || '');

    if (!rawId) {
      rowsWithoutId++;
      return;
    }

    rowsWithId++;

    const normalizedId = normalizeId_(rawId);

    if (!byId.has(normalizedId)) {
      byId.set(normalizedId, []);
    }

    byId.get(normalizedId).push(row);

    if (!rawIds.has(normalizedId)) {
      rawIds.set(normalizedId, rawId);
    }
  });

  byId.forEach(list => {
    list.sort((rowA, rowB) =>
      (rowA.rowNumber || 0) - (rowB.rowNumber || 0)
    );
  });

  return {
    byId,
    rawIds,
    totalRows: Number(totalRowCount || rows.length),
    rowsWithId,
    rowsWithoutId
  };
}


/* ========================================================================
 * CELDAS
 * ====================================================================== */

function cellsToWrite_(sourceRow, smartColumns) {
  return COLUMN_MAP.map(([, smartTitle]) => {
    const columnName = canonical_(smartTitle);

    return writeCell_(
      smartColumns.get(columnName),
      sourceRow.values.get(columnName) || ''
    );
  });
}


function changedCells_(sourceRow, targetRow, smartColumns) {
  const cells = [];

  COLUMN_MAP.forEach(([, smartTitle]) => {
    const columnName = canonical_(smartTitle);
    const column = smartColumns.get(columnName);

    const sourceValue = sourceRow.values.get(columnName) || '';
    const targetValue = targetRow._values.get(String(column.id)) || '';

    if (compare_(sourceValue, column) !== compare_(targetValue, column)) {
      cells.push(writeCell_(column, sourceValue));
    }
  });

  return cells;
}


function writeCell_(column, value) {
  return {
    columnId: column.id,
    value,
    strict: column.type === 'TEXT_NUMBER'
  };
}


/* ========================================================================
 * HTTP
 * ====================================================================== */

function smartRequest_(method, path, payload) {
  const token = requireToken_();
  let lastError;

  for (let attempt = 0; attempt < CFG.RETRIES; attempt++) {
    const options = {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'smartsheet-integration-source':
          'SCRIPT,Kelea,GoogleSheets-RRHH-Sync'
      },
      contentType: 'application/json',
      muteHttpExceptions: true
    };

    if (payload !== undefined) {
      options.payload = JSON.stringify(payload);
    }

    const response = UrlFetchApp.fetch(CFG.SMARTSHEET_API + path, options);

    const status = response.getResponseCode();
    const text = response.getContentText();

    if (status >= 200 && status < 300) {
      return text ? JSON.parse(text) : {};
    }

    let responseBody = null;

    try {
      responseBody = text ? JSON.parse(text) : null;
    } catch (parseError) {
      responseBody = null;
    }

    lastError = new Error(
      `Smartsheet respondió ${status} en ` +
      `${String(method).toUpperCase()} ${path}: ${text}`
    );

    lastError.httpStatus = status;
    lastError.smartsheetErrorCode =
      responseBody && responseBody.errorCode !== undefined
        ? responseBody.errorCode
        : null;
    lastError.smartsheetRefId =
      responseBody && responseBody.refId
        ? responseBody.refId
        : null;

    const canRetry = status === 429 || status >= 500;

    if (!canRetry || attempt === CFG.RETRIES - 1) {
      throw lastError;
    }

    Utilities.sleep(1000 * Math.pow(2, attempt));
  }

  throw lastError;
}


function requireToken_() {
  const token = PropertiesService
    .getScriptProperties()
    .getProperty(CFG.TOKEN_PROPERTY);

  if (!token || !token.trim()) {
    throw new Error(
      `Falta la propiedad ${CFG.TOKEN_PROPERTY} ` +
      'con el token de Smartsheet.'
    );
  }

  return token.trim();
}


/* ========================================================================
 * ESTADO Y UTILIDADES
 * ====================================================================== */

function scheduleFollowUpSyncs_() {
  PropertiesService
    .getScriptProperties()
    .setProperty(
      CFG.FOLLOW_UP_PROPERTY,
      String(CFG.FOLLOW_UP_SYNCS_AFTER_CHANGE)
    );
}


function markSyncPending_(reason) {
  const properties = PropertiesService.getScriptProperties();

  properties.setProperty(CFG.SYNC_PENDING_PROPERTY, '1');
  properties.setProperty(
    CFG.SYNC_REASON_PROPERTY,
    clean_(reason).slice(0, 500)
  );
}


function hasTimeForAnotherRequest_(deadline) {
  return Date.now() + CFG.MIN_TIME_FOR_API_CALL_MS < deadline;
}


function cellText_(cell) {
  if (!cell || cell.value === null || cell.value === undefined) {
    return '';
  }

  if (Array.isArray(cell.value)) {
    return cell.value.join(', ');
  }

  if (typeof cell.value === 'object') {
    return JSON.stringify(cell.value);
  }

  return String(cell.value);
}


function compare_(value, column) {
  const text = clean_(value);

  if (column.type === 'CONTACT_LIST') {
    return text.toLowerCase();
  }

  return text;
}


function clean_(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/\u00A0/g, ' ')
    .replace(/\r\n?/g, '\n')
    .trim();
}


function normalizeId_(value) {
  return clean_(value)
    .replace(/\s+/g, ' ')
    .toLowerCase();
}


function canonical_(value) {
  return clean_(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}


function uniqueBy_(items, keyFunction) {
  const result = new Map();

  items.forEach(item => {
    result.set(keyFunction(item), item);
  });

  return Array.from(result.values());
}
