import { describe, expect, it, vi } from 'vitest';
import {
  ACCOUNTS_PAYABLE_ROUTE,
  accountPayableRecordPath,
  accountsPayablePath,
  navigateToRecordDetail,
  resolveRecordRouteId,
} from './record-route.js';

describe('record-route', () => {
  it('uses Accounts Payable as the canonical workspace route', () => {
    expect(ACCOUNTS_PAYABLE_ROUTE).toBe('/accounts-payable');
    expect(accountsPayablePath()).toBe('/accounts-payable');
    expect(accountsPayablePath('scope=approvals')).toBe('/accounts-payable?scope=approvals');
    expect(accountPayableRecordPath('AP 1')).toBe('/accounts-payable/AP%201');
  });

  it('navigates record details through the canonical route', () => {
    const navigate = vi.fn();

    expect(navigateToRecordDetail(navigate, 'AP-1')).toBe(true);

    expect(navigate).toHaveBeenCalledWith('/accounts-payable/AP-1');
  });

  it('resolves Accounts Payable hashes', () => {
    expect(resolveRecordRouteId({}, '#/accounts-payable/AP-2')).toBe('AP-2');
  });
});
