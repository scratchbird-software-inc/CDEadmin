/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import url_for from 'sources/url_for';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box} from '../cdeadmin_ui/primitives/Layout';
import {Button, IconButton} from '../cdeadmin_ui/primitives/Button';

export default function UrlDialogContent({url, helpFile, onClose}) {
  return (
    <ModalContent>
      <Box style={{flexGrow: 1, minHeight: 0}}>
        <iframe
          src={url}
          title={gettext('Help content')}
          width="100%"
          height="100%"
          style={{border: 0}}
          onLoad={(e) => {
            e.target?.contentWindow?.focus();
          }}
        />
      </Box>
      <ModalFooter>
        <Box style={{marginRight: 'auto'}}>
          <IconButton
            data-test={'help-' + helpFile}
            label={gettext('Help')}
            onClick={() => {
              const _url = url_for('help.static', {filename: helpFile});
              window.open(_url, 'pgadmin_help');
            }}
          >
            ?
          </IconButton>
        </Box>
        <Button
          data-test="close"
          onClick={() => {
            onClose();
          }}
        >
          {gettext('Close')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

UrlDialogContent.propTypes = {
  url: PropTypes.string,
  helpFile: PropTypes.string,
  onClose: PropTypes.func,
};
