export interface InquiryNode {
  code: string;
  name: string;
  children: InquiryNode[];
}

export interface InquiryFaq {
  id: string;
  process_code: string;
  process_name: string;
  subprocess_code?: string | null;
  subprocess_name?: string | null;
  nested_process_code?: string | null;
  nested_process_name?: string | null;
  question: string;
  answer: string;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface InquiryFaqPayload {
  path: string;
  question: string;
  answer: string;
  sort_order?: number;
}

export interface InquiryFaqList {
  items: InquiryFaq[];
  total: number;
}

export function inquiryFaqPath(faq: InquiryFaq): string {
  return faq.nested_process_code || faq.subprocess_code || faq.process_code;
}
