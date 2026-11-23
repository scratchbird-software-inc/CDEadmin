/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {TextField} from '../cdeadmin_ui/primitives/Field';
import {isEmptyString} from '../validators';

export default function NamedRestoreContent({closeModal, onOK, setHeight}) {
  const containerRef = useRef();
  const firstEleRef = useRef();
  const [namedRestorePoint, setNamedRestorePoint] = useState('');

  const isOKDisabled = isEmptyString(namedRestorePoint);

  const submit = () => {
    if (isOKDisabled) return;
    const postFormData = new FormData();
    postFormData.append('value', namedRestorePoint);
    onOK?.(postFormData);
    closeModal();
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      firstEleRef.current?.focus();
    }, 275);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    setHeight?.(containerRef.current?.offsetHeight);
  }, [setHeight]);

  return (
    <ModalContent ref={containerRef}>
      <Box style={{flexGrow: 1, padding: 16}}>
        <Stack spacing={1.5}>
          <TextField
            ref={firstEleRef}
            label={gettext('Enter the name of the restore point to add')}
            value={namedRestorePoint}
            onChange={(e) => setNamedRestorePoint(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !isOKDisabled) {
                e.preventDefault();
                submit();
              }
            }}
          />
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
          disabled={isOKDisabled}
          onClick={submit}
        >
          {gettext('OK')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

NamedRestoreContent.propTypes = {
  closeModal: PropTypes.func,
  onOK: PropTypes.func,
  setHeight: PropTypes.func,
};
