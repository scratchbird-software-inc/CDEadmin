/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useMemo} from 'react';
import {Box, FormControlLabel, Radio} from '@mui/material';
import gettext from 'sources/gettext';
import usePreferences from '../../../../preferences/static/js/store';

const RAIL_CONTROL_HEIGHT = 30;

function resolveThemePreference(selected) {
  if(selected === 'system') {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?
      'dark' : 'light';
  }
  return selected === 'dark' ? 'dark' : 'light';
}

export function ActivityThemeToggle() {
  const prefStore = usePreferences();
  const selectedTheme = prefStore?.getPreferencesForModule('misc')?.theme ||
    window.theme || 'light';
  const isDark = useMemo(
    () => resolveThemePreference(selectedTheme) === 'dark',
    [selectedTheme, prefStore?.version]
  );

  const applyTheme = useCallback(async (next) => {
    const store = usePreferences.getState();
    const preference = store.getPreferences('misc', 'theme');
    if(!preference) return;
    await store.setPreferences([{
      category_id: preference.cid,
      id: preference.id,
      mid: preference.mid,
      name: preference.name,
      value: next,
    }]);
  }, []);

  const toggle = useCallback(() => {
    const store = usePreferences.getState();
    const selected = store.getPreferencesForModule('misc')?.theme ||
      window.theme || 'light';
    const currentlyDark = resolveThemePreference(selected) === 'dark';
    void applyTheme(currentlyDark ? 'light' : 'dark');
  }, [applyTheme]);

  return <Box
    data-cdeadmin-qa-key="activity-theme-dark"
    sx={{
      ml: 'auto',
      flexShrink: 0,
      alignSelf: 'center',
      display: 'inline-flex',
      alignItems: 'center',
      maxHeight: RAIL_CONTROL_HEIGHT,
      px: 0.75,
      color: isDark ? 'primary.main' : 'text.primary',
    }}
  >
    <FormControlLabel
      sx={{
        m: 0,
        gap: 0.25,
        '& .MuiFormControlLabel-label': {
          fontSize: '0.75rem',
          lineHeight: 1,
          color: isDark ? 'primary.main' : 'inherit',
        },
      }}
      control={<Radio
        size="small"
        color="primary"
        checked={isDark}
        inputProps={{'aria-label': gettext('Dark theme')}}
        onClick={(event) => {
          event.preventDefault();
          toggle();
        }}
        sx={{
          p: 0.25,
          color: 'primary.main',
          '&.Mui-checked': {color: 'primary.main'},
        }}
      />}
      label={gettext('Dark')}
    />
  </Box>;
}
