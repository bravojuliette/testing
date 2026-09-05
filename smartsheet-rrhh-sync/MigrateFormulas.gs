/**
 * MIGRACIÓN DE FÓRMULAS: maestro único -> 3 maestros.
 *
 * Añadir como un archivo NUEVO en el mismo proyecto de Apps Script
 * (Archivo > Nuevo > Script), junto a Code.gs. Usa el mismo token
 * (propiedad SMARTSHEET_TOKEN). No interfiere con la sincronización.
 *
 * PANEL WEB (recomendado): Implementar > Nueva implementación >
 * Aplicación web (ejecutar como tú, acceso solo tú) y abre la URL.
 * Desde el panel puedes rastrear hojas y previsualizar, aplicar o
 * restaurar cada hoja de una en una.
 *
 * Flujo por funciones (alternativa al panel):
 *   0. migrationDebugSheet()    Opcional: comprueba la detección sobre una
 *                               hoja conocida (MIG_CFG.DEBUG_SHEET_ID).
 *   1. migrationDiscover()      Localiza las hojas que referencian al
 *                               maestro antiguo. Continúa solo cada
 *                               minuto hasta terminar.
 *   2. migrationStartPreview()  Simula la migración y escribe el informe
 *                               en un Google Sheet. NO toca Smartsheet.
 *   3. Revisa el informe (sobre todo las filas REVISAR).
 *   4. migrationStartApply()    Crea referencias y reescribe fórmulas.
 *   5. migrationStatus()        Progreso en cualquier momento.
 *   6. migrationStartRollback() Restaura las fórmulas originales desde
 *                               el informe, si hiciera falta.
 *
 * Los pasos 2, 4 y 6 instalan un activador por minuto que se
 * autodestruye al terminar, para sortear el límite de 6 minutos.
 *
 * Reglas de reescritura (solo se tocan fórmulas que usan referencias
 * al maestro antiguo; el resto de la fórmula queda intacto):
 *
 *   INDEX / VLOOKUP / MATCH  -> IFERROR(v_ER, IFERROR(v_WTS, v_AGUA))
 *       La última variante NO va envuelta en IFERROR: si el empleado no
 *       está en ningún maestro, la fórmula da el mismo error que antes,
 *       así se conserva el comportamiento de IFERROR/ISERROR externos.
 *
 *   COUNT / COUNTIF(S) / SUM / SUMIF(S) -> (v_ER + v_WTS + v_AGUA)
 *   MAX                                  -> MAX(v_ER, v_WTS, v_AGUA)
 *   JOIN(COLLECT(...))                   -> (v_ER + v_WTS + v_AGUA)
 *   IF / IFERROR / AND / etc.            -> se entra en sus argumentos.
 *   Cualquier otro uso                   -> REVISAR (no se modifica).
 */

const MIG_CFG = Object.freeze({
  SMARTSHEET_API: 'https://api.smartsheet.com/2.0',
  TOKEN_PROPERTY: 'SMARTSHEET_TOKEN',

  OLD_MASTER_SHEET_ID: '3382072258285444',

  // Prefijo = cómo se llamarán las referencias nuevas: "{ER NOMBRE ...}".
  MASTERS: [
    { key: 'ER',   prefix: 'ER',   sheetId: '5049183181426564' },
    { key: 'WTS',  prefix: 'WTS',  sheetId: '4408773492821892' },
    { key: 'AGUA', prefix: 'AGUA', sheetId: '4550142341369732' }
  ],

  // Vacío = usar la lista descubierta por migrationDiscover().
  CONSUMER_SHEET_IDS: [],

  // Hojas que nunca se deben tocar.
  SKIP_SHEET_IDS: [],

  // Para migrationDebugSheet(): ID de una hoja que sepas que consulta
  // el maestro antiguo.
  DEBUG_SHEET_ID: '',

  PAGE_SIZE: 5000,
  ROW_UPDATE_BATCH: 100,
  RETRIES: 5,

  MAX_EXECUTION_MS: 240000,
  MIN_TIME_FOR_API_CALL_MS: 20000,

  PROP_CONSUMERS: 'MIG_CONSUMER_SHEETS',
  PROP_DISCOVER_CURSOR: 'MIG_DISCOVER_CURSOR',
  PROP_DONE: 'MIG_DONE_SHEETS',
  PROP_MODE: 'MIG_MODE',
  PROP_REPORT: 'MIG_REPORT_SPREADSHEET_ID',
  PROP_ERRORS: 'MIG_SHEET_ERRORS',
  PROP_STATE_PREFIX: 'MIG_STATE_',
  PROP_DISCOVER_INFO: 'MIG_DISCOVER_INFO',

  REPORT_NAME: 'Migración fórmulas Smartsheet - maestros RRHH'
});

const MIG_LOOKUP_FUNCTIONS = new Set(['INDEX', 'VLOOKUP', 'MATCH']);
const MIG_SUM_FUNCTIONS = new Set([
  'COUNT', 'COUNTIF', 'COUNTIFS', 'SUM', 'SUMIF', 'SUMIFS'
]);
const MIG_MAX_FUNCTIONS = new Set(['MAX']);

const MIG_REPORT_HEADERS = Object.freeze([
  'Fecha', 'Modo', 'Sheet ID', 'Hoja', 'Tipo', 'Columna',
  'Fila', 'Row ID', 'Estado', 'Nota', 'Fórmula original', 'Fórmula nueva'
]);


/* ========================================================================
 * FUNCIONES PÚBLICAS
 * ====================================================================== */

/**
 * Localiza las hojas que referencian al maestro antiguo.
 *
 * Recorre todas las hojas accesibles. Si no termina en una ejecución,
 * instala un activador por minuto que continúa solo y se elimina al
 * acabar. Ejecuta migrationStatus() para ver el progreso.
 */
function migrationDiscover() {
  migRequireToken_();

  const finished = migDiscoverPass_();

  if (finished) {
    migRemoveTrigger_('migrationDiscoverWorker');
    return;
  }

  if (!migTriggerInstalled_('migrationDiscoverWorker')) {
    ScriptApp.newTrigger('migrationDiscoverWorker')
      .timeBased()
      .everyMinutes(1)
      .create();
  }

  console.log(
    'El rastreo continúa automáticamente cada minuto hasta terminar. ' +
    'Consulta migrationStatus().'
  );
}


function migrationDiscoverWorker() {
  const lock = LockService.getUserLock();

  if (!lock.tryLock(2000)) {
    return;
  }

  try {
    if (migDiscoverPass_()) {
      migRemoveTrigger_('migrationDiscoverWorker');
    }
  } finally {
    lock.releaseLock();
  }
}


/**
 * Borra la lista de hojas descubiertas y el cursor, para rastrear
 * desde cero.
 */
function migrationDiscoverReset() {
  migRemoveTrigger_('migrationDiscoverWorker');

  const props = PropertiesService.getScriptProperties();
  props.deleteProperty(MIG_CFG.PROP_CONSUMERS);
  props.deleteProperty(MIG_CFG.PROP_DISCOVER_CURSOR);
  props.deleteProperty(MIG_CFG.PROP_DISCOVER_INFO);

  console.log('Rastreo reiniciado.');
}


/**
 * Diagnóstico: muestra las referencias entre hojas de la hoja indicada
 * en MIG_CFG.DEBUG_SHEET_ID y si alguna apunta al maestro antiguo.
 * Úsala con una hoja que sepas que consulta el maestro antiguo.
 */
function migrationDebugSheet() {
  const sheetId = String(MIG_CFG.DEBUG_SHEET_ID || '').trim();

  if (!sheetId) {
    throw new Error('Rellena MIG_CFG.DEBUG_SHEET_ID con el ID de una hoja.');
  }

  const sheet = migRequest_('get', `/sheets/${sheetId}?page=1&pageSize=1`);
  const refs = migListReferences_(sheetId);

  const oldRefs = refs.filter(
    ref => String(ref.sourceSheetId) === MIG_CFG.OLD_MASTER_SHEET_ID
  );

  console.log(JSON.stringify({
    sheetId,
    sheetName: sheet.name,
    accessLevel: sheet.accessLevel,
    oldMasterSheetId: MIG_CFG.OLD_MASTER_SHEET_ID,
    referencesTotal: refs.length,
    referencesToOldMaster: oldRefs.length,
    references: refs.map(ref => ({
      name: ref.name,
      sourceSheetId: String(ref.sourceSheetId),
      pointsToOldMaster:
        String(ref.sourceSheetId) === MIG_CFG.OLD_MASTER_SHEET_ID,
      startColumnId: ref.startColumnId,
      endColumnId: ref.endColumnId,
      startRowId: ref.startRowId || null,
      endRowId: ref.endRowId || null,
      status: ref.status
    }))
  }, null, 2));
}


/**
 * Una pasada de rastreo limitada por tiempo. Devuelve true si terminó.
 */
function migDiscoverPass_() {
  const startedAt = Date.now();
  const deadline = startedAt + MIG_CFG.MAX_EXECUTION_MS;
  const props = PropertiesService.getScriptProperties();

  // Orden fijo por ID para que el cursor sea fiable entre ejecuciones.
  const allSheets = (migRequest_('get', '/sheets?includeAll=true').data || [])
    .slice()
    .sort((a, b) => String(a.id) < String(b.id) ? -1 : 1);

  let cursor = Number(props.getProperty(MIG_CFG.PROP_DISCOVER_CURSOR) || 0);
  const found = migJsonProp_(MIG_CFG.PROP_CONSUMERS, []);
  const foundIds = new Set(found.map(item => String(item.id)));
  const info = migJsonProp_(MIG_CFG.PROP_DISCOVER_INFO, {
    sheetsTotal: 0, scanned: 0, withReferences: 0, errors: 0, errorSamples: [],
    otherSourcesTop: {}
  });
  const skipped = [];
  let scannedNow = 0;

  info.sheetsTotal = allSheets.length;

  const save = () => {
    info.scanned = cursor;
    info.errorSamples = info.errorSamples.slice(0, 30);
    props.setProperty(MIG_CFG.PROP_CONSUMERS, JSON.stringify(found));
    props.setProperty(MIG_CFG.PROP_DISCOVER_CURSOR, String(cursor));
    props.setProperty(MIG_CFG.PROP_DISCOVER_INFO, JSON.stringify(info));
  };

  for (; cursor < allSheets.length; cursor++) {
    if (!migHasTime_(deadline)) {
      break;
    }

    const sheet = allSheets[cursor];
    const sheetId = String(sheet.id);

    if (
      sheetId === MIG_CFG.OLD_MASTER_SHEET_ID ||
      MIG_CFG.MASTERS.some(master => master.sheetId === sheetId) ||
      foundIds.has(sheetId)
    ) {
      continue;
    }

    try {
      const refs = migListReferences_(sheetId);

      if (refs.length) {
        info.withReferences++;
      }

      // Recuento de hojas origen más referenciadas (para detectar copias
      // del maestro o hojas intermedias).
      refs.forEach(ref => {
        const source = String(ref.sourceSheetId);
        info.otherSourcesTop[source] = (info.otherSourcesTop[source] || 0) + 1;
      });

      if (refs.some(ref => String(ref.sourceSheetId) === MIG_CFG.OLD_MASTER_SHEET_ID)) {
        found.push({ id: sheetId, name: sheet.name, accessLevel: sheet.accessLevel, permalink: sheet.permalink || '' });
        foundIds.add(sheetId);
      }
    } catch (error) {
      info.errors++;
      skipped.push({ id: sheetId, name: sheet.name, error: migClean_(error.message).slice(0, 200) });

      if (info.errorSamples.length < 30) {
        info.errorSamples.push({
          id: sheetId,
          name: sheet.name,
          accessLevel: sheet.accessLevel || '',
          httpStatus: error.httpStatus || null,
          error: migClean_(error.message).slice(0, 160)
        });
      }
    }

    scannedNow++;

    if (scannedNow % 100 === 0) {
      save();
    }
  }

  const finished = cursor >= allSheets.length;

  // Conservar solo las 15 hojas origen más referenciadas.
  info.otherSourcesTop = Object.fromEntries(
    Object.entries(info.otherSourcesTop)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 15)
  );

  save();

  if (finished) {
    props.deleteProperty(MIG_CFG.PROP_DISCOVER_CURSOR);
  }

  console.log(JSON.stringify({
    finished,
    message: finished
      ? 'Rastreo completo.'
      : 'Tiempo agotado; continúa en la siguiente ejecución.',
    durationSeconds: Math.round((Date.now() - startedAt) / 1000),
    sheetsScanned: cursor,
    sheetsTotal: allSheets.length,
    consumersFound: found.length,
    consumers: found,
    skippedByError: skipped
  }, null, 2));

  return finished;
}


function migrationStartPreview() {
  migStart_('PREVIEW');
}


function migrationStartApply() {
  migStart_('APPLY');
}


function migrationStartRollback() {
  migStart_('ROLLBACK');
}


/**
 * Detiene el worker sin borrar el progreso.
 */
function migrationStop() {
  migRemoveWorkerTrigger_();
  console.log('Worker de migración detenido.');
}


/**
 * Borra el progreso (no la lista de hojas ni el informe).
 */
function migrationReset() {
  migRemoveWorkerTrigger_();

  const props = PropertiesService.getScriptProperties();
  props.deleteProperty(MIG_CFG.PROP_DONE);
  props.deleteProperty(MIG_CFG.PROP_MODE);
  props.deleteProperty(MIG_CFG.PROP_ERRORS);

  Object.keys(props.getProperties()).forEach(key => {
    if (key.indexOf(MIG_CFG.PROP_STATE_PREFIX) === 0) {
      props.deleteProperty(key);
    }
  });

  console.log('Progreso de migración reiniciado.');
}


function migrationStatus() {
  const props = PropertiesService.getScriptProperties();
  const consumers = migConsumers_();
  const done = new Set(migJsonProp_(MIG_CFG.PROP_DONE, []));

  const discoverCursor = props.getProperty(MIG_CFG.PROP_DISCOVER_CURSOR);

  console.log(JSON.stringify({
    discovery: {
      inProgress: migTriggerInstalled_('migrationDiscoverWorker'),
      sheetsScanned: discoverCursor ? Number(discoverCursor) : '(terminado o no iniciado)',
      consumersFound: consumers.length
    },
    mode: props.getProperty(MIG_CFG.PROP_MODE) || '(ninguno)',
    workerInstalled: migWorkerInstalled_(),
    consumersTotal: consumers.length,
    consumersDone: consumers.filter(item => done.has(String(item.id))).length,
    pending: consumers
      .filter(item => !done.has(String(item.id)))
      .map(item => `${item.id} - ${item.name}`),
    sheetErrors: migJsonProp_(MIG_CFG.PROP_ERRORS, []),
    reportUrl: migReportUrl_()
  }, null, 2));
}


/**
 * Worker del activador. Procesa hojas hasta agotar el tiempo.
 */
function migrationWorker() {
  const lock = LockService.getUserLock();

  if (!lock.tryLock(2000)) {
    return;
  }

  try {
    const props = PropertiesService.getScriptProperties();
    const mode = props.getProperty(MIG_CFG.PROP_MODE);

    if (!mode) {
      migRemoveWorkerTrigger_();
      return;
    }

    const deadline = Date.now() + MIG_CFG.MAX_EXECUTION_MS;
    const consumers = migConsumers_();
    const done = migJsonProp_(MIG_CFG.PROP_DONE, []);
    const doneSet = new Set(done);
    const errors = migJsonProp_(MIG_CFG.PROP_ERRORS, []);
    const context = migBuildContext_();

    for (const consumer of consumers) {
      const sheetId = String(consumer.id);

      if (doneSet.has(sheetId)) {
        continue;
      }

      if (!migHasTime_(deadline)) {
        console.log('Tiempo agotado; continúa en el siguiente minuto.');
        return;
      }

      try {
        if (mode === 'ROLLBACK') {
          const result = migRollbackSheet_(sheetId, consumer.name);
          migSaveSheetState_(sheetId, {
            status: 'RESTAURADA',
            message: `Columnas: ${result.columns}. Celdas: ${result.cells}.`
          });
        } else {
          const result = migProcessSheet_(sheetId, consumer.name, mode, context, deadline);
          migSaveSheetState_(sheetId, migStateFromResult_(result));
        }
      } catch (error) {
        migSaveSheetState_(sheetId, {
          status: 'ERROR',
          message: migClean_(error.message).slice(0, 300)
        });

        console.error(`Error en ${sheetId} (${consumer.name}): ${error.message}`);

        errors.push({
          sheetId,
          name: consumer.name,
          mode,
          error: migClean_(error.message).slice(0, 500)
        });

        migAppendReport_([[
          new Date(), mode, sheetId, consumer.name, 'hoja', '', '', '',
          'ERROR', migClean_(error.message).slice(0, 1000), '', ''
        ]]);
      }

      done.push(sheetId);
      props.setProperty(MIG_CFG.PROP_DONE, JSON.stringify(done));
      props.setProperty(MIG_CFG.PROP_ERRORS, JSON.stringify(errors));
    }

    migRemoveWorkerTrigger_();
    props.deleteProperty(MIG_CFG.PROP_MODE);

    console.log(JSON.stringify({
      message: `Migración en modo ${mode} terminada.`,
      sheets: consumers.length,
      sheetErrors: errors.length,
      reportUrl: migReportUrl_()
    }, null, 2));

  } finally {
    lock.releaseLock();
  }
}


/* ========================================================================
 * ARRANQUE / ACTIVADORES
 * ====================================================================== */

function migStart_(mode) {
  migRequireToken_();

  const consumers = migConsumers_();

  if (!consumers.length) {
    throw new Error(
      'No hay hojas que migrar. Ejecuta migrationDiscover() o rellena ' +
      'MIG_CFG.CONSUMER_SHEET_IDS.'
    );
  }

  const props = PropertiesService.getScriptProperties();
  props.setProperty(MIG_CFG.PROP_MODE, mode);
  props.deleteProperty(MIG_CFG.PROP_DONE);
  props.deleteProperty(MIG_CFG.PROP_ERRORS);

  migEnsureReport_();
  migRemoveWorkerTrigger_();

  ScriptApp.newTrigger('migrationWorker')
    .timeBased()
    .everyMinutes(1)
    .create();

  console.log(
    `Modo ${mode} iniciado para ${consumers.length} hoja(s). ` +
    'El worker se ejecuta cada minuto y se elimina solo al terminar. ' +
    'Informe: ' + migReportUrl_()
  );

  // Primera pasada inmediata.
  migrationWorker();
}


function migRemoveWorkerTrigger_() {
  migRemoveTrigger_('migrationWorker');
}


function migWorkerInstalled_() {
  return migTriggerInstalled_('migrationWorker');
}


function migRemoveTrigger_(handlerName) {
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === handlerName) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}


function migTriggerInstalled_(handlerName) {
  return ScriptApp.getProjectTriggers().some(
    trigger => trigger.getHandlerFunction() === handlerName
  );
}


function migConsumers_() {
  const skip = new Set(MIG_CFG.SKIP_SHEET_IDS.map(String));

  const list = MIG_CFG.CONSUMER_SHEET_IDS.length
    ? MIG_CFG.CONSUMER_SHEET_IDS.map(id => ({ id: String(id), name: '' }))
    : migJsonProp_(MIG_CFG.PROP_CONSUMERS, []);

  return list.filter(item => !skip.has(String(item.id)));
}


/* ========================================================================
 * PROCESO POR HOJA
 * ====================================================================== */

/**
 * Columnas del maestro antiguo y de los nuevos, indexadas por título.
 */
function migBuildContext_() {
  const oldColumns = migRequest_(
    'get',
    `/sheets/${MIG_CFG.OLD_MASTER_SHEET_ID}/columns?includeAll=true`
  ).data || [];

  const oldById = new Map();
  oldColumns.forEach(column => {
    oldById.set(String(column.id), column);
  });

  const masters = MIG_CFG.MASTERS.map(master => {
    const columns = migRequest_(
      'get',
      `/sheets/${master.sheetId}/columns?includeAll=true`
    ).data || [];

    const byTitle = new Map();
    columns.forEach(column => {
      const key = migCanonical_(column.title);
      if (!byTitle.has(key)) {
        byTitle.set(key, column);
      }
    });

    return Object.assign({}, master, { byTitle });
  });

  return { oldById, masters };
}


function migProcessSheet_(sheetId, sheetName, mode, context, deadline) {
  const apply = mode === 'APPLY';
  const refs = migListReferences_(sheetId);

  const oldRefs = refs.filter(
    ref => String(ref.sourceSheetId) === MIG_CFG.OLD_MASTER_SHEET_ID
  );

  if (!oldRefs.length) {
    migAppendReport_([[
      new Date(), mode, sheetId, sheetName, 'hoja', '', '', '',
      'SIN_REFERENCIAS', 'La hoja ya no referencia al maestro antiguo.', '', ''
    ]]);

    return {
      sheetId, sheetName, mode, noRefs: true,
      toCreate: [], refNotes: [], changes: [],
      counts: { total: 0, rewritten: 0, review: 0, errors: 0, refs: 0 }
    };
  }

  // 1. Planificar referencias nuevas.
  const usedNames = new Set(refs.map(ref => ref.name));
  const refMap = new Map();      // nombre antiguo -> { ER: nombre, ... } | null
  const toCreate = [];           // referencias que hay que crear
  const refNotes = [];

  oldRefs.forEach(oldRef => {
    const startColumn = context.oldById.get(String(oldRef.startColumnId));
    const endColumn = context.oldById.get(String(oldRef.endColumnId));

    if (!startColumn || !endColumn) {
      refMap.set(oldRef.name, null);
      refNotes.push(
        `{${oldRef.name}}: columnas ${oldRef.startColumnId}-${oldRef.endColumnId} ` +
        'no existen en el maestro antiguo.'
      );
      return;
    }

    if (oldRef.startRowId || oldRef.endRowId) {
      refNotes.push(
        `{${oldRef.name}}: la referencia antigua estaba limitada a filas; ` +
        'las nuevas abarcan la columna completa.'
      );
    }

    const oldTitles = migColumnsBetween_(context.oldById, startColumn, endColumn)
      .map(column => column.title);

    const mapping = {};
    let mappable = true;

    context.masters.forEach(master => {
      const newStart = master.byTitle.get(migCanonical_(startColumn.title));
      const newEnd = master.byTitle.get(migCanonical_(endColumn.title));

      if (!newStart || !newEnd) {
        mappable = false;
        refNotes.push(
          `{${oldRef.name}}: falta la columna "${startColumn.title}" o ` +
          `"${endColumn.title}" en ${master.key}.`
        );
        return;
      }

      const existing = refs.find(ref =>
        String(ref.sourceSheetId) === master.sheetId &&
        String(ref.startColumnId) === String(newStart.id) &&
        String(ref.endColumnId) === String(newEnd.id) &&
        !ref.startRowId && !ref.endRowId
      ) || toCreate.find(item =>
        item.sourceSheetId === master.sheetId &&
        item.startColumnId === newStart.id &&
        item.endColumnId === newEnd.id
      );

      if (existing) {
        mapping[master.key] = existing.name;
        return;
      }

      const baseName = migReferenceName_(master.prefix, oldTitles);
      const name = migUniqueName_(baseName, usedNames);
      usedNames.add(name);

      toCreate.push({
        name,
        sourceSheetId: master.sheetId,
        startColumnId: newStart.id,
        endColumnId: newEnd.id
      });

      mapping[master.key] = name;
    });

    refMap.set(oldRef.name, mappable ? mapping : null);
  });

  // 2. Leer fórmulas.
  const columns = migRequest_(
    'get',
    `/sheets/${sheetId}/columns?includeAll=true`
  ).data || [];

  const columnTitle = new Map();
  const columnFormulaIds = new Set();

  columns.forEach(column => {
    columnTitle.set(String(column.id), column.title);
    if (column.formula) {
      columnFormulaIds.add(String(column.id));
    }
  });

  const oldNames = Array.from(refMap.keys());
  const changes = [];   // { kind, columnId, rowId, rowNumber, oldFormula, newFormula, status, note }

  columns.forEach(column => {
    if (column.formula && migContainsRef_(column.formula, oldNames)) {
      changes.push(Object.assign(
        { kind: 'columna', columnId: column.id, rowId: '', rowNumber: '' },
        migRewriteFormula_(column.formula, refMap, context.masters)
      ));
    }
  });

  migReadRows_(sheetId).forEach(row => {
    (row.cells || []).forEach(cell => {
      if (
        !cell.formula ||
        columnFormulaIds.has(String(cell.columnId)) ||
        !migContainsRef_(cell.formula, oldNames)
      ) {
        return;
      }

      changes.push(Object.assign(
        {
          kind: 'celda',
          columnId: cell.columnId,
          rowId: row.id,
          rowNumber: row.rowNumber
        },
        migRewriteFormula_(cell.formula, refMap, context.masters)
      ));
    });
  });

  const rewritable = changes.filter(item => item.status === 'REESCRITA');

  // 3. Aplicar.
  if (apply && rewritable.length) {
    toCreate.forEach(ref => {
      migRequest_('post', `/sheets/${sheetId}/crosssheetreferences`, ref);
    });

    rewritable
      .filter(item => item.kind === 'columna')
      .forEach(item => {
        try {
          migRequest_(
            'put',
            `/sheets/${sheetId}/columns/${item.columnId}`,
            { formula: item.newFormula }
          );
        } catch (error) {
          item.status = 'ERROR';
          item.note = migClean_(error.message).slice(0, 500);
        }
      });

    const cellChanges = rewritable.filter(item => item.kind === 'celda');

    for (let start = 0; start < cellChanges.length; start += MIG_CFG.ROW_UPDATE_BATCH) {
      const batch = cellChanges.slice(start, start + MIG_CFG.ROW_UPDATE_BATCH);

      try {
        migRequest_(
          'put',
          `/sheets/${sheetId}/rows`,
          migRowsPayload_(batch, 'newFormula')
        );
      } catch (batchError) {
        // Reintento individual para aislar la fórmula que falla.
        batch.forEach(item => {
          try {
            migRequest_(
              'put',
              `/sheets/${sheetId}/rows`,
              migRowsPayload_([item], 'newFormula')
            );
          } catch (error) {
            item.status = 'ERROR';
            item.note = migClean_(error.message).slice(0, 500);
          }
        });
      }
    }
  }

  // 4. Informe.
  const now = new Date();
  const rows = [];

  rows.push([
    now, mode, sheetId, sheetName, 'resumen', '', '', '',
    apply ? 'APLICADO' : 'SIMULADO',
    `Fórmulas: ${changes.length}. Reescritas: ` +
    `${changes.filter(item => item.status === 'REESCRITA').length}. ` +
    `A revisar: ${changes.filter(item => item.status === 'REVISAR').length}. ` +
    `Errores: ${changes.filter(item => item.status === 'ERROR').length}. ` +
    `Referencias nuevas: ${toCreate.length}. ` +
    refNotes.join(' '),
    '', ''
  ]);

  toCreate.forEach(ref => {
    rows.push([
      now, mode, sheetId, sheetName, 'referencia', '', '', '',
      apply ? 'CREADA' : 'SE CREARÁ',
      `{${ref.name}} -> hoja ${ref.sourceSheetId}, columnas ` +
      `${ref.startColumnId}..${ref.endColumnId}`,
      '', ''
    ]);
  });

  changes.forEach(item => {
    rows.push([
      now, mode, sheetId, sheetName, item.kind,
      columnTitle.get(String(item.columnId)) || item.columnId,
      item.rowNumber, item.rowId ? String(item.rowId) : '',
      item.status, item.note, item.oldFormula, item.newFormula || ''
    ]);
  });

  migAppendReport_(rows);

  return {
    sheetId,
    sheetName,
    mode,
    noRefs: false,
    toCreate: toCreate.map(ref => ref.name),
    refNotes,
    changes: changes.map(item => ({
      kind: item.kind,
      column: columnTitle.get(String(item.columnId)) || String(item.columnId),
      rowNumber: item.rowNumber || '',
      status: item.status,
      note: item.note || '',
      oldFormula: item.oldFormula,
      newFormula: item.newFormula || ''
    })),
    counts: {
      total: changes.length,
      rewritten: changes.filter(item => item.status === 'REESCRITA').length,
      review: changes.filter(item => item.status === 'REVISAR').length,
      errors: changes.filter(item => item.status === 'ERROR').length,
      refs: toCreate.length
    }
  };
}


function migRowsPayload_(items, formulaField) {
  const byRow = new Map();

  items.forEach(item => {
    const rowId = String(item.rowId);

    if (!byRow.has(rowId)) {
      byRow.set(rowId, { id: Number(item.rowId), cells: [] });
    }

    byRow.get(rowId).cells.push({
      columnId: item.columnId,
      formula: item[formulaField]
    });
  });

  return Array.from(byRow.values());
}


/**
 * Restaura las fórmulas originales de una hoja a partir de las filas
 * REESCRITA en modo APPLY del informe.
 */
function migRollbackSheet_(sheetId, sheetName) {
  const sheet = migReportSheet_();
  const values = sheet.getDataRange().getValues();
  const header = values[0];

  const col = name => header.indexOf(name);
  const iMode = col('Modo'), iSheet = col('Sheet ID'), iType = col('Tipo');
  const iRowId = col('Row ID'), iStatus = col('Estado'), iOld = col('Fórmula original');
  const iColumn = col('Columna');

  const columns = migRequest_(
    'get',
    `/sheets/${sheetId}/columns?includeAll=true`
  ).data || [];

  const columnIdByTitle = new Map(
    columns.map(column => [column.title, column.id])
  );

  const columnItems = [];
  const cellItems = [];

  values.slice(1).forEach(row => {
    if (
      String(row[iMode]) !== 'APPLY' ||
      String(row[iSheet]) !== String(sheetId) ||
      String(row[iStatus]) !== 'REESCRITA'
    ) {
      return;
    }

    const columnId = columnIdByTitle.get(String(row[iColumn]));

    if (!columnId) {
      return;
    }

    if (String(row[iType]) === 'columna') {
      columnItems.push({ columnId, formula: String(row[iOld]) });
    } else if (String(row[iType]) === 'celda' && row[iRowId]) {
      cellItems.push({
        columnId,
        rowId: String(row[iRowId]),
        oldFormula: String(row[iOld])
      });
    }
  });

  columnItems.forEach(item => {
    migRequest_(
      'put',
      `/sheets/${sheetId}/columns/${item.columnId}`,
      { formula: item.formula }
    );
  });

  for (let start = 0; start < cellItems.length; start += MIG_CFG.ROW_UPDATE_BATCH) {
    migRequest_(
      'put',
      `/sheets/${sheetId}/rows`,
      migRowsPayload_(cellItems.slice(start, start + MIG_CFG.ROW_UPDATE_BATCH), 'oldFormula')
    );
  }

  migAppendReport_([[
    new Date(), 'ROLLBACK', sheetId, sheetName, 'resumen', '', '', '',
    'RESTAURADO',
    `Columnas: ${columnItems.length}. Celdas: ${cellItems.length}.`,
    '', ''
  ]]);

  return { columns: columnItems.length, cells: cellItems.length };
}


/* ========================================================================
 * MOTOR DE REESCRITURA DE FÓRMULAS (puro, sin llamadas externas)
 * ====================================================================== */

/**
 * Devuelve { oldFormula, newFormula, status, note }.
 * status: REESCRITA | REVISAR
 */
function migRewriteFormula_(formula, refMap, masters) {
  const oldNames = Array.from(refMap.keys());

  try {
    const rewritten = migRewriteExpr_(formula, refMap, masters, oldNames);

    if (migContainsRef_(rewritten, oldNames)) {
      return {
        oldFormula: formula,
        newFormula: '',
        status: 'REVISAR',
        note: 'Quedan referencias antiguas fuera de un patrón reconocido.'
      };
    }

    return {
      oldFormula: formula,
      newFormula: rewritten,
      status: 'REESCRITA',
      note: ''
    };

  } catch (error) {
    return {
      oldFormula: formula,
      newFormula: '',
      status: 'REVISAR',
      note: migClean_(error.message)
    };
  }
}


function migRewriteExpr_(expr, refMap, masters, oldNames) {
  let out = '';
  let i = 0;

  while (i < expr.length) {
    const ch = expr[i];

    // Cadena de texto: copiar tal cual.
    if (ch === '"') {
      const end = migFindStringEnd_(expr, i);
      out += expr.slice(i, end + 1);
      i = end + 1;
      continue;
    }

    // Referencia {..} o columna [..]: copiar tal cual.
    if (ch === '{' || ch === '[') {
      const close = ch === '{' ? '}' : ']';
      const end = expr.indexOf(close, i);

      if (end < 0) {
        throw new Error('Fórmula mal formada: falta ' + close);
      }

      out += expr.slice(i, end + 1);
      i = end + 1;
      continue;
    }

    // Identificador: posible función.
    if (/[A-Za-z_]/.test(ch)) {
      let j = i;
      while (j < expr.length && /[A-Za-z0-9_.]/.test(expr[j])) {
        j++;
      }

      const ident = expr.slice(i, j);
      let k = j;
      while (k < expr.length && expr[k] === ' ') {
        k++;
      }

      if (expr[k] !== '(') {
        out += ident;
        i = j;
        continue;
      }

      const close = migFindMatchingParen_(expr, k);
      const args = expr.slice(k + 1, close);
      const name = ident.toUpperCase();
      const callText = ident + '(' + args + ')';

      if (!migContainsRef_(args, oldNames)) {
        out += callText;
        i = close + 1;
        continue;
      }

      if (MIG_LOOKUP_FUNCTIONS.has(name)) {
        out += migCascade_(migVariants_(callText, refMap, masters, oldNames));

      } else if (MIG_SUM_FUNCTIONS.has(name)) {
        out += '(' + migVariants_(callText, refMap, masters, oldNames).join(' + ') + ')';

      } else if (MIG_MAX_FUNCTIONS.has(name)) {
        out += 'MAX(' + migVariants_(callText, refMap, masters, oldNames).join(', ') + ')';

      } else if (name === 'JOIN' && /^\s*COLLECT\s*\(/i.test(args)) {
        out += '(' + migVariants_(callText, refMap, masters, oldNames).join(' + ') + ')';

      } else if (name === 'COLLECT' || name === 'DISTINCT' || name === 'AVG' || name === 'MIN') {
        throw new Error(
          `${name}() sobre el maestro antiguo no se puede repartir ` +
          'automáticamente entre varios maestros.'
        );

      } else {
        // IF, IFERROR, AND, OR, NOT, ISERROR, JOIN, etc.: entrar en argumentos.
        out += ident + '(' + migRewriteExpr_(args, refMap, masters, oldNames) + ')';
      }

      i = close + 1;
      continue;
    }

    out += ch;
    i++;
  }

  return out;
}


/**
 * Genera una variante del texto por maestro, sustituyendo cada referencia
 * antigua por la nueva correspondiente.
 */
function migVariants_(text, refMap, masters, oldNames) {
  return masters.map(master =>
    text.replace(/\{([^}]*)\}/g, (match, name) => {
      if (!oldNames.includes(name)) {
        return match;
      }

      const mapping = refMap.get(name);

      if (!mapping || !mapping[master.key]) {
        throw new Error(
          `La referencia {${name}} no tiene equivalente en ${master.key}.`
        );
      }

      return '{' + mapping[master.key] + '}';
    })
  );
}


/**
 * IFERROR(a, IFERROR(b, c)): la última variante no se envuelve para que
 * la fórmula siga dando error cuando el empleado no existe en ninguno.
 */
function migCascade_(variants) {
  return variants.reduceRight((acc, variant) =>
    acc === null ? variant : `IFERROR(${variant}, ${acc})`
  , null);
}


function migContainsRef_(text, names) {
  if (!names.length) {
    return false;
  }

  const regex = /\{([^}]*)\}/g;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (names.includes(match[1])) {
      return true;
    }
  }

  return false;
}


function migFindStringEnd_(expr, start) {
  let i = start + 1;

  while (i < expr.length) {
    if (expr[i] === '"') {
      if (expr[i + 1] === '"') {
        i += 2;
        continue;
      }
      return i;
    }
    i++;
  }

  throw new Error('Fórmula mal formada: cadena sin cerrar.');
}


function migFindMatchingParen_(expr, openIndex) {
  let depth = 0;
  let i = openIndex;

  while (i < expr.length) {
    const ch = expr[i];

    if (ch === '"') {
      i = migFindStringEnd_(expr, i) + 1;
      continue;
    }

    if (ch === '{' || ch === '[') {
      const end = expr.indexOf(ch === '{' ? '}' : ']', i);
      i = end < 0 ? expr.length : end + 1;
      continue;
    }

    if (ch === '(') {
      depth++;
    } else if (ch === ')') {
      depth--;
      if (depth === 0) {
        return i;
      }
    }

    i++;
  }

  throw new Error('Fórmula mal formada: paréntesis sin cerrar.');
}


/* ========================================================================
 * NOMBRES DE REFERENCIAS
 * ====================================================================== */

function migReferenceName_(prefix, titles) {
  const body = titles.length === 1
    ? titles[0]
    : `${titles[0]} a ${titles[titles.length - 1]}`;

  return (prefix + ' ' + body)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9 _-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 60);
}


function migUniqueName_(baseName, usedNames) {
  if (!usedNames.has(baseName)) {
    return baseName;
  }

  let counter = 2;
  while (usedNames.has(`${baseName} ${counter}`)) {
    counter++;
  }

  return `${baseName} ${counter}`;
}


/**
 * Columnas del maestro antiguo entre dos columnas (ambas incluidas),
 * ordenadas por índice.
 */
function migColumnsBetween_(oldById, startColumn, endColumn) {
  const from = Math.min(startColumn.index, endColumn.index);
  const to = Math.max(startColumn.index, endColumn.index);

  return Array.from(oldById.values())
    .filter(column => column.index >= from && column.index <= to)
    .sort((a, b) => a.index - b.index);
}


/* ========================================================================
 * LECTURA DE SMARTSHEET
 * ====================================================================== */

function migListReferences_(sheetId) {
  return migRequest_(
    'get',
    `/sheets/${sheetId}/crosssheetreferences?includeAll=true`
  ).data || [];
}


function migReadRows_(sheetId) {
  const rows = [];
  let page = 1;

  while (true) {
    const response = migRequest_(
      'get',
      `/sheets/${sheetId}?page=${page}&pageSize=${MIG_CFG.PAGE_SIZE}` +
      '&exclude=nonexistentCells'
    );

    const pageRows = response.rows || [];
    pageRows.forEach(row => rows.push(row));

    const total = Number(response.totalRowCount || 0);

    if (!pageRows.length || rows.length >= total || page > 1000) {
      break;
    }

    page++;
  }

  return rows;
}


/* ========================================================================
 * INFORME EN GOOGLE SHEETS
 * ====================================================================== */

function migEnsureReport_() {
  const props = PropertiesService.getScriptProperties();
  const existingId = props.getProperty(MIG_CFG.PROP_REPORT);

  if (existingId) {
    try {
      SpreadsheetApp.openById(existingId);
      return existingId;
    } catch (error) {
      // El informe fue borrado: se crea otro.
    }
  }

  const spreadsheet = SpreadsheetApp.create(MIG_CFG.REPORT_NAME);
  const sheet = spreadsheet.getSheets()[0];

  sheet.setName('Informe');
  sheet.getRange(1, 1, 1, MIG_REPORT_HEADERS.length)
    .setValues([MIG_REPORT_HEADERS])
    .setFontWeight('bold');
  sheet.setFrozenRows(1);

  props.setProperty(MIG_CFG.PROP_REPORT, spreadsheet.getId());
  return spreadsheet.getId();
}


function migReportSheet_() {
  const id = migEnsureReport_();
  return SpreadsheetApp.openById(id).getSheetByName('Informe');
}


function migReportUrl_() {
  const id = PropertiesService.getScriptProperties().getProperty(MIG_CFG.PROP_REPORT);
  return id ? `https://docs.google.com/spreadsheets/d/${id}` : '(sin informe)';
}


function migAppendReport_(rows) {
  if (!rows.length) {
    return;
  }

  const sheet = migReportSheet_();
  const width = MIG_REPORT_HEADERS.length;

  const normalized = rows.map(row => {
    const copy = row.slice(0, width);
    while (copy.length < width) {
      copy.push('');
    }
    return copy.map(value => value === undefined || value === null ? '' : value);
  });

  sheet.getRange(sheet.getLastRow() + 1, 1, normalized.length, width)
    .setValues(normalized);
}



/* ========================================================================
 * PANEL WEB (Implementar > Nueva implementación > Aplicación web)
 * ====================================================================== */

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Panel')
    .setTitle('Migración de fórmulas Smartsheet')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}


/**
 * Estado global para el panel.
 */
function uiGetState() {
  const props = PropertiesService.getScriptProperties();
  const all = props.getProperties();
  const consumers = migConsumers_();
  const discoverCursor = all[MIG_CFG.PROP_DISCOVER_CURSOR];

  return {
    reportUrl: migReportUrl_(),
    oldMasterSheetId: MIG_CFG.OLD_MASTER_SHEET_ID,
    masters: MIG_CFG.MASTERS.map(master => ({ key: master.key, sheetId: master.sheetId })),
    discovery: Object.assign(
      {
        inProgress: migTriggerInstalled_('migrationDiscoverWorker'),
        sheetsScanned: discoverCursor ? Number(discoverCursor) : null,
        consumersFound: consumers.length
      },
      migJsonProp_(MIG_CFG.PROP_DISCOVER_INFO, {})
    ),
    batchMode: all[MIG_CFG.PROP_MODE] || '',
    batchWorkerInstalled: migWorkerInstalled_(),
    sheets: consumers.map(consumer => {
      const raw = all[MIG_CFG.PROP_STATE_PREFIX + consumer.id];
      let state = null;

      try {
        state = raw ? JSON.parse(raw) : null;
      } catch (error) {
        state = null;
      }

      return {
        id: String(consumer.id),
        name: consumer.name || '',
        permalink: consumer.permalink || '',
        accessLevel: consumer.accessLevel || '',
        state: state || { status: 'PENDIENTE' }
      };
    })
  };
}


function uiPreviewSheet(sheetId) {
  return uiRunSheet_(sheetId, 'PREVIEW');
}


function uiApplySheet(sheetId) {
  return uiRunSheet_(sheetId, 'APPLY');
}


function uiRunSheet_(sheetId, mode) {
  migRequireToken_();
  migEnsureReport_();

  const consumer = migConsumers_().find(item => String(item.id) === String(sheetId));
  const sheetName = consumer ? consumer.name : '';
  const deadline = Date.now() + MIG_CFG.MAX_EXECUTION_MS;

  try {
    const context = migBuildContext_();
    const result = migProcessSheet_(String(sheetId), sheetName, mode, context, deadline);
    migSaveSheetState_(sheetId, migStateFromResult_(result));
    return result;

  } catch (error) {
    migSaveSheetState_(sheetId, {
      status: 'ERROR',
      message: migClean_(error.message).slice(0, 300)
    });

    migAppendReport_([[
      new Date(), mode, String(sheetId), sheetName, 'hoja', '', '', '',
      'ERROR', migClean_(error.message).slice(0, 1000), '', ''
    ]]);

    throw error;
  }
}


function uiRollbackSheet(sheetId) {
  migRequireToken_();

  const consumer = migConsumers_().find(item => String(item.id) === String(sheetId));
  const sheetName = consumer ? consumer.name : '';

  try {
    const result = migRollbackSheet_(String(sheetId), sheetName);

    migSaveSheetState_(sheetId, {
      status: 'RESTAURADA',
      message: `Columnas: ${result.columns}. Celdas: ${result.cells}.`
    });

    return result;

  } catch (error) {
    migSaveSheetState_(sheetId, {
      status: 'ERROR',
      message: migClean_(error.message).slice(0, 300)
    });

    throw error;
  }
}


/**
 * Detalle de la última acción sobre una hoja, leído del informe.
 */
function uiGetSheetDetail(sheetId) {
  const sheet = migReportSheet_();
  const values = sheet.getDataRange().getValues();
  const header = values[0];
  const col = name => header.indexOf(name);

  const iDate = col('Fecha'), iMode = col('Modo'), iSheet = col('Sheet ID');
  const iType = col('Tipo'), iColumn = col('Columna'), iRow = col('Fila');
  const iStatus = col('Estado'), iNote = col('Nota');
  const iOld = col('Fórmula original'), iNew = col('Fórmula nueva');

  // Localizar el último "resumen" de esta hoja y tomar su lote.
  let lastSummary = -1;

  for (let i = values.length - 1; i >= 1; i--) {
    if (
      String(values[i][iSheet]) === String(sheetId) &&
      String(values[i][iType]) === 'resumen'
    ) {
      lastSummary = i;
      break;
    }
  }

  if (lastSummary < 0) {
    return { mode: '', summary: '', rows: [] };
  }

  const batchTime = String(values[lastSummary][iDate]);
  const rows = [];

  for (let i = lastSummary + 1; i < values.length; i++) {
    const row = values[i];

    if (
      String(row[iSheet]) !== String(sheetId) ||
      String(row[iDate]) !== batchTime
    ) {
      if (String(row[iSheet]) === String(sheetId)) {
        break;
      }
      continue;
    }

    rows.push({
      kind: String(row[iType]),
      column: String(row[iColumn]),
      rowNumber: String(row[iRow]),
      status: String(row[iStatus]),
      note: String(row[iNote]),
      oldFormula: String(row[iOld]),
      newFormula: String(row[iNew])
    });
  }

  return {
    mode: String(values[lastSummary][iMode]),
    date: batchTime,
    summary: String(values[lastSummary][iNote]),
    rows
  };
}


/**
 * Comprueba una hoja concreta: acceso y referencias que contiene.
 */
function uiDebugSheet(sheetId) {
  migRequireToken_();
  sheetId = String(sheetId || '').trim();

  if (!/^\d+$/.test(sheetId)) {
    throw new Error('El ID de hoja debe ser numérico (Archivo > Propiedades en Smartsheet).');
  }

  let sheet;

  try {
    sheet = migRequest_('get', `/sheets/${sheetId}?page=1&pageSize=1`);
  } catch (error) {
    return {
      sheetId,
      accessible: false,
      httpStatus: error.httpStatus || null,
      error: migClean_(error.message).slice(0, 300),
      references: []
    };
  }

  const refs = migListReferences_(sheetId);
  const columnFormulas = (sheet.columns || []).filter(column => column.formula).length;

  return {
    sheetId,
    accessible: true,
    name: sheet.name,
    permalink: sheet.permalink || '',
    accessLevel: sheet.accessLevel,
    totalRows: sheet.totalRowCount,
    columnFormulas,
    referencesToOldMaster: refs.filter(
      ref => String(ref.sourceSheetId) === MIG_CFG.OLD_MASTER_SHEET_ID
    ).length,
    alreadyListed: migConsumers_().some(item => String(item.id) === sheetId),
    references: refs.map(ref => ({
      name: ref.name,
      sourceSheetId: String(ref.sourceSheetId),
      pointsToOldMaster: String(ref.sourceSheetId) === MIG_CFG.OLD_MASTER_SHEET_ID,
      pointsToNewMaster: MIG_CFG.MASTERS.some(master => master.sheetId === String(ref.sourceSheetId)),
      status: ref.status || ''
    }))
  };
}


/**
 * Añade una hoja a la lista manualmente.
 */
function uiAddSheet(sheetId) {
  const debug = uiDebugSheet(sheetId);

  if (!debug.accessible) {
    throw new Error('No se puede acceder a la hoja: ' + debug.error);
  }

  const props = PropertiesService.getScriptProperties();
  const consumers = migJsonProp_(MIG_CFG.PROP_CONSUMERS, []);

  if (!consumers.some(item => String(item.id) === debug.sheetId)) {
    consumers.push({
      id: debug.sheetId,
      name: debug.name,
      accessLevel: debug.accessLevel,
      permalink: debug.permalink
    });
    props.setProperty(MIG_CFG.PROP_CONSUMERS, JSON.stringify(consumers));
  }

  return uiGetState();
}


function uiStartDiscover() {
  migrationDiscover();
  return uiGetState();
}


function uiResetDiscover() {
  migrationDiscoverReset();
  return uiGetState();
}


function uiRemoveSheet(sheetId) {
  const props = PropertiesService.getScriptProperties();
  const consumers = migJsonProp_(MIG_CFG.PROP_CONSUMERS, [])
    .filter(item => String(item.id) !== String(sheetId));

  props.setProperty(MIG_CFG.PROP_CONSUMERS, JSON.stringify(consumers));
  props.deleteProperty(MIG_CFG.PROP_STATE_PREFIX + sheetId);

  return uiGetState();
}


function migSaveSheetState_(sheetId, state) {
  PropertiesService.getScriptProperties().setProperty(
    MIG_CFG.PROP_STATE_PREFIX + sheetId,
    JSON.stringify(Object.assign({ at: new Date().toISOString() }, state))
  );
}


function migStateFromResult_(result) {
  if (result.noRefs) {
    return { status: 'SIN_REFERENCIAS', message: 'No referencia al maestro antiguo.' };
  }

  const counts = result.counts;
  const status = result.mode === 'APPLY'
    ? (counts.errors ? 'APLICADA_CON_ERRORES' : 'APLICADA')
    : 'PREVISUALIZADA';

  return {
    status,
    rewritten: counts.rewritten,
    review: counts.review,
    errors: counts.errors,
    refs: counts.refs,
    message: result.refNotes.join(' ')
  };
}


/* ========================================================================
 * HTTP Y UTILIDADES
 * ====================================================================== */

function migRequest_(method, path, payload) {
  const token = migRequireToken_();
  let lastError;

  for (let attempt = 0; attempt < MIG_CFG.RETRIES; attempt++) {
    const options = {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'smartsheet-integration-source': 'SCRIPT,Kelea,Formula-Migration'
      },
      contentType: 'application/json',
      muteHttpExceptions: true
    };

    if (payload !== undefined) {
      options.payload = JSON.stringify(payload);
    }

    const response = UrlFetchApp.fetch(MIG_CFG.SMARTSHEET_API + path, options);
    const status = response.getResponseCode();
    const text = response.getContentText();

    if (status >= 200 && status < 300) {
      return text ? JSON.parse(text) : {};
    }

    lastError = new Error(
      `Smartsheet respondió ${status} en ${String(method).toUpperCase()} ${path}: ${text}`
    );
    lastError.httpStatus = status;

    const canRetry = status === 429 || status >= 500;

    if (!canRetry || attempt === MIG_CFG.RETRIES - 1) {
      throw lastError;
    }

    Utilities.sleep(1000 * Math.pow(2, attempt));
  }

  throw lastError;
}


function migRequireToken_() {
  const token = PropertiesService
    .getScriptProperties()
    .getProperty(MIG_CFG.TOKEN_PROPERTY);

  if (!token || !token.trim()) {
    throw new Error(`Falta la propiedad ${MIG_CFG.TOKEN_PROPERTY}.`);
  }

  return token.trim();
}


function migJsonProp_(name, fallback) {
  const raw = PropertiesService.getScriptProperties().getProperty(name);

  if (!raw) {
    return fallback;
  }

  try {
    return JSON.parse(raw);
  } catch (error) {
    return fallback;
  }
}


function migHasTime_(deadline) {
  return Date.now() + MIG_CFG.MIN_TIME_FOR_API_CALL_MS < deadline;
}


function migClean_(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/ /g, ' ')
    .replace(/\r\n?/g, '\n')
    .trim();
}


function migCanonical_(value) {
  return migClean_(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}
