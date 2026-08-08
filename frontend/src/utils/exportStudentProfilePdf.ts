import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { createPdfLayout } from './pdfLayout';
import {
  joinLabels,
  type StudentProfilePreviewModel,
} from './studentProfilePreview';

function drawDocumentTitle(
  doc: jsPDF,
  model: StudentProfilePreviewModel,
  layoutStartY: number,
  margin: number,
  pageWidth: number
): number {
  let y = layoutStartY + 6;
  const rightX = pageWidth - margin;

  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(100, 116, 139);
  doc.text(model.generatedAtLabel, rightX, y, { align: 'right' });

  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(15, 23, 42);
  doc.text('Student Profile Preview', pageWidth / 2, y, { align: 'center' });

  // Blank line between the title and the candidate row.
  y += 32;

  const label = 'Candidate Name : ';
  doc.setFontSize(11);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(71, 85, 105);
  doc.text(label, margin, y);
  const labelWidth = doc.getTextWidth(label);

  doc.setFont('helvetica', 'bold');
  doc.setTextColor(30, 41, 59);
  doc.text(model.candidateName, margin + labelWidth, y);

  doc.setFont('helvetica', 'normal');
  doc.setTextColor(0);
  // Blank line after candidate name before section content.
  return y + 28;
}

/** Nexus website primary / accent (`--color-primary` / `--color-accent`). */
const NEXUS_BLUE: [number, number, number] = [50, 47, 134];

export function exportStudentProfilePdf(
  model: StudentProfilePreviewModel,
  filename = 'student-profile-preview.pdf',
  brandingOverride?: { logoDataUrl?: string | null }
): void {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' });
  const layout = createPdfLayout(doc, {
    branding: {
      businessName: model.companyName,
      addressLines: model.companyAddressLines,
      logoDataUrl: brandingOverride?.logoDataUrl ?? model.logoDataUrl,
    },
    margin: 40,
  });
  const { margin, tableMargins } = layout;
  const pageWidth = layout.pageWidth;

  let y = drawDocumentTitle(doc, model, layout.contentStartY, margin, pageWidth);

  if (!model.aspirationSections.length) {
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(120);
    doc.text('No aspiration answers available.', margin, y + 8);
    doc.setTextColor(0);
  } else {
    model.aspirationSections.forEach(section => {
      if (layout.needsNewPage(y, 60)) {
        doc.addPage();
        y = layout.contentStartY + 6;
      }

      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...NEXUS_BLUE);
      doc.text(section.title, margin, y + 8);
      doc.setTextColor(0);
      y += 14;

      autoTable(doc, {
        startY: y,
        head: [['Code', 'Question', 'Answer']],
        body: section.items.map(item => [item.code, item.question, item.answer || '—']),
        styles: {
          fontSize: 8,
          cellPadding: 3,
          overflow: 'linebreak',
          valign: 'top',
        },
        columnStyles: {
          0: { cellWidth: 36, fontStyle: 'bold' },
          1: { cellWidth: 180 },
          2: { cellWidth: 'auto' },
        },
        headStyles: {
          fillColor: [241, 245, 249],
          textColor: [51, 65, 85],
          fontStyle: 'bold',
        },
        alternateRowStyles: {
          fillColor: [248, 250, 252],
        },
        margin: tableMargins,
      });

      y =
        ((doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY || y) +
        14;
    });
  }

  doc.addPage();
  y = layout.contentStartY + 6;
  doc.setFontSize(13);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(15, 23, 42);
  doc.text('Recommended Institutions by Country', margin, y);
  y += 14;

  if (!model.countryGroups.length) {
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(120);
    doc.text('No recommended institutions selected.', margin, y + 8);
    doc.setTextColor(0);
  } else {
    model.countryGroups.forEach(group => {
      if (layout.needsNewPage(y, 100)) {
        doc.addPage();
        y = layout.contentStartY + 6;
        doc.setFontSize(13);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(15, 23, 42);
        doc.text('Recommended Institutions by Country (continued)', margin, y);
        y += 14;
      }

      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(30, 41, 59);
      doc.text(`Country: ${group.countryName}`, margin, y + 8);
      y += 14;

      autoTable(doc, {
        startY: y,
        head: [
          [
            'College / Institution',
            'State',
            'City',
            'Level',
            'Majors',
            'Programs',
            'English',
            'Aptitude',
            'Avg Cost',
            'Backlog',
            'Scholarship',
          ],
        ],
        body: group.colleges.map(college => [
          `${college.name}\n(${college.kind === 'college' ? 'College' : 'Institution'})`,
          college.state_name || '—',
          college.city_name || '—',
          model.levelLabel,
          joinLabels(model.majorLabels),
          joinLabels(model.programLabels),
          joinLabels(model.englishLabels),
          joinLabels(model.aptitudeLabels),
          '—',
          '—',
          model.scholarshipLabel,
        ]),
        styles: {
          fontSize: 7,
          cellPadding: 3,
          overflow: 'linebreak',
          valign: 'top',
        },
        headStyles: {
          fillColor: NEXUS_BLUE,
          textColor: [255, 255, 255],
          fontStyle: 'bold',
        },
        alternateRowStyles: {
          fillColor: [248, 250, 252],
        },
        margin: tableMargins,
      });

      y = ((doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY || y) + 18;
    });
  }

  layout.applyChromeToAllPages();
  doc.save(filename);
}
