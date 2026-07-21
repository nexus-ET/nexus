interface WizardFieldErrorProps {
  message?: string;
}

const WizardFieldError: React.FC<WizardFieldErrorProps> = ({ message }) => {
  if (!message) return null;
  return <p className="text-xs text-alert">{message}</p>;
};

export default WizardFieldError;
