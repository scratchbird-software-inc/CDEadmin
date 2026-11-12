/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {SecretField} from '../primitives/Field';
import {Dialog} from '../overlays/Dialog';
import {Banner} from '../feedback/Indicators';
import {Icon} from '../icons';
import {ScratchFilterTable} from '../data/beautiful/ScratchFilterTable';
import {ScratchPreferencesDialog} from './ScratchPreferencesDialog';

/**
 * System Icon (index 0) Session / Logout Dialog:
 * Offers Lock Screen, Logout, and Cancel.
 */
export function ProjectSessionLogoutDialog({
  open,
  onClose,
  onLockScreen,
  onLogout,
  username = '',
}) {
  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      title={gettext('Session')}
      size="small"
      actions={
        <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end', width: '100%'}}>
          <Button intent="neutral" onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          <Button
            intent="primary"
            data-cdeadmin-qa-key="session-lock-screen"
            onClick={() => {
              onClose?.();
              onLockScreen?.();
            }}
          >
            {gettext('Lock Screen')}
          </Button>
          <Button
            intent="danger"
            data-cdeadmin-qa-key="session-logout"
            onClick={() => {
              onClose?.();
              onLogout?.();
            }}
          >
            {gettext('Logout')}
          </Button>
        </Box>
      }
    >
      <Stack spacing={1.5}>
        <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
          <Icon iconKey="tool.scratchrobin" decorative size="24px" />
          <Box>
            <Box sx={{fontWeight: 600}}>
              {username
                ? gettext('Signed in as %s', username)
                : gettext('Active ScratchRobin Session')}
            </Box>
            <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
              {gettext(
                'Lock Screen hides the entire workspace down to a single unlock dialog while keeping open applications intact.'
              )}
            </Box>
          </Box>
        </Box>
      </Stack>
    </Dialog>
  );
}

ProjectSessionLogoutDialog.propTypes = {
  open: PropTypes.bool,
  onClose: PropTypes.func,
  onLockScreen: PropTypes.func,
  onLogout: PropTypes.func,
  username: PropTypes.string,
};

/**
 * Full-hide Lock Screen:
 * Replaces all Main Form chrome and blanks floating windows so ONLY a single
 * centered Unlock Dialog is visible on screen until re-authenticated.
 */
export function ProjectLockScreen({
  username = '',
  onUnlock,
  onLogout,
  busy = false,
  error = '',
}) {
  const [password, setPassword] = useState('');

  const submit = () => {
    onUnlock?.(password);
  };

  return (
    <Box
      data-cdeadmin-qa-key="project-lock-screen"
      role="region"
      aria-label={gettext('Locked ScratchRobin Session')}
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: 2000,
        bgcolor: 'background.default',
        color: 'text.primary',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
      }}
    >
      <Dialog
        open
        title={gettext('Unlock ScratchRobin')}
        size="small"
        busy={busy}
        defaultAction={submit}
        actions={
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'space-between', width: '100%'}}>
            <Button
              intent="danger"
              disabled={busy}
              data-cdeadmin-qa-key="lock-screen-logout"
              onClick={onLogout}
            >
              {gettext('Logout')}
            </Button>
            <Button
              intent="primary"
              disabled={busy}
              data-cdeadmin-qa-key="lock-screen-unlock"
              onClick={submit}
            >
              {gettext('Unlock')}
            </Button>
          </Box>
        }
      >
        <Stack spacing={1.5}>
          {error && <Banner status="error">{error}</Banner>}
          <Box sx={{fontSize: '0.875rem', color: 'text.secondary'}}>
            {username
              ? gettext('Session locked for %s. Enter your password to resume work.', username)
              : gettext('Session is locked. Enter your password to resume work.')}
          </Box>
          <SecretField
            label={gettext('Password')}
            value={password}
            autoFocus
            disabled={busy}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Stack>
      </Dialog>
    </Box>
  );
}

ProjectLockScreen.propTypes = {
  username: PropTypes.string,
  onUnlock: PropTypes.func.isRequired,
  onLogout: PropTypes.func,
  busy: PropTypes.bool,
  error: PropTypes.string,
};

/**
 * Area 2 Bottom Gear & Unified Preferences Dialog:
 * Delegates directly to the logically merged 6-Domain `ScratchPreferencesDialog`.
 */
export function ProjectSettingsDialog(props) {
  return <ScratchPreferencesDialog {...props} />;
}

ProjectSettingsDialog.propTypes = ScratchPreferencesDialog.propTypes;

const FALLBACK_REFERENCES = Object.freeze({
  sql: {
    title: 'SQL Reference',
    entries: [
      {term: 'SELECT', syntax: 'SELECT projection FROM relation [WHERE predicate]', notes: 'Retrieves projected rows across relational and analytical engines.'},
      {term: 'CREATE TABLE', syntax: 'CREATE TABLE name (column type [constraints])', notes: 'Defines persistent table storage; engine type mappings follow neutral logical rules.'},
      {term: 'MERGE', syntax: 'MERGE INTO target USING source ON condition ...', notes: 'Supported natively on Firebird 5, PostgreSQL 15+, and SQL:2008 engines.'},
    ],
  },
  engines: {
    title: 'Database Engine Reference',
    entries: [
      {engine: 'Firebird 5', capabilities: 'Domains, generators, packages, triggers, PSQL routines, embedded & network wire protocols'},
      {engine: 'PostgreSQL', capabilities: 'Schemas, extensions, partitioned tables, logical replication, PL/pgSQL'},
      {engine: 'MariaDB / MySQL', capabilities: 'InnoDB storage, routines, events, triggers, system-versioned tables'},
      {engine: 'DuckDB & SQLite', capabilities: 'Embedded OLAP/OLTP catalogs, Parquet/Arrow scan, local designs.db store'},
    ],
  },
  glossary: {
    title: 'Glossary of Terms',
    entries: [
      {term: 'DDN (Diagram-Design-Notation)', definition: 'Textual canonical representation for ERD, Cube, BI, and Screen Mesh designs.'},
      {term: 't_actions', definition: 'Central action registry controlling icon, i18n text/hint, status, owning application, and client/server target.'},
      {term: 'Directed Save Point', definition: 'Immutable design version carrying Draft, In-progress, In-review, or Accepted status.'},
    ],
  },
});

/**
 * Help Menu Reference & About Dialog (`Help > SQL Reference`,
 * `Database Engine Reference`, `Glossary of Terms`, `Help`, `About`).
 */
export function ProjectHelpReferenceDialog({open, topic = '', onClose, fetchImpl}) {
  const [payload, setPayload] = useState(null);

  useEffect(() => {
    if (!open || !topic) return;
    if (topic === 'about' || topic === 'docs') {
      setPayload(null);
      return;
    }
    const fallback = FALLBACK_REFERENCES[topic] || FALLBACK_REFERENCES.sql;
    setPayload(fallback);
    const runFetch = fetchImpl || (typeof fetch === 'function' ? fetch : null);
    if (!runFetch) return;
    let active = true;
    Promise.resolve(runFetch(`/cdeadmin/api/shell/reference/${topic}`, {credentials: 'same-origin'}))
      .then((res) => (res?.ok ? res.json() : null))
      .then((data) => {
        if (active && data?.entries) setPayload(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [open, topic, fetchImpl]);

  const title =
    topic === 'about'
      ? gettext('About ScratchRobin')
      : topic === 'docs'
        ? gettext('ScratchRobin Help')
        : payload?.title || gettext('Reference');

  const rows = (payload?.entries || []).map((entry, idx) => ({
    id: entry.term || entry.engine || `ref-${idx}`,
    name: entry.term || entry.engine || '',
    syntax: entry.syntax || '',
    description: entry.notes || entry.capabilities || entry.definition || '',
  }));

  const columns = rows.some((r) => Boolean(r.syntax))
    ? [
      {key: 'name', label: gettext('Term'), chip: true},
      {key: 'syntax', label: gettext('Syntax'), mono: true},
      {key: 'description', label: gettext('Description')},
    ]
    : [
      {key: 'name', label: topic === 'engines' ? gettext('Engine') : gettext('Term'), chip: true},
      {key: 'description', label: topic === 'engines' ? gettext('Capabilities') : gettext('Definition')},
    ];

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      size="large"
      title={title}
      actions={<Button onClick={onClose}>{gettext('Close')}</Button>}
    >
      {topic === 'about' ? (
        <Stack spacing={1}>
          <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
            <Icon iconKey="tool.scratchrobin" decorative size="28px" />
            <Box sx={{fontWeight: 700, fontSize: '1rem'}}>ScratchRobin CDE Administrator</Box>
          </Box>
          <Box sx={{fontSize: '0.875rem', color: 'text.secondary'}}>
            {gettext(
              'Multi-engine database administration, DDN data modelling, dimensional cubes, BI questions/dashboards, and screen mesh design under the PostgreSQL Licence.'
            )}
          </Box>
        </Stack>
      ) : topic === 'docs' ? (
        <Stack spacing={1}>
          <Box sx={{fontSize: '0.875rem'}}>
            {gettext(
              'Use Area 2 (Side Menu) or Applications to launch Data Navigator, SQL Editor, ERD, Cube, BI, and Screen Mesh designers. Drag any tab off Area 3 for multi-monitor floating windows and drop it back onto Area 3 to re-dock.'
            )}
          </Box>
        </Stack>
      ) : (
        <ScratchFilterTable
          title={title}
          columns={columns}
          rows={rows}
          maxHeight={340}
        />
      )}
    </Dialog>
  );
}

ProjectHelpReferenceDialog.propTypes = {
  open: PropTypes.bool,
  topic: PropTypes.string,
  onClose: PropTypes.func,
  fetchImpl: PropTypes.func,
};
