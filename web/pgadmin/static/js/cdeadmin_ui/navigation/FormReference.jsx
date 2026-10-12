import PropTypes from 'prop-types';
import {Box} from '@mui/material';
import references from './formReferences.json';

export function formReference(key) {
  return references.forms[key]?.reference || references.forms.placeholder.reference;
}
export default function FormReference({formKey, reference, children}) {
  const id = reference || formReference(formKey);
  return <Box data-form-reference={id} sx={{minWidth: 0}}>
    <Box component="small" aria-label="Form reference" sx={{display: 'block', color: 'text.secondary', fontFamily: 'monospace', px: 1}}>{id}</Box>
    {children}
  </Box>;
}
FormReference.propTypes = {formKey: PropTypes.string, reference: PropTypes.string, children: PropTypes.node};
