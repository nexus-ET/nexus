import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  path?: string;
}

interface AcademiaBreadcrumbsProps {
  items: BreadcrumbItem[];
}

const AcademiaBreadcrumbs: React.FC<AcademiaBreadcrumbsProps> = ({ items }) => (
  <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1 text-sm text-text-muted">
    {items.map((item, index) => {
      const isLast = index === items.length - 1;
      return (
        <span key={`${item.label}-${index}`} className="inline-flex items-center gap-1">
          {index > 0 && <ChevronRight size={14} className="text-text-muted/60" />}
          {item.path && !isLast ? (
            <Link to={item.path} className="font-medium text-text-muted hover:text-accent transition-colors">
              {item.label}
            </Link>
          ) : (
            <span className={isLast ? 'font-semibold text-text-main' : 'font-medium'}>{item.label}</span>
          )}
        </span>
      );
    })}
  </nav>
);

export default AcademiaBreadcrumbs;
