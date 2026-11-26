import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import {OperationDialog, makePost} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {refusalFieldErrors, refusalMessage, refusalOf} from '../../../pgadmin/static/js/cdeadmin_ui/objects/refusals';
import {loadEngineBundle} from './familyFixtures';

const GENERIC = 'The operation was refused before dispatch. Review the indicated fields or create a new plan.';
const refusal = (errors, reference = '0123456789abcdef') => ({code: 'VISUAL_ADMIN_INVALID_DRAFT', errors,
  native_dispatched: false, automatic_retry: false, ...(reference ? {reference} : {})});
const rejected = (data) => Object.assign(new Error('Request failed with status code 422'),
  {response: {status: 422, data: {success: 0, errormsg: GENERIC, info: 'VISUAL_ADMIN_INVALID_DRAFT', data}}});

describe('refusal reasons (Decision 22)', () => {
  it('shows the catalog sentence for each reason and the reference, and the generic sentence for an uncatalogued one', () => {
    const catalogued = refusal([{field_id: 'database', code: 'database_not_chosen', message: 'Choose the database this runs in.'}]);
    expect(refusalMessage(catalogued, GENERIC)).toBe('Choose the database this runs in. Reference: 0123456789abcdef');
    const plain = refusal([{field_id: null, code: 'native_review_refused'}], null);
    expect(refusalMessage(plain, GENERIC)).toBe(GENERIC);
    expect(refusalMessage(refusal([{field_id: null, code: 'native_review_refused'}]), GENERIC))
      .toBe(`${GENERIC} Reference: 0123456789abcdef`);
  });

  it('says each distinct sentence once and names the fields that have one', () => {
    const same = refusal([
      {field_id: 'a', code: 'c', message: 'Same.'}, {field_id: 'b', code: 'c', message: 'Same.'},
      {field_id: 'x', code: 'u'}, {field_id: null, code: 'c', message: 'No field.'}], null);
    expect(refusalMessage(same, GENERIC)).toBe('Same. No field.');
    expect(refusalFieldErrors({data: {refusal: same}})).toEqual({a: 'Same.', b: 'Same.'});
    expect(refusalFieldErrors(new Error('x'))).toEqual({});
    expect(refusalOf({data: {refusal: 'x'}})).toBeNull();
  });

  describe('makePost', () => {
    it('carries the refusal on the error and puts the reason in its message', async () => {
      const data = {refusal: refusal([{field_id: 'database', code: 'database_not_chosen', message: 'Choose the database this runs in.'}])};
      const api = {post: jest.fn(async () => { throw rejected(data); })};
      const error = await makePost(api, '/ws', undefined)({action: 'visual_admin_plan', request: {}}).catch((e) => e);
      expect(error.message).toBe('Choose the database this runs in. Reference: 0123456789abcdef');
      expect(error.data.refusal.errors[0]).toMatchObject({field_id: 'database', code: 'database_not_chosen'});
    });

    it('keeps the server sentence, with the reference, for a refusal with no catalog text', async () => {
      const data = {refusal: refusal([{field_id: null, code: 'native_review_refused'}])};
      const api = {post: jest.fn(async () => { throw rejected(data); })};
      const error = await makePost(api, '/ws', undefined)({action: 'visual_admin_plan', request: {}}).catch((e) => e);
      expect(error.message).toBe(`${GENERIC} Reference: 0123456789abcdef`);
    });

    it('leaves any other failure as it was', async () => {
      const api = {post: jest.fn(async () => { throw Object.assign(new Error('x'), {response: {status: 400, data: {errormsg: 'Plain failure'}}}); })};
      const error = await makePost(api, '/ws', undefined)({action: 'visual_admin_plan', request: {}}).catch((e) => e);
      expect(error.message).toBe('Plain failure');
    });
  });

  describe('OperationDialog', () => {
    const grant = loadEngineBundle('firebird').kinds.privilege.operations.find((op) => op.operation_id === 'grant');
    const fixedValues = {privilege_scope: 'object', object_type: 'TABLE', object_name: 'ORDERS', privileges: ['SELECT']};
    const message = 'Use a name that exists, for example APP_USER.';

    it('marks the field the provider refused with the catalog sentence, and clears it when the field is edited', async () => {
      const data = {refusal: refusal([{field_id: 'principal', code: 'unknown_principal', message}])};
      const plan = jest.fn(async () => { throw Object.assign(new Error(`${message} Reference: 0123456789abcdef`), {data}); });
      render(<Theme><OperationDialog open operation={grant} targetName="ORDERS" fixedValues={fixedValues}
        plan={plan} apply={async () => ({})} onClose={() => {}} /></Theme>);
      fireEvent.change(screen.getByLabelText(/Grantee name/), {target: {value: 'NOBODY'}});
      await waitFor(() => expect(screen.getByRole('button', {name: 'Preview'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button', {name: 'Preview'}));
      // the banner and the field both carry the reason
      await waitFor(() => expect(screen.getAllByText(new RegExp(message.replace(/[.]/g, '\\.'))).length).toBeGreaterThanOrEqual(2));
      expect(screen.getByText(/Reference: 0123456789abcdef/)).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText(/Grantee name/), {target: {value: 'APP_USER'}});
      await waitFor(() => expect(screen.queryAllByText(new RegExp(message.replace(/[.]/g, '\\.'))).length).toBe(0));
    });

    const refusedPlan = () => jest.fn(async () => {
      throw Object.assign(new Error(`${message} Reference: 0123456789abcdef`),
        {data: {refusal: refusal([{field_id: 'principal', code: 'unknown_principal', message}])}});
    });
    const open = async (props) => {
      render(<Theme><OperationDialog open operation={grant} targetName="ORDERS" fixedValues={fixedValues}
        plan={refusedPlan()} apply={async () => ({})} onClose={() => {}} {...props} /></Theme>);
      fireEvent.change(screen.getByLabelText(/Grantee name/), {target: {value: 'NOBODY'}});
      await waitFor(() => expect(screen.getByRole('button', {name: 'Preview'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button', {name: 'Preview'}));
      await screen.findByText(/Reference: 0123456789abcdef/);
    };

    it('offers the full reason only on request and shows what the server returns', async () => {
      const lookup = jest.fn(async () => ({reference: '0123456789abcdef', message: 'the provider said so'}));
      await open({reasonLookup: lookup});
      expect(lookup).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('button', {name: 'Show reason'}));
      expect(await screen.findByText('the provider said so')).toBeInTheDocument();
      expect(lookup).toHaveBeenCalledWith('0123456789abcdef');
    });

    it('says so when the server will not show the reason, and offers nothing without a lookup', async () => {
      const lookup = jest.fn(async () => { throw new Error('You are not allowed to read the reasons for refused operations.'); });
      await open({reasonLookup: lookup});
      fireEvent.click(screen.getByRole('button', {name: 'Show reason'}));
      expect(await screen.findByText(/not allowed to read the reasons/)).toBeInTheDocument();
    });

    it('has no Show reason button when the caller gives no lookup', async () => {
      await open({});
      expect(screen.queryByRole('button', {name: 'Show reason'})).not.toBeInTheDocument();
    });
  });
});
