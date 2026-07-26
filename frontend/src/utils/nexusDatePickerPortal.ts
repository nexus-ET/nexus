/** Shared react-datepicker portal props so calendars escape overflow/sticky parents. */
export const nexusDatePickerPortalProps = {
  /** Full portal overlay — required in react-datepicker v9 to escape overflow clipping. */
  withPortal: true,
  portalId: 'nexus-datepicker-portal',
  popperClassName: 'nexus-datepicker-popper',
  popperProps: { strategy: 'fixed' as const },
};
