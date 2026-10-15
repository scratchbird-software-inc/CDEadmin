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
export const QueryToolFrame = styled(Box)({
  width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
  flex: 1, minHeight: 0, minWidth: 0, overflow: 'hidden',
});

export const QueryToolToolbar = styled(Box)(({theme}) => ({
  padding: '2px 4px', display: 'flex', alignItems: 'center', gap: '4px',
  flexShrink: 0, flexWrap: 'wrap', backgroundColor: theme.otherVars.editorToolbarBg,
  ...theme.mixins.panelBorder.bottom,
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
