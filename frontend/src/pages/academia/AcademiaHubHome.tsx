import { Link } from 'react-router-dom';
import { ArrowRight, Building2, Globe2, GraduationCap } from 'lucide-react';
import { ACADEMIA_HUB_SECTIONS } from '../../config/academiaHubNav';

const sectionIcons = {
  geography: Globe2,
  institutions: Building2,
  framework: GraduationCap,
} as const;

const AcademiaHubHome: React.FC = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {ACADEMIA_HUB_SECTIONS.map(section => {
        const Icon = sectionIcons[section.key];
        return (
          <section
            key={section.key}
            className="rounded-2xl border border-border-subtle bg-card p-5 shadow-sm"
          >
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-accent/10 p-2 text-accent">
                <Icon size={18} />
              </div>
              <h2 className="text-lg font-bold text-text-main">{section.label}</h2>
            </div>
            {section.tabbed ? (
              <Link
                to={section.path}
                className="flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium text-text-main transition-colors hover:bg-surface-bg"
              >
                <span>Open {section.label}</span>
                <ArrowRight size={14} className="text-text-muted" />
              </Link>
            ) : (
              <ul className="space-y-2">
                {section.items.map(item => (
                  <li key={item.key}>
                    <Link
                      to={item.path}
                      className="flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium text-text-main transition-colors hover:bg-surface-bg"
                    >
                      <span>{item.label}</span>
                      <ArrowRight size={14} className="text-text-muted" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  </div>
);

export default AcademiaHubHome;
