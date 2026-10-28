/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useRef, useState} from 'react';
import {infoKey, questionInfo} from './dashboardMapping';

const message = (error) => error?.message || String(error);

/**
 * The pinned question revisions a dashboard uses, loaded once each
 * (bi_question_revision) and summarised for mapping and display.
 *
 * With a `catalog` (useBICatalog) a builder question's source columns and a
 * semantic question's model fields are added as picker suggestions once the
 * catalog is ready. Without one only the revision itself is read, which is all
 * the viewer needs.
 */
export default function useQuestionInfos(client, pins, catalog) {
  const [definitions, setDefinitions] = useState({});
  const [extras, setExtras] = useState({});
  const [errors, setErrors] = useState({});
  const alive = useRef(true);
  const asked = useRef(new Set());
  const enriched = useRef(new Set());
  const pinKey = pins.filter((pin) => pin.question_id).map(infoKey).sort().join('|');

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    for(const pin of pins) {
      const key = infoKey(pin);
      if(!pin.question_id || asked.current.has(key)) continue;
      asked.current.add(key);
      client.revision(pin.question_id, pin.revision).then(
        (record) => { if(alive.current) setDefinitions((current) => ({...current, [key]: record.definition})); },
        (error) => { if(alive.current) setErrors((current) => ({...current, [key]: message(error)})); });
    }
    // `pins` is summarised by pinKey: a new array with the same pins must not refetch.
  }, [client, pinKey]);

  const ready = catalog?.status === 'ready';
  const loadColumns = catalog?.loadColumns;
  const loadModel = catalog?.loadModel;
  useEffect(() => {
    if(!ready) return;
    for(const [key, definition] of Object.entries(definitions)) {
      if(enriched.current.has(key)) continue;
      enriched.current.add(key);
      const query = definition?.query || {};
      const work = query.kind === 'builder' && query.builder?.source?.relation ?
        loadColumns(query.builder.source.relation).then((columns) => ({columns})) :
        query.kind === 'semantic' && definition.semantic_model?.id ?
          loadModel(definition.semantic_model.id).then((model) => ({model})) : null;
      work?.then((extra) => { if(alive.current) setExtras((current) => ({...current, [key]: extra})); },
        () => { /* suggestions are optional */ });
    }
  }, [ready, definitions, loadColumns, loadModel]);

  const infos = useMemo(() => Object.fromEntries(Object.entries(definitions).map(
    ([key, definition]) => [key, questionInfo(definition, extras[key])])), [definitions, extras]);
  return {infos, definitions, errors};
}
