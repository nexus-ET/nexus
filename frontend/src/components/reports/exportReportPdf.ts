import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ReportColumn } from './ReportTable';
import { createPdfLayout } from '../../utils/pdfLayout';
import type { PdfBusinessBranding } from '../../utils/pdfLayout';

interface ExportReportPdfOptions<T> {
  title: string;
  subtitle?: string;
  columns: ReportColumn<T>[];
  rows: T[];
  filename?: string;
  branding?: PdfBusinessBranding;
}

export function exportReportPdf<T>({
  title,
  subtitle,
  columns,
  rows,
  filename = 'report.pdf',
  branding,
}: ExportReportPdfOptions<T>): void {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
  const layout = createPdfLayout(doc, {
    branding: branding || {},
    margin: 40,
  });

  let y = layout.contentStartY + 6;
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(15, 23, 42);
  doc.text(title, layout.margin, y);
  y += 16;

  if (subtitle) {
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(71, 85, 105);
    doc.text(subtitle, layout.margin, y);
    doc.setTextColor(0, 0, 0);
    y += 14;
  }

  autoTable(doc, {
    startY: y,
    head: [columns.map(column => column.header)],
    body: rows.map(row =>
      columns.map(column => {
        if (column.pdfValue) {
          return column.pdfValue(row);
        }
        const rendered = column.render(row);
        if (typeof rendered === 'string' || typeof rendered === 'number') {
          return String(rendered);
        }
        return '';
      })
    ),
    styles: {
      fontSize: 8,
      cellPadding: 4,
      overflow: 'linebreak',
    },
    headStyles: {
      fillColor: [24, 24, 27],
      textColor: [255, 255, 255],
      fontStyle: 'bold',
    },
    alternateRowStyles: {
      fillColor: [248, 250, 252],
    },
    margin: layout.tableMargins,
  });

  layout.applyChromeToAllPages();
  doc.save(filename);
}
