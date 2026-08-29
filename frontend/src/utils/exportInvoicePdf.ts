import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { InvoiceDocument } from '../schemas/invoiceWorkspaceSchema';
import { formatMoneyInr, roundMoney } from './invoiceMoney';
import type { InvoiceWorkspaceTotals } from './invoiceTotals';
import { fetchBusinessPdfBranding } from './fetchBusinessPdfBranding';
import type { BankPaymentDetails } from '../schemas/billingSettingsSchema';
import { FALLBACK_COUNTRIES } from '../types/country';
import { numberToIndianWords } from './indianCurrency';
import { buildUpiPayUri, upiQrImageUrl } from './upiPay';

/** Classic invoice template palette (matches uploaded layout). */
const COLORS = {
  darkBlue: [46, 65, 114] as [number, number, number],
  lightBlue: [166, 201, 236] as [number, number, number],
  zebra: [242, 242, 242] as [number, number, number],
  metaFill: [245, 245, 245] as [number, number, number],
  border: [60, 60, 60] as [number, number, number],
  text: [30, 30, 30] as [number, number, number],
  muted: [90, 90, 90] as [number, number, number],
};

const MARGIN = 40;
const MIN_LINE_ROWS = 12;
const LOGO_MAX_W = 72;
const LOGO_MAX_H = 40;
const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

function countryLabel(iso2: string | undefined): string {
  const code = (iso2 || '').trim().toUpperCase();
  if (!code) return '';
  return FALLBACK_COUNTRIES.find(c => c.iso2 === code)?.name || code;
}

/** Format YYYY-MM-DD as DD-MMM-YYYY (e.g. 11-Aug-2026). */
function formatInvoiceDisplayDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((iso || '').trim());
  if (!m) return iso || '—';
  const monthIdx = Number(m[2]) - 1;
  const day = String(Number(m[3])).padStart(2, '0');
  const mon = MONTHS[monthIdx] || m[2];
  return `${day}-${mon}-${m[1]}`;
}

/** Sanitize a filename segment for common OS restrictions (keep spaces). */
function sanitizeFilenamePart(value: string, fallback: string): string {
  const cleaned = value
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .trim();
  return cleaned || fallback;
}

/**
 * `{InvoiceID}_{StudentID}_{StudentName}_{DD-MMM-YYYY}[_{Status}].pdf`
 * Drafts without a number use `DRAFT` (no status suffix).
 * Issued → `_Issued`; cancelled (void) → `_Cancelled`; archived → `_Archived`.
 */
export function buildInvoicePdfFilename(invoice: InvoiceDocument): string {
  const hasNumber = Boolean(invoice.invoiceNumber?.trim());
  const idPart = hasNumber
    ? sanitizeFilenamePart(invoice.invoiceNumber!.trim(), 'INVOICE')
    : invoice.status === 'draft'
      ? 'DRAFT'
      : sanitizeFilenamePart(invoice.invoiceNumber || invoice.id, 'INVOICE');
  const studentIdPart = sanitizeFilenamePart(
    String(invoice.studentMasterId || '').trim(),
    'NoStudentID'
  );
  const namePart = sanitizeFilenamePart(invoice.studentFullName || '', 'Unnamed');
  const datePart = sanitizeFilenamePart(
    formatInvoiceDisplayDate(invoice.invoiceDate),
    'Undated'
  );
  const statusSuffix =
    invoice.status === 'issued'
      ? '_Issued'
      : invoice.status === 'void'
        ? '_Cancelled'
        : invoice.status === 'archived'
          ? '_Archived'
          : '';
  return `${idPart}_${studentIdPart}_${namePart}_${datePart}${statusSuffix}.pdf`;
}

function moneyPlain(value: number): string {
  return formatMoneyInr(roundMoney(value));
}

function pct2(value: number): string {
  return roundMoney(value).toFixed(2);
}

function titleCaseWords(value: string): string {
  return value
    .split(' ')
    .map(part =>
      part
        .split('-')
        .map(token => (token ? token.charAt(0).toUpperCase() + token.slice(1) : token))
        .join('-')
    )
    .join(' ');
}

/** e.g. "Rupees Fifty Thousand Only" */
export function amountToRupeesInWords(amount: number): string {
  const whole = Math.round(Math.abs(Number(amount) || 0));
  const words = titleCaseWords(numberToIndianWords(whole));
  return `Rupees ${words} Only`;
}

function detectImageFormat(dataUrl: string): 'PNG' | 'JPEG' | 'GIF' | 'WEBP' {
  const match = /^data:image\/([a-zA-Z0-9+.-]+);/i.exec(dataUrl);
  const subtype = (match?.[1] || 'png').toLowerCase();
  if (subtype === 'jpeg' || subtype === 'jpg') return 'JPEG';
  if (subtype === 'gif') return 'GIF';
  if (subtype === 'webp') return 'WEBP';
  return 'PNG';
}

function measureLogo(
  doc: jsPDF,
  logoDataUrl?: string | null
): { width: number; height: number } | null {
  if (!logoDataUrl) return null;
  try {
    const props = doc.getImageProperties(logoDataUrl);
    if (props.width > 0 && props.height > 0) {
      const scale = Math.min(LOGO_MAX_W / props.width, LOGO_MAX_H / props.height);
      return { width: props.width * scale, height: props.height * scale };
    }
  } catch {
    // unsupported
  }
  return { width: LOGO_MAX_W, height: LOGO_MAX_H };
}

/** Shrink font so `text` fits on one line (no wrap). */
function fitSingleLineFontSize(
  doc: jsPDF,
  text: string,
  maxWidth: number,
  maxSize: number,
  minSize: number
): number {
  let size = maxSize;
  doc.setFontSize(size);
  while (size > minSize && doc.getTextWidth(text) > maxWidth) {
    size -= 0.5;
    doc.setFontSize(size);
  }
  return size;
}

function drawSectionBanner(
  doc: jsPDF,
  x: number,
  y: number,
  width: number,
  label: string
): number {
  const h = 16;
  doc.setFillColor(...COLORS.darkBlue);
  doc.rect(x, y, width, h, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.text(label, x + 6, y + 11);
  doc.setTextColor(...COLORS.text);
  return y + h;
}

function drawMetaRow(
  doc: jsPDF,
  labelX: number,
  valueX: number,
  y: number,
  labelW: number,
  valueW: number,
  label: string,
  value: string,
  highlight = false
): number {
  const h = 16;
  doc.setDrawColor(...COLORS.border);
  doc.setLineWidth(0.4);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8);
  doc.setTextColor(...COLORS.text);
  doc.text(label, labelX + 4, y + 11);

  if (highlight) {
    doc.setFillColor(...COLORS.lightBlue);
  } else {
    doc.setFillColor(...COLORS.metaFill);
  }
  doc.rect(valueX, y, valueW, h, 'FD');
  doc.setFont('helvetica', 'normal');
  doc.text(value || '—', valueX + valueW - 4, y + 11, { align: 'right' });
  return y + h;
}

/** Draw bank lines on the left and optional UPI QR on the right; height fits content. */
function drawBankDetailsBox(
  doc: jsPDF,
  x: number,
  top: number,
  width: number,
  lines: string[],
  qrDataUrl: string | null
): number {
  const qrSize = 58;
  const qrPad = 8;
  const hasQr = Boolean(qrDataUrl);
  const textWidth = hasQr ? Math.max(80, width - qrSize - qrPad * 3) : width - 16;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.setTextColor(...COLORS.text);
  let cy = top + 10;
  for (let i = 0; i < lines.length; i += 1) {
    const wrapped = doc.splitTextToSize(lines[i], textWidth) as string[];
    for (const w of wrapped) {
      doc.text(w, x + 8, cy);
      cy += 10;
    }
    if (i < lines.length - 1) cy += 1;
  }

  // Fit height to text (+ QR if present) — do not stretch to match the totals panel.
  const textBottom = cy + 6;
  const qrBottom = hasQr ? top + qrPad * 2 + qrSize : top;
  const bottom = Math.max(textBottom, qrBottom);
  doc.setDrawColor(...COLORS.border);
  doc.setLineWidth(0.5);
  doc.rect(x, top, width, bottom - top);

  if (qrDataUrl) {
    const boxH = bottom - top;
    const qrX = x + width - qrPad - qrSize;
    const qrY = top + Math.max(qrPad, (boxH - qrSize) / 2);
    try {
      doc.addImage(qrDataUrl, 'PNG', qrX, qrY, qrSize, qrSize);
    } catch {
      // QR optional
    }
  }

  return bottom;
}

async function fetchQrDataUrl(upiUri: string): Promise<string | null> {
  try {
    const response = await fetch(upiQrImageUrl(upiUri, 160));
    if (!response.ok) return null;
    const blob = await response.blob();
    return await new Promise<string | null>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '') || null);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

export async function exportInvoicePdf(input: {
  invoice: InvoiceDocument;
  totals: InvoiceWorkspaceTotals;
  bank: BankPaymentDetails | null;
  orgGstin: string;
  gstPercentage: number;
  /** Designated account manager contact for the footer. */
  accountManager?: {
    name?: string | null;
    email?: string | null;
  };
  /** When true (default), trigger a browser download. */
  download?: boolean;
}): Promise<{ blob: Blob; filename: string }> {
  const { invoice, totals, bank } = input;
  const branding = await fetchBusinessPdfBranding();
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const contentW = pageW - MARGIN * 2;

  const companyName = (branding.businessName || '').trim() || 'Company Name';
  const addressLines = (branding.addressLines || []).map(l => l.trim()).filter(Boolean);
  const phone = (branding.phone || '').trim();
  const website = (branding.website || '').trim();
  const orgGstin = (input.orgGstin || invoice.orgGstinSnapshot || '').trim();

  const metaW = 210;
  const metaLabelW = 78;
  const metaValueW = metaW - metaLabelW;
  const metaX = pageW - MARGIN - metaW;
  const companyMaxW = metaX - MARGIN - 16;

  // ── Logo ──────────────────────────────────────────────────────────────
  // Start one line higher than the page margin so the header sits tighter.
  let y = MARGIN - 22;
  const logoSize = measureLogo(doc, branding.logoDataUrl);
  if (branding.logoDataUrl && logoSize) {
    try {
      doc.addImage(
        branding.logoDataUrl,
        detectImageFormat(branding.logoDataUrl),
        MARGIN,
        y,
        logoSize.width,
        logoSize.height
      );
      y += logoSize.height + 8;
    } catch {
      // Logo optional
    }
  }

  // ── Business name (single line, no wrap) + INVOICE title ──────────────
  const nameBaseline = y + 14;
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(...COLORS.darkBlue);
  const nameSize = fitSingleLineFontSize(doc, companyName, companyMaxW, 16, 10);
  doc.setFontSize(nameSize);
  doc.text(companyName, MARGIN, nameBaseline);

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  doc.setTextColor(...COLORS.lightBlue);
  doc.text('INVOICE', pageW - MARGIN, nameBaseline, { align: 'right' });

  let leftY = nameBaseline + 14;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(...COLORS.text);
  for (const line of addressLines.slice(0, 4)) {
    doc.text(line, MARGIN, leftY);
    leftY += 11;
  }
  if (phone) {
    doc.text(`Phone: ${phone}`, MARGIN, leftY);
    leftY += 11;
  }
  if (website) {
    doc.text(`Website: ${website}`, MARGIN, leftY);
    leftY += 11;
  }

  // Blank line, then GSTIN
  leftY += 8;
  if (orgGstin) {
    doc.setFont('helvetica', 'bold');
    doc.text(`GSTIN: ${orgGstin}`, MARGIN, leftY);
    doc.setFont('helvetica', 'normal');
    leftY += 11;
  }

  let metaY = nameBaseline + 14;
  const customerId =
    invoice.studentMasterId?.trim() ||
    (invoice.leadId != null ? String(invoice.leadId) : '') ||
    '—';
  metaY = drawMetaRow(
    doc,
    metaX,
    metaX + metaLabelW,
    metaY,
    metaLabelW,
    metaValueW,
    'DATE',
    formatInvoiceDisplayDate(invoice.invoiceDate)
  );
  metaY = drawMetaRow(
    doc,
    metaX,
    metaX + metaLabelW,
    metaY,
    metaLabelW,
    metaValueW,
    'INVOICE #',
    invoice.invoiceNumber || (invoice.status === 'draft' ? 'DRAFT' : invoice.id.slice(0, 12))
  );
  if (invoice.status === 'issued' || invoice.status === 'void') {
    metaY = drawMetaRow(
      doc,
      metaX,
      metaX + metaLabelW,
      metaY,
      metaLabelW,
      metaValueW,
      'STATUS',
      invoice.status === 'issued' ? 'Issued' : 'Cancelled'
    );
  }
  metaY = drawMetaRow(
    doc,
    metaX,
    metaX + metaLabelW,
    metaY,
    metaLabelW,
    metaValueW,
    'CUSTOMER ID',
    customerId
  );
  metaY = drawMetaRow(
    doc,
    metaX,
    metaX + metaLabelW,
    metaY,
    metaLabelW,
    metaValueW,
    'DUE DATE',
    formatInvoiceDisplayDate(invoice.dueDate),
    true
  );

  y = Math.max(leftY, metaY) + 7;

  // ── BILL TO (no package name) ─────────────────────────────────────────
  const billToW = Math.min(260, contentW * 0.45);
  y = drawSectionBanner(doc, MARGIN, y, billToW, 'BILL TO');
  y += 10;

  const cityStateZip = [
    invoice.addressCity,
    invoice.addressState,
    invoice.addressPincode,
  ]
    .map(p => (p || '').trim())
    .filter(Boolean)
    .join(', ');
  const billLines = [
    invoice.studentFullName || '[Name]',
    (invoice.addressStreet || '').trim(),
    [cityStateZip, countryLabel(invoice.addressCountry)].filter(Boolean).join(', '),
    invoice.phone ? `Phone: ${invoice.phone}` : '',
    invoice.email ? `Email: ${invoice.email}` : '',
    invoice.buyerGstin ? `GSTIN: ${invoice.buyerGstin}` : '',
    invoice.pan ? `PAN: ${invoice.pan}` : '',
  ].filter(Boolean);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(...COLORS.text);
  for (const line of billLines) {
    doc.text(String(line), MARGIN, y);
    y += 11;
  }
  y += 6;

  // ── Description table (no TAXED column) ───────────────────────────────
  const packageName = (invoice.packageName || '').trim().toUpperCase();
  const packageInvoiceDescription = (invoice.packageInvoiceDescription || '').trim();
  const hasPackage = Boolean(packageName);
  const descRows: {
    kind: 'package' | 'service' | 'empty' | 'subtotal';
    description: string;
    amount: string;
  }[] = [];

  if (hasPackage) {
    const packageLine = packageInvoiceDescription
      ? `${packageName} — package services including ${packageInvoiceDescription}`
      : packageName;
    descRows.push({ kind: 'package', description: packageLine, amount: '' });
  }

  for (const line of invoice.lines) {
    const qty = Math.max(0, Number(line.quantity) || 0);
    const unit = Math.max(0, Number(line.unitPriceInr) || 0);
    const amount = roundMoney(qty * unit);
    let desc = line.name?.trim() || 'Service';
    if (qty > 1) desc = `${desc} (Qty: ${qty})`;
    descRows.push({ kind: 'service', description: desc, amount: moneyPlain(amount) });
  }

  while (descRows.length < MIN_LINE_ROWS - 1) {
    descRows.push({ kind: 'empty', description: '', amount: '' });
  }
  descRows.push({
    kind: 'subtotal',
    description: 'Subtotal',
    amount: moneyPlain(totals.linesSubtotal),
  });

  autoTable(doc, {
    startY: y,
    head: [['DESCRIPTION', 'AMOUNT']],
    body: descRows.map(row => [row.description, row.amount]),
    theme: 'grid',
    styles: {
      font: 'helvetica',
      fontSize: 8,
      cellPadding: { top: 4, bottom: 4, left: 5, right: 5 },
      textColor: COLORS.text,
      lineColor: COLORS.border,
      lineWidth: 0.4,
      minCellHeight: 16,
      valign: 'middle',
    },
    headStyles: {
      fillColor: COLORS.darkBlue,
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 9,
      halign: 'left',
    },
    bodyStyles: {
      fillColor: [255, 255, 255],
    },
    alternateRowStyles: {
      fillColor: COLORS.zebra,
    },
    columnStyles: {
      0: { cellWidth: contentW - 100, halign: 'left' },
      1: { cellWidth: 100, halign: 'right' },
    },
    didParseCell: data => {
      if (data.section === 'head' && data.column.index === 1) {
        data.cell.styles.halign = 'right';
        return;
      }
      if (data.section !== 'body') return;
      const row = descRows[data.row.index];
      if (!row) return;

      if (data.column.index === 1) {
        data.cell.styles.halign = 'right';
      }

      if (row.kind === 'package' && data.column.index === 0) {
        data.cell.styles.fontStyle = 'bold';
        data.cell.styles.fontSize = 9;
        data.cell.styles.cellPadding = { top: 5, bottom: 5, left: 6, right: 5 };
      } else if (row.kind === 'service' && data.column.index === 0) {
        // Tabbed indent under the package heading
        data.cell.styles.cellPadding = { top: 4, bottom: 4, left: 22, right: 5 };
      } else if (row.kind === 'subtotal') {
        data.cell.styles.fontStyle = 'bold';
        data.cell.styles.fontSize = 9;
        if (data.column.index === 0) {
          data.cell.styles.halign = 'right';
        }
      }
    },
    margin: { left: MARGIN, right: MARGIN },
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  y = ((doc as any).lastAutoTable?.finalY || y) + 14;

  // ── BANK DETAILS (left) + totals (right) ──────────────────────────────
  const bankPanelW = contentW * 0.48;
  const totalsW = contentW * 0.46;
  const totalsX = pageW - MARGIN - totalsW;
  const panelStartY = y;

  const bankLines: string[] = [];
  if (bank) {
    if (bank.beneficiaryName?.trim()) {
      bankLines.push(`Beneficiary: ${bank.beneficiaryName.trim()}`);
    }
    if (bank.bankName?.trim()) bankLines.push(`Bank: ${bank.bankName.trim()}`);
    if (bank.accountNumber?.trim()) bankLines.push(`A/c No: ${bank.accountNumber.trim()}`);
    if (bank.accountType?.trim()) bankLines.push(`Account type: ${bank.accountType.trim()}`);
    if (bank.ifscCode?.trim()) bankLines.push(`IFSC: ${bank.ifscCode.trim()}`);
    if (bank.branchNameCity?.trim()) bankLines.push(`Branch: ${bank.branchNameCity.trim()}`);
    if (bank.swiftBicCode?.trim()) bankLines.push(`SWIFT/BIC: ${bank.swiftBicCode.trim()}`);
    if (bank.iban?.trim()) bankLines.push(`IBAN: ${bank.iban.trim()}`);
    const upi = (invoice.upiVpa || bank.upiVpa || '').trim();
    if (upi) bankLines.push(`UPI: ${upi}`);
  }
  if (!bankLines.length) {
    bankLines.push('Bank details not configured in Accounts settings.');
  }

  const upiVpa = (invoice.upiVpa || bank?.upiVpa || '').trim();
  const upiUri = upiVpa
    ? buildUpiPayUri({
        vpa: upiVpa,
        payeeName: bank?.beneficiaryName || companyName,
        amountInr: totals.finalPayableAmount,
        note: invoice.invoiceNumber || invoice.id,
        transactionRef: invoice.invoiceNumber || undefined,
      })
    : null;
  const qrDataUrl = upiUri ? await fetchQrDataUrl(upiUri) : null;

  drawSectionBanner(doc, MARGIN, panelStartY, bankPanelW, 'BANK DETAILS');
  const bankBoxTop = panelStartY + 16;

  // Totals / Subtotal panel
  const tax = totals.tax;
  const discountPct =
    invoice.discountType === 'percentage'
      ? roundMoney(invoice.discountValue)
      : totals.discountPercentOfSubtotal;

  type TotalRow = { label: string; value: string; boxed?: boolean; total?: boolean };
  const totalRows: TotalRow[] = [
    { label: 'Subtotal', value: moneyPlain(totals.linesSubtotal) },
  ];

  if (totals.discountAmount > 0) {
    totalRows.push({
      label: `Discount (${pct2(discountPct)}%)`,
      value: `- ${moneyPlain(totals.discountAmount)}`,
    });
  }

  totalRows.push({ label: 'Taxable', value: moneyPlain(totals.taxableAmount) });

  if (tax.supplyType === 'intra') {
    totalRows.push({
      label: `CGST (${pct2(tax.cgstRate)}%)`,
      value: moneyPlain(tax.cgstAmount),
    });
    totalRows.push({
      label: `SGST (${pct2(tax.sgstRate)}%)`,
      value: moneyPlain(tax.sgstAmount),
    });
  } else if (tax.supplyType === 'inter') {
    totalRows.push({
      label: `IGST (${pct2(tax.igstRate)}%)`,
      value: moneyPlain(tax.igstAmount),
    });
  } else {
    totalRows.push({ label: 'GST', value: 'Exempt / 0.00' });
  }

  if (Math.abs(totals.roundOffAmount) >= 0.005) {
    totalRows.push({
      label: 'Round-off',
      value: moneyPlain(totals.roundOffAmount),
      boxed: true,
    });
  }

  totalRows.push({
    label: 'Total Payable',
    value: moneyPlain(totals.finalPayableAmount),
    total: true,
  });

  let ty = panelStartY;
  const labelColW = totalsW * 0.55;
  const valueColW = totalsW - labelColW;
  const rowH = 15;

  for (const row of totalRows) {
    doc.setFont('helvetica', row.total ? 'bold' : 'normal');
    doc.setFontSize(row.total ? 10 : 9);
    doc.setTextColor(...COLORS.text);
    doc.text(row.label, totalsX + 2, ty + 11);

    const vx = totalsX + labelColW;
    if (row.total) {
      doc.setFillColor(...COLORS.lightBlue);
      doc.setDrawColor(...COLORS.border);
      doc.setLineWidth(0.8);
      doc.rect(vx, ty, valueColW, rowH, 'FD');
      doc.setLineWidth(1.1);
      doc.line(vx, ty - 1, vx + valueColW, ty - 1);
      doc.line(vx, ty + 1.5, vx + valueColW, ty + 1.5);
      doc.setFont('helvetica', 'bold');
      doc.text(`Rs ${row.value}`, vx + valueColW - 4, ty + 11, { align: 'right' });
    } else if (row.boxed) {
      doc.setFillColor(255, 255, 255);
      doc.setDrawColor(...COLORS.border);
      doc.setLineWidth(0.4);
      doc.rect(vx, ty + 1, valueColW, rowH - 2, 'FD');
      doc.setFont('helvetica', 'normal');
      doc.text(row.value, vx + valueColW - 4, ty + 11, { align: 'right' });
    } else {
      doc.setFont('helvetica', 'normal');
      doc.text(row.value, vx + valueColW - 4, ty + 11, { align: 'right' });
    }
    ty += rowH + (row.total ? 2 : 1);
  }

  // Amount in words under totals
  ty += 6;
  doc.setFont('helvetica', 'italic');
  doc.setFontSize(8);
  doc.setTextColor(...COLORS.text);
  const words = amountToRupeesInWords(totals.finalPayableAmount);
  const wordsWrapped = doc.splitTextToSize(`Amount in words: ${words}`, totalsW) as string[];
  for (const line of wordsWrapped) {
    doc.text(line, totalsX, ty);
    ty += 10;
  }

  const bankBoxBottom = drawBankDetailsBox(
    doc,
    MARGIN,
    bankBoxTop,
    bankPanelW,
    bankLines,
    qrDataUrl
  );

  y = Math.max(bankBoxBottom, ty) + 16;

  // ── Questions ─────────────────────────────────────────────────────────
  const mgrName = (
    input.accountManager?.name ||
    invoice.counselorName ||
    ''
  ).trim();
  const mgrEmail = (input.accountManager?.email || '').trim();
  const contactParts = [mgrName, mgrEmail].filter(Boolean);
  const questionsLine = contactParts.length
    ? `Questions regarding this invoice? Please reach out to your designated account manager: ${contactParts.join('  |  ')}.`
    : 'Questions regarding this invoice? Please reach out to your designated account manager.';

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.setTextColor(...COLORS.text);
  const questionsWrapped = doc.splitTextToSize(questionsLine, contentW) as string[];
  for (const line of questionsWrapped) {
    doc.text(line, MARGIN, y);
    y += 11;
  }
  y += 8;

  // Computer-generated note
  doc.setFont('helvetica', 'italic');
  doc.setFontSize(8);
  doc.setTextColor(...COLORS.muted);
  doc.text(
    'This is a computer-generated invoice and does not require a physical signature.',
    pageW / 2,
    y,
    { align: 'center', maxWidth: contentW }
  );

  // Page numbers on every page
  const pageCount = doc.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    doc.setPage(page);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(100, 100, 100);
    doc.text(`Page ${page} of ${pageCount}`, pageW - MARGIN, pageH - 18, { align: 'right' });
  }

  const filename = buildInvoicePdfFilename(invoice);
  const arrayBuffer = doc.output('arraybuffer') as ArrayBuffer;
  const blob = new Blob([arrayBuffer], { type: 'application/pdf' });
  if (input.download !== false) {
    doc.save(filename);
  }
  return { blob, filename };
}
