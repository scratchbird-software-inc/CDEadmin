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
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Banner} from '../../feedback/Indicators';
import {frameAddress, previewRequest} from './embeds';

const message = (error) => error?.message || String(error);

/**
 * A live preview of an enabled embed. The server mints a one-time token that
 * lives for a couple of minutes and lets this page (and only it) frame the
 * embed; the token is not shown and not kept. Each load asks for a new one.
 */
export default function EmbedPreview({client, embed, draft, onClose}) {
  const [texts, setTexts] = useState({});
  const [claimTexts, setClaimTexts] = useState({});
  const [problems, setProblems] = useState({});
  const [state, setState] = useState({status: 'idle', src: '', error: '', expiresIn: 0});
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const used = draft.parameters.filter((item) => item.mode !== 'off');
  const load = async () => {
    const request = previewRequest(draft, texts, claimTexts);
    setProblems(request.problems);
    if(Object.keys(request.problems).length) return;
    setState({status: 'loading', src: '', error: '', expiresIn: 0});
    try {
      const preview = await client.previewEmbed(embed.embed_id, {params: request.params, claims: request.claims});
      if(alive.current) {
        setState({status: 'ready', src: frameAddress(preview.frame_path, preview.token), error: '',
          expiresIn: preview.expires_in});
      }
    } catch(error) {
      if(alive.current) setState({status: 'error', src: '', error: message(error), expiresIn: 0});
    }
  };

  return <Box component="section" aria-label={gettext('Preview')}
    sx={{display: 'grid', gap: 0.75, border: '1px solid', borderColor: 'divider', p: 1}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
      <Box component="h4" sx={{m: 0, fontSize: '0.8125rem', flex: 1}}>{gettext('Preview of %s', embed.name)}</Box>
      <Button size="small" onClick={onClose}>{gettext('Close preview')}</Button>
    </Stack>
    <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('The preview signs a token for you that works once and for a short time. It runs the embed exactly as a viewer would see it.')}
    </Box>
    {(used.length > 0 || draft.claims.length > 0) && <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
      {used.map((item) => <TextField key={item.id} size="small" label={gettext('Value of %s', item.name)}
        value={texts[item.id] ?? ''} validationMessage={problems[item.id]} sx={{width: 190}}
        helperText={item.multiple ? gettext('Separate values with commas.') : undefined}
        onChange={(event) => setTexts({...texts, [item.id]: event.target.value})} />)}
      {draft.claims.map((claim) => <TextField key={claim.name} size="small"
        label={gettext('Claim %s', claim.name)} value={claimTexts[claim.name] ?? ''}
        validationMessage={problems[`claim.${claim.name}`]} sx={{width: 190}}
        onChange={(event) => setClaimTexts({...claimTexts, [claim.name]: event.target.value})} />)}
    </Stack>}
    <Stack direction="row"><Button intent="primary" loading={state.status === 'loading'} onClick={load}>
      {state.src ? gettext('Reload preview') : gettext('Load preview')}</Button></Stack>
    {state.status === 'error' && <Banner status="error">{state.error}</Banner>}
    {state.src && <Box component="iframe" title={gettext('Embed preview')} src={state.src}
      sandbox="allow-scripts allow-same-origin" referrerPolicy="no-referrer"
      sx={{width: '100%', height: 420, border: '1px solid', borderColor: 'divider'}} />}
    {state.src && <Box sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
      {gettext('This preview token expires in %s seconds; reload to get a new one.', state.expiresIn)}</Box>}
  </Box>;
}

EmbedPreview.propTypes = {
  client: PropTypes.object.isRequired, embed: PropTypes.object.isRequired, draft: PropTypes.object.isRequired,
  onClose: PropTypes.func.isRequired,
};
