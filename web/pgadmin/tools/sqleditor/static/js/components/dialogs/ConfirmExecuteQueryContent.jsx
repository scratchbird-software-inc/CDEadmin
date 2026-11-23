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
import gettext from 'sources/gettext';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../../../../../../static/js/cdeadmin_ui/primitives/Layout';
import {Button} from '../../../../../../static/js/cdeadmin_ui/primitives/Button';
import {Checkbox} from '../../../../../../static/js/cdeadmin_ui/primitives/Choice';
import CodeMirror from '../../../../../../static/js/components/ReactCodeMirror';

export default function ConfirmExecuteQueryContent({
  onContinue,
  onClose,
  closeModal,
  text,
}) {
  const [saveUserChoice, setSaveUserChoice] = useState(false);

  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16, overflow: 'auto'}}>
        <Stack spacing={1}>
          <div style={{fontWeight: 600}}>
            {gettext('Do you want to run this query -')}
          </div>
          <div
            style={{
              border: '1px solid var(--sr-border, rgba(128,128,128,0.28))',
              borderRadius: 6,
              maxHeight: 500,
              overflowY: 'auto',
            }}
          >
            <CodeMirror value={text || ''} className="textarea" readonly />
          </div>
        </Stack>
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
                  name: 'underlined_query_execute_warning',
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

ConfirmExecuteQueryContent.propTypes = {
  closeModal: PropTypes.func,
  text: PropTypes.string,
  onContinue: PropTypes.func,
  onClose: PropTypes.func,
};
