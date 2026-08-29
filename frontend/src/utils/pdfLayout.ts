import type jsPDF from 'jspdf';

/** Tenant branding bound at export time — never hardcode company details. */
export interface PdfBusinessBranding {
  businessName?: string | null;
  addressLines?: string[] | null;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  /** PNG/JPEG/GIF data URL or ArrayBuffer for jsPDF addImage. */
  logoDataUrl?: string | null;
}

export interface PdfLayoutOptions {
  branding: PdfBusinessBranding;
  /** Outer page margin in document units (pt when using jsPDF unit:'pt'). */
  margin?: number;
}

export interface PdfLayoutMargins {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const LOGO_MAX_HEIGHT = 28;
const LOGO_MAX_WIDTH = 72;
const NAME_FONT_SIZE = 12;
const FOOTER_FONT_SIZE = 8;
const FOOTER_MAX_ADDRESS_LINES = 2;

/**
 * Reusable page chrome for Nexus PDF reports (jsPDF).
 * Injects a standardized header (logo + business name) and footer
 * (full business address + Page X of Y) on every page without
 * overlapping body content.
 */
export class PdfLayoutWrapper {
  readonly doc: jsPDF;
  readonly margin: number;
  readonly branding: PdfBusinessBranding;
  readonly pageWidth: number;
  readonly pageHeight: number;

  private readonly wrappedAddressLines: string[];
  private readonly headerBand: number;
  private readonly headerRowHeight: number;
  private readonly footerBand: number;
  private readonly logoSize: { width: number; height: number } | null;

  constructor(doc: jsPDF, options: PdfLayoutOptions) {
    this.doc = doc;
    this.margin = options.margin ?? 40;
    this.branding = options.branding;
    this.pageWidth = doc.internal.pageSize.getWidth();
    this.pageHeight = doc.internal.pageSize.getHeight();

    const addressLines = (options.branding.addressLines || [])
      .map(line => line.trim())
      .filter(Boolean);

    const hasName = Boolean((options.branding.businessName || '').trim());
    this.logoSize = measureLogo(doc, options.branding.logoDataUrl);
    this.headerRowHeight = Math.max(
      this.logoSize?.height ?? 0,
      hasName ? NAME_FONT_SIZE + 2 : 0
    );
    this.headerBand = this.headerRowHeight > 0 ? this.headerRowHeight + 14 : 12;

    const usableWidth = Math.max(120, this.pageWidth - this.margin * 2 - 90);
    this.wrappedAddressLines = addressLines.length
      ? clampToLines(doc, addressLines.join(' · '), usableWidth, FOOTER_MAX_ADDRESS_LINES)
      : [];
    const addressBlock = Math.max(1, this.wrappedAddressLines.length) * 10;
    this.footerBand = 16 + addressBlock + 6;
  }

  /** Y where document body may begin (below repeating header). */
  get contentStartY(): number {
    return this.margin + this.headerBand;
  }

  /** Lowest Y body content may use (above repeating footer). */
  get contentEndY(): number {
    return this.pageHeight - this.margin - this.footerBand;
  }

  /** Safe bottom inset for autoTable / multi-page flows. */
  get footerReserve(): number {
    return this.margin + this.footerBand;
  }

  /** Margins suitable for jspdf-autotable so split pages clear chrome. */
  get tableMargins(): PdfLayoutMargins {
    return {
      left: this.margin,
      right: this.margin,
      top: this.contentStartY,
      bottom: this.footerReserve,
    };
  }

  /** True when `y` is past the safe content bottom (caller should add a page). */
  needsNewPage(y: number, extra = 0): boolean {
    return y > this.contentEndY - extra;
  }

  /** Draw header + footer on the current page only. */
  drawPageChrome(pageNumber: number, pageCount: number): void {
    this.drawHeader();
    this.drawFooter(pageNumber, pageCount);
  }

  /**
   * Apply standardized header/footer to every page after content is complete
   * so `Page X of Y` uses the final page count.
   */
  applyChromeToAllPages(): void {
    const pageCount = this.doc.getNumberOfPages();
    for (let page = 1; page <= pageCount; page += 1) {
      this.doc.setPage(page);
      this.drawPageChrome(page, pageCount);
    }
  }

  private drawHeader(): void {
    const name = (this.branding.businessName || '').trim();
    const left = this.margin;
    const right = this.pageWidth - this.margin;
    const rowCenterY = this.margin + this.headerRowHeight / 2;
    let textX = left;

    if (this.branding.logoDataUrl && this.logoSize) {
      try {
        const format = detectImageFormat(this.branding.logoDataUrl);
        this.doc.addImage(
          this.branding.logoDataUrl,
          format,
          left,
          rowCenterY - this.logoSize.height / 2,
          this.logoSize.width,
          this.logoSize.height
        );
        textX = left + this.logoSize.width + 10;
      } catch {
        // Logo formats such as SVG may be unsupported by jsPDF; keep name-only header.
      }
    }

    if (name) {
      this.doc.setFont('helvetica', 'bold');
      this.doc.setFontSize(NAME_FONT_SIZE);
      this.doc.setTextColor(15, 23, 42);
      // baseline offset keeps the name optically centred against the logo
      this.doc.text(name, textX, rowCenterY + NAME_FONT_SIZE * 0.35);
    }

    const dividerY = this.margin + this.headerBand - 8;
    this.doc.setDrawColor(203, 213, 225);
    this.doc.setLineWidth(0.6);
    this.doc.line(left, dividerY, right, dividerY);
    this.doc.setTextColor(0);
  }

  private drawFooter(pageNumber: number, pageCount: number): void {
    const left = this.margin;
    const right = this.pageWidth - this.margin;
    const footerTop = this.pageHeight - this.margin - this.footerBand;

    this.doc.setDrawColor(203, 213, 225);
    this.doc.setLineWidth(0.5);
    this.doc.line(left, footerTop, right, footerTop);

    this.doc.setFont('helvetica', 'normal');
    this.doc.setFontSize(FOOTER_FONT_SIZE);
    this.doc.setTextColor(100, 116, 139);

    let addressY = footerTop + 12;
    this.wrappedAddressLines.forEach(line => {
      this.doc.text(line, left, addressY);
      addressY += 10;
    });

    const pageLabel = `Page ${pageNumber} of ${pageCount}`;
    this.doc.text(pageLabel, right, this.pageHeight - this.margin - 4, {
      align: 'right',
    });

    this.doc.setTextColor(0);
  }
}

function measureLogo(
  doc: jsPDF,
  logoDataUrl?: string | null
): { width: number; height: number } | null {
  if (!logoDataUrl) return null;
  try {
    const props = doc.getImageProperties(logoDataUrl);
    if (props.width > 0 && props.height > 0) {
      const scale = Math.min(LOGO_MAX_WIDTH / props.width, LOGO_MAX_HEIGHT / props.height);
      return { width: props.width * scale, height: props.height * scale };
    }
  } catch {
    // fall through to the default box
  }
  return { width: LOGO_MAX_WIDTH, height: LOGO_MAX_HEIGHT };
}

/** Wrap `text` to at most `maxLines`, ellipsising the final line when it overflows. */
function clampToLines(doc: jsPDF, text: string, maxWidth: number, maxLines: number): string[] {
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(FOOTER_FONT_SIZE);

  const lines = doc.splitTextToSize(text, maxWidth) as string[];
  if (lines.length <= maxLines) return lines;

  const kept = lines.slice(0, maxLines);
  let last = kept[maxLines - 1];
  while (last.length > 1 && doc.getTextWidth(`${last}…`) > maxWidth) {
    last = last.slice(0, -1);
  }
  kept[maxLines - 1] = `${last.trimEnd()}…`;
  return kept;
}

function detectImageFormat(dataUrl: string): 'PNG' | 'JPEG' | 'GIF' | 'WEBP' {
  const match = /^data:image\/([a-zA-Z0-9+.-]+);/i.exec(dataUrl);
  const subtype = (match?.[1] || 'png').toLowerCase();
  if (subtype === 'jpeg' || subtype === 'jpg') return 'JPEG';
  if (subtype === 'gif') return 'GIF';
  if (subtype === 'webp') return 'WEBP';
  return 'PNG';
}

export function createPdfLayout(doc: jsPDF, options: PdfLayoutOptions): PdfLayoutWrapper {
  return new PdfLayoutWrapper(doc, options);
}
