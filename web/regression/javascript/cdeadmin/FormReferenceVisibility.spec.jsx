/////////////////////////////////////////////////////////////
// FormReference QA visibility gate verification.
/////////////////////////////////////////////////////////////

import {act, render, screen} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import FormReference, {
  readShowFormReferences,
  setShowFormReferences,
} from 'sources/cdeadmin_ui/navigation/FormReference';

describe('FormReference QA visibility gate', () => {
  const ThemedFormReference = withTheme(FormReference);

  beforeEach(() => {
    delete window.__SCRATCHROBIN_SHOW_FORM_REFS;
    window.localStorage.clear();
  });

  afterEach(() => {
    delete window.__SCRATCHROBIN_SHOW_FORM_REFS;
    window.localStorage.clear();
  });

  it('preserves DOM data attributes and accessibility label while visually hiding SR-F-* text by default', () => {
    expect(readShowFormReferences()).toBe(false);
    const {container} = render(
      <ThemedFormReference reference="SR-F-099999">
        <div>Form Body</div>
      </ThemedFormReference>
    );
    const wrapper = container.querySelector('[data-form-reference="SR-F-099999"]');
    expect(wrapper).toBeInTheDocument();
    expect(wrapper).toHaveAttribute('data-sr-form-ref', 'SR-F-099999');

    const badge = screen.getByLabelText('Form reference');
    expect(badge).toHaveTextContent('SR-F-099999');
    expect(badge).toHaveStyle({
      position: 'absolute',
      width: '1px',
      height: '1px',
      overflow: 'hidden',
    });
  });

  it('reveals and hides the visible monospace badge live via setShowFormReferences()', () => {
    render(<ThemedFormReference reference="SR-F-099999" />);
    const badge = screen.getByLabelText('Form reference');
    expect(badge).toHaveStyle({position: 'absolute', width: '1px'});

    act(() => {
      setShowFormReferences(true);
    });
    expect(readShowFormReferences()).toBe(true);
    expect(badge).toHaveStyle({display: 'block'});

    act(() => {
      setShowFormReferences(false);
    });
    expect(readShowFormReferences()).toBe(false);
    expect(badge).toHaveStyle({position: 'absolute', width: '1px'});
  });
});
