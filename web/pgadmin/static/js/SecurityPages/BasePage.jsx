import { Box, Button, darken } from '@mui/material';
import { styled } from '@mui/material/styles';
import { useSnackbar } from 'notistack';
import { useEffect } from 'react';
import { MESSAGE_TYPE, NotifierMessage } from '../components/FormComponents';
import { FinalNotifyContent } from '../helpers/Notifier';
import PropTypes from 'prop-types';
import CustomPropTypes from '../custom_prop_types';
import gettext from 'sources/gettext';
import ScratchRobinMarkUrl from '../../assets/cdeadmin/branding/scratchrobin-dark.svg?url';

// Owner direction 2026-11-06: the sign-in pages follow the ScratchBird
// Software sign-in standard (owner reference): a navy brand panel beside a
// light sign-in panel. The brand panel states the release honestly.
const brandNavy = '#1b2640';
const brandAccent = '#7fa8e6';
const brandMuted = '#aab6cc';
const actionBlue = '#3366d6';

const StyledBox = styled(Box)(({theme}) => ({
  display: 'flex',
  minHeight: '100%',
  height: '100%',
  overflow: 'auto',
  backgroundColor: theme.palette.background.default,
  color: theme.palette.text.primary,
  '& .BasePage-brand': {
    position: 'relative',
    overflow: 'hidden',
    flex: '0 0 46%',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    gap: '2rem',
    padding: '3rem 3.5rem',
    backgroundColor: brandNavy,
    color: '#ffffff',
    '&::after': {
      // Decorative rings, as in the reference layout.
      content: '""',
      position: 'absolute',
      right: '-18rem',
      bottom: '-20rem',
      width: '34rem',
      height: '34rem',
      borderRadius: '50%',
      border: '4.5rem solid rgba(255, 255, 255, 0.035)',
      pointerEvents: 'none',
    },
  },
  '& .BasePage-mark': {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    '& img': {width: '2.75rem', height: '2.75rem', flex: '0 0 auto'},
  },
  '& .BasePage-wordmark': {
    fontSize: '1.2rem',
    lineHeight: 1.2,
    '& strong': {fontWeight: 700},
  },
  '& .BasePage-console': {
    marginTop: '0.2rem',
    fontSize: '0.68rem',
    fontWeight: 600,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
    color: brandAccent,
  },
  '& .BasePage-story': {
    position: 'relative',
    zIndex: 1,
    maxWidth: '34rem',
  },
  '& .BasePage-eyebrow': {
    margin: 0,
    fontSize: '0.72rem',
    fontWeight: 700,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    color: brandAccent,
  },
  '& .BasePage-headline': {
    margin: '1rem 0',
    fontSize: '2.4rem',
    lineHeight: 1.15,
    fontWeight: 600,
    letterSpacing: '-0.02em',
  },
  '& .BasePage-lead': {
    margin: 0,
    maxWidth: '27rem',
    fontSize: '0.9rem',
    lineHeight: 1.7,
    color: brandMuted,
  },
  '& .BasePage-facts': {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.4rem 1.2rem',
    margin: '1.75rem 0 0',
    padding: 0,
    listStyle: 'none',
    fontSize: '0.75rem',
    color: brandAccent,
    '& li + li::before': {
      content: '"·"',
      marginRight: '1.2rem',
      color: brandMuted,
    },
  },
  '& .BasePage-company': {
    position: 'relative',
    zIndex: 1,
    margin: 0,
    fontSize: '0.72rem',
    color: brandMuted,
  },
  '& .BasePage-panel': {
    flex: '1 1 auto',
    backgroundColor: theme.palette.mode === 'dark' ?
      theme.palette.background.default : '#f7f8fb',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '3rem 1.5rem',
  },
  '& .BasePage-pageContent': {
    display: 'flex',
    flexDirection: 'column',
    width: '100%',
    maxWidth: '21rem',
    '& .MuiOutlinedInput-root': {
      borderRadius: '6px',
      '& fieldset': {
        borderRadius: '6px',
      },
    },
    '& .MuiButton-root': {
      borderRadius: '6px',
    },
    // Nested here so it outranks the theme's own button styles.
    '& .BasePage-button': {
      backgroundColor: actionBlue,
      color: '#fff',
      padding: '0.55rem 0.9rem',
      width: '100%',
      justifyContent: 'space-between',
      textTransform: 'none',
      fontWeight: 600,
      '&:hover': {
        backgroundColor: darken(actionBlue, 0.12),
      },
      '&.Mui-disabled': {
        opacity: 0.60,
        color: '#fff'
      },
    },
  },
  '& .BasePage-tile': {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '3rem',
    height: '3rem',
    marginBottom: '1.5rem',
    padding: '0.6rem',
    borderRadius: '10px',
    border: `1px solid ${theme.palette.divider}`,
    backgroundColor: theme.palette.mode === 'dark' ?
      theme.palette.background.paper : '#eaf0fb',
    color: actionBlue,
    '& svg, & img': {width: '100%', height: '100%'},
  },
  '& .BasePage-title': {
    margin: 0,
    fontSize: '1.5rem',
    fontWeight: 700,
    letterSpacing: '-0.01em',
  },
  '& .BasePage-subtitle': {
    margin: '0.4rem 0 0',
    fontSize: '0.85rem',
    color: theme.palette.text.muted ?? theme.palette.text.secondary,
  },
  '& .BasePage-form': {
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    marginTop: '1.75rem',
  },
  '& .BasePage-label': {
    display: 'block',
    marginBottom: '0.3rem',
    fontSize: '0.78rem',
    fontWeight: 600,
  },
  // Narrow windows and enlarged text: stack the panels, never clip.
  '@media (max-width: 900px)': {
    flexDirection: 'column',
    height: 'auto',
    '& .BasePage-brand': {
      flex: '0 0 auto',
      padding: '2rem 1.5rem',
    },
    '& .BasePage-headline': {
      fontSize: '1.7rem',
    },
  },
}));

function LockGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

// '0.325-alpha' reads as 'Alpha 0.325'; a plain number is shown as it is.
export function releaseLabel(productVersion) {
  if (!productVersion) return null;
  const [number, stage] = String(productVersion).split('-', 2);
  if (!stage) return number;
  return `${stage.charAt(0).toUpperCase()}${stage.slice(1)} ${number}`;
}

export function SecurityButton({children, ...props}) {

  return <Button type="submit" className='BasePage-button' {...props}>
    <span>{children}</span>
    <span aria-hidden="true">›</span>
  </Button>;
}

SecurityButton.propTypes = {
  children: CustomPropTypes.children,
};

function BrandPanel({productVersion, qaKey}) {
  const release = releaseLabel(productVersion);
  return (
    <Box component="aside" className='BasePage-brand'
      aria-label={gettext('About ScratchRobin')} data-cdeadmin-qa-key={qaKey}>
      <div className='BasePage-mark'>
        <img src={ScratchRobinMarkUrl} alt="" />
        <div>
          <div className='BasePage-wordmark'>Scratch<strong>Robin</strong></div>
          <div className='BasePage-console'>{gettext('CDE administration console')}</div>
        </div>
      </div>
      <div className='BasePage-story'>
        <p className='BasePage-eyebrow'>
          {release ? gettext('Open-source project · %s', release) :
            gettext('Open-source project')}
        </p>
        <h1 className='BasePage-headline'>
          {gettext('Many data engines. One administration console.')}
        </h1>
        <p className='BasePage-lead'>
          {gettext('ScratchRobin is an open-source project in alpha release. Only a few of its supported platforms, and part of its functionality, are ready for review. It is not approved for production use.')}
        </p>
        <ul className='BasePage-facts'>
          <li>{gettext('Open source')}</li>
          {release && <li>{release}</li>}
          <li>{gettext('Not for production use')}</li>
        </ul>
      </div>
      <p className='BasePage-company'>ScratchBird Software Inc.</p>
    </Box>
  );
}

BrandPanel.propTypes = {
  productVersion: PropTypes.string,
  qaKey: PropTypes.string,
};

export default function BasePage({pageImage, title, subtitle, children, messages,
  productVersion, brandQaKey}) {
  const snackbar = useSnackbar();
  useEffect(()=>{
    messages?.forEach((message)=>{
      let options = {
        autoHideDuration: null,
        content:(key)=>{
          if(Array.isArray(message[0])) message[0] = message[0][0];
          const type = Object.values(MESSAGE_TYPE).includes(message[0]) ? message[0] : MESSAGE_TYPE.INFO;
          return <FinalNotifyContent>
            <NotifierMessage type={type} message={message[1]} closable={true} onClose={()=>{snackbar.closeSnackbar(key);}} style={{maxWidth: '400px'}} />
          </FinalNotifyContent>;
        }
      };
      options.content.displayName = 'content';
      snackbar.enqueueSnackbar(options);
    });
  }, [messages]);
  return (
    <StyledBox>
      <BrandPanel productVersion={productVersion} qaKey={brandQaKey} />
      <Box component="main" className='BasePage-panel'>
        <Box className='BasePage-pageContent'>
          <div className='BasePage-tile' aria-hidden="true">
            {pageImage ?? <LockGlyph />}
          </div>
          <h2 className='BasePage-title'>{title}</h2>
          {subtitle && <p className='BasePage-subtitle'>{subtitle}</p>}
          <div className='BasePage-form'>{children}</div>
        </Box>
      </Box>
    </StyledBox>
  );
}

BasePage.propTypes = {
  pageImage: CustomPropTypes.children,
  title: PropTypes.string,
  subtitle: PropTypes.string,
  children: CustomPropTypes.children,
  messages: PropTypes.arrayOf(PropTypes.array),
  productVersion: PropTypes.string,
  brandQaKey: PropTypes.string,
};
