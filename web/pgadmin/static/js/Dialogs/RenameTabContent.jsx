/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import _ from 'lodash';
import {useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {TextField} from '../cdeadmin_ui/primitives/Field';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';

export default function RenameTabContent({panelId, panelDocker, closeModal}) {
  const containerRef = useRef();
  const panelData = useMemo(() => panelDocker.find(panelId), [panelDocker, panelId]);
  const initialTitle = panelData.internal?.isDirty
    ? panelData?.internal?.title.slice(0, -1)
    : panelData?.internal?.title;
  const [title, setTitle] = useState(initialTitle || '');

  const isValid = title.length !== 0;

  const onOkClick = () => {
    if (!isValid) return;
    if (panelData.internal.isDirty) {
      panelDocker.setTitle(panelId, `${title}*`);
    } else {
      panelDocker.setTitle(panelId, title);
    }
    if (_.isUndefined(panelData.internal.orig_title)) {
      panelDocker.setInternalAttrs(panelId, {
        orig_title: initialTitle,
      });
    }
    closeModal();
  };

  return (
    <ModalContent ref={containerRef}>
      <Box style={{flexGrow: 1, padding: 12}}>
        <Stack spacing={1}>
          <div style={{fontSize: '0.8125rem', color: 'var(--sr-text-muted)'}}>
            {gettext('Current')}: {initialTitle}
          </div>
          <TextField
            label={gettext('New tab title')}
            value={title}
            autoFocus
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && isValid) {
                e.preventDefault();
                onOkClick();
              }
            }}
          />
          {!isValid && <Banner tone="error">{gettext('Title cannot be empty')}</Banner>}
        </Stack>
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
          data-test="save"
          variant="primary"
          disabled={!isValid}
          onClick={onOkClick}
        >
          {gettext('OK')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

RenameTabContent.propTypes = {
  panelId: PropTypes.string,
  panelDocker: PropTypes.object,
  closeModal: PropTypes.func,
};
