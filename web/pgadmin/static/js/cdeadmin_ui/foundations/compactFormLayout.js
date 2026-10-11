// Short fields share columns; native editors and result panels keep a full row.
export const compactFormSx = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 24rem))',
  gap: 1, alignContent: 'start', alignItems: 'start', minWidth: 0,
  '& > *': {minWidth: 0, maxWidth: '100%'},
  '& > :not(.MuiTextField-root):not(.MuiFormControlLabel-root):not(.MuiButton-root)': {
    gridColumn: '1 / -1',
  },
  '& > .MuiTextField-root:has(textarea), & > .MuiTextField-root.MuiFormControl-fullWidth': {
    gridColumn: '1 / -1',
  },
  '& .MuiFormHelperText-root': {whiteSpace: 'normal', overflowWrap: 'anywhere'},
};
export const compactActionsSx = {
  display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 0.5,
  '& > .MuiAlert-root': {flexBasis: '100%'},
};
