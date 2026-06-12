import { describe, it, expect, vi } from 'vitest';
import { h } from 'preact';
import { fireEvent, render, screen } from '@testing-library/preact';
import { Router } from 'wouter-preact';
import { SidebarNav } from './SidebarNav.js';

function mount(props = {}) {
  return render(h(Router, {}, h(SidebarNav, props)));
}

describe('SidebarNav grouping', () => {
  it('groups the work surfaces under WORK TYPES and reference under DATA', () => {
    mount();
    expect(screen.getByText('WORK TYPES')).toBeTruthy();
    expect(screen.getByText('DATA')).toBeTruthy();
    expect(screen.getByText('Accounts Payable')).toBeTruthy();
    expect(screen.queryByText('Procurement')).toBeNull();
    expect(screen.queryByText('Builder')).toBeNull();
    // Reference surfaces.
    for (const label of ['Vendors', 'Reports', 'Audit log']) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    // No stray "Workflows" item (the builder is labeled "Builder").
    expect(screen.queryByText('Workflows')).toBeNull();
  });

  it('orders WORK TYPES before DATA', () => {
    mount();
    const labels = Array.from(document.querySelectorAll('.cl-sidebar-group-label'))
      .map((n) => n.textContent);
    expect(labels.indexOf('WORK TYPES')).toBeGreaterThanOrEqual(0);
    expect(labels.indexOf('WORK TYPES')).toBeLessThan(labels.indexOf('DATA'));
  });

  it('keeps secondary admin destinations out of the sidebar rail', () => {
    mount();
    expect(screen.getByText('Connections')).toBeTruthy();
    expect(screen.getByText('Approval rules')).toBeTruthy();
    expect(screen.getByText('Settings')).toBeTruthy();
    expect(screen.queryByText('API keys')).toBeNull();
    expect(screen.queryByText('Plan')).toBeNull();
    expect(screen.queryByText('Status')).toBeNull();
  });

  it('keeps collapsed rail links accessible with labels and titles', () => {
    mount({ collapsed: true });

    const home = screen.getByLabelText('Home');
    expect(home.getAttribute('title')).toBe('Home');
    expect(screen.getByLabelText('Expand sidebar')).toBeTruthy();
    expect(document.querySelector('.cl-sidebar-brand-mark')).toBeTruthy();
  });

  it('calls the collapse toggle from the rail control', () => {
    const onToggleCollapse = vi.fn();
    mount({ onToggleCollapse });

    fireEvent.click(screen.getByLabelText('Collapse sidebar'));
    expect(onToggleCollapse).toHaveBeenCalledTimes(1);
  });
});
