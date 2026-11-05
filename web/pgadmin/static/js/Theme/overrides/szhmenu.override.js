/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

export default function szhMenuOverride(theme) {
  return {
    '& .szh-menu': {
      padding: '4px 0px',
      zIndex: 1081,
      backgroundColor: theme.palette.background.default,
      color: theme.palette.text.primary,
      border: `1px solid ${theme.otherVars.borderColor}`
    },
    '& .szh-menu__divider': {
      margin: 0,
      background: theme.otherVars.borderColor,
    },
    '& .szh-menu__item': {
      display: 'flex',
      padding: '3px 12px',
      // Menu text size from View > Appearance and Accessibility; menus grow
      // with it and are never shorter than the menu row height setting.
      fontSize: 'var(--cde-menu-font-size, 0.875rem)',
      minHeight: 'var(--cde-menu-row-height, 28px)',
      alignItems: 'center',
      '&:after': {
        right: '0.75rem',
      },
      '&.szh-menu__item--active, &.szh-menu__item--hover': {
        backgroundColor: theme.palette.primary.main,
        color: theme.palette.primary.contrastText,
      },
      '&.szh-menu__item--disabled':{
        color: theme.palette.text.muted,
      }
    }
  };
}
