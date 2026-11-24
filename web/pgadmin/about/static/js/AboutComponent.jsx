/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import url_for from 'sources/url_for';
import {Box, Stack} from 'sources/cdeadmin_ui/primitives/Layout';
import {Icon} from 'sources/cdeadmin_ui/icons';
import {InputSQL} from '../../../static/js/components/FormComponents';
import getApiInstance from '../../../static/js/api_instance';
import {usePgAdmin} from '../../../static/js/PgAdminProvider';

const FAMILY_BRANDS = [
  {iconKey: 'brand.scratchbird', name: 'ScratchBird'},
  {iconKey: 'brand.scratchrobin', name: 'ScratchRobin'},
  {iconKey: 'brand.scratchweaver', name: 'ScratchWeaver'},
  {iconKey: 'brand.ddn', name: 'DDN'},
  {iconKey: 'brand.opensource', name: 'Open Source'},
];

function AboutFieldRow({label, value, mono = false, qaKey}) {
  if (!value) return null;
  return (
    <div
      data-cdeadmin-qa-key={qaKey}
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(170px, 220px) minmax(0, 1fr)',
        gap: 12,
        alignItems: 'baseline',
        padding: '4px 0',
        borderBottom: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.16))',
        fontSize: '0.82rem',
      }}
    >
      <span style={{fontWeight: 700, color: 'var(--sr-text-secondary, inherit)'}}>
        {label}
      </span>
      <span
        className={mono ? 'sr-bui-mono' : undefined}
        style={{wordBreak: 'break-word'}}
      >
        {value}
      </span>
    </div>
  );
}

AboutFieldRow.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.node,
  mono: PropTypes.bool,
  qaKey: PropTypes.string,
};

export default function AboutComponent() {
  const containerRef = useRef(null);
  const [aboutData, setAboutData] = useState({});
  const pgAdmin = usePgAdmin();

  useEffect(() => {
    const aboutUrl = url_for('about.index');
    const api = getApiInstance();

    api
      .get(aboutUrl)
      .then((res) => {
        setAboutData(res?.data?.data || {});
      })
      .catch((err) => {
        pgAdmin?.Browser?.notifier?.errorText?.(err);
      });
  }, [pgAdmin]);

  const releaseText = aboutData.release || aboutData.version || '';
  const buildDateText =
    aboutData.build_datetime || aboutData.build_timestamp_utc || '';

  return (
    <Box
      ref={containerRef}
      data-cdeadmin-qa-key="about-scratchrobin-view"
      sx={{
        p: 2,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
        overflow: 'auto',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          paddingBottom: 10,
          borderBottom: '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
        }}
      >
        <Icon iconKey="brand.scratchrobin" label="ScratchRobin" size="48px" />
        <div style={{minWidth: 0, flex: 1}}>
          <div style={{fontWeight: 700, fontSize: '1.15rem'}}>
            {aboutData.product_name || 'ScratchRobin'}
          </div>
          {releaseText && (
            <div
              data-cdeadmin-qa-key="about-release-badge"
              style={{
                fontSize: '0.8rem',
                fontWeight: 600,
                color: 'var(--sr-accent, #0284c7)',
              }}
            >
              {gettext('Release %s', releaseText)}
              {buildDateText ? ` · ${gettext('Built %s', buildDateText)}` : ''}
            </div>
          )}
          {aboutData.fork_summary && (
            <div
              style={{
                fontSize: '0.8rem',
                marginTop: 4,
                color: 'var(--sr-text-secondary, inherit)',
              }}
            >
              {aboutData.fork_summary}
            </div>
          )}
        </div>
      </div>

      <div>
        <AboutFieldRow
          label={gettext('Release')}
          value={releaseText}
          qaKey="about-row-release"
        />
        <AboutFieldRow
          label={gettext('Build Date / Time')}
          value={buildDateText}
          mono
          qaKey="about-row-build-datetime"
        />
        <AboutFieldRow
          label={gettext('Commit')}
          value={aboutData.commit_hash}
          mono
          qaKey="about-row-commit"
        />
        <AboutFieldRow
          label={gettext('Application Mode')}
          value={aboutData.app_mode}
        />
        <AboutFieldRow
          label={gettext('Project Status')}
          value={aboutData.fork_status}
        />
        <AboutFieldRow
          label={gettext('Upstream Base')}
          value={
            aboutData.upstream_name
              ? `${aboutData.upstream_name} ${aboutData.upstream_version || ''}`.trim()
              : ''
          }
        />
        <AboutFieldRow
          label={gettext('Electron Version')}
          value={aboutData.electron}
        />
        <AboutFieldRow
          label={gettext('Browser')}
          value={aboutData.browser_details}
        />
        <AboutFieldRow
          label={gettext('Python Version')}
          value={aboutData.python_version}
        />
        <AboutFieldRow
          label={gettext('Operating System')}
          value={aboutData.os_details}
        />
        <AboutFieldRow
          label={gettext('Current User')}
          value={aboutData.current_user}
        />
        <AboutFieldRow
          label={gettext('User Configuration Vault')}
          value={aboutData.user_config_db}
          mono
        />
        <AboutFieldRow
          label={gettext('ScratchRobin Configuration Database')}
          value={aboutData.config_db}
          mono
        />
        <AboutFieldRow
          label={gettext('Log File')}
          value={aboutData.log_file}
          mono
        />
      </div>

      {aboutData.settings && (
        <Box sx={{flex: 1, display: 'flex', flexDirection: 'column', minHeight: 140}}>
          <div style={{fontWeight: 700, fontSize: '0.82rem', marginBottom: 4}}>
            {gettext('ScratchRobin Server Configuration')}
          </div>
          <Box sx={{flex: 1, minHeight: 0}}>
            <InputSQL
              value={aboutData.settings}
              controlProps={{
                readonly: true,
                showCopyBtn: true,
              }}
              options={{
                lineNumbers: false,
                foldGutter: false,
              }}
            />
          </Box>
        </Box>
      )}

      <Stack
        direction="row"
        gap="standard"
        data-cdeadmin-qa-key="about-family-logos"
        style={{
          alignItems: 'center',
          flexWrap: 'wrap',
          paddingTop: 8,
          borderTop: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.2))',
        }}
      >
        {FAMILY_BRANDS.map((brand) => (
          <div
            key={brand.iconKey}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 8px',
              borderRadius: 6,
              background: 'var(--sr-surface-subtle, rgba(128,128,128,0.08))',
              fontSize: '0.75rem',
              fontWeight: 600,
            }}
          >
            <Icon iconKey={brand.iconKey} label={brand.name} size="20px" />
            <span>{brand.name}</span>
          </div>
        ))}
      </Stack>

      {aboutData.attribution && (
        <div style={{fontSize: '0.76rem', color: 'var(--sr-text-secondary, inherit)'}}>
          <div style={{fontWeight: 700, marginBottom: 2}}>
            {gettext('Attribution and Licence')}
          </div>
          <div>{aboutData.attribution}</div>
        </div>
      )}
    </Box>
  );
}
