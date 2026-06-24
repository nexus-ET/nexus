import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ReportColumn } from './ReportTable';

interface ExportReportPdfOptions<T> {
  title: string;
  subtitle?: string;
  columns: ReportColumn<T>[];
  rows: T[];
  filename?: string;
}

export function exportReportPdf<T>({
  title,
  subtitle,
  columns,
  rows,
  filename = 'report.pdf',
}: ExportReportPdfOptions<T>): void {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
  const margin = 40;

  doc.setFontSize(16);
  doc.text(title, margin, margin);

  if (subtitle) {
    doc.setFontSize(10);
    doc.setTextColor(90, 90, 90);
    doc.text(subtitle, margin, margin + 18);
    doc.setTextColor(0, 0, 0);
  }

  autoTable(doc, {
    startY: subtitle ? margin + 30 : margin + 20,
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
  });

  doc.save(filename);
}
