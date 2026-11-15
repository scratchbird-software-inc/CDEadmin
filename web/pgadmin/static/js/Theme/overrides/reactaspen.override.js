/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////


export default function reactAspenOverride(theme) {
  const reducedMotionLoader =
    'html[data-cdeadmin-motion="reduced"] '
    + '.file-entry button.directory-toggle.loading';
  return {
    '.drag-tree-node': {
      position: 'absolute',
      top: '-100px',
      left: 0,
      zIndex: 99999,
      color: theme.otherVars.tree.textFg,
      background: theme.otherVars.tree.inputBg,
      padding: '0.25rem 0.75rem',
      maxWidth: '30%',
      overflow: 'hidden',
      whiteSpace: 'nowrap',
      textOverflow: 'ellipsis',
    },

    '.file-tree': {
      color: theme.otherVars.tree.textFg + ' !important',
      backgroundColor: theme.otherVars.tree.inputBg + ' !important',
      fontFamily: theme.typography.fontFamily + ' !important',
      fontSize: '0.815rem' + ' !important',
      display: 'inline-block',
      position: 'relative',
      width: '100%',
      '&, & *': {
        boxSizing: 'border-box',
      },
    },

    '.browser-tree': {
      height: '100%',
    },

    '@keyframes cde-tree-spin': {
      to: {transform: 'rotate(360deg)'},
    },

    [reducedMotionLoader]: {
      animation: 'none',
      backgroundColor: theme.palette.primary.main,
      borderColor: theme.palette.primary.main,
      opacity: 0.7,
    },

    '@media (forced-colors: active)': {
      '.file-entry button.directory-toggle': {
        borderColor: 'CanvasText',
        color: 'CanvasText',
        forcedColorAdjust: 'auto',
      },
    },

    '.file-tree>': {
      'div:not(.sr-branched-sticky-ancestors)': {
        position: 'absolute' + ' !important',
        height: '100%' + ' !important',
        top: '0px' + ' !important',

        '>div': {
          scrollbarGutter: 'auto',
          overflow: 'overlay' + ' !important',
        },
      },
    },

    '.file-entry': {
      font: 'inherit',
      textAlign: 'left',
      display: 'flex',
      alignItems: 'center',
      whiteSpace: 'nowrap',
      padding: '0 4px 0 4px',
      height: '28px',
      minHeight: '28px',
      border: 'none',
      boxShadow: 'none',
      cursor: 'default',

      'span.tree-branch': {
        alignSelf: 'stretch',
        display: 'inline-flex',
        flexShrink: 0,
        pointerEvents: 'none',
      },

      'span.tree-branch-segment': {
        alignSelf: 'stretch',
        display: 'inline-block',
        flexShrink: 0,
        position: 'relative',
      },

      'span.directory-toggle-slot': {
        alignItems: 'center',
        alignSelf: 'stretch',
        display: 'inline-flex',
        flexShrink: 0,
        justifyContent: 'center',
        position: 'relative',

        'svg.directory-toggle-stem': {
          inset: 0,
          overflow: 'visible',
          pointerEvents: 'none',
          position: 'absolute',
        },
      },

      'button.directory-toggle': {
        appearance: 'none',
        backgroundColor: 'var(--sr-drawer-bg, ' + theme.otherVars.tree.inputBg + ')',
        border: '2px solid var(--sr-tree-guide, ' + (theme.palette.grey?.[600] || theme.otherVars.tree.iconFg) + ')',
        borderRadius: '50%',
        color: 'var(--sr-fg, ' + theme.otherVars.tree.textFg + ')',
        cursor: 'pointer',
        flex: '0 0 16px',
        height: '16px',
        margin: 0,
        padding: 0,
        position: 'relative',
        transition: 'border-color 120ms ease, background-color 120ms ease, color 120ms ease',
        width: '16px',
        zIndex: 1,

        '&:hover': {
          borderColor: 'var(--sr-accent, ' + theme.palette.primary.main + ')',
          color: 'var(--sr-accent, ' + theme.palette.primary.main + ')',
        },

        '&:before': {
          backgroundColor: 'currentColor',
          borderRadius: '1px',
          content: '""',
          height: '2px',
          left: 'calc(50% - 4px)',
          position: 'absolute',
          top: 'calc(50% - 1px)',
          width: '8px',
        },

        '&:not(.open):not(.loading):after': {
          backgroundColor: 'currentColor',
          borderRadius: '1px',
          content: '""',
          height: '8px',
          left: 'calc(50% - 1px)',
          position: 'absolute',
          top: 'calc(50% - 4px)',
          width: '2px',
        },

        '&.open:after': {
          display: 'none',
        },

        '&.loading': {
          borderColor: 'transparent',
          borderRadius: '50%',
          borderTopColor: theme.palette.primary.main,
          animation: 'cde-tree-spin var(--cde-motion-slow, 300ms) linear infinite',
          '&:before, &:after': {
            display: 'none',
          },
        },

        '&:focus-visible': {
          outline: 'var(--cde-focus-width, 2px) solid '
            + 'var(--cde-color-focus, ' + theme.palette.primary.main + ')',
          outlineOffset: 'var(--cde-focus-offset, 1px)',
        },
      },

      'span.tree-node-terminal.leaf': {
        display: 'inline-block',
        flex: '0 0 4px',
        height: '1px',
        margin: 0,
        width: '4px',
      },

      'input.tree-node-check': {
        accentColor: theme.palette.primary.main,
        cursor: 'pointer',
        flex: '0 0 auto',
        height: 'calc(var(--cde-tree-expander-size, 16px) - 2px)',
        margin: '0 4px 0 1px',
        width: 'calc(var(--cde-tree-expander-size, 16px) - 2px)',
      },

      '&.disabled': {
        cursor: 'not-allowed',
        opacity: 0.58,
      },

      '&.big': {
        fontFamily: 'monospace',
      },

      '&:hover, &.pseudo-active': {
        color: theme.otherVars.tree.textHoverFg + ' !important',
        backgroundColor: theme.otherVars.tree.bgHover + ' !important',
        'span.file-label': {
          'span.file-name': {
            color: theme.otherVars.tree.textHoverFg,
          },
          'span.children-count': {
            color: theme.otherVars.tree.textHoverFg
          },
        },
      },

      '&.active, &.prompt': {
        color: theme.otherVars.tree.textHoverFg + ' !important',
        backgroundColor: theme.otherVars.tree.bgSelected + ' !important',
        border: 'none !important',
        boxShadow: 'none !important',
        outline: 'none',
        'span.file-label': {
          'span.file-name': {
            color: theme.otherVars.textHoverFg,
          },
        },
      },

      'span.file-label': {
        display: 'flex',
        gap: '2px',
        alignItems: 'center',
        padding: '0 2px 0 2px',
        border: '1px solid transparent',
        height: 'auto',
        whiteSpace: 'normal',
        cursor: 'pointer !important',
        marginLeft: '2px',
        '&:hover, &.pseudo-active': {
          color: theme.otherVars.tree.fgHover,
        },
      },

      'span.file-name': {
        font: 'inherit',
        flexGrow: 1,
        userSelect: 'none',
        cursor: 'pointer !important',
        whiteSpace: 'nowrap',
        '&:hover, &.pseudo-active': {
          color: theme.otherVars.tree.fgHover,
        },
      },

      'span.children-count': {
        '&:hover, &.pseudo-active': {
          color: theme.otherVars.tree.fgHover,
        },
      },

      'div.file-tag': {
        color: 'var(--tag-color)',
        border: '1px solid color-mix(in srgb, var(--tag-color) 90%, #fff)',
        padding: '0px 4px',
        borderRadius: theme.shape.borderRadius,
        backgroundColor: 'color-mix(in srgb, color-mix(in srgb, var(--tag-color) 10%, #fff) 50%, transparent);',
        lineHeight: 1.2,
        whiteSpace: 'nowrap'
      },

      i: {
        display: 'inline-block',
        font: 'normal normal normal 18px/1 "Font Awesome 5 Free"',
        fontSize: 'var(--cde-icon-scale, 18px)',
        textAlign: 'center',
        height: '21px !important',
        width: '20px !important',
        flexShrink: 0,

        '&:before': {
          height: 'inherit',
          width: 'inherit',
          display: 'inline-block',
        },

      },

    },
  };
}
