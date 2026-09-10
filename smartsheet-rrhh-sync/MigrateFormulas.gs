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
 * Reglas de reescritura. Se tocan las fórmulas que usan referencias al
 * maestro antiguo O a cualquiera de los maestros actuales (así una hoja
 * migrada a 3 maestros se vuelve a migrar a 4 sin restaurar nada: la
 * cascada existente se reconoce, se colapsa y se reconstruye). Volver a
 * ejecutar sobre una hoja ya migrada no cambia nada (SIN_CAMBIOS).
 *
 *   INDEX / VLOOKUP / MATCH  -> IFERROR(v_ER, IFERROR(v_WS, IFERROR(v_CORP, v_AGUA)))
 *       La última variante NO va envuelta en IFERROR: si el empleado no
 *       está en ningún maestro, la fórmula da el mismo error que antes,
 *       así se conserva el comportamiento de IFERROR/ISERROR externos.
 *
 *   COUNT / COUNTIF(S) / SUM / SUMIF(S) -> (v_ER + v_WS + v_CORP + v_AGUA)
 *   MAX                                  -> MAX(v_ER, v_WS, v_CORP, v_AGUA)
 *   JOIN(COLLECT(...))                   -> (v_ER + v_WS + v_CORP + v_AGUA)
 *   IF / IFERROR / AND / etc.            -> se entra en sus argumentos.
 *   Cualquier otro uso                   -> REVISAR (no se modifica).
 */

const MIG_CFG = Object.freeze({
  SMARTSHEET_API: 'https://api.smartsheet.com/2.0',
  TOKEN_PROPERTY: 'SMARTSHEET_TOKEN',

  OLD_MASTER_SHEET_ID: '3382072258285444',

  // Prefijo = cómo se llamarán las referencias nuevas: "{ER NOMBRE ...}".
  // El orden define el orden de búsqueda en cascada.
  MASTERS: [
    { key: 'ER',   prefix: 'ER',   sheetId: '5049183181426564' },
    { key: 'WS',   prefix: 'WS',   sheetId: '3857949708472196' },
    { key: 'CORP', prefix: 'CORP', sheetId: '4408773492821892' },
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
  const familyIds = migFamilySheetIds_();
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

    if (familyIds.has(sheetId) || foundIds.has(sheetId)) {
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

      if (refs.some(ref => familyIds.has(String(ref.sourceSheetId)))) {
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
 * IDs de las hojas "de la familia": el maestro antiguo y los actuales.
 */
function migFamilySheetIds_() {
  return new Set(
    [MIG_CFG.OLD_MASTER_SHEET_ID].concat(MIG_CFG.MASTERS.map(master => master.sheetId))
  );
}


/**
 * Columnas del maestro antiguo y de los maestros actuales, indexadas
 * por ID y por título.
 */
function migBuildContext_() {
  const family = new Map();

  const load = (sheetId, meta) => {
    const columns = migRequest_(
      'get',
      `/sheets/${sheetId}/columns?includeAll=true`
    ).data || [];

    const byId = new Map();
    const byTitle = new Map();

    columns.forEach(column => {
      byId.set(String(column.id), column);
      const key = migCanonical_(column.title);
      if (!byTitle.has(key)) {
        byTitle.set(key, column);
      }
    });

    family.set(String(sheetId), Object.assign(
      { sheetId: String(sheetId), columns, byId, byTitle },
      meta
    ));
  };

  load(MIG_CFG.OLD_MASTER_SHEET_ID, { key: 'OLD', prefix: '', isMaster: false });

  MIG_CFG.MASTERS.forEach(master => {
    load(master.sheetId, { key: master.key, prefix: master.prefix, isMaster: true });
  });

  return {
    family,
    masters: MIG_CFG.MASTERS.map(master => family.get(master.sheetId))
  };
}


function migProcessSheet_(sheetId, sheetName, mode, context, deadline) {
  const apply = mode === 'APPLY';
  const refs = migListReferences_(sheetId);

  const familyRefs = refs.filter(
    ref => context.family.has(String(ref.sourceSheetId))
  );

  if (!familyRefs.length) {
    migAppendReport_([[
      new Date(), mode, sheetId, sheetName, 'hoja', '', '', '',
      'SIN_REFERENCIAS', 'La hoja no referencia a ningún maestro.', '', ''
    ]]);

    return {
      sheetId, sheetName, mode, noRefs: true,
      toCreate: [], refNotes: [], changes: [],
      counts: { total: 0, rewritten: 0, unchanged: 0, review: 0, errors: 0, refs: 0 }
    };
  }

  // 1. Clasificar referencias existentes por rango de columnas (clave).
  const usedNames = new Set(refs.map(ref => ref.name));
  const refNotes = [];
  const toCreate = [];
  const keyInfo = new Map();        // clave -> { startTitle, endTitle }
  const refKeyByName = new Map();   // nombre de referencia -> clave | null
  const refByMasterKey = new Map(); // "MASTER|clave" -> nombre existente o planificado

  familyRefs.forEach(ref => {
    const source = context.family.get(String(ref.sourceSheetId));
    const start = source.byId.get(String(ref.startColumnId));
    const end = source.byId.get(String(ref.endColumnId));

    if (!start || !end) {
      refKeyByName.set(ref.name, null);
      refNotes.push(
        `{${ref.name}}: columnas ${ref.startColumnId}-${ref.endColumnId} ` +
        `no existen en la hoja ${source.sheetId}.`
      );
      return;
    }

    const limitedToRows = Boolean(ref.startRowId || ref.endRowId);

    if (limitedToRows) {
      refNotes.push(
        `{${ref.name}}: estaba limitada a filas; las nuevas abarcan la columna completa.`
      );
    }

    const key = migCanonical_(start.title) + '|' + migCanonical_(end.title);
    refKeyByName.set(ref.name, key);

    if (!keyInfo.has(key)) {
      keyInfo.set(key, { startTitle: start.title, endTitle: end.title });
    }

    if (source.isMaster && !limitedToRows) {
      const masterKey = source.key + '|' + key;
      if (!refByMasterKey.has(masterKey)) {
        refByMasterKey.set(masterKey, ref.name);
      }
    }
  });

  const resolver = {
    keys: refKeyByName,
    masters: context.masters,
    refName: (master, key) => {
      const masterKey = master.key + '|' + key;

      if (refByMasterKey.has(masterKey)) {
        return refByMasterKey.get(masterKey);
      }

      const info = keyInfo.get(key);
      const newStart = master.byTitle.get(migCanonical_(info.startTitle));
      const newEnd = master.byTitle.get(migCanonical_(info.endTitle));

      if (!newStart || !newEnd) {
        throw new Error(
          `Falta la columna "${info.startTitle}"` +
          (info.endTitle !== info.startTitle ? ` o "${info.endTitle}"` : '') +
          ` en el maestro ${master.key}.`
        );
      }

      const titles = info.startTitle === info.endTitle
        ? [info.startTitle]
        : [info.startTitle, info.endTitle];

      const name = migUniqueName_(migReferenceName_(master.prefix, titles), usedNames);
      usedNames.add(name);

      toCreate.push({
        name,
        sourceSheetId: master.sheetId,
        startColumnId: newStart.id,
        endColumnId: newEnd.id
      });

      refByMasterKey.set(masterKey, name);
      return name;
    }
  };

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

  const changes = [];

  columns.forEach(column => {
    if (column.formula && migContainsFamily_(column.formula, resolver)) {
      changes.push(Object.assign(
        { kind: 'columna', columnId: column.id, rowId: '', rowNumber: '' },
        migRewriteFormula_(column.formula, resolver)
      ));
    }
  });

  migReadRows_(sheetId).forEach(row => {
    (row.cells || []).forEach(cell => {
      if (
        !cell.formula ||
        columnFormulaIds.has(String(cell.columnId)) ||
        !migContainsFamily_(cell.formula, resolver)
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
        migRewriteFormula_(cell.formula, resolver)
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
  const count = status => changes.filter(item => item.status === status).length;
  const now = new Date();
  const rows = [];

  rows.push([
    now, mode, sheetId, sheetName, 'resumen', '', '', '',
    apply ? 'APLICADO' : 'SIMULADO',
    `Fórmulas: ${changes.length}. Reescritas: ${count('REESCRITA')}. ` +
    `Sin cambios: ${count('SIN_CAMBIOS')}. A revisar: ${count('REVISAR')}. ` +
    `Errores: ${count('ERROR')}. Referencias nuevas: ${toCreate.length}. ` +
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
      rewritten: count('REESCRITA'),
      unchanged: count('SIN_CAMBIOS'),
      review: count('REVISAR'),
      errors: count('ERROR'),
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
 *
 * Idea: toda referencia a un maestro (antiguo o actual) se sustituye por
 * un marcador canónico {@clave} que identifica el rango de columnas.
 * Una cascada existente IFERROR(a, IFERROR(b, c)) cuyas variantes son la
 * misma llamada canónica se "colapsa" a esa llamada. Después la llamada
 * canónica se "expande" a una variante por maestro actual.
 * ====================================================================== */

const MIG_UNSUPPORTED_FUNCTIONS = new Set(['AVG', 'MIN', 'COLLECT', 'DISTINCT']);


/**
 * Devuelve { oldFormula, newFormula, status, note }.
 * status: REESCRITA | SIN_CAMBIOS | REVISAR
 */
function migRewriteFormula_(formula, resolver) {
  try {
    const rewritten = migRewriteExpr_(formula, resolver);

    if (rewritten === formula) {
      return { oldFormula: formula, newFormula: formula, status: 'SIN_CAMBIOS', note: 'Ya estaba migrada.' };
    }

    return { oldFormula: formula, newFormula: rewritten, status: 'REESCRITA', note: '' };

  } catch (error) {
    return { oldFormula: formula, newFormula: '', status: 'REVISAR', note: migClean_(error.message) };
  }
}


function migRewriteExpr_(expr, resolver) {
  let out = '';
  let i = 0;

  while (i < expr.length) {
    const ch = expr[i];

    if (ch === '"') {
      const end = migFindStringEnd_(expr, i);
      out += expr.slice(i, end + 1);
      i = end + 1;
      continue;
    }

    if (ch === '[') {
      const end = expr.indexOf(']', i);
      if (end < 0) throw new Error('Fórmula mal formada: falta ]');
      out += expr.slice(i, end + 1);
      i = end + 1;
      continue;
    }

    if (ch === '{') {
      const end = expr.indexOf('}', i);
      if (end < 0) throw new Error('Fórmula mal formada: falta }');
      const name = expr.slice(i + 1, end);

      if (resolver.keys.has(name)) {
        throw new Error(
          `La referencia {${name}} se usa fuera de una función reconocida ` +
          '(INDEX, VLOOKUP, MATCH, COUNTIF, SUMIF, MAX, JOIN/COLLECT).'
        );
      }

      out += expr.slice(i, end + 1);
      i = end + 1;
      continue;
    }

    // Grupo entre paréntesis sin función delante: posible suma de variantes.
    if (ch === '(') {
      const close = migFindMatchingParen_(expr, i);
      const group = expr.slice(i, close + 1);

      if (migContainsFamily_(group, resolver)) {
        const canonical = migCollapseSum_(group, resolver);
        out += canonical
          ? migExpand_(canonical, resolver)
          : '(' + migRewriteExpr_(group.slice(1, -1), resolver) + ')';
      } else {
        out += group;
      }

      i = close + 1;
      continue;
    }

    if (/[A-Za-z_]/.test(ch)) {
      let j = i;
      while (j < expr.length && /[A-Za-z0-9_.]/.test(expr[j])) j++;

      const ident = expr.slice(i, j);
      let k = j;
      while (k < expr.length && expr[k] === ' ') k++;

      if (expr[k] !== '(') {
        out += ident;
        i = j;
        continue;
      }

      const close = migFindMatchingParen_(expr, k);
      const args = expr.slice(k + 1, close);
      const callText = ident + '(' + args + ')';
      const name = ident.toUpperCase();

      if (!migContainsFamily_(callText, resolver)) {
        out += callText;
        i = close + 1;
        continue;
      }

      if (name === 'IFERROR') {
        const canonical = migCollapseLookup_(callText, resolver);
        out += canonical
          ? migExpand_(canonical, resolver)
          : ident + '(' + migRewriteExpr_(args, resolver) + ')';

      } else if (MIG_LOOKUP_FUNCTIONS.has(name)) {
        out += migExpand_(migCanon_(callText, resolver), resolver);

      } else if (MIG_SUM_FUNCTIONS.has(name) || (name === 'JOIN' && migIsJoinCollect_(args))) {
        out += migExpand_(migCanon_(callText, resolver), resolver);

      } else if (MIG_MAX_FUNCTIONS.has(name)) {
        const canonical = migCollapseMax_(callText, resolver) || migCanon_(callText, resolver);
        out += migExpand_(canonical, resolver);

      } else if (MIG_UNSUPPORTED_FUNCTIONS.has(name)) {
        throw new Error(
          `${name}() sobre un maestro no se puede repartir automáticamente entre varios maestros.`
        );

      } else {
        // IF, AND, OR, NOT, ISERROR, JOIN sin COLLECT, etc.: entrar en argumentos.
        out += ident + '(' + migRewriteExpr_(args, resolver) + ')';
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
 * Sustituye cada referencia de la familia por su marcador {@clave}.
 */
function migCanon_(text, resolver) {
  return text.replace(/\{([^}]*)\}/g, (match, name) => {
    if (!resolver.keys.has(name)) return match;
    const key = resolver.keys.get(name);
    if (!key) {
      throw new Error(`La referencia {${name}} apunta a columnas que no se pueden identificar.`);
    }
    return '{@' + key + '}';
  });
}


/**
 * Genera la fórmula final a partir de una llamada canónica.
 */
function migExpand_(canonical, resolver) {
  const call = migParseCall_(canonical);
  const name = call ? call.name.toUpperCase() : '';

  const variants = resolver.masters.map(master =>
    canonical.replace(/\{@([^}]*)\}/g, (match, key) => '{' + resolver.refName(master, key) + '}')
  );

  if (MIG_LOOKUP_FUNCTIONS.has(name)) {
    return migCascade_(variants);
  }

  if (MIG_MAX_FUNCTIONS.has(name)) {
    return 'MAX(' + variants.join(', ') + ')';
  }

  return '(' + variants.join(' + ') + ')';
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


/**
 * Si el texto es una búsqueda (INDEX/VLOOKUP/MATCH) con referencias de la
 * familia, o una cascada IFERROR de variantes de la misma búsqueda,
 * devuelve la llamada canónica. Si no, null.
 */
function migCollapseLookup_(text, resolver) {
  const call = migParseCall_(text);
  if (!call) return null;

  const name = call.name.toUpperCase();

  if (name === 'IFERROR') {
    const args = migSplitTopLevel_(call.args, ',');
    if (args.length !== 2) return null;

    const a = migCollapseLookup_(args[0], resolver);
    const b = migCollapseLookup_(args[1], resolver);
    return a && b && a === b ? a : null;
  }

  if (MIG_LOOKUP_FUNCTIONS.has(name) && migContainsFamily_(text, resolver)) {
    return migCanon_(text.trim(), resolver);
  }

  return null;
}


/**
 * "(A + B + C)" donde todas son la misma llamada de agregación sobre
 * distintos maestros -> llamada canónica. Si no, null.
 */
function migCollapseSum_(text, resolver) {
  let inner = text.trim();

  if (inner.startsWith('(') && migFindMatchingParen_(inner, 0) === inner.length - 1) {
    inner = inner.slice(1, -1);
  }

  const parts = migSplitTopLevel_(inner, '+');
  if (parts.length < 2) return null;

  const canonicals = parts.map(part => {
    const call = migParseCall_(part);
    if (!call) return null;

    const name = call.name.toUpperCase();
    const isSum = MIG_SUM_FUNCTIONS.has(name) || (name === 'JOIN' && migIsJoinCollect_(call.args));

    return isSum && migContainsFamily_(part, resolver) ? migCanon_(part.trim(), resolver) : null;
  });

  if (canonicals.some(item => !item)) return null;
  return canonicals.every(item => item === canonicals[0]) ? canonicals[0] : null;
}


/**
 * MAX(A, B, C) donde todas son la misma llamada MAX sobre distintos
 * maestros -> llamada canónica. Si no, null.
 */
function migCollapseMax_(text, resolver) {
  const call = migParseCall_(text);
  if (!call || call.name.toUpperCase() !== 'MAX') return null;

  const args = migSplitTopLevel_(call.args, ',');
  if (args.length < 2) return null;

  const canonicals = args.map(arg => {
    const inner = migParseCall_(arg);
    if (!inner || !MIG_MAX_FUNCTIONS.has(inner.name.toUpperCase())) return null;
    return migContainsFamily_(arg, resolver) ? migCanon_(arg.trim(), resolver) : null;
  });

  if (canonicals.some(item => !item)) return null;
  return canonicals.every(item => item === canonicals[0]) ? canonicals[0] : null;
}


function migIsJoinCollect_(args) {
  return /^\s*COLLECT\s*\(/i.test(args);
}


function migContainsFamily_(text, resolver) {
  const regex = /\{([^}]*)\}/g;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (resolver.keys.has(match[1])) return true;
  }

  return false;
}


/**
 * Si el texto (recortado) es exactamente una llamada NOMBRE(args),
 * devuelve { name, args }. Si no, null.
 */
function migParseCall_(text) {
  const trimmed = text.trim();
  const match = /^([A-Za-z_][A-Za-z0-9_.]*)\s*\(/.exec(trimmed);
  if (!match) return null;

  const open = match[0].length - 1;
  let close;

  try {
    close = migFindMatchingParen_(trimmed, open);
  } catch (error) {
    return null;
  }

  if (close !== trimmed.length - 1) return null;

  return { name: match[1], args: trimmed.slice(open + 1, close) };
}


/**
 * Divide por un separador de un solo carácter en el nivel superior,
 * respetando cadenas, paréntesis, llaves y corchetes.
 */
function migSplitTopLevel_(text, separator) {
  const parts = [];
  let depth = 0;
  let current = '';
  let i = 0;

  while (i < text.length) {
    const ch = text[i];

    if (ch === '"') {
      const end = migFindStringEnd_(text, i);
      current += text.slice(i, end + 1);
      i = end + 1;
      continue;
    }

    if (ch === '{' || ch === '[') {
      const end = text.indexOf(ch === '{' ? '}' : ']', i);
      const stop = end < 0 ? text.length - 1 : end;
      current += text.slice(i, stop + 1);
      i = stop + 1;
      continue;
    }

    if (ch === '(') depth++;
    if (ch === ')') depth--;

    if (ch === separator && depth === 0) {
      parts.push(current);
      current = '';
    } else {
      current += ch;
    }

    i++;
  }

  parts.push(current);

  return parts.some(part => part.trim() === '') ? [] : parts;
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
      if (depth === 0) return i;
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
    referencesToMasters: refs.filter(
      ref => MIG_CFG.MASTERS.some(master => master.sheetId === String(ref.sourceSheetId))
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
    return { status: 'SIN_REFERENCIAS', message: 'No referencia a ningún maestro.' };
  }

  const counts = result.counts;
  const status = result.mode === 'APPLY'
    ? (counts.errors ? 'APLICADA_CON_ERRORES' : 'APLICADA')
    : 'PREVISUALIZADA';

  return {
    status,
    rewritten: counts.rewritten,
    unchanged: counts.unchanged,
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
