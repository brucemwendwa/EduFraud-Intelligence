import { ActivationForm } from '@/features/student/ActivationPage';

export default function StaffActivationPage() {
  return (
    <ActivationForm
      endpoint="/staff-activation"
      heading="Activate your staff account"
      intro="Create a password to access EduShield AI for your institution."
      welcome="Your staff account is ready."
    />
  );
}
