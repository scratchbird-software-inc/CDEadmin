import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Box} from '@mui/material';
import references from './formReferences.json';

export const QA_FORM_REFS_STORAGE_KEY = 'scratchrobin.qa.show_form_refs';
export const QA_FORM_REFS_EVENT = 'scratchrobin:qa-form-refs-changed';

const VISIBLE_BADGE_SX = {
  display: 'block',
  color: 'text.secondary',
  fontFamily: 'monospace',
  px: 1,
};

const VISUALLY_HIDDEN_SX = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

export function readShowFormReferences() {
  if (typeof window === 'undefined') return false;
  if (window.__SCRATCHROBIN_SHOW_FORM_REFS === true) return true;
  try {
    return window.localStorage?.getItem(QA_FORM_REFS_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function setShowFormReferences(enabled) {
  const next = Boolean(enabled);
  if (typeof window === 'undefined') return next;
  window.__SCRATCHROBIN_SHOW_FORM_REFS = next;
  try {
    if (next) {
      window.localStorage?.setItem(QA_FORM_REFS_STORAGE_KEY, 'true');
    } else {
      window.localStorage?.removeItem(QA_FORM_REFS_STORAGE_KEY);
    }
  } catch {
    // Ignore restricted storage contexts; window global still reflects current mode.
  }
  window.dispatchEvent(new CustomEvent(QA_FORM_REFS_EVENT, {detail: {enabled: next}}));
  return next;
}

export function formReference(key) {
  return references.forms[key]?.reference || references.forms.placeholder.reference;
}

export default function FormReference({formKey, reference, children, sx}) {
  const id = reference || formReference(formKey);
  const [showRefs, setShowRefs] = useState(() => readShowFormReferences());

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const sync = () => setShowRefs(readShowFormReferences());
    sync();
    window.addEventListener(QA_FORM_REFS_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(QA_FORM_REFS_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  return (
    <Box data-form-reference={id} data-sr-form-ref={id} sx={{minWidth: 0, ...sx}}>
      <Box
        component="small"
        aria-label="Form reference"
        sx={showRefs ? VISIBLE_BADGE_SX : VISUALLY_HIDDEN_SX}
      >
        {id}
      </Box>
      {children}
    </Box>
  );
}

FormReference.propTypes = {
  formKey: PropTypes.string,
  reference: PropTypes.string,
  children: PropTypes.node,
  sx: PropTypes.object,
};
