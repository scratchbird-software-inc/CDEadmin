import pgAdmin from 'sources/pgadmin';
import {startFirebirdBrowserDownload} from '../../../pgadmin/static/js/Dialogs/firebirdBrowserDownload';

describe('Firebird browser-managed file transport', () => {
  it('submits authenticated form identities in the body and cleans up its frame', () => {
    const previous = pgAdmin.csrf_token;
    pgAdmin.csrf_token = 'test-csrf';
    const random = jest.spyOn(window.crypto, 'randomUUID').mockReturnValue('owned-frame');
    const payload = {session_id: 'owned-session', request: {download_id: 'owned-download'}};
    const submit = jest.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(function() {
      expect(this.getAttribute('method')).toBe('POST');
      expect(this.getAttribute('action')).not.toContain('owned-download');
      expect(this.elements.csrf_token.value).toBe('test-csrf');
      expect(JSON.parse(this.elements.payload.value)).toEqual(payload);
      expect(document.querySelector(`iframe[name="${this.target}"]`)).not.toBeNull();
    });
    try {
      const cleanup = startFirebirdBrowserDownload('/workspace', payload);
      expect(submit).toHaveBeenCalledTimes(1);
      expect(document.querySelector('form[target="firebird-download-owned-frame"]')).toBeNull();
      cleanup();
      expect(document.querySelector('iframe[name="firebird-download-owned-frame"]')).toBeNull();
      expect(() => startFirebirdBrowserDownload('https://other.invalid/', payload)).toThrow(/origin/);
      expect(submit).toHaveBeenCalledTimes(1);
    } finally {
      submit.mockRestore(); random.mockRestore(); pgAdmin.csrf_token = previous;
    }
  });
});
