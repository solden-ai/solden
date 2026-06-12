/**
 * Reports page for the workspace control center.
 *
 * The page exposes a fixed set of operational reports with shared filters,
 * summary metrics, inline charts, breakdown tables, and scheduled delivery.
 */
import { h } from 'preact';
import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import htm from 'htm';
import {
  formatAmount,
  getExceptionLabel,
  humanizeSnakeText,
} from '../../utils/formatters.js';

const html = htm.bind(h);


// ─── Constants ──────────────────────────────────────────────────────

const REPORTS = [
  {
    id: 'volume',
    label: 'Volume',
    endpoint: '/api/workspace/reports/volume',
    csvEndpoint: '/api/workspace/reports/volume.csv',
    pdfEndpoint: '/api/workspace/reports/volume.pdf',
    description: 'Invoice count and spend by period, entity, and vendor.',
    summaryShape: 'volume',
    seriesShape: 'volume',
    breakdownShape: 'volume_vendors',
    supportsPeriod: true,
  },
  {
    id: 'agent_performance',
    label: 'Agent outcomes',
    endpoint: '/api/workspace/reports/agent-performance',
    csvEndpoint: '/api/workspace/reports/agent-performance.csv',
    pdfEndpoint: '/api/workspace/reports/agent-performance.pdf',
    description: 'Work handled without intervention, exception rate, and confidence trend.',
    summaryShape: 'agent_performance',
    seriesShape: 'agent_performance',
    breakdownShape: null,
    supportsPeriod: true,
  },
  {
    id: 'cycle_time',
    label: 'Cycle time',
    endpoint: '/api/workspace/reports/cycle-time',
    csvEndpoint: '/api/workspace/reports/cycle-time.csv',
    pdfEndpoint: '/api/workspace/reports/cycle-time.pdf',
    description: 'Time from invoice receipt to ERP post across posted records.',
    summaryShape: 'cycle_time',
    seriesShape: 'cycle_time',
    breakdownShape: 'cycle_time_entities',
    supportsPeriod: true,
  },
  {
    id: 'exception_breakdown',
    label: 'Exceptions',
    endpoint: '/api/workspace/reports/exception-breakdown',
    csvEndpoint: '/api/workspace/reports/exception-breakdown.csv',
    pdfEndpoint: '/api/workspace/reports/exception-breakdown.pdf',
    description: 'Where work is getting blocked and which blockers are rising.',
    summaryShape: 'exception_breakdown',
    seriesShape: 'exception_breakdown',
    breakdownShape: 'exception_codes',
    supportsPeriod: true,
  },
  {
    id: 'vendor_quality',
    label: 'Vendor quality',
    endpoint: '/api/workspace/reports/vendor-quality',
    csvEndpoint: '/api/workspace/reports/vendor-quality.csv',
    pdfEndpoint: '/api/workspace/reports/vendor-quality.pdf',
    description: 'Vendor relationships ranked by exception rate, with low-volume noise filtered out.',
    summaryShape: 'vendor_quality',
    seriesShape: null,
    breakdownShape: 'vendor_quality',
    supportsPeriod: false,
  },
];

const PERIOD_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];


// ─── Top-level page ─────────────────────────────────────────────────

export default function ReportsPage({ api, orgId, toast }) {
  const [activeId, setActiveId] = useState(REPORTS[0].id);
  const [period, setPeriod] = useState('weekly');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [entityId, setEntityId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const activeReport = useMemo(
    () => REPORTS.find((r) => r.id === activeId) || REPORTS[0],
    [activeId],
  );

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (activeReport.supportsPeriod && period) params.set('period', period);
    if (from) params.set('from', from);
    if (to) params.set('to', to);
    if (entityId) params.set('entity_id', entityId);
    return params.toString();
  }, [activeReport.supportsPeriod, period, from, to, entityId]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${activeReport.endpoint}${queryString ? `?${queryString}` : ''}`;
      const resp = await api(url);
      setData({
        reportId: activeReport.id,
        queryString,
        payload: resp,
      });
    } catch (exc) {
      setError(String(exc?.message || exc || 'Failed to load report'));
    } finally {
      setLoading(false);
    }
  }, [api, activeReport.endpoint, activeReport.id, queryString]);

  useEffect(() => { loadReport(); }, [loadReport]);

  const visibleData = data?.reportId === activeReport.id && data?.queryString === queryString
    ? data.payload
    : null;

  const downloadCsv = useCallback(() => {
    const url = `${activeReport.csvEndpoint}${queryString ? `?${queryString}` : ''}`;
    // Browser handles the download via Content-Disposition.
    window.location.href = url;
    toast(`Preparing ${activeReport.label} CSV…`, 'info');
  }, [activeReport, queryString, toast]);

  const downloadPdf = useCallback(() => {
    if (!activeReport.pdfEndpoint) return;
    const url = `${activeReport.pdfEndpoint}${queryString ? `?${queryString}` : ''}`;
    window.location.href = url;
    toast(`Preparing ${activeReport.label} PDF…`, 'info');
  }, [activeReport, queryString, toast]);

  return html`
    <div class="cl-reports">
      <header class="cl-reports-header">
        <h1>Reports</h1>
        <p class="cl-reports-sub">
          Operating reports for AP volume, cycle time, exceptions, vendor quality, and agent outcomes.
        </p>
      </header>

      <nav class="cl-reports-tabs" role="tablist" aria-label="Report tabs">
        ${REPORTS.map((report) => html`
          <button
            key=${report.id}
            role="tab"
            aria-selected=${activeId === report.id}
            class=${`cl-reports-tab ${activeId === report.id ? 'is-active' : ''}`}
            onClick=${() => setActiveId(report.id)}
          >${report.label}</button>
        `)}
      </nav>

      <p class="cl-reports-description">${activeReport.description}</p>

      <${FilterBar}
        period=${period}
        from=${from}
        to=${to}
        entityId=${entityId}
        showPeriod=${activeReport.supportsPeriod}
        onPeriod=${setPeriod}
        onFrom=${setFrom}
        onTo=${setTo}
        onEntity=${setEntityId}
        onExport=${downloadCsv}
        onExportPdf=${downloadPdf}
        busy=${loading}
      />

      ${loading && !visibleData ? html`<${LoadingState} />` : null}
      ${error ? html`<${ErrorState} message=${error} onRetry=${loadReport} />` : null}
      ${visibleData && !loading ? html`
        <${ReportContent}
          report=${activeReport}
          data=${visibleData}
        />
      ` : null}

      <${SubscriptionsPanel}
        api=${api}
        toast=${toast}
        report=${activeReport}
        params=${{ period, from, to, entityId }}
      />
    </div>
  `;
}


// ─── Filter bar ─────────────────────────────────────────────────────

function FilterBar({
  period, from, to, entityId, showPeriod,
  onPeriod, onFrom, onTo, onEntity,
  onExport, onExportPdf, busy,
}) {
  return html`
    <section class="cl-reports-filter-bar" aria-label="Report filters">
      ${showPeriod ? html`
        <label class="cl-reports-filter">
          <span class="cl-reports-filter-label">Period</span>
          <select value=${period} onChange=${(e) => onPeriod(e.target.value)} disabled=${busy}>
            ${PERIOD_OPTIONS.map((opt) => html`
              <option value=${opt.value} key=${opt.value}>${opt.label}</option>`)}
          </select>
        </label>
      ` : null}
      <label class="cl-reports-filter">
        <span class="cl-reports-filter-label">From</span>
        <input type="date" value=${from?.slice(0, 10) || ''}
          onChange=${(e) => onFrom(e.target.value ? `${e.target.value}T00:00:00+00:00` : '')}
          disabled=${busy} />
      </label>
      <label class="cl-reports-filter">
        <span class="cl-reports-filter-label">To</span>
        <input type="date" value=${to?.slice(0, 10) || ''}
          onChange=${(e) => onTo(e.target.value ? `${e.target.value}T23:59:59+00:00` : '')}
          disabled=${busy} />
      </label>
      <label class="cl-reports-filter">
        <span class="cl-reports-filter-label">Entity</span>
        <input type="text" placeholder="All entities" value=${entityId}
          onChange=${(e) => onEntity(e.target.value)}
          disabled=${busy} />
      </label>
      <div class="cl-reports-filter-actions" aria-label="Report exports">
        <button class="btn btn-secondary cl-reports-export" onClick=${onExport} disabled=${busy}>
          CSV
        </button>
        ${onExportPdf ? html`
          <button class="btn btn-secondary cl-reports-export" onClick=${onExportPdf} disabled=${busy}>
            PDF
          </button>
        ` : null}
      </div>
    </section>
  `;
}


// ─── States ─────────────────────────────────────────────────────────

function LoadingState() {
  return html`
    <div class="cl-reports-loading" role="status" aria-live="polite">
      <div class="cl-reports-skeleton cl-reports-skeleton-summary"></div>
      <div class="cl-reports-skeleton cl-reports-skeleton-chart"></div>
      <div class="cl-reports-skeleton cl-reports-skeleton-table"></div>
    </div>
  `;
}

function ErrorState({ message, onRetry }) {
  return html`
    <div class="cl-reports-error" role="alert">
      <h3>Couldn't load this report</h3>
      <p>${message}</p>
      <button class="btn btn-primary" onClick=${onRetry}>Try again</button>
    </div>
  `;
}


// ─── Report content (dispatched by report id) ──────────────────────

function ReportContent({ report, data }) {
  const summary = data.summary || {};
  const series = Array.isArray(data.series) ? data.series : [];
  const breakdown = Array.isArray(data.breakdown) ? data.breakdown : [];

  const isEmpty = isReportEmpty(report.id, summary, series, breakdown);

  if (isEmpty) {
    return html`
      <section class="cl-reports-empty">
        <h3>${emptyTitleFor(report.id)}</h3>
        <p>${emptyCopyFor(report.id)}</p>
      </section>
    `;
  }

  return html`
    <section class="cl-reports-body">
      <${SummaryStrip} report=${report} summary=${summary} />
      ${series.length > 0 ? html`
        <${TimeSeriesChart} report=${report} series=${series} />
      ` : null}
      ${breakdown.length > 0 ? html`
        <${BreakdownTable} report=${report} breakdown=${breakdown} />
      ` : null}
    </section>
  `;
}


// ─── Summary strip ─────────────────────────────────────────────────

function SummaryStrip({ report, summary }) {
  const cells = summaryCellsFor(report.id, summary);
  if (cells.length === 0) return null;

  return html`
    <section class="cl-reports-summary-strip" aria-label="Summary">
      ${cells.map((cell) => html`
        <div class="cl-reports-summary-cell" key=${cell.label}>
          <span class="cl-reports-summary-label">${cell.label}</span>
          <span class=${`cl-reports-summary-value ${cell.tone ? `cl-reports-summary-${cell.tone}` : ''}`}>
            ${cell.value}
          </span>
          ${cell.sub ? html`<span class="cl-reports-summary-sub">${cell.sub}</span>` : null}
        </div>
      `)}
    </section>
  `;
}

function summaryCellsFor(reportId, s) {
  switch (reportId) {
    case 'volume':
      return [
        { label: 'Total invoices', value: s.total_invoices ?? 0 },
        {
          label: 'Total amount',
          value: formatAmount(s.total_amount ?? 0, s.currency),
        },
        { label: 'Vendors', value: formatInteger(s.distinct_vendors ?? 0) },
      ];
    case 'agent_performance':
      return [
        {
          label: 'Handled automatically',
          value: pct(s.auto_resolution_rate),
          tone: rateColor(s.auto_resolution_rate, true),
        },
        {
          label: 'Exception rate',
          value: pct(s.exception_rate),
          tone: rateColor(s.exception_rate, false),
        },
        {
          label: 'Avg confidence',
          value: s.avg_confidence != null ? pct(s.avg_confidence) : '—',
        },
        { label: 'Records reviewed', value: formatInteger(s.sample_size ?? 0) },
      ];
    case 'cycle_time':
      return [
        {
          label: 'Average days',
          value: s.avg_cycle_days != null ? `${s.avg_cycle_days.toFixed(1)}d` : '—',
        },
        {
          label: 'p50 days',
          value: s.p50_cycle_days != null ? `${s.p50_cycle_days.toFixed(1)}d` : '—',
        },
        {
          label: 'p90 days',
          value: s.p90_cycle_days != null ? `${s.p90_cycle_days.toFixed(1)}d` : '—',
        },
        { label: 'Posted records', value: formatInteger(s.posted_count ?? 0) },
      ];
    case 'exception_breakdown':
      return [
        { label: 'Total blockers', value: formatInteger(s.total_exceptions ?? 0) },
        { label: 'Blocker types', value: formatInteger(s.distinct_codes ?? 0) },
        {
          label: 'Top blocker',
          value: s.top_code ? formatExceptionText(s.top_code) : '—',
          sub: s.top_code_count ? `${formatInteger(s.top_code_count)} occurrence${Number(s.top_code_count) === 1 ? '' : 's'}` : null,
        },
      ];
    case 'vendor_quality':
      return [
        { label: 'Vendors ranked', value: formatInteger(s.ranked_vendor_count ?? 0) },
        {
          label: 'Avg exception rate',
          value: pct(s.avg_exception_rate),
          tone: rateColor(s.avg_exception_rate, false),
        },
        {
          label: 'Worst vendor',
          value: s.worst_vendor || '—',
          sub: s.worst_exception_rate != null ? pct(s.worst_exception_rate) : null,
        },
        {
          label: 'Minimum invoices',
          value: formatInteger(s.min_invoices_floor ?? 3),
          sub: 'ranking floor',
        },
      ];
    default:
      return [];
  }
}


// ─── Time-series chart ──────────────────────────────────────────────

function TimeSeriesChart({ report, series }) {
  const valueKey = chartValueKeyFor(report.id);
  if (!valueKey) return null;

  const values = series.map((row) => Number(row[valueKey] || 0));
  const max = Math.max(...values, 0);
  const safeMax = max > 0 ? max : 1;
  const valueLabel = chartValueLabelFor(report.id);
  const labelEvery = values.length <= 7 ? 1 : Math.ceil(values.length / 5);
  const yTicks = [safeMax, safeMax / 2, 0];

  return html`
    <section class="cl-reports-chart-card">
      <header class="cl-reports-chart-head">
        <h3>${valueLabel} over time</h3>
        <span class="cl-reports-chart-meta">${series.length} buckets</span>
      </header>
      <div
        class="cl-reports-chart"
        role="img"
        aria-label=${`${valueLabel} time series`}
      >
        <div class="cl-reports-chart-y-axis" aria-hidden="true">
          ${yTicks.map((tick) => html`
            <span key=${tick}>${formatChartValue(report.id, tick)}</span>
          `)}
        </div>
        <div class="cl-reports-chart-plot" style=${{ '--bucket-count': values.length }}>
          <div class="cl-reports-chart-grid" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div class="cl-reports-chart-bars">
            ${values.map((v, idx) => {
              const barHeight = v > 0 ? Math.max(4, (v / safeMax) * 88) : 0;
              const showBucket = idx === 0 || idx === values.length - 1 || idx % labelEvery === 0;
              const bucketLabel = chartBucketLabel(series[idx].bucket);

              return html`
                <div
                  key=${idx}
                  class="cl-reports-chart-bucket"
                  style=${{ '--bar-height': `${barHeight}%` }}
                  title=${`${series[idx].bucket}: ${formatChartValue(report.id, v)}`}
                >
                  <span class="cl-reports-chart-bar-area">
                    ${v > 0 ? html`
                      <span class="cl-reports-chart-value">${formatChartValue(report.id, v)}</span>
                    ` : null}
                    <span class="cl-reports-chart-bar"></span>
                  </span>
                  ${showBucket ? html`
                    <span class="cl-reports-chart-x-label">${bucketLabel}</span>
                  ` : html`<span class="cl-reports-chart-x-label" aria-hidden="true"></span>`}
                </div>
              `;
            })}
          </div>
        </div>
      </div>
    </section>
  `;
}

function chartBucketLabel(bucket) {
  const text = String(bucket || '');
  const compactWeek = text.match(/^(\d{4})-W(\d{2})$/);
  if (compactWeek) return `W${compactWeek[2]}`;

  const compactDate = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (compactDate) return `${compactDate[2]}/${compactDate[3]}`;

  return text;
}

function chartValueKeyFor(reportId) {
  switch (reportId) {
    case 'volume': return 'invoice_count';
    case 'agent_performance': return 'auto_resolution_rate';
    case 'cycle_time': return 'avg_cycle_days';
    case 'exception_breakdown': return 'total_exceptions';
    default: return null;
  }
}

function chartValueLabelFor(reportId) {
  switch (reportId) {
    case 'volume': return 'Invoice count';
    case 'agent_performance': return 'Handled automatically';
    case 'cycle_time': return 'Average days to post';
    case 'exception_breakdown': return 'Blockers';
    default: return '';
  }
}

function formatChartValue(reportId, v) {
  if (reportId === 'agent_performance') return pct(v);
  if (reportId === 'cycle_time') return `${v.toFixed(1)}d`;
  return String(Math.round(v));
}


// ─── Breakdown table ───────────────────────────────────────────────

function BreakdownTable({ report, breakdown }) {
  const cols = breakdownColumnsFor(report.id);
  if (cols.length === 0) return null;

  const title = breakdownTitleFor(report.id);

  return html`
    <section class="cl-reports-table-card">
      <header class="cl-reports-chart-head">
        <h3>${title}</h3>
        <span class="cl-reports-chart-meta">${breakdown.length} rows</span>
      </header>
      <div class="cl-reports-mobile-rows" role="list">
        ${breakdown.map((row, idx) => html`
          <div class="cl-reports-mobile-row" role="listitem" key=${idx}>
            <div class="cl-reports-mobile-row-head">
              <strong>${formatBreakdownCell(report.id, cols[0].key, row[cols[0].key], row)}</strong>
              ${cols[1] ? html`<span>${formatBreakdownCell(report.id, cols[1].key, row[cols[1].key], row)}</span>` : null}
            </div>
            <dl>
              ${cols.slice(2).map((c) => html`
                <div key=${c.key}>
                  <dt>${c.label}</dt>
                  <dd>${formatBreakdownCell(report.id, c.key, row[c.key], row)}</dd>
                </div>
              `)}
            </dl>
          </div>
        `)}
      </div>
      <div class="cl-reports-table-wrap">
        <table class="cl-reports-table">
          <thead>
            <tr>
              ${cols.map((c) => html`<th class=${c.numeric ? 'cl-reports-num' : ''} key=${c.key}>${c.label}</th>`)}
            </tr>
          </thead>
          <tbody>
            ${breakdown.map((row, idx) => html`
              <tr key=${idx}>
                ${cols.map((c) => html`
                  <td class=${c.numeric ? 'cl-reports-num' : ''} key=${c.key}>
                    ${formatBreakdownCell(report.id, c.key, row[c.key], row)}
                  </td>`)}
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function breakdownColumnsFor(reportId) {
  switch (reportId) {
    case 'volume':
      return [
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'invoice_count', label: 'Invoices', numeric: true },
        { key: 'total_amount', label: 'Total', numeric: true },
      ];
    case 'cycle_time':
      return [
        { key: 'entity_id', label: 'Entity' },
        { key: 'avg_cycle_days', label: 'Avg days', numeric: true },
        { key: 'posted_count', label: 'Posted', numeric: true },
      ];
    case 'exception_breakdown':
      return [
        { key: 'exception_code', label: 'Blocker' },
        { key: 'count', label: 'Count', numeric: true },
        { key: 'share', label: 'Share', numeric: true },
      ];
    case 'vendor_quality':
      return [
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'total_invoices', label: 'Total', numeric: true },
        { key: 'exception_count', label: 'Exceptions', numeric: true },
        { key: 'exception_rate', label: 'Rate', numeric: true },
      ];
    default:
      return [];
  }
}

function breakdownTitleFor(reportId) {
  switch (reportId) {
    case 'volume': return 'Top vendors by amount';
    case 'cycle_time': return 'By entity';
    case 'exception_breakdown': return 'Blockers ranked';
    case 'vendor_quality': return 'Vendors ranked by exception rate';
    default: return 'Breakdown';
  }
}

function formatBreakdownCell(reportId, key, value, row) {
  if (value === null || value === undefined) return '—';
  if (key === 'total_amount') return formatAmount(value, row?.currency);
  if (key === 'invoice_count' || key === 'total_invoices' || key === 'exception_count' || key === 'posted_count' || key === 'count') {
    return formatInteger(value);
  }
  if (key === 'avg_cycle_days') {
    const days = Number(value);
    return Number.isNaN(days) ? '—' : `${days.toFixed(1)}d`;
  }
  if (key === 'share' || key === 'exception_rate') return pct(value);
  if (key === 'exception_code') return formatExceptionText(value);
  if (key === 'entity_id') {
    return row.entity_name || humanizeSnakeText(value);
  }
  return value;
}


// ─── Helpers ───────────────────────────────────────────────────────

function pct(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

function formatInteger(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return Math.round(n).toLocaleString();
}

function formatExceptionText(value) {
  const label = getExceptionLabel(value);
  return label
    .replace(/\bPo\b/g, 'PO')
    .replace(/\bErp\b/g, 'ERP');
}

function isReportEmpty(reportId, summary, series, breakdown) {
  if (series.length > 0 || breakdown.length > 0) return false;
  switch (reportId) {
    case 'volume':
      return Number(summary.total_invoices || 0) === 0;
    case 'agent_performance':
      return Number(summary.sample_size || 0) === 0;
    case 'cycle_time':
      return Number(summary.posted_count || 0) === 0;
    case 'exception_breakdown':
      return Number(summary.total_exceptions || 0) === 0;
    case 'vendor_quality':
      return Number(summary.ranked_vendor_count || 0) === 0;
    default:
      return true;
  }
}

function emptyTitleFor(reportId) {
  switch (reportId) {
    case 'cycle_time': return 'No posted records in this window';
    case 'exception_breakdown': return 'No blockers in this window';
    case 'vendor_quality': return 'No vendors meet the ranking floor';
    default: return 'No report data in this window';
  }
}

function emptyCopyFor(reportId) {
  switch (reportId) {
    case 'cycle_time':
      return 'Cycle time appears once records have both a receipt time and an ERP post time.';
    case 'exception_breakdown':
      return 'No exception codes were recorded for the selected period.';
    case 'vendor_quality':
      return 'Try widening the date range, or come back once more vendor invoices have flowed through.';
    default:
      return 'Try widening the date range, or come back after more AP records flow through.';
  }
}

function rateColor(rate, higherIsBetter) {
  if (rate === null || rate === undefined) return null;
  const n = Number(rate);
  if (Number.isNaN(n)) return null;
  if (higherIsBetter) {
    if (n >= 0.7) return 'success';
    if (n >= 0.4) return 'warning';
    return 'error';
  }
  if (n <= 0.1) return 'success';
  if (n <= 0.3) return 'warning';
  return 'error';
}


// ─── Subscriptions panel ───────────────────────────────────────────
//
// Per-report scheduled email subscriptions. The leader picks
// recipient + cadence; the backend handles the rest. Each
// subscription row supports pause / resume / delete inline so the
// leader doesn't have to leave the report to manage delivery.

function SubscriptionsPanel({ api, toast, report, params }) {
  const [subs, setSubs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [recipient, setRecipient] = useState('');
  const [cadence, setCadence] = useState('weekly');

  const loadSubs = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await api('/api/workspace/reports/subscriptions');
      const all = (resp && resp.subscriptions) || [];
      setSubs(all.filter((s) => s.report_type === report.id));
    } catch (exc) {
      // Non-fatal; just leave list empty.
      setSubs([]);
    } finally {
      setLoading(false);
    }
  }, [api, report.id]);

  useEffect(() => { loadSubs(); }, [loadSubs]);

  const onCreate = useCallback(async (e) => {
    e?.preventDefault?.();
    if (!recipient || !recipient.includes('@')) {
      toast('Enter a valid recipient email', 'error');
      return;
    }
    setCreating(true);
    try {
      // Build the same params the report page uses, so the email
      // delivers exactly what the operator currently sees.
      const subParams = {};
      if (report.supportsPeriod && params.period) subParams.period = params.period;
      if (params.from) subParams.from = params.from;
      if (params.to) subParams.to = params.to;
      if (params.entityId) subParams.entity_id = params.entityId;

      await api('/api/workspace/reports/subscriptions', {
        method: 'POST',
        body: JSON.stringify({
          report_type: report.id,
          cadence,
          recipient_email: recipient,
          params: subParams,
        }),
      });
      toast(`Subscribed ${recipient} to ${report.label} (${cadence}).`, 'success');
      setRecipient('');
      await loadSubs();
    } catch (exc) {
      toast(`Subscribe failed: ${String(exc?.message || exc)}`, 'error');
    } finally {
      setCreating(false);
    }
  }, [api, recipient, cadence, report, params, toast, loadSubs]);

  const onTogglePause = useCallback(async (sub) => {
    try {
      await api(`/api/workspace/reports/subscriptions/${sub.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ paused: !sub.paused_at }),
      });
      await loadSubs();
    } catch (exc) {
      toast(`Update failed: ${String(exc?.message || exc)}`, 'error');
    }
  }, [api, toast, loadSubs]);

  const onDelete = useCallback(async (sub) => {
    if (!window.confirm(`Stop sending the ${report.label} report to ${sub.recipient_email}?`)) {
      return;
    }
    try {
      await api(`/api/workspace/reports/subscriptions/${sub.id}`, {
        method: 'DELETE',
      });
      toast('Subscription removed.', 'success');
      await loadSubs();
    } catch (exc) {
      toast(`Delete failed: ${String(exc?.message || exc)}`, 'error');
    }
  }, [api, toast, loadSubs, report.label]);

  return html`
    <section class="cl-reports-subs-card">
      <header class="cl-reports-chart-head">
        <h3>Scheduled delivery</h3>
        <span class="cl-reports-chart-meta">${subs.length} active</span>
      </header>

      <form class="cl-reports-subs-form" onSubmit=${onCreate}>
        <label class="cl-reports-filter">
          <span class="cl-reports-filter-label">Recipient</span>
          <input
            type="email"
            placeholder="recipient@company.com"
            value=${recipient}
            onInput=${(e) => setRecipient(e.target.value)}
            disabled=${creating}
            required
          />
        </label>
        <label class="cl-reports-filter">
          <span class="cl-reports-filter-label">Cadence</span>
          <select value=${cadence} onChange=${(e) => setCadence(e.target.value)} disabled=${creating}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly (Mondays)</option>
            <option value="monthly">Monthly (1st)</option>
          </select>
        </label>
        <button type="submit" class="btn btn-primary cl-reports-subs-submit" disabled=${creating}>
          ${creating ? 'Subscribing…' : 'Subscribe'}
        </button>
      </form>

      ${loading ? html`
        <p class="cl-reports-subs-empty">Loading subscriptions…</p>
      ` : null}

      ${!loading && subs.length === 0 ? html`
        <p class="cl-reports-subs-empty">
          No scheduled delivery for this report yet.
        </p>
      ` : null}

      ${!loading && subs.length > 0 ? html`
        <ul class="cl-reports-subs-list">
          ${subs.map((sub) => html`
            <li key=${sub.id} class=${`cl-reports-subs-row ${sub.paused_at ? 'is-paused' : ''}`}>
              <div class="cl-reports-subs-row-main">
                <span class="cl-reports-subs-recipient">${sub.recipient_email}</span>
                <span class="cl-reports-subs-cadence">${cadenceLabel(sub.cadence)}</span>
                ${sub.paused_at ? html`<span class="cl-reports-chip cl-reports-chip-warning">paused</span>` : null}
                ${sub.failure_count > 0 ? html`
                  <span class="cl-reports-chip cl-reports-chip-error">
                    ${sub.failure_count} failure${sub.failure_count === 1 ? '' : 's'}
                  </span>` : null}
              </div>
              <div class="cl-reports-subs-row-meta">
                Next: ${formatNextDue(sub.next_due_at)}
                ${sub.last_delivered_at ? html` · last sent ${formatNextDue(sub.last_delivered_at)}` : null}
              </div>
              <div class="cl-reports-subs-row-actions">
                <button class="btn btn-tertiary btn-sm" onClick=${() => onTogglePause(sub)}>
                  ${sub.paused_at ? 'Resume' : 'Pause'}
                </button>
                <button class="btn btn-tertiary btn-sm" onClick=${() => onDelete(sub)}>
                  Remove
                </button>
              </div>
            </li>
          `)}
        </ul>
      ` : null}
    </section>
  `;
}

function cadenceLabel(cadence) {
  switch (cadence) {
    case 'daily': return 'Daily at 09:00 UTC';
    case 'weekly': return 'Weekly on Mondays';
    case 'monthly': return 'Monthly on the 1st';
    default: return cadence || '';
  }
}

function formatNextDue(iso) {
  if (!iso) return '—';
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
      hour12: false, timeZone: 'UTC',
    }) + ' UTC';
  } catch {
    return iso;
  }
}

// Reference SubscriptionsPanel so the bundler doesn't tree-shake it.
// (Component is referenced from the JSX above; this is just a JS hint.)
void SubscriptionsPanel;
