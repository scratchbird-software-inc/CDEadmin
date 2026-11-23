/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import HTMLReactParser from 'html-react-parser';
import DOMPurify from 'dompurify';
import gettext from 'sources/gettext';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';

export default function ConfirmSaveContent({closeModal, text, onDontSave, onSave}) {
  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16}}>
        {typeof text === 'string' ? HTMLReactParser(DOMPurify.sanitize(text)) : text}
      </Box>
      <ModalFooter>
        <Button
          data-test="close"
          onClick={() => {
            closeModal();
          }}
        >
          {gettext('Cancel')}
        </Button>
        <Button
          data-test="dont-save"
          variant="danger"
          onClick={() => {
            onDontSave?.();
            closeModal();
          }}
        >
          {gettext('Don\'t save')}
        </Button>
        <Button
          data-test="save"
          variant="primary"
          autoFocus
          onClick={() => {
            onSave?.();
            closeModal();
          }}
        >
          {gettext('Save')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

ConfirmSaveContent.propTypes = {
  closeModal: PropTypes.func,
  text: PropTypes.node,
  onDontSave: PropTypes.func,
  onSave: PropTypes.func,
};
