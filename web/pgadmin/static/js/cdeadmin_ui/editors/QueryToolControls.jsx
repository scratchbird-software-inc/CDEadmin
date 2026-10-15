import {Box} from '@mui/material';
import {styled} from '@mui/material/styles';
import PropTypes from 'prop-types';
import {PgIconButton} from '../../components/Buttons';
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';
import StopRoundedIcon from '@mui/icons-material/StopRounded';
import ExplicitRoundedIcon from '@mui/icons-material/ExplicitRounded';
import AssessmentRoundedIcon from '@mui/icons-material/AssessmentRounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import {CommitIcon, RollbackIcon, ExecuteQueryIcon} from '../../components/ExternalIcon';

// PostgreSQL Query Tool primitives shared by every native execution adapter.
// These controls never choose SQL, issue transactions, or infer an outcome.
export const QueryToolFrame = styled(Box)(({theme}) => ({
  width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
  flex: 1, minHeight: 0, minWidth: 0, overflow: 'hidden',
  '--cde-query-control-height': 'max(var(--cde-control-height, 28px), var(--cde-target-size, 24px))',
  '--cde-query-tab-height': 'max(30px, var(--cde-tab-height, 30px), var(--cde-target-size, 24px))',
  '& .QueryTool-workspace .dock-bar': {
    height: 'var(--cde-query-tab-height)',
    minHeight: 'var(--cde-query-tab-height)',
    padding: 0,
    alignItems: 'stretch',
  },
  '& .QueryTool-workspace .dock-nav, & .QueryTool-workspace .dock-nav-wrap, & .QueryTool-workspace .dock-nav-list': {
    height: '100%', padding: 0, margin: 0,
  },
  '& .QueryTool-workspace .dock-tab': {
    display: 'flex', height: '100%', padding: 0, margin: 0,
    '& > div': {
      display: 'flex', alignItems: 'center', height: '100%',
      minHeight: 0, padding: '0 8px', whiteSpace: 'nowrap',
    },
    '&.dock-tab-active': {
      backgroundColor: theme.palette.primary.main,
      color: theme.palette.primary.contrastText,
      '& .dock-tab-close-btn, & .dock-tab-icon': {
        color: theme.palette.primary.contrastText,
      },
    },
  },
  '& .QueryTool-workspace .dock-ink-bar': {display: 'none'},
}));

// Size against the tool pane, including when it is docked or detached.
export const QueryToolHeader = styled(Box)(({theme}) => ({
  containerType: 'inline-size', flexShrink: 0,
  ...theme.mixins.panelBorder.bottom,
  '& > .QueryTool-headerRows': {
    display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)',
  },
  '& .QueryTool-headerRows > .MuiAlert-root': {gridColumn: '1 / -1'},
  '& .QueryTool-mainToolbar': {borderBottom: 0},
  '@container (min-width: 1440px)': {
    '& > .QueryTool-headerRows': {
      gridTemplateColumns: 'minmax(16rem, 1fr) max-content',
      alignItems: 'start',
    },
    '& .QueryTool-mainToolbar': {maxWidth: 'calc(100cqw - 16rem)'},
  },
}));

export const queryToolControlStyles = {
  boxSizing: 'border-box', minHeight: 'calc(var(--cde-query-control-height, 28px) + 4px)',
  '& .MuiButtonGroup-root': {flexShrink: 0},
  '& .MuiButton-root, & .MuiInputBase-root, & .MuiFormControlLabel-root': {
    boxSizing: 'border-box', height: 'var(--cde-query-control-height, 28px)',
    minHeight: 'var(--cde-query-control-height, 28px)',
  },
  '& .MuiInputBase-input': {paddingTop: '3px', paddingBottom: '3px'},
  '& .MuiCheckbox-root': {padding: '2px'},
  '& .MuiFormControlLabel-label': {whiteSpace: 'nowrap'},
};

export const QueryToolToolbar = styled(Box)(({theme}) => ({
  padding: '2px 4px', display: 'flex', alignItems: 'center', gap: '4px',
  flexShrink: 0, flexWrap: 'wrap', backgroundColor: theme.otherVars.editorToolbarBg,
  ...theme.mixins.panelBorder.bottom,
  ...queryToolControlStyles,
}));

const icons = {
  execute: ExecuteQueryIcon, script: PlayArrowRoundedIcon, cancel: StopRoundedIcon,
  explain: ExplicitRoundedIcon, analyze: AssessmentRoundedIcon,
  commit: CommitIcon, rollback: RollbackIcon, refresh: RefreshRoundedIcon,
  close: CloseRoundedIcon,
};
export function QueryToolAction({action, title, ...props}) {
  const Icon = icons[action] || ExecuteQueryIcon;
  return <PgIconButton aria-label={title} title={title} icon={<Icon />} {...props} />;
}
QueryToolAction.propTypes = {action: PropTypes.string.isRequired, title: PropTypes.string.isRequired};
