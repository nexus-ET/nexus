/** Shared react-datepicker portal props so calendars escape overflow/sticky parents. */
export const nexusDatePickerPortalProps = {
  /** Full portal overlay — required in react-datepicker v9 to escape overflow clipping. */
  withPortal: true,
  portalId: 'nexus-datepicker-portal',
  popperClassName: 'nexus-datepicker-popper',
  popperProps: { strategy: 'fixed' as const },
};

/** Use for date pickers rendered inside high z-index modals (session drawer / score capture). */
export const nexusDatePickerModalPortalProps = {
  ...nexusDatePickerPortalProps,
  portalId: 'nexus-datepicker-modal-portal',
  popperClassName: 'nexus-datepicker-popper nexus-datepicker-popper--modal',
};
