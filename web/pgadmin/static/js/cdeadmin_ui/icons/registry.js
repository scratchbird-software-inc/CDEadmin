/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import AddCircleIcon from '../../../assets/cdeadmin/commands/add-circle.svg?svgr';
import ArrowAllDirectionIcon from '../../../assets/cdeadmin/commands/arrow-all-direction.svg?svgr';
import CalendarClockIcon from '../../../assets/cdeadmin/commands/calendar-clock.svg?svgr';
import CancelCircleIcon from '../../../assets/cdeadmin/commands/cancel-circle.svg?svgr';
import CodeIcon from '../../../assets/cdeadmin/commands/code.svg?svgr';
import CommandLineIcon from '../../../assets/cdeadmin/commands/command-line.svg?svgr';
import ConnectIcon from '../../../assets/cdeadmin/commands/connect.svg?svgr';
import CopyIcon from '../../../assets/cdeadmin/commands/copy01.svg?svgr';
import DatabaseAddIcon from '../../../assets/cdeadmin/commands/database-add.svg?svgr';
import DatabaseBackupIcon from '../../../assets/cdeadmin/commands/database-backup.svg?svgr';
import DatabaseRestoreIcon from '../../../assets/cdeadmin/commands/database-restore.svg?svgr';
import DeleteIcon from '../../../assets/cdeadmin/commands/delete02.svg?svgr';
import DownloadIcon from '../../../assets/cdeadmin/commands/download01.svg?svgr';
import EditIcon from '../../../assets/cdeadmin/commands/edit01.svg?svgr';
import EyeIcon from '../../../assets/cdeadmin/commands/eye.svg?svgr';
import FileAddIcon from '../../../assets/cdeadmin/commands/file-add.svg?svgr';
import FilterIcon from '../../../assets/cdeadmin/commands/filter.svg?svgr';
import GitCompareIcon from '../../../assets/cdeadmin/commands/git-compare.svg?svgr';
import HelpCircleIcon from '../../../assets/cdeadmin/commands/help-circle.svg?svgr';
import HistoryIcon from '../../../assets/cdeadmin/commands/history.svg?svgr';
import InformationCircleIcon from '../../../assets/cdeadmin/commands/information-circle.svg?svgr';
import LinkIcon from '../../../assets/cdeadmin/commands/link01.svg?svgr';
import LockIcon from '../../../assets/cdeadmin/commands/lock.svg?svgr';
import MenuCircleIcon from '../../../assets/cdeadmin/commands/menu-circle.svg?svgr';
import PlayCircleIcon from '../../../assets/cdeadmin/commands/play-circle.svg?svgr';
import PrinterIcon from '../../../assets/cdeadmin/commands/printer.svg?svgr';
import RefreshIcon from '../../../assets/cdeadmin/commands/refresh.svg?svgr';
import SaveIcon from '../../../assets/cdeadmin/commands/save.svg?svgr';
import SearchIcon from '../../../assets/cdeadmin/commands/search01.svg?svgr';
import SettingsIcon from '../../../assets/cdeadmin/commands/settings02.svg?svgr';
import ShieldUserIcon from '../../../assets/cdeadmin/commands/shield-user.svg?svgr';
import SortIcon from '../../../assets/cdeadmin/commands/sort-by-down01.svg?svgr';
import TransactionIcon from '../../../assets/cdeadmin/commands/transaction.svg?svgr';
import UnlinkIcon from '../../../assets/cdeadmin/commands/unlink01.svg?svgr';
import UploadIcon from '../../../assets/cdeadmin/commands/upload01.svg?svgr';
import ScratchRobinIcon from '../../../assets/cdeadmin/branding/scratchrobincde.svg?svgr';

function UndoIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M5 9.5H14.5C17.5376 9.5 20 11.9624 20 15C20 18.0376 17.5376 20.5 14.5 20.5H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8.5 5.5L4.5 9.5L8.5 13.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RedoIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M19 9.5H9.5C6.46243 9.5 4 11.9624 4 15C4 18.0376 6.46243 20.5 9.5 20.5H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15.5 5.5L19.5 9.5L15.5 13.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CutIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <line x1="20" y1="4" x2="8.12" y2="15.88" />
      <line x1="14.47" y1="14.48" x2="20" y2="20" />
      <line x1="8.12" y1="8.12" x2="12" y2="12" />
    </svg>
  );
}

function PasteIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" />
    </svg>
  );
}

function SelectPointerIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5 3l14 7.5-6.2 1.8L10 19 5 3z" />
      <path d="M12.8 12.3L18 17.5" />
    </svg>
  );
}

function SelectMarqueeIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="3 3" aria-hidden="true" {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function AlignIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="4" y1="4" x2="4" y2="20" />
      <rect x="8" y="6" width="12" height="4" rx="1" />
      <rect x="8" y="14" width="8" height="4" rx="1" />
    </svg>
  );
}

function LayersIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 12 12 17 22 12" />
      <polyline points="2 17 12 22 22 17" />
    </svg>
  );
}

function PaletteEntitiesIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <line x1="17.5" y1="14" x2="17.5" y2="21" />
      <line x1="14" y1="17.5" x2="21" y2="17.5" />
    </svg>
  );
}

function PaletteUdtIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4 7V4h16v3" />
      <line x1="12" y1="4" x2="12" y2="20" />
      <line x1="9" y1="20" x2="15" y2="20" />
    </svg>
  );
}

function EndpointSourceIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <ellipse cx="10" cy="6" rx="6" ry="2.5" />
      <path d="M4 6v10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V6" />
      <path d="M15 12h6m-2.5-2.5L21 12l-2.5 2.5" />
    </svg>
  );
}

function EndpointTargetIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 12h6m-2.5-2.5L9 12l-2.5 2.5" />
      <ellipse cx="15" cy="6" rx="5.5" ry="2.5" />
      <path d="M9.5 6v10c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V6" />
    </svg>
  );
}

function SendReviewIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function StatisticsBarChartIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 20h18" />
      <rect x="5" y="11" width="3.5" height="9" rx="0.8" />
      <rect x="10.25" y="6" width="3.5" height="14" rx="0.8" />
      <rect x="15.5" y="8.5" width="3.5" height="11.5" rx="0.8" />
    </svg>
  );
}

function DependenciesGraphIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M8.7 10.7L15.3 7.3" />
      <path d="M8.7 13.3L15.3 16.7" />
    </svg>
  );
}

function DependentsGraphIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="12" r="3" />
      <path d="M8.7 7.3L15.3 10.7" />
      <path d="M8.7 16.7L15.3 13.3" />
    </svg>
  );
}

function QueryPauseIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
  );
}

function FetchLimitsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="4" y1="6" x2="20" y2="6" />
      <circle cx="9" cy="6" r="2" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <circle cx="15" cy="12" r="2" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="11" cy="18" r="2" />
    </svg>
  );
}

function InspectorDrawerIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </svg>
  );
}

function ServerHostIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="18" height="7" rx="2" />
      <rect x="3" y="14" width="18" height="7" rx="2" />
      <circle cx="7" cy="6.5" r="1" fill="currentColor" />
      <circle cx="7" cy="17.5" r="1" fill="currentColor" />
      <line x1="11" y1="6.5" x2="17" y2="6.5" />
      <line x1="11" y1="17.5" x2="17" y2="17.5" />
    </svg>
  );
}

function EmbeddedHostIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <line x1="8" y1="20" x2="16" y2="20" />
      <line x1="12" y1="16" x2="12" y2="20" />
    </svg>
  );
}

function SectionTagIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <circle cx="7" cy="7" r="1.3" fill="currentColor" />
    </svg>
  );
}

function SectionColumnsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <line x1="15" y1="3" x2="15" y2="21" />
    </svg>
  );
}

function SectionConstraintsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  );
}

function SectionIndexesIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <polyline points="3 6 4.5 7.5 6.5 5" />
      <polyline points="3 12 4.5 13.5 6.5 11" />
      <polyline points="3 18 4.5 19.5 6.5 17" />
    </svg>
  );
}

function SectionCommentsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function SectionOperationsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  );
}

function NavigationSidebarIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <line x1="9" y1="4" x2="9" y2="20" />
      <line x1="5.5" y1="8.5" x2="7" y2="8.5" />
      <line x1="5.5" y1="12" x2="7" y2="12" />
    </svg>
  );
}

function ViewToolbarIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <line x1="3" y1="9.5" x2="21" y2="9.5" />
      <line x1="6.5" y1="6.8" x2="9.5" y2="6.8" />
      <line x1="12" y1="6.8" x2="15" y2="6.8" />
    </svg>
  );
}

function ViewStatusBarIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <line x1="3" y1="15.5" x2="21" y2="15.5" />
      <circle cx="6.5" cy="17.8" r="0.8" fill="currentColor" />
      <line x1="9.5" y1="17.8" x2="15.5" y2="17.8" />
    </svg>
  );
}

function ExternalWindowIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M14 4h6v6" />
      <path d="M10 14L20 4" />
      <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" />
    </svg>
  );
}

function CustomizeSlidersIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="4" y1="21" x2="4" y2="14" />
      <line x1="4" y1="10" x2="4" y2="3" />
      <line x1="12" y1="21" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12" y2="3" />
      <line x1="20" y1="21" x2="20" y2="16" />
      <line x1="20" y1="12" x2="20" y2="3" />
      <line x1="2" y1="14" x2="6" y2="14" />
      <line x1="10" y1="8" x2="14" y2="8" />
      <line x1="18" y1="16" x2="22" y2="16" />
    </svg>
  );
}

function FolderObjectIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
    </svg>
  );
}

function DrawerCloseIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <line x1="9" y1="4" x2="9" y2="20" />
      <path d="M16 9.5L13.5 12L16 14.5" />
    </svg>
  );
}

function SignOutIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

function UnlockOpenIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 7.6-1.7" />
    </svg>
  );
}

function MoveUpIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="6 11 12 5 18 11" />
    </svg>
  );
}

function MoveDownIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <polyline points="18 13 12 19 6 13" />
    </svg>
  );
}

function ColorPaletteIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 3a9 9 0 1 0 0 18h1.5a2.5 2.5 0 0 0 0-5H12a2 2 0 0 1 0-4h4.5A4.5 4.5 0 0 0 21 7.5C21 5 16.97 3 12 3z" />
      <circle cx="7.5" cy="10.5" r="1" fill="currentColor" />
      <circle cx="10.5" cy="7" r="1" fill="currentColor" />
      <circle cx="7.5" cy="14.5" r="1" fill="currentColor" />
    </svg>
  );
}

function FontSizeIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="4 7 4 4 16 4 16 7" />
      <line x1="10" y1="4" x2="10" y2="20" />
      <line x1="7" y1="20" x2="13" y2="20" />
      <line x1="15" y1="12" x2="21" y2="12" />
      <line x1="18" y1="12" x2="18" y2="20" />
    </svg>
  );
}

function StatusInProgressIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  );
}

function StatusInReviewIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <circle cx="11.5" cy="14.5" r="2.5" />
      <line x1="13.5" y1="16.5" x2="16" y2="19" />
    </svg>
  );
}

function AcceptVersionIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="9" />
      <polyline points="8.5 12.5 11 15 16 9.5" />
    </svg>
  );
}

function BranchDraftIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="8" r="2.5" />
      <line x1="6" y1="8.5" x2="6" y2="15.5" />
      <path d="M18 10.5c0 4.5-12 2-12 5" />
    </svg>
  );
}

function GitSyncIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="3" />
      <line x1="3" y1="12" x2="9" y2="12" />
      <line x1="15" y1="12" x2="21" y2="12" />
      <polyline points="17 8 21 12 17 16" />
      <polyline points="7 16 3 12 7 8" />
    </svg>
  );
}

function WhereUsedIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="11" cy="11" r="6" />
      <line x1="20" y1="20" x2="15.4" y2="15.4" />
      <circle cx="11" cy="11" r="2" />
    </svg>
  );
}

function RecomputeLayoutIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="7" height="6" rx="1.2" />
      <rect x="14" y="3" width="7" height="6" rx="1.2" />
      <rect x="8.5" y="15" width="7" height="6" rx="1.2" />
      <path d="M6.5 9v3h11V9" />
      <line x1="12" y1="12" x2="12" y2="15" />
    </svg>
  );
}

function SketchLookIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 19l7-7 3 3-7 7-3-3z" />
      <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z" />
      <path d="M2 2l7.5 7.5" />
    </svg>
  );
}

function PromoteWhiteboardIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="13" width="8" height="7" rx="1.5" strokeDasharray="2.5 2.5" />
      <rect x="13" y="4" width="8" height="7" rx="1.5" />
      <path d="M7 11V7h4" />
      <polyline points="9 5 11 7 9 9" />
    </svg>
  );
}

function LevelConceptualIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M9 18h6" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.8 10.6c.7.6 1.3 1.4 1.5 2.4h4.6c.2-1 .8-1.8 1.5-2.4A6 6 0 0 0 12 3z" />
    </svg>
  );
}

function LevelLogicalIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="7" height="7" rx="1.5" />
      <rect x="14" y="13" width="7" height="7" rx="1.5" />
      <path d="M10 7.5h4v9" />
    </svg>
  );
}

function LevelPhysicalIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
      <path d="M5 5.5v6.5c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V5.5" />
      <path d="M5 12v6.5c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V12" />
    </svg>
  );
}

function LevelDeploymentIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M6.5 17H18a4 4 0 0 0 .5-7.97A5.5 5.5 0 0 0 7.7 7.5 4.5 4.5 0 0 0 6.5 17z" />
      <line x1="12" y1="17" x2="12" y2="21" />
      <line x1="8" y1="21" x2="16" y2="21" />
    </svg>
  );
}

function PinNodeIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M9 4h6l-1 6 3 3v2H7v-2l3-3-1-6z" />
      <line x1="12" y1="15" x2="12" y2="21" />
    </svg>
  );
}

function NamingStandardsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      <polyline points="9 10 11 12 15 8" />
    </svg>
  );
}

function EngineConvertIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="17 2 21 6 17 10" />
      <path d="M3 11V9a3 3 0 0 1 3-3h15" />
      <polyline points="7 22 3 18 7 14" />
      <path d="M21 13v2a3 3 0 0 1-3 3H3" />
    </svg>
  );
}

function SystemDriftIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="22 12 18 12 15 20 9 4 6 12 2 12" />
    </svg>
  );
}

function EnvMatrixIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="15" x2="21" y2="15" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <line x1="15" y1="3" x2="15" y2="21" />
    </svg>
  );
}

function DimensionObjectIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
      <polyline points="4 7.5 12 12 20 7.5" />
      <line x1="12" y1="12" x2="12" y2="21" />
    </svg>
  );
}

function HierarchyObjectIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="9" y="3" width="6" height="4" rx="1" />
      <rect x="3" y="15" width="6" height="4" rx="1" />
      <rect x="15" y="15" width="6" height="4" rx="1" />
      <path d="M12 7v4m-6 4v-4h12v4" />
    </svg>
  );
}

function MeasureObjectIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M18 4H6l6 8-6 8h12" />
    </svg>
  );
}

function StarSchemaIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="3" />
      <circle cx="12" cy="4" r="1.8" />
      <circle cx="19.5" cy="9.5" r="1.8" />
      <circle cx="17" cy="18.5" r="1.8" />
      <circle cx="7" cy="18.5" r="1.8" />
      <circle cx="4.5" cy="9.5" r="1.8" />
      <line x1="12" y1="9" x2="12" y2="5.8" />
      <line x1="14.8" y1="11" x2="17.8" y2="10" />
      <line x1="13.8" y1="14.4" x2="15.8" y2="17" />
      <line x1="10.2" y1="14.4" x2="8.2" y2="17" />
      <line x1="9.2" y1="11" x2="6.2" y2="10" />
    </svg>
  );
}

function UsageMatrixIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <polyline points="12.5 15 14.5 17 18 13" />
    </svg>
  );
}

function AiDraftSparkleIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z" />
    </svg>
  );
}

function LatticeReducerIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polygon points="3 4 21 4 14 12.5 14 19 10 21 10 12.5 3 4" />
    </svg>
  );
}

function PerspectiveEyeIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function LocaleTranslationIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="3" y1="6" x2="13" y2="6" />
      <line x1="8" y1="3" x2="8" y2="6" />
      <path d="M5 6c0 4.5 3 8 7 9.5" />
      <path d="M11 6c-.5 3.5-3 7-7 9" />
      <path d="M13 20l4-9 4 9" />
      <line x1="14.5" y1="17" x2="19.5" y2="17" />
    </svg>
  );
}

function DashboardCardsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="8" height="9" rx="1.5" />
      <rect x="13" y="3" width="8" height="5" rx="1.5" />
      <rect x="13" y="10" width="8" height="11" rx="1.5" />
      <rect x="3" y="14" width="8" height="7" rx="1.5" />
    </svg>
  );
}

function AxisFormatIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="4 4 4 20 20 20" />
      <polyline points="8 15 12 10 15 13 19 7" />
    </svg>
  );
}

function AccessibleTableIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="14.5" x2="21" y2="14.5" />
      <line x1="10" y1="9" x2="10" y2="20" />
    </svg>
  );
}

function CollectorSnapshotIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4.9 19.1A10 10 0 1 1 19.1 19.1" />
      <line x1="12" y1="12" x2="16" y2="8" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
    </svg>
  );
}

function SubscriptionsAlertsIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function EmbedSwitchIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="8 7 3 12 8 17" />
      <polyline points="16 7 21 12 16 17" />
      <line x1="14" y1="4" x2="10" y2="20" />
    </svg>
  );
}

function KioskDeviceIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="2" y="4" width="20" height="13" rx="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
      <circle cx="18" cy="8" r="1" fill="currentColor" />
    </svg>
  );
}

function UiScreenFrameIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="8.5" x2="21" y2="8.5" />
      <circle cx="6" cy="6.3" r="0.7" fill="currentColor" />
      <circle cx="8.5" cy="6.3" r="0.7" fill="currentColor" />
    </svg>
  );
}

function UiGridControlIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="5" width="18" height="14" rx="1.8" />
      <line x1="3" y1="9.5" x2="21" y2="9.5" />
      <line x1="9" y1="5" x2="9" y2="19" />
      <line x1="15" y1="5" x2="15" y2="19" />
    </svg>
  );
}

function UiDropdownControlIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="7" width="18" height="10" rx="2" />
      <line x1="7" y1="12" x2="13" y2="12" />
      <polyline points="15.5 10.5 17.5 13 19.5 10.5" />
    </svg>
  );
}

function UiRadioControlIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="7" cy="8" r="3" />
      <circle cx="7" cy="8" r="1.2" fill="currentColor" />
      <line x1="13" y1="8" x2="20" y2="8" />
      <circle cx="7" cy="16" r="3" />
      <line x1="13" y1="16" x2="20" y2="16" />
    </svg>
  );
}

function UiTabsControlIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 9h18v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" />
      <path d="M3 9V6.5A1.5 1.5 0 0 1 4.5 5h4A1.5 1.5 0 0 1 10 6.5V9" />
      <path d="M10 9V6.5A1.5 1.5 0 0 1 11.5 5h4A1.5 1.5 0 0 1 17 6.5V9" />
    </svg>
  );
}

function UiRegionHotspotIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="4" y="5" width="16" height="14" rx="2" strokeDasharray="3 2.5" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

function UiDataBindingIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <ellipse cx="7.5" cy="7" rx="4.5" ry="2" />
      <path d="M3 7v6c0 1.1 2 2 4.5 2S12 14.1 12 13V7" />
      <rect x="14" y="12" width="7" height="7" rx="1.5" />
      <path d="M12 10h4.5v2" />
    </svg>
  );
}

function UiScreenNavigationIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="2.5" y="5" width="7.5" height="6" rx="1.2" />
      <rect x="14" y="13" width="7.5" height="6" rx="1.2" />
      <path d="M10 8h5v5" />
      <polyline points="12.5 11 15 13.5 17.5 11" />
    </svg>
  );
}

function ScreenshotUploadIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.5" />
      <polyline points="21 15 16 10 7 19" />
    </svg>
  );
}

function RedactRegionIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <line x1="6" y1="9" x2="18" y2="15" />
      <line x1="18" y1="9" x2="6" y2="15" />
    </svg>
  );
}

function TraceMeshIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="5" cy="5" r="2" />
      <circle cx="19" cy="5" r="2" />
      <circle cx="5" cy="19" r="2" />
      <circle cx="19" cy="19" r="2" />
      <line x1="7" y1="5" x2="17" y2="5" />
      <line x1="7" y1="19" x2="17" y2="19" />
      <line x1="5" y1="7" x2="5" y2="17" />
      <line x1="19" y1="7" x2="19" y2="17" />
      <line x1="6.5" y1="6.5" x2="17.5" y2="17.5" />
    </svg>
  );
}

function SqlBuilderIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <line x1="10" y1="6.5" x2="14" y2="6.5" />
      <path d="M5 15l3 3-3 3" />
      <line x1="10" y1="21" x2="19" y2="21" />
    </svg>
  );
}

function SavepointFlagIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5 21V4h13l-2.5 4.5L18 13H5" />
    </svg>
  );
}

function ExportCsvIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="16" y2="17" />
      <line x1="12" y1="11" x2="12" y2="19" />
    </svg>
  );
}

function ExportJsonIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M8 4H6a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2 2 2 0 0 1 2 2v4a2 2 0 0 0 2 2h2" />
      <path d="M16 4h2a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2 2 2 0 0 0-2 2v4a2 2 0 0 1-2 2h-2" />
    </svg>
  );
}

function ConnectAsUserIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 19c0-3 2.7-5 6-5s6 2 6 5" />
      <line x1="16" y1="11" x2="21" y2="11" />
      <polyline points="19 8.5 21.5 11 19 13.5" />
    </svg>
  );
}

function ManageRoutesIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="5" cy="6" r="2" />
      <circle cx="19" cy="6" r="2" />
      <circle cx="12" cy="19" r="2" />
      <path d="M7 6h10" />
      <path d="M6.5 7.5L11 17" />
      <path d="M17.5 7.5L13 17" />
    </svg>
  );
}

function BrowseDataGridIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="14.5" x2="21" y2="14.5" />
      <line x1="9" y1="4" x2="9" y2="20" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </svg>
  );
}

function EnginesToggleIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <ellipse cx="9" cy="6" rx="5.5" ry="2.2" />
      <path d="M3.5 6v8c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2V6" />
      <rect x="13" y="13" width="8" height="5" rx="2.5" />
      <circle cx="18.5" cy="15.5" r="1.2" fill="currentColor" />
    </svg>
  );
}

function TruncateTableIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="9" y1="12.5" x2="15" y2="17.5" />
      <line x1="15" y1="12.5" x2="9" y2="17.5" />
    </svg>
  );
}

function CountRowsHashIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <line x1="4" y1="9" x2="20" y2="9" />
      <line x1="4" y1="15" x2="20" y2="15" />
      <line x1="10" y1="3" x2="8" y2="21" />
      <line x1="16" y1="3" x2="14" y2="21" />
    </svg>
  );
}

function DockerContainerIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="4" y="9" width="3.5" height="3.5" rx="0.5" />
      <rect x="8.5" y="9" width="3.5" height="3.5" rx="0.5" />
      <rect x="13" y="9" width="3.5" height="3.5" rx="0.5" />
      <rect x="8.5" y="4.5" width="3.5" height="3.5" rx="0.5" />
      <path d="M2 13.5h16.5c1.5 0 2.5-.8 3.5-2 0 4.5-3 7.5-9.5 7.5S2 16.5 2 13.5z" />
    </svg>
  );
}

function ProfilerStopwatchIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="13" r="8" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="13" x2="15" y2="15" />
      <line x1="9" y1="2" x2="15" y2="2" />
      <line x1="12" y1="2" x2="12" y2="5" />
    </svg>
  );
}

function BinlogReplayIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <polyline points="3 3 3 8 8 8" />
      <polygon points="10.5 9 16 12 10.5 15 10.5 9" />
    </svg>
  );
}

export const ICON_CATEGORIES = Object.freeze({
  ACTION: 'action',
  ENGINE: 'engine',
  OBJECT: 'object',
  STATUS: 'status',
  TOOL: 'tool',
});

export const ENGINE_IDS = Object.freeze([
  'apache_ignite', 'cassandra', 'clickhouse', 'cockroachdb', 'dolt',
  'duckdb', 'firebird', 'foundationdb', 'immudb', 'influxdb', 'mariadb',
  'milvus', 'mongodb', 'mysql', 'neo4j', 'opensearch', 'postgresql',
  'redis', 'scratchbird', 'sqlite', 'tidb', 'tikv', 'vitess', 'xtdb',
  'yugabytedb',
]);

const OBJECT_CLASSES = Object.freeze({
  unknown: 'icon-object',
  server: 'icon-server',
  instance: 'icon-server',
  cluster: 'icon-server-group',
  database: 'icon-database',
  catalog: 'icon-database',
  schema: 'icon-schema',
  keyspace: 'icon-schema',
  table: 'icon-table',
  columnar_table: 'icon-table',
  wide_column_table: 'icon-table',
  view: 'icon-view',
  materialized_view: 'icon-mview',
  mview: 'icon-mview',
  column: 'icon-column',
  domain: 'icon-domain',
  type: 'icon-type',
  sequence: 'icon-sequence',
  function: 'icon-function',
  procedure: 'icon-procedure',
  package: 'icon-package',
  trigger: 'icon-trigger',
  index: 'icon-index',
  constraint: 'icon-check_constraint',
  role: 'icon-role',
  user: 'icon-role',
  grant: 'icon-security',
  privilege: 'icon-security',
  extension: 'icon-extension',
  plugin: 'icon-extension',
  partition: 'icon-partition',
  tablespace: 'icon-tablespace',
  filespace: 'icon-tablespace',
  replication: 'icon-publication',
  job: 'icon-pga_job',
  event: 'icon-event_trigger',
  collection: 'icon-coll-table',
  document: 'icon-file',
  validation_rule: 'icon-check_constraint',
  aggregation_pipeline: 'icon-query-tool',
  replica_set: 'icon-server-group',
  sharding: 'icon-partition',
  node: 'icon-server',
  relationship: 'icon-dependency',
  label: 'icon-collation',
  graph_projection: 'icon-erd',
  transaction: 'icon-commit',
  query_plan: 'icon-query-tool',
  cluster_member: 'icon-server',
  key: 'icon-key',
  ttl: 'icon-clock',
  stream: 'icon-query-tool',
  pubsub: 'icon-publication',
  consumer_group: 'icon-role',
  module: 'icon-extension',
  acl: 'icon-security',
  index_alias: 'icon-synonym',
  template: 'icon-template',
  pipeline: 'icon-query-tool',
  shard: 'icon-partition',
  snapshot: 'icon-backup',
  ingest_processor: 'icon-query-tool',
  measurement: 'icon-statistics',
  tag: 'icon-collation',
  field: 'icon-column',
  retention_policy: 'icon-clock',
  vector_collection: 'icon-coll-table',
  vector: 'icon-type',
  semantic_model: 'icon-erd',
});

const ACTION_COMPONENTS = Object.freeze({
  about: InformationCircleIcon,
  accept_version: AcceptVersionIcon,
  accessible_table: AccessibleTableIcon,
  add: AddCircleIcon,
  ai_draft: AiDraftSparkleIcon,
  align: AlignIcon,
  alter: EditIcon,
  attach: LinkIcon,
  axis_format: AxisFormatIcon,
  backup: DatabaseBackupIcon,
  branch_draft: BranchDraftIcon,
  browse_data: BrowseDataGridIcon,
  cancel: CancelCircleIcon,
  check: AcceptVersionIcon,
  checkpoints: HistoryIcon,
  close: CancelCircleIcon,
  collector_snapshot: CollectorSnapshotIcon,
  command_palette: CommandLineIcon,
  comment: SectionCommentsIcon,
  commit: SaveIcon,
  compare: GitCompareIcon,
  compare_run: RefreshIcon,
  connect: ConnectIcon,
  connect_as: ConnectAsUserIcon,
  copy: CopyIcon,
  count_rows: CountRowsHashIcon,
  create: AddCircleIcon,
  create_database: DatabaseAddIcon,
  customize: CustomizeSlidersIcon,
  cut: CutIcon,
  dashboard_cards: DashboardCardsIcon,
  delete: DeleteIcon,
  dependencies: DependenciesGraphIcon,
  dependents: DependentsGraphIcon,
  detach: UnlinkIcon,
  disconnect: UnlinkIcon,
  documentation: HelpCircleIcon,
  drawer_close: DrawerCloseIcon,
  drop: DeleteIcon,
  duplicate: CopyIcon,
  edit: EditIcon,
  embed_switch: EmbedSwitchIcon,
  embedded_host: EmbeddedHostIcon,
  endpoint_source: EndpointSourceIcon,
  endpoint_target: EndpointTargetIcon,
  engine_convert: EngineConvertIcon,
  engines: EnginesToggleIcon,
  env_matrix: EnvMatrixIcon,
  execute: PlayCircleIcon,
  explain: StatisticsBarChartIcon,
  export: DownloadIcon,
  export_csv: ExportCsvIcon,
  export_json: ExportJsonIcon,
  external: ExternalWindowIcon,
  external_link: ExternalWindowIcon,
  fetch_limits: FetchLimitsIcon,
  filter: FilterIcon,
  float: ArrowAllDirectionIcon,
  font_size: FontSizeIcon,
  git_sync: GitSyncIcon,
  help: HelpCircleIcon,
  history: HistoryIcon,
  import: UploadIcon,
  insert: AddCircleIcon,
  inspector_drawer: InspectorDrawerIcon,
  kiosk_device: KioskDeviceIcon,
  lattice_reducer: LatticeReducerIcon,
  layers: LayersIcon,
  level_conceptual: LevelConceptualIcon,
  level_deployment: LevelDeploymentIcon,
  level_logical: LevelLogicalIcon,
  level_physical: LevelPhysicalIcon,
  locale_translation: LocaleTranslationIcon,
  lock: LockIcon,
  maintenance: CustomizeSlidersIcon,
  manage_routes: ManageRoutesIcon,
  menu: MenuCircleIcon,
  monitor: StatisticsBarChartIcon,
  move: ArrowAllDirectionIcon,
  move_down: MoveDownIcon,
  move_up: MoveUpIcon,
  naming_standards: NamingStandardsIcon,
  new: FileAddIcon,
  open: EyeIcon,
  operation: SectionOperationsIcon,
  palette_color: ColorPaletteIcon,
  palette_entities: PaletteEntitiesIcon,
  palette_udt: PaletteUdtIcon,
  paste: PasteIcon,
  pause: QueryPauseIcon,
  perspective: PerspectiveEyeIcon,
  pin_node: PinNodeIcon,
  play: PlayCircleIcon,
  preferences: CustomizeSlidersIcon,
  print: PrinterIcon,
  promote_whiteboard: PromoteWhiteboardIcon,
  properties: InformationCircleIcon,
  query_pause: QueryPauseIcon,
  recompute_layout: RecomputeLayoutIcon,
  redact_region: RedactRegionIcon,
  redo: RedoIcon,
  refresh: RefreshIcon,
  rename: EditIcon,
  restore: DatabaseRestoreIcon,
  rollback: HistoryIcon,
  save: SaveIcon,
  savepoint: SavepointFlagIcon,
  schedule: CalendarClockIcon,
  screenshot_upload: ScreenshotUploadIcon,
  script: CodeIcon,
  search: SearchIcon,
  section_columns: SectionColumnsIcon,
  section_comments: SectionCommentsIcon,
  section_constraints: SectionConstraintsIcon,
  section_indexes: SectionIndexesIcon,
  section_operations: SectionOperationsIcon,
  section_tags: SectionTagIcon,
  security: ShieldUserIcon,
  select_marquee: SelectMarqueeIcon,
  select_pointer: SelectPointerIcon,
  send_review: SendReviewIcon,
  server_host: ServerHostIcon,
  settings: SettingsIcon,
  sign_out: SignOutIcon,
  sketch_look: SketchLookIcon,
  sort: SortIcon,
  source_endpoint: EndpointSourceIcon,
  sql_builder: SqlBuilderIcon,
  sql_preview: CodeIcon,
  star_schema: StarSchemaIcon,
  statistics: StatisticsBarChartIcon,
  status_in_progress: StatusInProgressIcon,
  status_in_review: StatusInReviewIcon,
  stop: CancelCircleIcon,
  subscriptions_alerts: SubscriptionsAlertsIcon,
  system_drift: SystemDriftIcon,
  target_endpoint: EndpointTargetIcon,
  terminal: CommandLineIcon,
  trace_mesh: TraceMeshIcon,
  transaction: TransactionIcon,
  truncate: TruncateTableIcon,
  tune: FetchLimitsIcon,
  undo: UndoIcon,
  unlock: UnlockOpenIcon,
  usage_matrix: UsageMatrixIcon,
  view: EyeIcon,
  where_used: WhereUsedIcon,
});

const ACTION_INFERENCE = Object.freeze([
  ['create_database', /\b(?:create|new|register|add)[ _-]+database\b/],
  ['disconnect', /\bdisconnect(?:ed|ion)?\b/],
  ['connect_as', /\bconnect[ _-]+as\b/],
  ['manage_routes', /\b(?:manage[ _-]+)?routes?\b/],
  ['browse_data', /\bbrowse[ _-]+data\b/],
  ['sql_builder', /\b(?:sql[ _-]+builder|build[ _-]+query)\b/],
  ['export_csv', /\bexport[ _-]+csv\b/],
  ['export_json', /\bexport[ _-]+json\b/],
  ['savepoint', /\bsavepoints?\b/],
  ['truncate', /\btruncate\b/],
  ['count_rows', /\bcount[ _-]+rows?\b/],
  ['tool.docker', /\bdocker\b/],
  ['tool.profiler', /\bprofiler?\b/],
  ['tool.isql', /\bisql\b/],
  ['tool.binlog_replay', /\bbinlogs?(?:[ _-]+replay)?\b/],
  ['server_host', /\b(?:fleet|topolog(?:y|ies)|routers?|sandboxes|eds[ _-]+pool)\b/],
  ['duplicate', /\blocal[ _-]+clone\b/],
  ['detach', /\bdetach\b/],
  ['rollback', /\broll[ _-]?back\b/],
  ['restore', /\brestore\b/],
  ['backup', /\bbackup\b/],
  ['documentation', /\b(?:documentation|manual|docs)\b/],
  ['properties', /\b(?:properties|details|information)\b/],
  ['security', /\b(?:security|permissions?|privileges?|grants?|roles?|users?)\b/],
  ['transaction', /\btransactions?\b/],
  ['schedule', /\b(?:schedule|jobs?|events?)\b/],
  ['compare', /\b(?:compare|comparison|diff)\b/],
  ['settings', /\b(?:settings?|preferences?|configure|configuration|manage)\b/],
  ['execute', /\b(?:execute|run|start|play)\b/],
  ['terminal', /\b(?:terminal|console|shell|command[ _-]?line|psql)\b/],
  ['script', /\b(?:script|code|sql)\b/],
  ['connect', /\bconnect(?:ion)?\b/],
  ['attach', /\b(?:attach|link)\b/],
  ['delete', /\b(?:delete|remove)\b/],
  ['drop', /\bdrop\b/],
  ['cancel', /\b(?:cancel|abort|stop)\b/],
  ['close', /\b(?:close|exit|quit)\b/],
  ['import', /\b(?:import|upload)\b/],
  ['export', /\b(?:export|download)\b/],
  ['refresh', /\b(?:refresh|reload|rescan|sync)\b/],
  ['search', /\b(?:search|find|locate)\b/],
  ['filter', /\bfilter\b/],
  ['sort', /\bsort\b/],
  ['copy', /\b(?:copy|duplicate|clone)\b/],
  ['rename', /\brename\b/],
  ['alter', /\balter\b/],
  ['edit', /\b(?:edit|modify|update)\b/],
  ['commit', /\bcommit\b/],
  ['save', /\bsave\b/],
  ['undo', /\bundo\b/],
  ['redo', /\bredo\b/],
  ['print', /\bprint\b/],
  ['lock', /\block\b/],
  ['unlock', /\bunlock\b/],
  ['float', /\b(?:float|tear[ _-]?off|undock)\b/],
  ['move', /\b(?:move|reorder)\b/],
  ['new', /\bnew\b/],
  ['create', /\b(?:create|register|add)\b/],
  ['open', /\bopen\b/],
  ['view', /\b(?:view|show|inspect|browse)\b/],
  ['about', /\babout\b/],
  ['help', /\bhelp\b/],
]);

const STATUS_CLASSES = Object.freeze({
  connected: 'fa fa-check-circle',
  disconnected: 'fa fa-circle-o',
  error: 'fa fa-exclamation-circle',
  loading: 'fa fa-spinner fa-spin',
  locked: 'fa fa-lock',
  offline: 'fa fa-minus-circle',
  readonly: 'fa fa-eye',
  running: 'fa fa-play-circle',
  stopped: 'fa fa-stop-circle',
  warning: 'fa fa-exclamation-triangle',
});

const TOOL_CLASSES = Object.freeze({
  dashboard: 'icon-dashboard',
  dataflow: 'icon-erd',
  datapump: 'fa fa-exchange',
  mind_map: 'fa fa-sitemap',
  report: 'fa fa-bar-chart',
  whiteboard: 'fa fa-pencil-square-o',
});

const TAXONOMY_FALLBACKS = Object.freeze([
  ['relation.view.materialized', 'object.materialized_view'],
  ['relation.view', 'object.view'],
  ['relation.column', 'object.column'],
  ['relation.partition', 'object.partition'],
  ['relation.sequence', 'object.sequence'],
  ['relation.table', 'object.table'],
  ['columnar.table', 'object.columnar_table'],
  ['wide_column.table', 'object.wide_column_table'],
  ['access.index', 'object.index'],
  ['constraint.', 'object.constraint'],
  ['routine.procedure', 'object.procedure'],
  ['routine.trigger', 'object.trigger'],
  ['routine.package', 'object.package'],
  ['routine.', 'object.function'],
  ['namespace.keyspace', 'object.keyspace'],
  ['namespace.schema', 'object.schema'],
  ['namespace.', 'object.database'],
  ['security.role', 'object.role'],
  ['security.user', 'object.user'],
  ['security.', 'object.privilege'],
  ['replication.', 'object.replication'],
  ['operation.job', 'object.job'],
  ['operation.event', 'object.event'],
  ['operation.snapshot', 'object.snapshot'],
  ['topology.node', 'object.node'],
  ['topology.', 'object.cluster'],
  ['keyvalue.stream', 'object.stream'],
  ['keyvalue.ttl', 'object.ttl'],
  ['keyvalue.', 'object.key'],
  ['graph.relationship', 'object.relationship'],
  ['graph.node', 'object.node'],
  ['graph.', 'object.graph_projection'],
  ['search.pipeline', 'object.pipeline'],
  ['search.', 'object.index'],
  ['timeseries.measurement', 'object.measurement'],
  ['timeseries.tag', 'object.tag'],
  ['timeseries.', 'object.field'],
  ['vector.collection', 'object.vector_collection'],
  ['vector.', 'object.vector'],
  ['semantic.', 'object.semantic_model'],
  ['storage.filespace', 'object.filespace'],
  ['storage.tablespace', 'object.tablespace'],
]);

const SAFE_CLASS = /^[a-zA-Z0-9_-]+(?:\s+[a-zA-Z0-9_-]+)*$/;
const SAFE_KEY = /^[a-z0-9][a-z0-9._-]*$/;
export const ICON_ASSIGNMENT_SCHEMA = 'cdeadmin.icon-assignments.v1';

function title(value) {
  return String(value).replace(/[._-]+/g, ' ').replace(/\b\w/g, (c)=>c.toUpperCase());
}

function definition(key, category, className, label=title(key.split('.').pop())) {
  return Object.freeze({key, category, kind: 'class', className, label});
}

function componentDefinition(
  key, category, component, label=title(key.split('.').pop())
) {
  return Object.freeze({
    key,
    category,
    kind: 'component',
    component,
    label,
    license: 'MIT',
    attribution: 'Hugeicons Free Icons 4.3.0',
  });
}

const BUILTIN_DEFINITIONS = [
  ...ENGINE_IDS.map((id)=>definition(
    `engine.${id}`, ICON_CATEGORIES.ENGINE, `icon-engine-type-${id}`,
    title(id)
  )),
  ...Object.entries(OBJECT_CLASSES).map(([name, className])=>definition(
    `object.${name}`, ICON_CATEGORIES.OBJECT, className
  )),
  componentDefinition(
    'object.blob_filter', ICON_CATEGORIES.OBJECT, FilterIcon, 'BLOB Filter'
  ),
  componentDefinition(
    'object.shadow', ICON_CATEGORIES.OBJECT, CopyIcon, 'Database Shadow'
  ),
  componentDefinition(
    'object.storage_file', ICON_CATEGORIES.OBJECT, SaveIcon, 'Storage File'
  ),
  componentDefinition(
    'object.folder', ICON_CATEGORIES.OBJECT, FolderObjectIcon, 'Folder'
  ),
  componentDefinition(
    'object.notebook', ICON_CATEGORIES.OBJECT, FileAddIcon, 'SQL Notebook'
  ),
  componentDefinition(
    'object.schedule', ICON_CATEGORIES.OBJECT, CalendarClockIcon, 'Schedule & Calendar'
  ),
  componentDefinition(
    'object.setting', ICON_CATEGORIES.OBJECT, SettingsIcon, 'Configuration Setting'
  ),
  componentDefinition(
    'object.session', ICON_CATEGORIES.OBJECT, ConnectAsUserIcon, 'Active Session'
  ),
  componentDefinition(
    'folder.monitoring', ICON_CATEGORIES.OBJECT, StatisticsBarChartIcon, 'Monitoring Folder'
  ),
  componentDefinition(
    'folder.programming', ICON_CATEGORIES.OBJECT, CodeIcon, 'Programming Folder'
  ),
  componentDefinition(
    'folder.security', ICON_CATEGORIES.OBJECT, ShieldUserIcon, 'Security Folder'
  ),
  componentDefinition(
    'folder.system', ICON_CATEGORIES.OBJECT, ServerHostIcon, 'System Folder'
  ),
  componentDefinition(
    'object.dimension', ICON_CATEGORIES.OBJECT, DimensionObjectIcon, 'Dimension'
  ),
  componentDefinition(
    'object.hierarchy', ICON_CATEGORIES.OBJECT, HierarchyObjectIcon, 'Hierarchy'
  ),
  componentDefinition(
    'object.measure', ICON_CATEGORIES.OBJECT, MeasureObjectIcon, 'Measure'
  ),
  componentDefinition(
    'navigation.sidebar', ICON_CATEGORIES.ACTION, NavigationSidebarIcon, 'Left Side Drawer'
  ),
  componentDefinition(
    'view.toolbar', ICON_CATEGORIES.ACTION, ViewToolbarIcon, 'Tabbed-Icon-Bar'
  ),
  componentDefinition(
    'view.status', ICON_CATEGORIES.ACTION, ViewStatusBarIcon, 'Status Bar'
  ),
  componentDefinition(
    'security.lock', ICON_CATEGORIES.ACTION, LockIcon, 'Lock Screen'
  ),
  componentDefinition(
    'help.docs', ICON_CATEGORIES.ACTION, HelpCircleIcon, 'Documentation'
  ),
  componentDefinition(
    'help.info', ICON_CATEGORIES.ACTION, InformationCircleIcon, 'Glossary & Info'
  ),
  componentDefinition(
    'ui.screen_frame', ICON_CATEGORIES.OBJECT, UiScreenFrameIcon, 'Screen Frame'
  ),
  componentDefinition(
    'ui.grid_control', ICON_CATEGORIES.OBJECT, UiGridControlIcon, 'Grid Control'
  ),
  componentDefinition(
    'ui.dropdown_control', ICON_CATEGORIES.OBJECT, UiDropdownControlIcon, 'Dropdown Control'
  ),
  componentDefinition(
    'ui.radio_control', ICON_CATEGORIES.OBJECT, UiRadioControlIcon, 'Radio Control'
  ),
  componentDefinition(
    'ui.tabs_control', ICON_CATEGORIES.OBJECT, UiTabsControlIcon, 'Tabs Control'
  ),
  componentDefinition(
    'ui.region_hotspot', ICON_CATEGORIES.OBJECT, UiRegionHotspotIcon, 'Image Region'
  ),
  componentDefinition(
    'ui.data_binding', ICON_CATEGORIES.ACTION, UiDataBindingIcon, 'Data Binding'
  ),
  componentDefinition(
    'ui.screen_navigation', ICON_CATEGORIES.ACTION, UiScreenNavigationIcon, 'Screen Navigation'
  ),
  componentDefinition(
    'command.default', ICON_CATEGORIES.ACTION, MenuCircleIcon, 'Command'
  ),
  componentDefinition(
    'tool.schema-compare', ICON_CATEGORIES.TOOL, GitCompareIcon, 'Schema Comparison'
  ),
  componentDefinition(
    'tool.schema-diff', ICON_CATEGORIES.TOOL, GitCompareIcon, 'Schema Diff'
  ),
  componentDefinition(
    'tool.docker', ICON_CATEGORIES.TOOL, DockerContainerIcon, 'Docker Containers'
  ),
  componentDefinition(
    'tool.profiler', ICON_CATEGORIES.TOOL, ProfilerStopwatchIcon, 'Profiler'
  ),
  componentDefinition(
    'tool.isql', ICON_CATEGORIES.TOOL, CommandLineIcon, 'External ISQL'
  ),
  componentDefinition(
    'tool.psql', ICON_CATEGORIES.TOOL, CommandLineIcon, 'PSQL Tool'
  ),
  componentDefinition(
    'tool.command-line', ICON_CATEGORIES.TOOL, CommandLineIcon, 'Command Line'
  ),
  componentDefinition(
    'tool.binlog_replay', ICON_CATEGORIES.TOOL, BinlogReplayIcon, 'Binlog Replay'
  ),
  componentDefinition(
    'tool.ai-interface', ICON_CATEGORIES.TOOL, AiDraftSparkleIcon, 'AI Interface'
  ),
  componentDefinition(
    'tool.discovery', ICON_CATEGORIES.TOOL, SearchIcon, 'Discovery Intelligence'
  ),
  componentDefinition(
    'tool.lineage', ICON_CATEGORIES.TOOL, LinkIcon, 'Data Lineage'
  ),
  componentDefinition(
    'tool.quality', ICON_CATEGORIES.TOOL, FilterIcon, 'Data Quality'
  ),
  componentDefinition(
    'tool.contract', ICON_CATEGORIES.TOOL, ShieldUserIcon, 'Data Contract Manager'
  ),
  componentDefinition(
    'tool.etl', ICON_CATEGORIES.TOOL, ArrowAllDirectionIcon, 'ETL Designer'
  ),
  componentDefinition(
    'tool.cdc', ICON_CATEGORIES.TOOL, TransactionIcon, 'CDC Designer'
  ),
  componentDefinition(
    'tool.replication', ICON_CATEGORIES.TOOL, RefreshIcon, 'Replication Topology'
  ),
  componentDefinition(
    'tool.tracing', ICON_CATEGORIES.TOOL, SearchIcon, 'Distributed Tracing'
  ),
  componentDefinition(
    'tool.migration', ICON_CATEGORIES.TOOL, UploadIcon, 'Migration Planning'
  ),
  componentDefinition(
    'tool.api', ICON_CATEGORIES.TOOL, LinkIcon, 'API Designer'
  ),
  componentDefinition(
    'tool.ml-vector', ICON_CATEGORIES.TOOL, SearchIcon, 'ML / Vector Tooling'
  ),
  componentDefinition(
    'tool.ai', ICON_CATEGORIES.TOOL, CommandLineIcon, 'AI Database Assistant'
  ),
  ...Object.entries(ACTION_COMPONENTS).map(([name, component])=>componentDefinition(
    `action.${name}`, ICON_CATEGORIES.ACTION, component
  )),
  ...Object.entries(STATUS_CLASSES).map(([name, className])=>definition(
    `status.${name}`, ICON_CATEGORIES.STATUS, className
  )),
  ...Object.entries(TOOL_CLASSES).map(([name, className])=>definition(
    `tool.${name}`, ICON_CATEGORIES.TOOL, className
  )),
  componentDefinition(
    'tool.data-explorer', ICON_CATEGORIES.TOOL, EyeIcon, 'Data Explorer'
  ),
  componentDefinition(
    'tool.project-explorer', ICON_CATEGORIES.TOOL, FileAddIcon, 'Project Explorer'
  ),
  componentDefinition(
    'object.cube', ICON_CATEGORIES.OBJECT, DatabaseAddIcon, 'Cube'
  ),
  componentDefinition(
    'tool.cube', ICON_CATEGORIES.TOOL, DatabaseAddIcon, 'Cube Designer'
  ),
  componentDefinition(
    'tool.bi', ICON_CATEGORIES.TOOL, SortIcon, 'BI Questions & Dashboards'
  ),
  componentDefinition(
    'tool.screen-mesh', ICON_CATEGORIES.TOOL, EditIcon, 'Screen Mesh Designer'
  ),
  componentDefinition(
    'tool.erd', ICON_CATEGORIES.TOOL, ArrowAllDirectionIcon, 'Diagram Designer'
  ),
  componentDefinition(
    'tool.search', ICON_CATEGORIES.TOOL, SearchIcon, 'Discovery Search'
  ),
  componentDefinition(
    'tool.query', ICON_CATEGORIES.TOOL, CodeIcon, 'Query Tool'
  ),
  componentDefinition(
    'tool.scratchrobin', ICON_CATEGORIES.TOOL, ScratchRobinIcon,
    'ScratchRobin Home'
  ),
];

const builtins = new Map(BUILTIN_DEFINITIONS.map((item)=>[item.key, item]));
const providerDefinitions = new Map();

function normalizeDefinition(input) {
  const key = String(input?.key ?? '').trim().toLowerCase();
  if(!SAFE_KEY.test(key)) {
    throw new TypeError('Icon key must contain only lowercase semantic segments.');
  }
  const category = String(input.category ?? key.split('.')[0]);
  if(!Object.values(ICON_CATEGORIES).includes(category)) {
    throw new TypeError(`Unknown icon category: ${category}`);
  }
  const kind = input.svgUrl ? 'svg' : 'class';
  const className = String(input.className ?? '').trim();
  const svgUrl = String(input.svgUrl ?? '').trim();
  if(kind === 'class' && (!className || !SAFE_CLASS.test(className))) {
    throw new TypeError('Class icon definitions require safe CSS class names.');
  }
  if(kind === 'svg' && !svgUrl) {
    throw new TypeError('SVG icon definitions require a URL.');
  }
  if(kind === 'svg' && !/^(?:\/|https:\/\/)/.test(svgUrl)) {
    throw new TypeError('SVG icon URLs must use an application or HTTPS URL.');
  }
  return Object.freeze({
    key,
    category,
    kind,
    className,
    svgUrl,
    label: String(input.label ?? title(key.split('.').pop())),
    license: String(input.license ?? ''),
    attribution: String(input.attribution ?? ''),
    providerId: String(input.providerId ?? ''),
  });
}

export function registerIconDefinition(input) {
  const item = normalizeDefinition(input);
  if(builtins.has(item.key) || providerDefinitions.has(item.key)) {
    throw new Error(`Icon key is already registered: ${item.key}`);
  }
  providerDefinitions.set(item.key, item);
  return ()=>providerDefinitions.delete(item.key);
}

export function normalizeIconAssignments(input={}) {
  let candidate = input;
  if(typeof candidate === 'string') {
    try {
      candidate = JSON.parse(candidate || '{}');
    } catch {
      return Object.freeze({});
    }
  }
  if(candidate?.schema === ICON_ASSIGNMENT_SCHEMA) {
    candidate = candidate.assignments;
  }
  if(!candidate || Array.isArray(candidate) || typeof candidate !== 'object') {
    return Object.freeze({});
  }
  const assignments = {};
  Object.entries(candidate).forEach(([source, target]) => {
    const normalizedSource = String(source).trim().toLowerCase();
    const normalizedTarget = String(target).trim().toLowerCase();
    if(SAFE_KEY.test(normalizedSource) && SAFE_KEY.test(normalizedTarget) &&
        normalizedSource !== normalizedTarget) {
      assignments[normalizedSource] = normalizedTarget;
    }
  });
  return Object.freeze(assignments);
}

export function mergeIconAssignments(...layers) {
  return Object.freeze(Object.assign({}, ...layers.map(normalizeIconAssignments)));
}

export function createIconAssignmentDocument(assignments={}) {
  return Object.freeze({
    schema: ICON_ASSIGNMENT_SCHEMA,
    assignments: normalizeIconAssignments(assignments),
  });
}

function assignedIconKey(iconKey, input) {
  const assignments = normalizeIconAssignments(input);
  let key = String(iconKey ?? '').trim().toLowerCase();
  const visited = new Set();
  while(assignments[key] && !visited.has(key)) {
    visited.add(key);
    key = assignments[key];
  }
  return key;
}

function familyFallback(key) {
  const match = TAXONOMY_FALLBACKS.find(([prefix])=>key.startsWith(prefix));
  if(match) return builtins.get(match[1]);
  if(key.startsWith('action.') || key.startsWith('command.')) {
    return builtins.get('command.default');
  }
  return builtins.get('object.unknown');
}

export function resolveIconDefinition(iconKey, options={}) {
  let key = assignedIconKey(iconKey, options.assignments);
  if(providerDefinitions.has(key)) return providerDefinitions.get(key);
  if(builtins.has(key)) return builtins.get(key);

  // Provider object kinds use hyphens; the semantic icon registry uses
  // underscores. Preserve exact registered overrides before normalizing.
  if(key.startsWith('object.')) {
    const semanticKey = `object.${key.slice(7).replace(/-/g, '_')}`;
    const assignedSemanticKey = assignedIconKey(semanticKey, options.assignments);
    if(assignedSemanticKey !== semanticKey && assignedSemanticKey !== key) {
      return resolveIconDefinition(assignedSemanticKey, {...options, assignments: undefined});
    }
    if(providerDefinitions.has(semanticKey)) return providerDefinitions.get(semanticKey);
    if(builtins.has(semanticKey)) return builtins.get(semanticKey);
  }

  if(SAFE_CLASS.test(key) && (key.startsWith('icon-') || key.startsWith('fa '))) {
    return Object.freeze({
      key: `legacy.${key.replace(/\s+/g, '.')}`,
      category: options.category ?? ICON_CATEGORIES.OBJECT,
      kind: 'class',
      className: key,
      label: String(options.label ?? title(key)),
      legacy: true,
    });
  }

  if(!key.includes('.')) {
    const objectKey = `object.${key.replace(/-/g, '_')}`;
    if(builtins.has(objectKey)) return builtins.get(objectKey);
  }
  if(key.startsWith('engine.') && SAFE_KEY.test(key)) {
    return definition(key, ICON_CATEGORIES.ENGINE,
      `icon-engine-type-${key.slice(7)}`);
  }
  return familyFallback(key || 'object.unknown');
}

export function listIconDefinitions({category}={}) {
  return Object.freeze([...builtins.values(), ...providerDefinitions.values()]
    .filter((item)=>!category || item.category === category));
}

export function semanticObjectIconKey(objectType) {
  const normalized = String(objectType ?? 'unknown').trim().toLowerCase()
    .replace(/^coll-/, '').replace(/-/g, '_');
  return builtins.has(`object.${normalized}`) ?
    `object.${normalized}` : `object.${normalized || 'unknown'}`;
}

export function semanticEngineIconKey(engineId) {
  return `engine.${String(engineId ?? '').trim().toLowerCase()}`;
}

export function inferActionIconKey(action={}) {
  if(action.iconKey) return action.iconKey;
  const source = [action.id, action.name, action.label, action.description]
    .filter(Boolean).join(' ').toLowerCase().replace(/[^a-z0-9]+/g, ' ');
  const match = ACTION_INFERENCE.find(([, pattern])=>pattern.test(source));
  if(!match) return '';
  return match[0].includes('.') ? match[0] : `action.${match[0]}`;
}

export function resolveSectionIconKey(sectionKey, titleOrEngine='') {
  const raw = String(sectionKey ?? '').trim().toLowerCase();
  const extra = String(titleOrEngine ?? '').trim().toLowerCase();
  if (raw === 'connection') return 'action.connect';
  if (raw === 'authentication' || raw === 'auth') return 'action.security';
  if (raw === 'ssl/tls' || raw === 'ssl' || raw === 'tls') return 'action.lock';
  if (raw === 'advanced' || raw === 'options') return 'action.settings';
  if (raw === 'tags') return 'action.section_tags';
  if (raw === 'engine') {
    const engMatch = ENGINE_IDS.find(
      (id) => extra === id || extra.replace(/[^a-z0-9]+/g, '_') === id || extra.startsWith(id)
    );
    return engMatch ? `engine.${engMatch}` : 'action.layers';
  }
  const directEngine = ENGINE_IDS.find((id) => raw === id);
  if (directEngine) return `engine.${directEngine}`;
  if (raw === 'general' || raw === 'properties' || raw === 'summary' || raw === 'state') {
    return 'action.properties';
  }
  if (raw === 'columns' || raw === 'fields') return 'action.section_columns';
  if (raw === 'constraints' || raw === 'checks') return 'action.section_constraints';
  if (raw === 'indexes' || raw === 'keys') return 'action.section_indexes';
  if (raw === 'triggers' || raw === 'events') return 'action.send_review';
  if (raw === 'grants' || raw === 'privileges' || raw === 'security') return 'action.security';
  if (raw === 'comments' || raw === 'notes') return 'action.section_comments';
  if (
    raw === 'sql' ||
    raw === 'ddl' ||
    raw === 'definition' ||
    raw === 'calculations' ||
    raw === 'code'
  ) {
    return 'action.sql_preview';
  }
  if (raw === 'dependencies') return 'action.dependencies';
  if (raw === 'dependents') return 'action.dependents';
  if (raw === 'statistics') return 'action.statistics';
  if (raw === 'operations') return 'action.section_operations';
  if (raw === 'data') return 'action.open';
  if (raw === 'parameters') return 'action.fetch_limits';
  if (raw === 'files') return 'action.save';
  return 'action.layers';
}
