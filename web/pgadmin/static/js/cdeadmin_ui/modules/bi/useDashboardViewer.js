/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useReducer, useRef, useState} from 'react';
import {executionFrom} from './executionModel';
import {
  RUN_CONCURRENCY, cardLinks, cardsToRun, filterPayload, initialViewer, linkChoices, missingRequired,
  runBounded, runnableCards, viewerKey, viewerReducer,
} from './dashboardViewer';
import useQuestionInfos from './useQuestionInfos';

const PAGE_SIZE = 100;
const message = (error) => error?.message || String(error);

/**
 * Everything one open dashboard needs in the viewer: filter values and
 * cross-filter bookkeeping (reducer), running the visible tab's cards with
 * bounded concurrency through bi_dashboard_card_run, per-card refresh that
 * bypasses the result cache, the optional auto-refresh timer (which does not
 * bypass it), and the click handling that calls the server for cross-filters
 * and drill-throughs.
 *
 * `dashboard` is the stored document (snake_case, as bi_dashboard_get returns
 * in `definition`). `onDrill(target, context)` receives a resolved
 * drill-through for the host to navigate.
 */
export default function useDashboardViewer({client, dashboardId, dashboard, initial, onDrill}) {
  const [state, dispatch] = useReducer(viewerReducer, null, () => initialViewer(dashboard, initial));
  const [notice, setNotice] = useState('');
  const [choices, setChoices] = useState(null);
  const [refreshSeconds, setRefreshSeconds] = useState(dashboard.settings?.auto_refresh_seconds || 0);
  const latest = useRef(state);
  latest.current = state;
  const tokens = useRef(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const pins = useMemo(() => runnableCards(dashboard).map((card) => card.question), [dashboard]);
  const {infos} = useQuestionInfos(client, pins);
  const missing = missingRequired(dashboard, state.values);

  const runOne = useCallback(async (card, fresh) => {
    tokens.current += 1;
    const token = tokens.current;
    const snapshot = latest.current;
    dispatch({type: 'cardStart', id: card.id, token, key: viewerKey(snapshot)});
    try {
      const response = await client.runDashboardCard(dashboardId, card.id, {
        filters: filterPayload(snapshot.values), exclude: snapshot.exclusions,
        pageSize: PAGE_SIZE, bypassCache: fresh});
      if(alive.current) {
        dispatch({type: 'cardDone', id: card.id, token, execution: executionFrom(response), receivedAt: Date.now()});
      }
    } catch(error) {
      if(alive.current) dispatch({type: 'cardFail', id: card.id, token, error: message(error)});
    }
  }, [client, dashboardId]);

  // A batch stops starting cards once the filters it was started for have moved on.
  const runMany = useCallback((cards, fresh) => {
    const key = viewerKey(latest.current);
    return runBounded(cards, RUN_CONCURRENCY, (card) => runOne(card, fresh),
      () => !alive.current || viewerKey(latest.current) !== key);
  }, [runOne]);

  const key = viewerKey(state);
  const blocked = missing.length > 0;
  useEffect(() => {
    if(blocked) return;
    const todo = cardsToRun(dashboard, latest.current, latest.current.tabId);
    if(todo.length) runMany(todo, false);
  }, [key, state.tabId, blocked, dashboard, runMany]);

  useEffect(() => {
    if(!refreshSeconds || blocked) return undefined;
    const timer = setInterval(() => {
      if(typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      runMany(runnableCards(dashboard, latest.current.tabId), false);
    }, refreshSeconds * 1000);
    return () => clearInterval(timer);
  }, [refreshSeconds, blocked, dashboard, runMany]);

  const refreshCard = useCallback((card) => runOne(card, true), [runOne]);
  const refreshAll = useCallback(() => runMany(runnableCards(dashboard), true), [dashboard, runMany]);

  const perform = useCallback(async (choice, row) => {
    setNotice('');
    setChoices(null);
    const values = filterPayload(latest.current.values);
    try {
      if(choice.kind === 'cross') {
        const link = dashboard.cross_filters.find((item) => item.id === choice.id);
        const outcome = await client.crossFilter(dashboardId, link.id, row, values);
        if(alive.current) {
          dispatch({type: 'crossFilter', filters: outcome.filters, exclude: outcome.exclude, filterId: link.filter_id});
        }
        return;
      }
      const drill = dashboard.drill_throughs.find((item) => item.id === choice.id);
      const target = await client.drill(dashboardId, drill.id, row, values);
      if(alive.current) {
        onDrill?.(target, {label: drill.label, values: latest.current.values, tabId: latest.current.tabId});
      }
    } catch(error) {
      if(alive.current) setNotice(message(error));
    }
  }, [client, dashboard, dashboardId, onDrill]);

  /** A click on a mark or cell of a card: do the one thing it triggers, or ask which. */
  const activate = useCallback((card, row, column) => {
    const items = linkChoices(dashboard, cardLinks(dashboard, card.id, column), row);
    if(!items.length) return;
    if(items.length === 1) perform(items[0], row);
    else setChoices({card, row, items});
  }, [dashboard, perform]);

  return {
    state, dispatch, infos, notice, setNotice, choices, setChoices, perform, activate,
    refreshCard, refreshAll, refreshSeconds, setRefreshSeconds, missing,
    setValues: (values) => dispatch({type: 'setValues', values}),
    selectTab: (tabId) => dispatch({type: 'selectTab', tabId}),
    setFullscreen: (id) => dispatch({type: 'fullscreen', id}),
  };
}
