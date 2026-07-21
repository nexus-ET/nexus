interface EntityStatusBadgeProps {
  isActive: boolean;
}

const EntityStatusBadge: React.FC<EntityStatusBadgeProps> = ({ isActive }) => (
  <span
    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
      isActive ? 'bg-success/15 text-success' : 'bg-alert/15 text-alert'
    }`}
  >
    {isActive ? 'Active' : 'Inactive'}
  </span>
);

export default EntityStatusBadge;
