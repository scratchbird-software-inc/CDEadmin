/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import HTMLReactParser from 'html-react-parser';
import DOMPurify from 'dompurify';
import gettext from 'sources/gettext';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box} from '../../../../../../static/js/cdeadmin_ui/primitives/Layout';
import {Button} from '../../../../../../static/js/cdeadmin_ui/primitives/Button';
import {Checkbox} from '../../../../../../static/js/cdeadmin_ui/primitives/Choice';

export default function ConfirmPromotionContent({
  onContinue,
  onClose,
  closeModal,
  text,
}) {
  const [saveUserChoice, setSaveUserChoice] = useState(false);

  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16}}>
        {typeof text === 'string'
          ? HTMLReactParser(DOMPurify.sanitize(text))
          : text}
      </Box>
      <ModalFooter>
        <Box style={{marginRight: 'auto'}}>
          <Checkbox
            label={gettext('Don\'t ask again')}
            checked={saveUserChoice}
            onChange={(checked) => setSaveUserChoice(Boolean(checked))}
          />
        </Box>
        <Button
          data-test="close"
          onClick={() => {
            onClose?.();
            closeModal?.();
          }}
        >
          {gettext('Cancel')}
        </Button>
        <Button
          data-test="Continue"
          variant="primary"
          autoFocus
          onClick={() => {
            const postFormData = new FormData();
            postFormData.append(
              'pref_data',
              JSON.stringify([
                {
                  name: 'view_edit_promotion_warning',
                  value: !saveUserChoice,
                  module: 'sqleditor',
                },
              ])
            );
            onContinue?.(postFormData);
            closeModal?.();
          }}
        >
          {gettext('Continue')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

ConfirmPromotionContent.propTypes = {
  closeModal: PropTypes.func,
  text: PropTypes.node,
  onContinue: PropTypes.func,
  onClose: PropTypes.func,
};
