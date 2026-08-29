/**
 * Sample Qualified Prospect guidance PDF (NEXUS branding).
 * Run from frontend/: node scripts/generate-sample-guidance-pdf.mjs
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, '..', '..', 'docs');
const OUT_PDF = join(OUT_DIR, 'sample-qualified-prospect-guidance.pdf');
const OUT_HTML = join(OUT_DIR, 'sample-qualified-prospect-guidance.html');

const ACCENT = [50, 47, 134];
const SLATE = [44, 62, 80];
const MUTED = [100, 116, 139];
const LINE = [220, 220, 220];
const CALLOUT_BG = [244, 247, 249];
const PAGE_BG = [252, 252, 252];

const SAMPLE = {
  candidateName: 'Jai Prakash',
  studentId: 'SM-1842',
  packageName: 'Elite',
  accountManager: 'Priya Sharma',
  accountManagerRole: 'Assigned Counsellor / Account Manager',
  services: [
    'University Shortlisting',
    'SOP & Essay Drafting',
    'Visa Application Help',
    'Mock Interview Prep',
  ],
};

const RACI = [
  {
    service: 'University Shortlisting',
    am: 'Build a fit-based shortlist (profile, budget, intake, visa pathway). Present 8–12 targets with rationale.',
    candidate: 'Confirm preferences, budget ceiling, and must-have / deal-breaker criteria. Approve final list.',
  },
  {
    service: 'SOP & Essay Drafting',
    am: 'Draft and iterate SOP / essays to university prompts. Editorial review before each submission.',
    candidate: 'Share academic story, achievements, and prompt answers. Review drafts within 3 working days.',
  },
  {
    service: 'Visa Application Help',
    am: 'Prepare document checklist, review evidence pack, and guide filing sequence for the chosen destination.',
    candidate: 'Collect originals, translations, and financials. Attend biometrics / interview on scheduled dates.',
  },
  {
    service: 'Mock Interview Prep',
    am: 'Run destination-specific mock interviews, feedback notes, and a final dress-rehearsal before the real call.',
    candidate: 'Complete pre-read, join scheduled mocks, and implement feedback before the university / visa interview.',
  },
];

const SUPPORT = [
  'Single point of contact for all opted Elite services until landing handoff.',
  'Weekly progress note in the student portal while any opted service is active.',
  'Escalation to senior counselling within one business day if an offer or visa milestone slips.',
  'Interview prep slots booked at least 5 working days before the real interview (when Mock Interview Prep is opted).',
  'Visa file completeness review before submission (when Visa Application Help is opted).',
];

function hexFill(doc, rgb) {
  doc.setFillColor(...rgb);
  doc.setDrawColor(...rgb);
}

function wrap(doc, text, width, fontSize = 10) {
  doc.setFontSize(fontSize);
  return doc.splitTextToSize(text, width);
}

function drawHeader(doc, pageW, marginX, marginY) {
  hexFill(doc, ACCENT);
  doc.rect(0, 0, pageW, 28, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.text('Nexus Intel  ·  Admission Services', marginX, 12);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8.5);
  doc.text('Qualified Prospect Guidance', marginX, 20);
  doc.setFontSize(8);
  doc.text('Confidential', pageW - marginX, 12, { align: 'right' });
  doc.text(`Student ID  ${SAMPLE.studentId}`, pageW - marginX, 20, { align: 'right' });
}

function drawFooter(doc, pageW, pageH, marginX, page, pages) {
  doc.setDrawColor(...LINE);
  doc.setLineWidth(0.3);
  doc.line(marginX, pageH - 12, pageW - marginX, pageH - 12);
  doc.setTextColor(...MUTED);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7.5);
  doc.text(
    'Nexus Admission Services  |  Confidential Document  |  For the registered candidate only',
    marginX,
    pageH - 7
  );
  doc.text(`Page ${page} of ${pages}`, pageW - marginX, pageH - 7, { align: 'right' });
}

function sectionTitle(doc, n, title, x, y) {
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.setTextColor(...ACCENT);
  doc.text(`${n}.  ${title}`, x, y);
  return y + 6;
}

function buildPdf() {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const mx = 12;
  const contentW = pageW - mx * 2;

  hexFill(doc, PAGE_BG);
  doc.rect(0, 0, pageW, pageH, 'F');
  drawHeader(doc, pageW, mx, 15);

  let y = 36;
  doc.setTextColor(...SLATE);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  doc.text(`Welcome, ${SAMPLE.candidateName}`, mx, y);
  y += 7;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  doc.setTextColor(51, 65, 85);
  const welcome = wrap(
    doc,
    `Congratulations on registering as a Qualified Prospect. This guidance note is tailored to your ${SAMPLE.packageName} package and the services you opted for. Your ${SAMPLE.accountManagerRole.toLowerCase()}, ${SAMPLE.accountManager}, will lead delivery of the scope below.`,
    contentW
  );
  doc.text(welcome, mx, y);
  y += welcome.length * 4.6 + 4;

  doc.setFillColor(238, 242, 255);
  doc.setDrawColor(...ACCENT);
  doc.setLineWidth(0.35);
  doc.roundedRect(mx, y, contentW, 18, 1.5, 1.5, 'FD');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8.5);
  doc.setTextColor(...ACCENT);
  doc.text('PACKAGE  ·  OPTED SERVICES', mx + 4, y + 6);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.setTextColor(...SLATE);
  doc.text(SAMPLE.packageName, mx + 4, y + 13);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(51, 65, 85);
  doc.text(SAMPLE.services.join('   ·   '), mx + 38, y + 13);
  y += 24;

  y = sectionTitle(doc, '1', 'Intake & Strategic Alignment', mx, y);
  doc.setFillColor(...CALLOUT_BG);
  doc.setDrawColor(...LINE);
  doc.setLineWidth(0.3);
  const intakeLines = wrap(
    doc,
    `Elite intake (90 minutes). ${SAMPLE.accountManager} will run a deep-dive onboarding covering academic profile, destination fit, budget, timeline, and visa pathway. Because University Shortlisting and SOP & Essay Drafting are in scope, the session ends with a shortlist hypothesis and an essay narrative brief. Visa and interview workstreams are scheduled after the first target list is locked.`,
    contentW - 8,
    9.5
  );
  const boxH = intakeLines.length * 4.4 + 10;
  doc.roundedRect(mx, y, contentW, boxH, 1.5, 1.5, 'FD');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.setTextColor(...ACCENT);
  doc.text('Elite onboarding callout', mx + 4, y + 5.5);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9.5);
  doc.setTextColor(51, 65, 85);
  doc.text(intakeLines, mx + 4, y + 11);
  y += boxH + 8;

  y = sectionTitle(doc, '2', 'Admission Processing Pipeline', mx, y);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(...MUTED);
  doc.text('Responsibilities apply only to services you selected.', mx, y);
  y += 3;

  autoTable(doc, {
    startY: y,
    margin: { left: mx, right: mx },
    head: [['Opted service', 'Account Manager', 'Candidate / family']],
    body: RACI.map(row => [row.service, row.am, row.candidate]),
    styles: {
      font: 'helvetica',
      fontSize: 8,
      cellPadding: 2.2,
      textColor: [51, 65, 85],
      lineColor: LINE,
      lineWidth: 0.2,
      valign: 'top',
    },
    headStyles: {
      fillColor: ACCENT,
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 8.5,
    },
    columnStyles: {
      0: { cellWidth: 38, fontStyle: 'bold', textColor: SLATE },
      1: { cellWidth: 74 },
      2: { cellWidth: contentW - 38 - 74 },
    },
    alternateRowStyles: { fillColor: [248, 250, 252] },
  });
  y = doc.lastAutoTable.finalY + 10;

  y = sectionTitle(doc, '3', 'Communication & Tracking', mx, y);
  const comms = [
    'Portal: milestone status, document requests, and offer tracking live on your student record.',
    'Notifications: email / in-app alerts when a university responds, a visa step is due, or an interview is booked.',
    'Interview prep: mock sessions appear on your Appointments calendar; feedback notes are filed against the application.',
    'Acceptance tracking: offers, deposits, and visa outcomes are logged on Process 4 Applications and related subprocesses.',
  ];
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9.5);
  doc.setTextColor(51, 65, 85);
  for (const line of comms) {
    const bullets = wrap(doc, `•  ${line}`, contentW, 9.5);
    doc.text(bullets, mx, y);
    y += bullets.length * 4.5 + 1.5;
  }
  y += 4;

  y = sectionTitle(doc, '4', 'Support Commitment', mx, y);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9.5);
  doc.setTextColor(51, 65, 85);
  for (const line of SUPPORT) {
    const bullets = wrap(doc, `•  ${line}`, contentW, 9.5);
    if (y + bullets.length * 4.5 > pageH - 18) {
      doc.addPage();
      hexFill(doc, PAGE_BG);
      doc.rect(0, 0, pageW, pageH, 'F');
      drawHeader(doc, pageW, mx, 15);
      y = 36;
    }
    doc.text(bullets, mx, y);
    y += bullets.length * 4.5 + 1.2;
  }

  y += 6;
  doc.setDrawColor(...LINE);
  doc.line(mx, y, pageW - mx, y);
  y += 6;
  doc.setFont('helvetica', 'italic');
  doc.setFontSize(8.5);
  doc.setTextColor(...MUTED);
  const close = wrap(
    doc,
    `Prepared for ${SAMPLE.candidateName} (${SAMPLE.studentId}) after Qualified Prospect registration. Scope is limited to the ${SAMPLE.packageName} package and the opted services listed. Additional services require a revised agreement and invoice.`,
    contentW,
    8.5
  );
  doc.text(close, mx, y);

  const pages = doc.getNumberOfPages();
  for (let p = 1; p <= pages; p += 1) {
    doc.setPage(p);
    drawFooter(doc, pageW, pageH, mx, p, pages);
  }

  mkdirSync(OUT_DIR, { recursive: true });
  const buf = Buffer.from(doc.output('arraybuffer'));
  writeFileSync(OUT_PDF, buf);
  return { pages };
}

function buildHtml() {
  const rows = RACI.map(
    row => `<tr>
      <th>${row.service}</th>
      <td>${row.am}</td>
      <td>${row.candidate}</td>
    </tr>`
  ).join('');
  const comms = [
    'Portal: milestone status, document requests, and offer tracking live on your student record.',
    'Notifications: email / in-app alerts when a university responds, a visa step is due, or an interview is booked.',
    'Interview prep: mock sessions appear on your Appointments calendar; feedback notes are filed against the application.',
    'Acceptance tracking: offers, deposits, and visa outcomes are logged on Process 4 Applications and related subprocesses.',
  ];
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Qualified Prospect Guidance — ${SAMPLE.candidateName}</title>
  <style>
    @page { size: A4; margin: 15mm 12mm; }
    * { box-sizing: border-box; }
    body {
      margin: 0; background: #e8edf3; color: #334155;
      font-family: Helvetica, Arial, sans-serif;
    }
    .sheet {
      width: 210mm; min-height: 297mm; margin: 16px auto; background: #fcfcfc;
      box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12); padding: 0 12mm 15mm;
    }
    .banner {
      margin: 0 -12mm 18px; background: #322f86; color: #fff;
      padding: 14px 12mm 12px; display: flex; justify-content: space-between; align-items: flex-end;
    }
    .banner h1 { margin: 0; font-size: 15px; letter-spacing: 0.02em; }
    .banner p { margin: 4px 0 0; font-size: 11px; opacity: 0.9; }
    .meta { text-align: right; font-size: 11px; }
    h2 { margin: 0 0 8px; font-size: 20px; color: #2c3e50; }
    h3 { margin: 20px 0 8px; font-size: 13px; color: #322f86; }
    .lead { font-size: 13px; line-height: 1.45; margin: 0 0 14px; }
    .pkg {
      border: 1px solid #322f86; background: #eef2ff; border-radius: 8px;
      padding: 10px 14px; margin-bottom: 16px; display: flex; gap: 16px; align-items: baseline;
    }
    .pkg strong { color: #2c3e50; font-size: 15px; }
    .pkg span { font-size: 12px; color: #475569; }
    .callout {
      background: #f4f7f9; border: 1px solid #dcdcdc; border-radius: 8px;
      padding: 12px 14px; font-size: 12.5px; line-height: 1.5;
    }
    .callout b { color: #322f86; display: block; margin-bottom: 6px; font-size: 11px; }
    table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
    th, td { border: 1px solid #dcdcdc; padding: 8px 9px; vertical-align: top; text-align: left; }
    thead th { background: #322f86; color: #fff; font-size: 11px; }
    tbody th { background: #f8fafc; color: #2c3e50; width: 22%; }
    tbody tr:nth-child(even) td { background: #f8fafc; }
    ul { margin: 0; padding-left: 18px; font-size: 12.5px; line-height: 1.55; }
    .note { margin-top: 18px; padding-top: 10px; border-top: 1px solid #dcdcdc;
      font-size: 11px; color: #64748b; font-style: italic; }
    .foot { margin-top: 22px; font-size: 10px; color: #64748b;
      display: flex; justify-content: space-between; border-top: 1px solid #dcdcdc; padding-top: 8px; }
  </style>
</head>
<body>
  <article class="sheet">
    <header class="banner">
      <div>
        <h1>Nexus Intel  ·  Admission Services</h1>
        <p>Qualified Prospect Guidance</p>
      </div>
      <div class="meta">
        <div>Confidential</div>
        <div>Student ID  ${SAMPLE.studentId}</div>
      </div>
    </header>
    <h2>Welcome, ${SAMPLE.candidateName}</h2>
    <p class="lead">Congratulations on registering as a Qualified Prospect. This guidance note is tailored to your <strong>${SAMPLE.packageName}</strong> package and the services you opted for. Your ${SAMPLE.accountManagerRole.toLowerCase()}, <strong>${SAMPLE.accountManager}</strong>, will lead delivery of the scope below.</p>
    <div class="pkg">
      <strong>${SAMPLE.packageName}</strong>
      <span>${SAMPLE.services.join('  ·  ')}</span>
    </div>
    <h3>1. Intake &amp; Strategic Alignment</h3>
    <div class="callout">
      <b>Elite onboarding callout</b>
      Elite intake (90 minutes). ${SAMPLE.accountManager} will run a deep-dive onboarding covering academic profile, destination fit, budget, timeline, and visa pathway. Because University Shortlisting and SOP &amp; Essay Drafting are in scope, the session ends with a shortlist hypothesis and an essay narrative brief. Visa and interview workstreams are scheduled after the first target list is locked.
    </div>
    <h3>2. Admission Processing Pipeline</h3>
    <p class="lead" style="font-size:12px;color:#64748b">Responsibilities apply only to services you selected.</p>
    <table>
      <thead>
        <tr><th>Opted service</th><th>Account Manager</th><th>Candidate / family</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <h3>3. Communication &amp; Tracking</h3>
    <ul>${comms.map(item => `<li>${item}</li>`).join('')}</ul>
    <h3>4. Support Commitment</h3>
    <ul>${SUPPORT.map(item => `<li>${item}</li>`).join('')}</ul>
    <p class="note">Prepared for ${SAMPLE.candidateName} (${SAMPLE.studentId}) after Qualified Prospect registration. Scope is limited to the ${SAMPLE.packageName} package and the opted services listed. Additional services require a revised agreement and invoice.</p>
    <footer class="foot">
      <span>Nexus Admission Services | Confidential Document | For the registered candidate only</span>
      <span>Sample preview</span>
    </footer>
  </article>
</body>
</html>`;
}

const { pages } = buildPdf();
writeFileSync(OUT_HTML, buildHtml(), 'utf8');
console.log(`pdf=${OUT_PDF}`);
console.log(`html=${OUT_HTML}`);
console.log(`pages=${pages}`);
