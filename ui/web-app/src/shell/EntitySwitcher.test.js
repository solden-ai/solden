import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'preact';
import { cleanup, fireEvent, render, screen } from '@testing-library/preact';
import { EntitySwitcher } from './EntitySwitcher.js';

const useEntitiesMock = vi.hoisted(() => vi.fn());

vi.mock('./EntityContext.js', () => ({
  useEntities: useEntitiesMock,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('EntitySwitcher', () => {
  it('shows the workspace-wide entity scope even before entities are configured', () => {
    const setActiveEntityId = vi.fn();
    useEntitiesMock.mockReturnValue({
      entities: [],
      activeEntityId: null,
      setActiveEntityId,
      loading: false,
    });

    render(h(EntitySwitcher, {}));

    const trigger = screen.getByRole('button', { name: /entity all entities/i });
    expect(trigger).toBeTruthy();

    fireEvent.click(trigger);

    expect(screen.getByText('Aggregate view')).toBeTruthy();
    expect(screen.getByText('No legal entities configured')).toBeTruthy();
  });

  it('lets an operator scope the workspace to a configured entity', () => {
    const setActiveEntityId = vi.fn();
    useEntitiesMock.mockReturnValue({
      entities: [
        { id: 'ent-uk', name: 'Solden UK', code: 'UK' },
        { id: 'ent-us', name: 'Solden US', code: 'US' },
      ],
      activeEntityId: null,
      setActiveEntityId,
      loading: false,
    });

    render(h(EntitySwitcher, {}));

    fireEvent.click(screen.getByRole('button', { name: /entity all entities/i }));
    fireEvent.click(screen.getByText('Solden UK'));

    expect(setActiveEntityId).toHaveBeenCalledWith('ent-uk');
  });

  it('renders the active entity name in the topbar control', () => {
    useEntitiesMock.mockReturnValue({
      entities: [{ id: 'ent-ie', name: 'Solden Ireland', code: 'IE' }],
      activeEntityId: 'ent-ie',
      setActiveEntityId: vi.fn(),
      loading: false,
    });

    render(h(EntitySwitcher, {}));

    expect(screen.getByRole('button', { name: /entity solden ireland/i })).toBeTruthy();
  });
});
