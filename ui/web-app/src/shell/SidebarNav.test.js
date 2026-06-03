import { describe, it, expect } from 'vitest';
import { h } from 'preact';
import { render, screen } from '@testing-library/preact';
import { Router } from 'wouter-preact';
import { SidebarNav } from './SidebarNav.js';

function mount() {
  return render(h(Router, {}, h(SidebarNav, {})));
}

describe('SidebarNav grouping', () => {
  it('groups the work surfaces under WORKFLOWS and reference under DATA', () => {
    mount();
    expect(screen.getByText('WORKFLOWS')).toBeTruthy();
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

  it('orders WORKFLOWS before DATA', () => {
    mount();
    const labels = Array.from(document.querySelectorAll('.cl-sidebar-group-label'))
      .map((n) => n.textContent);
    expect(labels.indexOf('WORKFLOWS')).toBeGreaterThanOrEqual(0);
    expect(labels.indexOf('WORKFLOWS')).toBeLessThan(labels.indexOf('DATA'));
  });
});
