import PropTypes from 'prop-types';
import {Alert, Box} from '@mui/material';
import FormReference from './FormReference';

export default function MissingForm({reference, title, context}) {
  return <FormReference reference={reference} formKey="placeholder">
    <Alert severity="info">{title || 'This form'} — form not implemented. No database operation is available from this placeholder.</Alert>
    <Box component="pre" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{JSON.stringify(context, null, 2)}</Box>
  </FormReference>;
}
MissingForm.propTypes = {reference: PropTypes.string, title: PropTypes.string, context: PropTypes.object};
