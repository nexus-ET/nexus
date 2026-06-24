import React from 'react';
import { messageBubbleTextClass } from './chatEmotes';
import { renderHighlightedPlainText } from '../hooks/useHighlight';

const FENCED_CODE = /```([\s\S]*?)```/g;
const INLINE_CODE = /`([^`\n]+)`/g;
const TECHNICAL_ID =
  /\b[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\b/gi;

const appendPlainText = (
  nodes: React.ReactNode[],
  text: string,
  keyPrefix: string,
  highlightQuery?: string | null
) => {
  if (!highlightQuery?.trim()) {
    nodes.push(text);
    return;
  }
  nodes.push(...renderHighlightedPlainText(text, highlightQuery, keyPrefix));
};

const renderInlineSegments = (
  text: string,
  keyPrefix: string,
  highlightQuery?: string | null
): React.ReactNode[] => {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  const pattern = new RegExp(INLINE_CODE.source, 'g');
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(
        ...renderTechnicalIds(
          text.slice(lastIndex, match.index),
          `${keyPrefix}-t-${lastIndex}`,
          highlightQuery
        )
      );
    }
    nodes.push(
      <code key={`${keyPrefix}-inline-${match.index}`} className="chat-message-code rounded px-1">
        {match[1]}
      </code>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(
      ...renderTechnicalIds(text.slice(lastIndex), `${keyPrefix}-t-${lastIndex}`, highlightQuery)
    );
  }

  return nodes.length > 0 ? nodes : renderHighlightedPlainText(text, highlightQuery, keyPrefix);
};

const renderTechnicalIds = (
  text: string,
  keyPrefix: string,
  highlightQuery?: string | null
): React.ReactNode[] => {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  const pattern = new RegExp(TECHNICAL_ID.source, 'gi');
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      appendPlainText(nodes, text.slice(lastIndex, match.index), `${keyPrefix}-p-${lastIndex}`, highlightQuery);
    }
    nodes.push(
      <code key={`${keyPrefix}-id-${match.index}`} className="chat-message-code rounded px-1">
        {match[0]}
      </code>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    appendPlainText(nodes, text.slice(lastIndex), `${keyPrefix}-p-${lastIndex}`, highlightQuery);
  }

  return nodes.length > 0 ? nodes : renderHighlightedPlainText(text, highlightQuery, keyPrefix);
};

const renderPlainText = (
  text: string,
  keyPrefix: string,
  highlightQuery?: string | null
): React.ReactNode[] => renderInlineSegments(text, keyPrefix, highlightQuery);

export const renderMessageBody = (
  text: string,
  highlightQuery?: string | null
): React.ReactNode => {
  if (!text) return null;

  if (!text.includes('```')) {
    return <>{renderPlainText(text, 'plain', highlightQuery)}</>;
  }

  FENCED_CODE.lastIndex = 0;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = FENCED_CODE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(...renderPlainText(text.slice(lastIndex, match.index), `seg-${lastIndex}`, highlightQuery));
    }
    parts.push(
      <pre
        key={`fence-${match.index}`}
        className="chat-message-code my-1 overflow-x-auto rounded-md bg-black/5 px-2 py-1"
      >
        <code>{match[1].trim()}</code>
      </pre>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(...renderPlainText(text.slice(lastIndex), `seg-${lastIndex}`, highlightQuery));
  }

  return <>{parts}</>;
};

interface MessageBodyProps {
  text: string;
  className?: string;
  highlightQuery?: string | null;
}

const MessageBody: React.FC<MessageBodyProps> = ({ text, className = '', highlightQuery = null }) => (
  <p className={`${messageBubbleTextClass(text)} ${className}`.trim()}>
    {renderMessageBody(text, highlightQuery)}
  </p>
);

export default MessageBody;
